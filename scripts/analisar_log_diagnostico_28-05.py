"""Le o log do replay 2026-05-28 e extrai estado do filtro NR7 do C#
nos dias em que houve trade.

Objetivo: descobrir por que C# considerou 02-09, 02-23, 03-25, 05-25, 05-26
elegiveis quando Python nao considera.
"""
import json
import re
from pathlib import Path

LOG = Path(r"e:\CAOS\05_BACKTEST\logs\2026-05-28-StrategyORBCrabelSpreadFilter.log")

dias_de_trade = [
    "2026-02-09", "2026-02-11", "2026-02-23", "2026-03-11",
    "2026-03-25", "2026-03-26", "2026-04-06", "2026-04-28",
    "2026-05-12", "2026-05-25", "2026-05-26",
]

# Le linhas do log
linhas = LOG.read_text(encoding="utf-8").splitlines()
# Extrai diagnostico-dia events para cada dia de trade
print("=" * 80)
print("DIAGNOSTICO C# (do log) PARA OS 11 DIAS DE TRADE")
print("=" * 80)

for dia in dias_de_trade:
    print(f"\n--- {dia} ---")
    # Busca eventos diagnostico-dia para esse dia (pega o ULTIMO)
    eventos_do_dia = []
    for linha in linhas:
        if "diagnostico-dia" in linha and f'"dia":"{dia}"' in linha:
            # Extrai payload JSON
            idx = linha.find("{")
            if idx >= 0:
                try:
                    payload = json.loads(linha[idx:])
                    eventos_do_dia.append(payload)
                except json.JSONDecodeError:
                    continue
    if eventos_do_dia:
        # Ultimo evento (estado mais recente)
        p = eventos_do_dia[-1]
        eleg = p.get("elegivel")
        n_hist = p.get("dias_no_historico")
        ranges = p.get("ranges_ultimos_7_dias", "")
        print(f"  C#: elegivel={eleg}, dias_no_historico={n_hist}")
        print(f"  ranges_ultimos_7: {ranges}")
    else:
        print("  (sem evento de diagnostico para este dia no log)")
