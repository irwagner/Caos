---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-29T00:00:00Z'
estrategia: VVG-Late-Session CB(SF(VVG))
id: 2026-05-29-04
identificador: 2026-05-29-04
manifesto_hash: e832e3adf2932c9e17ff30f85d92426c5e3ce8a7e20161ce4a2c100abf483ee1
num_janelas: 18
status: concluido
tags:
- walk-forward
- vvg-late-session-cb-sf-vvg
- concluido
titulo: Walk-Forward 2026-05-29-04 — VVG-Late-Session CB(SF(VVG))
---

# Relatório Walk-Forward — 2026-05-29-04

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | VVG-Late-Session CB(SF(VVG)) |
| Status | concluido |
| Identificador | 2026-05-29-04 |
| Manifesto (SHA-256) | e832e3adf2932c9e17ff30f85d92426c5e3ce8a7e20161ce4a2c100abf483ee1 |
| Instrumento | MNQ |
| Granularidade | 1m |
| Treino (dias úteis) | 60 |
| Teste (dias úteis) | 10 |
| Passo (dias úteis) | 10 |
| Seed | 42 |
| Total de janelas | 18 |
| Slippage (pts/lado) | 0.25 |
| Comissão (USD/lado/contrato) | 0.62 |

## Métricas por Janela

| Índice | Status | Trades | PnL | Sharpe | Calmar | Drawdown % | Drawdown dias | Win rate | Payoff médio | MFE médio | MAE médio | Look-ahead? | Duração (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 6281 |
| 1 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5969 |
| 2 | ok | 2 | -443.9900 | -1812.2820 | -25.2000 | 1.0000 | 3 | 0.0000 | 0.0000 | 31.2500 | -236.2500 | não | 6031 |
| 3 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 6000 |
| 4 | ok | 2 | 15.7600 | 2.8305 | 16.9941 | 1.0000 | 0 | 0.5000 | 1.6744 | 61.8750 | -67.8750 | não | 5938 |
| 5 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5937 |
| 6 | ok | 1 | 151.3800 | — | — | 0.0000 | 0 | 1.0000 | — | 180.5000 | -2.7500 | não | 6000 |
| 7 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5859 |
| 8 | ok | 1 | 60.3800 | — | — | 0.0000 | 0 | 1.0000 | — | 65.2500 | -40.7500 | não | 5860 |
| 9 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5953 |
| 10 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5750 |
| 11 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 6062 |
| 12 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5875 |
| 13 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 5891 |
| 14 | sem-trades | 0 | 0.0000 | — | — | — | — | — | — | — | — | não | 6344 |
| 15 | ok | 1 | 161.8800 | — | — | 0.0000 | 0 | 1.0000 | — | 171.5000 | -24.2500 | não | 6203 |
| 16 | ok | 2 | 46.5100 | 8.1894 | 135.9689 | 0.1853 | 0 | 0.5000 | 6.3956 | 96.1250 | -40.7500 | não | 6031 |
| 17 | ok | 2 | 28.7600 | 10.9434 | 1958.7892 | 0.0127 | 9 | 0.5000 | 78.7297 | 85.2500 | -34.7500 | não | 5656 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | 76.4815 |
| drawdown_maximo_dias | 0.0000 |
| drawdown_maximo_percentual | 0.0127 |
| mae_medio | -40.7500 |
| mfe_medio | 85.2500 |
| numero_trades | 0.0000 |
| payoff_medio | 4.0350 |
| pnl_total | 0.0000 |
| sharpe_anualizado | 5.5099 |
| win_rate | 0.5000 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 521.6380 |
| drawdown_maximo_dias | 1.7143 |
| drawdown_maximo_percentual | 0.3140 |
| mae_medio | -63.9107 |
| mfe_medio | 98.8214 |
| numero_trades | 0.6111 |
| payoff_medio | 21.6999 |
| pnl_total | 1.1489 |
| sharpe_anualizado | -447.5797 |
| win_rate | 0.6429 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
