"""Confirma o bug de timezone no Strategy_CAOS C#.

Hipotese: NT8 chama Time[0].ToUniversalTime() onde Time[0] vem com
DateTime.Kind != Utc (provavelmente Unspecified/Local). Em maquina
BR (UTC-3), isso ADICIONA 3h ao timestamp em vez de manter como UTC.

Evidencia: trade do log diz entrada 02-11 14:31 UTC com preco 25455.25.
Mas o preco 25455 SO aparece no CSV em 02-11 17:30 UTC (3h depois).

Verificacao: se aplicarmos -3h ao timestamp do log, a entrada cai
em 02-11 11:31 UTC, e o stop/alvo do log devem bater com o range
calculado pelo ORB nas 30 primeiras barras DESSA janela.
"""
import pandas as pd

CSV = r'e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv'

df = pd.read_csv(CSV, parse_dates=['timestamp'])
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

# Log diz: entrada 14:31 UTC, preco 25455.25, stop 25324.75
# Hipotese: timestamp real = 14:31 - 3h = 11:31? ou +3h = 17:31?
# Preco 25455 esta entre 16:57 e 17:33 UTC. Logo bate com +3h.
# Mas isso significa que o "UTC" do log eh na verdade hora local
# BR, e o evento real foi 17:31 UTC.

print("=== Hipotese: log_timestamp = local_BR (UTC-3), evento_real = log + 3h ===")
print()
ts_log = pd.Timestamp("2026-02-11T14:31:00Z")
ts_real_UTC = ts_log + pd.Timedelta(hours=3)
print(f"Log diz: {ts_log}")
print(f"Real (log + 3h): {ts_real_UTC}")
print()

# ORB do dia: SessaoInicioUtc = 13:30 (no log, mas se a logica
# C# tambem usa o "UTC errado", entao 13:30 do log = 16:30 UTC real)
# MinutosOR = 30 → janela 13:30-14:00 do log = 16:30-17:00 UTC real
print("=== Janela ORB das primeiras 30 barras (13:30-14:00 do log = 16:30-17:00 UTC real) ===")
sub_or = df[(df['timestamp'] >= '2026-02-11T16:30:00Z') &
            (df['timestamp'] < '2026-02-11T17:00:00Z')]
or_low = sub_or['low'].min()
or_high = sub_or['high'].max()
print(f"  range OR: [{or_low:.2f}, {or_high:.2f}] = {or_high - or_low:.2f} pts")
print()

# Entrada: 14:31 do log = 17:31 UTC real
print("=== Barra de entrada (14:31 do log = 17:31 UTC real) ===")
sub_entry = df[(df['timestamp'] >= '2026-02-11T17:30:00Z') &
                (df['timestamp'] <= '2026-02-11T17:35:00Z')]
print(sub_entry.to_string())
print()

# Stop esperado para LONG breakout: low_OR (porque entra em high+epsilon
# e stop fica no low_OR)
range_R = or_high - or_low
stop_esperado_long = or_low  # nesse padrao ORB classico
alvo_esperado_long = or_high + 2 * range_R  # alvo 2R
print(f"Estrategia ORB Crabel:")
print(f"  OR_high = {or_high:.2f}")
print(f"  OR_low = {or_low:.2f}")
print(f"  R = {range_R:.2f}")
print(f"  Entrada LONG = OR_high + epsilon ~ {or_high:.2f}")
print(f"  Stop esperado = OR_low = {or_low:.2f}")
print(f"  Alvo esperado = OR_high + 2R = {or_high + 2 * range_R:.2f}")
print()
print("Log diz:")
print(f"  Entrada: 25455.25")
print(f"  Stop:    25324.75")
print(f"  Alvo:    25713.25")
print()
print("Bate?", "SIM" if abs(or_high - 25455.25) < 5 else "NAO",
      "(entrada vs OR_high)")
print("Bate?", "SIM" if abs(or_low - 25324.75) < 5 else "NAO",
      "(stop vs OR_low)")
