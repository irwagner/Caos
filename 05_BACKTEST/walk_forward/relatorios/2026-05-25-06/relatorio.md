---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-25T00:00:00Z'
estrategia: EstrategiaOFI
id: 2026-05-25-06
identificador: 2026-05-25-06
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaofi
- concluido
titulo: Walk-Forward 2026-05-25-06 — EstrategiaOFI
---

# Relatório Walk-Forward — 2026-05-25-06

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaOFI |
| Status | concluido |
| Identificador | 2026-05-25-06 |
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
| 0 | ok | 6058 | -22846.3475 | -39.9871 | -4.1943 | 1.0000 | 74 | 0.3155 | 0.7391 | 9.6058 | -9.6323 | não | 4297 |
| 1 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 4312 |
| 2 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 4047 |
| 3 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 4203 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -4.1943 |
| drawdown_maximo_dias | 74.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -9.6323 |
| mfe_medio | 9.6058 |
| numero_trades | 0.0000 |
| payoff_medio | 0.7391 |
| pnl_total | 0.0000 |
| sharpe_anualizado | -39.9871 |
| win_rate | 0.3155 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -4.1943 |
| drawdown_maximo_dias | 74.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -9.6323 |
| mfe_medio | 9.6058 |
| numero_trades | 1514.5000 |
| payoff_medio | 0.7391 |
| pnl_total | -5711.5869 |
| sharpe_anualizado | -39.9871 |
| win_rate | 0.3155 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
