---
agentes_participantes:
- Athena
- Devils_Advocate
- Explorador
- Hermes
contexto_hash_sha256: fc2b79e75379752f88a7d961615b16976cae0ea302136a1d73d89aaede68bb82
data_fim: '2026-05-29T16:10:00Z'
data_inicio: '2026-05-29T15:51:26Z'
fase_final: SINTESE
identificador: 2026-05-29-02
modelos:
  Athena: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Explorador: claude-opus-4.7
  Hermes: claude-opus-4.7
notas_injetadas:
- gatilho:G4
- aberto_por:auto
- altera_exposicao:false
- requer_csharp:false
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Devils_Advocate: 42
  Explorador: 42
  Hermes: 42
status: concluido
titulo: triagem-shopping-list-papers-mnq
turnos_consumidos: 5
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T15:51:26Z'
```

### Tema

Após o **fallback A da Decisão `2026-05-29-01`** acionado pela
`[[Refutacao_P2_Range_Absoluto_2026-05-29]]`, o pipeline está
**ocioso**. A `shopping-list-fontes-notebooklm-2026-05-25.md` lista
10 papers TL;DR como candidatos para nova estratégia, mas **nenhum
foi triado formalmente** contra o filtro R12 (Spec 1):

- Sharpe ≥ 1 documentado fora de amostra
- Sample ≥ 200 trades
- Out-of-sample ≥ 30 observações
- Instrumento batendo (MNQ ou equivalente)
- Survivorship bias tratado

A lição da `[[Refutacao_P2_Range_Absoluto_2026-05-29]]` adiciona
critérios complementares (mas não substitutos) ao R12:

- Estacionariedade da série não pode ser pressuposto implícito
- Hold-out **temporal** real é obrigatório (não janelas WF rolantes
  contaminadas pela calibração)
- Critério de descarte deve ser pré-registrado com IC95% que NÃO
  cruze zero para o N esperado

### Objetivo

Triagem dos **10 papers do TL;DR** + emergentes da pesquisa rápida
de hoje. Saída: 1-3 candidatos prontos para virar Spec próprio.

### Agentes convocados

- **Explorador**: aplica filtros R12 paper a paper, propõe shortlist
  (proponente único nesta triagem; sem necessidade de round-robin
  — não há propostas competitivas de estratégia ainda, o que está
  em jogo é seleção de candidato). Para satisfazer R4.3 (≥ 2
  propostas) o Explorador ENTREGA 2 shortlists alternativas.
- **Cerberus**: avalia exposição esperada de cada candidato.
- **Hermes**: avalia viabilidade técnica em NinjaScript 8.
- **Devils_Advocate**: ataca cada shortlist — viés de publicação,
  replicabilidade, regime change pós-2024.

Como esta triagem **não propõe estratégia operável** (apenas
shortlist), `altera_exposicao=false`. Como pode levar a Spec novo
em C#, marco G4 (Explorador encontrou paper relevante) sem flag
`--csharp` (a flag é do Spec futuro, não desta triagem).

Avanço para fase **PROPOSTAS**.


## Turno 2 — Explorador (PROPOSTAS)

```meta
agente: Explorador
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T15:55:00Z'
```

### Triagem R12 paper a paper (TL;DR shopping-list)

Aplicando os 5 filtros R12 + 3 critérios complementares da
`[[Refutacao_P2_Range_Absoluto_2026-05-29]]`:

| # | Paper | R12.1 Sharpe ≥ 1 | R12.2 Sample ≥ 200 | R12.3 OOS ≥ 30 | R12.4 Instrumento | R12.5 Survivorship | Estacionariedade | Avaliação |
|---|---|---|---|---|---|---|---|---|
| 1 | arXiv 2605.04004 (Structural Limits MNQ) | NEGATIVO (paper prova edge nao existe) | sim (~944 dias) | sim | **MNQ direto** | n/a | n/a | **rejeitar como candidato; aceitar como BENCHMARK** |
| 2 | SSRN 4824172 (Beat the Market SPY) | sim (1.33) | sim (4292 dias) | sim | **SPY**, nao MNQ; intuicao adaptavel | sim (ETF) | parcial (regime 2007-2024) | **ACEITAR como candidato adaptado** |
| 3 | SSRN 3134546 (Disappearing Pre-FOMC) | NEGATIVO (paper documenta colapso) | sim | sim | SPX, nao MNQ direto | sim | n/a | **rejeitar; usar como benchmark** |
| 4 | SSRN 5233918 (Magnitudes FOMC) | n/a (survey) | n/a | n/a | SPX | sim | n/a | **rejeitar (survey, nao estrategia)** |
| 5 | ResearchGate 385968274 (Disappearing TOM) | NEGATIVO | sim | sim | SP500/futuros | sim | viola | **rejeitar; ja sabemos pelo WF interno** |
| 6 | Harbourfront Quant (Calendar replication) | parcial (algumas funcionam) | parcial | parcial | SPX | parcial | viola | **rejeitar (calendar replicado, sem edge novo MNQ)** |
| 7 | arXiv 2508.06788 (OFI in S&P E-mini) | NEGATIVO (OFI agregado nao prediz) | sim | sim | ES (proximo a MNQ) | n/a | parcial | **rejeitar; ja refutamos OFI no CAOS** |
| 8 | SSRN 3760365 (Hedging Demand intraday momentum) | sim (~1.0+) | sim (~5800 dias) | sim | SP500, mas universal | sim | sim (replicado em China SSE 50) | **ACEITAR como candidato** |
| 9 | SSRN 4692190 (0DTEs Gamma) | n/a (mecanismo, nao estrategia) | sim | sim | SP500 | sim | parcial | **rejeitar como estrategia direta; aceitar como REGIME FILTER** |
| 10 | Quantitativo (Intraday Momentum ES/NQ) | sim (replicado +1.5) | sim | sim | **ES e NQ — bate com MNQ** | sim | parcial | **ACEITAR como candidato** |

### Candidatos emergentes da pesquisa de hoje

| Paper | Origem | Avaliação |
|---|---|---|
| arXiv 2605.11423 (Volatility-Volume-Gap Classifier MNQ) | descoberto hoje | **MNQ direto, 947 dias 2021-2025, classifier de regime + late-session reversal** — candidato forte |
| arXiv 2605.17724 (Sequential Structure Intraday Futures) | descoberto hoje | dataset MNQ; menos direcionavel a estrategia operavel |

### Proposta P1 — Shortlist conservadora (1 candidato MNQ-nativo)

**Foco em arXiv 2605.11423 (Volatility-Volume-Gap Classifier MNQ)**.

Por que:
- Único paper especifico do MNQ (ou ES) com edge **positivo** documentado.
- Janela 2021-2025 cobre regime atual (pos-COVID, pos-0DTE explosion).
- Classifier de regime (volume + gap) pode ser implementado em
  Python sem book depth (so OHLCV).
- "Late-session reversal" descoberto e proximo da hipotese de
  Hedging Demand (SSRN 3760365), ou seja, **dois papers convergem**
  em conclusao similar.

Plano:
1. Baixar paper completo, extrair regras do classifier exatas.
2. Implementar classifier em `caos/walk_forward/estrategias/` como
   plugin novo `VolatilityVolumeGapClassifier`.
3. Implementar estrategia operavel: late-session reversal trade
   condicional ao classifier.
4. WF longo 2025-07 a 2026-05 (igual o WF da estrategia descartada)
   para comparacao direta.
5. Hold-out **temporal** em 2026-06+ (sem WF prévio nesse periodo).

### Proposta P2 — Shortlist combinada (2 candidatos)

**Foco em P1 + adaptacao MNQ do Beat the Market (SSRN 4824172)**.

Por que adicionar Beat the Market:
- Sharpe 1.33 documentado em SPY 2007-2024.
- Improvements em SSRN 5095349 (Maroy 2025) testam variantes
  recentes.
- Apesar de SPY (ETF, nao futuro), a logica de "noise boundary"
  (banda dinamica de volatility) eh trivialmente adaptavel para MNQ.
- Permite **dois candidatos paralelos** — se um falhar no WF longo,
  ainda temos o outro.

Plano:
1. Implementar P1 conforme acima.
2. Implementar Beat the Market adaptado: replicar logica de banda
  ATR + breakout em MNQ, comparar com WF da estrategia descartada.
3. Selecionar o **melhor dos dois** apos WF longo.

### Riscos comuns às propostas

- **Vies de publicacao**: ambos os papers usam dados ate 2024-2025;
  resultados podem ser cherrypicked sem que percebamos.
- **Custo de implementacao**: P2 dobra o custo de codigo + WF.
  P1 eh mais conservadora (1 candidato).
- **Regra anti-overfit**: nem P1 nem P2 podem introduzir parametros
  otimizaveis novos. Todos os parametros vem **literalmente** dos
  papers.

```proposta
id: P1
autor: Explorador
resumo: Shortlist conservadora — focar exclusivamente no arXiv 2605.11423 (Volatility-Volume-Gap Classifier MNQ).
conteudo: |
  Paper unico, MNQ direto, 947 dias 2021-2025, edge positivo
  documentado (classifier de regime + late-session reversal).
  Plano: baixar paper, extrair classifier, implementar plugin
  Python, estrategia operavel, WF longo 2025-07 a 2026-05, hold-out
  temporal em 2026-06+. Sem parametros otimizaveis novos.
  Custo estimado: 2-3 semanas.
