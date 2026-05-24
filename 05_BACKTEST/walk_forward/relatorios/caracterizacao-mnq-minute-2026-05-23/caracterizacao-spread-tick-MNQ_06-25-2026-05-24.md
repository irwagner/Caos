# Caracterizacao do spread MNQ tick — MNQ_06-25

**Data:** 2026-05-24
**Fonte:** e:\CAOS\dados\MNQ\MNQ_06-25\tick\spread_minuto.csv
**Periodo:** 2025-04-04 00:00:00+00:00 -> 2025-06-13 23:27:00+00:00

## Spread agregado por minuto (pts)

| Métrica | Valor |
|---|---|
| Minutos analisados | 34,205 |
| Spread médio (geral) | 0.4946 pts |
| Spread mediano (geral) | 0.5145 pts |
| Spread RTH NY mediano | 0.4104 pts |
| Spread overnight mediano | 0.5455 pts |
| Spread p90 | 0.7344 pts |
| Spread p99 | 1.1611 pts |

## Razão spread / range_minuto (informa slippage_fracao_range)

| Estatística | Valor |
|---|---|
| Mediana | 0.0812 |
| Média | 0.0966 |
| p25 | 0.0451 |
| p75 | 0.1296 |
| p90 | 0.1866 |

**Implicação:** o `slippage_fracao_range=0.075` usado no sweep superestima a fricção realista por **0.9x** (mediana real ~0.0812).

## Spread por hora UTC

| Hora UTC | spread mediano | spread médio | N minutos |
|---|---|---|---|
| 00 | 0.5476 | 0.5660 | 1,500 |
| 01 | 0.5305 | 0.5441 | 1,500 |
| 02 | 0.5207 | 0.5357 | 1,500 |
| 03 | 0.5151 | 0.5227 | 1,500 |
| 04 | 0.5187 | 0.5307 | 1,500 |
| 05 | 0.5180 | 0.5271 | 1,500 |
| 06 | 0.5479 | 0.5617 | 1,500 |
| 07 | 0.5569 | 0.5588 | 1,500 |
| 08 | 0.5739 | 0.5834 | 1,500 |
| 09 | 0.5571 | 0.5692 | 1,500 |
| 10 | 0.5570 | 0.5791 | 1,500 |
| 11 | 0.5727 | 0.5947 | 1,500 |
| 12 | 0.5926 | 0.6439 | 1,500 |
| 13 | 0.5112 | 0.5111 | 1,500 |
| 14 | 0.4098 | 0.4194 | 1,500 |
| 15 | 0.3970 | 0.4150 | 1,501 |
| 16 | 0.3966 | 0.4097 | 1,501 |
| 17 | 0.3941 | 0.3900 | 1,445 |
| 18 | 0.3916 | 0.3958 | 1,440 |
| 19 | 0.4066 | 0.4056 | 1,440 |
| 20 | 0.5140 | 0.5349 | 1,440 |
| 21 | 0.0000 | -18.5774 | 57 |
| 22 | 0.6683 | 0.7414 | 1,441 |
| 23 | 0.5545 | 0.5629 | 1,440 |

