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
> Relatório definitivo: `05_BACKTEST/walk_forward/relatorios/2026-05-29-04/`.
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
(estritamente disjunta da calibração — o file `01_MNQ_06-25.csv` foi
**deliberadamente excluído** da fonte de dados para impedir que os
primeiros cortes de Teste do WF anchored caíssem dentro da janela de
calibração, contaminação circular vetada por R10.2), configuração
**60+10 anchored**, **1 contrato MNQ**, fricção Topstep fixa (slippage
0.25 pt/lado + comissão USD 0.62/lado).

Composição exata avaliada (R3.3):

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaVvgLateSessionReversal(),
        modo="mediana_diaria", warmup=30, running_median=True),
    diario=-250, semanal=-750, janela=-1000)
```

## Números observados (REAIS — sem ajuste)

WF concluído com **18 janelas** e **11 trades** no total dos períodos de
Teste. Foram identificados **30 dias VVG-positivos** na janela. O Circuit
Breaker não descartou nenhum trade (a estratégia simplesmente operou
pouquíssimo, com a maioria das 18 janelas em `sem-trades`).

| Critério | Observado | Limiar | Resultado |
|---|---|---|---|
| Sharpe mediana | **5.5099** | >= 1.0 | PASSA |
| Calmar mediana | **76.4815** | >= 1.5 | PASSA |
| PnL total | **+20.68 pts (USD +41.36)** | > 0 | PASSA |
| Year-stability | **1/4 trimestres** | >= 3/4 | **FALHA** |

A estratégia falha **exclusivamente** no critério de year-stability —
o critério de consistência temporal que a emenda da
[[Decisao_2026-05-29-03]] introduziu justamente para este tipo de caso.
Como a regra R7.4/R9.1 é "falha em **qualquer** critério → fallback A",
**uma única falha basta** para o descarte automático.

### Year-stability detalhada (Sharpe por trimestre)

Composição canônica CB(SF(VVG)):

| Trimestre | Sharpe | PnL (pts) | Trades | Positivo? |
|---|---|---|---|---|
| 2025-Q3 | -4.8022 | -59.85 | 5 | não |
| 2025-Q4 | -4.8854 | -301.84 | 7 | não |
| 2026-Q1 | -5.6966 | -179.60 | 5 | não |
| 2026-Q2 | +12.8820 | +237.52 | 4 | **sim** |

Apenas **1 dos 4 trimestres** (2026-Q2) tem Sharpe positivo. Os três
primeiros trimestres são todos negativos — a estratégia só "fecha no
azul" no WF agregado porque o único trimestre vencedor (2026-Q2,
+237.52 pts) compensa por pouco a soma dos três perdedores. Isso é a
definição operacional de **instabilidade temporal**: o edge não persiste
entre regimes, concentra-se em uma única janela trimestral.

### Diagnóstico — VVG puro (sem overlays SF/CB)

Para isolar o efeito dos overlays, rodei também o plugin VVG puro na
mesma janela:

| Métrica | VVG puro | CB(SF(VVG)) |
|---|---|---|
| Sharpe mediana | 5.8281 | 5.5099 |
| Calmar mediana | 3.6627 | 76.4815 |
| PnL total | **-237.24 pts** | +20.68 pts |
| Trades | 27 | 11 |
| Year-stability | 3/4 | 1/4 |

Observação interessante: o VVG puro tem **PnL total negativo** (-237.24
pts) mas year-stability 3/4; a composição CB(SF(VVG)) tem **PnL positivo**
(+20.68) mas year-stability 1/4. Em ambos os casos a estratégia **falha
pelo menos um critério** → ambos seriam descartados. Os overlays SF/CB
filtram trades (27 → 11) e melhoram o PnL agregado, mas pioram a
distribuição trimestral (concentram o resultado em 2026-Q2). Nenhuma das
duas formas atinge os 4 critérios simultaneamente. A refutação é, portanto,
**robusta à presença dos overlays**.

## Por que Sharpe/Calmar medianas "passam" mas a estratégia falha

Este é o ponto metodológico central da refutação e a razão de existir o
critério de **year-stability** (emenda da [[Decisao_2026-05-29-03]]).

A agregação por mediana do Engine considera **apenas janelas com métrica
finita**. Com 11 trades espalhados por 18 janelas, a maioria das janelas
é `sem-trades` (Sharpe/Calmar = `None`, fora da agregação). As poucas
janelas que tiveram trades vencedores produzem Sharpe/Calmar locais
altíssimos (Calmar mediana ~76 é um artefato de amostra mínima), puxando
a mediana para cima. **A mediana entre janelas é cega à concentração
temporal dos ganhos — não enxerga que 3 dos 4 trimestres são negativos.**

Em outras palavras: Sharpe mediana +5.51 e Calmar +76 são **miragens de
N pequeno** — exatamente a armadilha que o STATE-OF-RESEARCH de
2026-05-29 já havia identificado ("WF longo sozinho NÃO valida
estratégia") e que a emenda da Decisao_2026-05-29-03 antecipou ao exigir
year-stability ≥ 3/4 trimestres. O critério de consistência temporal
capturou a refutação que as medianas mascaravam.

## Conformidade com a previsão do paper

O abstract do paper Mesfin (arXiv 2605.11423) **já admitia** que "all
tested directional trading strategies fail institutional validation
standards after transaction costs and multi-year consistency
requirements are applied". A [[Decisao_2026-05-29-03]] aceitou
implementar mesmo assim, sob critérios mais rigorosos, **reconhecendo
que a estratégia poderia ser refutada — e que isso seria um resultado
aceito**. A refutação aqui é, portanto, **esperada e válida**: o
pipeline funcionou como projetado. O paper falha precisamente em
"multi-year consistency"; nosso year-stability ≥ 3/4 é a versão
operacional desse mesmo critério, e foi exatamente ele que reprovou.

A causa-raiz provável também já estava pré-registrada na
[[Calibracao_VVG_2026-05-29]] (ressalva de risco do Cerberus): com
`stop_pontos=472.25` / `target_pontos=944.25` derivados do ATR(14)
**diário** (range de ~23h) aplicados a um trade de **~80 min**
(14:30→15:50 EST), stop/target são quase decorativos — a maioria das
posições fecha por **encerramento forçado** às 15:50, e o edge de
reversão não se materializa de forma consistente entre trimestres.

## Acionamento do fallback A (descarte automático)

A cláusula da R7.4 / R9.1 é explícita: falha em **qualquer** critério
(aqui falhou o year-stability) dispara fallback A **sem novo Debate**.
Por isso:

1. A estratégia **VVG Late-Session Reversal está ARQUIVADA** em
   2026-05-29 (`02_ESTRATEGIAS/mortas/VVG_Late_Session_Reversal.md`). Não
   avança para R8 (replay NT8). Não há hold-out.
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

> Nota de auditoria: uma execução exploratória anterior
> (`2026-05-29-01`, 16 janelas) chegou ao **mesmo veredito** (fallback A)
> falhando year-stability (1/4) e PnL (-8.08 pts). A execução definitiva
> registrada aqui (`2026-05-29-04`, 18 janelas) usa a fonte de dados com
> a janela de calibração estritamente excluída e confirma o descarte. O
> veredito é robusto à versão de windowing: **year-stability < 3/4 em
> ambas**.

## Lição aprendida

A emenda de year-stability provou seu valor: **mediana de Sharpe/Calmar
entre janelas WF é enganosa quando o número de trades é baixo e os ganhos
são temporalmente concentrados.** Aqui, PnL total e Sharpe/Calmar medianas
estavam TODOS no verde — e mesmo assim a estratégia é inválida porque 3
dos 4 trimestres são negativos. Critérios de consistência temporal são
mais difíceis de satisfazer por acaso e devem permanecer obrigatórios
para qualquer próxima candidata direcional.

Adicionalmente: stop/target dimensionados por ATR de horizonte muito
maior que o horizonte do trade tornam os níveis inertes (a posição morre
por EOD antes de tocá-los). Próximas estratégias intraday de horizonte
curto devem calibrar stop/target em janela compatível com a duração do
trade — mas isso é nota para planejamento, não autorização para
recalibrar esta.

## Arquivos relacionados

- `05_BACKTEST/walk_forward/relatorios/2026-05-29-04/resultado.json` (ResultadoWalkForward canônico)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-04/criterios.json` (avaliação dos 4 critérios + diagnóstico VVG puro)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-04/relatorio.md` (relatório human-readable)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-04/manifest_hash.txt`
- `CAOS_Orchestrator/scripts/rodar_wf_vvg_late_session.py` (script desta execução)
- `02_ESTRATEGIAS/mortas/VVG_Late_Session_Reversal.md` (nota de arquivamento)
- [[Calibracao_VVG_2026-05-29]] (parâmetros congelados + ressalva de risco do Cerberus)
- [[Decisao_2026-05-29-03]] (emendas: year-stability, T >= 2.0, MaxContratos=1 fixo)