confianca: 78
```

```proposta
id: P2
autor: Explorador
resumo: Shortlist combinada — P1 + Beat the Market SSRN 4824172 adaptado a MNQ (2 candidatos paralelos).
conteudo: |
  P1 mais Beat the Market adaptado (logica de noise boundary
  ATR-based, replicada em SPY 2007-2024 com Sharpe 1.33). Permite
  selecionar o melhor dos dois apos WF longo. Custo dobra mas
  reduz risco de pipeline ocioso por mais 4-8 semanas se P1
  isolada falhar. Sem parametros otimizaveis novos em nenhuma
  das implementacoes.
confianca: 65
```

### Confianca

72 (na shortlist; preferencia tecnica leve por P1 mas Conselho decide).


## Turno 3 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T16:00:00Z'
```

### Critica das duas propostas

#### Contra P1 (foco em arXiv 2605.11423)

1. **Paper recente DEMAIS para confiar**: arXiv 2605.11423 nao
   passou por peer review. Os subsequentes "May 27 paper review
   walls" (Princeton Chen Substack) que aparecem na busca **estao
   reportando resultados negativos** em arquiteturas similares
   (gradient boosting, LSTM em MNQ 5min) — quote: "No configuration
   beats the 51.8% base rate. Best GB p=0.135, LSTM p=0.515.
   Feature importance unstable across folds." Isso eh evidencia
   ADJACENTE de que ML em MNQ minute esta no limite teorico.
