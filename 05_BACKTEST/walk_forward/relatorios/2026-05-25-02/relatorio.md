---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-25T00:00:00Z'
estrategia: EstrategiaSpreadFilter
id: 2026-05-25-02
identificador: 2026-05-25-02
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaspreadfilter
- concluido
titulo: Walk-Forward 2026-05-25-02 — EstrategiaSpreadFilter
---

# Relatório Walk-Forward — 2026-05-25-02

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaSpreadFilter |
| Status | concluido |
| Identificador | 2026-05-25-02 |
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
| 0 | ok | 8 | 251.1400 | 2.5769 | 3.3359 | 0.6835 | 21 | 0.5000 | 1.6853 | 164.0625 | -87.9375 | não | 7110 |
| 1 | ok | 9 | -1711.2050 | -6.4595 | -4.2000 | 1.0000 | 70 | 0.2222 | 0.3668 | 74.5000 | -220.7778 | não | 7172 |
| 2 | ok | 8 | 1338.8400 | 6.8777 | 20.3458 | 0.2064 | 14 | 0.6250 | 2.5613 | 330.5938 | -73.5312 | não | 6843 |
| 3 | ok | 5 | 229.1625 | 3.2438 | 3.1024 | 0.5752 | 35 | 0.4000 | 2.6080 | 256.9000 | -120.7500 | não | 6922 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | 3.2191 |
| drawdown_maximo_dias | 28.0000 |
| drawdown_maximo_percentual | 0.6293 |
| mae_medio | -104.3438 |
| mfe_medio | 210.4812 |
| numero_trades | 8.0000 |
| payoff_medio | 2.1233 |
| pnl_total | 240.1513 |
| sharpe_anualizado | 2.9103 |
| win_rate | 0.4500 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 5.6460 |
| drawdown_maximo_dias | 35.0000 |
| drawdown_maximo_percentual | 0.6163 |
| mae_medio | -125.7491 |
| mfe_medio | 206.5141 |
| numero_trades | 7.5000 |
| payoff_medio | 1.8053 |
| pnl_total | 26.9844 |
| sharpe_anualizado | 1.5597 |
| win_rate | 0.4368 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
