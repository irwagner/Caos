import pandas as pd
df = pd.read_csv(r'e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv', parse_dates=['timestamp'])
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

print("=== 03-11 OR (13:30-14:00 do log = 16:30-17:00 UTC real) ===")
orb = df[(df['timestamp'] >= '2026-03-11T16:30:00Z') & (df['timestamp'] < '2026-03-11T17:00:00Z')]
print(f"  range: [{orb['low'].min():.2f}, {orb['high'].max():.2f}]")
print(f"  R = {orb['high'].max() - orb['low'].min():.2f}")
print()

print("=== 03-11 entrada 13:36 do log = 16:36 UTC real ===")
sub = df[(df['timestamp'] >= '2026-03-11T16:35:00Z') & (df['timestamp'] <= '2026-03-11T16:45:00Z')]
print(sub.to_string())
print()

print("Log 03-11: entrada=25168.50, stop=25014.75, alvo=25374")
oh = orb['high'].max()
ol = orb['low'].min()
r = oh - ol
print(f"OR_high = {oh:.2f}, OR_low = {ol:.2f}, R = {r:.2f}")
print(f"Entrada esperada (LONG breakout): {oh:.2f}")
print(f"Stop esperado (OR_low): {ol:.2f}")
print(f"Alvo esperado (OR_high + 2R): {oh + 2*r:.2f}")
