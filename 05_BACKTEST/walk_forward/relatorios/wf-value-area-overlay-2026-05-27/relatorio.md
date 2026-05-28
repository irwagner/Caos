# WF com Value Area Filter overlay (Decisao 2026-05-25-02)

> Periodo: 2025-03-17 a 2026-05-18
> Configuracao WF: treino=60 dias uteis, teste=10 dias uteis
> Filtro: Value Area do dia anterior (cobertura 70%, modo 'trend')
> Tese: estrategia ORB+NR7+SF+CB e estrategia de breakout — funciona melhor em dias TREND

## Comparacao baseline vs overlay

| Metrica | Baseline (sem VA) | Overlay (com VA, modo trend) | Delta |
|---|---|---|---|
| Janelas total | 24 | 24 | 0 |
| Janelas com trades | 17 | 15 | -2 |
| Janelas sem trades | 7 | 9 | 2 |
| Janelas lucrativas | 9 | 6 | -3 |
| Janelas perdedoras | 5 | 5 | 0 |
| Trades total | 28 | 17 | -11 |
| Trades mediana/janela | +1 | +1 | +0 |
| PnL total (pts) | +655.50 | -628.50 | -1284.00 |
| PnL total (USD) | +1311.00 | -1257.00 | -2568.00 |
| Sharpe mediana | +9.07 | +6.05 | -3.02 |
| Drawdown mediana | +0.0000 | +0.0000 | +0.0000 |
| Win rate mediana | +0.50 | +0.50 | +0.00 |

## Estatistica de regime (overlay)

- Dias TREND: 7
- Dias RANGE: 5
- % TREND: 58.3%

## Veredito

**OVERLAY DEGRADA** — filtro de regime reduz performance. Hipotese de Market Profile (80% rule) nao se aplica nesta estrategia.

## Implicacoes

- Se overlay melhora: incorporar como camada 4 da estrategia aprovada.
  Exige Debate formal (gatilho G5: muda regra de decisao da Decisao 2026-05-25-02).
- Se overlay degrada: refutado empiricamente. Valor do hold-out atual e do paper
  arXiv 2605.11423 (Volatility-Volume-Gap classifier) precisa ser investigado.
- Se neutro: deixar como overlay opcional, util para regimes especificos.

## Notas

- Baseline = `EstrategiaORBCrabelSFCB` (composicao aprovada Decisao 2026-05-25-02).
- Overlay = `EstrategiaValueAreaFilter(baseline, modo='trend')`.
- Cobertura VA = 70% (constante de Market Profile, CME Group).
- Sem novos parametros otimizaveis livres (Property anti-overfit).

---
Gerado por `scripts/wf_value_area_overlay_2026-05-27.py`.