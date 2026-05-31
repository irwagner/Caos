---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Explorador
- Mister_M
- Odin
contexto_hash_sha256: 9f4e488383b2047338d08d65ecc58368060f97f7e46128b313282b390cc5f47f
data_fim: '2026-05-31T03:46:00Z'
data_inicio: '2026-05-31T03:19:57Z'
fase_final: SINTESE
identificador: 2026-05-31-01
modelos:
  Athena: claude-opus-4.7
  Cerberus: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Explorador: claude-opus-4.7
  Mister_M: claude-opus-4.7
  Odin: claude-opus-4.7
notas_injetadas:
- gatilho:usuario
- aberto_por:usuario
- altera_exposicao:false
- requer_csharp:false
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Cerberus: 42
  Devils_Advocate: 42
  Explorador: 42
  Mister_M: 42
  Odin: 42
status: concluido
titulo: rumo-do-pipeline-apos-tres-refutacoes
turnos_consumidos: 7
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:19:57Z'
```

### Tema

Em maio/2026, o pipeline do CAOS produziu **três refutações
consecutivas**:

1. **Crabel NR7 + ORB + SF + CB** (`Decisao_2026-05-25-02`):
   aprovada no WF longo (Sharpe mediana +2.91), mas re-replay NT8
   28/01-26/05 deu −USD 573,50. Arquivada via fallback A da
   `Decisao_2026-05-29-01`.
2. **P2 range_absoluto** (`Decisao_2026-05-29-01`, caminho B):
   refutada na própria calibração — threshold absoluto não resiste
   à não-estacionariedade do MNQ (volatilidade variou 37% no P17
   entre dois trimestres).
3. **VVG Late-Session Reversal** (`Decisao_2026-05-29-02/03`, paper
   Mesfin arXiv 2605.11423): refutada no WF longo por year-stability
   (1/4 trimestres positivos). O próprio abstract do paper já
   admitia "fails multi-year consistency".

### O que está em jogo

O usuário pediu "prossiga". A ação default seria triar a próxima
candidata da shopping-list e abrir o quarto Spec. Mas três
refutações seguidas são um **sinal** que merece síntese antes de
gastar mais 1-2 semanas em uma quarta tentativa que pode ter o
mesmo destino.

A pergunta central: **o problema é a escolha de candidatas, ou é
estrutural ao MNQ minute + fricção Topstep?**

Evidência convergente acumulada:

- **arXiv 2605.04004** (Structural Limits MNQ): edge bruto OHLCV
  intraday gravita entre 0.07 e 1.5 pts/trade — abaixo do limiar
  de 5 pts que a fricção exige. Conclusão do paper: edge se
  desintegra após custos.
- **arXiv 2605.11423** (Mesfin/VVG): mesmo o melhor setup
  condicional (+7.80 pts/trade, T=1.46) falha em estabilidade
  plurianual.
- **arXiv 2508.06788** (OFI): OFI agregado não prediz sem book
  depth (que o NT8 não exporta de forma confiável).
- Empiria interna: 3 estratégias direcionais refutadas em 1 mês.

Isto é coerente com a hipótese de que **edges direcionais
≥ 5 pts/trade no MNQ minute com OHLCV puro simplesmente não
existem de forma persistente** no regime atual (pós-0DTE,
pós-2024).

### Caminhos possíveis

- **(A) Continuar triando a shopping-list**: pegar o próximo
  candidato (Beat the Market adaptado, Hedging Demand momentum,
  ou calendar anomalies) e abrir Spec.
- **(B) Mudar de classe de problema**: abandonar OHLCV-direcional
  e investigar algo estruturalmente diferente (ex: position
  sizing / gestão de risco sobre uma estratégia neutra; ou
  aquisição de dados melhores — book depth real — antes de tentar
  order flow).
- **(C) Pausar o pipeline de estratégias** e consolidar:
  documentar a "regra de ouro negativa" (o que NÃO funciona),
  formalizar o filtro R12 reforçado, e esperar dado/ideia
  materialmente nova antes de gastar mais ciclos.

### Agentes convocados

- Explorador (candidatos remanescentes e o que a literatura diz)
- Mister_M (leitura estatística das 3 refutações — é padrão ou
  azar?)
- Odin (visão macro/estrutural do MNQ)
- Devils_Advocate (régua dura contra viés de ação)
- Cerberus (risco de continuar gastando ciclos vs. risco de parar)
- Athena (síntese)

`altera_exposicao=false`. `requer_csharp=false`. Orçamento: 12.

Avanço para a fase **PROPOSTAS**.


## Turno 2 — Explorador (PROPOSTAS)

```meta
agente: Explorador
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:24:00Z'
```

### Proposta P1 — Mudar de classe de problema: parar de caçar edge direcional OHLCV

Aceito o enquadramento da Athena. Olhando a shopping-list que eu
mesmo curei, os candidatos remanescentes se dividem em três grupos,
e **todos os três grupos já têm evidência negativa**:

1. **Direcionais OHLCV** (Beat the Market adaptado, Hedging Demand
   momentum): mesma classe das 3 refutadas. arXiv 2605.04004
   crava o teto de edge bruto em 1.5 pts. Probabilidade alta de
   quarta refutação.
2. **Calendar anomalies** (Pre-FOMC, Turn-of-Month): a própria
   shopping-list anota que ambos estão documentados como
   **desaparecendo** pós-2015/pós-2020 (SSRN 3134546, ResearchGate
   385968274). Caçar anomalia em extinção é trabalho perdido.
3. **Order Flow** (OFI): exige book depth Level 2 que o NT8 não
   exporta confiável. O sniffer já falhou (Sharpe −39). Sem dado
   novo, morto na origem.

Minha proposta honesta, contrariando meu próprio papel de
"buscador de papers": **a shopping-list está esgotada como fonte
de edge direcional**. O que sobra de genuinamente novo exige
**dado que não temos** (book depth) ou **classe de problema
diferente**.

Proponho **caminho B**: parar de procurar edge direcional e
investigar **a única coisa que a evidência sugere ter valor**: o
regime 0DTE gamma como filtro de *quando NÃO operar*, não de
direção. Mas isso exige dado de gamma exposure (GEX) que também
não temos de graça.

Conclusão: sem dado novo, a melhor jogada é **B degenera em C**.

### Confiança

60 (a favor de mudar de classe de problema; honestidade sobre o
esgotamento da própria curadoria).

```proposta
id: P1
autor: Explorador
resumo: Mudar de classe de problema — a shopping-list está esgotada como fonte de edge direcional OHLCV; o que resta exige dado que não temos (book depth, GEX).
conteudo: |
  Os 3 grupos de candidatos remanescentes têm evidencia negativa:
  direcionais OHLCV (teto 1.5 pts, arXiv 2605.04004), calendar
  anomalies (documentadas como desaparecendo), order flow (exige
  book depth que NT8 nao exporta). Continuar triando a shopping-list
  e' caçar em poço seco. Mudar de classe de problema exige dado novo
  (book depth/GEX) que nao temos. Sem dado novo, B degenera em C
  (pausar e consolidar).
