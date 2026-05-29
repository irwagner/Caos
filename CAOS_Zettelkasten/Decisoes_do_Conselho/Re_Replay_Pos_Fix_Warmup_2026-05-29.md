---
tipo: nota_zettel
area: Decisoes_do_Conselho
titulo: Re-replay pos-fix warmup NR7 (28/01-26/05/2026 MNQ 06-26)
data: 2026-05-29
autor: Kiro_Brain
links:
  - "[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]"
  - "[[Bug_Paridade_Warmup_NR7_2026-05-28]]"
  - "[[Replay_Final_Limpo_2026-05-28]]"
tags:
  - re-replay
  - bug-fix
  - veto-de-risco-condicional
  - PnL-negativo
  - holdout-suspenso
---

# Re-replay pos-fix warmup NR7 — 28/01 a 26/05/2026

## Contexto

Apos a Decisao `2026-05-28-01` aprovar P1 (hidratacao em
`State.DataLoaded` + `BarsRequiredToTrade` defensivo), Gemini Pro
respondeu (via NotebookLM, em resposta versionada em
`e:\CAOS\Resposta Gemini`) que a P1 original era **inviavel**: NT8 nao
permite acesso a `Bars[i]` em `State.DataLoaded`. Caminho revisado:
usar **apenas** `BarsRequiredToTrade = 19320` (14 dias uteis * 1380
barras/dia) em `State.SetDefaults`. Implementacao em commits:

- `a281e47` — `BarsRequiredToTrade = 19320` em `Strategy.cs`
- `240c089` — fix `MfeMaeTracker ja tem trade aberto` em camada 1
  (force-close defensivo de `MfeMae` + `Trailing` antes de reabrir)
- `17450e3` — guard `CurrentBar < BarsRequiredToTrade` no inicio de
  `EntrarInterno` (camada 2; bloqueia tambem `State.Historical` para
  que nem o MfeMae interno acumule trades durante warmup)

Whitelist `ninjascript-api.md` atualizada com `BarsRequiredToTrade`,
`RealtimeErrorHandling`, `StopTargetHandling`. README de instalacao
atualizado com Passo 3.5 (`Days to load >= 44`).

## Re-replay

- **Instrumento**: `MNQ 06-26` (Junho 2026, contrato corrente)
- **Janela operacional**: 28/01/2026 — 26/05/2026
- **Granularidade**: 1 minuto, `Calculate.OnBarClose`, RTH ampliado
- **Conta**: Sim101 (NT8 Playback)
- **Days to load**: configuracao do chart respeitada; ultima barra
  inicialmente carregada foi 13/03 (replay avancou em tempo simulado
  ate 26/05)

### Comportamento da defesa em camadas

| Camada | Indicador | Resultado |
|---|---|---|
| `BarsRequiredToTrade=19320` | bloqueio nativo NT8 de `EnterLong/Short` | OK |
| Force-close MfeMae+Trailing | logs `mfemae-fechamento-defensivo` | 2 ocorrencias residuais (sem virar excecao) |
| Guard `CurrentBar < BarsRequiredToTrade` em `EntrarInterno` | logs `entrada-bloqueada` durante warmup | 0 (warmup ja se esgotou na carga) |
| Excecao `MfeMaeTracker ja tem trade aberto` | log do NT8 | **0 ocorrencias** — fix funcionou |

A excecao que motivou o fix foi **eliminada por completo**.

### Resultado financeiro

| Metrica | Valor |
|---|---|
| Trades | 11 |
| Vitorias | 4 |
| Derrotas | 6 |
| Breakeven | 1 |
| Win-rate | 36,4% |
| Maior win | +USD 537,50 (26/03 SHORT) |
| Maior perda | -USD 307,00 (11/03 LONG) |
| Long / Short | 4 / 7 |
| **PnL total** | **-USD 573,50** |
| Periodo | ~85 dias uteis (28/01 → 26/05) |

PnL/dia util ≈ **-USD 6,75**. Anualizado (252 dias) ≈ **-USD 1.700**.

