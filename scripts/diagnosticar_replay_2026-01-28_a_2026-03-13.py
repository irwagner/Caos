"""Diagnostico do Replay NT8 28/01/2026 a 13/03/2026.

Compara o que o Walk-Forward Python esperaria com o que o
StrategyORBCrabelSpreadFilter no NT8 produziu (2 trades:
2026-02-09 SHORT e 2026-02-23 LONG).

Pergunta-chave: com NR7 puro sobre o CSV real do contrato MNQ 03-26,
quantos dias do periodo deveriam ser elegiveis para abrir ORB?
A divergencia (real -> esperado) aponta se o problema e:
  - falta de NR7 no periodo (regime de baixa volatilidade)
  - SF cortando trades validos
  - dataset NT8 != CSV do WF

Gera um relatorio markdown em
05_BACKTEST/walk_forward/relatorios/diagnostico-replay-2026-01-28/.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# Importa logica canonica do projeto
sys.path.insert(0, str(Path(r"e:\CAOS\CAOS_Orchestrator").resolve()))

from caos.walk_forward.estrategias.orb_crabel import (
    _calcular_range_diario,
    _dias_apos_nr,
)


PERIODO_INICIO = date(2026, 1, 28)
PERIODO_FIM = date(2026, 3, 13)
CSV_FONTE = Path(r"e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv")
TRADES_OBSERVADOS_NT8 = [
    {"data": date(2026, 2, 9), "direcao": "SHORT", "mfe": 117, "mae": -20, "pnl_usd": 0},
    {"data": date(2026, 2, 23), "direcao": "LONG", "mfe": 202, "mae": -79, "pnl_usd": 32},
]
RAIZ_RELATORIO = Path(r"e:\CAOS\05_BACKTEST\walk_forward\relatorios")
DIRETORIO_SAIDA = RAIZ_RELATORIO / "diagnostico-replay-2026-01-28"


def carregar_csv_periodo(caminho: Path, inicio: date, fim: date) -> pd.DataFrame:
    """Carrega CSV, filtra periodo e remove sabado/domingo.

    DESCOBERTA 2026-05-25: o CSV bruto inclui barras parciais de
    sabado (~61 barras) e domingo (~1 barra) por causa da abertura
    da sessao Globex. Esses pseudo-dias geram "NR7 fantasma" no
    Python WF que NAO acontecem no NT8 (que so olha pregoes regulares).
    Filtro `dow < 5` alinha o diagnostico ao comportamento do NT8.
    """
    df = pd.read_csv(caminho, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["dia"] = df["timestamp"].dt.date
    # Filtra fins de semana
    df["dow"] = df["timestamp"].dt.dayofweek  # 0=Monday, 6=Sunday
    df = df[df["dow"] < 5].copy()
    df = df.drop(columns=["dow"])
    # Pega 14 dias antes do inicio para warmup do NR7
    inicio_buffer = pd.Timestamp(inicio) - pd.Timedelta(days=14)
    fim_buffer = pd.Timestamp(fim) + pd.Timedelta(days=1)
    mask = (df["timestamp"] >= inicio_buffer.tz_localize("UTC")) & (df["timestamp"] < fim_buffer.tz_localize("UTC"))
    df = df.loc[mask].copy()
    return df.sort_values("timestamp").reset_index(drop=True)


def main() -> int:
    if not CSV_FONTE.is_file():
        print(f"ERRO: CSV nao encontrado em {CSV_FONTE}", file=sys.stderr)
        return 1

    print(f"Carregando {CSV_FONTE}...")
    df = carregar_csv_periodo(CSV_FONTE, PERIODO_INICIO, PERIODO_FIM)
    print(f"  {len(df)} barras de minuto, {df['dia'].nunique()} dias")
    print(f"  primeiro timestamp: {df['timestamp'].min()}")
    print(f"  ultimo timestamp:   {df['timestamp'].max()}")

    # --- 1. Calcula NR7 sobre o periodo ---
    ranges_por_dia = _calcular_range_diario(df)
    elegiveis_nr7, _ = _dias_apos_nr(ranges_por_dia, janela=7)

    dias_ordenados = sorted(ranges_por_dia.keys())
    dias_no_periodo = [d for d in dias_ordenados if PERIODO_INICIO <= d <= PERIODO_FIM]
    elegiveis_no_periodo = sorted(d for d in elegiveis_nr7 if PERIODO_INICIO <= d <= PERIODO_FIM)

    print()
    print("=" * 70)
    print(f"NR7 ELEGIVEIS no periodo {PERIODO_INICIO} a {PERIODO_FIM}")
    print("=" * 70)
    print(f"  total dias com dados:  {len(dias_no_periodo)}")
    print(f"  dias elegiveis (NR7):  {len(elegiveis_no_periodo)}")
    print()
    print(f"  taxa de elegibilidade: {len(elegiveis_no_periodo) / max(len(dias_no_periodo), 1) * 100:.1f}%")
    print()
    print("Dias elegiveis (apos NR7):")
    for d in elegiveis_no_periodo:
        ranges_recentes = [
            (dia_ant, ranges_por_dia[dia_ant])
            for dia_ant in dias_ordenados
            if dia_ant < d
        ][-7:]
        nr_dia = min(ranges_recentes, key=lambda x: x[1])
        print(f"  - {d}  range_dia={ranges_por_dia[d]:.2f}  apos_NR7={nr_dia[0]} (range={nr_dia[1]:.2f})")

    # --- 2. Cruzar com trades observados do NT8 ---
    print()
    print("=" * 70)
    print("TRADES OBSERVADOS (replay NT8)")
    print("=" * 70)
    elegiveis_set = set(elegiveis_no_periodo)
    for trade in TRADES_OBSERVADOS_NT8:
        elegivel = trade["data"] in elegiveis_set
        marca = "OK" if elegivel else "INCONSISTENTE"
        print(f"  {trade['data']}  {trade['direcao']:5}  PnL=USD{trade['pnl_usd']:+}   "
              f"NR7_eligivel={elegivel}  [{marca}]")

    # --- 3. Sumario ---
    print()
    print("=" * 70)
    print("SUMARIO")
    print("=" * 70)
    elegiveis_sem_trade = sorted(d for d in elegiveis_no_periodo
                                  if d not in {t["data"] for t in TRADES_OBSERVADOS_NT8})
    print(f"  trades observados:               {len(TRADES_OBSERVADOS_NT8)}")
    print(f"  dias elegiveis pelo NR7 puro:    {len(elegiveis_no_periodo)}")
    print(f"  diferenca (filtros + range_min): {len(elegiveis_sem_trade)} dias elegiveis SEM trade")
    print()
    if elegiveis_sem_trade:
        print(f"  Dias elegiveis pelo NR7 mas SEM trade no replay (provavel filtro SF ou "
              f"range_minimo_pontos > range_or):")
        for d in elegiveis_sem_trade:
            print(f"    - {d}")

    # --- 4. Gravar relatorio markdown ---
    DIRETORIO_SAIDA.mkdir(parents=True, exist_ok=True)
    relatorio_md = DIRETORIO_SAIDA / "relatorio.md"
    with relatorio_md.open("w", encoding="utf-8") as f:
        f.write(f"""# Diagnostico do Replay NT8 — 28/01/2026 a 13/03/2026

