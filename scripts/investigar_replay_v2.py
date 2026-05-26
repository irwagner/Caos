"""Investigacao v2: testar NR4, NR7 e diferentes definicoes de 'dia'.

Hipoteses para por que o NT8 disparou trade em 02-09 e 02-23:
H1: C# usa NR4 em vez de NR7 (constante hardcoded esta NR7=7, mas talvez
    overlay este desativado e a estrategia rode ORB pura).
H2: C# define 'dia' como data LOCAL (America/Chicago no PC do usuario),
    enquanto Python define 'dia' como UTC. Diferenca de 5-6 horas pode
    realocar barras de fim de pregao para o proximo dia.
H3: Replay NT8 inclui pre-mercado/Globex, criando ranges diferentes.

Analisa: Range diario nas 3 definicoes de dia (UTC, ET, dias-uteis-UTC),
e cruza com NR4/NR7.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd

CSV_FONTE = Path(r"e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv")


def calcular_range_por_dia(df: pd.DataFrame, coluna_dia: str) -> pd.DataFrame:
    """Devolve DataFrame com colunas dia, range_dia, n_barras, dow."""
    g = df.groupby(coluna_dia).agg(
        high_max=("high", "max"),
        low_min=("low", "min"),
        n_barras=("high", "count"),
    ).reset_index()
    g["range_dia"] = g["high_max"] - g["low_min"]
    g["dow"] = pd.to_datetime(g[coluna_dia]).dt.dayofweek
    return g[[coluna_dia, "range_dia", "n_barras", "dow"]].sort_values(coluna_dia).reset_index(drop=True)


def encontrar_nr_elegiveis(por_dia: pd.DataFrame, janela: int, coluna_dia: str) -> set:
    """Retorna conjunto de dias elegiveis (apos NR-janela) usando lista ordenada."""
    elegiveis = set()
    dias = por_dia[coluna_dia].tolist()
    ranges = por_dia["range_dia"].tolist()
    for i in range(janela - 1, len(dias)):
        slice_ranges = ranges[i - janela + 1 : i + 1]
        if ranges[i] == min(slice_ranges) and i + 1 < len(dias):
            elegiveis.add(dias[i + 1])
    return elegiveis


def main() -> int:
    df = pd.read_csv(CSV_FONTE, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Tres definicoes de "dia"
    df["dia_utc"] = df["timestamp"].dt.date
    df["dia_et"] = df["timestamp"].dt.tz_convert("America/New_York").dt.date
    df["dia_ct"] = df["timestamp"].dt.tz_convert("America/Chicago").dt.date

    # Filtrar apenas dias uteis em cada definicao
    print("=== Range por dia em cada definicao de 'dia' ===")
    print()

    for coluna in ["dia_utc", "dia_et", "dia_ct"]:
        print(f"--- coluna={coluna} ---")
        por_dia_full = calcular_range_por_dia(df, coluna)
        # Filtrar so seg-sex
        por_dia_uteis = por_dia_full[por_dia_full["dow"] < 5].reset_index(drop=True)
        # Filtrar apenas dias com >=300 barras (RTH minimo decente)
        por_dia_filtrado = por_dia_uteis[por_dia_uteis["n_barras"] >= 300].reset_index(drop=True)

        for nr_janela in [4, 7]:
            elegiveis = encontrar_nr_elegiveis(por_dia_filtrado, nr_janela, coluna)
            elegiveis_periodo = sorted(d for d in elegiveis
                                        if date(2026, 1, 28) <= d <= date(2026, 3, 13))
            tem_02_09 = date(2026, 2, 9) in elegiveis_periodo
            tem_02_23 = date(2026, 2, 23) in elegiveis_periodo
            print(f"  NR{nr_janela}: {len(elegiveis_periodo)} elegiveis. "
                  f"02-09 elegivel? {tem_02_09}  |  02-23 elegivel? {tem_02_23}")
            if tem_02_09 or tem_02_23:
                print(f"     dias: {elegiveis_periodo}")
        print()

    # Mostrar ranges dos dias-chave em cada definicao
    print()
    print("=== Range dos dias-chave (06/02 e 22/02) em cada definicao ===")
    for coluna in ["dia_utc", "dia_et", "dia_ct"]:
        por_dia = calcular_range_por_dia(df, coluna)
        sub = por_dia[
            (por_dia[coluna] >= date(2026, 1, 30)) & (por_dia[coluna] <= date(2026, 2, 25))
        ].reset_index(drop=True)
        print(f"\n  --- {coluna} ---")
        print(sub[[coluna, "range_dia", "n_barras", "dow"]].to_string())

    return 0


if __name__ == "__main__":
    main()
