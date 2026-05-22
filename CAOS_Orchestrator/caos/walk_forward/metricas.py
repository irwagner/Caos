"""MetricasCalculator — métricas de uma janela de Walk-Forward (Spec 2 — Task 5).

Cobre o **R6** do ``requirements.md`` do Spec 2 e a linha correspondente da
tabela em ``design.md`` seção 4 (Components and Interfaces).

Responsabilidade
----------------
A partir do log de :class:`Trade` produzido pelo ``BacktestRunner`` em uma
:class:`JanelaWF`, calcular o conjunto mínimo de métricas exigido por R6.1
e devolver um :class:`ResultadoJanela` válido respeitando as regras de
status do model (``ok`` / ``sem-trades`` / ``falha``) — em particular a
regra R6.2: sem trades ⇒ métricas dependentes ``None``.

Métricas computadas
-------------------
- ``numero_trades``  — contagem de :class:`Trade` no Periodo_Teste.
- ``pnl_total``      — soma dos PnLs em pontos.
- ``win_rate``       — ``wins / (wins + losses)``; ``None`` se 0 trades.
- ``payoff_medio``   — ``mean(ganhos) / mean(|perdas|)``; ``None`` se 0
  perdas (R6.2 — payoff indefinido sem perdedores). Com 0 ganhos e
  ≥ 1 perda devolve ``0.0``.
- ``mfe_medio`` /
  ``mae_medio``      — média simples de ``mfe_pontos`` / ``mae_pontos``
  por trade.
- ``sharpe_anualizado`` — ``mean(returns_diarios) / std(returns_diarios)
  * sqrt(252)``; ``None`` se ``std == 0`` ou ``len(returns_diarios) < 2``.
  ``returns_diarios`` é o PnL diário agregado por ``saida_timestamp.date()``
  — mean/std são invariantes a rescaling, portanto não há necessidade de
  normalizar por capital nominal.
- ``drawdown_maximo_percentual`` /
  ``drawdown_maximo_dias`` — calculados sobre a curva de equity por trade
  (``cumsum(pnl)``) com normalização por
  ``capital_base = max(peak, max_dd_abs, 1.0)`` (ver função interna
  :func:`_drawdown_maximo`). Garante valor em ``[0.0, 1.0]``, dentro dos
  limites do model.
- ``calmar``         — ``retorno_anualizado / drawdown_maximo_percentual``;
  ``None`` se drawdown == 0 ou < 1 trade. ``retorno_anualizado`` =
  ``(pnl_total / capital_base) * (252 / tamanho_teste_dias_uteis)``.

Convenção de PnL
----------------
Para cada :class:`Trade`:

- ``long``  → ``pnl_pontos = (saida_preco - entrada_preco) * contratos``
- ``short`` → ``pnl_pontos = (entrada_preco - saida_preco) * contratos``

A unidade é "pontos × contratos" (consistente com ``mfe_pontos`` /
``mae_pontos``). O multiplicador em USD do MNQ (USD 2 / ponto) é
deliberadamente omitido aqui — o agregador não precisa dele para Sharpe,
Calmar, drawdown%, win_rate ou payoff.

API pública
-----------
- :class:`Trade`              — modelo do trade (Pydantic v2).
- :class:`MetricasCalculator` — fachada estática com :meth:`calcular`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev
from typing import Annotated, Any, Literal, Optional, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from caos.walk_forward.models import (
    ConfiguracaoWalkForward,
    JanelaWF,
    ResultadoJanela,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Dias úteis padrão por ano para anualização de Sharpe e Calmar.
DIAS_UTEIS_POR_ANO = 252

#: Tipos enumerados para o lado da operação.
LadoTrade = Literal["long", "short"]


# ---------------------------------------------------------------------------
# Helpers de parsing de datetime UTC
# ---------------------------------------------------------------------------


def _parse_datetime_utc(valor: Any) -> datetime:
    """Converte ``valor`` em ``datetime`` exigindo UTC (offset 0).

    Réplica local de ``caos.walk_forward.models._parse_datetime_utc`` para
    manter este módulo sem dependência de helper privado externo. Aceita
    ``datetime`` aware UTC ou string ISO 8601 com sufixo ``"Z"``/``"+00:00"``.
    """
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            raise ValueError(
                "datetime exige tzinfo (UTC ou offset 0); "
                "recebido naive datetime"
            )
        if valor.utcoffset() != timedelta(0):
            raise ValueError(
                "datetime deve estar em UTC (offset 0); "
                f"recebido {valor.isoformat()}"
            )
        return valor
    if isinstance(valor, str):
        bruto = valor.strip()
        if not bruto:
            raise ValueError("string de data vazia")
        normalizado = bruto[:-1] + "+00:00" if bruto.endswith("Z") else bruto
        try:
            parsed = datetime.fromisoformat(normalizado)
        except ValueError as exc:
            raise ValueError(
                f"data não está em formato ISO 8601 válido: {valor!r}"
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                f"data sem fuso horário: {valor!r} (use sufixo 'Z' ou '+00:00')"
            )
        if parsed.utcoffset() != timedelta(0):
            raise ValueError(
                f"data deve estar em UTC (offset 0); recebido {parsed.isoformat()}"
            )
        return parsed
    raise TypeError(
        "data deve ser datetime ou string ISO 8601, "
        f"recebido {type(valor).__name__}"
    )


# ---------------------------------------------------------------------------
# Modelo Trade
# ---------------------------------------------------------------------------


class Trade(BaseModel):
    """Trade fechado dentro do Periodo_Teste de uma :class:`JanelaWF`.

    Campos:
    - ``entrada_timestamp`` — abertura da posição, ``datetime`` UTC.
    - ``saida_timestamp``   — fechamento da posição, ``datetime`` UTC,
      estritamente posterior a ``entrada_timestamp``.
    - ``entrada_preco``     — preço de entrada em pontos do índice.
    - ``saida_preco``       — preço de saída em pontos do índice.
    - ``lado``              — ``"long"`` ou ``"short"``.
    - ``contratos``         — quantidade de contratos do MNQ; inteiro ``> 0``.
    - ``mfe_pontos``        — Maximum Favorable Excursion em pontos
      (magnitude máxima a favor durante o trade); por convenção ``>= 0``.
    - ``mae_pontos``        — Maximum Adverse Excursion em pontos
      (magnitude máxima contra durante o trade); por convenção ``<= 0``,
      mas o model não exige (deixa a estratégia escolher convenção).

    Esta é a fonte da verdade para o ``MetricasCalculator``: nada além
    destes 8 campos é necessário para reconstruir as métricas de R6.1.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entrada_timestamp: datetime
    saida_timestamp: datetime
    entrada_preco: float
    saida_preco: float
    lado: LadoTrade
    contratos: Annotated[int, Field(ge=1)]
    mfe_pontos: float
    mae_pontos: float

    @field_validator("entrada_timestamp", "saida_timestamp", mode="before")
    @classmethod
    def _parse_datas_utc(cls, valor: Any) -> datetime:
        return _parse_datetime_utc(valor)

    @model_validator(mode="after")
    def _check_ordem_temporal(self) -> "Trade":
        if self.saida_timestamp <= self.entrada_timestamp:
            raise ValueError(
                "saida_timestamp deve ser estritamente maior que "
                f"entrada_timestamp; recebido entrada="
                f"{self.entrada_timestamp.isoformat()}, saida="
                f"{self.saida_timestamp.isoformat()}"
            )
        return self

    # ------------------------------------------------------------------
    # Conveniências derivadas
    # ------------------------------------------------------------------
    def pnl_pontos(self) -> float:
        """PnL do trade em pontos × contratos.

        - ``long``  → ``(saida - entrada) * contratos``
        - ``short`` → ``(entrada - saida) * contratos``
        """
        delta = self.saida_preco - self.entrada_preco
        if self.lado == "short":
            delta = -delta
        return delta * self.contratos


