"""Experimento exploratório: ORB com entrada LIMIT (pullback) vs entrada
no fechamento do rompimento (market).

NÃO é estratégia plugável nem altera código ativo. É a investigação
preliminar gratuita prescrita pelo Conselho ANTES de comprometer um Spec
(critério de triagem `criterio-triagem-nao-persistencia`).

Contexto
--------
- O ORB do Hydra (referência) tinha edge REAL e PERSISTENTE (PSR 98.9%,
  8/9 janelas rolling 3m positivas, 3/3 janelas 6m) mas MORREU por
  slippage: a entrada via *market order* no rompimento paga ~7.5%-15.8%
  do or_size de slippage no gap.
- A Decisão CAOS `2026-05-24-01` confirmou em dados próprios: o ORB com
  entrada no close + slippage proporcional realista = -USD 13.719/13m.
- O FIX nunca executado (nota de ressuscitação do Hydra, caminho #1/#2):
  entrar via LIMIT no nível de rompimento, preenchendo SOMENTE quando o
  preço RETORNA ao nível (pullback). Captura o move sem pagar o gap.

Desenho do experimento (isola UMA variável: o modelo de execução)
-----------------------------------------------------------------
- Sinal: idêntico ao ORB canônico (`decidir_acao` de orb_logica.py).
  Parâmetros default congelados — SEM tuning, SEM novos parâmetros.
- Modelo A (reproduz a morte): entra no `close` da barra de rompimento.
  Slippage proporcional (7.5% do or_size) — modelo Hydra v1.
- Modelo B (o fix): arma LIMIT no nível de rompimento (high_or p/ long,
  low_or p/ short). Preenche só se uma barra POSTERIOR (causal) recuar e
  tocar o nível. Cancela se não preencher até a hora de corte / fim de
  sessão. Sem slippage de gap (limit); custo conservador de 1 tick.
- Gate decisivo: year-stability por trimestre (>=3/4 positivos). Foi o
  critério que pegou a VVG e que o ORB-Hydra passava. Também PF e N.

Saída: tabela comparativa + PnL por trimestre, impressa no stdout.
"""

from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

import pandas as pd

from caos.walk_forward.estrategias.orb_logica import (
    Barra,
    EstadoORB,
    ParametrosORB,
    decidir_acao,
)
from caos.walk_forward.models import CustosOperacionais

USD_POR_PONTO = 2.0  # MNQ
TICK = 0.25
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "dados", "MNQ", "_concat_minute_last")


# ---------------------------------------------------------------------------
# Carga de dados
# ---------------------------------------------------------------------------