confianca: 60
```


## Turno 3 — Mister_M (PROPOSTAS)

```meta
agente: Mister_M
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:28:00Z'
```

### Análise estatística: três refutações são padrão, não azar?

Pergunta-chave da Athena: as 3 refutações são sinal estrutural ou
ruído de N pequeno?

**Distingo as três — elas falharam por razões DIFERENTES**:

1. **Crabel**: aprovou no WF (+2.91 Sharpe) e falhou no
   hold-out/replay (−USD 573). Isso é **overfit ao WF** — clássico.
   O WF e o hold-out viram regimes diferentes.
2. **P2**: falhou na calibração por **não-estacionariedade**
   (threshold absoluto). Isso é **erro de especificação** — nem
   chegou a ser testada.
3. **VVG**: aprovou Sharpe/Calmar/PnL e falhou só em
   **year-stability** (1/4). Isso é **falta de persistência
   temporal** — edge real mas concentrado num trimestre.

Três modos de falha distintos NÃO são "azar repetido". São três
manifestações do **mesmo fenômeno subjacente**: o MNQ minute tem
edges que **aparecem em janelas específicas e somem em outras**.
Isso é a assinatura estatística de um mercado **eficiente o
suficiente** para que qualquer edge OHLCV seja transitório.

**Cálculo de poder**: para detectar um edge de 1.5 pts/trade
(o teto do arXiv 2605.04004) com fricção de ~1 pt round-trip,
o edge líquido é ~0.5 pts. Para distinguir 0.5 pts de zero com
significância 95% e poder 80%, assumindo sd de ~50 pts/trade
(observado na VVG), precisaríamos de **N ≈ 78.000 trades**.
Nenhuma estratégia direcional gera isso em janela testável.
**Conclusão estatística: o edge, se existe, é indetectável com
o N que conseguimos gerar.**

### Proposta P2 — Consolidar a evidência negativa formalmente (caminho C)

Antes de mais qualquer tentativa, documentar a **"regra de ouro
negativa"** como artefato permanente do projeto: edges direcionais
OHLCV no MNQ minute são estatisticamente indetectáveis sob fricção
Topstep com o N gerável. Isso vira critério de triagem: qualquer
candidato futuro precisa **superar esse teorema de impossibilidade
prático** com dado/mecanismo materialmente novo, ou é rejeitado na
triagem sem gastar Spec.

### Confiança

74 (na análise estatística e na proposta de consolidação).

```proposta
id: P2
autor: Mister_M
resumo: Consolidar formalmente a regra de ouro negativa — edges direcionais OHLCV no MNQ minute são estatisticamente indetectaveis com o N gerável sob fricção Topstep. Vira critério de triagem.
conteudo: |
  As 3 refutacoes falharam por modos distintos (overfit ao WF;
  nao-estacionariedade; falta de year-stability) — nao e' azar,
  e' a assinatura de um mercado eficiente onde edges OHLCV sao
  transitorios. Calculo de poder: detectar edge liquido de ~0.5
  pts/trade com sd ~50 exigiria N ~78.000 trades, inalcancavel.
  Consolidar isso como "regra de ouro negativa" permanente: futuro
  candidato precisa superar esse teorema de impossibilidade pratico
  com dado/mecanismo novo, ou e' rejeitado na triagem sem gastar Spec.
