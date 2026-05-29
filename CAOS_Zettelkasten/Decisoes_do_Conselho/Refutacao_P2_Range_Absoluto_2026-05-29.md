---
tipo: nota_zettel
area: Decisoes_do_Conselho
titulo: Refutacao da P2 (range_absoluto) na fase de calibracao
data: 2026-05-29
autor: Kiro_Brain
links:
  - "[[Decisao_2026-05-29-01_Descarte_Reengenharia]]"
  - "[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]"
tags:
  - refutacao
  - non-stationarity
  - P2-falha
  - fallback-A-acionado
---

# Refutacao da P2 (range_absoluto) na fase de calibracao

## Contexto

A Decisao `2026-05-29-01` aprovou caminho B (re-engenharia minima
P2 do Manolo: substituir filtro NR7 por filtro `range_absoluto`
com K=80 ticks congelado em codigo) **com clausula de fallback
automatico para A (descarte)** caso P2 falhe pelos criterios
quantitativos pre-registrados.

Implementei a P2 em `caos/walk_forward/estrategias/orb_crabel.py`
(commits ainda nao enviados, ver abaixo) e tentei calibrar K em
janela 2025-01-01 a 2025-06-30 separada do WF original
(2025-07-01 a 2026-05-15).

## Achados que refutam P2

### 1. K=80 ticks proposto pelo Manolo era cego aos dados reais

Range medio do MNQ minute em 2025-03-17 a 2025-06-14 = **540 pontos
= 2.160 ticks** por dia. Range minimo do periodo = **162 pontos =
647 ticks**. K=80 ticks (= 20 pontos) gera **0 dias elegiveis** —
threshold ordens de grandeza abaixo dos ranges reais.

Manolo propos 80 ticks por intuicao de "compressao" sem verificar
o dataset. Erro de calibracao mental, nao bug de logica.

### 2. Volatilidade do MNQ NAO eh estacionaria na janela de calibracao

Janela de calibracao foi dividida em duas metades de 6 semanas:

| Periodo | N dias uteis | P10 (ticks) | P17 (ticks) | P25 (ticks) |
|---|---|---|---|---|
| 2025-03-17 a 2025-04-30 | 32 | 1352 | 1487 | 1521 |
| 2025-05-01 a 2025-06-14 | 32 | 788 | 947 | 1043 |

Variacao de **~37% no P17** entre as duas metades. Qualquer K
fixo calibrado na primeira metade vai produzir elegibilidade
**totalmente diferente** na segunda — viola o invariante implicito
da P2 ("filtro absoluto de range eh estavel ao longo do tempo").

### 3. Filtro absoluto = filtro de regime, nao de compressao

