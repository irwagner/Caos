---
tipo: estrategia_arquivada
estrategia: EstrategiaVvgLateSessionReversal
status: morta
data_arquivamento: 2026-05-29
motivo: falha-year-stability-no-walk-forward
spec: caos-vvg-late-session-reversal-mnq
paper_base: arXiv 2605.11423 (Mesfin)
links:
  - "[[Refutacao_VVG_Late_Session_2026-05-29]]"
  - "[[Calibracao_VVG_2026-05-29]]"
  - "[[Decisao_2026-05-29-03]]"
tags:
  - estrategia-morta
  - vvg
  - late-session-reversal
  - fallback-A
  - mesfin
---

# VVG Late-Session Reversal — ARQUIVADA

Estratégia direcional de reversão de fim de sessão para o MNQ em dias
VVG-positivos (classificador Volatility-Volume-Gap de Mesfin, arXiv
2605.11423). Arquivada em **2026-05-29** via **fallback A automático**
(R7.4 / R9) após reprovar o Walk-Forward longo de validação.

## Por que está morta

WF longo `2026-05-29-04` (60+10 anchored, 2025-07-01 a 2026-05-15, 1
contrato MNQ, fricção Topstep). Composição CB(SF(VVG)):

| Critério | Observado | Limiar | Resultado |
|---|---|---|---|
| Sharpe mediana | 5.5099 | >= 1.0 | PASSA |
| Calmar mediana | 76.4815 | >= 1.5 | PASSA |
| PnL total | +20.68 pts | > 0 | PASSA |
| **Year-stability** | **1/4 trimestres** | **>= 3/4** | **FALHA** |

Sharpe positivo em apenas 1 dos 4 trimestres (2025-Q3, 2025-Q4 e 2026-Q1
todos negativos; só 2026-Q2 positivo). O edge não persiste entre regimes.
Falha de **consistência temporal** — exatamente o que o abstract do paper
Mesfin já admitia ("all tested directional trading strategies fail
institutional validation standards ... multi-year consistency").

Detalhes completos e diagnóstico VVG-puro: [[Refutacao_VVG_Late_Session_2026-05-29]].

## Regra anti-overfit (vinculante)

- **NÃO recalibrar.** Os 5 parâmetros congelados (`multiplicador_volume=1.5`,
  `threshold_gap_pct=0.0015`, `n_dias_baseline=10`, `stop_pontos=472.25`,
  `target_pontos=944.25`) permanecem como estão. Não existe "tentar de
  novo com valores diferentes".
- Qualquer variante (ex.: stop/target via ATR **intradiário** compatível
  com o horizonte de ~80 min do trade, em vez de ATR diário) seria uma
  **nova estratégia** sob Decisão formal — não um conserto desta.
- Tag `caos-frozen-*` nunca foi aplicada e não será.

## Código preservado (inativo)

Os artefatos permanecem versionados como biblioteca/histórico, **fora de
qualquer composição aprovada**:

- `CAOS_Orchestrator/caos/walk_forward/estrategias/vvg_logica.py`
- `CAOS_Orchestrator/caos/walk_forward/estrategias/vvg_classifier.py`
- `CAOS_Orchestrator/caos/walk_forward/estrategias/vvg_late_session_reversal.py`
- `CAOS_Orchestrator/caos/estrategias_modelo/vvg.py`
- `04_CODIGO/ninjascript/EstrategiaVvgLateSessionLogica.cs`
- `04_CODIGO/ninjascript/EstrategiaVvgClassifierLogica.cs`
- `04_CODIGO/ninjascript/StrategyVvgLateSessionReversal.cs`

## Relatório

`05_BACKTEST/walk_forward/relatorios/2026-05-29-04/`
