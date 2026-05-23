"""Analise estatistica completa do Pre-FOMC drift no MNQ.

Cobre 4 itens:

1. t-stat formal sobre os trades (H0: media = 0).
2. Re-execucao em granularidade day/last para sanity check.
3. Investigacao do trade catastrofico (mar/2026 -412 pts).
4. Autocorrelacao condicional dos log-retornos por bucket de
   gap e de volatilidade.

Sem dependencias externas alem do que ja esta no projeto.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ROOT_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_REPO / "CAOS_Orchestrator"))

from caos.walk_forward.data_reader import SkillDataReader
from caos.walk_forward.estrategias.pre_fomc import (
    EstrategiaPreFomcDrift,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _executar_serie_completa(
    df: pd.DataFrame, csv_fomc: Path
) -> List[Trade]:
    plugin = EstrategiaPreFomcDrift(csv_fomc)
    plugin.treinar(df.copy())
    iterator = BarrasTesteIterator(df)
    for barra in iterator:
        plugin.on_barra(barra, iterator)
    return list(plugin.finalizar())


def _aplicar_friccao(
    pnls_brutos: List[float], custo_por_trade: float = 1.12
) -> List[float]:
    """Aplica custo Topstep (1.12 pts/trade round-trip)."""
    return [p - custo_por_trade for p in pnls_brutos]


def _t_stat_uma_amostra(amostra: List[float]) -> tuple[float, float, int]:
    """Devolve (t_stat, p_valor_aprox, df). H0: media = 0.

    Para N pequeno usa t-Student. p_valor calculado via aproximacao
    da distribuicao normal padrao (suficiente para N >= 10 quando o
    objetivo e' rejeitar H0 com folga >= 2 sigma).
    """
    if len(amostra) < 2:
        return (float("nan"), float("nan"), 0)
    arr = np.asarray(amostra, dtype=float)
    n = len(arr)
    media = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    if std == 0:
        return (float("inf") if media > 0 else float("-inf"), 0.0, n - 1)
    t = media / (std / np.sqrt(n))
    # Aproximacao bilateral via normal padrao para p_valor.
    from math import erf, sqrt

    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    return t, p, n - 1


# ---------------------------------------------------------------------------
# 1. t-stat formal
# ---------------------------------------------------------------------------


def analise_t_stat() -> tuple[List[Trade], List[float]]:
    print("=" * 70)
    print("1. T-STAT FORMAL — minute/last (serie completa, 5 contratos)")
    print("=" * 70)
    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="analise-completa",
    )
    df_min = reader.carregar(
        ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last"
    )
    csv_fomc = ROOT_REPO / "dados" / "macros" / "fomc_meetings.csv"
    trades = _executar_serie_completa(df_min, csv_fomc)
    pnls_brutos = [t.pnl_pontos() for t in trades]
    pnls_liq = _aplicar_friccao(pnls_brutos)
    print(f"  N = {len(trades)} trades")
    print(f"  PnL bruto:    soma={sum(pnls_brutos):+.2f} pts  media={np.mean(pnls_brutos):+.2f} pts")
    print(f"  PnL liquido:  soma={sum(pnls_liq):+.2f} pts    media={np.mean(pnls_liq):+.2f} pts")
    print(f"  Std (liq.):   {np.std(pnls_liq, ddof=1):.2f} pts")
    print(f"  Win rate:     {sum(1 for p in pnls_liq if p > 0) / len(pnls_liq):.1%}")
    print()
    t_b, p_b, df_b = _t_stat_uma_amostra(pnls_brutos)
    t_l, p_l, df_l = _t_stat_uma_amostra(pnls_liq)
    print(f"  H0: media PnL = 0")
    print(f"  Bruto:    t = {t_b:+.3f}  df = {df_b}  p (bilateral) = {p_b:.4f}")
    print(f"  Liquido:  t = {t_l:+.3f}  df = {df_l}  p (bilateral) = {p_l:.4f}")
    if abs(t_l) >= 2.0:
        print("  => |t| >= 2.0  REJEITA H0 ao nivel 5% (criterio Mesfin 2026).")
    else:
        print("  => |t| < 2.0   NAO rejeita H0; resultado indistinguivel de zero.")
    print()
    return trades, pnls_liq


# ---------------------------------------------------------------------------
# 2. Re-execucao em day/last
# ---------------------------------------------------------------------------


def analise_day() -> None:
    print("=" * 70)
    print("2. SANITY CHECK — granularidade day/last")
    print("=" * 70)
    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="analise-completa",
    )
    df_day = reader.carregar(
        ROOT_REPO / "dados" / "MNQ" / "_concat_day_last"
    )
    csv_fomc = ROOT_REPO / "dados" / "macros" / "fomc_meetings.csv"
    trades = _executar_serie_completa(df_day, csv_fomc)
    pnls_brutos = [t.pnl_pontos() for t in trades]
    pnls_liq = _aplicar_friccao(pnls_brutos)
    print(f"  N = {len(trades)} trades (em day deve ser igual ao minute)")
    print(f"  PnL bruto:   soma={sum(pnls_brutos):+.2f} pts")
    print(f"  PnL liquido: soma={sum(pnls_liq):+.2f} pts")
    t, p, dfree = _t_stat_uma_amostra(pnls_liq)
    print(f"  t = {t:+.3f}  p = {p:.4f}")
    print()
    print("  (Esperado: numeros proximos do minute/last; small drift")
    print("   por causa do horario de close exato pode ocorrer.)")
    print()


# ---------------------------------------------------------------------------
# 3. Investigar trade catastrofico
# ---------------------------------------------------------------------------


def analise_trade_catastrofico(trades: List[Trade]) -> None:
    print("=" * 70)
    print("3. ANATOMIA DO TRADE CATASTROFICO")
    print("=" * 70)
    pior = min(trades, key=lambda t: t.pnl_pontos())
    print(f"  Entrada: {pior.entrada_timestamp.isoformat()}")
    print(f"  Saida:   {pior.saida_timestamp.isoformat()}")
    print(f"  Lado:    {pior.lado}")
    print(f"  Preco entrada: {pior.entrada_preco:.2f}")
    print(f"  Preco saida:   {pior.saida_preco:.2f}")
    print(f"  PnL bruto:     {pior.pnl_pontos():+.2f} pts (= USD {pior.pnl_pontos() * 2:.2f})")
    print(f"  MFE:           {pior.mfe_pontos:+.2f} pts (excursao maxima a favor)")
    print(f"  MAE:           {pior.mae_pontos:+.2f} pts (excursao maxima contra)")
    print()
    # Carrega contexto: 5 dias antes e 1 dia depois do trade.
    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="analise-completa",
    )
    df_min = reader.carregar(
        ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last"
    )
    janela_inicio = pior.entrada_timestamp - pd.Timedelta(days=5)
    janela_fim = pior.saida_timestamp + pd.Timedelta(days=1)
    contexto = df_min[
        (df_min["timestamp"] >= janela_inicio)
        & (df_min["timestamp"] <= janela_fim)
    ]
    if contexto.empty:
        print("  (sem dados de contexto)")
        return
    # Range diario nesse contexto.
    contexto = contexto.copy()
    contexto["dia"] = contexto["timestamp"].dt.date
    por_dia = contexto.groupby("dia").agg(
        primeira=("timestamp", "first"),
        ultima=("timestamp", "last"),
        open_d=("open", "first"),
        close_d=("close", "last"),
        high_d=("high", "max"),
        low_d=("low", "min"),
        n_barras=("close", "count"),
    )
    por_dia["range_d"] = por_dia["high_d"] - por_dia["low_d"]
    por_dia["ret_d"] = (por_dia["close_d"] - por_dia["open_d"]) / por_dia["open_d"]
    print("  Contexto diario (D-5 ate D+1):")
    print("  Dia          | Open    | Close   | Range  | Retorno | Barras")
    for d, row in por_dia.iterrows():
        marca = ""
        if d == pior.entrada_timestamp.date():
            marca = "  <- ENTRADA"
        elif d == pior.saida_timestamp.date():
            marca = "  <- SAIDA"
        print(
            f"  {d.isoformat()} | {row['open_d']:8.2f} | {row['close_d']:8.2f} | "
            f"{row['range_d']:6.2f} | {row['ret_d']:+.4f} | {row['n_barras']:>5}{marca}"
        )
    print()


# ---------------------------------------------------------------------------
# 4. Autocorrelacao condicional
# ---------------------------------------------------------------------------


def analise_autocorr_condicional() -> None:
    print("=" * 70)
    print("4. AUTOCORRELACAO CONDICIONAL — sub-conjuntos de dias")
    print("=" * 70)
    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="analise-completa",
    )
    df = reader.carregar(
        ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last"
    )
    df = df.copy()
    df["dia"] = df["timestamp"].dt.date

    # Range diario por dia.
    por_dia = df.groupby("dia").agg(
        high_max=("high", "max"),
        low_min=("low", "min"),
        primeiro_open=("open", "first"),
        ultimo_close=("close", "last"),
    )
    por_dia["range"] = por_dia["high_max"] - por_dia["low_min"]
    por_dia = por_dia.reset_index()
    por_dia["close_anterior"] = por_dia["ultimo_close"].shift(1)
    por_dia["gap_pct"] = (
        por_dia["primeiro_open"] - por_dia["close_anterior"]
    ).abs() / por_dia["close_anterior"]
    por_dia = por_dia.dropna()

    p75_range = por_dia["range"].quantile(0.75)
    p75_gap = por_dia["gap_pct"].quantile(0.75)
    print(f"  P75 do range diario: {p75_range:.2f} pts")
    print(f"  P75 do gap %:        {p75_gap:.4%}")
    print()

    # Para cada bucket, calcula autocorrelacao(1m) APENAS nos minutos
    # daqueles dias.
    dias_alta_vol = set(por_dia.loc[por_dia["range"] >= p75_range, "dia"])
    dias_alto_gap = set(por_dia.loc[por_dia["gap_pct"] >= p75_gap, "dia"])
    dias_baixa_vol = set(por_dia.loc[por_dia["range"] < por_dia["range"].quantile(0.25), "dia"])

    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df = df.dropna(subset=["log_ret"])

    def _rho1(serie: pd.Series) -> tuple[float, int]:
        if len(serie) < 100:
            return float("nan"), len(serie)
        y = serie.to_numpy()
        if np.std(y[1:]) == 0 or np.std(y[:-1]) == 0:
            return float("nan"), len(serie)
        return float(np.corrcoef(y[1:], y[:-1])[0, 1]), len(serie)

    todos = df["log_ret"]
    alta_vol = df.loc[df["dia"].isin(dias_alta_vol), "log_ret"]
    alto_gap = df.loc[df["dia"].isin(dias_alto_gap), "log_ret"]
    baixa_vol = df.loc[df["dia"].isin(dias_baixa_vol), "log_ret"]

    rho_t, n_t = _rho1(todos)
    rho_av, n_av = _rho1(alta_vol)
    rho_ag, n_ag = _rho1(alto_gap)
    rho_bv, n_bv = _rho1(baixa_vol)

    print("  Autocorrelacao(1) dos log-retornos por sub-conjunto:")
    print(f"  - Todos os dias:           rho = {rho_t:+.4f}  N = {n_t:>7,}")
    print(f"  - Dias com range >= P75:   rho = {rho_av:+.4f}  N = {n_av:>7,}")
    print(f"  - Dias com |gap| >= P75:   rho = {rho_ag:+.4f}  N = {n_ag:>7,}")
    print(f"  - Dias com range < P25:    rho = {rho_bv:+.4f}  N = {n_bv:>7,}")
    print()
    print("  Heuristica: |rho| > 0.02 com N > 10000 sugere sinal nao-aleatorio.")
    print("  Reversao: rho < 0; momentum: rho > 0.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    trades, _ = analise_t_stat()
    analise_day()
    analise_trade_catastrofico(trades)
    analise_autocorr_condicional()

    # Grava saida formatada em arquivo para versionar.
    saida = (
        ROOT_REPO
        / "05_BACKTEST"
        / "walk_forward"
        / "relatorios"
        / "2026-05-23-04"
        / "analise-estatistica-2026-05-23.txt"
    )
    saida.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n(saida tambem disponivel via redirecionamento; arquivo nao versionado neste run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
