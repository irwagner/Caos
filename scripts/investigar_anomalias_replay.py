"""Investigacao das anomalias do diagnostico do replay.

Foca em:
1. Dia 2026-02-01 com range=0.00 (suspeita: domingo, sessao curta).
2. Trade do NT8 em 2026-02-09 (SHORT) que NAO e NR7 pelo CSV — entender
   se o NR7 do C# usa janela diferente, ou se o dataset NT8 difere.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

CSV_FONTE = Path(r"e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv")


def main() -> int:
    df = pd.read_csv(CSV_FONTE, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["dia"] = df["timestamp"].dt.date
    df["dow"] = df["timestamp"].dt.day_name()

    print("=== Inspecao 2026-02-01 (range=0.00 reportado) ===")
    sub = df[df["dia"] == date(2026, 2, 1)]
    print(f"  barras: {len(sub)}")
    if len(sub) > 0:
        print(f"  dow: {sub['dow'].iloc[0]}")
        print(f"  primeiro: {sub['timestamp'].min()}")
        print(f"  ultimo:   {sub['timestamp'].max()}")
        print(f"  high_max={sub['high'].max():.2f} low_min={sub['low'].min():.2f}")
        print(f"  range={sub['high'].max() - sub['low'].min():.2f}")
        print(f"  primeiras 3:")
        print(sub.head(3).to_string())
        print(f"  ultimas 3:")
        print(sub.tail(3).to_string())

    print()
    print("=== Inspecao janela NR7 ao redor de 2026-02-09 ===")
    print()
    # Para 2026-02-09 ser elegivel, o dia 2026-02-08 (ou ultimo dia util antes)
    # deve ter sido NR7. Vamos olhar todos os dias com range, ordenados.
    por_dia = df.groupby("dia").agg(
        range_dia=("high", lambda x: x.max() - df.loc[x.index, "low"].min()),
        n_barras=("high", "count"),
        dow=("dow", "first"),
    ).reset_index()
    # Recalcula range corretamente
    por_dia["range_dia"] = df.groupby("dia").apply(lambda g: g["high"].max() - g["low"].min()).values
    # Filtra para janela ao redor de 02-09
    janela = por_dia[
        (por_dia["dia"] >= date(2026, 1, 26)) & (por_dia["dia"] <= date(2026, 2, 10))
    ].sort_values("dia").reset_index(drop=True)

    print(janela.to_string())
    print()
    # Calcula NR7 manualmente em cada dia da janela
    print("=== NR7 manual: para cada dia, range e o menor dos ultimos 7? ===")
    print()
    todos_dias_ord = sorted(por_dia["dia"].tolist())
    print(f"{'dia':<14} {'dow':<10} {'range':>8} {'min_ult7':>10} {'eh_NR7':>7}")
    for i, dia in enumerate(todos_dias_ord):
        if dia < date(2026, 1, 26) or dia > date(2026, 2, 10):
            continue
        if i < 6:
            continue
        ult7 = todos_dias_ord[max(0, i - 6) : i + 1]
        ranges_ult7 = por_dia.loc[por_dia["dia"].isin(ult7), "range_dia"].tolist()
        range_dia = por_dia.loc[por_dia["dia"] == dia, "range_dia"].iloc[0]
        dow = por_dia.loc[por_dia["dia"] == dia, "dow"].iloc[0]
        eh_nr7 = range_dia == min(ranges_ult7)
        marca = "** NR7 **" if eh_nr7 else ""
        print(f"{str(dia):<14} {dow:<10} {range_dia:>8.2f} {min(ranges_ult7):>10.2f} {marca}")

    print()
    print("=== Conclusao ===")
    print()
    print("Para o trade do NT8 em 2026-02-09 ser legitimo, o dia 2026-02-06")
    print("(sexta, ultimo pregao antes) deveria ter sido NR7 — ou o C# esta")
    print("usando dias corridos (incluindo sabado/domingo) o que gera dias-zero.")
    print()
    print("Inspecao 2026-02-08 (domingo, dia que abre Globex):")
    sub = df[df["dia"] == date(2026, 2, 8)]
    if len(sub) > 0:
        print(f"  {len(sub)} barras, primeiro: {sub['timestamp'].min()}, ultimo: {sub['timestamp'].max()}")
        print(f"  range={sub['high'].max() - sub['low'].min():.2f}")
    else:
        print("  (sem barras)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
