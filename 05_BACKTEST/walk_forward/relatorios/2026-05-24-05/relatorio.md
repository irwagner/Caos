---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaNoiseArea
id: 2026-05-24-05
identificador: 2026-05-24-05
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategianoisearea
- concluido
titulo: Walk-Forward 2026-05-24-05 — EstrategiaNoiseArea
---

# Relatório Walk-Forward — 2026-05-24-05

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaNoiseArea |
| Status | concluido |
| Identificador | 2026-05-24-05 |
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
| 0 | ok | 60 | -264.8125 | -5.1767 | -4.2000 | 1.0000 | 81 | 0.3500 | 0.1962 | 6.2333 | -12.4458 | não | 4953 |
| 1 | ok | 60 | -121.5500 | -2.7051 | -3.7228 | 1.0000 | 45 | 0.4500 | 0.5951 | 12.4292 | -15.5542 | não | 5422 |
| 2 | ok | 58 | -171.7225 | -4.1934 | -3.8674 | 1.0000 | 64 | 0.4828 | 0.3151 | 8.2586 | -12.7198 | não | 5047 |
| 3 | ok | 59 | -188.7425 | -1.8642 | -2.8652 | 1.0000 | 51 | 0.5424 | 0.4348 | 14.6780 | -19.6907 | não | 5031 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -3.7951 |
| drawdown_maximo_dias | 57.5000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -14.1370 |
| mfe_medio | 10.3439 |
| numero_trades | 59.5000 |
| payoff_medio | 0.3750 |
| pnl_total | -180.2325 |
| sharpe_anualizado | -3.4493 |
| win_rate | 0.4664 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -3.6638 |
| drawdown_maximo_dias | 60.2500 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -15.1026 |
| mfe_medio | 10.3998 |
| numero_trades | 59.2500 |
| payoff_medio | 0.3853 |
| pnl_total | -186.7069 |
| sharpe_anualizado | -3.4848 |
| win_rate | 0.4563 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
