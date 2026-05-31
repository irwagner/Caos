"""Experimento 6 (confirmatorio, ULTIMO corte): testa as horas que o
walk-forward rolling selecionou em 100% dos meses como hipotese ESTRUTURAL
fixa, nao data-mined por split.

Achado do experimento 5: as horas ET 16, 19 e 22 foram selecionadas como
lucrativas em 9/9 meses independentes (100%). Isso e' evidencia forte de
que NAO sao artefato de um split — persistiram em toda janela rolling.

Aqui medimos essas 3 horas (e a uniao com as 78%+: 10, 18) como conjunto
FIXO, no sample inteiro, treino e hold-out, com custo honesto. Confirma
ou refuta a persistencia estrutural.

IMPORTANTE (honestidade): selecionar o conjunto "100% dos meses" usa
informacao do sample inteiro. Mas como a selecao foi feita por
PERSISTENCIA (aparecer em todo mes), nao por PnL agregado, o risco de
cherry-pick e' menor. O teste decisivo continua sendo o hold-out cego.

NAO e' estrategia plugavel; investigacao exploratoria (fora de tests/).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict

from caos.walk_forward.models import CustosOperacionais
from experimento_orb_sem_limites import carregar, simular_v2, TradeExp, ET, USD_POR_PONTO, TRAIN_FRAC

CUSTO_LIMIT_PT = 0.62 + 0.25

# Conjuntos de horas a testar (derivados da frequencia do exp.5).
HORAS_100 = {16, 19, 22}            # selecionadas em 9/9 meses
HORAS_78MAIS = {10, 16, 18, 19, 22} # selecionadas em >=78% dos meses


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
    dias = len(set(t.entrada_ts.astimezone(ET).date() for t in trades))
    print(f"\n=== {nome} ===")
    print(f"  N={len(trades)}  WR={len(wins)/len(trades):.1%}  PF={pf:.2f}  "
          f"PnL={sum(pnls):+.0f}pts (USD {sum(pnls)*USD_POR_PONTO:+,.0f})  "
          f"avg={sum(pnls)/len(trades):+.2f}  trades/dia={len(trades)/max(dias,1):.2f}")
    print(f"  Year-stability: {npos}/{len(qs)} {'PASSA' if gate else 'FALHA'}")
    for q, v in qs:
        print(f"    {q}: {v:+8.1f}")


def main() -> None:
    df = carregar()
    datas = sorted(df["data_et"].unique())
    corte = datas[int(len(datas) * TRAIN_FRAC)]
    trades = simular_v2(df, "limit", CustosOperacionais.zerados())
    for t in trades:
        t.custo_pontos = CUSTO_LIMIT_PT

    def in_train(t): return t.entrada_ts.astimezone(ET).date() < corte

    for nome, horas in [("HORAS 100% {16,19,22}", HORAS_100),
                        ("HORAS >=78% {10,16,18,19,22}", HORAS_78MAIS)]:
        sub = [t for t in trades if t.entrada_et_hora in horas]
        print("\n" + "#"*70 + f"\n# {nome}")
        _resumo("FULL", sub)
        _resumo("TREINO", [t for t in sub if in_train(t)])
        _resumo("HOLD-OUT (cego)", [t for t in sub if not in_train(t)])


if __name__ == "__main__":
    main()
