---
agente_autor: Athena
area: Walk_Forwards
data_criacao: '2026-05-25T02:30:00Z'
identificador: 2026-05-25-04
estrategia: EstrategiaPreFomcDrift(meetings_csv)
status: concluido
janelas: 4
relevancia: media
tags:
- walk-forward
- pre-fomc
- lucca-moench
- regime-adverso
titulo: "Walk-Forward 2026-05-25-04 — Pre-FOMC isolado nas mesmas janelas"
---

# Walk-Forward 2026-05-25-04 — Pre-FOMC isolado

> Confirmação cruzada do diagnóstico de [[Walk_Forward_2026-05-25-03]]:
> Pre-FOMC e Crabel NR7+SF são positivamente correlacionados em
> regime adverso, não descorrelacionados.

## Resultado por janela

| Janela | Trades | PnL (pts) | Sharpe | Win rate |
|---|---|---|---|---|
| 0 | 2 | +123 | +7.22 | 0.50 |
| 1 | 2 | **−106** | −13.53 | 0.00 |
| 2 | 2 | +96 | +23.33 | 1.00 |
| 3 | 2 | **−621** | −17.45 | 0.00 |

## Diagnóstico

**Janelas 1 e 3 perderam isoladas** — exatamente as janelas onde o NR7+SF também sofreu. Isso refuta a hipótese de descorrelação que motivou o mini-portfolio em [[Walk_Forward_2026-05-25-03]].

Hipótese subsequente: Pre-FOMC drift (Lucca-Moench 2015, dados 1994-2011) está **degradando em 2025**. Regime de Fed mais transparente + meetings com cortes/aumentos abruptos invalidam parcialmente o long-only.

## Configuração

```yaml
estrategia: EstrategiaPreFomcDrift
config_yaml: 05_BACKTEST/walk_forward/configs/noise_area_topstep.yaml
caminho_meetings_csv: dados/macros/fomc_meetings.csv
janelas: 4 × (60 dias treino + 60 dias teste)
```

## Links

- Tese refutada: `[[Walk_Forward_2026-05-25-03]]`.
- Estratégia aprovada (substituiu mini-portfolio): `[[Decisao_2026-05-25-02]]`.
