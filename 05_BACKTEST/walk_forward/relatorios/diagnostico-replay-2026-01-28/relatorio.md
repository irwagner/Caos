# Diagnostico do Replay NT8 — 28/01/2026 a 13/03/2026

Estrategia: `StrategyORBCrabelSpreadFilter` (Decisao 2026-05-25-02).

## Dados

- CSV fonte: `e:\CAOS\dados\MNQ\MNQ_03-26\minute\last.csv`
- Periodo: `2026-01-28` a `2026-03-13` (33 dias com dados)
- Trades observados no replay NT8: **2**

## NR7 puro sobre o periodo

Aplicando apenas o filtro Crabel NR7 (sem Spread Filter, sem
`RangeMinimoPontos`):

- Dias elegiveis: **4 de 33** (12.1%)

| Data elegivel | Range do dia (pts) |
|---|---|
| 2026-01-28 | 288.00 |
| 2026-02-11 | 407.50 |
| 2026-03-11 | 306.25 |
| 2026-03-12 | 432.75 |


## Trades observados no replay

| Data | Direcao | NR7-elegivel? | MFE (ticks) | MAE (ticks) | PnL (USD) |
|---|---|---|---|---|---|
| 2026-02-09 | SHORT | NAO | 117 | -20 | +0 |
| 2026-02-23 | LONG | NAO | 202 | -79 | +32 |


## Conclusao

- **Volume esperado vs observado:** WF previa 6.5-8 trades por janela de
  60 dias uteis (mediana). Em 33 dias, projetamos
  3.9-4.4
  trades. Observados: **2**.
- **Filtro NR7 puro** liberaria **4 dias**.
- **Trades NT8 / NR7 elegiveis** = **2 / 4** =
  50% de "execucao" entre os dias elegiveis.

Os outros **4 dias elegiveis sem trade** indicam que
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
