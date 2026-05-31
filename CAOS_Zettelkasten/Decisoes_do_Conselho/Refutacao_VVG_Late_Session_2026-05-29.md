---
tipo: nota_zettel
area: Decisoes_do_Conselho
titulo: Refutacao da VVG Late-Session Reversal no Walk-Forward longo
data: 2026-05-29
autor: Kiro_Brain
estrategia: EstrategiaVvgLateSessionReversal
status: arquivada
links:
  - "[[Calibracao_VVG_2026-05-29]]"
  - "[[Decisao_2026-05-29-03]]"
  - "[[Decisao_2026-05-29-02]]"
  - "[[Etapa_Zero_NotebookLM_Gemini_2026-05-29]]"
tags:
  - refutacao
  - walk-forward
  - vvg
  - late-session-reversal
  - year-stability
  - fallback-A-acionado
  - mesfin
  - arxiv-2605-11423
---

# Refutacao da VVG Late-Session Reversal no Walk-Forward longo

> Tarefa 11 (CRÍTICA) do spec `caos-vvg-late-session-reversal-mnq`.
> Critérios pré-registrados: R7.3 + emenda [[Decisao_2026-05-29-03]]
> (year-stability). Fallback A acionado **automaticamente** (R7.4 / R9).
> Relatório: `05_BACKTEST/walk_forward/relatorios/2026-05-29-01-vvg-late-session/`.
> Paper-base: arXiv 2605.11423 (Mesfin).

## Contexto

A estratégia **VVG Late-Session Reversal** (CB(SF(VVG))) foi calibrada
UMA vez em janela separada (2025-03-17 a 2025-06-13, file
`01_MNQ_06-25.csv` — ver [[Calibracao_VVG_2026-05-29]]) e os 5
parâmetros foram congelados em código:

| Parâmetro | Valor congelado |
|---|---|
| `multiplicador_volume` | 1.5 |
| `threshold_gap_pct` | 0.0015 |
| `n_dias_baseline` | 10 |
| `stop_pontos` | 472.25 |
| `target_pontos` | 944.25 |

O WF longo de validação rodou sobre a janela **2025-07-01 a 2026-05-15**
(disjunta da calibração — o file `01_MNQ_06-25.csv` foi corretamente
omitido por ter 0 linhas na janela), configuração **60+10 anchored**,
**1 contrato MNQ**, fricção Topstep fixa (slippage 0.25 pt/lado +
comissão USD 0.62/lado).

Composição exata avaliada (R3.3):

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaVvgLateSessionReversal(),
        modo="mediana_diaria", warmup=30, running_median=True),
    diario=-250, semanal=-750, janela=-1000)
