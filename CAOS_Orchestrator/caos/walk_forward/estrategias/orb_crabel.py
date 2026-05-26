"""Plugin ``EstrategiaORBCrabel`` — variante NR4/NR7 da ORB.

Implementa a versão ORB original de Toby Crabel (1990): só opera ORB
em dias seguintes a um **NR4** (Narrow Range 4) ou **NR7** (Narrow Range
7) — o dia de hoje só é elegível se o dia anterior teve range diário
≤ menor range dos últimos 4 (ou 7) dias.

Hipótese de Crabel: **compressão precede expansão.** Após um dia de
range estreito, o próximo dia tende a ter movimento direcional
desproporcionalmente maior, e o ORB intraday tem follow-through mais
consistente.

Decisões de implementação:

- Reusa toda a lógica de :class:`EstrategiaORB` por composição interna —
  apenas filtra os dias em que opera. Nada de duplicação de código.
- O cálculo de NR usa o range diário (high-day - low-day) calculado a
  partir das barras. Cada dia útil é uma observação. Janelas N=4 (NR4)
  ou N=7 (NR7) são fixas — não há parâmetro otimizável.
- O histórico de Treino fornece os primeiros N dias de range; durante o
  Teste, o filtro é atualizado bar-a-bar conforme novos dias são vistos.
- Quando um dia não passa o filtro NR4/NR7, todas as barras desse dia
  são repassadas ao plugin interno **mas** com `range_minimo_pontos`
  efetivamente impossível de bater — ou seja, o plugin "vê" o dia mas
  nunca emite trade. Implementação simples: bloqueamos `on_barra` se
  o dia atual não está na lista de dias elegíveis.

Sem nenhum parâmetro otimizável — `usar_nr4_ou_nr7="nr7"` (default) ou
`"nr4"` é escolha discreta que vem do paper original.
"""

from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional, Sequence, Set

import pandas as pd

from caos.walk_forward.estrategias.orb import EstrategiaORB
from caos.walk_forward.estrategias.orb_logica import ParametrosORB
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


#: Modo de filtro NR. ``"nr4"`` = janela de 4 dias. ``"nr7"`` = 7 dias.
ModoNR = Literal["nr4", "nr7"]


#: Numero minimo de barras de minuto que um dia precisa ter para ser
#: contado como dia util valido pelo filtro NR (Decisao 2026-05-26-01).
#: Pregao regular MNQ = 1380 barras (23h * 60min); domingo Globex
#: tem ~120-300 barras; feriado parcial tem ~430-720. Limiar 300
#: descarta especificamente abertura noturna de fim de semana.
MIN_BARRAS_DIA_VALIDO: int = 300


def _calcular_range_diario(historico: pd.DataFrame) -> dict[date, float]:
    """Devolve mapa ``data -> range`` (em pontos) por dia útil válido.

    ``historico`` deve seguir o schema canônico do
    :mod:`caos.walk_forward.data_reader`. Sem barras → mapa vazio.

    **Filtro de dia válido (Decisao 2026-05-26-01)**:
    Só conta dias que satisfaçam AMBOS:

    - ``timestamp.dt.dayofweek < 5`` (segunda a sexta — exclui sábado e
      domingo, que no MNQ representam abertura noturna do Globex e
      têm sessão truncada de 3-5 horas).
    - Pelo menos ``MIN_BARRAS_DIA_VALIDO`` barras de minuto. Pregão
      regular MNQ = 1380 barras. Limiar de 300 barras (5h) descarta
      dias parciais (ex: feriado parcial com fechamento muito
      antecipado, abertura tardia por falha técnica) que gerariam
      NR7 falso-positivo.

    Sem este filtro, domingos com range artificialmente pequeno (~120-
    200 pts vs. ~500 pts de pregão regular) viram NR7 sistemáticos e
    toda segunda-feira é elegível espuriamente. Bug descoberto após
    replay NT8 28/01-13/03/2026 (commit d2ff9d6).
    """
    if "timestamp" not in historico.columns or historico.empty:
        return {}
    df = historico.copy()
    # Filtro 1: descarta sabado e domingo.
    if df["timestamp"].dt.tz is None:
        df = df[df["timestamp"].dt.dayofweek < 5].copy()
    else:
        df = df[df["timestamp"].dt.dayofweek < 5].copy()
    if df.empty:
        return {}
    df["dia"] = df["timestamp"].dt.date
    por_dia = df.groupby("dia").agg(
        high_max=("high", "max"),
        low_min=("low", "min"),
        n_barras=("high", "count"),
    )
    # Filtro 2: descarta dias com sessao truncada (< 300 barras).
    por_dia = por_dia[por_dia["n_barras"] >= MIN_BARRAS_DIA_VALIDO]
    return {
        d: float(row["high_max"] - row["low_min"])
        for d, row in por_dia.iterrows()
    }