2. **947 dias eh pouco para regime change**: 2021-2025 inclui
   3 regimes distintos (recovery COVID 2021, bear market 2022,
   bull dovish 2023-2024, volatility regime 2025). Classifier
   calibrado em uma janela tem alta chance de ser overfit a
   transicao especifica de regime.
3. **"Late-session reversal" pode ser efeito 0DTE temporario**:
   pelo paper 4692190 (0DTEs Gamma), MM gamma flipou de positivo
   pra negativo em 2023+, mudando dinamica intraday. Reversal pode
   ser **artefato do regime atual de gamma**, nao edge persistente.
4. **Volatility-Volume-Gap classifier eh complexo**: 3 features +
   regime = mais variaveis livres = mais chance de overfit.

#### Contra P2 (P1 + Beat the Market adaptado)

1. **Beat the Market eh SPY, NAO futuro**: ETF tem dinamica de
   liquidez fundamentalmente diferente de futuro alavancado. Banda
   ATR de SPY pode nao mapear para MNQ — ja vimos que volatilidade
   do MNQ varia 37% no P17 entre 6 semanas (`[[Refutacao_P2_Range_Absoluto_2026-05-29]]`).
2. **Custo dobra, beneficio nao dobra**: pipeline ocioso eh um
   problema **de gestao**, nao de research. Implementar 2 candidatos
   em paralelo so dilui foco e gera duas Decisoes de descarte
   provaveis em vez de uma.
