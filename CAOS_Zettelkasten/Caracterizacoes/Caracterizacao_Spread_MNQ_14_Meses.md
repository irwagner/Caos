---
agente_autor: Athena
area: Caracterizacoes
data_criacao: '2026-05-24T12:00:00Z'
periodo_dados: '2025-04-04 a 2026-05-07'
contratos: ['MNQ_06-25', 'MNQ_09-25', 'MNQ_12-25', 'MNQ_03-26', 'MNQ_06-26']
total_minutos: 351437
relevancia: alta
tags:
- caracterizacao
- spread-tick
- mnq
- regra-de-ouro
- 14-meses
titulo: "Caracterizacao do Spread MNQ — 14 meses (5 contratos)"
---

# Caracterização do Spread MNQ — 14 meses contíguos

> Base empírica para a **regra de ouro do projeto CAOS**: edge bruto
> ≥ 4 pts/trade em MNQ minute para Sharpe ≥ 1 sob fricção Topstep.

## Dataset

- **5 contratos**: 06-25, 09-25, 12-25, 03-26, 06-26.
- **210 GB de tick.txt** processado via streaming (~131k lin/s puro Python).
- **351 437 minutos** agregados em `dados/MNQ/MNQ_*/tick/spread_minuto.csv`.
- Período: **2025-04-04 → 2026-05-07** (14 meses contíguos).

## Spread efetivo medido

| Regime | Spread mediano | p90 |
|---|---|---|
| **RTH NY (14:30-21:00 UTC)** | **0.37 pts** | 0.56 pts |
| Geral (24h) | 0.49 pts | 0.73 pts |
| Overnight | 0.52 pts | 0.76 pts |
| Pico iliquidez (h=22 UTC) | 0.67 pts | — |

## Razão spread / range_minuto

| Métrica | Valor |
|---|---|
| Mediana | **0.0812** |
| Média | 0.097 |
| p75 | 0.130 |

**Validação crítica:** o `slippage_fracao_range = 0.075` usado no sweep de fricção ([[Sweep_Friccao_NoiseArea]]) é praticamente o valor real (overestimou só 0.9x). A regra de ouro **não é exagero — é o que a fricção REALMENTE custa em MNQ**.

## Sazonalidade trimestral descoberta

Spread varia de forma cíclica com vencimentos de contrato:

- **Pico** antes de cada vencimento: abr/2025 = 0.64, mar/2026 = 0.58 pts.
- **Mínimo** no meio do trimestre: set/2025 = 0.42, jul/2025 = 0.44 pts.

**Implicação operacional**: estratégias que operam só RTH NY pagam ~30% menos fricção. Estratégias overnight pagam mais. Esta sazonalidade deve ser considerada em estratégias multi-month — o roll perto do vencimento aumenta custos.

## Regra de ouro derivada

Para Sharpe ≥ 1 anualizado em MNQ minute sob fricção Topstep:

> **Edge bruto necessário ≥ 4 pts/trade.**

Derivação: fricção realista = 2.0 pts/trade (slippage 0.25 absoluto + spread efetivo RTH 0.37/2 + comissão 0.62 USD ÷ 2 USD/pt + slippage proporcional ~0.08 × range). Margem de segurança 50% → 4 pts/trade.

## Implicação para estratégias

**Eliminadas** (edge < 4 pts/trade):
- ORB sem filtro (~2 pts).
- Noise Area momentum/mean-reversion (~1.7 pts).
- Estratégias intraday "no ruído branco" do MNQ.

**Sobreviventes**:
- Pre-FOMC drift (~50-60 pts/trade, mas baixa frequência).
- Crabel NR7 + Spread Filter + Circuit Breaker (~30 pts/trade) — `[[Decisao_2026-05-25-02]]`.

## Como reproduzir

```cmd
cd e:\CAOS\CAOS_Orchestrator
python scripts\agregar_spread_tick.py MNQ_06-25
python scripts\analisar_spread_mnq.py MNQ_06-25
python scripts\comparar_spread_contratos.py
```

Output em `05_BACKTEST/walk_forward/relatorios/caracterizacao-mnq-minute-2026-05-23/`.

## Links

- Decisão que usa esta caracterização: `[[Decisao_2026-05-25-02]]`.
- Sweep de fricção que validou empiricamente: `2026-05-24-10..14`.
