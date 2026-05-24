"""Analise de correlacao Crabel NR7 vs Pre-FOMC drift.

Cumpre a Decisao 2026-05-24-01 (P2 vencedora): verificar se as duas
candidatas pegam dias DIFERENTES (compatibilidade para mini-portfolio
no futuro) ou se ha overlap alto (uma redundante).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_REPO / "CAOS_Orchestrator"))

from caos.walk_forward.data_reader import SkillDataReader
from caos.walk_forward.estrategias.orb_crabel import EstrategiaORBCrabel
from caos.walk_forward.estrategias.pre_fomc import EstrategiaPreFomcDrift
from caos.walk_forward.runner import BarrasTesteIterator


def main() -> int:
    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="correlacao-crabel-prefomc",
    )
    df = reader.carregar(ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last")
    print(f"Dataset: {len(df):,} barras")

    # Crabel NR7 — serie completa.
    crabel = EstrategiaORBCrabel(modo_nr="nr7")
    crabel.treinar(df.copy())
    it_c = BarrasTesteIterator(df)
    for barra in it_c:
        crabel.on_barra(barra, it_c)
    trades_crabel = list(crabel.finalizar())
    print(f"\nCrabel NR7: {len(trades_crabel)} trades")

    # Pre-FOMC drift.
    csv_fomc = ROOT_REPO / "dados" / "macros" / "fomc_meetings.csv"
    prefomc = EstrategiaPreFomcDrift(csv_fomc)
    prefomc.treinar(df.copy())
    it_p = BarrasTesteIterator(df)
    for barra in it_p:
        prefomc.on_barra(barra, it_p)
    trades_prefomc = list(prefomc.finalizar())
    print(f"Pre-FOMC drift: {len(trades_prefomc)} trades")

    # Datas.
    datas_crabel = {t.entrada_timestamp.date() for t in trades_crabel}
    datas_prefomc = {t.entrada_timestamp.date() for t in trades_prefomc}

    overlap = datas_crabel & datas_prefomc
    so_crabel = datas_crabel - datas_prefomc
    so_prefomc = datas_prefomc - datas_crabel

    print()
    print(f"Datas Crabel:    {sorted(datas_crabel)}")
    print(f"Datas Pre-FOMC:  {sorted(datas_prefomc)}")
    print()
    print(f"Overlap:         {len(overlap)} datas — {sorted(overlap)}")
    print(f"Apenas Crabel:   {len(so_crabel)} datas")
    print(f"Apenas Pre-FOMC: {len(so_prefomc)} datas")

    # Correlacao de PnL diario:
    pnl_por_data: dict[date, dict[str, float]] = {}
    for t in trades_crabel:
        d = t.entrada_timestamp.date()
        pnl_por_data.setdefault(d, {"crabel": 0.0, "prefomc": 0.0})
        pnl_por_data[d]["crabel"] += t.pnl_pontos()
    for t in trades_prefomc:
        d = t.entrada_timestamp.date()
        pnl_por_data.setdefault(d, {"crabel": 0.0, "prefomc": 0.0})
        pnl_por_data[d]["prefomc"] += t.pnl_pontos()

    # Soma agregada por estrategia.
    soma_crabel = sum(t.pnl_pontos() for t in trades_crabel)
    soma_prefomc = sum(t.pnl_pontos() for t in trades_prefomc)
    custo_crabel = len(trades_crabel) * 1.12  # round-trip Topstep fixo
    custo_prefomc = len(trades_prefomc) * 1.12
    print()
    print("PnL bruto e liquido (custos Topstep fixo, 1.12 pts/round-trip):")
    print(
        f"  Crabel NR7:    bruto {soma_crabel:+.2f} pts | "
        f"liquido {soma_crabel - custo_crabel:+.2f} pts (USD "
        f"{(soma_crabel - custo_crabel) * 2:+.2f})"
    )
    print(
        f"  Pre-FOMC:      bruto {soma_prefomc:+.2f} pts | "
        f"liquido {soma_prefomc - custo_prefomc:+.2f} pts (USD "
        f"{(soma_prefomc - custo_prefomc) * 2:+.2f})"
    )
    soma_total_bruto = soma_crabel + soma_prefomc
    soma_total_custo = custo_crabel + custo_prefomc
    print(
        f"  PORTFOLIO 1+1: bruto {soma_total_bruto:+.2f} pts | "
        f"liquido {soma_total_bruto - soma_total_custo:+.2f} pts (USD "
        f"{(soma_total_bruto - soma_total_custo) * 2:+.2f})"
    )
    print()
    print(
        f"  Trades total no portfolio: {len(trades_crabel) + len(trades_prefomc)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