def carregar_minuto() -> pd.DataFrame:
    """Concatena os 5 contratos em série contínua, dedup por timestamp."""
    arquivos = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    if not arquivos:
        raise SystemExit(f"Nenhum CSV em {DATA_DIR}")
    frames = []
    for i, caminho in enumerate(arquivos):
        df = pd.read_csv(caminho)
        df["__ordem"] = i  # contrato mais recente vence no overlap do roll
        frames.append(df)
    todo = pd.concat(frames, ignore_index=True)
    todo["timestamp"] = pd.to_datetime(todo["timestamp"], utc=True)
    # Mantém o contrato de maior ordem (mais recente) em timestamps duplicados.
    todo = todo.sort_values(["timestamp", "__ordem"])
    todo = todo.drop_duplicates(subset="timestamp", keep="last")
    todo = todo.sort_values("timestamp").reset_index(drop=True)
    return todo[["timestamp", "open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------------------
# Trade resultante do experimento
# ---------------------------------------------------------------------------

@dataclass
class TradeExp:
    lado: str  # "long" | "short"
    entrada_ts: datetime
    saida_ts: datetime
    entrada_preco: float
    saida_preco: float
    or_size: float
    motivo_saida: str
    custo_pontos: float

    def pnl_bruto_pontos(self) -> float:
        if self.lado == "long":
            return self.saida_preco - self.entrada_preco
        return self.entrada_preco - self.saida_preco

    def pnl_liquido_pontos(self) -> float:
        return self.pnl_bruto_pontos() - self.custo_pontos


# ---------------------------------------------------------------------------
# Simulador de execução (isola entrada market vs limit)
# ---------------------------------------------------------------------------

def _barra_de_row(row) -> Barra:
    return Barra(
        timestamp=row.timestamp.to_pydatetime(),
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=float(row.volume),
    )


def simular(
    df: pd.DataFrame,
    params: ParametrosORB,
    modelo: str,            # "market" | "limit"
    custos: CustosOperacionais,
) -> List[TradeExp]:
    estado = EstadoORB()
    trades: List[TradeExp] = []

    sessao_atual: Optional[datetime] = None
    sinal_usado = False           # 1 setup por sessão
    # Trade aberto (ou limit armado):
    aberto = False
    limit_armado = False
    lado = ""
    nivel = 0.0                   # nível de rompimento (high_or/low_or)
    or_size = 0.0
    entrada_preco = 0.0
    entrada_ts: Optional[datetime] = None
    stop = 0.0
    alvo = 0.0

    rows = list(df.itertuples(index=False))

    for row in rows:
        barra = _barra_de_row(row)
        d = decidir_acao(barra, estado, params)
        dia = barra.timestamp.date()

        # Reset de sessão (alinha com o reset interno de decidir_acao).
        if sessao_atual != dia:
            # Se virou o dia com trade aberto sem fechar (não deveria, mas
            # defensivo), fecha no último preço conhecido — ignorado aqui
            # porque o fim-de-sessão abaixo já força a saída.
            sessao_atual = dia
            sinal_usado = False
            aberto = False
            limit_armado = False

        sessao_fim_dt = datetime.combine(dia, params.sessao_fim_utc, tzinfo=timezone.utc)
        fim_sessao = barra.timestamp >= sessao_fim_dt - timedelta(minutes=1)

        # 1) Gerencia trade ABERTO (saída por stop/alvo/fim-de-sessão).
        if aberto:
            saiu = False
            if lado == "long":
                bateu_stop = barra.low <= stop
                bateu_alvo = barra.high >= alvo
                if bateu_stop:  # pessimista: stop antes do alvo na mesma barra
                    _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                            stop, or_size, "stop", custos)
                    saiu = True
                elif bateu_alvo:
                    _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                            alvo, or_size, "alvo", custos)
                    saiu = True
            else:  # short
                bateu_stop = barra.high >= stop
                bateu_alvo = barra.low <= alvo
                if bateu_stop:
                    _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                            stop, or_size, "stop", custos)
                    saiu = True
                elif bateu_alvo:
                    _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                            alvo, or_size, "alvo", custos)
                    saiu = True
            if not saiu and fim_sessao:
                _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                        barra.close, or_size, "fim-sessao", custos)
                saiu = True
            if saiu:
                aberto = False
            continue

        # 2) Gerencia LIMIT armado (espera pullback ao nível).
        if limit_armado:
            if fim_sessao:
                limit_armado = False  # cancela sem preencher
                continue
            preencheu = False
            if lado == "long" and barra.low <= nivel:
                entrada_preco = nivel
                preencheu = True
            elif lado == "short" and barra.high >= nivel:
                entrada_preco = nivel
                preencheu = True
            if preencheu:
                limit_armado = False
                entrada_ts = barra.timestamp
                r = or_size * params.risco_multiplicador
                if lado == "long":
                    stop = nivel - or_size      # = low_or
                    alvo = entrada_preco + r * params.alvo_multiplicador
                    # checa stop/alvo intrabar na própria barra de fill
                    if barra.low <= stop:
                        _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                                stop, or_size, "stop", custos)
                        continue
                    if barra.high >= alvo:
                        _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                                alvo, or_size, "alvo", custos)
                        continue
                else:
                    stop = nivel + or_size      # = high_or
                    alvo = entrada_preco - r * params.alvo_multiplicador
                    if barra.high >= stop:
                        _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                                stop, or_size, "stop", custos)
                        continue
                    if barra.low <= alvo:
                        _fechar(trades, lado, entrada_ts, barra.timestamp, entrada_preco,
                                alvo, or_size, "alvo", custos)
                        continue
                aberto = True
            continue

        # 3) Detecta sinal (rompimento) — 1 por sessão.
        if not sinal_usado and d.acao in ("LONG", "SHORT"):
            sinal_usado = True
            lado = "long" if d.acao == "LONG" else "short"
            or_size = estado.high_or - estado.low_or
            if lado == "long":
                nivel = estado.high_or
            else:
                nivel = estado.low_or

            if modelo == "market":
                # Entra no close do rompimento (comportamento atual do ORB).
                entrada_preco = barra.close
                entrada_ts = barra.timestamp
                r = or_size * params.risco_multiplicador
                if lado == "long":
                    stop = estado.low_or
                    alvo = entrada_preco + r * params.alvo_multiplicador
                else:
                    stop = estado.high_or
                    alvo = entrada_preco - r * params.alvo_multiplicador
                aberto = True
            else:  # limit
                # Arma limit no nível; preenche em pullback (barra futura).
                limit_armado = True
            continue

    return trades