3. **Maroy (SSRN 5095349) tem cheirinho de overfit**: titulo
   literal eh "Improvements... using **Parameter Optimization**".
   O improvement vem de optimizar parametros sobre dados ja vistos
   pelo paper original — overfit por construcao.

#### Critica de fundo a ambas

A shopping-list inteira tem **viés de sobrevivencia da literatura**:
papers publicados sao papers com edge documentado. Papers com
edge **negativo** ou **nulo** (que sao a maioria empiricamente) nao
chegam a publicacao. O fato de termos 10 papers pre-curados para
estrategias de momentum/reversal nao significa que MNQ tem 10
edges disponiveis — significa que filtramos a literatura por
edges aparentes.

A `[[Refutacao_P2_Range_Absoluto_2026-05-29]]` ensinou que **mesmo
estrategias internamente coerentes falham na nao-estacionariedade
do MNQ**. Qualquer paper aceito agora deve ser tratado como
**hipotese a ser refutada**, nao como solucao a ser implementada.

#### Posicao do Devils_Advocate

Nem P1 nem P2 sao **erradas**, mas ambas seguem o mesmo padrao
que matou a estrategia anterior: implementar primeiro, validar
depois. Proposta correta nao foi feita: **NENHUMA implementacao
ate triagem rigorosa**.

Caminho que defendo (proposta-implicita P3):

1. **Antes** de implementar qualquer paper, **carregar os 3
   candidatos validos** (arXiv 2605.11423, SSRN 4824172, SSRN 3760365)
   no NotebookLM com prompt do TL;DR (ja preparado pela
   shopping-list).
2. Esperar resposta sintetizada do NotebookLM identificando
   **conflitos** entre os papers (ex: 2605.11423 fala em reversal
   late-session, 3760365 fala em momentum late-session — qual
   esta certo?).
3. So **depois** abrir Spec do candidato vencedor.

Esta proposta-implicita NAO pode ser P3 formal porque sou critico,
nao proponente. Se o usuario concordar, pedir ao Explorador para
emitir proposta P3 formalizada num turno adicional.

### Confianca

85 (na critica). Sobre o caminho proposto: 70 — cuidado com
viés de sobrevivencia de papers eh real, mas pode-se argumentar
que NotebookLM nao sintetiza melhor que o proprio Conselho ja
fez nesta triagem.


## Turno 4 — Hermes (AVALIACAO_TECNICA)

```meta
agente: Hermes
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T16:05:00Z'
```

### Avaliacao tecnica das duas propostas

Esta eh **triagem de candidatos**, nao implementacao. Avaliacao
restrita ao que cada candidato **exigiria** se virasse Spec.

#### arXiv 2605.11423 (Volatility-Volume-Gap Classifier MNQ)

Implicacoes Python (`caos/walk_forward/estrategias/`):

- Plugin novo: `VolatilityVolumeGapClassifier` calcula tres features
  por dia (volatility, volume, gap) e classifica regime.
- Estrategia operavel: condiciona entradas em "late-session reversal"
  ao classifier ser positivo. Trivial em pandas.

Implicacoes C# (`04_CODIGO/ninjascript/`):

- Logica do classifier: 3 features OHLCV (volatility = `range`,
  volume = `Volume[1]`, gap = `Open[0] - Close[1]`). Sem novas
  APIs.
- Reversal trade: `EnterShort` no maximo dos 30 minutos finais se
  classifier positivo + sinal de reversal. Sem novas APIs.

**Sem Veto_Tecnico para P1 ou P2.**

#### SSRN 4824172 (Beat the Market SPY adaptado)

Implicacoes Python:

- "Noise boundary" = banda ATR-based em torno da abertura. Trivial
  em pandas.
- Trade trend-following ao romper banda. Trivial.

Implicacoes C#:

- Calculo de ATR em janela movel (Indicator NT8 nativo).
- `EnterLong` / `EnterShort` ao romper banda. Sem novas APIs.

**Sem Veto_Tecnico para P2.**

#### Custos comparados

