---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:00:00Z'
estrategia: EstrategiaSpreadFilter
id: 2026-05-24-19
identificador: 2026-05-24-19
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- estrategiaspreadfilter
- concluido
titulo: Walk-Forward 2026-05-24-19 — EstrategiaSpreadFilter
---

# Relatório Walk-Forward — 2026-05-24-19

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaSpreadFilter |
| Status | concluido |
| Identificador | 2026-05-24-19 |
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
| 0 | ok | 2 | -48.4900 | -6.1329 | -2.9679 | 1.0000 | 0 | 0.5000 | 0.2934 | 87.8750 | -124.2500 | não | 4125 |
| 1 | ok | 2 | 88.2600 | 3.5961 | 3.9595 | 1.0000 | 0 | 0.5000 | 1.9427 | 189.1250 | -86.1250 | não | 4078 |
| 2 | ok | 2 | -26.2400 | -1.4229 | -0.9450 | 1.0000 | 0 | 0.5000 | 0.7750 | 146.1250 | -142.5000 | não | 3984 |
| 3 | ok | 2 | 118.5100 | 4.8952 | 6.4962 | 0.6465 | 0 | 0.5000 | 2.5467 | 217.2500 | -106.7500 | não | 4110 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | 1.5073 |
| drawdown_maximo_dias | 0.0000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -115.5000 |
| mfe_medio | 167.6250 |
| numero_trades | 2.0000 |
| payoff_medio | 1.3589 |
| pnl_total | 31.0100 |
| sharpe_anualizado | 1.0866 |
| win_rate | 0.5000 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 1.6357 |
| drawdown_maximo_dias | 0.0000 |
| drawdown_maximo_percentual | 0.9116 |
| mae_medio | -114.9062 |
| mfe_medio | 160.0938 |
| numero_trades | 2.0000 |
| payoff_medio | 1.3895 |
| pnl_total | 33.0100 |
| sharpe_anualizado | 0.2339 |
| win_rate | 0.5000 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
