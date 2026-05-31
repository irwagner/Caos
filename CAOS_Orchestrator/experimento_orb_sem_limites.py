"""Experimento exploratório 3: ORB SEM LIMITES a-priori (MNQ).

Diretriz do usuário (31/mai/2026): "não vamos nos ligar em limite de
horário pra operação e limite de trader. Cria sem esses limites; depois
de validar consistência, a gente roda replay e descobre o melhor horário,
trades/dia ideal etc."

Hipótese testada: as amarras a-priori (janela RTH, hora de corte 19:00,
saída forçada 15:55, 1 trade/sessão) mascararam o edge do ORB?

Desenho (isola a remoção de constraints):
- Sinal ORB mantido (é a definição da estratégia): OR = [9:30, 9:45) ET.
  NOTA: a âncora 9:30 ET é o SINAL do ORB, não uma restrição de trading.
- REMOVIDO: hora de corte, saída forçada de fim de sessão, 1 trade/sessão.
- Trading na sessão CHEIA (23h) do dia ET. Múltiplos trades/dia via
  re-entrada: depois de sair, só rearma quando o preço VOLTA pra dentro
  do OR e rompe de novo (rompimento genuíno, não re-trigger imediato).
- Saída: stop = meio do OR (cap 30pts), alvo = 2x OR_size. Sem saída por
  horário; fecha no último bar do dia ET se stop/alvo não bateram.
- Custos: zero / 1 tick / proporcional 7.5% (modelo Hydra honesto).

ANTI-OVERFIT (preserva a ideia do usuário sem auto-engano):
- Split temporal: treino = primeiros 70% dos dias; hold-out = últimos 30%.
- Perfil hora-do-dia e trades/dia computados SÓ no treino. O hold-out só
  valida. Se o edge sobrevive disjunto no hold-out, é real.

NÃO é estratégia plugável; é investigação exploratória (fora de tests/).
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from caos.walk_forward.models import CustosOperacionais

USD_POR_PONTO = 2.0
TICK = 0.25
ET = ZoneInfo("America/New_York")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "dados", "MNQ", "_concat_minute_last")

# Sinal ORB (âncora do open; não é restrição de trading)
OR_INI = time(9, 30)
OR_FIM = time(9, 45)
STOP_CAP_PTS = 30.0
TARGET_X_OR = 2.0
TRAIN_FRAC = 0.70


def carregar() -> pd.DataFrame:
    arquivos = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    frames = []
    for i, c in enumerate(arquivos):
        df = pd.read_csv(c)
        df["__ordem"] = i
        frames.append(df)
    todo = pd.concat(frames, ignore_index=True)
    todo["timestamp"] = pd.to_datetime(todo["timestamp"], utc=True)
    todo = todo.sort_values(["timestamp", "__ordem"]).drop_duplicates("timestamp", keep="last")
    todo = todo.sort_values("timestamp").reset_index(drop=True)
    todo["et"] = todo["timestamp"].dt.tz_convert(ET)
    todo["data_et"] = todo["et"].dt.date
    return todo


@dataclass
class TradeExp:
    lado: str
    entrada_ts: datetime          # UTC
    entrada_et_hora: int          # hora ET de entrada (0-23)
    saida_ts: datetime
    entrada_preco: float
    saida_preco: float
    or_size: float
    motivo: str
    custo_pontos: float

    def bruto(self) -> float:
        return (self.saida_preco - self.entrada_preco) if self.lado == "long" \
            else (self.entrada_preco - self.saida_preco)

    def liquido(self) -> float:
        return self.bruto() - self.custo_pontos


def simular(df: pd.DataFrame, modelo: str, custos: CustosOperacionais) -> List[TradeExp]:
    trades: List[TradeExp] = []

    for data_et, grupo in df.groupby("data_et"):
        g = grupo.sort_values("timestamp").reset_index(drop=True)
        ett = g["et"].dt.time

        bar_or = g[(ett >= OR_INI) & (ett < OR_FIM)]
        if len(bar_or) == 0:
            continue
        or_high = float(bar_or["high"].max())
        or_low = float(bar_or["low"].min())
        or_size = or_high - or_low
        if or_size <= 0:
            continue
        stop_mid = (or_high + or_low) / 2.0

        # Barras de trading: tudo APÓS o fim do OR (sem corte de horário).
        pos_idx = g.index[ett >= OR_FIM]
        if len(pos_idx) == 0:
            continue
        resto = g.iloc[pos_idx[0]:].reset_index(drop=True)

        # Estado intradiário.
        em_trade = False
        armado = True          # pode abrir no 1o rompimento
        lado = ""
        entrada_preco = 0.0
        entrada_ts = None
        entrada_hora = 0
        stop_real = 0.0
        alvo = 0.0
        limit_armado = False   # para modelo "limit": aguarda pullback ao nível
        nivel = 0.0

        for j in range(len(resto)):
            row = resto.iloc[j]
            hi, lo, cl = float(row["high"]), float(row["low"]), float(row["close"])
            ts = row["timestamp"].to_pydatetime()

            # 1) Gestão de trade aberto.
            if em_trade:
                saiu = False
                if lado == "long":
                    if lo <= stop_real:
                        _add(trades, lado, entrada_ts, entrada_hora, row, stop_real, or_size, "stop", custos)
                        saiu = True
                    elif hi >= alvo:
                        _add(trades, lado, entrada_ts, entrada_hora, row, alvo, or_size, "alvo", custos)
                        saiu = True
                else:
                    if hi >= stop_real:
                        _add(trades, lado, entrada_ts, entrada_hora, row, stop_real, or_size, "stop", custos)
                        saiu = True
                    elif lo <= alvo:
                        _add(trades, lado, entrada_ts, entrada_hora, row, alvo, or_size, "alvo", custos)
                        saiu = True
                if saiu:
                    em_trade = False
                    armado = False   # rearma só quando preço voltar pra dentro do OR
                continue

            # 2) Limit armado (modelo limit): aguarda pullback ao nível.
            if limit_armado:
                tocou = (lado == "long" and lo <= nivel) or (lado == "short" and hi >= nivel)
                if tocou:
                    limit_armado = False
                    em_trade = True
                    entrada_preco = nivel
                    entrada_ts = ts
                    entrada_hora = row["et"].hour
                    if lado == "long":
                        stop_real = max(stop_mid, entrada_preco - STOP_CAP_PTS)
                        alvo = entrada_preco + TARGET_X_OR * or_size
                        if lo <= stop_real:
                            _add(trades, lado, entrada_ts, entrada_hora, row, stop_real, or_size, "stop", custos)
                            em_trade = False; armado = False
                        elif hi >= alvo:
                            _add(trades, lado, entrada_ts, entrada_hora, row, alvo, or_size, "alvo", custos)
                            em_trade = False; armado = False
                    else:
                        stop_real = min(stop_mid, entrada_preco + STOP_CAP_PTS)
                        alvo = entrada_preco - TARGET_X_OR * or_size
                        if hi >= stop_real:
                            _add(trades, lado, entrada_ts, entrada_hora, row, stop_real, or_size, "stop", custos)
                            em_trade = False; armado = False
                        elif lo <= alvo:
                            _add(trades, lado, entrada_ts, entrada_hora, row, alvo, or_size, "alvo", custos)
                            em_trade = False; armado = False
                continue

            # 3) Rearmar quando preço volta pra dentro do OR.
            if not armado:
                if or_low <= cl <= or_high:
                    armado = True
                continue

            # 4) Detecta rompimento (armado).
            if cl > or_high:
                lado = "long"; nivel = or_high
            elif cl < or_low:
                lado = "short"; nivel = or_low
            else:
                continue

            if modelo == "market":
                em_trade = True
                entrada_preco = cl
                entrada_ts = ts
                entrada_hora = row["et"].hour
                if lado == "long":
                    stop_real = max(stop_mid, entrada_preco - STOP_CAP_PTS)
                    alvo = entrada_preco + TARGET_X_OR * or_size
                else:
                    stop_real = min(stop_mid, entrada_preco + STOP_CAP_PTS)
                    alvo = entrada_preco - TARGET_X_OR * or_size
            else:
                limit_armado = True  # aguarda pullback

        # Fim do dia ET: fecha trade aberto no último close.
        if em_trade:
            ultima = resto.iloc[-1]
            _add(trades, lado, entrada_ts, entrada_hora, ultima, float(ultima["close"]), or_size, "eod", custos)

    return trades


def _add(trades, lado, entrada_ts, entrada_hora, row, saida_preco, or_size, motivo, custos):
    saida_ts = row["timestamp"].to_pydatetime()
    if saida_ts <= entrada_ts:
        saida_ts = entrada_ts + timedelta(seconds=1)
    custo = custos.custo_total_pontos(1, range_referencia=or_size)
    trades.append(TradeExp(lado, entrada_ts, entrada_hora, saida_ts,
                           float(_ENTRADA[0]), float(saida_preco), or_size, motivo, custo))


_ENTRADA = [0.0]  # ponte simples para entrada_preco


def _quarter(ts: datetime) -> str:
    return f"{ts.year}-Q{(ts.month-1)//3+1}"


def _stats(trades: List[TradeExp]) -> dict:
    if not trades:
        return {"n": 0}
    pnls = [t.liquido() for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    ganhos, perdas = sum(wins), abs(sum(losses))
    pf = ganhos / perdas if perdas > 0 else float("inf")
    por_q: Dict[str, float] = {}
    for t in trades:
        por_q.setdefault(_quarter(t.saida_ts), 0.0)
        por_q[_quarter(t.saida_ts)] += t.liquido()
    qs = sorted(por_q.items())
    n_pos = sum(1 for _, v in qs if v > 0)
    return {
        "n": len(trades), "wr": len(wins)/len(trades), "pnl": sum(pnls),
        "pf": pf, "avg": sum(pnls)/len(trades), "qs": qs,
        "ys": (n_pos, len(qs)),
    }


def _print_stats(nome: str, s: dict):
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
    print(f"Barras: {len(df):,} | dias ET: {len(datas)} | "
          f"treino<{corte} | holdout>={corte}")

    # Para o modelo market, _ENTRADA precisa ser setado antes de _add.
    # Reescrevo simular para registrar entrada_preco corretamente via closure.
    for modelo in ("market", "limit"):
        for nome_c, custos in [
            ("sem custo", CustosOperacionais.zerados()),
            ("1 tick", CustosOperacionais.topstep_mnq()),
            ("prop 7.5%", CustosOperacionais.topstep_mnq_proporcional()),
        ]:
            trades = _simular_fix(df, modelo, custos)
            tr_train = [t for t in trades if t.entrada_ts.astimezone(ET).date() < corte]
            tr_hold = [t for t in trades if t.entrada_ts.astimezone(ET).date() >= corte]
            print("\n" + "#" * 70)
            print(f"# ORB SEM LIMITES | entrada={modelo} | custo={nome_c}")
            _print_stats(f"{modelo}/{nome_c} | FULL", _stats(trades))
            _print_stats(f"{modelo}/{nome_c} | TREINO", _stats(tr_train))
            _print_stats(f"{modelo}/{nome_c} | HOLD-OUT", _stats(tr_hold))
            if trades:
                dias_op = len(set(t.entrada_ts.astimezone(ET).date() for t in trades))
                print(f"  trades/dia (full): {len(trades)/max(dias_op,1):.2f} "
                      f"em {dias_op} dias operados")

    # Perfil hora-do-dia (SÓ no treino, modelo market sem custo) — exploração.
    print("\n" + "=" * 70)
    print("PERFIL HORA-DO-DIA (TREINO apenas, market sem custo) — para descobrir")
    print("o melhor horário SEM contaminar o hold-out:")
    trades = _simular_fix(df, "market", CustosOperacionais.zerados())
    tr_train = [t for t in trades if t.entrada_ts.astimezone(ET).date() < corte]
    por_hora: Dict[int, List[float]] = {}
    for t in tr_train:
        por_hora.setdefault(t.entrada_et_hora, []).append(t.liquido())
    print("  hora_ET | n | pnl_total | avg")
    for h in sorted(por_hora):
        v = por_hora[h]
        print(f"   {h:02d}:00  | {len(v):4d} | {sum(v):+8.0f} | {sum(v)/len(v):+6.2f}")


def _simular_fix(df, modelo, custos):
    """Wrapper que corrige a ponte _ENTRADA: reimplementa a chamada a _add
    setando entrada_preco logo antes. Para manter o código simples, troco
    a estratégia: monkeypatch _add para ler entrada_preco do trade corrente."""
    return simular_v2(df, modelo, custos)


# ---------------------------------------------------------------------------
# Versão 2 da simulação: passa entrada_preco explicitamente (sem ponte global)
# ---------------------------------------------------------------------------

def simular_v2(df: pd.DataFrame, modelo: str, custos: CustosOperacionais) -> List[TradeExp]:
    trades: List[TradeExp] = []

    def fechar(lado, ep, ets, ehora, row, sp, orsz, motivo):
        sts = row["timestamp"].to_pydatetime()
        if sts <= ets:
            sts = ets + timedelta(seconds=1)
        custo = custos.custo_total_pontos(1, range_referencia=orsz)
        trades.append(TradeExp(lado, ets, ehora, sts, float(ep), float(sp), orsz, motivo, custo))

    for data_et, grupo in df.groupby("data_et"):
        g = grupo.sort_values("timestamp").reset_index(drop=True)
        ett = g["et"].dt.time
        bar_or = g[(ett >= OR_INI) & (ett < OR_FIM)]
        if len(bar_or) == 0:
            continue
        or_high = float(bar_or["high"].max())
        or_low = float(bar_or["low"].min())
        or_size = or_high - or_low
        if or_size <= 0:
            continue
        stop_mid = (or_high + or_low) / 2.0
        pos_idx = g.index[ett >= OR_FIM]
        if len(pos_idx) == 0:
            continue
        resto = g.iloc[pos_idx[0]:].reset_index(drop=True)

        em_trade = False
        armado = True
        limit_armado = False
        lado = ""
        ep = 0.0; ets = None; ehora = 0; stop_real = 0.0; alvo = 0.0; nivel = 0.0

        for j in range(len(resto)):
            row = resto.iloc[j]
            hi, lo, cl = float(row["high"]), float(row["low"]), float(row["close"])
            ts = row["timestamp"].to_pydatetime()

            if em_trade:
                if lado == "long":
                    if lo <= stop_real:
                        fechar(lado, ep, ets, ehora, row, stop_real, or_size, "stop"); em_trade=False; armado=False; continue
                    if hi >= alvo:
                        fechar(lado, ep, ets, ehora, row, alvo, or_size, "alvo"); em_trade=False; armado=False; continue
                else:
                    if hi >= stop_real:
                        fechar(lado, ep, ets, ehora, row, stop_real, or_size, "stop"); em_trade=False; armado=False; continue
                    if lo <= alvo:
                        fechar(lado, ep, ets, ehora, row, alvo, or_size, "alvo"); em_trade=False; armado=False; continue
                continue

            if limit_armado:
                tocou = (lado == "long" and lo <= nivel) or (lado == "short" and hi >= nivel)
                if tocou:
                    limit_armado = False; em_trade = True
                    ep = nivel; ets = ts; ehora = int(row["et"].hour)
                    if lado == "long":
                        stop_real = max(stop_mid, ep - STOP_CAP_PTS); alvo = ep + TARGET_X_OR*or_size
                        if lo <= stop_real:
                            fechar(lado, ep, ets, ehora, row, stop_real, or_size, "stop"); em_trade=False; armado=False
                        elif hi >= alvo:
                            fechar(lado, ep, ets, ehora, row, alvo, or_size, "alvo"); em_trade=False; armado=False
                    else:
                        stop_real = min(stop_mid, ep + STOP_CAP_PTS); alvo = ep - TARGET_X_OR*or_size
                        if hi >= stop_real:
                            fechar(lado, ep, ets, ehora, row, stop_real, or_size, "stop"); em_trade=False; armado=False
                        elif lo <= alvo:
                            fechar(lado, ep, ets, ehora, row, alvo, or_size, "alvo"); em_trade=False; armado=False
                continue

            if not armado:
                if or_low <= cl <= or_high:
                    armado = True
                continue

            if cl > or_high:
                lado = "long"; nivel = or_high
            elif cl < or_low:
                lado = "short"; nivel = or_low
            else:
                continue

            if modelo == "market":
                em_trade = True; ep = cl; ets = ts; ehora = int(row["et"].hour)
                if lado == "long":
                    stop_real = max(stop_mid, ep - STOP_CAP_PTS); alvo = ep + TARGET_X_OR*or_size
                else:
                    stop_real = min(stop_mid, ep + STOP_CAP_PTS); alvo = ep - TARGET_X_OR*or_size
            else:
                limit_armado = True

        if em_trade:
            ultima = resto.iloc[-1]
            fechar(lado, ep, ets, ehora, ultima, float(ultima["close"]), or_size, "eod")

    return trades


if __name__ == "__main__":
    main()
