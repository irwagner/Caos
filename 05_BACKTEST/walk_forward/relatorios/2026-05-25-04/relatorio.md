---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-25T00:00:00Z'
estrategia: EstrategiaPreFomcDrift
id: 2026-05-25-04
identificador: 2026-05-25-04
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaprefomcdrift
- concluido
titulo: Walk-Forward 2026-05-25-04 — EstrategiaPreFomcDrift
---

# Relatório Walk-Forward — 2026-05-25-04

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaPreFomcDrift |
| Status | concluido |
| Identificador | 2026-05-25-04 |
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
| 0 | ok | 2 | 122.8475 | 7.2192 | 15.1385 | 0.2774 | 0 | 0.5000 | 4.6044 | 229.2500 | -94.6250 | não | 3953 |
| 1 | ok | 2 | -106.1775 | -13.5340 | -4.2000 | 1.0000 | 42 | 0.0000 | 0.0000 | 161.1250 | -259.5000 | não | 3906 |
| 2 | ok | 2 | 95.7475 | 23.3327 | — | 0.0000 | 0 | 1.0000 | — | 226.2500 | -202.1250 | não | 3844 |
| 3 | ok | 2 | -621.1900 | -17.4506 | -4.2000 | 1.0000 | 42 | 0.0000 | 0.0000 | 253.0000 | -323.5000 | não | 3953 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -4.2000 |
| drawdown_maximo_dias | 21.0000 |
| drawdown_maximo_percentual | 0.6387 |
| mae_medio | -230.8125 |
| mfe_medio | 227.7500 |
| numero_trades | 2.0000 |
| payoff_medio | 0.0000 |
| pnl_total | -5.2150 |
| sharpe_anualizado | -3.1574 |
| win_rate | 0.2500 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 2.2462 |
| drawdown_maximo_dias | 21.0000 |
| drawdown_maximo_percentual | 0.5694 |
| mae_medio | -219.9375 |
| mfe_medio | 217.4062 |
| numero_trades | 2.0000 |
| payoff_medio | 1.5348 |
| pnl_total | -127.1931 |
| sharpe_anualizado | -0.1082 |
| win_rate | 0.3750 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
