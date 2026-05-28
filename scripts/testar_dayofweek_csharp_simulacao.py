"""Simula como C# em maquina BR (UTC-3) ve as barras.

Hipotese: NT8 chama Time[0].ToUniversalTime() em DateTime com Kind=Local.
Isso adiciona 3h ao timestamp REAL UTC, fazendo barras de fim de pregao
(22-23 UTC = 19-20 BR) virarem barras "do dia seguinte UTC errado".

Resultado pratico: o C# pode estar incluindo barras de DOMINGO (real UTC)
como sendo de SEGUNDA (porque ToUniversalTime adicionou 3h indevidamente,
empurrando para o dia seguinte). E vice-versa.

Vamos checar 2026-02-08 (domingo real):
- Globex abre 22:00 UTC do domingo (=18:00 ET = 19:00 BR)
- Em maquina BR, Time[0] retornaria 19:00 (Kind=Local).
- ToUniversalTime adiciona 3h -> 22:00 UTC mesmo dia (correto se Kind=Local
  mas seria errado se ja era UTC; o NT8 trata Time[0] como Local).
- Entao a barra de 22:00 UTC real eh marcada como 22:00 do dia ja.
  No C# DiaDaSemanaEhValido(2026-02-08) = Sunday = false. Filtra.

MAS: e se Time[0] vem com Kind=Unspecified ou Kind=Utc? ToUniversalTime
pode comportar-se diferente.

Vamos testar 3 cenarios e ver qual bate com o trade observado em 02-09.
"""
from datetime import datetime, timezone, timedelta

# Hipotese 1: Time[0] vem como Local BR (UTC-3). ToUniversalTime soma 3h.
# Hipotese 2: Time[0] vem como UTC ja, mas marcado Kind=Local. ToUniversalTime
#   soma 3h indevidamente, marca como dia "seguinte" ja.
# Hipotese 3: Time[0] vem como UTC com Kind=Unspecified. ToUniversalTime
#   acha que eh Local e converte (= soma 3h).

# Uma barra real: 2026-02-08 22:00 UTC (abertura Globex domingo)
ts_utc_real = datetime(2026, 2, 8, 22, 0, 0, tzinfo=timezone.utc)
print(f"Barra real UTC: {ts_utc_real}")
print(f"  Em hora local BR (UTC-3): {ts_utc_real.astimezone(timezone(timedelta(hours=-3)))}")
print()

# Cenario H2: NT8 retorna Time[0] como '2026-02-08 22:00' com Kind=Local.
# Em maquina BR, ToUniversalTime SOMA 3h:
ts_h2_falso_local = datetime(2026, 2, 8, 22, 0, 0)  # naive (Kind=Unspecified, mas C# trata como Local)
ts_h2_apos_to_universal = ts_h2_falso_local + timedelta(hours=3)
print(f"H2 (NT8 retorna como falso Local + ToUniversalTime soma 3h):")
print(f"  Time[0] = {ts_h2_falso_local}  (sem tz)")
print(f"  ToUniversalTime() = {ts_h2_apos_to_universal}  (UTC errado, +3h)")
print(f"  Date = {ts_h2_apos_to_universal.date()} = {ts_h2_apos_to_universal.strftime('%A')}")
print()

# Esse mesmo cenario H2 em barras de 22-23 UTC reais:
print("Cenario H2 em barras criticas:")
for h_utc_real in [22, 23, 0, 1, 2, 3]:
    if h_utc_real >= 22:
        # Mesmo dia
        ts_real = datetime(2026, 2, 8, h_utc_real, 0)
    else:
        # Dia seguinte UTC
        ts_real = datetime(2026, 2, 9, h_utc_real, 0)
    ts_apos = ts_real + timedelta(hours=3)
    print(f"  Barra real {ts_real.strftime('%a %Y-%m-%d %H:%M')} UTC -> "
          f"NT8 marca como {ts_apos.strftime('%a %Y-%m-%d %H:%M')} (.Date = {ts_apos.date()})")
print()

# Verificacao: que barras o C# vai entregar para o filtro NR7?
# Como o filtro NR7 usa timestampUtc.Date e DayOfWeek desse Date, o
# dia "fictício" virá no calculo de range diario.
print("=" * 70)
print("CONCLUSAO:")
print("Em 02-08 (domingo) das 22:00 UTC reais ate 23:59 UTC reais:")
print("  - Tempo real: domingo")
print("  - C# vê (ToUniversalTime falso): segunda 02-09 01:00-02:59 UTC")
print()
print("Barras de domingo Globex (22-23 UTC do domingo) sao marcadas pelo")
print("C# como sendo de SEGUNDA (02-09). O filtro DayOfWeek = Monday VALIDA.")
print("Mas como sao poucas barras (~120 entre 01-03 UTC do C# falso),")
print("se BarrasDiaCorrente >= MinBarrasDiaValido(300) for FALSE, filtra.")
print()
print("MAS! As barras de SEGUNDA REAL (02-09 00:00 UTC ate 23:00 UTC) viram")
print("'TERCA' falsa no C# (02-09 03:00 ate 02-10 02:00). Total = 1380 barras")
print("normalmente. Passa filtro de barras. Mas DayOfWeek = TERCA = Tuesday.")
print()
print("Isso vai gerar shift sistematico: dia X real = X+1 falso no C#.")
print("Range do 'X+1 falso' inclui parte de X real e parte de X+1 real,")
print("misturando duas sessoes — range gigante, NUNCA NR7.")
print()
print("Algo nao bate ainda. Hipotese H2 nao explica.")
