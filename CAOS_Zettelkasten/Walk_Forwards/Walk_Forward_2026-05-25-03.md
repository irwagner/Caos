---
agente_autor: Athena
area: Walk_Forwards
data_criacao: '2026-05-25T02:00:00Z'
identificador: 2026-05-25-03
estrategia: EstrategiaPortfolio([Pre-FOMC, NR7+SF])
status: concluido
sharpe_mediano: 0.08
janelas: 4
relevancia: alta
tags:
- walk-forward
- portfolio
- pre-fomc
- crabel-nr7
- tese-refutada
titulo: "Walk-Forward 2026-05-25-03 — Mini-portfolio (TESE REFUTADA)"
---

# Walk-Forward 2026-05-25-03 — Mini-portfolio (REFUTADO)

> **Achado mais valioso de "ausência de edge".** Refutou empiricamente
> a tese de descorrelação entre Pre-FOMC e Crabel NR7+SF. Confirmou que
> regime adverso afeta múltiplas estratégias simultaneamente — funda-
> mentou a necessidade de `EstrategiaCircuitBreaker`.

## Composição testada

```
EstrategiaPortfolio([
  EstrategiaPreFomcDrift(meetings_csv),
  EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7), mediana_diaria),
])
```

Hipótese inicial: as duas estratégias têm gatilhos completamente diferentes (Pre-FOMC = eventos macro; NR7+SF = compressão de volatilidade intraday). Esperávamos correlação baixa → diversificação reduzindo o pior caso da janela 1.

## Resultado por janela

| Janela | Trades | PnL (pts) | Sharpe | Comparação NR7+SF isolado |
|---|---|---|---|---|
| 0 | 10 | +374 | +3.36 | melhor (+251 isolado) |
| 1 | 11 | **−1817** | −6.21 | **PIOR** (−1711 isolado) |
| 2 | 10 | +1435 | +6.61 | melhor (+1339 isolado) |
| 3 | 7 | **−392** | −3.20 | **muito pior** (+229 isolado) |

**Mediana**: Sharpe **+0.08** (vs +2.91 do NR7+SF isolado).

## Diagnóstico

Pre-FOMC isolado (`[[Walk_Forward_2026-05-25-04]]`) confirmou:

- Janela 1 (set-nov 2025): PnL −106 pts (perdeu).
- Janela 3 (out-nov 2025): PnL −621 pts (perdeu).

Pre-FOMC degradou em 2025 H2. Hipótese: Fed mais transparente → pricing antecipado → drift menor. Meetings 2025 com cortes/aumentos abruptos invalidaram a tese long-only do Lucca-Moench 2015.

## Implicação

**Diversificação por estratégias separadas não funciona em regime macro adverso.** A defesa correta é parar de operar (Circuit Breaker), não compensar com outra estratégia.

Esse achado fundamentou a Decisão `[[Decisao_2026-05-25-02]]` — em vez de usar mini-portfolio, usar circuit breaker.

## Links

- Componentes: `[[Walk_Forward_2026-05-25-02]]` (NR7+SF), `[[Walk_Forward_2026-05-25-04]]` (Pre-FOMC isolado).
- Decisão que se beneficiou: `[[Decisao_2026-05-25-02]]`.
