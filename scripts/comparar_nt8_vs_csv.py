"""Compara o range diario que o NT8 enxerga (extraido do log de diagnostico)
com o range diario do CSV last.csv do MNQ_03-26.

Permite descobrir se a divergencia e nos dados (NT8 carregou outro
contrato/sessao) ou no calculo (mesmo CSV, range diferente).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd


LOG_NT8 = Path(r"e:\CAOS\05_BACKTEST\logs\2026-05-26-StrategyORBCrabelSpreadFilter.log")
CSV_FONTE = Path(r"e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv")


def parse_log_nt8(caminho: Path) -> dict[date, float]:
    """Extrai mapa data -> range_dia que o NT8 reporta no campo
    `ranges_ultimos_7_dias` do payload diagnostico-dia. Cada dia
    aparece uma vez, na primeira mensagem que o cita.
    """
    ranges: dict[date, float] = {}
    pattern = re.compile(r'"(\d{4}-\d{2}-\d{2})=([\d,]+)"')
    with caminho.open("r", encoding="utf-8") as f:
        for linha in f:
            if "diagnostico-dia" not in linha:
                continue
            payload_idx = linha.find("{")
            if payload_idx < 0:
                continue
            try:
                payload = json.loads(linha[payload_idx:])
            except json.JSONDecodeError:
                continue
            ranges_str = payload.get("ranges_ultimos_7_dias")
            if not ranges_str:
                continue
            # Formato: "2026-02-09=473,50,2026-02-10=249,50,..."
            # NT8 usa virgula como separador decimal e separador de
            # itens — ambiguo. Solucao: split em pares "AAAA-MM-DD=N,DD"
            # via regex sobre o texto inteiro.
            for parte in ranges_str.split(","):
                pass
            # Reparse manual: junta tokens em pares
            tokens = ranges_str.split(",")
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if "=" in tok:
                    chave, parte_inteira = tok.split("=")
                    try:
                        d = date.fromisoformat(chave.strip())
                    except ValueError:
                        i += 1
                        continue
                    # Proximo token e a parte decimal
                    if i + 1 < len(tokens) and tokens[i + 1].strip().isdigit():
                        parte_dec = tokens[i + 1].strip()
                        valor_str = f"{parte_inteira.strip()}.{parte_dec}"
                        valor = float(valor_str)
                        if d not in ranges:
                            ranges[d] = valor
                        i += 2
                        continue
                    else:
                        # Inteiro puro
                        try:
                            ranges[d] = float(parte_inteira.strip())
                        except ValueError:
                            pass
                        i += 1
                else:
                    i += 1
    return ranges


def calcular_range_csv(caminho: Path, dias_alvo: set[date]) -> dict[date, float]:
    """Calcula range diario do CSV: max(high) - min(low) por data UTC."""
    df = pd.read_csv(caminho, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["dia"] = df["timestamp"].dt.date
    df = df[df["dia"].isin(dias_alvo)].copy()
    g = df.groupby("dia").agg(
        high_max=("high", "max"),
        low_min=("low", "min"),
    )
    return {d: float(row["high_max"] - row["low_min"]) for d, row in g.iterrows()}


def main() -> int:
    print("=== Range diario NT8 vs CSV last.csv ===")
    print()

    nt8_ranges = parse_log_nt8(LOG_NT8)
    print(f"NT8 reportou range para {len(nt8_ranges)} dias.")

    csv_ranges = calcular_range_csv(CSV_FONTE, set(nt8_ranges.keys()))
    print(f"CSV calculou range para {len(csv_ranges)} dias.")
    print()

    print(f"{'data':<12} {'NT8':>10} {'CSV':>10} {'diff':>10} {'match?':>8}")
    print("-" * 56)
    matches = 0
    diffs = 0
    only_nt8 = 0
    for d in sorted(nt8_ranges.keys()):
        r_nt8 = nt8_ranges[d]
        r_csv = csv_ranges.get(d)
        if r_csv is None:
            print(f"{str(d):<12} {r_nt8:>10.2f} {'(faltando no CSV)':>20}")
            only_nt8 += 1
            continue
        diff = r_nt8 - r_csv
        match = abs(diff) < 0.01
        marca = "OK" if match else "DIFF"
        print(f"{str(d):<12} {r_nt8:>10.2f} {r_csv:>10.2f} {diff:>+10.2f}   [{marca}]")
        if match:
            matches += 1
        else:
            diffs += 1

    print()
    print(f"Resumo: {matches} match, {diffs} diferentes, {only_nt8} so no NT8.")
    print()

    # Replicar NR7 com os ranges DO NT8 (oraculo) e ver quais dias
    # foram corretamente identificados como elegiveis.
    print("=== NR7 calculado a partir dos ranges do NT8 ===")
    print()
    dias_ord = sorted(nt8_ranges.keys())
    for i, d in enumerate(dias_ord):
        if i < 6:
            continue
        slice_dias = dias_ord[i - 6 : i + 1]
        ranges = [nt8_ranges[dd] for dd in slice_dias]
        eh_nr7 = nt8_ranges[d] == min(ranges)
        proximo = dias_ord[i + 1] if i + 1 < len(dias_ord) else None
        if eh_nr7:
            print(f"  {d} foi NR7 (range={nt8_ranges[d]:.2f}) -> "
                  f"proximo dia ({proximo}) elegivel")

    return 0


if __name__ == "__main__":
    main()
