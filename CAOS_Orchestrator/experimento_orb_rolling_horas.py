"""Experimento 5 (teste decisivo de overfit): valida se a META-REGRA
"selecionar as horas lucrativas do passado e operar só nelas no futuro"
generaliza, via re-derivação em janela móvel (walk-forward do filtro).

Motivação: no experimento 4, filtrar pelas horas positivas do treino
deu PF 1.22 no hold-out. Mas isso pode ser sorte de um único split. Aqui
testamos a regra repetidamente:

  - Janela expanding: para cada mês-alvo M (a partir do 7º mês operado),
    deriva as horas ET positivas usando TODOS os trades ANTERIORES a M,
    congela, e opera só nessas horas durante M.
  - Acumula os trades out-of-sample de todos os M.
  - Se o PnL OOS acumulado é positivo e estável por trimestre -> a regra
    generaliza (não é cherry-pick de um split).

Compara com baseline (operar TODAS as horas, sem filtro) no mesmo OOS.

Custo honesto de entrada limit: 0.87 pt/trade.
NÃO é estratégia plugável; investigação exploratória (fora de tests/).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict

from caos.walk_forward.models import CustosOperacionais
from experimento_orb_sem_limites import carregar, simular_v2, TradeExp, ET, USD_POR_PONTO

CUSTO_LIMIT_PT = 0.62 + 0.25
MIN_HIST_MESES = 6  # warmup antes de começar a operar OOS


def _mes(ts: datetime) -> str:
    e = ts.astimezone(ET)
    return f"{e.year}-{e.month:02d}"


def _quarter(ts: datetime) -> str:
    e = ts.astimezone(ET)
    return f"{e.year}-Q{(e.month-1)//3+1}"


def _resumo(nome: str, trades: List[TradeExp]):
    if not trades:
        print(f"\n=== {nome} ===\n  SEM TRADES"); return
    pnls = [t.liquido() for t in trades]
    wins = [p for p in pnls if p > 0]
    perdas = abs(sum(p for p in pnls if p < 0))
    pf = sum(wins)/perdas if perdas > 0 else float("inf")
    por_q: Dict[str, float] = defaultdict(float)
    for t in trades:
        por_q[_quarter(t.saida_ts)] += t.liquido()
    qs = sorted(por_q.items())
    npos = sum(1 for _, v in qs if v > 0)
    gate = len(qs) > 0 and npos/len(qs) >= 0.75
    print(f"\n=== {nome} ===")
    print(f"  N={len(trades)}  WR={len(wins)/len(trades):.1%}  PF={pf:.2f}  "
          f"PnL={sum(pnls):+.0f}pts (USD {sum(pnls)*USD_POR_PONTO:+,.0f})  "
          f"avg={sum(pnls)/len(trades):+.2f}")
    print(f"  Year-stability OOS: {npos}/{len(qs)} {'PASSA' if gate else 'FALHA'}")
    for q, v in qs:
        print(f"    {q}: {v:+8.1f}")


def main() -> None:
    df = carregar()
    trades = simular_v2(df, "limit", CustosOperacionais.zerados())
    for t in trades:
        t.custo_pontos = CUSTO_LIMIT_PT

    # Ordena por entrada e agrupa por mês ET.
    trades.sort(key=lambda t: t.entrada_ts)
    meses = sorted(set(_mes(t.entrada_ts) for t in trades))
    print(f"N trades total: {len(trades)} | meses operados: {len(meses)} "
          f"({meses[0]} -> {meses[-1]})")

    # Walk-forward expanding do filtro de horas.
    oos_filtrado: List[TradeExp] = []
    oos_baseline: List[TradeExp] = []
    log_horas = []
    for i, m in enumerate(meses):
        if i < MIN_HIST_MESES:
            continue
        # Histórico = trades de meses anteriores a m.
        hist = [t for t in trades if _mes(t.entrada_ts) < m]
        alvo = [t for t in trades if _mes(t.entrada_ts) == m]
        # Deriva horas positivas no histórico.
        pnl_hora: Dict[int, float] = defaultdict(float)
        for t in hist:
            pnl_hora[t.entrada_et_hora] += t.liquido()
        horas_boas: Set[int] = {h for h, v in pnl_hora.items() if v > 0}
        log_horas.append((m, sorted(horas_boas)))
        # Opera no mês-alvo só nas horas congeladas.
        oos_filtrado.extend(t for t in alvo if t.entrada_et_hora in horas_boas)
        oos_baseline.extend(alvo)

    _resumo("BASELINE OOS (todas as horas)", oos_baseline)
    _resumo("FILTRO ROLLING OOS (horas re-derivadas a cada mes)", oos_filtrado)

    # Estabilidade do conjunto de horas escolhido (overfit se muda muito).
    print("\n" + "="*70)
    print("Horas congeladas por mes (estabilidade do filtro):")
    for m, hs in log_horas:
        print(f"  {m}: {hs}")

    if oos_filtrado:
        dias = len(set(t.entrada_ts.astimezone(ET).date() for t in oos_filtrado))
        print(f"\n  trades/dia OOS filtrado: {len(oos_filtrado)/max(dias,1):.2f}")

    # Frequência de cada hora ao longo dos meses (horas robustas aparecem sempre).
    freq: Dict[int, int] = defaultdict(int)
    for _, hs in log_horas:
        for h in hs:
            freq[h] += 1
    n = len(log_horas)
    print("\n  Frequencia de selecao por hora (robustez):")
    for h in sorted(freq):
        print(f"   {h:02d}:00 selecionada em {freq[h]}/{n} meses ({freq[h]/n:.0%})")


if __name__ == "__main__":
    main()
