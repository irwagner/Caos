"""Compara agregados de multiplos WFs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    ids = [
        "2026-05-22-01",  # ORB sem friccao, sem holdout
        "2026-05-23-02",  # ORB friccao fixa Topstep
        "2026-05-23-06",  # ORB friccao proporcional
        "2026-05-23-09",  # ORB Crabel NR7 friccao proporcional (fix)
        "2026-05-23-10",  # ORB Crabel NR4 friccao proporcional (fix)
    ]
    print(f"{'id':>14} | {'estrategia':>22} | {'janelas':>4} | {'PnL_med':>9} | {'Sharpe_med':>10} | {'WR_med':>6}")
    print("-" * 95)
    for ident in ids:
        arq = (
            ROOT_REPO
            / "05_BACKTEST"
            / "walk_forward"
            / "relatorios"
            / ident
            / "resultado.json"
        )
        if not arq.is_file():
            print(f"  {ident}: ARQUIVO AUSENTE")
            continue
        p = json.loads(arq.read_text(encoding="utf-8"))
        ag = p.get("agregado_mediana", {})
        n = len(p.get("janelas", []))
        sharpe = ag.get("sharpe_anualizado")
        pnl = ag.get("pnl_total")
        wr = ag.get("win_rate")
        sharpe_s = f"{sharpe:>+10.4f}" if sharpe is not None else "       n/a"
        pnl_s = f"{pnl:>+9.2f}" if pnl is not None else "      n/a"
        wr_s = f"{wr:>6.2%}" if wr is not None else "   n/a"
        print(
            f"{ident:>14} | {p['estrategia']:>22} | {n:>7} | {pnl_s} | {sharpe_s} | {wr_s}"
        )

    # PnL total agregado (soma das janelas) — metrica importante quando
    # janelas tem muito poucos trades cada (caso Pre-FOMC).
    print()
    print("PnL acumulado total (soma de todas as janelas):")
    for ident in ids:
        arq = (
            ROOT_REPO
            / "05_BACKTEST"
            / "walk_forward"
            / "relatorios"
            / ident
            / "resultado.json"
        )
        if not arq.is_file():
            continue
        p = json.loads(arq.read_text(encoding="utf-8"))
        soma_pnl = sum(j.get("pnl_total", 0.0) or 0.0 for j in p["janelas"])
        soma_trades = sum(j.get("numero_trades", 0) for j in p["janelas"])
        print(
            f"  {ident:>14} ({p['estrategia']:>22}): "
            f"{soma_trades:>4} trades, PnL acumulado {soma_pnl:>+8.2f} pts (= USD {soma_pnl * 2:>+9.2f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
