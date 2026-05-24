---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaNoiseArea
id: 2026-05-24-17
identificador: 2026-05-24-17
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategianoisearea
- concluido
titulo: Walk-Forward 2026-05-24-17 — EstrategiaNoiseArea
---

# Relatório Walk-Forward — 2026-05-24-17

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaNoiseArea |
| Status | concluido |
| Identificador | 2026-05-24-17 |
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
| 0 | ok | 60 | -243.4625 | -4.8538 | -4.2000 | 1.0000 | 81 | 0.3667 | 0.1942 | 6.2333 | -12.2125 | não | 5047 |
| 1 | ok | 60 | -103.3625 | -2.2864 | -3.3058 | 1.0000 | 30 | 0.5167 | 0.5026 | 12.4750 | -15.4042 | não | 4969 |
| 2 | ok | 58 | -197.8225 | -4.6529 | -4.0759 | 1.0000 | 80 | 0.4828 | 0.2824 | 8.3362 | -13.2284 | não | 4922 |
| 3 | ok | 59 | -188.7425 | -1.8642 | -2.8652 | 1.0000 | 51 | 0.5424 | 0.4348 | 14.6780 | -19.6907 | não | 4984 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -3.6908 |
| drawdown_maximo_dias | 65.5000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -14.3163 |
| mfe_medio | 10.4056 |
| numero_trades | 59.5000 |
| payoff_medio | 0.3586 |
| pnl_total | -193.2825 |
| sharpe_anualizado | -3.4696 |
| win_rate | 0.4997 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -3.6117 |
| drawdown_maximo_dias | 60.5000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -15.1339 |
| mfe_medio | 10.4306 |
| numero_trades | 59.2500 |
| payoff_medio | 0.3535 |
| pnl_total | -183.3475 |
| sharpe_anualizado | -3.4143 |
| win_rate | 0.4771 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
