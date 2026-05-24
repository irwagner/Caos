---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaOvernightDrift
id: 2026-05-24-16
identificador: 2026-05-24-16
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaovernightdrift
- concluido
titulo: Walk-Forward 2026-05-24-16 — EstrategiaOvernightDrift
---

# Relatório Walk-Forward — 2026-05-24-16

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaOvernightDrift |
| Status | concluido |
| Identificador | 2026-05-24-16 |
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
| 0 | ok | 50 | -1108.1125 | -2.8138 | -4.2000 | 1.0000 | 82 | 0.4600 | 0.7297 | 85.1450 | -98.4700 | não | 4141 |
| 1 | ok | 52 | -336.7025 | -0.5740 | -0.7458 | 1.0000 | 23 | 0.5385 | 0.7739 | 133.4087 | -122.0673 | não | 4156 |
| 2 | ok | 49 | -638.1300 | -1.5657 | -2.2371 | 1.0000 | 47 | 0.3878 | 1.2082 | 113.0408 | -121.6531 | não | 4109 |
| 3 | ok | 48 | 240.0400 | 0.3143 | 0.4904 | 1.0000 | 48 | 0.5833 | 0.7560 | 190.0052 | -142.6615 | não | 4110 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -1.4914 |
| drawdown_maximo_dias | 47.5000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -121.8602 |
| mfe_medio | 123.2247 |
| numero_trades | 49.5000 |
| payoff_medio | 0.7649 |
| pnl_total | -487.4162 |
| sharpe_anualizado | -1.0699 |
| win_rate | 0.4992 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -1.6731 |
| drawdown_maximo_dias | 50.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -121.2130 |
| mfe_medio | 130.3999 |
| numero_trades | 49.7500 |
| payoff_medio | 0.8670 |
| pnl_total | -460.7262 |
| sharpe_anualizado | -1.1598 |
| win_rate | 0.4924 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