```

## Números observados (REAIS — sem ajuste)

WF concluído com **16 janelas** e apenas **9 trades** no total dos
períodos de Teste. Circuit Breaker não descartou nenhum trade (diário=0,
semanal=0, janela=0) — a estratégia simplesmente operou pouquíssimo.

| Critério | Observado | Limiar | Resultado |
|---|---|---|---|
| Sharpe mediana | **2.8305** | >= 1.0 | PASSA |
| Calmar mediana | **16.9941** | >= 1.5 | PASSA |
| PnL total | **-8.08 pts (USD -16.16)** | > 0 | **FALHA** |
| Year-stability | **1/4 trimestres** | >= 3/4 | **FALHA** |

Sanity-check: o PnL recoletado trade-a-trade (recomposição fiel do
fluxo do `BacktestRunner`) bate exatamente com o agregado do Engine
(-8.08 pts, `bate_com_engine=true`).

### Year-stability detalhada (Sharpe por trimestre)

| Trimestre | Sharpe | PnL (pts) | Trades | Dias c/ trade | Positivo? |
|---|---|---|---|---|---|
| 2025-Q3 | — | 0.00 | 0 | 0 | não |
| 2025-Q4 | -5.3435 | -276.85 | 5 | 5 | não |
| 2026-Q1 | — | +60.38 | 1 | 1 | não |
| 2026-Q2 | +12.7999 | +208.39 | 3 | 3 | **sim** |

Apenas **1 dos 4 trimestres** tem Sharpe positivo (2026-Q2). 2025-Q3
não teve nenhum trade; 2026-Q1 teve 1 único trade (Sharpe indefinido —
amostra insuficiente, não conta como positivo); 2025-Q4 foi
francamente negativo (-276.85 pts em 5 trades).

## Por que Sharpe/Calmar medianas "passam" mas a estratégia falha

Este é o ponto metodológico central da refutação e a razão de existir o
critério de **year-stability** (emenda da [[Decisao_2026-05-29-03]]).

A agregação por mediana do Engine considera **apenas janelas com
métrica finita**. Com 9 trades espalhados por 16 janelas, a maioria das
janelas é `sem-trades` (Sharpe/Calmar = `None`, fora da agregação). As
poucas janelas que tiveram trades vencedores produzem Sharpe/Calmar
locais altíssimos (Calmar mediana ~17 é um artefato de amostra mínima),
puxando a mediana para cima. **A mediana entre janelas é cega ao fato de
o PnL agregado ser negativo e à concentração temporal dos ganhos.**

Em outras palavras: Sharpe mediana +2.83 e Calmar +17 são **miragens de
N pequeno** — exatamente a armadilha que o STATE-OF-RESEARCH de
2026-05-29 já havia identificado ("WF longo sozinho NÃO valida
estratégia") e que a emenda da Decisao_2026-05-29-03 antecipou ao exigir
year-stability ≥ 3/4 trimestres. Os dois critérios mais robustos (PnL
total e year-stability) capturaram a refutação que as medianas
mascaravam.

## Conformidade com a previsão do paper

O abstract do paper Mesfin (arXiv 2605.11423) **já admitia** que "all
tested directional trading strategies fail institutional validation
standards after transaction costs and multi-year consistency
requirements are applied". A [[Decisao_2026-05-29-03]] aceitou
implementar mesmo assim, sob critérios mais rigorosos, **reconhecendo
que a estratégia poderia ser refutada — e que isso seria um resultado
aceito**. A refutação aqui é, portanto, **esperada e válida**: o
pipeline funcionou como projetado.

A causa-raiz provável também já estava pré-registrada na
[[Calibracao_VVG_2026-05-29]] (ressalva de risco do Cerberus): com
`stop_pontos=472.25` / `target_pontos=944.25` derivados do ATR(14)
**diário** (range de ~23h) aplicados a um trade de **~80 min**
(14:30→15:50 EST), stop/target são quase decorativos — a maioria das
posições fecha por **encerramento forçado** às 15:50, e o edge de
reversão não se materializa de forma consistente entre trimestres.

## Acionamento do fallback A (descarte automático)

A cláusula da R7.4 / R9.1 é explícita: falha em **qualquer** critério
(aqui falharam DOIS — PnL total e year-stability) dispara fallback A
**sem novo Debate**. Por isso:

1. A estratégia **VVG Late-Session Reversal está ARQUIVADA** em
   2026-05-29. Não avança para R8 (replay NT8). Não há hold-out.
2. **NÃO recalibrar** (regra anti-overfit R10.2). Os 5 parâmetros
   congelados permanecem como estão; não existe "tentar de novo com
   stop/target/multiplicador/threshold diferente". Qualquer variante
   (ex.: ATR intradiário em vez de diário) seria uma **nova estratégia**
   sob Decisão formal, não um conserto desta.
3. **Tag `caos-frozen-*` NÃO é aplicada** (nunca foi — a tag só viria
   após R7 + R8 ambos aprovados).
4. O código Python da estratégia (`vvg_logica.py`, `vvg_classifier.py`,
   `vvg_late_session_reversal.py`) e o espelho C# permanecem versionados
   como biblioteca/histórico, **inativos** em qualquer composição
   aprovada — mesmo tratamento dado à P2 em
   [[Refutacao_P2_Range_Absoluto_2026-05-29]].

## Lição aprendida

A emenda de year-stability provou seu valor logo na primeira aplicação:
**mediana de Sharpe/Calmar entre janelas WF é enganosa quando o número
de trades é baixo e os ganhos são temporalmente concentrados.** Critérios
de consistência temporal (PnL agregado positivo + Sharpe positivo na
maioria dos trimestres) são mais difíceis de satisfazer por acaso e
devem permanecer obrigatórios para qualquer próxima candidata direcional.

Adicionalmente: stop/target dimensionados por ATR de horizonte muito
maior que o horizonte do trade tornam os níveis inertes (a posição morre
por EOD antes de tocá-los). Próximas estratégias intraday de horizonte
curto devem calibrar stop/target em janela compatível com a duração do
trade — mas isso é nota para planejamento, não autorização para
recalibrar esta.

## Arquivos relacionados

- `05_BACKTEST/walk_forward/relatorios/2026-05-29-01-vvg-late-session/resultado.json` (ResultadoWalkForward canônico)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-01-vvg-late-session/avaliacao_criterios.json` (avaliação dos 4 critérios)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-01-vvg-late-session/relatorio.md` (relatório human-readable)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-01-vvg-late-session/manifest_hash.txt`
- `CAOS_Orchestrator/scripts/rodar_wf_vvg_late_session.py` (script desta execução)
- [[Calibracao_VVG_2026-05-29]] (parâmetros congelados + ressalva de risco do Cerberus)
- [[Decisao_2026-05-29-03]] (emendas: year-stability, T >= 2.0, MaxContratos=1 fixo)