def _fechar(trades, lado, entrada_ts, saida_ts, entrada_preco, saida_preco,
            or_size, motivo, custos: CustosOperacionais) -> None:
    if saida_ts <= entrada_ts:
        saida_ts = entrada_ts + timedelta(seconds=1)
    custo = custos.custo_total_pontos(1, range_referencia=or_size)
    trades.append(TradeExp(
        lado=lado, entrada_ts=entrada_ts, saida_ts=saida_ts,
        entrada_preco=entrada_preco, saida_preco=saida_preco,
        or_size=or_size, motivo_saida=motivo, custo_pontos=custo,
    ))


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def _quarter(ts: datetime) -> str:
    return f"{ts.year}-Q{(ts.month - 1)//3 + 1}"


def resumo(nome: str, trades: List[TradeExp]) -> None:
    if not trades:
        print(f"\n=== {nome} ===\n  SEM TRADES")
        return
    pnls = [t.pnl_liquido_pontos() for t in trades]
    brutos = [t.pnl_bruto_pontos() for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pts = sum(pnls)
    total_bruto = sum(brutos)
    ganhos = sum(wins)
    perdas = abs(sum(losses))
    pf = (ganhos / perdas) if perdas > 0 else float("inf")
    wr = len(wins) / len(trades)

    # Year-stability por trimestre (gate).
    por_q: dict = {}
    for t in trades:
        q = _quarter(t.saida_ts)
        por_q.setdefault(q, 0.0)
        por_q[q] += t.pnl_liquido_pontos()
    qs = sorted(por_q.items())
    n_pos = sum(1 for _, v in qs if v > 0)

    print(f"\n=== {nome} ===")
    print(f"  N trades         : {len(trades)}")
    print(f"  Win rate         : {wr:.1%}")
    print(f"  PnL bruto (pts)  : {total_bruto:+.1f}")
    print(f"  PnL liquido(pts) : {total_pts:+.1f}  (USD {total_pts*USD_POR_PONTO:+,.0f})")
    print(f"  Profit Factor    : {pf:.2f}")
    print(f"  Avg trade (pts)  : {total_pts/len(trades):+.2f}")
    print(f"  Year-stability   : {n_pos}/{len(qs)} trimestres positivos"
          f" {'PASSA(>=3/4 equiv)' if (len(qs)>0 and n_pos/len(qs) >= 0.75) else 'FALHA'}")
    print(f"  PnL por trimestre (liquido, pts):")
    for q, v in qs:
        print(f"    {q}: {v:+8.1f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    df = carregar_minuto()
    print(f"Barras: {len(df):,}  | periodo: {df.timestamp.min()} -> {df.timestamp.max()}")

    params = ParametrosORB()  # defaults congelados, SEM tuning

    custo_prop = CustosOperacionais.topstep_mnq_proporcional()   # 7.5% or_size
    custo_fixo = CustosOperacionais.topstep_mnq()                # 1 tick/lado
    custo_zero = CustosOperacionais.zerados()

    # Modelo A — entrada market no close do rompimento.
    a_zero = simular(df, params, "market", custo_zero)
    a_prop = simular(df, params, "market", custo_prop)

    # Modelo B — entrada LIMIT no pullback ao nível.
    b_zero = simular(df, params, "limit", custo_zero)
    b_fixo = simular(df, params, "limit", custo_fixo)
    b_prop = simular(df, params, "limit", custo_prop)

    resumo("A.market  | SEM custo (edge bruto)", a_zero)
    resumo("A.market  | slippage PROPORCIONAL 7.5% (reproduz a morte)", a_prop)
    resumo("B.limit   | SEM custo (edge bruto do pullback)", b_zero)
    resumo("B.limit   | custo FIXO 1 tick/lado (limit realista)", b_fixo)
    resumo("B.limit   | slippage PROPORCIONAL 7.5% (teste pessimista)", b_prop)


if __name__ == "__main__":
    main()
