"""Investiga qual contrato MNQ o NT8 usou no replay 02-11 14:31 UTC.

Trade do log:
  preco_entrada = 25455.25
  stop = 25324.75 (130.5 pts abaixo)
  alvo = 25713.25 (258 pts acima)
  range_R = 130.5 pts

Compara com cada CSV disponivel para ver qual bate com 25455.
"""

from pathlib import Path
import pandas as pd

PRECO_ALVO_LOG = 25455.25
TIMESTAMP_ALVO = "2026-02-11T14:31:00Z"

raiz = Path(r"e:\CAOS\dados\MNQ")
csvs = sorted(raiz.glob("MNQ_*/minute/last.csv"))

print(f"Procurando preco {PRECO_ALVO_LOG} em {TIMESTAMP_ALVO} entre contratos:")
print()
for p in csvs:
    nome = p.parts[-3]
    df = pd.read_csv(p, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    sub = df[(df["timestamp"] >= "2026-02-11T14:30:00Z") &
             (df["timestamp"] <= "2026-02-11T14:35:00Z")]
    if len(sub) == 0:
        print(f"  {nome:<12}: (sem dados em 02-11)")
        continue
    h_max = sub["high"].max()
    l_min = sub["low"].min()
    print(f"  {nome:<12}: range 14:30-14:35 = [{l_min:.2f}, {h_max:.2f}]  range diario do dia:")
    dia = df[df["timestamp"].dt.date == pd.Timestamp("2026-02-11").date()]
    if len(dia) > 0:
        print(f"            range 02-11 dia: [{dia['low'].min():.2f}, {dia['high'].max():.2f}] = {dia['high'].max() - dia['low'].min():.2f} pts")
    print()

print("===")
print(f"Preco do log: {PRECO_ALVO_LOG}")
print()
print("Conclusao:")
print(f"  Se algum contrato tem preco {PRECO_ALVO_LOG} em 02-11 14:31, era esse")
print("  o contrato carregado pelo NT8. Caso nenhum bata, o NT8 usou")
print("  contrato continuous (## ##) que aplica back-adjusted prices.")
