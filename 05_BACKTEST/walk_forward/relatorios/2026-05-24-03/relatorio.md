---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaNoiseArea
id: 2026-05-24-03
identificador: 2026-05-24-03
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 3
status: concluido
tags:
- walk-forward
- estrategianoisearea
- concluido
titulo: Walk-Forward 2026-05-24-03 — EstrategiaNoiseArea
---

# Relatório Walk-Forward — 2026-05-24-03

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaNoiseArea |
| Status | concluido |
| Identificador | 2026-05-24-03 |
| Manifesto (SHA-256) | f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f |
| Instrumento | MNQ |
| Granularidade | 1m |
| Treino (dias úteis) | 100 |
| Teste (dias úteis) | 60 |
| Passo (dias úteis) | 60 |
| Seed | 42 |
| Total de janelas | 3 |
| Slippage (pts/lado) | 0.25 |
| Comissão (USD/lado/contrato) | 0.62 |

## Métricas por Janela

| Índice | Status | Trades | PnL | Sharpe | Calmar | Drawdown % | Drawdown dias | Win rate | Payoff médio | MFE médio | MAE médio | Look-ahead? | Duração (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ok | 60 | -377.0750 | -10.0768 | -4.2000 | 1.0000 | 81 | 0.0833 | 0.2932 | 11.8708 | -8.8042 | não | 6985 |
| 1 | ok | 58 | -363.5225 | -15.7852 | -4.2000 | 1.0000 | 84 | 0.0345 | 1.0471 | 9.5129 | -8.4526 | não | 7156 |
| 2 | ok | 60 | -570.9250 | -8.6173 | -4.2000 | 1.0000 | 83 | 0.1000 | 1.2215 | 21.0875 | -13.6042 | não | 7266 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -4.2000 |
| drawdown_maximo_dias | 83.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -8.8042 |
| mfe_medio | 11.8708 |
| numero_trades | 60.0000 |
| payoff_medio | 1.0471 |
| pnl_total | -377.0750 |
| sharpe_anualizado | -10.0768 |
| win_rate | 0.0833 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -4.2000 |
| drawdown_maximo_dias | 82.6667 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -10.2870 |
| mfe_medio | 14.1571 |
| numero_trades | 59.3333 |
| payoff_medio | 0.8539 |
| pnl_total | -437.1742 |
| sharpe_anualizado | -11.4931 |
| win_rate | 0.0726 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
