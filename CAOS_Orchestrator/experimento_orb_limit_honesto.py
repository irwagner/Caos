"""Experimento 4: ORB sem limites, entrada LIMIT, CUSTO HONESTO + filtro de
horário derivado SÓ do treino e validado no hold-out cego.

Por que um custo diferente: o slippage proporcional 7.5% do or_size foi
medido pelo Hydra em ordens MARKET/STOP no rompimento. Entrada LIMIT NÃO
paga esse gap — preenche no nível ou não preenche. O custo honesto da
versão limit é:
  - comissão: 0.62 USD/contrato/lado = 0.31 pt/lado = 0.62 pt round-trip
  - saída: o stop é market (~1 tick = 0.25 pt); o alvo é limit (0 slip).
    Conservador: assume 1 tick de slip na saída sempre.
  => custo_honesto ≈ 0.62 (comissão) + 0.25 (1 tick saída) = 0.87 pt/trade.

Metodologia anti-overfit (segue a diretriz do usuário SEM auto-engano):
  1. Roda ORB sem limites, entrada limit, custo honesto.
  2. Deriva o conjunto de HORAS ET lucrativas usando SÓ o treino (70%).
  3. CONGELA esse conjunto.
  4. Aplica ao hold-out (30% final, nunca visto). Se o edge sobrevive
     disjunto -> persistência real.
  5. Reporta tambem cap de trades/dia (sensibilidade), derivado no treino.

NÃO é estratégia plugável; investigação exploratória (fora de tests/).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

# Reusa a simulação sem-limites já validada (entrada limit/market + re-entrada).
from experimento_orb_sem_limites import (
    carregar, simular_v2, TradeExp, ET, USD_POR_PONTO, TRAIN_FRAC,
)

# Custo honesto para entrada LIMIT (pontos por trade round-trip).
CUSTO_LIMIT_PT = 0.62 + 0.25  # comissão round-trip + 1 tick saída


def _aplicar_custo_honesto(trades: List[TradeExp]) -> None:
    """Sobrescreve custo_pontos com o modelo honesto de entrada limit."""
    for t in trades:
        t.custo_pontos = CUSTO_LIMIT_PT


def _quarter(ts: datetime) -> str:
    return f"{ts.year}-Q{(ts.month-1)//3+1}"


def _stats(trades: List[TradeExp]) -> dict:
    if not trades:
        return {"n": 0}
    pnls = [t.liquido() for t in trades]
    wins = [p for p in pnls if p > 0]
    perdas = abs(sum(p for p in pnls if p < 0))
    ganhos = sum(wins)
    pf = ganhos / perdas if perdas > 0 else float("inf")
    por_q: Dict[str, float] = {}
    for t in trades:
        por_q.setdefault(_quarter(t.saida_ts), 0.0)
        por_q[_quarter(t.saida_ts)] += t.liquido()
    qs = sorted(por_q.items())
    n_pos = sum(1 for _, v in qs if v > 0)
    return {"n": len(trades), "wr": len(wins)/len(trades), "pnl": sum(pnls),
            "pf": pf, "avg": sum(pnls)/len(trades), "qs": qs, "ys": (n_pos, len(qs))}


def _print(nome: str, s: dict):
    if s.get("n", 0) == 0:
        print(f"\n=== {nome} ===\n  SEM TRADES"); return
    npos, nq = s["ys"]
    gate = nq > 0 and npos/nq >= 0.75
    print(f"\n=== {nome} ===")
    print(f"  N={s['n']}  WR={s['wr']:.1%}  PF={s['pf']:.2f}  "
          f"PnL={s['pnl']:+.0f}pts (USD {s['pnl']*USD_POR_PONTO:+,.0f})  avg={s['avg']:+.2f}")
    print(f"  Year-stability: {npos}/{nq} {'PASSA' if gate else 'FALHA'}")
    for q, v in s["qs"]:
        print(f"    {q}: {v:+8.1f}")


def main() -> None:
    df = carregar()
    datas = sorted(df["data_et"].unique())
    corte = datas[int(len(datas) * TRAIN_FRAC)]
    print(f"dias ET: {len(datas)} | treino<{corte} | holdout>={corte}")
    print(f"Custo honesto limit: {CUSTO_LIMIT_PT:.2f} pt/trade "
          f"(USD {CUSTO_LIMIT_PT*USD_POR_PONTO:.2f})")

    trades = simular_v2(df, "limit", __import__("caos.walk_forward.models",
                        fromlist=["CustosOperacionais"]).CustosOperacionais.zerados())
    _aplicar_custo_honesto(trades)  # aplica custo honesto pós-simulação

    def in_train(t): return t.entrada_ts.astimezone(ET).date() < corte
    tr_train = [t for t in trades if in_train(t)]
    tr_hold = [t for t in trades if not in_train(t)]

    print("\n" + "#"*70 + "\n# BASELINE: limit + custo honesto, SEM filtro de horario")
    _print("FULL", _stats(trades))
    _print("TREINO", _stats(tr_train))
    _print("HOLD-OUT", _stats(tr_hold))

    # ---- Deriva horas lucrativas SÓ no treino ----
    por_hora_train: Dict[int, List[float]] = {}
    for t in tr_train:
        por_hora_train.setdefault(t.entrada_et_hora, []).append(t.liquido())
    horas_boas = sorted(h for h, v in por_hora_train.items() if sum(v) > 0)
    print("\n" + "="*70)
    print("PERFIL HORA-DO-DIA (TREINO, custo honesto):")
    print("  hora_ET | n | pnl_total | avg | inclui?")
    for h in sorted(por_hora_train):
        v = por_hora_train[h]
        inc = "SIM" if h in horas_boas else "nao"
        print(f"   {h:02d}:00 | {len(v):4d} | {sum(v):+8.0f} | {sum(v)/len(v):+6.2f} | {inc}")
    print(f"\nHoras CONGELADAS (positivas no treino): {horas_boas}")

    # ---- Aplica filtro congelado ao hold-out ----
    tr_train_f = [t for t in tr_train if t.entrada_et_hora in horas_boas]
    tr_hold_f = [t for t in tr_hold if t.entrada_et_hora in horas_boas]
    print("\n" + "#"*70)
    print("# COM FILTRO DE HORARIO (congelado no treino) aplicado:")
    _print("TREINO filtrado", _stats(tr_train_f))
    _print("HOLD-OUT filtrado (VEREDITO)", _stats(tr_hold_f))

    if tr_hold_f:
        dias = len(set(t.entrada_ts.astimezone(ET).date() for t in tr_hold_f))
        print(f"\n  trades/dia no hold-out filtrado: {len(tr_hold_f)/max(dias,1):.2f}")


if __name__ == "__main__":
    main()
