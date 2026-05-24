---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T00:00:00Z'
estrategia: EstrategiaPreFomcDrift
id: 2026-05-23-05
identificador: 2026-05-23-05
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaprefomcdrift
- concluido
titulo: Walk-Forward 2026-05-23-05 — EstrategiaPreFomcDrift
---

# Relatório Walk-Forward — 2026-05-23-05

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaPreFomcDrift |
| Status | concluido |
| Identificador | 2026-05-23-05 |
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
| 0 | ok | 2 | 186.8225 | 12.7337 | — | 0.0000 | 0 | 1.0000 | — | 229.2500 | -94.6250 | não | 3859 |
| 1 | ok | 2 | 6.0975 | 0.7642 | 0.6137 | 1.0000 | 0 | 0.5000 | 1.1461 | 161.1250 | -259.5000 | não | 3844 |
| 2 | ok | 2 | 190.4350 | 125.7428 | — | 0.0000 | 0 | 1.0000 | — | 226.2500 | -202.1250 | não | 3813 |
| 3 | ok | 2 | -515.2900 | -13.2884 | -4.2000 | 1.0000 | 42 | 0.0000 | 0.0000 | 253.0000 | -323.5000 | não | 3875 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -1.7932 |
| drawdown_maximo_dias | 0.0000 |
| drawdown_maximo_percentual | 0.5000 |
| mae_medio | -230.8125 |
| mfe_medio | 227.7500 |
| numero_trades | 2.0000 |
| payoff_medio | 0.5731 |
| pnl_total | 96.4600 |
| sharpe_anualizado | 6.7489 |
| win_rate | 0.7500 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -1.7932 |
| drawdown_maximo_dias | 10.5000 |
| drawdown_maximo_percentual | 0.5000 |
| mae_medio | -219.9375 |
| mfe_medio | 217.4062 |
| numero_trades | 2.0000 |
| payoff_medio | 0.5731 |
| pnl_total | -32.9838 |
| sharpe_anualizado | 31.4881 |
| win_rate | 0.6250 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