# ---------------------------------------------------------------------------
# Funções internas de cálculo
# ---------------------------------------------------------------------------


def _agregar_pnl_diario(
    trades: Sequence[Trade],
) -> list[float]:
    """Agrega PnL por ``saida_timestamp.date()`` em ordem cronológica.

    Devolve a lista de PnLs diários, sem dias zero entre dias com trades —
    apenas dias em que ao menos 1 trade fechou. Útil para Sharpe diário.
    """
    por_dia: dict = {}
    for t in trades:
        dia = t.saida_timestamp.date()
        por_dia[dia] = por_dia.get(dia, 0.0) + t.pnl_pontos()
    # Ordem cronológica determinística.
    return [por_dia[d] for d in sorted(por_dia.keys())]


def _sharpe_anualizado(returns_diarios: Sequence[float]) -> Optional[float]:
    """Sharpe anualizado: ``mean / std * sqrt(252)``.

    Retorna ``None`` quando ``len(returns_diarios) < 2`` ou ``std == 0``
    (variância nula), conforme regra fixada na Task 5.
    """
    if len(returns_diarios) < 2:
        return None
    media = mean(returns_diarios)
    desvio = stdev(returns_diarios)  # ddof=1 (sample std)
    if desvio == 0.0:
        return None
    return (media / desvio) * math.sqrt(DIAS_UTEIS_POR_ANO)


