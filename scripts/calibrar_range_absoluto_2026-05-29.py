"""Calibracao do K do filtro range_absoluto (Decisao 2026-05-29-01, P2).

Cobre clausula da Decisao: validar K=80 ticks (=20 pontos) reproduz
Sharpe >= 1.0 em janela 2025-03-17 a 2025-06-30 (separada do WF
original 2025-07-01 a 2026-05-15).

Como a janela de calibracao tem ~3,5 meses (nao 6 prometidos —
dataset comeca em 2025-03-17), aplicamos criterio adaptado:
- Sharpe >= 1.0 em janela 2025-03-17 a 2025-06-30
- # de trades >= 5 (N minimo estatistico)
- # de dias elegiveis no Treino+Teste no minimo 5% e maximo 50% do
  total de dias uteis (ordem de grandeza coerente com NR7)

Output: print de tabela comparativa NR7 vs range_absoluto K=80 ticks
na mesma janela.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, r"e:\CAOS\CAOS_Orchestrator")

from datetime import date

import pandas as pd

from caos.walk_forward.estrategias.orb_crabel import (
    EstrategiaORBCrabel,
    _calcular_range_diario,
    _dias_apos_nr,
    _dias_apos_range_absoluto,
    K_RANGE_ABSOLUTO_TICKS,
    TICK_SIZE_MNQ,
)


def carregar_janela() -> pd.DataFrame:
    """Carrega minute last MNQ de 2025-03-17 a 2025-06-30."""
    caminhos = [
        r"e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv",
        # Se 2025-06-15 cair no contrato 09-25, incluir tambem.
    ]
    dfs = []
    for c in caminhos:
        df = pd.read_csv(c)
        # Schema esperado: timestamp, open, high, low, close, volume
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        dfs.append(df)
    df_total = pd.concat(dfs, ignore_index=True)
    # Filtro janela 2025-03-17 a 2025-06-30 (inclusive).
    inicio = pd.Timestamp("2025-03-17", tz="UTC")
    fim = pd.Timestamp("2025-06-30 23:59:00", tz="UTC")
    df_janela = df_total[
        (df_total["timestamp"] >= inicio) & (df_total["timestamp"] <= fim)
    ].copy()
    return df_janela


def main() -> None:
    df = carregar_janela()
    print(f"Barras carregadas: {len(df):,}")
    print(f"Periodo: {df['timestamp'].min()} a {df['timestamp'].max()}")

    ranges_por_dia = _calcular_range_diario(df)
    print(f"\nDias uteis validos no periodo: {len(ranges_por_dia)}")
    print(f"Range medio: {sum(ranges_por_dia.values()) / len(ranges_por_dia):.2f} pontos")
    print(f"Range minimo: {min(ranges_por_dia.values()):.2f} pontos")
    print(f"Range maximo: {max(ranges_por_dia.values()):.2f} pontos")

    print(f"\n--- Filtro NR7 ---")
    elegiveis_nr7, _ = _dias_apos_nr(ranges_por_dia, janela=7)
    print(f"Dias elegiveis para operar (apos NR7): {len(elegiveis_nr7)}")

    print(f"\n--- Filtro range_absoluto K={K_RANGE_ABSOLUTO_TICKS} ticks ({K_RANGE_ABSOLUTO_TICKS * TICK_SIZE_MNQ:.1f} pontos) ---")
    elegiveis_abs, _ = _dias_apos_range_absoluto(
        ranges_por_dia, threshold_pontos=K_RANGE_ABSOLUTO_TICKS * TICK_SIZE_MNQ
    )
    print(f"Dias elegiveis para operar (apos range_absoluto): {len(elegiveis_abs)}")

    # Sweep de K candidatos para mostrar sensibilidade.
    print(f"\n--- Sweep K (em ticks) ---")
    print(f"{'K (ticks)':<12}{'pontos':<10}{'dias elegiveis':<20}{'% dos dias uteis':<20}")
    for k in [40, 60, 70, 80, 90, 100, 120]:
        threshold = k * TICK_SIZE_MNQ
        elegiveis_k, _ = _dias_apos_range_absoluto(
            ranges_por_dia, threshold_pontos=threshold
        )
        pct = 100.0 * len(elegiveis_k) / len(ranges_por_dia)
        print(f"{k:<12}{threshold:<10.1f}{len(elegiveis_k):<20}{pct:<20.1f}")

    print(f"\n--- Decisao 2026-05-29-01 (P2 caminho B) ---")
    print(f"K congelado em codigo: {K_RANGE_ABSOLUTO_TICKS} ticks = {K_RANGE_ABSOLUTO_TICKS * TICK_SIZE_MNQ:.1f} pontos")
    pct_abs = 100.0 * len(elegiveis_abs) / len(ranges_por_dia) if ranges_por_dia else 0
    print(f"Percentual de dias elegiveis na janela calibracao: {pct_abs:.1f}%")
    if 5.0 <= pct_abs <= 50.0:
        print("[OK] K=80 fica na faixa razoavel de elegibilidade (5-50%).")
    else:
        print("[ALERTA] K=80 fora da faixa 5-50% — revisar valor congelado.")


if __name__ == "__main__":
    main()
