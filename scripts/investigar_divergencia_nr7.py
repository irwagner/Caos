"""Investiga dias divergentes entre Python e C# do filtro NR7.

Para cada dia em que NT8 entrou mas Python nao consideraria elegivel,
mostra os ranges dos ultimos 7 dias uteis e qual era o NR.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(r"e:\CAOS\CAOS_Orchestrator").resolve()))

from caos.walk_forward.estrategias.orb_crabel import (
    _calcular_range_diario,
    MIN_BARRAS_DIA_VALIDO,
)

csvs = [
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\02_MNQ_09-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\03_MNQ_12-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\04_MNQ_03-26.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\05_MNQ_06-26.csv"),
]

dfs = []
for csv in csvs:
    d = pd.read_csv(csv, parse_dates=["timestamp"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    dfs.append(d)
df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

ranges = _calcular_range_diario(df)
dias_ord = sorted(ranges.keys())

dias_divergentes = [
    date(2026, 2, 9),
    date(2026, 2, 23),
    date(2026, 3, 25),
]

# Tambem checa contagem bruta de barras por dia (sem filtros)
df["dia"] = df["timestamp"].dt.date
df["dow"] = df["timestamp"].dt.dayofweek  # 0=Mon
contagem_bruta = df.groupby("dia").agg(
    n_barras=("high", "count"),
    dow=("dow", "first"),
    high_max=("high", "max"),
    low_min=("low", "min"),
)
contagem_bruta["range"] = contagem_bruta["high_max"] - contagem_bruta["low_min"]

for d in dias_divergentes:
    print(f"=== {d} ===")
    # Encontra os 7 dias uteis ANTERIORES no Python (ja filtrados)
    anteriores = [dd for dd in dias_ord if dd < d][-7:]
    print(f"  7 dias uteis VALIDOS anteriores (Python pos-fix):")
    for da in anteriores:
        print(f"    {da} range={ranges[da]:.2f}")
    if anteriores:
        min_range = min(ranges[da] for da in anteriores)
        nr_dia = [da for da in anteriores if ranges[da] == min_range][0]
        print(f"  Menor range = {min_range:.2f} no dia {nr_dia}")
        print(f"  Eh NR7? {anteriores[-1] == nr_dia} (NR7 = ULTIMO dia ser o menor)")
    print()
    # Ja a contagem BRUTA: o que NT8 provavelmente esta usando
    print(f"  Contagem bruta (incluindo dias rejeitados pelo Python):")
    bruta = contagem_bruta.loc[contagem_bruta.index < d].tail(10)
    print(bruta.to_string())
    print()
    # NT8 usa Time[0] em hora local BR (UTC-3). Se o C# nao filtra
    # sabados/domingos por DayOfWeek, ele mantem barras parciais.
    # Verifica se algum dia recente (em hora local BR) bate com NR7 do C#.
    print(f"  Hipotese: C# inclui dias com poucas barras (< {MIN_BARRAS_DIA_VALIDO}) ou dia da semana invalido.")
    print()
