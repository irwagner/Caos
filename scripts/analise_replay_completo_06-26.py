"""Analise consolidada dos trades do replay completo (contratos 03-26 + 06-26)."""

from pathlib import Path
import pandas as pd

DIR = Path(r"e:\CAOS\05_BACKTEST\mfe_mae")

# Trades dos 2 contratos rodados em playback
trades = []
for csv in sorted(DIR.glob("*StrategyORBCrabelSpreadFilter.csv")):
    df = pd.read_csv(csv)
    # Pega so primeira linha (cada arquivo eh 1 trade, replicado).
    if len(df) > 0:
        trades.append(df.iloc[0].to_dict())

df_trades = pd.DataFrame(trades).drop_duplicates(subset=["id_trade", "entrada_timestamp"])
df_trades = df_trades.sort_values("entrada_timestamp").reset_index(drop=True)
df_trades["entrada_timestamp"] = pd.to_datetime(df_trades["entrada_timestamp"])
df_trades["saida_timestamp"] = pd.to_datetime(df_trades["saida_timestamp"])

# Re-numera id_trade sequencialmente para clareza
df_trades["id"] = range(1, len(df_trades) + 1)

print("=" * 90)
print(f"TRADES CONSOLIDADOS — {len(df_trades)} entradas")
print("=" * 90)
print()
print(df_trades[["id", "entrada_timestamp", "saida_timestamp", "direcao",
                "mfe_ticks", "mae_ticks", "pnl_usd"]].to_string(index=False))
print()

# Metricas
n = len(df_trades)
pnl_total = df_trades["pnl_usd"].sum()
wins = df_trades[df_trades["pnl_usd"] > 0]
losses = df_trades[df_trades["pnl_usd"] < 0]
breakeven = df_trades[df_trades["pnl_usd"] == 0]
win_rate = len(wins) / n
mfe_med = df_trades["mfe_ticks"].median()
mae_med = df_trades["mae_ticks"].median()
mfe_mean = df_trades["mfe_ticks"].mean()
mae_mean = df_trades["mae_ticks"].mean()

# Razao MFE/MAE (em valor absoluto)
razao_mfe_mae = abs(mfe_mean / mae_mean) if mae_mean != 0 else float("inf")

print("=" * 90)
print("METRICAS CONSOLIDADAS")
print("=" * 90)
print(f"  Trades total:           {n}")
print(f"  PnL total:              USD {pnl_total:+.2f}")
print(f"  PnL medio/trade:        USD {pnl_total / n:+.2f}")
print(f"  Wins:                   {len(wins)} ({win_rate:.1%})")
print(f"  Losses:                 {len(losses)}")
print(f"  Breakeven (PnL ~0):     {len(breakeven)}")
print(f"  Maior win:              USD {df_trades['pnl_usd'].max():+.2f}")
print(f"  Maior loss:             USD {df_trades['pnl_usd'].min():+.2f}")
print()
print(f"  MFE mediana:            {mfe_med:.0f} ticks ({mfe_med * 0.25:.2f} pts)")
print(f"  MAE mediana:            {mae_med:.0f} ticks ({mae_med * 0.25:.2f} pts)")
print(f"  MFE media:              {mfe_mean:.0f} ticks")
print(f"  MAE media:              {mae_mean:.0f} ticks")
print(f"  Razao |MFE/MAE| media:  {razao_mfe_mae:.2f}")
print()

# Direcao breakdown
print("Por direcao:")
for direcao, grupo in df_trades.groupby("direcao"):
    g_pnl = grupo["pnl_usd"].sum()
    g_wins = (grupo["pnl_usd"] > 0).sum()
    print(f"  {direcao}: {len(grupo)} trades, {g_wins} wins, PnL USD {g_pnl:+.2f}")
print()

# Distribuicao de outcomes
print("Distribuicao de outcomes (em USD):")
print(df_trades["pnl_usd"].describe().round(2).to_string())
print()

# Periodo
inicio = df_trades["entrada_timestamp"].min()
fim = df_trades["entrada_timestamp"].max()
dias_calendario = (fim - inicio).days
print(f"Periodo: {inicio.date()} a {fim.date()} ({dias_calendario} dias calendario)")

# Projecao anualizada simples
if dias_calendario > 0:
    pnl_dia = pnl_total / dias_calendario
    proj_anual = pnl_dia * 365
    print(f"PnL/dia calendario:      USD {pnl_dia:+.2f}")
    print(f"Projecao anualizada:     USD {proj_anual:+.2f}/ano (1 contrato)")
print()

# Comparacao com WF longo
print("=" * 90)
print("COMPARACAO COM WF LONGO (validacao 2026-05-27)")
print("=" * 90)
print("  WF previa: Sharpe mediana +9.07, PnL anualizado USD +1100/ano")
print(f"  Replay realizado: PnL USD {pnl_total:+.2f} em {dias_calendario}d, projecao USD {proj_anual:+.2f}/ano")
print()
print(f"  Trades por janela WF (60d teste): WF mediana 1.0")
print(f"  Trades no replay: {n} em {dias_calendario}d = {n / max(dias_calendario, 1) * 60:.1f} trades/janela_WF")
