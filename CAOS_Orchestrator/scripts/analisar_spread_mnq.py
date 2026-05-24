"""Analisa o spread_minuto.csv produzido pelo agregar_spread_tick.py.

Objetivos:

1. Medir o spread efetivo do MNQ por regime:
   - Hora-do-dia (UTC).
   - Sessao RTH NY (14:30-21:00 UTC) vs overnight.
   - Por dia da semana.
2. Comparar com slippage_fracao_range usado no sweep (0.075 vs real).
3. Computar a relacao spread / range_minuto para informar o
   parametro slippage_fracao_range realista.
4. Salvar relatorio markdown.

Uso: python scripts/analisar_spread_mnq.py <contrato>
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timezone
from pathlib import Path
from statistics import mean, median, quantiles, stdev
from typing import List, Optional

import pandas as pd


def main(contrato: str) -> int:
    raiz = Path(r"e:\CAOS\dados\MNQ") / contrato / "tick"
    spread_csv = raiz / "spread_minuto.csv"
    if not spread_csv.is_file():
        print(f"ERRO: {spread_csv} nao encontrado.", file=sys.stderr)
        return 1

    df = pd.read_csv(spread_csv, parse_dates=["minuto_utc"])
    df["minuto_utc"] = pd.to_datetime(df["minuto_utc"], utc=True)
    print(f"[load] {len(df):,} minutos, periodo "
          f"{df['minuto_utc'].min()} -> {df['minuto_utc'].max()}")

    # Filtra minutos com bid+ask validos.
    com_spread = df.dropna(subset=["spread_avg"])
    print(f"  com_spread: {len(com_spread):,} minutos "
          f"({len(com_spread)/len(df)*100:.1f}%)")

    # Filtra outliers obvios (spread > 5 pts: provavelmente fim de
    # contrato ou halt).
    razoavel = com_spread[com_spread["spread_avg"] <= 5.0]
    print(f"  razoavel (spread <= 5): {len(razoavel):,} "
          f"({len(razoavel)/len(com_spread)*100:.1f}%)")

    range_minuto = (razoavel["last_high"] - razoavel["last_low"]).fillna(0)
    com_range = razoavel[range_minuto > 0]
    range_minuto = (com_range["last_high"] - com_range["last_low"])

    print()
    print("=" * 72)
    print("ESTATISTICAS GERAIS DE SPREAD (pts)")
    print("=" * 72)
    spreads = razoavel["spread_avg"].values
    print(f"  N minutos:        {len(spreads):,}")
    print(f"  spread_avg medio: {spreads.mean():.4f}")
    print(f"  mediana:          {pd.Series(spreads).median():.4f}")
    print(f"  std:              {spreads.std():.4f}")
    print(f"  p10:              {pd.Series(spreads).quantile(0.10):.4f}")
    print(f"  p25:              {pd.Series(spreads).quantile(0.25):.4f}")
    print(f"  p75:              {pd.Series(spreads).quantile(0.75):.4f}")
    print(f"  p90:              {pd.Series(spreads).quantile(0.90):.4f}")
    print(f"  p99:              {pd.Series(spreads).quantile(0.99):.4f}")

    # Sessao RTH NY: 14:30-21:00 UTC.
    razoavel = razoavel.copy()
    razoavel["hora_utc"] = razoavel["minuto_utc"].dt.time
    razoavel["dow"] = razoavel["minuto_utc"].dt.dayofweek
    rth = razoavel[
        (razoavel["hora_utc"] >= time(14, 30))
        & (razoavel["hora_utc"] < time(21, 0))
    ]
    overnight = razoavel[
        (razoavel["hora_utc"] < time(14, 30))
        | (razoavel["hora_utc"] >= time(21, 0))
    ]

    print()
    print("=" * 72)
    print("RTH NY (14:30-21:00 UTC) vs OVERNIGHT")
    print("=" * 72)
    for nome, sub in (("RTH", rth), ("Overnight", overnight)):
        s = sub["spread_avg"]
        if s.empty:
            continue
        print(f"  {nome:<12} N={len(sub):>7,}  "
              f"avg={s.mean():.4f}  med={s.median():.4f}  "
              f"p75={s.quantile(0.75):.4f}  "
              f"p90={s.quantile(0.90):.4f}")

    print()
    print("=" * 72)
    print("SPREAD POR HORA DO DIA (UTC) - top 5 mais e menos liquidos")
    print("=" * 72)
    razoavel["hora_int"] = razoavel["minuto_utc"].dt.hour
    por_hora = razoavel.groupby("hora_int").agg(
        spread_med=("spread_avg", "median"),
        spread_avg=("spread_avg", "mean"),
        n=("spread_avg", "count"),
    ).sort_values("spread_med")
    print("  Mais liquidos (menor spread mediana):")
    for h, row in por_hora.head(5).iterrows():
        print(f"    h={h:>2}h UTC  med={row['spread_med']:.4f}  "
              f"avg={row['spread_avg']:.4f}  n={int(row['n']):>6,}")
    print("  Menos liquidos (maior spread mediana):")
    for h, row in por_hora.tail(5).iterrows():
        print(f"    h={h:>2}h UTC  med={row['spread_med']:.4f}  "
              f"avg={row['spread_avg']:.4f}  n={int(row['n']):>6,}")

    print()
    print("=" * 72)
    print("SPREAD / RANGE_MINUTO (informa slippage_fracao_range realista)")
    print("=" * 72)
    if not com_range.empty:
        razao = com_range["spread_avg"] / range_minuto
        razao = razao[razao.between(0, 5)]  # filtra outliers absurdos
        print(f"  N minutos com range>0: {len(razao):,}")
        print(f"  razao spread/range:")
        print(f"    media:    {razao.mean():.4f}")
        print(f"    mediana:  {razao.median():.4f}")
        print(f"    p25:      {razao.quantile(0.25):.4f}")
        print(f"    p75:      {razao.quantile(0.75):.4f}")
        print(f"    p90:      {razao.quantile(0.90):.4f}")

    print()
    print("=" * 72)
    print("INTERPRETACAO DA REGRA DE OURO")
    print("=" * 72)
    spread_med = pd.Series(spreads).median()
    rth_med = rth["spread_avg"].median()
    overnight_med = overnight["spread_avg"].median()
    print(f"  spread_efetivo_total_medio:    {spread_med:.4f} pts")
    print(f"  spread_RTH_medio:              {rth_med:.4f} pts")
    print(f"  spread_overnight_medio:        {overnight_med:.4f} pts")
    print(f"  slippage_pontos_por_lado fixo: 0.25 pts (config)")
    print(f"  Resultado pratico: spread/2 ja consome o slippage.")
    print(f"  Se slippage_fracao_range fosse REALISTA pelo MNQ:")
    if not com_range.empty:
        razao = com_range["spread_avg"] / range_minuto
        razao = razao[razao.between(0, 5)]
        print(f"    sf_realista = mediana(spread/range) = {razao.median():.4f}")
        print(f"    sf usado no sweep = 0.075 (overestimou: {0.075/razao.median():.1f}x)" if razao.median() > 0 else "")

    # Salva resumo Markdown.
    saida_md = (
        Path(r"e:\CAOS\05_BACKTEST\walk_forward\relatorios\caracterizacao-mnq-minute-2026-05-23")
        / f"caracterizacao-spread-tick-{contrato}-2026-05-24.md"
    )
    linhas = []
    linhas.append(f"# Caracterizacao do spread MNQ tick — {contrato}")
    linhas.append("")
    linhas.append(f"**Data:** 2026-05-24")
    linhas.append(f"**Fonte:** {spread_csv}")
    linhas.append(f"**Periodo:** {df['minuto_utc'].min()} -> {df['minuto_utc'].max()}")
    linhas.append("")
    linhas.append("## Spread agregado por minuto (pts)")
    linhas.append("")
    linhas.append("| Métrica | Valor |")
    linhas.append("|---|---|")
    linhas.append(f"| Minutos analisados | {len(razoavel):,} |")
    linhas.append(f"| Spread médio (geral) | {spreads.mean():.4f} pts |")
    linhas.append(f"| Spread mediano (geral) | {pd.Series(spreads).median():.4f} pts |")
    linhas.append(f"| Spread RTH NY mediano | {rth_med:.4f} pts |")
    linhas.append(f"| Spread overnight mediano | {overnight_med:.4f} pts |")
    linhas.append(f"| Spread p90 | {pd.Series(spreads).quantile(0.90):.4f} pts |")
    linhas.append(f"| Spread p99 | {pd.Series(spreads).quantile(0.99):.4f} pts |")
    linhas.append("")
    if not com_range.empty:
        razao = com_range["spread_avg"] / range_minuto
        razao = razao[razao.between(0, 5)]
        linhas.append("## Razão spread / range_minuto (informa slippage_fracao_range)")
        linhas.append("")
        linhas.append("| Estatística | Valor |")
        linhas.append("|---|---|")
        linhas.append(f"| Mediana | {razao.median():.4f} |")
        linhas.append(f"| Média | {razao.mean():.4f} |")
        linhas.append(f"| p25 | {razao.quantile(0.25):.4f} |")
        linhas.append(f"| p75 | {razao.quantile(0.75):.4f} |")
        linhas.append(f"| p90 | {razao.quantile(0.90):.4f} |")
        linhas.append("")
        linhas.append(f"**Implicação:** o `slippage_fracao_range=0.075` usado no sweep "
                      f"superestima a fricção realista por **{0.075/razao.median():.1f}x** "
                      f"(mediana real ~{razao.median():.4f}).")
        linhas.append("")
    linhas.append("## Spread por hora UTC")
    linhas.append("")
    linhas.append("| Hora UTC | spread mediano | spread médio | N minutos |")
    linhas.append("|---|---|---|---|")
    por_hora = razoavel.groupby("hora_int").agg(
        spread_med=("spread_avg", "median"),
        spread_avg=("spread_avg", "mean"),
        n=("spread_avg", "count"),
    ).sort_index()
    for h, row in por_hora.iterrows():
        linhas.append(f"| {h:02d} | {row['spread_med']:.4f} | "
                      f"{row['spread_avg']:.4f} | {int(row['n']):,} |")
    linhas.append("")
    saida_md.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"\n[done] relatorio em {saida_md}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
