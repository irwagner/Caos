---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaSpreadFilter
id: 2026-05-24-20
identificador: 2026-05-24-20
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaspreadfilter
- concluido
titulo: Walk-Forward 2026-05-24-20 — EstrategiaSpreadFilter
---

# Relatório Walk-Forward — 2026-05-24-20

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaSpreadFilter |
| Status | concluido |
| Identificador | 2026-05-24-20 |
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
| 0 | ok | 60 | -224.5500 | -4.2719 | -4.0093 | 1.0000 | 81 | 0.4500 | 0.2586 | 6.9833 | -12.0750 | não | 11578 |
| 1 | ok | 60 | 44.1625 | 1.2859 | 2.4302 | 1.0000 | 39 | 0.5167 | 1.1990 | 9.6042 | -10.5500 | não | 11828 |
| 2 | ok | 57 | -201.5025 | -3.9354 | -4.2000 | 1.0000 | 84 | 0.5088 | 0.3537 | 9.2018 | -14.7588 | não | 11312 |
| 3 | ok | 60 | -136.4875 | -1.5380 | -2.5093 | 1.0000 | 25 | 0.6000 | 0.4109 | 16.1792 | -18.5750 | não | 11547 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -3.2593 |
| drawdown_maximo_dias | 60.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -13.4169 |
| mfe_medio | 9.4030 |
| numero_trades | 60.0000 |
| payoff_medio | 0.3823 |
| pnl_total | -168.9950 |
| sharpe_anualizado | -2.7367 |
| win_rate | 0.5127 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -2.0721 |
| drawdown_maximo_dias | 57.2500 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -13.9897 |
| mfe_medio | 10.4921 |
| numero_trades | 59.2500 |
| payoff_medio | 0.5556 |
| pnl_total | -129.5944 |
| sharpe_anualizado | -2.1148 |
| win_rate | 0.5189 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
