"""Investigacao do achado de autocorrelacao condicional.

A analise de 2026-05-23 encontrou rho(1) = -0.046 nos minutos de
dias com range < P25 (N=6358). Esta e' direcao nova candidata a
familia estrategica.

Investigamos:

1. Estabilidade do achado: rho(1) calculado em 5 sub-amostras
   sequenciais (cada contrato separado). Se o sinal e' real, deve
   aparecer em > 50% dos sub-grupos.
2. Distribuicao de retornos condicionais: dado que a barra anterior
   subiu (cresceu), qual e' a distribuicao do retorno da barra
   atual? Se rho < 0, a media condicional deve ser negativa (e
   vice-versa).
3. Edge bruto por trade hipotetico: simulacao simples de "compra
   se barra anterior caiu, vende se subiu" em dias selecionados.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_REPO / "CAOS_Orchestrator"))

from caos.walk_forward.data_reader import SkillDataReader

CUSTO_TOPSTEP_PTS = 1.12  # round-trip


def carregar_minute() -> pd.DataFrame:
    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="investigar-mr",
    )
    return reader.carregar(
        ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last"
    )


def _classificar_dias_baixa_vol(df: pd.DataFrame, percentil: float = 0.25) -> set:
    df = df.copy()
    df["dia"] = df["timestamp"].dt.date
    por_dia = df.groupby("dia").agg(
        high_max=("high", "max"),
        low_min=("low", "min"),
    )
    por_dia["range"] = por_dia["high_max"] - por_dia["low_min"]
    limiar = por_dia["range"].quantile(percentil)
    return set(por_dia.loc[por_dia["range"] < limiar].index), float(limiar)


# ---------------------------------------------------------------------------
# 1. Estabilidade: rho por sub-amostra
# ---------------------------------------------------------------------------


def estabilidade_por_contrato() -> None:
    print("=" * 70)
    print("1. ESTABILIDADE — rho(1) por contrato (5 sub-amostras)")
    print("=" * 70)
    df = carregar_minute()
    df = df.copy()
    df["dia"] = df["timestamp"].dt.date
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df = df.dropna(subset=["log_ret"])

    # Particiona o DataFrame em 5 sub-amostras cronologicas iguais.
    n = len(df)
    tamanhos = [n // 5] * 5
    tamanhos[-1] = n - sum(tamanhos[:-1])

    inicio = 0
    print()
    print(f"{'Sub-amostra':>12} | {'N total':>8} | {'rho_geral':>10} | {'N baixa-vol':>11} | {'rho_baixa':>10}")
    print("-" * 65)
    rhos_geral = []
    rhos_baixa = []
    for i, t in enumerate(tamanhos, start=1):
        sub = df.iloc[inicio : inicio + t]
        inicio += t
        # rho geral
        y = sub["log_ret"].to_numpy()
        rho_g = float(np.corrcoef(y[1:], y[:-1])[0, 1]) if len(y) > 100 else float("nan")
        # rho baixa vol
        dias_bv, _ = _classificar_dias_baixa_vol(sub)
        sub_bv = sub.loc[sub["dia"].isin(dias_bv), "log_ret"].to_numpy()
        rho_bv = float("nan")
        if len(sub_bv) > 100:
            std0 = np.std(sub_bv[1:])
            std1 = np.std(sub_bv[:-1])
            if std0 > 0 and std1 > 0:
                rho_bv = float(np.corrcoef(sub_bv[1:], sub_bv[:-1])[0, 1])
        print(
            f"{i:>12} | {len(sub):>8,} | {rho_g:>+.4f} | {len(sub_bv):>11,} | {rho_bv:>+.4f}"
        )
        rhos_geral.append(rho_g)
        rhos_baixa.append(rho_bv)
    print()
    val_baixa = [r for r in rhos_baixa if not np.isnan(r)]
    if val_baixa:
        print(f"  Media de rho baixa-vol entre sub-amostras: {np.mean(val_baixa):+.4f}")
        negativos = sum(1 for r in val_baixa if r < -0.02)
        print(f"  Sub-amostras com rho < -0.02: {negativos}/{len(val_baixa)}")
        if negativos >= 3:
            print("  => SINAL ROBUSTO entre contratos (>= 3/5).")
        else:
            print("  => SINAL FRACO entre contratos. Pode ser artefato de 1-2 contratos.")
    print()


# ---------------------------------------------------------------------------
# 2. Distribuicao condicional
# ---------------------------------------------------------------------------


def distribuicao_condicional() -> None:
    print("=" * 70)
    print("2. DISTRIBUICAO CONDICIONAL — log-retorno dado barra anterior")
    print("=" * 70)
    df = carregar_minute()
    df = df.copy()
    df["dia"] = df["timestamp"].dt.date
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["log_ret_lag1"] = df["log_ret"].shift(1)
    df = df.dropna(subset=["log_ret", "log_ret_lag1"])

    # So dias de baixa vol.
    dias_bv, limiar = _classificar_dias_baixa_vol(df)
    sub = df.loc[df["dia"].isin(dias_bv)].copy()

    print(f"  Limiar baixa-vol: range < {limiar:.2f} pts")
    print(f"  N barras em dias de baixa vol: {len(sub):,}")
    print()

    # Bucket pelo sinal da barra anterior.
    sub_pos = sub.loc[sub["log_ret_lag1"] > 0, "log_ret"]
    sub_neg = sub.loc[sub["log_ret_lag1"] < 0, "log_ret"]
    sub_zero = sub.loc[sub["log_ret_lag1"] == 0, "log_ret"]

    def _stats(s: pd.Series, nome: str) -> None:
        if len(s) == 0:
            print(f"  {nome:>20}: N=0 (sem amostras)")
            return
        media = float(np.mean(s))
        std = float(np.std(s, ddof=1))
        # Em pontos (close * log_ret).
        # Para preco medio ~24500: 1 unit log_ret ~24500 pts.
        # media * 24500 = pts esperados por barra.
        media_pts_aprox = media * 24500
        t = media / (std / np.sqrt(len(s))) if std > 0 else float("nan")
        print(
            f"  {nome:>20}: N={len(s):>7,} | media_log={media:+.6f} "
            f"(~{media_pts_aprox:+.3f} pts) | t={t:+.2f}"
        )

    _stats(sub_pos, "barra anterior +")
    _stats(sub_neg, "barra anterior -")
    _stats(sub_zero, "barra anterior 0")
    print()
    print("  Interpretacao: se rho < 0 e' real, barra anterior + deve ter")
    print("  media negativa do retorno atual (e vice-versa). |t| > 2 indica")
    print("  rejeicao formal de H0: media = 0.")
    print()


# ---------------------------------------------------------------------------
# 3. Edge bruto por trade hipotetico
# ---------------------------------------------------------------------------


def edge_hipotetico() -> None:
    print("=" * 70)
    print("3. EDGE BRUTO POR TRADE HIPOTETICO")
    print("=" * 70)
    df = carregar_minute()
    df = df.copy()
    df["dia"] = df["timestamp"].dt.date
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["pts_ret"] = df["close"] - df["close"].shift(1)
    df = df.dropna()
    df["log_ret_lag1"] = df["log_ret"].shift(1)
    df = df.dropna()

    dias_bv, _ = _classificar_dias_baixa_vol(df)
    sub = df.loc[df["dia"].isin(dias_bv)].copy()

    # Estrategia hipotetica: na barra t, se barra t-1 subiu, vende
    # (curto); se caiu, compra (longo). PnL bruto = -pts_ret(t) se
    # short ou +pts_ret(t) se long; mas como o sinal vem da barra
    # anterior, o PnL e' simetrico: -sign(log_ret_lag1) * pts_ret.
    sub["sinal"] = -np.sign(sub["log_ret_lag1"])
    sub["pnl_bruto"] = sub["sinal"] * sub["pts_ret"]
    pnl = sub["pnl_bruto"].to_numpy()
    pnl_nao_zero = pnl[sub["sinal"].to_numpy() != 0]

    n = len(pnl_nao_zero)
    soma = float(np.sum(pnl_nao_zero))
    media = float(np.mean(pnl_nao_zero))
    std = float(np.std(pnl_nao_zero, ddof=1))
    t = media / (std / np.sqrt(n)) if std > 0 else float("nan")
    win = float(np.mean(pnl_nao_zero > 0))

    print(f"  N trades hipoteticos: {n:,}")
    print(f"  Soma PnL bruto:  {soma:+.2f} pts")
    print(f"  Media por trade: {media:+.4f} pts (custo: {CUSTO_TOPSTEP_PTS} pts)")
    print(f"  Std por trade:   {std:.4f} pts")
    print(f"  Sharpe-like:     {t:+.3f}")
    print(f"  Win rate:        {win:.2%}")
    print()
    edge_liquido = media - CUSTO_TOPSTEP_PTS
    print(f"  Edge liquido por trade: {edge_liquido:+.4f} pts")
    if edge_liquido > 0:
        print("  => RENTAVEL apos custo Topstep (mas validar!)")
    else:
        print("  => NAO RENTAVEL apos custo Topstep.")
    print()
    print("  Atencao: simulacao IDEAL — opera CADA barra de cada dia de")
    print("  baixa vol. Realisticamente teria slippage por sinais")
    print("  consecutivos (compra-vende-compra), retencao de 1min.")
    print("  Numero serve para AVALIAR ORDEM DE GRANDEZA do edge bruto.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    estabilidade_por_contrato()
    distribuicao_condicional()
    edge_hipotetico()
    return 0


if __name__ == "__main__":
    sys.exit(main())
