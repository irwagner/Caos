---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaNoiseArea
id: 2026-05-24-02
identificador: 2026-05-24-02
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategianoisearea
- concluido
titulo: Walk-Forward 2026-05-24-02 — EstrategiaNoiseArea
---

# Relatório Walk-Forward — 2026-05-24-02

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaNoiseArea |
| Status | concluido |
| Identificador | 2026-05-24-02 |
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
| 0 | ok | 60 | -145.8125 | -6.6195 | -3.9578 | 1.0000 | 70 | 0.1500 | 1.6747 | 12.4458 | -6.2333 | não | 6047 |
| 1 | ok | 60 | -456.5500 | -8.7258 | -4.1947 | 1.0000 | 81 | 0.1167 | 0.2524 | 15.5542 | -12.4292 | não | 6297 |
| 2 | ok | 58 | -265.2225 | -11.4389 | -4.2000 | 1.0000 | 84 | 0.1034 | 1.3568 | 12.7198 | -8.2586 | não | 6140 |
| 3 | ok | 59 | -492.7425 | -7.7862 | -4.2000 | 1.0000 | 83 | 0.0678 | 2.7604 | 19.6907 | -14.6780 | não | 6344 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | -4.1973 |
| drawdown_maximo_dias | 82.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -10.3439 |
| mfe_medio | 14.1370 |
| numero_trades | 59.5000 |
| payoff_medio | 1.5158 |
| pnl_total | -360.8862 |
| sharpe_anualizado | -8.2560 |
| win_rate | 0.1101 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | -4.1381 |
| drawdown_maximo_dias | 79.5000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -10.3998 |
| mfe_medio | 15.1026 |
| numero_trades | 59.2500 |
| payoff_medio | 1.5111 |
| pnl_total | -340.0819 |
| sharpe_anualizado | -8.6426 |
| win_rate | 0.1095 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
