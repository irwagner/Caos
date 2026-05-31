"""Experimento exploratório 2: replica a CONFIG DOCUMENTADA do ORB-Hydra
(a que tinha edge persistente PSR 98.9%, 8/9 janelas 3m) e testa o FIX
nunca executado — entrada LIMIT em pullback — sob custo honesto.

NÃO é estratégia plugável nem altera código ativo. Investigação preliminar
gratuita prescrita pelo Conselho (critério `criterio-triagem-nao-persistencia`).

Diferença para experimento_orb_limit.py: aquele usou o ORB-CAOS default
(OR 30min, sem filtros). Este replica a config Hydra EXATA, que é a única
com edge persistente documentado:

Config Hydra (pré-registrada na nota de ressuscitação, NÃO é tuning):
- OR: 9:30-9:45 ET (15 min)
- Trigger: 9:45-10:30 ET; close > OR_high (long) / < OR_low (short)
- Filtro OR_size in [0.3, 1.5] x ATR50_diario (Wilder)
- Filtro volume barra trigger >= 1.2 x media_20_barras
- Stop: meio do OR = (OR_high+OR_low)/2, cap 30 pts
- Target: 2.0 x OR_size desde a entrada
- Saída forçada: 15:55 ET
- 1 trade/sessão; anti-failed-first (cancela se lado oposto tocado antes)

Variável isolada: modelo de execução (market no rompimento vs limit no
pullback). Gate: year-stability por trimestre + PF + N.
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
DATA_DIR_DAY = os.path.join(os.path.dirname(__file__), "..", "dados", "MNQ", "_concat_day_last")

# Config Hydra (congelada)
OR_INI = time(9, 30)
OR_FIM = time(9, 45)
TRIG_FIM = time(10, 30)
SAIDA_FORCADA = time(15, 55)
ATR_MIN_MULT = 0.3
ATR_MAX_MULT = 1.5
VOL_MULT_MIN = 1.2
STOP_CAP_PTS = 30.0
TARGET_X_OR = 2.0


def _carregar(dir_: str) -> pd.DataFrame:
    arquivos = sorted(glob.glob(os.path.join(dir_, "*.csv")))
    frames = []
    for i, c in enumerate(arquivos):
        df = pd.read_csv(c)
        df["__ordem"] = i
        frames.append(df)
    todo = pd.concat(frames, ignore_index=True)
    todo["timestamp"] = pd.to_datetime(todo["timestamp"], utc=True)
    todo = todo.sort_values(["timestamp", "__ordem"]).drop_duplicates("timestamp", keep="last")
    return todo.sort_values("timestamp").reset_index(drop=True)


def atr50_wilder(day: pd.DataFrame) -> Dict[pd.Timestamp, float]:
    """ATR50 Wilder por data (usa True Range diário). Retorna ATR do dia
    ANTERIOR para cada data (causal: ATR conhecido antes da abertura)."""
    day = day.sort_values("timestamp").reset_index(drop=True)
    highs = day["high"].astype(float).values
    lows = day["low"].astype(float).values
    closes = day["close"].astype(float).values
    n = 50
    atr_por_data: Dict[pd.Timestamp, float] = {}
    trs = [highs[0] - lows[0]]
    for i in range(1, len(day)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        trs.append(tr)
    # Wilder seed = média simples dos primeiros n; depois suavização.
    atr = None
    for i in range(len(trs)):
        if i < n - 1:
            atr_val = None
        elif i == n - 1:
            atr = sum(trs[:n]) / n
            atr_val = atr
        else:
            atr = (atr * (n - 1) + trs[i]) / n
            atr_val = atr
        # ATR do dia i fica disponível para o dia i+1 (causal).
        if atr_val is not None and i + 1 < len(day):
            data_seguinte = day.iloc[i + 1]["timestamp"].date()
            atr_por_data[data_seguinte] = atr_val
    return atr_por_data


@dataclass
class TradeExp:
    lado: str
    entrada_ts: datetime
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


def simular(minute: pd.DataFrame, atr: Dict, modelo: str,
            custos: CustosOperacionais, usar_filtro_atr: bool = False,
            usar_filtro_vol: bool = False) -> List[TradeExp]:
    minute = minute.copy()
    minute["et"] = minute["timestamp"].dt.tz_convert(ET)
    minute["data_et"] = minute["et"].dt.date
    trades: List[TradeExp] = []

    for data_et, grupo in minute.groupby("data_et"):
        atr50 = atr.get(data_et)
        g = grupo.reset_index(drop=True)
        et_times = g["et"].dt.time

        # 1) Forma OR 9:30-9:45 ET
        mask_or = (et_times >= OR_INI) & (et_times < OR_FIM)
        bar_or = g[mask_or]
        if len(bar_or) == 0:
            continue
        or_high = float(bar_or["high"].max())
        or_low = float(bar_or["low"].min())
        or_size = or_high - or_low
        if or_size <= 0:
            continue
        # Filtro OR_size in [0.3, 1.5] x ATR50 (opcional; Hydra diz que
        # nao agrega valor — desligado por padrao).
        if usar_filtro_atr:
            if atr50 is None or atr50 <= 0:
                continue
            if not (ATR_MIN_MULT * atr50 <= or_size <= ATR_MAX_MULT * atr50):
                continue

        # 2) Janela de trigger 9:45-10:30 ET
        mask_trig = (et_times >= OR_FIM) & (et_times < TRIG_FIM)
        trig = g[mask_trig].reset_index(drop=True)
        if len(trig) == 0:
            continue

        # volume médio das 20 barras anteriores ao trigger (até 9:45)
        antes = g[et_times < OR_FIM]
        vol_avg = float(antes["volume"].tail(20).mean()) if len(antes) else 0.0

        # 3) Detecta rompimento (1 setup/sessão) + anti-failed-first
        lado = None
        idx_sinal = None
        for i, row in trig.iterrows():
            c = float(row["close"])
            vol = float(row["volume"])
            if usar_filtro_vol and vol_avg > 0 and vol < VOL_MULT_MIN * vol_avg:
                continue
            if c > or_high:
                lado, idx_sinal = "long", i
                break
            if c < or_low:
                lado, idx_sinal = "short", i
                break
        if lado is None:
            continue

        nivel = or_high if lado == "long" else or_low
        stop = (or_high + or_low) / 2.0
        # cap de stop em 30 pts a partir da entrada (aplicado após definir entrada)

        # Barras desde a barra de sinal (inclusive) até o fim do dia.
        # idx_global = posição em g da barra de trigger que disparou o sinal.
        idx_global = int(g.index[mask_trig][idx_sinal])
        resto = g.iloc[idx_global:].reset_index(drop=True)

        entrada_preco: Optional[float] = None
        entrada_ts = None
        stop_real = None
        alvo = None
        if modelo == "market":
            entrada_preco = float(trig.iloc[idx_sinal]["close"])
            entrada_ts = trig.iloc[idx_sinal]["timestamp"].to_pydatetime()
            if lado == "long":
                stop_real = max(stop, entrada_preco - STOP_CAP_PTS)
                alvo = entrada_preco + TARGET_X_OR * or_size
            else:
                stop_real = min(stop, entrada_preco + STOP_CAP_PTS)
                alvo = entrada_preco - TARGET_X_OR * or_size

        saiu = False
        for j in range(1, len(resto)):
            row = resto.iloc[j]
            t_et = row["et"].time()
            hi, lo, cl = float(row["high"]), float(row["low"]), float(row["close"])
            forcar = t_et >= SAIDA_FORCADA

            if modelo == "limit" and entrada_preco is None:
                # espera pullback ao nível (preenche limit)
                if forcar:
                    break  # cancela sem preencher
                tocou = (lado == "long" and lo <= nivel) or (lado == "short" and hi >= nivel)
                if not tocou:
                    continue
                entrada_preco = nivel
                entrada_ts = row["timestamp"].to_pydatetime()
                if lado == "long":
                    stop_real = max(stop, entrada_preco - STOP_CAP_PTS)
                    alvo = entrada_preco + TARGET_X_OR * or_size
                else:
                    stop_real = min(stop, entrada_preco + STOP_CAP_PTS)
                    alvo = entrada_preco - TARGET_X_OR * or_size
                # checa stop/alvo intrabar na própria barra de fill
                if lado == "long":
                    if lo <= stop_real:
                        _add(trades, lado, entrada_preco, entrada_ts, row, stop_real, or_size, "stop", custos)
                        saiu = True; break
                    if hi >= alvo:
                        _add(trades, lado, entrada_preco, entrada_ts, row, alvo, or_size, "alvo", custos)
                        saiu = True; break
                else:
                    if hi >= stop_real:
                        _add(trades, lado, entrada_preco, entrada_ts, row, stop_real, or_size, "stop", custos)
                        saiu = True; break
                    if lo <= alvo:
                        _add(trades, lado, entrada_preco, entrada_ts, row, alvo, or_size, "alvo", custos)
                        saiu = True; break
                continue

            if entrada_preco is None:
                continue

            # gestão de trade aberto (stop pessimista antes do alvo)
            if lado == "long":
                if lo <= stop_real:
                    _add(trades, lado, entrada_preco, entrada_ts, row, stop_real, or_size, "stop", custos)
                    saiu = True; break
                if hi >= alvo:
                    _add(trades, lado, entrada_preco, entrada_ts, row, alvo, or_size, "alvo", custos)
                    saiu = True; break
            else:
                if hi >= stop_real:
                    _add(trades, lado, entrada_preco, entrada_ts, row, stop_real, or_size, "stop", custos)
                    saiu = True; break
                if lo <= alvo:
                    _add(trades, lado, entrada_preco, entrada_ts, row, alvo, or_size, "alvo", custos)
                    saiu = True; break
            if forcar:
                _add(trades, lado, entrada_preco, entrada_ts, row, cl, or_size, "fim-sessao", custos)
                saiu = True; break

        if not saiu and entrada_preco is not None:
            ultima = resto.iloc[-1]
            _add(trades, lado, entrada_preco, entrada_ts, ultima, float(ultima["close"]), or_size, "eod", custos)

    return trades


def _add(trades, lado, entrada_preco, entrada_ts, row, saida_preco, or_size, motivo, custos):
    saida_ts = row["timestamp"].to_pydatetime()
    if saida_ts <= entrada_ts:
        saida_ts = entrada_ts + timedelta(seconds=1)
    custo = custos.custo_total_pontos(1, range_referencia=or_size)
    trades.append(TradeExp(lado, entrada_ts, saida_ts, float(entrada_preco),
                           float(saida_preco), or_size, motivo, custo))


def _quarter(ts: datetime) -> str:
    return f"{ts.year}-Q{(ts.month-1)//3+1}"


def resumo(nome: str, trades: List[TradeExp]) -> None:
    if not trades:
        print(f"\n=== {nome} ===\n  SEM TRADES")
        return
    pnls = [t.liquido() for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = sum(pnls)
    ganhos, perdas = sum(wins), abs(sum(losses))
    pf = ganhos / perdas if perdas > 0 else float("inf")
    por_q: Dict[str, float] = {}
    for t in trades:
        por_q.setdefault(_quarter(t.saida_ts), 0.0)
        por_q[_quarter(t.saida_ts)] += t.liquido()
    qs = sorted(por_q.items())
    n_pos = sum(1 for _, v in qs if v > 0)
    print(f"\n=== {nome} ===")
    print(f"  N trades        : {len(trades)}")
    print(f"  Win rate        : {len(wins)/len(trades):.1%}")
    print(f"  PnL liquido(pts): {total:+.1f}  (USD {total*USD_POR_PONTO:+,.0f})")
    print(f"  Profit Factor   : {pf:.2f}")
    print(f"  Avg trade (pts) : {total/len(trades):+.2f}")
    gate = (len(qs) > 0 and n_pos/len(qs) >= 0.75)
    print(f"  Year-stability  : {n_pos}/{len(qs)} trimestres+ {'PASSA' if gate else 'FALHA'}")
    for q, v in qs:
        print(f"    {q}: {v:+8.1f}")


def main() -> None:
    minute = _carregar(DATA_DIR)
    day = _carregar(DATA_DIR_DAY)
    atr = atr50_wilder(day)
    print(f"Barras minute: {len(minute):,} | dias com ATR50: {len(atr)}")
    print(f"Periodo: {minute.timestamp.min()} -> {minute.timestamp.max()}")

    # Núcleo Hydra SEM filtros ATR/vol (a versão de 93 trades / edge persistente)
    print("\n############ CONFIG HYDRA (sem filtro ATR/vol — versão 93 trades) ############")
    for nome, modelo, custos in [
        ("HYDRA market | SEM custo", "market", CustosOperacionais.zerados()),
        ("HYDRA market | slippage 0.5pt (orig Hydra)", "market", CustosOperacionais.topstep_mnq(0.5)),
        ("HYDRA market | slippage PROP 7.5%", "market", CustosOperacionais.topstep_mnq_proporcional()),
        ("HYDRA limit  | SEM custo", "limit", CustosOperacionais.zerados()),
        ("HYDRA limit  | custo 1 tick/lado", "limit", CustosOperacionais.topstep_mnq()),
        ("HYDRA limit  | slippage PROP 7.5%", "limit", CustosOperacionais.topstep_mnq_proporcional()),
    ]:
        trades = simular(minute, atr, modelo, custos,
                         usar_filtro_atr=False, usar_filtro_vol=False)
        resumo(nome, trades)

    # Com filtro de volume (>=1.2x media) — config "completa" da nota
    print("\n############ CONFIG HYDRA + filtro volume 1.2x ############")
    for nome, modelo, custos in [
        ("HYDRA+vol market | slippage PROP 7.5%", "market", CustosOperacionais.topstep_mnq_proporcional()),
        ("HYDRA+vol limit  | custo 1 tick/lado", "limit", CustosOperacionais.topstep_mnq()),
        ("HYDRA+vol limit  | slippage PROP 7.5%", "limit", CustosOperacionais.topstep_mnq_proporcional()),
    ]:
        trades = simular(minute, atr, modelo, custos,
                         usar_filtro_atr=False, usar_filtro_vol=True)
        resumo(nome, trades)


def simular_wrap(minute, atr, modelo, custos):
    return simular(minute, atr, modelo, custos)


if __name__ == "__main__":
    main()