confianca: 74
```


## Turno 4 — Odin (PROPOSTAS)

```meta
agente: Odin
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:32:00Z'
```

### Visão macro/estrutural: o que mudou no MNQ

Concordo com o diagnóstico, mas adiciono a dimensão **estrutural
de mercado** que o Mister_M tratou só estatisticamente.

O MNQ de 2026 não é o de 2018. Três mudanças estruturais:

1. **0DTE engole >50% do volume de derivativos do índice**. Isso
   muda a microestrutura intraday: dealers passam mais tempo Long
   Gamma, suprimindo volatilidade direcional (a força que
   estratégias direcionais precisam). É por isso que reversal
   (VVG) teve edge num trimestre — mas não persiste, porque o
   regime de gamma oscila.
2. **Algos institucionais comprimiram os edges OHLCV clássicos**.
   NR7/Crabel funcionava em 1990 (Crabel publicou) porque o
   mercado era mais lento. Hoje o follow-through de breakout é
   arbitrado em milissegundos.
3. **O retail-flow via 0DTE cria mean-reversion intradiária** que
   é real mas **não-estacionária** — depende do posicionamento de
   gamma do dia, que não medimos.

### Proposta P3 — Adquirir o dado que falta antes de mais estratégia

A conclusão estrutural é clara: **todo edge remanescente plausível
depende de medir o regime de gamma/posicionamento (GEX) ou o book
depth real (Level 2)**. Sem esses dados, estamos lutando com uma
mão amarrada.

Proponho um caminho **B construtivo** (não o B-degenera-em-C do
Explorador): em vez de mais uma estratégia OHLCV, abrir um Spec de
**aquisição e validação de dado de GEX/Level 2** — investigar se
há fonte viável (CBOE GEX feed, ou reconstrução de DOM do NT8 com
configuração diferente do sniffer que falhou). Se o dado for
obtenível e confiável, ele destrava uma classe inteira de
estratégias que hoje é impossível. Se não for, fecha-se a porta
com honestidade e vai-se para C.

### Confiança

58 (a tese estrutural é sólida; a viabilidade de obter GEX/L2 é
incerta — daí a confiança média).

```proposta
id: P3
autor: Odin
resumo: Adquirir o dado que falta (GEX/Level 2) antes de mais estratégia — todo edge remanescente plausível depende de medir regime de gamma ou book depth, que hoje não temos.
conteudo: |
  Mudancas estruturais do MNQ 2026 (0DTE >50% do volume, algos
  comprimindo edges OHLCV, mean-reversion retail nao-estacionaria
  dependente de gamma) implicam que edge remanescente plausivel
  depende de medir GEX ou book depth Level 2. Proponho Spec de
  AQUISICAO e validacao desse dado (CBOE GEX feed, ou reconstrucao
  de DOM com config diferente do sniffer que falhou) antes de mais
  estrategia. Se o dado for obtenivel/confiavel, destrava classe
  nova; se nao, fecha a porta com honestidade e vai-se para C.
