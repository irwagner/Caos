"""Auditoria de paridade Python <-> C# do filtro NR7.

Compara os 11 dias em que o NT8 disparou trade (replay limpo 2026-05-28)
com os dias que o Python EstrategiaORBCrabel(modo='nr7') considera
elegiveis no mesmo periodo.

Discrepancia revela bug de paridade.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(r"e:\CAOS\CAOS_Orchestrator").resolve()))

from caos.walk_forward.estrategias.orb_crabel import (
    _calcular_range_diario,
    _dias_apos_nr,
)

# Dias em que NT8 disparou trade (do replay 2026-05-28)
dias_nt8 = [
    date(2026, 2, 9),   # 1 - SHORT (suspeito - antes tinha sido filtrado pelo fix)
    date(2026, 2, 11),  # 2 - LONG
    date(2026, 2, 23),  # 3 - LONG (suspeito - antes filtrado pelo fix)
    date(2026, 3, 11),  # 4 - LONG
    date(2026, 3, 25),  # 5 - SHORT
    date(2026, 3, 26),  # 6 - SHORT
    date(2026, 4, 6),   # 7 - SHORT
    date(2026, 4, 28),  # 8 - SHORT
    date(2026, 5, 12),  # 9 - SHORT
    date(2026, 5, 25),  # 10 - SHORT
    date(2026, 5, 26),  # 11 - LONG
]

# CSVs disponiveis (concat dos 5 contratos)
csvs = [
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\02_MNQ_09-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\03_MNQ_12-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\04_MNQ_03-26.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\05_MNQ_06-26.csv"),
]

print("Carregando dataset Python (5 contratos concat)...")
dfs = []
for csv in csvs:
    d = pd.read_csv(csv, parse_dates=["timestamp"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    dfs.append(d)
df = (
    pd.concat(dfs, ignore_index=True)
    .drop_duplicates(subset=["timestamp"])
    .sort_values("timestamp")
    .reset_index(drop=True)
)
print(f"  {len(df)} barras totais, {df['timestamp'].min()} a {df['timestamp'].max()}")
print()

# Calcula NR7 elegiveis pelo Python (com fix de domingos)
ranges_por_dia = _calcular_range_diario(df)
elegiveis_python, _ = _dias_apos_nr(ranges_por_dia, janela=7)

print(f"Total dias com range valido (Python pos-fix): {len(ranges_por_dia)}")
print(f"Total dias NR7-elegiveis (Python pos-fix):    {len(elegiveis_python)}")
print()

# Cruza com dias do NT8
print("=" * 80)
print(f"{'#':<3} {'Data':<12} {'C#-NT8':<8} {'Python':<8} {'Match?':<8} {'Range CSV':<12}")
print("=" * 80)

casos_diff = []
for i, dia in enumerate(dias_nt8, 1):
    py_eleg = "SIM" if dia in elegiveis_python else "NAO"
    range_csv = ranges_por_dia.get(dia, "NO_DATA")
    if range_csv != "NO_DATA":
        range_csv = f"{range_csv:.2f}"
    nt8_eleg = "SIM"  # Por definicao, NT8 disparou trade nesse dia
    match = "OK" if dia in elegiveis_python else "DIFF"
    if match == "DIFF":
        casos_diff.append(dia)
    print(f"{i:<3} {str(dia):<12} {nt8_eleg:<8} {py_eleg:<8} {match:<8} {range_csv}")

print()
print(f"Resumo: {len(dias_nt8) - len(casos_diff)}/{len(dias_nt8)} matches.")
print(f"Divergencias C#-NT8 entrou mas Python NAO consideraria elegivel: {len(casos_diff)}")
if casos_diff:
    print()
    print("Dias em que NT8 entrou mas Python rejeitaria:")
    for d in casos_diff:
        print(f"  - {d}")

# Tambem cruza no sentido inverso: dias que Python permitiria mas NT8 nao operou
print()
print("Dias NR7-elegiveis pelo Python no periodo 02-09 a 05-26:")
periodo_inicio = date(2026, 2, 9)
periodo_fim = date(2026, 5, 26)
elegiveis_no_periodo = sorted(
    d for d in elegiveis_python if periodo_inicio <= d <= periodo_fim
)
print(f"  Total: {len(elegiveis_no_periodo)} dias")
nt8_set = set(dias_nt8)
nao_operados = [d for d in elegiveis_no_periodo if d not in nt8_set]
print(f"  Operados pelo NT8: {len(elegiveis_no_periodo) - len(nao_operados)}")
print(f"  NAO operados pelo NT8 (Python permitiria): {len(nao_operados)}")
if nao_operados:
    print("  Lista:")
    for d in nao_operados:
        r = ranges_por_dia.get(d, 0)
        print(f"    - {d}  range={r:.2f}")
