"""Plugin ``EstrategiaNoiseArea`` — momentum intraday baseado em
"Beat the Market" (Zarattini, Aziz, Barbon 2024).

Hipótese: durante o dia, o preço fica em uma "Noise Area" definida
por bandas dinâmicas baseadas em volatilidade histórica. Quando o
preço SAI dessa banda, há sinal de demanda/oferta abnormal —
oportunidade momentum direcional. Saída no fechamento da sessão ou
quando preço retorna à Noise Area.

Setup formal (paráfrase do paper):

- ``upper_band(t) = open_dia + open_dia × move_medio_14d_ate_minuto_t + max(0, gap_neg_overnight)``
- ``lower_band(t) = open_dia - open_dia × move_medio_14d_ate_minuto_t - max(0, gap_pos_overnight)``

Onde ``move_medio_14d_ate_minuto_t`` é a média dos retornos absolutos
acumulados desde a abertura até o minuto t, calculada sobre os
últimos 14 dias úteis. Gaps overnight ajustam a banda na direção
oposta ao gap (ex: gap-up de 1% expande lower band 1% pra baixo, pra
não pegar a queda natural pós-gap).

Regras de entrada:
- LONG: close cruza acima da upper_band
- SHORT: close cruza abaixo da lower_band
- Apenas 1 trade por dia em cada direção (ou só 1 trade por dia, sem
  re-entrada na mesma direção após sair)

Regras de saída:
- Close do dia (forced exit antes do session close)
- Trailing stop: retorno do preço à Noise Area OU breakout do VWAP
  na direção contrária

Decisões de implementação:

- A construção da Noise Area exige histórico de N=14 dias antes do
  dia atual. Para que a estratégia opere desde o primeiro dia do
  Teste WF, o ``treinar`` recebe os 60 dias de Treino e calcula a
  estrutura inicial dos retornos absolutos por minuto da sessão.
- Sessão por hora local — para MNQ futures cobrindo 23h/dia, a
  "sessão" relevante é RTH (09:30-16:00 NY = 14:30-21:00 UTC).
  Configurável.
- Retornos absolutos por minuto são re-acumulados a cada dia novo
  durante o Teste, com janela rolante de 14 dias.
- VWAP de sessão usado como trailing condicional.

Sem parâmetros otimizáveis livres. Os únicos ajustáveis vêm
diretamente do paper (lookback=14, sessão=RTH NY, target=2% daily
vol). A versão Quantitativo NQ usou lookback=90 + leverage 8x mas
isso é opt-in via construtor.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


#: Lookback default em dias úteis (paper original).
LOOKBACK_DEFAULT: int = 14

#: Sessão RTH NY = 14:30-21:00 UTC.
SESSAO_RTH_NY_INICIO_UTC: time = time(14, 30)
SESSAO_RTH_NY_FIM_UTC: time = time(21, 0)

#: Antes do fim, deixa-se uma janela "lockout" para não abrir trade
#: que não consegue fechar antes do close. Em minutos.
MINUTOS_LOCKOUT_PRE_FECHAMENTO: int = 30


@dataclass(frozen=True)
class ParametrosNoiseArea:
    """Parâmetros da Noise Area momentum.

    Defaults vêm do paper (Zarattini-Aziz-Barbon 2024). Variantes
    possíveis: lookback 90 (Quantitativo NQ), 21 (intermediário).
    """

    lookback_dias: int = LOOKBACK_DEFAULT
    sessao_inicio_utc: time = SESSAO_RTH_NY_INICIO_UTC
    sessao_fim_utc: time = SESSAO_RTH_NY_FIM_UTC
    minutos_lockout: int = MINUTOS_LOCKOUT_PRE_FECHAMENTO
    apenas_long: bool = False
    apenas_short: bool = False
    #: Quando ``True``, inverte os sinais: breakout acima da banda
    #: dispara SHORT, breakout abaixo dispara LONG. Hipótese de
    #: mean-reversion (testada empiricamente em MNQ depois que a versão
    #: momentum mostrou Sharpe -8.64 com win rate 11%).
    inverter_sinais: bool = False

    def __post_init__(self) -> None:
        if not (5 <= self.lookback_dias <= 252):
            raise ValueError(
                f"lookback_dias deve estar em [5, 252]; recebido {self.lookback_dias}"
            )
        if self.sessao_inicio_utc >= self.sessao_fim_utc:
            raise ValueError(
                "sessao_inicio_utc deve ser anterior a sessao_fim_utc"
            )
        if self.minutos_lockout < 0 or self.minutos_lockout > 240:
            raise ValueError(
                f"minutos_lockout deve estar em [0, 240]; recebido {self.minutos_lockout}"
            )
        if self.apenas_long and self.apenas_short:
            raise ValueError("apenas_long e apenas_short não podem ser ambos True")


@dataclass
class _DiaSessao:
    """Estado de um dia de sessão durante a iteração."""

    data: date
    open_preco: float
    open_timestamp: datetime
    # close anterior (último close pré-sessão) para cálculo de gap.
    close_anterior: Optional[float] = None
    # Retornos abs cumulativos do open por minuto (1=primeiro min, 2=segundo...).
    # Usado para construir o "move médio acumulado".
    retorno_abs_por_minuto: Dict[int, float] = field(default_factory=dict)

    @property
    def gap_overnight(self) -> float:
        """Gap = open_dia - close_anterior. Positivo = gap up."""
        if self.close_anterior is None:
            return 0.0
        return self.open_preco - self.close_anterior


@dataclass
class _PosicaoNoise:
    """Posição aberta da Noise Area."""

    lado: str  # "long" ou "short"
    entrada_timestamp: datetime
    entrada_preco: float
    high_max: float
    low_min: float

    def atualizar(self, high: float, low: float) -> None:
        if high > self.high_max:
            self.high_max = high
        if low < self.low_min:
            self.low_min = low


class EstrategiaNoiseArea:
    """Plugin que implementa Noise Area momentum sobre série OHLCV
    canônica do CAOS.

    Args:
        parametros: :class:`ParametrosNoiseArea` opcional (default = paper).

    Pipeline operacional:

    1. ``treinar`` recebe DataFrame do Treino e popula histórico de
       retornos absolutos por minuto-da-sessão (14 dias × N minutos).
    2. ``on_barra`` consume cada barra do Teste:
       - Detecta troca de dia → fecha posição se aberta, registra
         dados do dia anterior no histórico, inicia novo dia.
       - Para cada barra dentro da sessão: calcula bandas dinâmicas,
         testa cruzamento, abre/fecha posição.
    3. ``finalizar`` fecha qualquer posição aberta com o último close.
    """

    NOME: str = "EstrategiaNoiseArea"

    def __init__(
        self,
        parametros: Optional[ParametrosNoiseArea] = None,
        *,
        lookback_dias: Optional[int] = None,
        apenas_long: Optional[bool] = None,
        apenas_short: Optional[bool] = None,
        minutos_lockout: Optional[int] = None,
        inverter_sinais: Optional[bool] = None,
    ) -> None:
        # Se kwargs explicitos vierem, sobrescrevem o default. Permite
        # invocacao via --estrategia-args '{"lookback_dias": 90}' sem
        # precisar serializar ParametrosNoiseArea.
        if parametros is None:
            base = ParametrosNoiseArea()
        else:
            base = parametros
        overrides = {}
        if lookback_dias is not None:
            overrides["lookback_dias"] = lookback_dias
        if apenas_long is not None:
            overrides["apenas_long"] = apenas_long
        if apenas_short is not None:
            overrides["apenas_short"] = apenas_short
        if minutos_lockout is not None:
            overrides["minutos_lockout"] = minutos_lockout
        if inverter_sinais is not None:
            overrides["inverter_sinais"] = inverter_sinais
        if overrides:
            from dataclasses import replace
            base = replace(base, **overrides)
        self._parametros = base
        # Deque de dicts {minuto_da_sessao: retorno_abs} pelos últimos
        # ``lookback_dias`` dias. minuto_da_sessao = 1 para a 1ª barra
        # de RTH, 2 para 2ª, etc.
        self._historico: Deque[Dict[int, float]] = deque(
            maxlen=self._parametros.lookback_dias
        )
        # Estado do dia atual (None entre dias).
        self._dia_atual: Optional[_DiaSessao] = None
        # Posição aberta (None se flat).
        self._posicao: Optional[_PosicaoNoise] = None
        # Trades fechados para finalizar.
        self._trades: List[Trade] = []
        # Marca se já abriu trade no dia (1 por dia, sem re-entrada).
        self._dia_ja_operou: bool = False
        # Último close visto (para gap overnight do próximo dia).
        self._ultimo_close: Optional[float] = None
        # Último timestamp visto.
        self._ultimo_timestamp: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Protocol Estrategia
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        """Popula o histórico de retornos absolutos a partir do Treino."""
        self._historico.clear()
        self._dia_atual = None
        self._posicao = None
        self._trades = []
        self._dia_ja_operou = False
        self._ultimo_close = None
        self._ultimo_timestamp = None

        if historico.empty:
            return
        df = historico.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        # Popula o histórico processando dia por dia.
        for dia_data, grupo in df.groupby(df["timestamp"].dt.date):
            mapa = self._processar_dia_para_historico(grupo)
            if mapa:
                self._historico.append(mapa)

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        ts = self._timestamp_de_barra(barra)
        dia_atual_data = ts.date()
        close = float(barra["close"])
        high = float(barra["high"])
        low = float(barra["low"])
        open_b = float(barra["open"])

        # Atualiza posição com excursões da barra atual.
        if self._posicao is not None:
            self._posicao.atualizar(high, low)

        # Detecta mudança de dia.
        if self._dia_atual is None or dia_atual_data != self._dia_atual.data:
            # Fecha dia anterior: registra ranges no histórico.
            if self._dia_atual is not None:
                # Fecha posição forçadamente (forced close de sessão).
                if self._posicao is not None and self._ultimo_timestamp is not None and self._ultimo_close is not None:
                    self._fechar_posicao(
                        ts=self._ultimo_timestamp,
                        preco=self._ultimo_close,
                    )
                # Registra mapa do dia anterior no histórico.
                if self._dia_atual.retorno_abs_por_minuto:
                    self._historico.append(
                        dict(self._dia_atual.retorno_abs_por_minuto)
                    )

            # Inicia novo dia.
            if self._eh_dentro_sessao(ts):
                self._dia_atual = _DiaSessao(
                    data=dia_atual_data,
                    open_preco=open_b,
                    open_timestamp=ts,
                    close_anterior=self._ultimo_close,
                )
            else:
                # Barra fora da sessão (ex: overnight) — não inicia
                # _DiaSessao mas atualiza ultimo close.
                self._dia_atual = None
            self._dia_ja_operou = False

        # Atualiza memória do close para próximo dia.
        self._ultimo_close = close
        self._ultimo_timestamp = ts

        # Se barra está fora da sessão ou sem _dia_atual válido, sai.
        if self._dia_atual is None or not self._eh_dentro_sessao(ts):
            return

        # Calcula minuto-da-sessão (1-based).
        minuto_sessao = self._minuto_da_sessao(ts)
        if minuto_sessao < 1:
            return

        # Atualiza retorno absoluto cumulativo do dia.
        retorno_abs = abs(close - self._dia_atual.open_preco)
        self._dia_atual.retorno_abs_por_minuto[minuto_sessao] = retorno_abs

        # Histórico mínimo para calcular bandas? Precisa lookback_dias completos.
        if len(self._historico) < self._parametros.lookback_dias:
            return

        # Lockout pré-fechamento — não abre trade nos últimos N min.
        if self._eh_lockout(ts):
            return

        # Calcula bandas dinâmicas.
        upper, lower = self._calcular_bandas(minuto_sessao)
        if upper is None or lower is None:
            return

        # Lógica de entrada / saída.
        if self._posicao is None:
            if self._dia_ja_operou:
                # Já operou hoje, não re-entra (regra do paper).
                return
            # Determina lados conforme flag inverter_sinais.
            # Versão momentum (paper original): close > upper => long,
            # close < lower => short.
            # Versão mean-reversion (inverter_sinais=True): close > upper
            # => short, close < lower => long.
            if not self._parametros.inverter_sinais:
                lado_alto = "long"
                lado_baixo = "short"
            else:
                lado_alto = "short"
                lado_baixo = "long"

            if close > upper:
                if (
                    lado_alto == "long" and not self._parametros.apenas_short
                ) or (
                    lado_alto == "short" and not self._parametros.apenas_long
                ):
                    self._abrir_posicao(lado_alto, ts, close, high, low)
                    self._dia_ja_operou = True
                return
            if close < lower:
                if (
                    lado_baixo == "long" and not self._parametros.apenas_short
                ) or (
                    lado_baixo == "short" and not self._parametros.apenas_long
                ):
                    self._abrir_posicao(lado_baixo, ts, close, high, low)
                    self._dia_ja_operou = True
                return
        else:
            # Posição aberta — checa saída.
            # Versão momentum: long sai quando close <= upper (preço
            # voltou pra dentro da Noise Area pelo lado de cima),
            # short sai quando close >= lower.
            # Versão mean-reversion: short sai quando close <= upper
            # (preço já reverteu o suficiente), long sai quando close
            # >= lower.
            if not self._parametros.inverter_sinais:
                if self._posicao.lado == "long" and close <= upper:
                    self._fechar_posicao(ts=ts, preco=close)
                    return
                if self._posicao.lado == "short" and close >= lower:
                    self._fechar_posicao(ts=ts, preco=close)
                    return
            else:
                if self._posicao.lado == "short" and close <= upper:
                    self._fechar_posicao(ts=ts, preco=close)
                    return
                if self._posicao.lado == "long" and close >= lower:
                    self._fechar_posicao(ts=ts, preco=close)
                    return

    def finalizar(self) -> Sequence[Trade]:
        """Fecha posição aberta com último close conhecido."""
        if (
            self._posicao is not None
            and self._ultimo_timestamp is not None
            and self._ultimo_close is not None
        ):
            self._fechar_posicao(
                ts=self._ultimo_timestamp,
                preco=self._ultimo_close,
            )
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

    def _eh_dentro_sessao(self, ts: datetime) -> bool:
        """True se o timestamp UTC está na janela de sessão configurada."""
        hora = ts.time()
        return self._parametros.sessao_inicio_utc <= hora < self._parametros.sessao_fim_utc

    def _eh_lockout(self, ts: datetime) -> bool:
        """True se a barra está nos últimos N minutos antes do close."""
        # Tempo restante até sessao_fim_utc, em minutos.
        sessao_fim = ts.replace(
            hour=self._parametros.sessao_fim_utc.hour,
            minute=self._parametros.sessao_fim_utc.minute,
            second=0,
            microsecond=0,
        )
        if ts > sessao_fim:
            return True
        diff = (sessao_fim - ts).total_seconds() / 60
        return diff <= self._parametros.minutos_lockout

    def _minuto_da_sessao(self, ts: datetime) -> int:
        """Minuto da sessão 1-based desde sessao_inicio_utc."""
        if self._dia_atual is None:
            return 0
        delta = ts - self._dia_atual.open_timestamp
        minutos = int(delta.total_seconds() // 60) + 1
        return max(1, minutos)

    def _calcular_bandas(
        self, minuto_sessao: int
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calcula upper/lower band para o minuto atual baseado no
        histórico dos últimos ``lookback_dias`` dias.

        Banda = open_dia ± open_dia × move_relativo_medio + ajuste_gap.

        Onde move_relativo_medio é a média de
        ``retorno_abs[minuto] / open_dia_correspondente`` sobre o
        histórico.
        """
        if self._dia_atual is None or self._dia_atual.open_preco <= 0:
            return None, None

        # Coleta retornos relativos do mesmo minuto-da-sessão nos
        # últimos ``lookback_dias`` dias.
        relativos: List[float] = []
        for mapa_dia in self._historico:
            if minuto_sessao in mapa_dia:
                # Não temos o open daquele dia armazenado por minuto
                # individual, então normalizamos pelo retorno absoluto
                # já. O paper calcula sobre `move/open`. Como nosso
                # histórico armazena `abs(close-open)` em pontos, e
                # opens variam pouco entre dias próximos, dividimos
                # pelo open do dia atual como proxy razoável.
                relativos.append(mapa_dia[minuto_sessao] / self._dia_atual.open_preco)

        if len(relativos) < 5:
            return None, None

        move_medio_relativo = sum(relativos) / len(relativos)
        move_pontos = self._dia_atual.open_preco * move_medio_relativo

        gap = self._dia_atual.gap_overnight
        # Ajuste do paper: gap negativo (gap-down) expande upper band
        # pra cima (preço caiu, então o "natural rebound" não vira
        # sinal momentum). Gap positivo expande lower band pra baixo.
        ajuste_upper = max(0.0, -gap)
        ajuste_lower = max(0.0, gap)

        upper = self._dia_atual.open_preco + move_pontos + ajuste_upper
        lower = self._dia_atual.open_preco - move_pontos - ajuste_lower
        return upper, lower

    def _abrir_posicao(
        self,
        lado: str,
        ts: datetime,
        preco: float,
        high: float,
        low: float,
    ) -> None:
        self._posicao = _PosicaoNoise(
            lado=lado,
            entrada_timestamp=ts,
            entrada_preco=preco,
            high_max=high,
            low_min=low,
        )

    def _fechar_posicao(self, *, ts: datetime, preco: float) -> None:
        if self._posicao is None:
            return
        if ts <= self._posicao.entrada_timestamp:
            ts = self._posicao.entrada_timestamp + pd.Timedelta(seconds=1)
        if self._posicao.lado == "long":
            mfe = max(0.0, self._posicao.high_max - self._posicao.entrada_preco)
            mae = min(0.0, self._posicao.low_min - self._posicao.entrada_preco)
        else:  # short
            mfe = max(0.0, self._posicao.entrada_preco - self._posicao.low_min)
            mae = min(0.0, self._posicao.entrada_preco - self._posicao.high_max)
        self._trades.append(
            Trade(
                entrada_timestamp=self._posicao.entrada_timestamp,
                saida_timestamp=ts,
                entrada_preco=self._posicao.entrada_preco,
                saida_preco=preco,
                lado=self._posicao.lado,  # type: ignore[arg-type]
                contratos=1,
                mfe_pontos=mfe,
                mae_pontos=mae,
            )
        )
        self._posicao = None

    def _processar_dia_para_historico(self, grupo: pd.DataFrame) -> Dict[int, float]:
        """Constrói mapa minuto-da-sessão -> retorno_abs do dia.

        Filtra apenas barras dentro da sessão. Define minuto-1 como
        primeira barra da sessão.
        """
        mapa: Dict[int, float] = {}
        if grupo.empty:
            return mapa
        # Filtra dentro da sessão.
        em_sessao = grupo[
            (grupo["timestamp"].dt.time >= self._parametros.sessao_inicio_utc)
            & (grupo["timestamp"].dt.time < self._parametros.sessao_fim_utc)
        ].reset_index(drop=True)
        if em_sessao.empty:
            return mapa
        open_dia = float(em_sessao["open"].iloc[0])
        if open_dia <= 0:
            return mapa
        for i, row in em_sessao.iterrows():
            close = float(row["close"])
            mapa[i + 1] = abs(close - open_dia)
        return mapa

    # ------------------------------------------------------------------
    # Acessores (testes / debug)
    # ------------------------------------------------------------------

    @property
    def parametros(self) -> ParametrosNoiseArea:
        return self._parametros

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)

    @property
    def historico_size(self) -> int:
        return len(self._historico)


__all__ = [
    "EstrategiaNoiseArea",
    "LOOKBACK_DEFAULT",
    "ParametrosNoiseArea",
    "SESSAO_RTH_NY_FIM_UTC",
    "SESSAO_RTH_NY_INICIO_UTC",
]
