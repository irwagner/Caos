---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaORBCrabel
id: 2026-05-24-22
identificador: 2026-05-24-22
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaorbcrabel
- concluido
titulo: Walk-Forward 2026-05-24-22 — EstrategiaORBCrabel
---

# Relatório Walk-Forward — 2026-05-24-22

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaORBCrabel |
| Status | concluido |
| Identificador | 2026-05-24-22 |
| Manifesto (SHA-256) | f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f |
| Instrumento | MNQ |
| Granularidade | 1m |
| Treino (dias úteis) | 60 |
| Teste (dias úteis) | 60 |
| Passo (dias úteis) | 60 |
| Seed | 42 |
| Total de janelas | 4 |
| Slippage (pts/lado) | 0.25 |
| Comissão (USD/lado/contrato) | 0.62 |

## Métricas por Janela

| Índice | Status | Trades | PnL | Sharpe | Calmar | Drawdown % | Drawdown dias | Win rate | Payoff médio | MFE médio | MAE médio | Look-ahead? | Duração (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ok | 10 | -216.6000 | -3.0778 | -2.0145 | 1.0000 | 28 | 0.5000 | 0.5710 | 87.7000 | -87.9000 | não | 4516 |
| 1 | ok | 10 | -606.8875 | -8.4551 | -4.2000 | 1.0000 | 70 | 0.2000 | 0.9831 | 68.2250 | -109.9000 | não | 6047 |
| 2 | ok | 9 | 944.7575 | 8.9299 | 14.1290 | 0.2973 | 14 | 0.7778 | 1.2469 | 207.8333 | -73.5833 | não | 4422 |
| 3 | ok | 6 | 115.7050 | 1.9348 | 1.5664 | 0.7284 | 35 | 0.5000 | 1.3730 | 187.9583 | -103.7917 | não | 4500 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -0.2240 |
| drawdown_maximo_dias | 31.5000 |
| drawdown_maximo_percentual | 0.8642 |
| mae_medio | -95.8458 |
| mfe_medio | 137.8292 |
| numero_trades | 9.5000 |
| payoff_medio | 1.1150 |
| pnl_total | -50.4475 |
| sharpe_anualizado | -0.5715 |
| win_rate | 0.5000 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 2.3702 |
| drawdown_maximo_dias | 36.7500 |
| drawdown_maximo_percentual | 0.7564 |
| mae_medio | -93.7938 |
| mfe_medio | 137.9292 |
| numero_trades | 8.7500 |
| payoff_medio | 1.0435 |
| pnl_total | 59.2438 |
| sharpe_anualizado | -0.1670 |
| win_rate | 0.4944 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
