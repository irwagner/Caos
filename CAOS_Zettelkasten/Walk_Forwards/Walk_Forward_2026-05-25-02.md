---
agente_autor: Athena
area: Walk_Forwards
data_criacao: '2026-05-25T01:30:00Z'
identificador: 2026-05-25-02
estrategia: EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7))
status: concluido
sharpe_mediano: 2.91
calmar_mediano: 3.22
pnl_total_mediano: 240.15
janelas: 4
relevancia: media
tags:
- walk-forward
- crabel-nr7
- spread-filter
- running-median
- bloqueado-pela-janela-1
titulo: "Walk-Forward 2026-05-25-02 — NR7 + Spread Filter (running median, sem CB)"
---

# Walk-Forward 2026-05-25-02

> **Versão sem Circuit Breaker.** Janela 1 com PnL −1711 pts (USD −3422)
> excede trailing drawdown Topstep (USD −2500). Bloqueada por
> [[Decisao_2026-05-25-01]]. Resolvida por [[Walk_Forward_2026-05-25-05]]
> (com CB).

## Resultado por janela

| Janela | Trades | PnL (pts) | Sharpe |
|---|---|---|---|
| 0 | 8 | +251 | +2.58 |
| 1 | 9 | **−1711** | −6.46 |
| 2 | 8 | +1339 | +6.88 |
| 3 | 5 | +229 | +3.24 |

## Achado lateral

Esta foi a versão **corrigida** do look-ahead disfarçado. Comparação:

| | Com look-ahead (`2026-05-24-21`) | Running median (`2026-05-25-02`) |
|---|---|---|
| Sharpe mediano | +3.37 | **+2.91** |
| PnL mediano | +269 | +240 |
| Calmar | +4.00 | +3.22 |
| Janela 1 | −1877 | −1711 |

Degradação após correção: ~14%. Confirma que o look-ahead **não era a causa principal** do edge — a tese tem fundamento real.

## Links

- Decisão de bloqueio: `[[Decisao_2026-05-25-01]]`.
- WF aprovado (com CB): `[[Walk_Forward_2026-05-25-05]]`.
- Mini-portfolio refutado: `[[Walk_Forward_2026-05-25-03]]`.