confianca: 58
```


## Turno 5 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:37:00Z'
```

### Crítica

Este é o Debate mais importante da sessão, porque é o único em que
o Conselho pode errar **silenciosamente** — não por implementar
algo ruim, mas por escolher mal o que fazer com o tempo. Régua dura
nas três.

#### Contra P1 (Explorador — "shopping-list esgotada, B degenera em C")

Honestidade louvável, mas a conclusão é **derrotista cedo demais**.
"A shopping-list está esgotada" não é o mesmo que "não há edge".
A shopping-list foi curada com um viés específico (papers
acadêmicos de momentum/reversal). Há classes inteiras nunca
tocadas: **arbitragem estatística entre MNQ e correlatos** (ES,
MES, NQ), **estratégias de volatilidade** (não-direcionais),
**market making passivo**. P1 conclui "poço seco" tendo cavado
um único poço.

#### Contra P2 (Mister_M — "consolidar regra de ouro negativa")

O cálculo de poder (N≈78.000) é **o argumento mais forte do
Debate** e eu não consigo refutá-lo. MAS há uma armadilha: o
cálculo assume que queremos detectar o edge **médio incondicional**.
Estratégias condicionais (operar só em N dias específicos) têm
edge maior por trade — a VVG tinha +7.80 pts, não 1.5. O problema
da VVG não foi edge pequeno, foi **falta de persistência**. P2
generaliza "edge indetectável" a partir de um cálculo que se aplica
ao caso incondicional, não ao condicional. **Erro de escopo.**

Ainda assim, P2 tem um mérito que nenhuma outra tem: **é a única
que não gasta mais ciclos antes de aprender algo**. Documentar o
que NÃO funciona é valor permanente.

#### Contra P3 (Odin — "adquirir GEX/Level 2")

Esta é a proposta mais sedutora e mais perigosa. "Se tivéssemos
dado melhor, teríamos edge" é a **falácia favorita de todo quant
que perde dinheiro**. Não há garantia de que GEX/L2 destrave
qualquer coisa — o arXiv 2508.06788 mostra que mesmo OFI com book
depth tem sinal fraco. P3 propõe gastar semanas adquirindo dado
caro/difícil baseado numa **esperança**, não numa evidência de que
o dado resolve. É o caminho que mais consome recurso com menor
base empírica.

E tem o problema do freio humano: GEX feed da CBOE é **pago**;
reconstruir DOM exige o sniffer que **já falhou**. P3 reabre uma
ferida sem evidência nova de que desta vez funciona.

#### Posição do Devils_Advocate

A combinação honesta: **P2 como base (consolidar a evidência
negativa) + uma fração de P1 corrigida (reconhecer que só um poço
foi cavado, sem prometer que os outros têm água)**.

NÃO fazer P3 agora — é gasto especulativo. NÃO continuar triando a
shopping-list cegamente (caminho A do enunciado) — é repetir o erro.

O caminho honesto é **parar, documentar o teorema de
impossibilidade prático (com o escopo correto que a P2 errou:
vale para incondicional E para condicional-sem-persistência), e
só reabrir o pipeline quando houver hipótese que ataque
especificamente a NÃO-PERSISTÊNCIA** — que é a causa-raiz comum
das 3 refutações, não o tamanho do edge.

### Confiança

88 (na crítica). O insight central: a causa-raiz das 3 refutações
não é "edge pequeno" — é **não-persistência temporal**. Qualquer
caminho futuro tem que atacar isso, não o tamanho do edge.


## Turno 6 — Cerberus (AVALIACAO_RISCO)

```meta
agente: Cerberus
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:41:00Z'
```

> Fase normalmente condicionada a `altera_exposicao=true`. Aqui o
> "risco" não é de exposição financeira (Sim101 o tempo todo), mas
> de **alocação de recurso** (tempo/tokens/foco). Avalio nessa chave.

