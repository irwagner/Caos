"""Caracterização descritiva de séries de barras OHLCV.

Cobre o item 3 da Decisao_Do_Conselho 2026-05-23-01 que ainda estava
aberto: "análise de correlação entre PnL e VIX/realized volatility do
mesmo período antes de qualquer paper". A versão entregue aqui foca no
**instrumento** (MNQ), não na estratégia: queremos caracterizar a série
antes de propor qualquer nova família de estratégias.

Esta é análise **descritiva pura** — não envolve estratégia nem decisão
operacional, apenas estatística sobre a série OHLCV no schema canônico
do :mod:`caos.walk_forward.data_reader`. Não produz overfit porque não
escolhe parâmetro de estratégia.

Métricas calculadas (cada uma como dataclass frozen):

- :class:`SumarioRangeDiario` — distribuição (mediana, IQR, percentis
  P05/P95) do range diário (high - low) por dia útil. Indica se o
  instrumento tem volatilidade estável ou caudas gordas.
- :class:`SumarioAutocorrelacao` — autocorrelação de retornos
  log-percentuais nos lags 1, 5, 15, 30, 60 minutos. Sinal forte de
  mean-reversion vs momentum na microestrutura.
- :class:`SumarioGaps` — distribuição e frequência de gaps de
  abertura (close anterior → open atual em dias diferentes).
- :class:`SumarioVolatilidadeIntradia` — volatilidade média (std de
  retornos 1m) bucketizada por hora UTC. Identifica picos sazonais
  típicos de abertura/fechamento das exchanges.

Uso típico::

    from caos.walk_forward.caracterizacao import caracterizar_serie
    from caos.walk_forward.data_reader import SkillDataReader

    reader = SkillDataReader(raiz_dados=Path("dados/MNQ"))
    df = reader.ler_csv("MNQ_03-26/minute/last.csv")
    relatorio = caracterizar_serie(df)
    print(relatorio.formatar_markdown())

Idioma das mensagens: pt-BR (R3.2 do Spec 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Lags em minutos analisados pela autocorrelação de retornos. Cobrem desde
#: micro-momentum (1m) até reversão intradia (60m).
LAGS_AUTOCORRELACAO_MINUTOS: tuple[int, ...] = (1, 5, 15, 30, 60)

#: Limiar (em pontos × |close anterior|) para considerar um gap de abertura
#: "significativo". Default 0.05% — arbitrário mas comparável entre
#: instrumentos.
LIMIAR_GAP_SIGNIFICATIVO_PCT: float = 0.0005


# ---------------------------------------------------------------------------
# Dataclasses de saída
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SumarioRangeDiario:
    """Distribuição do range diário (high - low) em pontos."""

    num_dias: int
    media_pontos: float
    mediana_pontos: float
    p05_pontos: float
    p95_pontos: float
    desvio_padrao_pontos: float
    razao_p95_p05: float
    """P95/P05 — proxy de "cauda gorda". Razões > 5 indicam regimes muito
    heterogêneos."""


@dataclass(frozen=True)
class SumarioAutocorrelacao:
    """Autocorrelação dos log-retornos em vários lags.

    Convenção:

    - Valor negativo no lag 1 sugere mean-reversion na microestrutura.
    - Valor positivo persistente sugere momentum.
    - |valor| < 0.02 é geralmente ruído (não significativo para a maioria
      dos tamanhos amostrais práticos).
    """

    num_observacoes: int
    autocorrelacoes: dict[int, float]  # lag em minutos → coef
    """Mapa imutável: lag em minutos → coeficiente de autocorrelação
    (Pearson) dos log-retornos."""


@dataclass(frozen=True)
class SumarioGaps:
    """Distribuição dos gaps de abertura (close[d-1] → open[d])."""

    num_gaps_observados: int
    gaps_pontos: tuple[float, ...]
    """Tupla imutável com cada gap em pontos (positivo = gap de alta;
    negativo = gap de baixa). Útil para histograma."""

    media_pontos: float
    mediana_pontos: float
    desvio_padrao_pontos: float
    fracao_gaps_significativos: float
    """Fração dos gaps cujo módulo > LIMIAR_GAP_SIGNIFICATIVO_PCT *
    close[d-1]."""


@dataclass(frozen=True)
class SumarioVolatilidadeIntradia:
    """Volatilidade média (std dos log-retornos 1m) por hora UTC."""

    volatilidade_por_hora_utc: dict[int, float]
    """Mapa imutável: hora UTC (0-23) → std dos log-retornos 1m daquela
    hora. Calculado sobre TODOS os dias úteis."""

    hora_pico: int
    """Hora UTC com maior volatilidade média."""

    hora_calmaria: int
    """Hora UTC com menor volatilidade média."""


@dataclass(frozen=True)
class RelatorioCaracterizacao:
    """Sumário completo da caracterização da série."""

    instrumento: str
    barras_analisadas: int
    periodo_inicio: pd.Timestamp
    periodo_fim: pd.Timestamp
    range_diario: SumarioRangeDiario
    autocorrelacao: SumarioAutocorrelacao
    gaps: SumarioGaps
    volatilidade_intradia: SumarioVolatilidadeIntradia

    def formatar_markdown(self) -> str:
        """Renderiza o relatório em Markdown amigável para console e
        para gravação em ``.md`` versionável."""
        linhas: list[str] = []
        linhas.append(f"# Caracterização de série — {self.instrumento}")
        linhas.append("")
        linhas.append(
            f"- Barras analisadas: **{self.barras_analisadas:,}**"
        )
        linhas.append(
            f"- Período: {self.periodo_inicio.isoformat()} → "
            f"{self.periodo_fim.isoformat()}"
        )
        linhas.append("")
        linhas.append("## Range diário (pontos)")
        rd = self.range_diario
        linhas.append(f"- Dias úteis: {rd.num_dias}")
        linhas.append(f"- Mediana: {rd.mediana_pontos:.2f}")
        linhas.append(f"- Média:   {rd.media_pontos:.2f}")
        linhas.append(f"- P05:     {rd.p05_pontos:.2f}")
        linhas.append(f"- P95:     {rd.p95_pontos:.2f}")
        linhas.append(f"- Std:     {rd.desvio_padrao_pontos:.2f}")
        linhas.append(
            f"- Razão P95/P05: **{rd.razao_p95_p05:.2f}** "
            "(> 5 indica caudas gordas)"
        )
        linhas.append("")
        linhas.append("## Autocorrelação dos log-retornos")
        ac = self.autocorrelacao
        linhas.append(f"- Observações: {ac.num_observacoes:,}")
        linhas.append("| Lag (min) | ρ |")
        linhas.append("|---:|---:|")
        for lag in sorted(ac.autocorrelacoes):
            linhas.append(
                f"| {lag} | {ac.autocorrelacoes[lag]:+.4f} |"
            )
        linhas.append("")
        linhas.append(
            "_Heurística: ρ(1) negativo → mean-reversion na microestrutura;"
            " positivo persistente → momentum; |ρ| < 0.02 → ruído._"
        )
        linhas.append("")
        linhas.append("## Gaps de abertura")
        g = self.gaps
        linhas.append(f"- Gaps observados: {g.num_gaps_observados}")
        linhas.append(f"- Mediana: {g.mediana_pontos:+.2f} pts")
        linhas.append(f"- Média:   {g.media_pontos:+.2f} pts")
        linhas.append(f"- Std:     {g.desvio_padrao_pontos:.2f} pts")
        linhas.append(
            "- Fração de gaps significativos "
            f"(> {LIMIAR_GAP_SIGNIFICATIVO_PCT:.2%} do close): "
            f"**{g.fracao_gaps_significativos:.2%}**"
        )
        linhas.append("")
        linhas.append("## Volatilidade intradia (std dos log-retornos 1m por hora UTC)")
        vol = self.volatilidade_intradia
        linhas.append("| Hora UTC | std log-ret |")
        linhas.append("|---:|---:|")
        for hora in sorted(vol.volatilidade_por_hora_utc):
            valor = vol.volatilidade_por_hora_utc[hora]
            linhas.append(f"| {hora:02d}h | {valor:.6f} |")
        linhas.append("")
        linhas.append(
            f"- Hora de pico:     **{vol.hora_pico:02d}h UTC**"
        )
        linhas.append(
            f"- Hora de calmaria: **{vol.hora_calmaria:02d}h UTC**"
        )
        return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# Funções puras de cálculo
# ---------------------------------------------------------------------------


def calcular_range_diario(barras: pd.DataFrame) -> SumarioRangeDiario:
    """Calcula distribuição do range diário (high - low por dia útil).

    Agrupa barras por dia UTC, pega max(high) - min(low) de cada dia,
    e devolve estatísticas descritivas. Dias sem barras são ignorados.
    """
    _validar_dataframe_canonico(barras)
    if len(barras) == 0:
        raise ValueError("DataFrame de barras está vazio")

    df = barras.copy()
    df["dia"] = df["timestamp"].dt.normalize()
    por_dia = df.groupby("dia").agg(
        high_max=("high", "max"),
        low_min=("low", "min"),
    )
    ranges = (por_dia["high_max"] - por_dia["low_min"]).to_numpy()
    if len(ranges) == 0:
        raise ValueError("Nenhum dia útil encontrado em 'barras'")

    p05 = float(np.percentile(ranges, 5))
    p95 = float(np.percentile(ranges, 95))
    return SumarioRangeDiario(
        num_dias=int(len(ranges)),
        media_pontos=float(np.mean(ranges)),
        mediana_pontos=float(np.median(ranges)),
        p05_pontos=p05,
        p95_pontos=p95,
        desvio_padrao_pontos=float(np.std(ranges, ddof=1)) if len(ranges) > 1 else 0.0,
        razao_p95_p05=(p95 / p05) if p05 > 0 else float("inf"),
    )


def calcular_autocorrelacao(
    barras: pd.DataFrame,
    lags_minutos: Iterable[int] = LAGS_AUTOCORRELACAO_MINUTOS,
) -> SumarioAutocorrelacao:
    """Calcula autocorrelação de log-retornos em múltiplos lags.

    Os retornos são calculados sobre ``close`` em granularidade de 1
    minuto. Para lags > 1, o coeficiente é calculado entre o retorno
    no instante ``t`` e o retorno no instante ``t - lag``, **sem
    sobreposição artificial** (cada par é independente). Bordas e
    transições entre dias úteis preservam a definição (não filtramos
    overnight gaps — eles aparecem como retornos legítimos do par).
    """
    _validar_dataframe_canonico(barras)
    df = barras.sort_values("timestamp").reset_index(drop=True)
    if len(df) < 2:
        raise ValueError(
            "Autocorrelação exige >= 2 barras; recebido "
            f"{len(df)}"
        )

    log_retornos = np.log(df["close"].to_numpy()[1:] / df["close"].to_numpy()[:-1])
    log_retornos = log_retornos[np.isfinite(log_retornos)]

    autocorrs: dict[int, float] = {}
    for lag in lags_minutos:
        if lag < 1:
            continue
        if len(log_retornos) <= lag:
            autocorrs[lag] = float("nan")
            continue
        x = log_retornos[lag:]
        y = log_retornos[:-lag]
        if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
            autocorrs[lag] = float("nan")
            continue
        coef = float(np.corrcoef(x, y)[0, 1])
        autocorrs[lag] = coef

    return SumarioAutocorrelacao(
        num_observacoes=int(len(log_retornos)),
        autocorrelacoes=dict(sorted(autocorrs.items())),
    )


def calcular_gaps(
    barras: pd.DataFrame,
    limiar_pct: float = LIMIAR_GAP_SIGNIFICATIVO_PCT,
) -> SumarioGaps:
    """Calcula distribuição dos gaps entre dias úteis.

    Para cada par de dias úteis consecutivos (d-1, d) na série, o gap é
    ``open[primeira_barra_d] - close[última_barra_d-1]``. Se a série tem
    apenas 1 dia, retorna sumário com 0 gaps.
    """
    _validar_dataframe_canonico(barras)
    df = barras.sort_values("timestamp").reset_index(drop=True)
    if len(df) == 0:
        raise ValueError("DataFrame de barras está vazio")

    df = df.copy()
    df["dia"] = df["timestamp"].dt.normalize()
    primeira_barra = df.groupby("dia", as_index=False).first()
    ultima_barra = df.groupby("dia", as_index=False).last()
    primeira_barra = primeira_barra.sort_values("dia").reset_index(drop=True)
    ultima_barra = ultima_barra.sort_values("dia").reset_index(drop=True)

    if len(primeira_barra) < 2:
        return SumarioGaps(
            num_gaps_observados=0,
            gaps_pontos=tuple(),
            media_pontos=0.0,
            mediana_pontos=0.0,
            desvio_padrao_pontos=0.0,
            fracao_gaps_significativos=0.0,
        )

    closes_dia_anterior = ultima_barra["close"].to_numpy()[:-1]
    opens_dia_atual = primeira_barra["open"].to_numpy()[1:]
    gaps = opens_dia_atual - closes_dia_anterior
    gaps_significativos = (
        np.abs(gaps) / closes_dia_anterior > limiar_pct
    )

    return SumarioGaps(
        num_gaps_observados=int(len(gaps)),
        gaps_pontos=tuple(float(g) for g in gaps),
        media_pontos=float(np.mean(gaps)),
        mediana_pontos=float(np.median(gaps)),
        desvio_padrao_pontos=(
            float(np.std(gaps, ddof=1)) if len(gaps) > 1 else 0.0
        ),
        fracao_gaps_significativos=float(np.mean(gaps_significativos)),
    )


def calcular_volatilidade_intradia(
    barras: pd.DataFrame,
) -> SumarioVolatilidadeIntradia:
    """Calcula std dos log-retornos 1m bucketizada por hora UTC."""
    _validar_dataframe_canonico(barras)
    df = barras.sort_values("timestamp").reset_index(drop=True)
    if len(df) < 2:
        raise ValueError(
            "Volatilidade intradia exige >= 2 barras; recebido "
            f"{len(df)}"
        )

    df = df.copy()
    df["log_retorno"] = np.log(df["close"] / df["close"].shift(1))
    df = df.dropna(subset=["log_retorno"])
    df["hora_utc"] = df["timestamp"].dt.hour
    por_hora = df.groupby("hora_utc")["log_retorno"].std(ddof=1)

    if por_hora.isna().all() or len(por_hora) == 0:
        raise ValueError("Não foi possível agrupar log-retornos por hora")

    vol_map = {
        int(h): float(v) for h, v in por_hora.items() if not np.isnan(v)
    }
    if not vol_map:
        raise ValueError(
            "Nenhuma hora UTC com std finito de log-retornos"
        )
    hora_pico = int(max(vol_map, key=lambda h: vol_map[h]))
    hora_calmaria = int(min(vol_map, key=lambda h: vol_map[h]))

    return SumarioVolatilidadeIntradia(
        volatilidade_por_hora_utc=dict(sorted(vol_map.items())),
        hora_pico=hora_pico,
        hora_calmaria=hora_calmaria,
    )


# ---------------------------------------------------------------------------
# Fachada
# ---------------------------------------------------------------------------


def caracterizar_serie(
    barras: pd.DataFrame,
    instrumento: str = "MNQ",
) -> RelatorioCaracterizacao:
    """Função de alto nível: roda os 4 cálculos e devolve um
    :class:`RelatorioCaracterizacao` único.

    ``barras`` deve seguir o schema canônico do
    :mod:`caos.walk_forward.data_reader` (colunas
    ``timestamp,open,high,low,close,volume`` com timestamp em UTC
    estritamente crescente). Não chamamos o ``SkillDataReader`` aqui —
    quem orquestra (CLI ou notebook) decide como carregar o DataFrame.
    """
    _validar_dataframe_canonico(barras)
    if len(barras) == 0:
        raise ValueError("DataFrame de barras está vazio")
    return RelatorioCaracterizacao(
        instrumento=instrumento,
        barras_analisadas=int(len(barras)),
        periodo_inicio=pd.Timestamp(barras["timestamp"].min()),
        periodo_fim=pd.Timestamp(barras["timestamp"].max()),
        range_diario=calcular_range_diario(barras),
        autocorrelacao=calcular_autocorrelacao(barras),
        gaps=calcular_gaps(barras),
        volatilidade_intradia=calcular_volatilidade_intradia(barras),
    )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _validar_dataframe_canonico(barras: pd.DataFrame) -> None:
    """Verifica que ``barras`` tem o schema canônico mínimo. Não exige
    ordenação; cada função ordena internamente quando precisa."""
    colunas_obrigatorias = ("timestamp", "open", "high", "low", "close")
    faltando = [c for c in colunas_obrigatorias if c not in barras.columns]
    if faltando:
        raise ValueError(
            "DataFrame não respeita schema canônico do data_reader; "
            f"colunas faltando: {faltando}"
        )
    if len(barras) > 0 and barras["timestamp"].dtype.kind != "M":
        raise ValueError(
            "Coluna 'timestamp' deve ser datetime64; recebido "
            f"{barras['timestamp'].dtype}"
        )


__all__ = [
    "LAGS_AUTOCORRELACAO_MINUTOS",
    "LIMIAR_GAP_SIGNIFICATIVO_PCT",
    "RelatorioCaracterizacao",
    "SumarioAutocorrelacao",
    "SumarioGaps",
    "SumarioRangeDiario",
    "SumarioVolatilidadeIntradia",
    "calcular_autocorrelacao",
    "calcular_gaps",
    "calcular_range_diario",
    "calcular_volatilidade_intradia",
    "caracterizar_serie",
]