def _drawdown_maximo(
    pnls: Sequence[float],
    saida_timestamps: Sequence[datetime],
) -> tuple[Optional[float], Optional[int], float]:
    """Calcula drawdown máximo percentual, em dias, e o capital base usado.

    A curva de equity é construída como ``cumsum(pnls)`` precedida por
    ``0.0`` (estado pré-primeiro-trade). Para cada ponto, calculamos
    ``dd_abs[i] = peak[i] - equity[i]``, onde ``peak[i] = max(equity[0..i])``.

    Para converter o drawdown absoluto em percentual no intervalo
    ``[0.0, 1.0]`` (limite do campo no model), usamos como denominador
    ``capital_base = max(peak_global, max_dd_abs, 1.0)``. Esta normalização
    é **bem definida em qualquer cenário** (incluindo pure-loss e pure-win)
    e devolve:

    - ``0.0`` para pure-win (drawdown absoluto = 0).
    - ``1.0`` para pure-loss (drawdown absoluto == capital_base).
    - Valor em ``(0.0, 1.0)`` para séries mistas com algum drawdown.

    O ``drawdown_maximo_dias`` é a diferença em dias calendário entre a
    ``saida_timestamp`` da trade que estabeleceu o pico antes do drawdown
    e a ``saida_timestamp`` da trade que tocou o fundo. Quando o pico
    coincide com o estado pré-primeiro-trade (``equity == 0``), usamos a
    ``saida_timestamp`` do primeiro trade como referência (o pico não tem
    timestamp próprio).

    Retorna ``(None, None, 1.0)`` quando ``pnls`` está vazio.
    """
    if not pnls:
        return None, None, 1.0

    equity: list[float] = [0.0]
    for p in pnls:
        equity.append(equity[-1] + p)

    peak = equity[0]
    peak_idx = 0
    max_dd_abs = 0.0
    max_dd_peak_idx = 0
    max_dd_trough_idx = 0
    peak_global = equity[0]
    for i, eq in enumerate(equity):
        if eq > peak:
            peak = eq
            peak_idx = i
        if eq > peak_global:
            peak_global = eq
        dd = peak - eq
        if dd > max_dd_abs:
            max_dd_abs = dd
            max_dd_peak_idx = peak_idx
            max_dd_trough_idx = i

    capital_base = max(peak_global, max_dd_abs, 1.0)
    dd_pct = max_dd_abs / capital_base

    if max_dd_abs == 0.0:
        # Sem drawdown: por convenção, dias = 0.
        return 0.0, 0, capital_base

    # Mapear índices da curva de equity para timestamps de trades.
    # equity[0] é "antes do primeiro trade"; equity[i] (i >= 1) é
    # "após o trade i-1", cuja saida_timestamp é saida_timestamps[i-1].
    if max_dd_peak_idx == 0:
        ts_peak = saida_timestamps[0]
    else:
        ts_peak = saida_timestamps[max_dd_peak_idx - 1]

    # Trough sempre >= 1 quando max_dd_abs > 0 (índice 0 tem dd = 0).
    ts_trough = saida_timestamps[max_dd_trough_idx - 1]

    dias = (ts_trough.date() - ts_peak.date()).days
    if dias < 0:
        dias = 0  # defensivo; saidas devem estar ordenadas, mas trades não.
    return dd_pct, dias, capital_base


def _payoff_medio(
    pnls: Sequence[float],
) -> Optional[float]:
    """Razão ``mean(ganhos) / mean(|perdas|)``.

    Convenção:
    - 0 perdas  → ``None`` (payoff indefinido sem perdedores).
    - 0 ganhos  → ``0.0`` (média dos vencedores tratada como 0).
    - Outros    → razão positiva.
    """
    ganhos = [p for p in pnls if p > 0]
    perdas = [p for p in pnls if p < 0]
    if not perdas:
        return None
    media_ganhos = mean(ganhos) if ganhos else 0.0
    media_perdas = mean([abs(p) for p in perdas])
    return media_ganhos / media_perdas


# ---------------------------------------------------------------------------
# Fachada pública: MetricasCalculator
# ---------------------------------------------------------------------------