### Avaliação de risco de cada caminho

| Caminho | Custo (semanas) | Risco principal | Valor esperado |
|---|---|---|---|
| A (triar shopping-list) | 1-2 por candidato | 4ª refutação provável | baixo — repete padrão |
| P1 (mudar classe) | indefinido | escopo vago sem dado novo | médio mas difuso |
| P2 (consolidar negativo) | 0.5 | nenhum — só documenta | alto — valor permanente |
| P3 (adquirir GEX/L2) | 3-6 | dado pago/difícil sem garantia | alto SE der certo, mas base fraca |

### Veredito de risco

**Não emito veto bloqueante a nenhum caminho** — nenhum gasta
dinheiro real ou aumenta exposição. Mas registro **graduação de
risco de recurso**:

- **P3 tem o pior perfil risco/recurso**: maior custo, menor base
  empírica. Veto_De_Risco **condicional**: só autorizar P3 se
  houver evidência prévia (sem custo) de que o dado é obtenível e
  confiável. Investigação preliminar gratuita primeiro; compromisso
  de semanas só depois.
- **P2 tem o melhor perfil**: custo mínimo, valor permanente, zero
  risco. Aprovo sem ressalvas.
- **A repete o padrão refutado**: não vetado, mas desencorajado —
  o ônus da prova passa a ser do candidato (precisa atacar
  não-persistência, não só ter edge).

### Condição imposta (alinhada ao Devils_Advocate)

Qualquer reabertura do pipeline de estratégia (A, P1 ou P3) DEVE,
como critério de triagem pré-registrado, **demonstrar como ataca a
não-persistência temporal** — a causa-raiz comum das 3 refutações.
Candidato que não enderece isso é rejeitado na triagem, sem Spec.

### Confiança

82 (na avaliação de risco de recurso e na condição de triagem).


