---
agente_autor: Athena
area: Walk_Forwards
data_criacao: '2026-05-25T03:00:00Z'
identificador: 2026-05-25-05
estrategia: EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7)))
status: concluido
sharpe_mediano: 2.91
calmar_mediano: 3.22
pnl_total_mediano: 240.15
janelas: 4
relevancia: alta
tags:
- walk-forward
- crabel-nr7
- spread-filter
- circuit-breaker
- aprovado
- versao-final
titulo: "Walk-Forward 2026-05-25-05 — Crabel NR7 + Spread Filter + Circuit Breaker"
---

# Walk-Forward 2026-05-25-05

> **Versão APROVADA da estratégia** ([[Decisao_2026-05-25-02]]).
> Adiciona EstrategiaCircuitBreaker à composição NR7+SF para trazer
> a janela 1 para dentro do envelope Topstep.

## Resultado por janela

| Janela | Trades | PnL (pts) | Sharpe | Win rate |
|---|---|---|---|---|
| 0 | 8 | +251 | +2.58 | 0.50 |
| 1 | 2 | **−1435** | −11.66 | 0.00 |
| 2 | 8 | +1339 | +6.88 | 0.70 |
| 3 | 5 | +229 | +3.24 | 0.40 |

**Mediana**: Sharpe +2.91, PnL +240, Calmar +3.22.

## Configuração

```yaml
estrategia: EstrategiaCircuitBreaker
  componente:
    EstrategiaSpreadFilter:
      modo: mediana_diaria
      warmup: 30 minutos
      running_median: true
      componente:
        EstrategiaORBCrabel:
          modo_nr: nr7
limites_circuit_breaker:
  diario_pts: -250
  semanal_pts: -750
  janela_pts: -1000
config_yaml: 05_BACKTEST/walk_forward/configs/noise_area_topstep.yaml
manifesto_hash: f81eb5be8bacd0763d3e33d870b513186a6e43d3892a79f9afe649f2f5659f7f
```

## Comportamento do Circuit Breaker na janela 1

Janela 1 sem CB: 9 trades, PnL −1711 pts.
Janela 1 com CB: 2 trades aceitos, 7 trades descartados, PnL −1435 pts.

O CB **funcionou exatamente como projetado**: detectou regime adverso e parou de operar. Diferença −1711 → −1435 = 276 pts (USD 552) economizados.

## Links

- Decisão que aprovou: `[[Decisao_2026-05-25-02]]`.
- WF baseline (sem CB): `[[Walk_Forward_2026-05-25-02]]`.
- Caracterização tick: `[[Caracterizacao_Spread_MNQ_14_Meses]]`.

## Reproduzir

```cmd
cd e:\CAOS\CAOS_Orchestrator
python scripts\rodar_wf_nr7_sf_cb.py 2026-05-25-05
```

Relatório: `05_BACKTEST/walk_forward/relatorios/2026-05-25-05/`.
