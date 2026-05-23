---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T00:00:00Z'
estrategia: EstrategiaPreFomcDrift
id: 2026-05-23-04
identificador: 2026-05-23-04
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaprefomcdrift
- concluido
titulo: Walk-Forward 2026-05-23-04 — EstrategiaPreFomcDrift
---

# Relatório Walk-Forward — 2026-05-23-04

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaPreFomcDrift |
| Status | concluido |
| Identificador | 2026-05-23-04 |
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
| 0 | ok | 2 | 219.0100 | 12.6884 | — | 0.0000 | 0 | 1.0000 | — | 229.2500 | -94.6250 | não | 3703 |
| 1 | ok | 2 | 19.0100 | 2.3007 | 2.1655 | 1.0000 | 0 | 0.5000 | 1.5156 | 161.1250 | -259.5000 | não | 3704 |
| 2 | ok | 2 | 223.2600 | 125.3044 | — | 0.0000 | 0 | 1.0000 | — | 226.2500 | -202.1250 | não | 3609 |
| 3 | ok | 2 | -449.2400 | -13.3229 | -4.2000 | 1.0000 | 42 | 0.0000 | 0.0000 | 253.0000 | -323.5000 | não | 3734 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -1.0172 |
| drawdown_maximo_dias | 0.0000 |
| drawdown_maximo_percentual | 0.5000 |
| mae_medio | -230.8125 |
| mfe_medio | 227.7500 |
| numero_trades | 2.0000 |
| payoff_medio | 0.7578 |
| pnl_total | 119.0100 |
| sharpe_anualizado | 7.4945 |
| win_rate | 0.7500 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -1.0172 |
| drawdown_maximo_dias | 10.5000 |
| drawdown_maximo_percentual | 0.5000 |
| mae_medio | -219.9375 |
| mfe_medio | 217.4062 |
| numero_trades | 2.0000 |
| payoff_medio | 0.7578 |
| pnl_total | 3.0100 |
| sharpe_anualizado | 31.7426 |
| win_rate | 0.6250 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