def _dias_apos_nr(
    ranges_por_dia: dict[date, float],
    janela: int,
) -> tuple[Set[date], bool]:
    """Devolve ``(elegiveis, proximo_dia_eh_elegivel)``.

    Um dia ``d`` está em NR-janela se ``range[d]`` é o **menor** entre
    os ``janela`` últimos dias úteis (incluindo ``d``). O dia útil
    seguinte fica elegível para operar ORB.

    Retorna:
    - ``elegiveis``: conjunto de dias **conhecidos** que vêm logo após
      um NR-janela. Não inclui o "próximo dia desconhecido" porque ele
      ainda não tem data definida.
    - ``proximo_dia_eh_elegivel``: ``True`` se o ÚLTIMO dia em
      ``ranges_por_dia`` é um NR-janela, sinalizando que o próximo dia
      útil que aparecer (durante o Teste) deve ser tratado como
      elegível. Crítico para WF onde o filtro é calculado no Treino e
      o Teste começa imediatamente depois.
    """
    if janela < 2:
        raise ValueError(f"janela NR deve ser >= 2; recebido {janela}")
    dias_ordenados = sorted(ranges_por_dia.keys())
    if len(dias_ordenados) < janela:
        return set(), False
    elegiveis: Set[date] = set()
    # i percorre de janela-1 até len-1 (inclusive último dia).
    for i in range(janela - 1, len(dias_ordenados)):
        slice_dias = dias_ordenados[i - janela + 1 : i + 1]
        ranges_janela = [ranges_por_dia[d] for d in slice_dias]
        eh_nr = ranges_por_dia[dias_ordenados[i]] == min(ranges_janela)
        if not eh_nr:
            continue
        if i + 1 < len(dias_ordenados):
            elegiveis.add(dias_ordenados[i + 1])
    # Próximo dia (desconhecido) é elegível se o último dia atual é NR.
    if len(dias_ordenados) >= janela:
        ultimo = dias_ordenados[-1]
        slice_ultimo = dias_ordenados[-janela:]
        ranges_ultimo = [ranges_por_dia[d] for d in slice_ultimo]
        proximo_dia_elegivel = ranges_por_dia[ultimo] == min(ranges_ultimo)
    else:
        proximo_dia_elegivel = False
    return elegiveis, proximo_dia_elegivel


