"""Compara spread_minuto.csv entre contratos disponiveis.

Junta todos os spread_minuto.csv encontrados em dados/MNQ/<contrato>/tick/
e produz tabela e grafico (ASCII) de evolucao temporal.

Uso: python scripts/comparar_spread_contratos.py
"""

from __future__ import annotations

import sys
from datetime import time
from pathlib import Path
from typing import List

import pandas as pd


def main() -> int:
    raiz = Path(r"e:\CAOS\dados\MNQ")
    contratos = []
    for tick_dir in sorted(raiz.glob("MNQ_*/tick")):
        csv = tick_dir / "spread_minuto.csv"
        if csv.is_file() and csv.stat().st_size > 100 * 1024:
            contratos.append((tick_dir.parent.name, csv))

    if not contratos:
        print("Nenhum spread_minuto.csv encontrado.")
        return 1

    print(f"Contratos disponiveis: {len(contratos)}")
    for nome, _ in contratos:
        print(f"  - {nome}")
    print()

    dfs: List[pd.DataFrame] = []
    for nome, csv in contratos:
        df = pd.read_csv(csv, parse_dates=["minuto_utc"])
        df["minuto_utc"] = pd.to_datetime(df["minuto_utc"], utc=True)
        df["contrato"] = nome
        dfs.append(df)
    df_all = pd.concat(dfs, ignore_index=True)
    print(f"Total minutos agregados: {len(df_all):,}")

    # Filtra spread valido e razoavel.
    df_all = df_all.dropna(subset=["spread_avg"])
    df_all = df_all[df_all["spread_avg"].between(0, 5)]
    print(f"Apos filtro razoavel: {len(df_all):,}")
    print()

    # Estatistica por contrato.
    print("=" * 88)
    print("SPREAD POR CONTRATO (pts)")
    print("=" * 88)
    print(f"{'Contrato':<14} {'N min':>8} {'Periodo':<25} {'mediana':>9} "
          f"{'media':>9} {'p75':>8} {'p90':>8}")
    for nome, sub in df_all.groupby("contrato"):
        med = sub["spread_avg"].median()
        avg = sub["spread_avg"].mean()
        p75 = sub["spread_avg"].quantile(0.75)
        p90 = sub["spread_avg"].quantile(0.90)
        ini = sub["minuto_utc"].min().date()
        fim = sub["minuto_utc"].max().date()
        periodo = f"{ini}->{fim}"
        print(f"{nome:<14} {len(sub):>8,} {periodo:<25} "
              f"{med:>9.4f} {avg:>9.4f} {p75:>8.4f} {p90:>8.4f}")
    print()

    # Spread por mes (evolucao temporal).
    df_all["ano_mes"] = df_all["minuto_utc"].dt.to_period("M")
    print("=" * 88)
    print("EVOLUCAO TEMPORAL (spread mediana por mes)")
    print("=" * 88)
    por_mes = df_all.groupby("ano_mes").agg(
        spread_med=("spread_avg", "median"),
        spread_avg=("spread_avg", "mean"),
        n=("spread_avg", "count"),
    ).sort_index()
    print(f"{'Ano-mes':<10} {'mediana':>9} {'media':>9} {'N':>8} {'barra':<40}")
    max_med = por_mes["spread_med"].max()
    for am, row in por_mes.iterrows():
        bar_len = int(row["spread_med"] / max_med * 40)
        bar = "#" * bar_len
        print(f"{str(am):<10} {row['spread_med']:>9.4f} {row['spread_avg']:>9.4f} "
              f"{int(row['n']):>8,} {bar}")
    print()

    # RTH vs overnight.
    print("=" * 88)
    print("RTH NY (14:30-21:00 UTC) vs OVERNIGHT - todos os contratos")
    print("=" * 88)
    df_all["hora"] = df_all["minuto_utc"].dt.time
    rth = df_all[
        (df_all["hora"] >= time(14, 30))
        & (df_all["hora"] < time(21, 0))
    ]
    overnight = df_all[
        (df_all["hora"] < time(14, 30))
        | (df_all["hora"] >= time(21, 0))
    ]
    for nome, sub in (("RTH       ", rth), ("Overnight ", overnight)):
        s = sub["spread_avg"]
        print(f"  {nome} N={len(sub):>8,}  "
              f"med={s.median():.4f}  avg={s.mean():.4f}  "
              f"p75={s.quantile(0.75):.4f}  p90={s.quantile(0.90):.4f}")
    print()

    # Salva relatorio markdown consolidado.
    saida_md = (
        Path(r"e:\CAOS\05_BACKTEST\walk_forward\relatorios"
             r"\caracterizacao-mnq-minute-2026-05-23")
        / "caracterizacao-spread-tick-todos-contratos-2026-05-24.md"
    )
    linhas = []
    linhas.append("# Caracterizacao do spread MNQ tick — todos os contratos")
    linhas.append("")
    linhas.append(f"**Data:** 2026-05-24")
    linhas.append(f"**Contratos cobertos:** {', '.join(c for c, _ in contratos)}")
    linhas.append(f"**Total de minutos:** {len(df_all):,}")
    linhas.append("")
    linhas.append("## Spread por contrato")
    linhas.append("")
    linhas.append("| Contrato | N min | Período | Mediana | Média | p75 | p90 |")
    linhas.append("|---|---|---|---|---|---|---|")
    for nome, sub in df_all.groupby("contrato"):
        med = sub["spread_avg"].median()
        avg = sub["spread_avg"].mean()
        p75 = sub["spread_avg"].quantile(0.75)
        p90 = sub["spread_avg"].quantile(0.90)
        ini = sub["minuto_utc"].min().date()
        fim = sub["minuto_utc"].max().date()
        linhas.append(f"| {nome} | {len(sub):,} | {ini} → {fim} | "
                      f"{med:.4f} | {avg:.4f} | {p75:.4f} | {p90:.4f} |")
    linhas.append("")
    linhas.append("## Evolução por mês")
    linhas.append("")
    linhas.append("| Ano-mês | Spread mediana | Spread média | N minutos |")
    linhas.append("|---|---|---|---|")
    for am, row in por_mes.iterrows():
        linhas.append(f"| {am} | {row['spread_med']:.4f} | "
                      f"{row['spread_avg']:.4f} | {int(row['n']):,} |")
    linhas.append("")
    linhas.append("## RTH vs Overnight (consolidado)")
    linhas.append("")
    linhas.append("| Regime | N minutos | Mediana | Média | p75 | p90 |")
    linhas.append("|---|---|---|---|---|---|")
    for nome, sub in (("RTH NY 14:30-21:00 UTC", rth), ("Overnight", overnight)):
        s = sub["spread_avg"]
        linhas.append(f"| {nome} | {len(sub):,} | "
                      f"{s.median():.4f} | {s.mean():.4f} | "
                      f"{s.quantile(0.75):.4f} | {s.quantile(0.90):.4f} |")
    linhas.append("")
    saida_md.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"[done] relatorio em {saida_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