## Turno 7 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-31T03:46:00Z'
```

### Síntese

Três propostas formais (P1, P2, P3) + crítica dura do
Devils_Advocate + graduação de risco do Cerberus. Há convergência
mais forte do que parece à primeira vista.

#### O insight central que unifica o Debate

O Devils_Advocate cravou o ponto que reorganiza tudo: **as 3
refutações não compartilham "edge pequeno" como causa — elas
compartilham NÃO-PERSISTÊNCIA TEMPORAL**:

- Crabel: edge no WF, sumiu no hold-out (regime mudou).
- P2: threshold não-estacionário (regime muda a volatilidade).
- VVG: edge num trimestre, negativo nos outros três.

A causa-raiz é **regime-dependência**: o MNQ de 2026 tem micro-edges
que existem em certos regimes e evaporam em outros. Mister_M
provou que detectá-los incondicionalmente exige N inalcançável;
Odin explicou a mecânica (0DTE gamma oscilando); Cerberus e DA
convergiram no critério de triagem.

#### Votos

| Proposta | Explorador | Mister_M | Odin | DA | Cerberus |
|---|---|---|---|---|---|
| P1 (mudar classe) | sim | — | — | parcial | desencoraja A |
| P2 (consolidar negativo) | (B→C) | sim | — | **sim (base)** | **aprova s/ ressalva** |
| P3 (adquirir dado) | — | — | sim | **não agora** | **veto condicional** |

P2 tem o apoio mais amplo e o melhor perfil risco/recurso. P3 leva
veto condicional do Cerberus (investigação gratuita antes de
compromisso). P1 é absorvida: "mudar de classe" só faz sentido
com o critério de não-persistência embutido.

#### Decisão

**Proposta vencedora: P2 (consolidar a evidência negativa)**,
emendada com o insight do Devils_Advocate (escopo correto:
não-persistência, não tamanho do edge) e a condição de triagem do
Cerberus.

Concretamente, a Decisão estabelece:

1. **Consolidar a "Regra de Ouro Negativa"** como artefato
   permanente do projeto (nota Zettel + steering): edges
   direcionais OHLCV no MNQ minute, sob fricção Topstep, falham por
   **não-persistência temporal** — confirmado por 3 refutações
   independentes (modos distintos, causa comum) + 2 papers
   (2605.04004, 2605.11423).

2. **Novo critério de triagem pré-registrado (R12 reforçado)**:
   qualquer candidato futuro DEVE demonstrar, na triagem, **como
   ataca a não-persistência temporal** (ex: mecanismo de adaptação
   de regime, ou edge estrutural que não dependa de regime). Quem
   não endereçar isso é rejeitado SEM gastar Spec. Isto economiza
   os ciclos que A/P1 desperdiçariam.

3. **P3 (dado GEX/L2) fica como investigação preliminar GRATUITA**,
   sob veto condicional do Cerberus: o Explorador pode pesquisar
   (sem custo, via web) se há fonte viável de GEX/Level 2 para MNQ.
   Só vira Spec se a investigação preliminar mostrar que o dado é
   obtenível, confiável e gratuito/barato. Sem isso, não há
   compromisso de semanas.

4. **Pipeline de novas estratégias OHLCV-direcionais: PAUSADO.**
   Não por desistência, mas por disciplina — o ônus da prova
   inverteu: agora um candidato precisa provar que merece um Spec,
   não o contrário.

### Status final

`concluido`. Caminho **P2 emendada**.

### Campos da Decisão final

- `proposta_aceita`: P2 (emendada com escopo não-persistência +
  critério de triagem do Cerberus)
- `vetos`: Cerberus veto_de_risco **condicional** sobre P3 (não
  bloqueante — apenas exige investigação preliminar gratuita antes
  de compromisso)
- `aprovado_walk_forward`: false (Decisão de processo, não de
  estratégia)
- `reproduzivel`: total
- `regressao_detectada`: false
- `status`: concluido
- `links_zettel`: `[[Refutacao_VVG_Late_Session_2026-05-29]]`,
  `[[Refutacao_P2_Range_Absoluto_2026-05-29]]`,
  `[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]`

### Saída concreta para o usuário

1. Kiro_Brain escreve a nota Zettel **"Regra de Ouro Negativa —
   Não-Persistência no MNQ Minute"** consolidando as 3 refutações
   + 2 papers.
2. Kiro_Brain cria/atualiza steering com o **critério de triagem
   reforçado** (candidato precisa atacar não-persistência).
3. Explorador faz **investigação preliminar gratuita** sobre
   viabilidade de GEX/Level 2 (web research, sem compromisso).
4. Pipeline de estratégias OHLCV-direcionais permanece **pausado**
   até candidato que passe o novo critério.

### Confiança

80 (na síntese; o Debate convergiu bem e a causa-raiz comum dá
um critério acionável).

```sintese
proposta_aceita: P2
rationale: |
  Apos 3 refutacoes consecutivas (Crabel via overfit-ao-WF; P2 via
  nao-estacionariedade; VVG via falta de year-stability), o Conselho
  identifica a CAUSA-RAIZ COMUM: nao-persistencia temporal (regime-
  dependencia) dos edges OHLCV-direcionais no MNQ minute. Mister_M
  provou que detectar edge incondicional exige N~78.000 trades
  (inalcancavel); Odin explicou a mecanica (0DTE gamma oscilando);
  Devils_Advocate corrigiu o escopo (a causa nao e' edge pequeno, e'
  nao-persistencia); Cerberus graduou o risco de recurso.

  Decisao: aceitar P2 (consolidar a evidencia negativa) emendada:
  (1) documentar a "Regra de Ouro Negativa" como artefato permanente
      (Zettel + steering);
  (2) criar criterio de triagem reforcado (R12+): candidato futuro
      DEVE demonstrar como ataca a nao-persistencia temporal, ou e'
      rejeitado sem gastar Spec;
  (3) P3 (adquirir GEX/Level 2) fica como investigacao preliminar
      GRATUITA sob veto condicional do Cerberus — so vira Spec se o
      dado for obtenivel/confiavel/barato;
  (4) pipeline de estrategias OHLCV-direcionais PAUSADO — onus da
      prova invertido.

  Nao e' desistencia: e' disciplina anti-vies-de-acao. Documentar o
  que NAO funciona e' valor permanente e evita gastar ciclos numa 4a
  refutacao previsivel.
links_zettel:
  - "[[Refutacao_VVG_Late_Session_2026-05-29]]"
  - "[[Refutacao_P2_Range_Absoluto_2026-05-29]]"
  - "[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]"
aprovado_walk_forward: false
reproduzivel: 'true'
regressao_detectada: false
status: concluido
```
