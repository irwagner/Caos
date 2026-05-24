---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaTurnOfMonth
id: 2026-05-24-15
identificador: 2026-05-24-15
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaturnofmonth
- concluido
titulo: Walk-Forward 2026-05-24-15 — EstrategiaTurnOfMonth
---

# Relatório Walk-Forward — 2026-05-24-15

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaTurnOfMonth |
| Status | concluido |
| Identificador | 2026-05-24-15 |
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
| 0 | ok | 3 | -356.9600 | -3.0808 | -1.7652 | 1.0000 | 59 | 0.3333 | 1.1594 | 464.9167 | -378.0833 | não | 4484 |
| 1 | ok | 2 | 111.8600 | 9.5922 | 49.3500 | 0.0784 | 31 | 0.5000 | 12.7500 | 423.6250 | -314.3750 | não | 4438 |
| 2 | ok | 2 | -61.7275 | -0.6394 | -0.4527 | 1.0000 | 62 | 0.5000 | 0.8922 | 620.0000 | -626.6250 | não | 4219 |
| 3 | ok | 3 | -107.8725 | -1.5017 | -0.9578 | 1.0000 | 30 | 0.6667 | 0.3860 | 482.5833 | -769.6667 | não | 4156 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -0.7052 |
| drawdown_maximo_dias | 45.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -502.3542 |
| mfe_medio | 473.7500 |
| numero_trades | 2.5000 |
| payoff_medio | 1.0258 |
| pnl_total | -84.8000 |
| sharpe_anualizado | -1.0705 |
| win_rate | 0.5000 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 11.5436 |
| drawdown_maximo_dias | 45.5000 |
| drawdown_maximo_percentual | 0.7696 |
| mae_medio | -522.1875 |
| mfe_medio | 497.7812 |
| numero_trades | 2.5000 |
| payoff_medio | 3.7969 |
| pnl_total | -103.6750 |
| sharpe_anualizado | 1.0926 |
| win_rate | 0.5000 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