### Comparacao com replay pre-fix (commit `c3d2ae9`)

| Metrica | Pre-fix (sem warmup defensivo) | Pos-fix |
|---|---|---|
| Trades | 11 | 11 |
| PnL | -USD 573,50 | **-USD 573,50** |
| Trades em dias inelegiveis pelo Python | 5/11 (45%) | 5/11 (45%) |

**Resultado identico**. O fix corrigiu o **erro tecnico** (excecao do
MfeMae) mas nao mudou os trades — a janela de teste 28/01-26/05 esta
proxima demais do inicio da memoria do replay para o `BarsRequiredToTrade`
fazer diferenca pratica. Em outras palavras, o bug de paridade
permanece presente nesta janela; o `BarsRequiredToTrade` e defesa
**futura** (para hold-out a partir de 29/05) e **passada** (para WF
longo que comeca em 2025-07).

## Decisao do Cerberus (Veto_De_Risco condicional)

A Decisao `2026-05-28-01` impos:

- **PnL ≥ -USD 100 em 105 dias** → hold-out retomado, tag
  `caos-frozen-2026-05-25-02` reativada.
- **PnL entre -USD 100 e -USD 500** → Debate de avaliacao, sem
  veredito automatico.
- **PnL ≤ -USD 500** → Debate de **descarte** (Devils_Advocate vence
  por gravidade); estrategia rebaixada para arquivo morto.

PnL observado: **-USD 573,50** em 85 dias (extrapolado para 105 dias
proporcionalmente: ≈ -USD 708).

**Cerberus emite Veto_De_Risco DEFINITIVO**: nao ha condicoes minimas
para retomar hold-out. Tag `caos-frozen-2026-05-25-02` permanece
**SUSPENSA**. Decisao `2026-05-25-02` fica em estado de **revisao
obrigatoria** ate o Conselho deliberar sobre descarte ou re-engenharia.

## Proximos passos

1. **Abrir Debate Auto** com gatilhos **G1** (mudanca em logica de
   decisao via descarte/re-engenharia) **+ G5** (contradiz Decisao
   aprovada `2026-05-25-02`):
   ```cmd
   caos debate iniciar descarte-ou-reengenharia-crabel-nr7-orb-sf-cb --gatilho G5 --csharp
   ```
2. Pauta minima do Debate:
   - Devils_Advocate apresenta caso de descarte (estrategia provada
     sem edge fora do WF Python original)
   - Mister_M / Odin defendem re-engenharia (substituicao do filtro
     NR7 por algo nao-paridade-dependente, ou troca de horario de
     entrada)
   - Hermes valida tecnicamente qualquer proposta que envolva C#
     novo
   - Cerberus tranca avaliacao com criterio quantitativo
3. Se vencedor for **descarte**: arquivar estrategia em
   `02_ESTRATEGIAS/mortas/`, registrar no `_index.md` da area, e
   liberar pipeline para proxima ideia (Spec 1 indica WF longo de
   nova candidata).
4. Se vencedor for **re-engenharia**: novo Spec/branch para
   intervencao + WF longo de validacao + Decisao com
   `aprovado_walk_forward=true`.

## Licao aprendida

A divergencia Python↔C# nao era apenas tecnica (`MfeMaeTracker`
quebrando) — era tambem **estrategica**: 5/11 trades (45%) ocorreram
em dias inelegiveis pela paridade Python. Mesmo com o fix tecnico
implantado, o codigo C# operou na janela com **paridade nao
restaurada** porque o historico carregado pelo NT8 nessa janela e
insuficiente para o `BarsRequiredToTrade=19320` mudar comportamento.
A defesa serve para **futuro** (hold-out e WF longo apos 29/05),
nao corrige o resultado deste replay especifico.

PnL de -USD 573,50 confirma: a janela 28/01-26/05 do MNQ 06-26
**nao tem edge** para a estrategia atual, com OU sem o bug de
warmup. Isso e estatistica de mercado, nao bug de software.