class MetricasCalculator:
    """Fachada estática para cálculo de métricas de uma janela WF (R6).

    A API ``MetricasCalculator.calcular(...)`` é a única exposta —
    operações intermediárias permanecem em funções privadas para
    facilitar testes e manter o módulo coeso.
    """

    @staticmethod
    def calcular(
        trades: Sequence[Trade],
        janela: JanelaWF,
        estrategia: str,
        configuracao: ConfiguracaoWalkForward,
        duracao_ms: int,
        *,
        look_ahead_violation: bool = False,
    ) -> ResultadoJanela:
        """Calcula métricas e devolve :class:`ResultadoJanela`.

        Regras de status:
        - ``len(trades) == 0`` ⇒ ``status="sem-trades"``, todas as
          métricas dependentes ``None``, ``pnl_total=0.0`` (R6.2).
        - Caso contrário ⇒ ``status="ok"`` com métricas calculadas.
          Métricas individuais podem ainda ser ``None`` quando
          indefinidas (Sharpe com ``std == 0`` ou ``< 2`` dias; Calmar
          com drawdown == 0; payoff com 0 perdas).

        Parâmetros:
        - ``trades``       — lista de :class:`Trade` fechados no Teste.
        - ``janela``       — :class:`JanelaWF` que originou os trades.
        - ``estrategia``   — nome canônico da Estrategia avaliada.
        - ``configuracao`` — :class:`ConfiguracaoWalkForward` usada.
        - ``duracao_ms``   — tempo de execução da janela em ms (R6 ←
          design 3, ``ResultadoJanela.duracao_ms``).
        - ``look_ahead_violation`` — flag opcional vinda do
          ``BacktestRunner``. ``False`` por default.
        """
        n = len(trades)

        # ------------------------------------------------------------------
        # Caso 1 — Sem trades (R6.2).
        # ------------------------------------------------------------------
        if n == 0:
            return ResultadoJanela(
                janela=janela,
                estrategia=estrategia,
                configuracao=configuracao,
                sharpe_anualizado=None,
                calmar=None,
                drawdown_maximo_percentual=None,
                drawdown_maximo_dias=None,
                win_rate=None,
                payoff_medio=None,
                mfe_medio=None,
                mae_medio=None,
                numero_trades=0,
                pnl_total=0.0,
                look_ahead_violation=look_ahead_violation,
                status="sem-trades",
                motivo_falha=None,
                duracao_ms=duracao_ms,
            )

        # ------------------------------------------------------------------
        # Caso 2 — ≥ 1 trade.
        # ------------------------------------------------------------------
        # Ordenamos os trades por saida_timestamp para que a curva de
        # equity reflita a sequência cronológica real, mesmo se o
        # caller passar fora de ordem.
        trades_ord = sorted(trades, key=lambda t: t.saida_timestamp)
        pnls = [t.pnl_pontos() for t in trades_ord]
        saidas = [t.saida_timestamp for t in trades_ord]

        pnl_total = float(sum(pnls))
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        # ``ge == 0`` (break-even) não conta nem como win nem como loss.
        denom_winrate = wins + losses
        win_rate = (wins / denom_winrate) if denom_winrate > 0 else None

        payoff = _payoff_medio(pnls)

        mfe_medio = float(mean(t.mfe_pontos for t in trades_ord))
        mae_medio = float(mean(t.mae_pontos for t in trades_ord))

        sharpe = _sharpe_anualizado(_agregar_pnl_diario(trades_ord))

        dd_pct, dd_dias, capital_base = _drawdown_maximo(pnls, saidas)

        # Calmar: retorno anualizado / drawdown.
        # retorno_anualizado = (pnl_total / capital_base) * (252 / dias_uteis_teste).
        if dd_pct is None or dd_pct == 0.0:
            calmar: Optional[float] = None
        else:
            dias_uteis_teste = configuracao.tamanho_teste_dias_uteis
            retorno_total = pnl_total / capital_base
            retorno_anualizado = retorno_total * (
                DIAS_UTEIS_POR_ANO / dias_uteis_teste
            )
            calmar = retorno_anualizado / dd_pct

        return ResultadoJanela(
            janela=janela,
            estrategia=estrategia,
            configuracao=configuracao,
            sharpe_anualizado=sharpe,
            calmar=calmar,
            drawdown_maximo_percentual=dd_pct,
            drawdown_maximo_dias=dd_dias,
            win_rate=win_rate,
            payoff_medio=payoff,
            mfe_medio=mfe_medio,
            mae_medio=mae_medio,
            numero_trades=n,
            pnl_total=pnl_total,
            look_ahead_violation=look_ahead_violation,
            status="ok",
            motivo_falha=None,
            duracao_ms=duracao_ms,
        )


__all__ = [
    "DIAS_UTEIS_POR_ANO",
    "LadoTrade",
    "Trade",
    "MetricasCalculator",
]
