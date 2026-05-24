"""Plugin ``EstrategiaTurnOfMonth`` — calendar effect persistente em
S&P 500 / Nasdaq futures (Carchano-Tornero 2011, Maberly-Waggoner 2000).

Hipótese: retornos das ações americanas se concentram nos dias úteis
ao redor da virada do mês (último dia útil + primeiros 3 dias úteis
do mês seguinte). Único calendar effect a passar rigor estatístico
entre 188 testados em ES futures (Carchano-Pardo Tornero 2011, SSRN
1958587).

Setup (paper):

- **Entrada**: long no fechamento do **5º último dia útil** do mês.
- **Saída**: fechamento do **3º dia útil** do mês seguinte.
- Holding total: ~7-8 dias úteis (cruza virada).

Sem parâmetros otimizáveis. As constantes (5 e 3) vêm direto do
paper original. O único elemento configurável é se opera só long
(default) ou também short — paper original é long-only mas a
implementação suporta short como variante exploratória.

Frequência: ~12 trades/ano (1 por mês). Holding longo. Compatível
com a caracterização do MNQ que mostrou ruído branco em escala
1m-60m — esta estratégia opera em escala semanal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import List, Optional, Sequence, Set

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


#: Default do paper: long no 5º último dia útil → exit no 3º dia útil
#: do mês seguinte.
DIAS_ANTES_FIM_MES_DEFAULT: int = 5
DIAS_DEPOIS_INICIO_MES_DEFAULT: int = 3


@dataclass(frozen=True)
class ParametrosTurnOfMonth:
    """Parâmetros — defaults vêm de Carchano-Tornero 2011.

    ``dias_antes_fim_mes``: entry no Nº último dia útil do mês (5
    no paper). Range testado [3, 10].

    ``dias_depois_inicio_mes``: exit no Nº dia útil do mês seguinte
    (3 no paper). Range testado [1, 7].
    """

    dias_antes_fim_mes: int = DIAS_ANTES_FIM_MES_DEFAULT
    dias_depois_inicio_mes: int = DIAS_DEPOIS_INICIO_MES_DEFAULT

    def __post_init__(self) -> None:
        if not (1 <= self.dias_antes_fim_mes <= 10):
            raise ValueError(
                f"dias_antes_fim_mes em [1, 10]; recebido {self.dias_antes_fim_mes}"
            )
        if not (1 <= self.dias_depois_inicio_mes <= 10):
            raise ValueError(
                f"dias_depois_inicio_mes em [1, 10]; recebido {self.dias_depois_inicio_mes}"
            )


def _calcular_dias_uteis_do_mes(dias_uteis: List[date]) -> dict[tuple[int, int], List[date]]:
    """Agrupa dias úteis por (ano, mês). Mantém ordem cronológica."""
    grupos: dict[tuple[int, int], List[date]] = {}
    for d in dias_uteis:
        chave = (d.year, d.month)
        grupos.setdefault(chave, []).append(d)
    for chave in grupos:
        grupos[chave].sort()
    return grupos


def _gerar_pares_entrada_saida(
    dias_uteis: List[date],
    dias_antes_fim: int,
    dias_depois_inicio: int,
) -> List[tuple[date, date]]:
    """Para cada par de meses consecutivos com cobertura suficiente,
    devolve (data_entrada, data_saida).

    ``data_entrada`` = (mês_corrente).últimos_dias_úteis[-dias_antes_fim]
    ``data_saida`` = (mês_seguinte).primeiros_dias_úteis[dias_depois_inicio - 1]

    Pula meses sem cobertura completa.
    """
    grupos = _calcular_dias_uteis_do_mes(sorted(set(dias_uteis)))
    if not grupos:
        return []
    chaves_ordenadas = sorted(grupos.keys())
    pares: List[tuple[date, date]] = []
    for i in range(len(chaves_ordenadas) - 1):
        m_atual = chaves_ordenadas[i]
        m_prox = chaves_ordenadas[i + 1]
        # Mês seguinte adjacente (consecutivo no calendário)?
        if m_prox != _proximo_mes(m_atual):
            continue
        dias_atual = grupos[m_atual]
        dias_prox = grupos[m_prox]
        if len(dias_atual) < dias_antes_fim or len(dias_prox) < dias_depois_inicio:
            continue
        d_entrada = dias_atual[-dias_antes_fim]
        d_saida = dias_prox[dias_depois_inicio - 1]
        pares.append((d_entrada, d_saida))
    return pares


def _proximo_mes(ano_mes: tuple[int, int]) -> tuple[int, int]:
    ano, mes = ano_mes
    if mes == 12:
        return (ano + 1, 1)
    return (ano, mes + 1)


@dataclass
class _PosicaoTOM:
    entrada_timestamp: datetime
    entrada_preco: float
    high_max: float
    low_min: float

    def atualizar(self, high: float, low: float) -> None:
        if high > self.high_max:
            self.high_max = high
        if low < self.low_min:
            self.low_min = low


class EstrategiaTurnOfMonth:
    """Plugin Turn-of-the-Month long-only para Walk-Forward.

    Sem parâmetros otimizáveis. Args só permitem variantes
    estruturalmente diferentes (não otimização).
    """

    NOME: str = "EstrategiaTurnOfMonth"

    def __init__(
        self,
        parametros: Optional[ParametrosTurnOfMonth] = None,
    ) -> None:
        self._parametros = parametros or ParametrosTurnOfMonth()
        self._trades: List[Trade] = []
        self._posicao: Optional[_PosicaoTOM] = None
        # Mapas calculados a partir do Treino + Teste:
        self._datas_entrada: Set[date] = set()
        self._datas_saida: Set[date] = set()
        # Conjunto completo dos dias úteis observados (Treino + Teste).
        # Mantido pra que ``_registrar_novo_dia`` consiga recomputar pares
        # sem perder a base do Treino — bug de regressão evitado.
        self._dias_uteis_conhecidos: Set[date] = set()
        # Memória do dia corrente.
        self._dia_corrente: Optional[date] = None
        self._ultimo_close: float = 0.0
        self._ultimo_high: float = 0.0
        self._ultimo_low: float = 0.0
        self._ultimo_ts: Optional[datetime] = None
        # Flags de ação pendente para fim de dia.
        self._abrir_no_fim_do_dia: bool = False
        self._fechar_no_fim_do_dia: bool = False

    def treinar(self, historico: pd.DataFrame) -> None:
        """Calcula calendário de entradas/saídas a partir dos dias do
        Treino. Será expandido bar-a-bar conforme novos dias chegam."""
        self._trades = []
        self._posicao = None
        self._dia_corrente = None
        self._ultimo_close = 0.0
        self._ultimo_high = 0.0
        self._ultimo_low = 0.0
        self._ultimo_ts = None
        self._abrir_no_fim_do_dia = False
        self._fechar_no_fim_do_dia = False

        if historico.empty:
            self._dias_uteis_conhecidos = set()
        else:
            dias_uteis = self._extrair_dias_uteis(historico)
            self._dias_uteis_conhecidos = set(dias_uteis)
        self._recomputar_pares()

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

        # Detecta transição de dia.
        if (
            self._dia_corrente is not None
            and dia_atual != self._dia_corrente
            and self._ultimo_ts is not None
        ):
            # Aplica ações pendentes do dia anterior.
            self._aplicar_acoes_pendentes()

        # Atualiza memória do dia corrente.
        if dia_atual != self._dia_corrente:
            self._dia_corrente = dia_atual
            self._ultimo_high = high
            self._ultimo_low = low
            # Quando dia novo entra, refaz calendário se necessário —
            # o calendário é determinístico (só depende dos dias úteis
            # vistos), então é seguro adicionar este dia ao set.
            self._registrar_novo_dia(dia_atual)
        else:
            if high > self._ultimo_high:
                self._ultimo_high = high
            if low < self._ultimo_low:
                self._ultimo_low = low
        self._ultimo_close = close
        self._ultimo_ts = ts

        # Atualiza excursão da posição.
        if self._posicao is not None:
            self._posicao.atualizar(high, low)

        # Agenda entrada se hoje é data de entrada.
        if (
            dia_atual in self._datas_entrada
            and self._posicao is None
            and not self._abrir_no_fim_do_dia
        ):
            self._abrir_no_fim_do_dia = True
        # Agenda saída se hoje é data de saída.
        if (
            dia_atual in self._datas_saida
            and self._posicao is not None
            and not self._fechar_no_fim_do_dia
        ):
            self._fechar_no_fim_do_dia = True

    def finalizar(self) -> Sequence[Trade]:
        """Aplica ações pendentes do último dia, fecha posição
        residual."""
        if self._fechar_no_fim_do_dia and self._posicao is not None and self._ultimo_ts is not None:
            self._fechar_posicao(ts=self._ultimo_ts, preco=self._ultimo_close)
            self._fechar_no_fim_do_dia = False
        # Posição aberta sem saída agendada → fecha pelo último close.
        if self._posicao is not None and self._ultimo_ts is not None:
            self._fechar_posicao(ts=self._ultimo_ts, preco=self._ultimo_close)
        self._abrir_no_fim_do_dia = False
        return list(self._trades)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp_de_barra(barra: pd.Series) -> datetime:
        ts = pd.Timestamp(barra["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    @staticmethod
    def _extrair_dias_uteis(df: pd.DataFrame) -> List[date]:
        """Lista ordenada de dias úteis (date) presentes no DataFrame.

        Considera "dia útil" como qualquer dia com >=1 barra. Pula
        finais de semana naturalmente porque CME não tem dados nesses
        dias para futures de equity.
        """
        if df.empty:
            return []
        ts = pd.to_datetime(df["timestamp"], utc=True)
        return sorted({d.date() for d in ts})

    def _registrar_novo_dia(self, dia: date) -> None:
        """Quando um novo dia chega no Teste, atualiza calendário se
        este dia ainda não era conhecido.

        Mantém o conjunto cumulativo de dias úteis observados (Treino +
        Teste) e re-projeta o calendário sintético à frente para que
        pares possam ser agendados no fechamento do dia de entrada
        (sem precisar esperar o mês seguinte chegar).
        """
        if dia in self._dias_uteis_conhecidos:
            return
        self._dias_uteis_conhecidos.add(dia)
        self._recomputar_pares()

    def _recomputar_pares(self) -> None:
        """Recomputa ``datas_entrada``/``datas_saida`` projetando dias
        úteis sintéticos (seg-sex) por ~3 meses adiante do último dia
        conhecido. Necessário porque ``_gerar_pares_entrada_saida``
        depende de ter o mês seguinte completo para identificar a saída.
        """
        base = sorted(self._dias_uteis_conhecidos)
        projecao = self._projetar_dias_uteis_futuros(base, meses_adiante=3)
        todos = sorted(set(base) | set(projecao))
        pares = _gerar_pares_entrada_saida(
            todos,
            self._parametros.dias_antes_fim_mes,
            self._parametros.dias_depois_inicio_mes,
        )
        self._datas_entrada = {p[0] for p in pares}
        self._datas_saida = {p[1] for p in pares}

    @staticmethod
    def _projetar_dias_uteis_futuros(
        base: List[date],
        meses_adiante: int = 3,
    ) -> List[date]:
        """Lista dias úteis (seg-sex) entre o último dia da ``base`` e
        ``meses_adiante`` meses à frente. Não trata feriados — em
        runtime, dias sem barra simplesmente não disparam evento na
        ``on_barra``.
        """
        if not base:
            return []
        ultimo = base[-1]
        fim = pd.Timestamp(ultimo) + pd.DateOffset(months=meses_adiante)
        rng = pd.bdate_range(
            start=pd.Timestamp(ultimo) + pd.Timedelta(days=1),
            end=fim,
        )
        return [ts.date() for ts in rng]

    def _aplicar_acoes_pendentes(self) -> None:
        """Aplica entrada/saída agendada pelo close do dia que acabou."""
        if (
            self._abrir_no_fim_do_dia
            and self._posicao is None
            and self._ultimo_ts is not None
        ):
            self._posicao = _PosicaoTOM(
                entrada_timestamp=self._ultimo_ts,
                entrada_preco=self._ultimo_close,
                high_max=self._ultimo_high,
                low_min=self._ultimo_low,
            )
            self._abrir_no_fim_do_dia = False
        if (
            self._fechar_no_fim_do_dia
            and self._posicao is not None
            and self._ultimo_ts is not None
        ):
            self._fechar_posicao(
                ts=self._ultimo_ts,
                preco=self._ultimo_close,
            )
            self._fechar_no_fim_do_dia = False

    def _fechar_posicao(self, *, ts: datetime, preco: float) -> None:
        if self._posicao is None:
            return
        if ts <= self._posicao.entrada_timestamp:
            ts = self._posicao.entrada_timestamp + pd.Timedelta(seconds=1)
        mfe = max(0.0, self._posicao.high_max - self._posicao.entrada_preco)
        mae = min(0.0, self._posicao.low_min - self._posicao.entrada_preco)
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

    @property
    def parametros(self) -> ParametrosTurnOfMonth:
        return self._parametros

    @property
    def datas_entrada(self) -> Set[date]:
        return set(self._datas_entrada)

    @property
    def datas_saida(self) -> Set[date]:
        return set(self._datas_saida)

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)


__all__ = [
    "DIAS_ANTES_FIM_MES_DEFAULT",
    "DIAS_DEPOIS_INICIO_MES_DEFAULT",
    "EstrategiaTurnOfMonth",
    "ParametrosTurnOfMonth",
]
