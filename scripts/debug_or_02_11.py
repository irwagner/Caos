import pandas as pd

df = pd.read_csv(r'e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv', parse_dates=['timestamp'])
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

# Janelas a testar
janelas = [
    ("16:30-17:00 UTC", "2026-02-11T16:30:00Z", "2026-02-11T17:00:00Z"),
    ("13:30-14:00 UTC", "2026-02-11T13:30:00Z", "2026-02-11T14:00:00Z"),
    ("19:30-20:00 UTC", "2026-02-11T19:30:00Z", "2026-02-11T20:00:00Z"),
    ("14:30-15:00 UTC", "2026-02-11T14:30:00Z", "2026-02-11T15:00:00Z"),
]

# Stop esperado pelo log: 25324.75
print("Procurando janela onde OR_low = 25324.75 (stop do log):")
print()
for nome, ini, fim in janelas:
    sub = df[(df['timestamp'] >= ini) & (df['timestamp'] < fim)]
    if len(sub) == 0:
        continue
    or_low = sub['low'].min()
    or_high = sub['high'].max()
    bate = abs(or_low - 25324.75) < 1.0
    marca = " <- BATE!" if bate else ""
    print(f"  {nome}: OR_low={or_low:.2f}  OR_high={or_high:.2f}  range={or_high - or_low:.2f}{marca}")

# Procurar TODAS as barras de 02-11 com low entre 25320 e 25330
print()
print("Barras de 02-11 com low em [25320, 25330]:")
sub = df[(df['timestamp'].dt.date == pd.Timestamp("2026-02-11").date()) &
         (df['low'] >= 25320) & (df['low'] <= 25330)]
print(sub.to_string())