| Metrica | P1 (so 2605.11423) | P2 (P1 + Beat the Market) |
|---|---|---|
| Plugin Python | 1 novo | 2 novos |
| Estrategia operavel Python | 1 nova | 2 novas |
| Linhas C# estimadas | ~150 | ~280 |
| Tempo de implementacao | 2-3 semanas | 4-6 semanas |
| Risco de Veto_Tecnico futuro | baixo | baixo |

#### Sobre o caminho-implicito P3 do Devils_Advocate

Carregar papers no NotebookLM e esperar sintese eh **zero codigo**
no CAOS, mas tambem eh fora do escopo formal do Conselho (nao gera
artefato versionavel). Hermes recomenda que se o usuario concordar
com P3, ela seja **adicional** a P1 ou P2 (nao substituta) — fazer
NotebookLM como **etapa de pre-Spec**, e abrir Spec apos.

### Veto_Tecnico

**Nenhum.** Tres caminhos (P1, P2, P3-implicita) sao tecnicamente
viaveis.

### Confianca

90 (na avaliacao tecnica).


## Turno 5 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T16:10:00Z'
```

### Sintese

Tres caminhos no espaco de propostas:

| Caminho | Acao | Custo | Risco principal |
|---|---|---|---|
| **P1** (Explorador, conf 78) | Implementar arXiv 2605.11423 isolado | 2-3 sem | overfit ao regime 2021-2025 |
| **P2** (Explorador, conf 65) | Implementar P1 + Beat the Market adaptado | 4-6 sem | dilui foco; Beat the Market eh SPY, nao MNQ |
| **P3** (implicita do DA, sem confianca formal) | Carregar 3 candidatos no NotebookLM antes de qualquer codigo | 0 sem (espera externa) | NotebookLM pode nao sintetizar melhor que o Conselho |

#### Vetos

**Nenhum.** Hermes nao emite Veto_Tecnico.

#### Avaliacao das criticas do Devils_Advocate

A critica de **viés de sobrevivencia da literatura** eh procedente
e fundamental — o Conselho aceita. Tambem eh procedente a critica
sobre **arXiv 2605.11423 nao ter peer review** (paper de 2026-03,
janela curta de exposicao publica). E a observacao de que outras
janelas de pesquisa em ML+MNQ no mesmo periodo dao **resultados
negativos** eh evidencia adjacente que pesa contra P1 isolada.

Por outro lado, a critica de "Beat the Market eh SPY, nao MNQ" eh
**procedente mas nao bloqueante** — a logica de noise boundary
ATR-based eh universalmente aplicavel a qualquer ativo de
volatilidade calibravel.

#### Decisao

A R4.5 (consenso 2/3) nao se aplica direto porque so o Explorador
foi proponente formal. O fluxo correto da R4.6 com so um
proponente eh: Athena interpreta confianca declarada das duas
propostas (78 vs 65) e atribui vencedor por margem ≥ 10 pontos.

Margem 78 - 65 = 13 pontos > 10. **Vencedora formal: P1**.

**MAS** acolhimento parcial da critica do Devils_Advocate: P1 eh
**aceita com modificacao** — antes de qualquer linha de Python,
o Spec novo deve ter uma **etapa zero de pre-validacao** que
carregue arXiv 2605.11423 + SSRN 3760365 (papers convergentes em
late-session) no NotebookLM com prompt explicito sobre conflitos
e regime change. Esta etapa zero eh barata (1 dia) e nao bloqueia
a implementacao se o NotebookLM nao revelar conflito grave.

### Status final

`concluido`. Caminho **P1 modificado** (P1 + etapa-zero NotebookLM
do P3 implicito do Devils_Advocate).

### Saida concreta para o usuario

1. **Etapa zero (1 dia)**: usuario carrega no NotebookLM:
   - arXiv 2605.11423 (Volatility-Volume-Gap Classifier MNQ)
   - SSRN 3760365 (Hedging Demand intraday momentum)
   - SSRN 4692190 (0DTEs Gamma — para contexto de regime)

   Prompt sugerido:
   > Sintetize esses 3 papers para um trader de MNQ futures em
   > NinjaTrader 8 com fricção Topstep (USD 2500 trailing DD).
   > Foque em: (a) edges documentados ≥ 5 pts/trade após fricção,
   > (b) por que ha conflito aparente entre 2605.11423 (reversal
   > late-session) e 3760365 (momentum last 30min) — qual paper
   > esta certo para o regime atual? (c) o regime de gamma 0DTE
   > muda a interpretacao do reversal? Liste regras
   > implementaveis em Python sem book depth.

2. **Etapa um (2-3 semanas)**: abrir Spec novo
   `caos-volatility-volume-gap-mnq` com:
   - Plugin Python `VolatilityVolumeGapClassifier`
   - Estrategia operavel `LateSessionReversal` condicional ao
     classifier
   - WF longo 2025-07 a 2026-05
   - Hold-out **temporal** em 2026-06+ (sem WF prévio)

3. Criterios de descarte **pre-registrados** (igual a Decisao
   2026-05-28-01 fez):
   - Sharpe mediana WF >= 1.0 e Calmar >= 1.5
   - PnL replay 2026-06+ >= -USD 100 em 30 dias uteis
   - Paridade Python<->C# trade-a-trade dentro de 5%

4. Tag `caos-frozen-2026-05-25-02` permanece SUSPENSA. Nao ha
   nova tag ate que P1 modificada complete validacao formal.

### Campos da Decisao final

- `proposta_aceita`: P1 (com modificacao do P3-implicito incorporada
  como etapa-zero no Spec futuro)
- `vetos`: nenhum
- `aprovado_walk_forward`: false (Decisao eh seleção de candidato,
  nao aprovacao de estrategia para WF)
- `reproduzivel`: true
- `regressao_detectada`: false
- `status`: concluido
- `links_zettel`: `[[Refutacao_P2_Range_Absoluto_2026-05-29]]`,
  `[[Decisao_2026-05-29-01_Descarte_Reengenharia]]`

### Confianca

72 (na sintese; usuario tem caminho concreto).

```sintese
proposta_aceita: P1
rationale: |
  Triagem dos 10 papers da shopping-list-fontes-notebooklm-2026-05-25
  contra o filtro R12 (Spec 1) + criterios complementares da
  [[Refutacao_P2_Range_Absoluto_2026-05-29]] resulta em 3 candidatos
  validos: arXiv 2605.11423 (Volatility-Volume-Gap Classifier MNQ),
  SSRN 3760365 (Hedging Demand intraday momentum), SSRN 4824172
  (Beat the Market SPY adaptado).

  Vencedor: P1 (foco isolado em arXiv 2605.11423) por:
  - Unico paper especifico do MNQ com edge positivo documentado
    (947 dias 2021-2025)
  - Janela cobre regime atual pos-COVID, pos-0DTE explosion
  - Implementavel em Python sem book depth (so OHLCV)
  - Convergencia parcial com SSRN 3760365 (Hedging Demand)
    fortalece tese de late-session reversal/momentum

  Modificacao acolhida do Devils_Advocate: antes da implementacao,
  etapa-zero de pre-validacao via NotebookLM (carregando arXiv
  2605.11423 + SSRN 3760365 + SSRN 4692190 com prompt explicito
  sobre conflitos e regime change). Esta etapa eh barata (1 dia)
  e nao bloqueia a implementacao se NotebookLM nao revelar
  conflito grave.

  Plano:
  1. Etapa zero (1 dia): NotebookLM com 3 papers + prompt.
  2. Etapa um (2-3 sem): Spec caos-volatility-volume-gap-mnq.
  3. Criterios de descarte pre-registrados (Sharpe>=1.0 WF,
     PnL>=-USD 100 replay 30 dias, paridade Python<->C# 5%).

  Tag caos-frozen-2026-05-25-02 permanece SUSPENSA. Nova tag
  apenas apos validacao formal completa de P1 modificada.
links_zettel:
  - "[[Refutacao_P2_Range_Absoluto_2026-05-29]]"
  - "[[Decisao_2026-05-29-01_Descarte_Reengenharia]]"
aprovado_walk_forward: false
reproduzivel: 'true'
regressao_detectada: false
status: concluido
```
