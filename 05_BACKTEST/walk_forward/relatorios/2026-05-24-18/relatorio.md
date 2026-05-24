---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaPreFomcDrift
id: 2026-05-24-18
identificador: 2026-05-24-18
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 1
status: concluido
tags:
- walk-forward
- estrategiaprefomcdrift
- concluido
titulo: Walk-Forward 2026-05-24-18 — EstrategiaPreFomcDrift
---

# Relatório Walk-Forward — 2026-05-24-18

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaPreFomcDrift |
| Status | concluido |
| Identificador | 2026-05-24-18 |
| Manifesto (SHA-256) | f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f |
| Instrumento | MNQ |
| Granularidade | 1m |
| Treino (dias úteis) | 120 |
| Teste (dias úteis) | 120 |
| Passo (dias úteis) | 120 |
| Seed | 42 |
| Total de janelas | 1 |
| Slippage (pts/lado) | 0.25 |
| Comissão (USD/lado/contrato) | 0.62 |

## Métricas por Janela

| Índice | Status | Trades | PnL | Sharpe | Calmar | Drawdown % | Drawdown dias | Win rate | Payoff médio | MFE médio | MAE médio | Look-ahead? | Duração (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ok | 4 | -10.4300 | -0.5828 | -0.2063 | 1.0000 | 42 | 0.5000 | 0.9018 | 193.6875 | -230.8125 | não | 10031 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -0.2063 |
| drawdown_maximo_dias | 42.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -230.8125 |
| mfe_medio | 193.6875 |
| numero_trades | 4.0000 |
| payoff_medio | 0.9018 |
| pnl_total | -10.4300 |
| sharpe_anualizado | -0.5828 |
| win_rate | 0.5000 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -0.2063 |
| drawdown_maximo_dias | 42.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -230.8125 |
| mfe_medio | 193.6875 |
| numero_trades | 4.0000 |
| payoff_medio | 0.9018 |
| pnl_total | -10.4300 |
| sharpe_anualizado | -0.5828 |
| win_rate | 0.5000 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
