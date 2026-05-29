---
area: Decisoes_do_Conselho
data_criacao: '2026-05-28T20:30:00Z'
identificador: 2026-05-28-01
status: concluido
tags:
- bug-fix
- paridade-python-csharp
- warmup-nr7
- bars-required-to-trade
- gemini-validacao
- decisao-do-conselho
titulo: Bug de paridade Python↔C# por reset de estado em troca de contrato
---

# Bug de paridade NR7 por reset de estado no NT8

> Decisão `2026-05-28-01` — Conselho-no-Chat (Spec 5).
> Gatilhos: G1 (modifica `*Logica.cs`/`Strategy_CAOS`) + G5 (regressão na
> Decisão `[[Decisao_2026-05-25-02]]`).
> Commit do CouncilRecorder: `95fb9b3`.

## Resumo executivo

Replay completo do NT8 sobre `MNQ 03-26 + 06-26` (28/01-26/05/2026, 105 dias)
produziu **11 trades com PnL -USD 573.50** (1 contrato). Walk-Forward Python
sobre o mesmo dataset projeta +USD 1100/ano com Sharpe +9.07. Discrepância
de **USD 8.000/ano** entre simulação Python e replay NT8.

Auditoria revelou: **5 de 11 trades (45%) foram disparados em dias que o
filtro NR7 do Python NÃO consideraria elegíveis**.

## Causa raiz

O `EstadoCrabelNR7` é reinstanciado em `State.DataLoaded`. Quando NT8
troca de contrato em playback (ex: `MNQ 03-26 → 06-26`) ou recarrega
estratégia (F5, restart), a instância da `Strategy_CAOS` é **destruída e
recriada**. `RangePorDia` zera. Após o reset, o filtro NR7 entra em
"warmup espúrio": com 1-7 dias no histórico, **qualquer dia parece NR7**
(estatística degenerada).

Confirmação Gemini Pro (resposta 2026-05-28): NT8 destrói a instância
em troca manual de contrato; Continuum auto-rollover não destrói.

Evidência no log de diagnóstico:

| Dia | dias_no_historico | trade entrou? |
|---|---|---|
| 02-23 | 21 | SIM |
| **03-11** | **1** | **SIM** ← reset entre 02-23 e 03-11 |
| 03-25 | 11 | SIM |

## Decisão (P1 — versão revisada após Gemini)

**Implementação refinada conforme prática de mercado NinjaScript:**

### Antes (P1 original, ABANDONADA)

Hidratar `RangePorDia` iterando `Bars[]` em `State.DataLoaded`.

❌ **Inviável**: NT8 não permite acesso a `Bars[i]` em `State.DataLoaded`
— a engine ainda não injetou os dados. Tentar isso causa out-of-bounds
ou estado inconsistente.

### Depois (P1 revisada, IMPLEMENTADA)

**Warmup passivo via `BarsRequiredToTrade`**:

1. **Em `State.SetDefaults`**: setar `BarsRequiredToTrade = 19320`
   (14 dias úteis × 1380 barras de minuto = warmup obrigatório).
2. **Em `OnBarUpdate`**: manter ordem atual (atualizar filtro NR7
   ANTES de qualquer guard). NT8 nativamente bloqueia `EnterLong/Short`
   enquanto `CurrentBar < BarsRequiredToTrade`.
3. **No chart NT8**: usuário deve configurar **Data Series → Dias para
   carregar ≥ 44** (14 warmup + 30 teste mínimos).

### Como funciona

- A cada barra (histórica ou realtime), `AtualizarFiltro` é chamada e
  popula `RangePorDia` silenciosamente.
- Até `CurrentBar = 19320`, NT8 bloqueia ordens nativamente.
- Após o warmup, filtro NR7 já tem 14 dias completos no histórico —
  decisões saem com paridade contra o Python.
- Em qualquer reset (troca de contrato, reload), o ciclo recomeça:
  o NT8 carrega `Days to load` barras históricas, alimenta `OnBarUpdate`
  silenciosamente, hidrata o filtro, e só aceita ordens após 14 dias úteis.

## Veto_De_Risco condicional do Cerberus

Tag `caos-frozen-2026-05-25-02` **SUSPENSA de hold-out** até:

