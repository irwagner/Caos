"""Plugin ``EstrategiaPreFomcDrift`` para o Walk-Forward.

Implementa a estratégia long-flat baseada na anomalia documentada por
Lucca-Moench (2015) e replicada em fontes independentes até dez/2024.

Tese declarada (não aprendida do dado, sem parâmetros otimizáveis):

- Entrar **long** no fechamento do dia útil ANTERIOR à data agendada
  do FOMC meeting.
- Sair (fechar a posição) no fechamento do dia da reunião.
- Não opera nos demais dias.

Decisões de implementação:

- O plugin é puramente **streaming**: vê uma barra por vez, sem
  peek de barras futuras. Detecta "fim do dia D-1" via transição de
  data civil — quando uma barra com data DIFERENTE chega, sabemos
  que o dia anterior acabou e usamos o close memorizado da última
  barra desse dia anterior como preço de entrada/saída.
- Funciona igualmente em granularidade ``1m`` e ``day``.
- Em ``day``, cada dia tem 1 barra, então a "última barra do dia"
  é trivialmente a única barra. Ainda usamos o mesmo mecanismo
  de transição.
- Se a janela WF terminar no meio de uma ação pendente (entrada
  agendada mas dia D não chegou; ou posição aberta mas dia D não
  bateu), a ação é abortada e nenhum trade fictício é emitido.

Calendário FOMC vem de CSV com colunas
``data_anuncio,duracao_dias,tem_press_conference,fonte``. Apenas
``data_anuncio`` é usada nesta versão; as demais ficam disponíveis
para variantes futuras (ex.: filtrar só meetings com press
conference, conforme Lucca-Moench 2018).

Esta estratégia não tem fricção — quem aplica slippage e comissão é
:class:`CustosOperacionais` no :class:`BacktestRunner`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


# ---------------------------------------------------------------------------
# Modelos auxiliares
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JanelaFomc:
    """Par de datas civis (UTC) ``(dia_antes, dia_anuncio)`` de um meeting."""

    dia_antes: date
    dia_anuncio: date


@dataclass
class _PosicaoAberta:
    entrada_timestamp: datetime
    entrada_preco: float
    high_max: float
    low_min: float

    def atualizar_excursoes(self, high: float, low: float) -> None:
        if high > self.high_max:
            self.high_max = high
        if low < self.low_min:
            self.low_min = low


# ---------------------------------------------------------------------------
# Calendário FOMC
# ---------------------------------------------------------------------------


def carregar_meetings_fomc(caminho_csv: Path) -> List[JanelaFomc]:
    """Lê o CSV de meetings e devolve a lista de :class:`JanelaFomc`.

    O CSV deve ter cabeçalho com pelo menos a coluna ``data_anuncio``
    (formato ISO ``YYYY-MM-DD``). Demais colunas são ignoradas nesta
    versão.

    O ``dia_antes`` é calculado como o dia útil estritamente anterior
    a ``data_anuncio`` (pula sábado/domingo). Feriados não são
    tratados aqui — se a barra do dia útil esperado não existir nos
    dados, o plugin descarta a janela em runtime.
    """
    caminho = Path(caminho_csv)
    if not caminho.is_file():
        raise FileNotFoundError(
            f"calendário FOMC ausente: {caminho}. "
            "Esperado em dados/macros/fomc_meetings.csv."
        )
    janelas: List[JanelaFomc] = []
    with caminho.open("r", encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        if "data_anuncio" not in (leitor.fieldnames or ()):
            raise ValueError(
                f"CSV {caminho} deve conter coluna 'data_anuncio'; "
                f"recebido {leitor.fieldnames}"
            )
        for linha in leitor:
            bruto = (linha.get("data_anuncio") or "").strip()
            if not bruto:
                continue
            try:
                d_anuncio = date.fromisoformat(bruto)
            except ValueError as exc:
                raise ValueError(
                    f"data_anuncio inválida em {caminho}: {bruto!r} ({exc})"
                ) from exc
            janelas.append(
                JanelaFomc(
                    dia_antes=_dia_util_anterior(d_anuncio),
                    dia_anuncio=d_anuncio,
                )
            )
    janelas.sort(key=lambda j: j.dia_anuncio)
    return janelas


def _dia_util_anterior(d: date) -> date:
    """Dia útil estritamente anterior a ``d`` (pula fim de semana)."""
    candidato = pd.Timestamp(d) - pd.Timedelta(days=1)
    while candidato.weekday() >= 5:
        candidato -= pd.Timedelta(days=1)
    return candidato.date()


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class EstrategiaPreFomcDrift:
    """Estratégia long-flat baseada no Pre-FOMC announcement drift.

    Sem parâmetros otimizáveis. O CSV de meetings FOMC é argumento
    obrigatório do construtor.

    Parameters
    ----------
    caminho_meetings_csv:
        Path do CSV com calendário FOMC.
    """

    NOME: str = "EstrategiaPreFomcDrift"

    def __init__(self, caminho_meetings_csv: Path) -> None:
        self._caminho_meetings_csv = Path(caminho_meetings_csv)
        self._janelas_fomc: List[JanelaFomc] = carregar_meetings_fomc(
            self._caminho_meetings_csv
        )
        self._datas_antes: Set[date] = {j.dia_antes for j in self._janelas_fomc}
        self._datas_anuncio: Set[date] = {
            j.dia_anuncio for j in self._janelas_fomc
        }

        self._trades: List[Trade] = []
        self._posicao: Optional[_PosicaoAberta] = None

        # Memória do dia corrente. Atualizada bar-a-bar.
        self._dia_corrente: Optional[date] = None
        self._ultimo_close: float = 0.0
        self._ultimo_high: float = 0.0
        self._ultimo_low: float = 0.0
        self._ultimo_ts: Optional[datetime] = None

        # Flags de decisão pendente — acionadas na PRÓXIMA transição
        # de dia, usando o close memorizado do dia que terminou.
        self._abrir_no_fim_do_dia: bool = False
        self._fechar_no_fim_do_dia: bool = False

    # ------------------------------------------------------------------
    # Protocol Estrategia
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        """Reseta estado interno entre janelas WF."""
        self._trades = []
        self._posicao = None
        self._dia_corrente = None
        self._ultimo_close = 0.0
        self._ultimo_high = 0.0
        self._ultimo_low = 0.0
        self._ultimo_ts = None
        self._abrir_no_fim_do_dia = False
        self._fechar_no_fim_do_dia = False

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        ts = self._timestamp_de_barra(barra)
        dia_atual = ts.date()
        close = float(barra["close"])
        high = float(barra["high"])
        low = float(barra["low"])

        # Detecta transição de dia. Quando o dia muda, o dia anterior
        # acabou; aplica decisões agendadas usando o close memorizado.
        if (
            self._dia_corrente is not None
            and dia_atual != self._dia_corrente
            and self._ultimo_ts is not None
        ):
            self._aplicar_acoes_pendentes()

        # Atualiza memória do dia corrente.
        if dia_atual != self._dia_corrente:
            self._dia_corrente = dia_atual
            self._ultimo_high = high
            self._ultimo_low = low
        else:
            if high > self._ultimo_high:
                self._ultimo_high = high
            if low < self._ultimo_low:
                self._ultimo_low = low
        self._ultimo_close = close
        self._ultimo_ts = ts

        # Atualiza excursão da posição corrente (se aberta) com a
        # barra recém-vista.
        if self._posicao is not None:
            self._posicao.atualizar_excursoes(high, low)

        # Agenda decisões para serem aplicadas no FIM deste dia.
        if (
            dia_atual in self._datas_antes
            and self._posicao is None
            and not self._abrir_no_fim_do_dia
        ):
            self._abrir_no_fim_do_dia = True
        if (
            dia_atual in self._datas_anuncio
            and self._posicao is not None
            and not self._fechar_no_fim_do_dia
        ):
            self._fechar_no_fim_do_dia = True

    def finalizar(self) -> Sequence[Trade]:
        """Aplica ações pendentes do último dia visto e fecha posição.

        Comportamento defensivo:

        - Se o último dia visto era ``dia_antes`` e a entrada estava
          agendada mas o dia D nunca chegou (janela WF terminou no
          meio), a entrada é descartada — não emitimos trade
          fictício.
        - Se a posição está aberta e a saída agendada nunca foi
          atingida, fecha pelo último close memorizado para que
          ResultadoJanela tenha PnL realista (vs. carry para outra
          janela WF, que não suportamos).
        """
        # Aplica fechamento pendente que possa estar acumulado.
        if self._fechar_no_fim_do_dia and self._posicao is not None and self._ultimo_ts is not None:
            self._fechar(ts=self._ultimo_ts, preco=self._ultimo_close)
            self._fechar_no_fim_do_dia = False

        # Posição ainda aberta (saída agendada não bateu) — fecha pelo
        # último close conhecido.
        if self._posicao is not None and self._ultimo_ts is not None:
            self._fechar(ts=self._ultimo_ts, preco=self._ultimo_close)

        # Entrada pendente que nunca virou trade — descartada.
        self._abrir_no_fim_do_dia = False
        return list(self._trades)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp_de_barra(barra: pd.Series) -> datetime:
        ts = pd.Timestamp(barra["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def _aplicar_acoes_pendentes(self) -> None:
        """Aplica ações agendadas no fim do dia que acabou.

        Chamado quando uma barra de NOVO dia chega — ``self._ultimo_*``
        ainda guardam os valores da última barra do dia anterior.
        """
        if self._abrir_no_fim_do_dia and self._posicao is None and self._ultimo_ts is not None:
            self._abrir(
                ts=self._ultimo_ts,
                preco=self._ultimo_close,
                high=self._ultimo_high,
                low=self._ultimo_low,
            )
            self._abrir_no_fim_do_dia = False
        if self._fechar_no_fim_do_dia and self._posicao is not None and self._ultimo_ts is not None:
            self._fechar(
                ts=self._ultimo_ts,
                preco=self._ultimo_close,
            )
            self._fechar_no_fim_do_dia = False

    def _abrir(
        self,
        *,
        ts: datetime,
        preco: float,
        high: float,
        low: float,
    ) -> None:
        self._posicao = _PosicaoAberta(
            entrada_timestamp=ts,
            entrada_preco=preco,
            high_max=high,
            low_min=low,
        )

    def _fechar(self, *, ts: datetime, preco: float) -> None:
        if self._posicao is None:
            return
        mfe = max(0.0, self._posicao.high_max - self._posicao.entrada_preco)
        mae = min(0.0, self._posicao.low_min - self._posicao.entrada_preco)
        if ts <= self._posicao.entrada_timestamp:
            ts = self._posicao.entrada_timestamp + pd.Timedelta(seconds=1)
        self._trades.append(
            Trade(
                entrada_timestamp=self._posicao.entrada_timestamp,
                saida_timestamp=ts,
                entrada_preco=self._posicao.entrada_preco,
                saida_preco=preco,
                lado="long",
                contratos=1,
                mfe_pontos=mfe,
                mae_pontos=mae,
            )
        )
        self._posicao = None

    # ------------------------------------------------------------------
    # Acessores
    # ------------------------------------------------------------------

    @property
    def janelas_fomc(self) -> Sequence[JanelaFomc]:
        return tuple(self._janelas_fomc)

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)


__all__ = [
    "EstrategiaPreFomcDrift",
    "JanelaFomc",
    "carregar_meetings_fomc",
]