Estrategia: `StrategyORBCrabelSpreadFilter` (Decisao 2026-05-25-02).

## Dados

- CSV fonte: `{CSV_FONTE}`
- Periodo: `{PERIODO_INICIO}` a `{PERIODO_FIM}` ({len(dias_no_periodo)} dias com dados)
- Trades observados no replay NT8: **{len(TRADES_OBSERVADOS_NT8)}**

## NR7 puro sobre o periodo

Aplicando apenas o filtro Crabel NR7 (sem Spread Filter, sem
`RangeMinimoPontos`):

- Dias elegiveis: **{len(elegiveis_no_periodo)} de {len(dias_no_periodo)}** ({len(elegiveis_no_periodo) / max(len(dias_no_periodo), 1) * 100:.1f}%)

| Data elegivel | Range do dia (pts) |
|---|---|
""")
        for d in elegiveis_no_periodo:
            f.write(f"| {d} | {ranges_por_dia[d]:.2f} |\n")
        f.write(f"""

## Trades observados no replay

| Data | Direcao | NR7-elegivel? | MFE (ticks) | MAE (ticks) | PnL (USD) |
|---|---|---|---|---|---|
""")
        for trade in TRADES_OBSERVADOS_NT8:
            elegivel = trade["data"] in elegiveis_set
            f.write(f"| {trade['data']} | {trade['direcao']} | {'SIM' if elegivel else 'NAO'} | "
                    f"{trade['mfe']} | {trade['mae']} | {trade['pnl_usd']:+} |\n")

        f.write(f"""

## Conclusao

- **Volume esperado vs observado:** WF previa 6.5-8 trades por janela de
  60 dias uteis (mediana). Em {len(dias_no_periodo)} dias, projetamos
  {len(dias_no_periodo) * 7 / 60:.1f}-{len(dias_no_periodo) * 8 / 60:.1f}
  trades. Observados: **{len(TRADES_OBSERVADOS_NT8)}**.
- **Filtro NR7 puro** liberaria **{len(elegiveis_no_periodo)} dias**.
- **Trades NT8 / NR7 elegiveis** = **{len(TRADES_OBSERVADOS_NT8)} / {len(elegiveis_no_periodo)}** =
  {len(TRADES_OBSERVADOS_NT8) / max(len(elegiveis_no_periodo), 1) * 100:.0f}% de "execucao" entre os dias elegiveis.

Os outros **{len(elegiveis_sem_trade)} dias elegiveis sem trade** indicam que
um dos filtros downstream cortou o sinal: SpreadFilter (mediana_diaria
em warmup ou spread alto), `RangeMinimoPontos > range_or`, ou
`HoraCorteEntradasUtc` antes do breakout.

## Proximos passos sugeridos

1. Adicionar logging de rejeicoes no `Strategy_CAOS` C# (motivo:
   `nao_elegivel_nr7`, `range_or_pequeno`, `fora_sessao`,
   `cooldown_ativo`, `spread_alto`, `cb_disparado`).
2. Re-rodar replay no mesmo periodo. Comparar logs.
3. Se `spread_alto` for o motivo dominante, validar se o
   `spread_minuto.csv` esta correto para o contrato 03-26 no periodo.

---

Gerado por: `scripts/diagnosticar_replay_2026-01-28_a_2026-03-13.py`.
""")
    print()
    print(f"Relatorio gravado: {relatorio_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
