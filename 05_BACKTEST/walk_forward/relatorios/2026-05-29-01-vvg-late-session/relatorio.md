# Walk-Forward de Validação — VVG Late-Session Reversal (2026-05-29-01)

> Tarefa 11 (CRÍTICA) do spec `caos-vvg-late-session-reversal-mnq`.
> Critérios pré-registrados: R7.3 + emenda `Decisao_2026-05-29-03`.

## Configuração

| Campo | Valor |
|---|---|
| Composição | `EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaVvgLateSessionReversal(), mediana_diaria, warmup=30), diario=-250, semanal=-750, janela=-1000)` |
| Janela WF | 2025-07-01T00:00:00+00:00 a 2026-05-15T23:59:59+00:00 |
| Configuração | 60+10 anchored |
| Contratos | 1 |
| Fricção | topstep_mnq (0.25 pt/lado slippage + USD 0.62/lado comissao) |
| Status WF | concluido |
| Janelas | 16 |
| Trades (total) | 9 |
| Manifesto (SHA-256) | 774891fce7c10be6c6a3ca66779886143f433a384a08b34bd43cedaa8a216b00 |

## Critérios pré-registrados

| Critério | Observado | Limiar | Resultado |
|---|---|---|---|
| Sharpe mediana | 2.8305 | >= 1.0 | PASSA |
| Calmar mediana | 16.9941 | >= 1.5 | PASSA |
| PnL total (pontos) | -8.0800 | > 0 | FALHA |
| Year-stability | 1/4 | >= 3/4 | FALHA |

PnL total em USD (1 contrato MNQ): **-16.16**

## Year-stability (Sharpe por trimestre)

| Trimestre | Sharpe | PnL (pontos) | Trades | Dias c/ trade | Positivo? |
|---|---|---|---|---|---|
| 2025-Q3 | — | 0.0000 | 0 | 0 | não |
| 2025-Q4 | -5.3435 | -276.8500 | 5 | 5 | não |
| 2026-Q1 | — | 60.3800 | 1 | 1 | não |
| 2026-Q2 | 12.7999 | 208.3900 | 3 | 3 | sim |

## Veredito

**REFUTADA** — fallback A automatico (arquivada, sem novo Debate).

Fallback A (R9) automático: estratégia arquivada sem novo Debate. Regra anti-overfit (R10.2): NÃO recalibrar parâmetros. O próprio paper Mesfin admite falha em year-stability — refutação é resultado VÁLIDO e esperado do pipeline.
