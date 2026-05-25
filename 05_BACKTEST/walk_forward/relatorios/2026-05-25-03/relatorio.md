---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-25T00:00:00Z'
estrategia: Portfolio_PreFOMC_NR7SF
id: 2026-05-25-03
identificador: 2026-05-25-03
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 4
status: concluido
tags:
- walk-forward
- portfolio-prefomc-nr7sf
- concluido
titulo: Walk-Forward 2026-05-25-03 — Portfolio_PreFOMC_NR7SF
---

# Relatório Walk-Forward — 2026-05-25-03

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | Portfolio_PreFOMC_NR7SF |
| Status | concluido |
| Identificador | 2026-05-25-03 |
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
| 0 | ok | 10 | 373.9875 | 3.3570 | 5.8345 | 0.4999 | 12 | 0.5000 | 1.9336 | 177.1000 | -89.2750 | não | 7954 |
| 1 | ok | 11 | -1817.3825 | -6.2142 | -4.2000 | 1.0000 | 70 | 0.1818 | 0.4467 | 90.2500 | -227.8182 | não | 8062 |
| 2 | ok | 10 | 1434.5875 | 6.6098 | 21.8009 | 0.1927 | 12 | 0.7000 | 1.9297 | 309.7250 | -99.2500 | não | 7531 |
| 3 | ok | 7 | -392.0275 | -3.2019 | -1.7677 | 1.0000 | 44 | 0.2857 | 1.4478 | 255.7857 | -178.6786 | não | 7719 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | 2.0334 |
| drawdown_maximo_dias | 28.0000 |
| drawdown_maximo_percentual | 0.7500 |
| mae_medio | -138.9643 |
| mfe_medio | 216.4429 |
| numero_trades | 10.0000 |
| payoff_medio | 1.6887 |
| pnl_total | -9.0200 |
| sharpe_anualizado | 0.0775 |
| win_rate | 0.3929 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 5.4169 |
| drawdown_maximo_dias | 34.5000 |
| drawdown_maximo_percentual | 0.6732 |
| mae_medio | -148.7554 |
| mfe_medio | 208.2152 |
| numero_trades | 9.5000 |
| payoff_medio | 1.4395 |
| pnl_total | -100.2087 |
| sharpe_anualizado | 0.1377 |
| win_rate | 0.4169 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
