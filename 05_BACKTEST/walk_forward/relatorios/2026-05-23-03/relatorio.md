---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T00:00:00Z'
estrategia: EstrategiaORB
id: 2026-05-23-03
identificador: 2026-05-23-03
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
num_janelas: 18
status: concluido
tags:
- walk-forward
- estrategiaorb
- concluido
titulo: Walk-Forward 2026-05-23-03 — EstrategiaORB
---

# Relatório Walk-Forward — 2026-05-23-03

## Resumo

| Campo | Valor |
|---|---|
| Estratégia | EstrategiaORB |
| Status | concluido |
| Identificador | 2026-05-23-03 |
| Manifesto (SHA-256) | f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f |
| Instrumento | MNQ |
| Granularidade | 1m |
| Treino (dias úteis) | 60 |
| Teste (dias úteis) | 10 |
| Passo (dias úteis) | 10 |
| Seed | 42 |
| Total de janelas | 18 |
| Hold-out (dias úteis) | 60 |
| Hold-out início | 2026-02-24T00:00:00+00:00 |
| Hold-out fim | 2026-05-19T00:00:00+00:00 |
| Slippage (pts/lado) | 0.25 |
| Comissão (USD/lado/contrato) | 0.62 |

## Métricas por Janela

| Índice | Status | Trades | PnL | Sharpe | Calmar | Drawdown % | Drawdown dias | Win rate | Payoff médio | MFE médio | MAE médio | Look-ahead? | Duração (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ok | 10 | 219.3000 | 3.2150 | 18.0683 | 1.0000 | 3 | 0.5000 | 1.6715 | 125.7750 | -83.0250 | não | 750 |
| 1 | ok | 9 | -218.0800 | -3.3025 | -12.7891 | 1.0000 | 9 | 0.3333 | 1.1518 | 88.3333 | -109.0278 | não | 750 |
| 2 | ok | 10 | 101.3000 | 1.5980 | 9.4463 | 0.7274 | 2 | 0.6000 | 0.8504 | 81.9750 | -95.2250 | não | 765 |
| 3 | ok | 10 | -215.7000 | -2.8731 | -18.8104 | 1.0000 | 7 | 0.4000 | 0.9125 | 87.1000 | -107.3750 | não | 782 |
| 4 | ok | 10 | -558.7000 | -5.4163 | -24.9371 | 1.0000 | 8 | 0.4000 | 0.6411 | 67.6000 | -159.6250 | não | 765 |
| 5 | ok | 10 | -123.4500 | -1.1436 | -7.4610 | 1.0000 | 10 | 0.4000 | 1.2556 | 99.7750 | -137.2750 | não | 750 |
| 6 | ok | 10 | 259.3000 | 6.4681 | 83.2509 | 0.3027 | 2 | 0.5000 | 2.9087 | 113.0250 | -64.6250 | não | 766 |
| 7 | ok | 10 | -21.2000 | -0.2513 | -1.3819 | 1.0000 | 5 | 0.7000 | 0.4125 | 96.0000 | -95.2750 | não | 781 |
| 8 | ok | 10 | -348.7000 | -2.3107 | -11.4047 | 1.0000 | 2 | 0.5000 | 0.6223 | 96.1500 | -140.5750 | não | 750 |
| 9 | ok | 10 | 440.0500 | 3.2621 | 28.3077 | 0.4710 | 2 | 0.6000 | 1.0906 | 186.3500 | -135.1500 | não | 766 |
| 10 | ok | 10 | -945.9500 | -5.3794 | -16.3236 | 1.0000 | 9 | 0.2000 | 1.5437 | 110.6250 | -197.5750 | não | 750 |
| 11 | ok | 10 | 1036.8000 | 6.5575 | 71.9782 | 0.3501 | 4 | 0.6000 | 2.0180 | 278.8000 | -142.0000 | não | 797 |
| 12 | ok | 9 | 244.4200 | 2.6723 | 19.7119 | 0.5611 | 9 | 0.4444 | 2.2204 | 139.1389 | -128.5000 | não | 719 |
| 13 | ok | 10 | -215.2000 | -1.3452 | -8.7312 | 1.0000 | 5 | 0.4000 | 1.2042 | 138.3750 | -184.4250 | não | 781 |
| 14 | ok | 9 | -265.5800 | -3.0203 | -15.9778 | 1.0000 | 2 | 0.5556 | 0.3811 | 84.6389 | -103.7778 | não | 672 |
| 15 | ok | 10 | 698.0500 | 7.0359 | 116.0194 | 0.1933 | 1 | 0.7000 | 1.1501 | 141.0250 | -103.2750 | não | 766 |
| 16 | ok | 10 | 1149.8000 | 7.8134 | 110.9642 | 0.2271 | 3 | 0.6000 | 2.4897 | 217.5250 | -109.3500 | não | 765 |
| 17 | ok | 10 | 200.3000 | 1.0165 | 7.2641 | 0.9243 | 3 | 0.6000 | 0.7836 | 234.7250 | -186.7250 | não | 766 |

## Agregado (mediana)

| Métrica | Mediana |
|---|---|
| calmar | 2.9411 |
| drawdown_maximo_dias | 3.5000 |
| drawdown_maximo_percentual | 1.0000 |
| mae_medio | -118.9250 |
| mfe_medio | 111.8250 |
| numero_trades | 10.0000 |
| payoff_medio | 1.1510 |
| pnl_total | 40.0500 |
| sharpe_anualizado | 0.3826 |
| win_rate | 0.5000 |

## Agregado (média)

| Métrica | Média |
|---|---|
| calmar | 19.2886 |
| drawdown_maximo_dias | 4.7778 |
| drawdown_maximo_percentual | 0.7643 |
| mae_medio | -126.8225 |
| mfe_medio | 132.6076 |
| numero_trades | 9.8333 |
| payoff_medio | 1.2949 |
| pnl_total | 79.8200 |
| sharpe_anualizado | 0.8109 |
| win_rate | 0.5019 |

## Versões de Dependências

| Dependência | Versão |
|---|---|
| numpy | 2.2.6 |
| pandas | 2.3.0 |
| python | 3.11.9 |
