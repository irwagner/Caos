---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaSpreadFilter
id: 2026-05-24-21
identificador: 2026-05-24-21
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaspreadfilter
- concluido
titulo: Walk-Forward 2026-05-24-21 — EstrategiaSpreadFilter
---

# Relatório Walk-Forward — 2026-05-24-21

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaSpreadFilter |
| Status | concluido |
| Identificador | 2026-05-24-21 |
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
| 0 | ok | 8 | 256.5400 | 2.6355 | 3.4568 | 0.6725 | 21 | 0.5000 | 1.7087 | 163.8750 | -87.3750 | não | 11079 |
| 1 | ok | 8 | -1876.6475 | -7.7863 | -4.2000 | 1.0000 | 70 | 0.1250 | 0.0970 | 54.7500 | -247.2812 | não | 10734 |
| 2 | ok | 7 | 1137.4475 | 6.1803 | 14.1275 | 0.2973 | 42 | 0.5714 | 2.8102 | 344.0000 | -80.9643 | não | 10375 |
| 3 | ok | 5 | 281.1625 | 4.1085 | 4.5378 | 0.4807 | 35 | 0.4000 | 3.1206 | 251.0500 | -126.6000 | não | 10515 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | 3.9973 |
| drawdown_maximo_dias | 38.5000 |
| drawdown_maximo_percentual | 0.5766 |
| mae_medio | -106.9875 |
| mfe_medio | 207.4625 |
| numero_trades | 7.5000 |
| payoff_medio | 2.2594 |
| pnl_total | 268.8513 |
| sharpe_anualizado | 3.3720 |
| win_rate | 0.4500 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 4.4805 |
| drawdown_maximo_dias | 42.0000 |
| drawdown_maximo_percentual | 0.6126 |
| mae_medio | -135.5551 |
| mfe_medio | 203.4187 |
| numero_trades | 7.0000 |
| payoff_medio | 1.9341 |
| pnl_total | -50.3744 |
| sharpe_anualizado | 1.2845 |
| win_rate | 0.3991 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