class EstrategiaORBCrabel:
    """ORB filtrada por NR4 ou NR7 (Crabel 1990).

    Composição com :class:`EstrategiaORB` interna — todas as regras de
    range, breakout, stop, alvo e cooldown são reusadas. Esta classe
    apenas adiciona o filtro de dias elegíveis.
    """

    NOME: str = "EstrategiaORBCrabel"

    def __init__(
        self,
        modo_nr: ModoNR = "nr7",
        parametros: Optional[ParametrosORB] = None,
    ) -> None:
        if modo_nr not in ("nr4", "nr7"):
            raise ValueError(
                f"modo_nr deve ser 'nr4' ou 'nr7'; recebido {modo_nr!r}"
            )
        self._modo_nr: ModoNR = modo_nr
        self._janela_nr: int = 4 if modo_nr == "nr4" else 7
        self._orb_interna = EstrategiaORB(parametros=parametros)
        self._ranges_por_dia: dict[date, float] = {}
        self._dias_elegiveis: Set[date] = set()
        # Flag: o próximo dia ainda não-visto é elegível (último dia
        # do histórico é NR).
        self._proximo_dia_elegivel: bool = False
        # Memória do dia corrente para atualizar ranges_por_dia bar-a-bar
        # durante o Teste.
        self._dia_corrente: Optional[date] = None
        self._high_corrente: float = float("-inf")
        self._low_corrente: float = float("inf")
        # Contador de barras do dia corrente (Decisao 2026-05-26-01).
        self._barras_dia_corrente: int = 0

    # ------------------------------------------------------------------
    # Protocol Estrategia
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        """Calcula ranges dos dias de Treino e prepara filtro NR."""
        self._orb_interna.treinar(historico)
        self._ranges_por_dia = _calcular_range_diario(historico)
        self._dias_elegiveis, self._proximo_dia_elegivel = _dias_apos_nr(
            self._ranges_por_dia, self._janela_nr
        )
        self._dia_corrente = None
        self._high_corrente = float("-inf")
        self._low_corrente = float("inf")
        self._barras_dia_corrente = 0

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        # Atualização do dia corrente (registra range do dia anterior
        # quando muda de data).
        ts = pd.Timestamp(barra["timestamp"])
        dia_atual = ts.date()
        if self._dia_corrente is None:
            self._dia_corrente = dia_atual
            self._high_corrente = float(barra["high"])
            self._low_corrente = float(barra["low"])
            self._barras_dia_corrente = 1
            # Se o filtro do treino sinalizou "próximo dia é elegível",
            # adiciona ESTE dia (o primeiro do Teste) ao conjunto —
            # APENAS se o dia atual passa o filtro de validade.
            if self._proximo_dia_elegivel and self._dia_eh_valido(dia_atual):
                self._dias_elegiveis.add(dia_atual)
                self._proximo_dia_elegivel = False
            elif self._proximo_dia_elegivel and not self._dia_eh_valido(dia_atual):
                # Dia atual e invalido (sabado/domingo). Mantem flag
                # ativa para o proximo dia util valido.
                pass
        elif dia_atual != self._dia_corrente:
            # Fecha o dia anterior: registra range APENAS se valido.
            if (
                self._barras_dia_corrente >= MIN_BARRAS_DIA_VALIDO
                and self._dia_eh_valido(self._dia_corrente)
            ):
                self._ranges_por_dia[self._dia_corrente] = (
                    self._high_corrente - self._low_corrente
                )
                self._dias_elegiveis, prox = _dias_apos_nr(
                    self._ranges_por_dia, self._janela_nr
                )
                # Se o ÚLTIMO dia (recém-fechado) é NR, o dia que está
                # entrando agora é elegível — apenas se valido.
                if prox and self._dia_eh_valido(dia_atual):
                    self._dias_elegiveis.add(dia_atual)
                elif prox and not self._dia_eh_valido(dia_atual):
                    self._proximo_dia_elegivel = True
            # Inicia novo dia.
            self._dia_corrente = dia_atual
            self._high_corrente = float(barra["high"])
            self._low_corrente = float(barra["low"])
            self._barras_dia_corrente = 1
        else:
            # Acumula no dia corrente.
            h = float(barra["high"])
            ll = float(barra["low"])
            if h > self._high_corrente:
                self._high_corrente = h
            if ll < self._low_corrente:
                self._low_corrente = ll
            self._barras_dia_corrente += 1

        # Filtro: se o dia atual NÃO é elegível, barra é silenciosamente
        # consumida sem invocar a ORB interna.
        if dia_atual not in self._dias_elegiveis:
            return

        self._orb_interna.on_barra(barra, contexto)

    @staticmethod
    def _dia_eh_valido(dia: date) -> bool:
        """True se o dia é segunda a sexta (0-4 em ``date.weekday()``).

        Decisao 2026-05-26-01: descarta sábado/domingo. Usado em
        conjunto com :data:`MIN_BARRAS_DIA_VALIDO` no fechamento de dia.
        """
        return dia.weekday() < 5

    def finalizar(self) -> Sequence[Trade]:
        return self._orb_interna.finalizar()

    # ------------------------------------------------------------------
    # Acessores (testes / debug)
    # ------------------------------------------------------------------

    @property
    def modo_nr(self) -> ModoNR:
        return self._modo_nr

    @property
    def dias_elegiveis(self) -> Set[date]:
        # Cópia defensiva.
        return set(self._dias_elegiveis)

    @property
    def trades(self) -> Sequence[Trade]:
        return self._orb_interna.trades


__all__ = [
    "EstrategiaORBCrabel",
    "ModoNR",
]