A intuicao da Crabel original (NR7) eh **relativa** ("este dia
tem o menor range dos 7 dias anteriores"). Isso captura
**compressao** independentemente do nivel de volatilidade do
mercado. Um filtro absoluto K capta **regime de baixa volatilidade
absoluta** — coisa diferente. Em 2025-03/04 (alta vol), nenhum
dia atinge K baixo; em 2025-05/06 (vol caindo), todos os dias
atingem K alto. O filtro nao discrimina nada — seleciona em
funcao do regime macro, nao da compressao local.

### 4. Criterio Cerberus pre-registrado nao alcancavel

A Decisao exigia:
- Sharpe mediana >= 1.0 em WF 60+10 anchored sobre 2025-07 a 2026-05;
- PnL >= -USD 100 em replay 2026-06+ sobre 30 dias uteis;
- Paridade Python<->C# trade-a-trade dentro de 5%.

Sem K que satisfaca os 3, nao adianta seguir adiante. A nao-estacionariedade
demonstra que o criterio (3) — paridade — eh trivialmente satisfeito
(filtro absoluto eh trivialmente Python<->C# equivalente), mas
criterio (1) Sharpe nao tem como ser robustamente reproduzivel
porque o filtro vai operar em regime totalmente diferente entre
treino, validacao e replay.

## Acionamento do fallback A (descarte automatico)

A clausula da Decisao `2026-05-29-01` eh explicita:

> "Falha em qualquer criterio acima ativa fallback A: arquivar
> estrategia em 02_ESTRATEGIAS/mortas/ com nota Zettel registrando
> o caminho completo (P2 testada e refutada)."

A P2 falhou na **fase de calibracao**, antes de gerar codigo C# ou
WF longo. **Fallback A acionado**: estrategia
`EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7), ...))`
(da `[[Decisao_2026-05-25-02]]`) eh definitivamente arquivada em
`02_ESTRATEGIAS/mortas/`. Tag `caos-frozen-2026-05-25-02` permanece
SUSPENSA permanentemente.

## Implementacao Python preservada

O codigo do `range_absoluto` em `orb_crabel.py` permanece como
parte da biblioteca de filtros disponiveis (com 10 testes
unitarios que provam comportamento correto), mas **nao esta
ativo** em nenhuma estrategia aprovada.

Isto nao eh inconsistencia: P2 tinha logica de filtro
**implementavel** e **testavel**, ela falha **na escolha do K**
e no pressuposto implicito de **estacionariedade**. Outra estrategia
futura pode reusar o filtro com K calibrado de outra forma (ex:
ATR-relativo, percentil rolante) sem precisar reimplementar.

## Licao aprendida

Threshold absoluto sobre serie nao-estacionaria nao eh estrategia
robusta. Crabel usou janela movel (NR7) precisamente porque o
mercado muda de regime. Substituir uma especificacao **relativa**
(NR7) por uma **absoluta** (K fixo) ganha simplicidade Python<->C#
mas perde robustez ao regime — overfit por simplificacao.

Para o proximo Spec/estrategia: se quiser eliminar dependencia de
janela em C#, considerar:

1. **Filtro percentil rolante** (ex: dia D-1 esta no decil mais
   baixo dos ultimos 30 dias): mantem invariancia a regime, mas
   precisa de janela como NR7. Volta a estaca zero.
2. **Filtro ATR-normalizado** (range[D-1] / ATR(20)[D-1] <= 0.5):
   janela viva, mas filtra **compressao relativa** ao ATR. Talvez
   menos sensivel a contrato Continuum.
3. **Filtro de regime macro** (VIX equivalente <= percentil 30):
   externa ao MNQ, requer dado adicional, talvez mais robusto.

Nenhum desses esta no escopo desta Decisao. Sao notas para o
proximo planejamento.

## Proxima acao

Executar fallback A no codigo:

1. Mover `02_ESTRATEGIAS/ressuscitavel/morta_ressuscitavel_head_02_orb.md` (no Hydra reference) — **NAO**, eh read-only.
2. Estrategia ativa esta no codigo `04_CODIGO/ninjascript/Strategy*.cs` + plugins Python. Marcar como arquivada via:
   - Atualizar `_index.md` em `CAOS_Zettelkasten/Estrategias/` (se existir) com status `arquivada-2026-05-29`.
   - Atualizar `STATE-OF-RESEARCH-2026-05-29.md` com fallback A consumado.
3. Tag `caos-frozen-2026-05-25-02` permanece SUSPENSA. Pipeline aguarda paper R12-aprovado independente.

## Codigo Python permanece

Os arquivos editados (NAO commitados ainda):

- `caos/walk_forward/estrategias/orb_crabel.py` — adiciona modo
  `range_absoluto` com K=80 ticks (errado por nao verificar dados).
- `tests/unit/test_orb_crabel.py` — 10 novos testes do
  `range_absoluto` (todos passam, validam logica de filtro).
- `scripts/calibrar_range_absoluto_2026-05-29.py` — script que
  refutou empiricamente a P2.

Estes commits ficam em branch separada ou commit unico marcado
"refutacao-P2", sem ativar o filtro em nenhuma estrategia.