1. Re-replay completo dos 105 dias (28/01-26/05) com C# corrigido
2. Comparação trade-a-trade Python ↔ C# corrigido (paridade ≥ 90%)
3. PnL do replay corrigido **≥ -USD 100** em 105 dias

Se PnL pós-fix continuar < -USD 500, **descarte da estratégia** é
obrigatório (estratégia sem edge real, não apenas bug de implementação).

## Crítica do Devils_Advocate (não ignorar)

Mesmo com fix:
- Win rate observado: **36.4%** (4/11 wins)
- Razão MFE/MAE média: **0.74** (assimétrica desfavorável)
- 7 dos 11 trades foram SHORT, todos com hit rate baixo

**Hipótese alternativa**: a estratégia **não tem edge real**. O Sharpe +9
do WF Python pode ter sido artefato de amostra pequena (1-3 trades por
janela de 60d) e o filtro NR7 reduzido pós-fix do bug de domingo.

**Antídoto**: re-replay obrigatório vai responder. Se PnL pós-fix
continuar negativo, abrir Debate de descarte.

## Implementação aplicada

Arquivos modificados:

- `04_CODIGO/ninjascript/Strategy.cs`: `BarsRequiredToTrade = 19320` em
  `State.SetDefaults`.
- `.kiro/steering/ninjascript-api.md`: whitelist atualizada com
  `BarsRequiredToTrade`.
- `04_CODIGO/ninjascript/README_INSTALACAO_HOLDOUT.md`: novo Passo 3.5
  (configurar Dias para carregar ≥ 44).

Sandbox NT8 sincronizada via `sincronizar.bat repo-para-caos`.

## Próximo passo (obrigatório)

1. Recompilar NT8 (F5 em Edit NinjaScript).
2. **Configurar Data Series → Dias para carregar = 44** no chart.
3. Re-rodar replay 28/01-26/05/2026 (mesmos 105 dias).
4. Comparar resultado:
   - Se PnL ≥ -USD 100: estratégia mantida, hold-out retomado.
   - Se PnL ainda < -USD 500: abrir Debate de descarte.

## Fontes externas

Resposta Gemini Pro (`e:\CAOS\Resposta Gemini`, 28/05/2026 21:00):

> "Esse é um erro clássico (e doloroso) de arquitetura orientada a
> eventos. O que aconteceu foi que o NT8 reiniciou a instância da sua
> estratégia, zerou as variáveis em memória e a estratégia começou a
> operar 'cega', achando que já tinha dados suficientes para calcular
> o NR7."
>
> "BarsRequiredToTrade é uma propriedade nativa do NT8. A engine do NT8
> bloqueia nativamente qualquer chamada aos métodos de ordem (como
> EnterLong()) se CurrentBar < BarsRequiredToTrade."
>
> "Configure no gráfico do NT8 Days to load para cobrir o seu período
> de teste mais a janela de warmup. O NT8 processa barras históricas
> a velocidades altíssimas. Reconstruir 14 dias de barras de 1 minuto
> em C# puro leva milissegundos."

Validação cruzada: Hermes (no Debate) e Gemini Pro (independentemente)
confirmaram que o padrão correto é warmup passivo via `OnBarUpdate`
+ `BarsRequiredToTrade`, NÃO iteração explícita em `State.DataLoaded`.

## Links

- `[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]` — Decisão original (suspensa)
- `[[Bug_NR7_Aceita_Domingos_2026-05-26]]` — bug fix anterior (filtro de domingos)
- `[[Replay_Final_Limpo_2026-05-28]]` — replay com 11 trades sob bug
- `[[WF_Validacao_Longa_2026-05-27]]` — WF longo (sem bug)
- `CAOS_Council/debates/2026-05-28-01-bug-paridade-warmup-nr7-csharp.md`
- `CAOS_Council/decisions/2026-05-28-01-bug-paridade-warmup-nr7-csharp.md`
- `e:\CAOS\Resposta Gemini` — resposta integral do Gemini Pro
- `scripts/auditar_paridade_nr7_2026-05-28.py` — auditoria que revelou o bug
- `scripts/analisar_log_diagnostico_28-05.py` — extração do estado interno C#
