# Validacao Longa do WF apos Bug Fix NR7 (Decisao 2026-05-26-01)

> Periodo: 2025-03-17 a 2026-05-18
> Estrategia: `EstrategiaORBCrabelSFCB` (composicao aprovada Decisao 2026-05-25-02)
> Filtro NR7 corrigido: descarta sabados/domingos e dias com < 300 barras de minuto

## Configuracoes testadas

| Config | Treino (dias) | Teste (dias) | Janelas | Lucrativas | Perdedoras | Sem trades |
|---|---|---|---|---|---|---|
| 60+10 | 60 | 10 | 24 | 9 | 5 | 7 |
| 60+20 | 60 | 20 | 12 | 7 | 2 | 1 |
| 80+20 | 80 | 20 | 11 | 7 | 2 | 1 |
| 100+20 | 100 | 20 | 10 | 6 | 2 | 1 |
| 120+20 | 120 | 20 | 9 | 6 | 1 | 1 |

## Metricas consolidadas (mediana entre janelas com trades)

| Config | Sharpe mediana | Calmar mediana | DD mediana | DD max | Win rate | PnL total (pts) | PnL total (USD) | Trades total |
|---|---|---|---|---|---|---|---|---|
| 60+10 | +9.07 | -24.18 | 0.0000 | 1.0000 | 0.50 | +655.50 | +1311.00 | 28 |
| 60+20 | +8.11 | +44.34 | 0.0592 | 1.0000 | 0.50 | +643.25 | +1286.50 | 26 |
| 80+20 | +8.11 | +44.34 | 0.0889 | 1.0000 | 0.50 | +643.25 | +1286.50 | 25 |
| 100+20 | +7.15 | +44.34 | 0.1187 | 1.0000 | 0.50 | +509.25 | +1018.50 | 22 |
| 120+20 | +8.11 | +69.52 | 0.0889 | 1.0000 | 0.50 | +769.25 | +1538.50 | 19 |

## Criterio de aprovacao (Decisao 2026-05-26-01)

- **Sharpe mediana >= 1.0 em majoria das configuracoes** mantem Decisao 2026-05-25-02.
- **Sharpe mediana < 1.0 em majoria** invalida aprovacao, exige Debate de seguimento.

### Resultado: 5 de 5 configuracoes com Sharpe mediana >= 1.0

**APROVACAO MANTIDA** — estrategia robusta sob diferentes janelas WF.

## PnL total por configuracao (USD, MNQ 1 contrato)

| Config | PnL total | PnL anualizado (~12 meses) |
|---|---|---|
| 60+10 | USD +1311.00 | USD +1123.71/ano |
| 60+20 | USD +1286.50 | USD +1102.71/ano |
| 80+20 | USD +1286.50 | USD +1102.71/ano |
| 100+20 | USD +1018.50 | USD +873.00/ano |
| 120+20 | USD +1538.50 | USD +1318.71/ano |

## Notas

- Backtest assume MaxContratos=1 (pre-condicao da Decisao 2026-05-25-02).
- MNQ: USD 2 por ponto. PnL em pontos × 2 = PnL em USD.
- Sharpe anualizado computado pelo MetricasCalculator do Spec 2.
- Valores `n/a` em janelas significam sem trades suficientes para metricas validas.

---
Gerado por `scripts/wf_validacao_longa_2026-05-27.py`.