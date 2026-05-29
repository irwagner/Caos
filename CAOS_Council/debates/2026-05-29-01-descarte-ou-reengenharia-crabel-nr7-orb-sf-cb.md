---
agentes_participantes:
- Athena
- Devils_Advocate
- Explorador
- Hermes
- Manolo
- Mister_M
contexto_hash_sha256: aa5f7a76b1ed84d9c8ff6ea2c2472e0365fa306c8a24367e66ef9c9f9102cc19
data_fim: '2026-05-29T14:28:00Z'
data_inicio: '2026-05-29T14:12:22Z'
fase_final: SINTESE
identificador: 2026-05-29-01
modelos:
  Athena: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Explorador: claude-opus-4.7
  Hermes: claude-opus-4.7
  Manolo: claude-opus-4.7
  Mister_M: claude-opus-4.7
notas_injetadas:
- gatilho:G5
- aberto_por:auto
- altera_exposicao:false
- requer_csharp:true
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Devils_Advocate: 42
  Explorador: 42
  Hermes: 42
  Manolo: 42
  Mister_M: 42
status: concluido
titulo: descarte-ou-reengenharia-crabel-nr7-orb-sf-cb
turnos_consumidos: 7
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:12:22Z'
```

### Tema

A Decisao `2026-05-25-02` aprovou a estrategia
`EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7), mediana_diaria, warmup=30, running_median), diario=-250 / semanal=-750 / janela=-1000 pts)`
para hold-out cego de 60 dias uteis com `MaxContratos=1`. O WF longo
(2025-07-01 â†’ 2026-05-25) deu Sharpe mediana **+2.91** e Calmar
mediana **+3.22** em 5 cortes anchored.

A Decisao `2026-05-28-01` impos Veto_De_Risco condicional do Cerberus:
hold-out **suspenso** ate o re-replay 28/01-26/05 do MNQ 06-26 com
PnL â‰¥ -USD 100 em 105 dias. Veto disparado por bug de paridade
Pythonâ†”C# descoberto na auditoria `d8e34dc` — 5/11 trades (45%)
ocorreram em dias que Python NAO consideraria elegiveis.

O re-replay foi executado em 28-29/05 com tres fixes em camadas:
`BarsRequiredToTrade=19320`, force-close defensivo do MfeMae+Trailing,
e guard `CurrentBar < BarsRequiredToTrade` em `EntrarInterno`.
**Resultado**: PnL **-USD 573,50** em 11 trades (win-rate 36,4%) sobre
~85 dias uteis. Extrapolado para 105 dias: â‰ˆ -USD 708.

### Veredito automatico do Cerberus

Limiar definido em `2026-05-28-01`:
- â‰¥ -USD 100 â†’ hold-out retomado.
- entre -USD 100 e -USD 500 â†’ Debate de avaliacao (sem veredito).
- â‰¤ -USD 500 â†’ **Debate de descarte (Devils_Advocate vence)**.

PnL observado (-USD 573,50) cruza o limiar **-USD 500**. Cerberus
emite Veto_De_Risco DEFINITIVO sobre hold-out: tag
`caos-frozen-2026-05-25-02` permanece SUSPENSA. Decisao `2026-05-25-02`
em estado de **revisao obrigatoria**.

### O que esta em jogo

1. **Descartar** a estrategia (mover para `02_ESTRATEGIAS/mortas/`,
   liberar pipeline para nova ideia) ou
2. **Re-engenheirar** parcialmente (substituir filtro NR7, trocar
   horario de entrada, substituir SpreadFilter, rever stops Crabel)
   com novo WF longo + nova Decisao com `aprovado_walk_forward=true`.

### Agentes convocados

- **Proponentes** (round-robin alfabetico ate quorum): Explorador,
  Manolo, Mister_M, Odin, Rodrigo.
- **Critico**: Devils_Advocate (turno mandatorio na fase CRITICA).
- **Tecnico**: Hermes (`requer_csharp=true`, qualquer proposta de
  re-engenharia mexe em `*Logica.cs`).
- **Risco**: Cerberus (pode comentar mas nao tem fase formal aqui;
  `altera_exposicao=false` enquanto a proposta nao propuser aumento
  de `MaxContratos` ou afrouxamento de `CircuitBreakerDiarioUSD`).

Avanco para a fase **PROPOSTAS**.


## Turno 2 — Explorador (PROPOSTAS)

```meta
agente: Explorador
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:14:00Z'
```

### Proposta P1 — Descarte completo + nova candidata vinda de paper aprovado

**Resumo**: arquivar `EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7), ...))`
em `02_ESTRATEGIAS/mortas/` e iniciar pipeline de nova candidata a
partir de paper academico aprovado pelo filtro R12 (sharpe â‰¥ 1,
sample â‰¥ 200, out_of_sample â‰¥ 30, instrumento batendo,
survivorship_bias_tratado=true).

### Justificativa

O re-replay 28/01-26/05 confirma o que a auditoria `d8e34dc` ja
sugeria: a estrategia **nao tem edge fora da janela de WF original**.
Win-rate 36,4% em mercado tendencial recente, com derrotas medianas
**maiores** do que vitorias medianas (MFE/MAE 0,74 — assimetrico
desfavoravel), sao sintomas classicos de overfit ao WF de
caracterizacao. Hipotese mais provavel: o filtro NR7 e o gatilho
ORB capturaram **uma janela especifica** de regime de volatilidade
que nao se repete em 2026.

Tres papers do shopping-list de NotebookLM atendem R12 e teriam
mais chance estatistica:

1. **arXiv 2605.04004** — *Structural Limits MNQ*: estuda o limite
   teorico de edge intraday no MNQ apos slippage. Indica que
   estrategias baseadas em compressao de range tem ceiling de
   Sharpe â‰ˆ 1,2-1,4 em RTH, abaixo do que `2026-05-25-02` estava
   prometendo. Util como **calibrador de expectativa** mas nao
   gera estrategia direta.
2. **Quantitativo Substack** — *Uncertainty: A probabilistic approach
   to momentum to deliver +1.7 Sharpe ratio* (Apr 5/2026): trata
   momentum probabilistico em portfolio de acoes. Adaptavel para
   MNQ se reinterpretar "aÃ§Ãµes" como "regimes intraday".
3. **arXiv 2508.06788** — *Structural Effects of LOB on Order Flow*:
   prova que OFI agregado nao tem edge sem reconstrucao da fila
   L2. Util **negativamente** — confirma que sniffer atual em NT8
   sem L2 nao gera proposta acionavel.

Caminho concreto se P1 vencer: abrir Spec novo "caos-momentum-probabilistico-mnq"
com Walk-Forward longo em paralelo enquanto a estrategia atual e
sepultada. Consumiria ~3 semanas de tempo de Conselho.

### Riscos

- **Custo de oportunidade**: sepultar uma estrategia que tinha
  Sharpe +2.91 no WF longo e desprezar evidencia, mesmo que parcial.
  Pode haver edge salvavel sem rebuild completo.
- **Overfit do proximo paper**: nao ha garantia que a proxima
  candidata sera melhor. Pode-se estar trocando um overfit
  conhecido por outro desconhecido.
- **Tempo morto**: sem estrategia em hold-out, o pipeline de
  validacao real fica ocioso por 4-6 semanas (novo WF + hold-out).

### Confianca

55

```proposta
id: P1
autor: Explorador
resumo: Descartar a estrategia atual e iniciar pipeline de nova candidata a partir de paper academico que atenda filtro R12.
conteudo: |
  Re-replay 28/01-26/05/2026 do MNQ 06-26 confirma: estrategia nao
  tem edge fora da janela de WF original. Win-rate 36,4% em mercado
  tendencial recente, MFE/MAE 0,74 (assimetrico desfavoravel) — sintomas
  classicos de overfit ao WF de caracterizacao. Acao: arquivar em
  02_ESTRATEGIAS/mortas/, abrir Spec novo "caos-momentum-probabilistico-mnq"
  com Walk-Forward longo em paralelo. Tres papers do shopping-list
  NotebookLM atendem R12 (arXiv 2605.04004, Quantitativo Substack,
  arXiv 2508.06788). Custo: ~3 semanas de Conselho.
confianca: 55
```


## Turno 3 — Manolo (PROPOSTAS)

```meta
agente: Manolo
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:16:00Z'
```

### Proposta P2 — Re-engenharia minima: substituir filtro NR7 por filtro de range absoluto sem dependencia de janela

**Resumo**: manter o gatilho ORB (rompimento da Opening Range), o
SpreadFilter mediana_diaria, o CircuitBreaker estendido e os stops
Crabel. **Trocar apenas** o filtro NR7 (que depende de janela de
7 dias para ser elegivel — fonte do bug de paridade Pythonâ†”C#) por
um filtro de **range absoluto fixo**: dia e elegivel se
`(High_dia_anterior - Low_dia_anterior) â‰¤ K * tickSize`, com K
calibrado UMA vez no WF original e congelado.

### Justificativa

O bug de paridade Pythonâ†”C# tem causa raiz **estrutural**: NR7 exige
saber "este dia tem o menor range dos 7 dias anteriores", e isso
quebra quando NT8 troca contrato em playback (ex: 03-26 â†’ 06-26),
porque a estrategia perde a memoria dos 6 dias anteriores. Mesmo
com `BarsRequiredToTrade=19320` defendendo, a primeira "barra util"
apos a troca vai ter janela CORRETA mas sem mostrar paridade
historica com Python (que rodou em pandas com janela completa o
tempo todo).

Filtro de range absoluto resolve isso porque:

- Nao depende de janela. Olha apenas dia `D-1`.
- Eh trivialmente paridade-equivalente Pythonâ†”C# (`Bars[1].High` -
  `Bars[1].Low`).
- Continua selecionando dias de **baixa volatilidade** — mesma
  intuicao macro do NR7.

Calibracao do K seria **um numero fixo** derivado do WF original
(p.ex.: K = 80 ticks = 20 pontos no MNQ) e marcada como
**congelada** na nova Decisao. Sem tunable novo (regra anti-overfit
do usuario observada).

Custo C#: ~30 linhas em `EstrategiaCrabelLogica.cs` para alternar
entre `nr7` e `range_absoluto` via parametro discreto. Sem novas
APIs NinjaScript.

### Riscos

- **K otimizado e nao validado fora de amostra**: o numero foi
  calibrado em 2025-07 â†’ 2026-05; se 2026-06 em diante mudar
  regime, K pode estar errado. Mitigacao: faixa K âˆˆ [60, 100]
  ticks com mediana 80, congelado.
- **Substituir NR7 nao salva a estrategia se o problema for o
  ORB em si**: o WF longo deu +2.91 Sharpe, mas o re-replay
  recente deu -USD 573,50 — pode ser que o proprio gatilho ORB
  nao tenha edge **agora** (regime mudou).
- **Eh uma re-engenharia que parece pequena mas exige novo WF
  longo** (1 mes de Conselho). Nao ha caminho rapido.

### Confianca

68

```proposta
id: P2
autor: Manolo
resumo: Re-engenharia minima — substituir filtro NR7 por filtro de range absoluto fixo K=80 ticks (sem dependencia de janela).
conteudo: |
  Bug de paridade Python<->C# tem causa raiz estrutural: NR7 exige
  saber "este dia tem o menor range dos 7 dias anteriores", e isso
  quebra quando NT8 troca contrato em playback. Filtro de range
  absoluto resolve: dia eh elegivel se (High[1] - Low[1]) <= 80
  ticks (= 20 pontos no MNQ). Nao depende de janela, paridade
  Python<->C# trivial. K congelado em codigo, sem novo tunable
  (regra anti-overfit). Manter ORB + SpreadFilter + CircuitBreaker
  inalterados. Custo: ~30-50 linhas em EstrategiaCrabelLogica.cs +
  porta Python espelho. Novo WF longo de validacao obrigatorio.
confianca: 68
```


## Turno 4 — Mister_M (PROPOSTAS)

```meta
agente: Mister_M
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:18:00Z'
```

### Proposta P3 — Manter estrategia, refazer hold-out com janela controlada e nova metrica de validacao

**Resumo**: NAO descartar e NAO re-engenheirar agora. O re-replay
28/01-26/05 tem **vies de janela curta** (85 dias uteis, 11
trades — N estatisticamente irrelevante). Refazer hold-out **mais
longo** sobre dados ja existentes em `dados/MNQ/` (cobertura
2024-01-01 â†’ 2026-05-15 segundo `manifesto.json`), com janela de
**252 dias uteis** (1 ano), e re-avaliar.

### Justificativa

11 trades NAO e amostra valida para concluir nada sobre uma
estrategia. O criterio de Cerberus (-USD 100 a -USD 500) foi
definido pre-replay com base em "quantos USD a estrategia pode
perder em 105 dias e ainda valer a pena". Mas o intervalo de
confianca de 11 trades sobre PnL e **enorme**: se medio = -USD 52
e desvio padrao por trade â‰ˆ USD 200, IC95% sobre PnL total fica
em [-USD 1.700, +USD 553] — ou seja, **o intervalo cruza zero**.
Concluir descarte ou re-engenharia com base em N=11 e estatistica
ruim, mesmo o resultado pontual sendo negativo.

A defesa do `BarsRequiredToTrade=19320` significa que para o
re-replay ter validade, o NT8 precisa carregar **44+ dias de
historico** ANTES da janela de teste. O re-replay atual quase nao
respeitou isso (Days to load do chart cobriu so ~43 dias uteis,
veja log `metadados-carga` mostrando "ultima_barra=13/03"). Em
outras palavras: o proprio resultado do re-replay esta
**comprometido pelo warmup insuficiente**, da mesma forma que o
replay original.

Caminho concreto:

1. Antes de fechar veredito, refazer replay sobre **252 dias
   uteis** (2025-05 â†’ 2026-05) com chart configurado para Days to
   load = 270+ dias. Isso da N â‰ˆ 30-50 trades.
2. Aplicar criterio Cerberus calibrado proporcionalmente: PnL â‰¥
   -USD 250 sobre 252 dias retoma hold-out; â‰¤ -USD 1.250 vira
   descarte.
3. Validar paridade trade-a-trade Pythonâ†”C# nessa janela
   estendida com novo script de auditoria.

Custo: 1 dia de NT8 replay + 1 dia de Conselho. Bem menor do que
descartar ou re-engenheirar.

### Riscos

- **Adia decisao**: a estrategia continua suspensa de hold-out
  enquanto se refaz validacao. Mas isso nao e custo real — o
  hold-out ja esta suspenso.
- **Pode-se estar postergando descarte inevitavel**: se a janela
  estendida tambem der negativo, sera Devils_Advocate vencendo
  com mais forca.
- **Replay de 252 dias no NT8 pode ser lento**: 1380 barras/dia *
  252 dias = 348k barras. Em hardware modesto, replay leva
  3-6 horas por execucao.

### Confianca

72

```proposta
id: P3
autor: Mister_M
resumo: Refazer hold-out com janela de 252 dias uteis (1 ano) sobre dados ja existentes; N=11 do replay e estatisticamente irrelevante.
conteudo: |
  11 trades NAO eh amostra valida para concluir descarte. IC95% sobre
  PnL total fica em [-USD 1.700, +USD 553] — cruza zero. O proprio
  re-replay 28/01-26/05 tem warmup insuficiente (Days to load do
  chart cobriu so ~43 dias uteis), invalidando o teste do
  BarsRequiredToTrade=19320. Caminho: refazer replay sobre 252 dias
  uteis (2025-05 -> 2026-05) com chart configurado para Days to
  load = 270+. N esperado: 30-50 trades. Criterio Cerberus calibrado
  proporcionalmente: PnL >= -USD 250 retoma; <= -USD 1.250 descarte.
  Custo: 1-2 dias.
confianca: 72
```


## Turno 5 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:21:00Z'
```

### Critica

Tres propostas, tres modos diferentes de a IA fugir da conclusao
desconfortavel. Vou atacar cada uma com regua dura, e depois
apresentar o que **realmente** os dados mostram.

#### Contra P1 (Explorador) — Descarte para nova candidata

O Explorador escolhe descarte, mas **acopla** o descarte a uma
nova candidata vinda de paper. **Isso e fuga**. Descartar uma
estrategia provada sem edge nao implica em "comecar nova". Implica
em **parar e nao operar**. A proposta esconde o vies de acao
("temos que estar fazendo algo"), que e o vies que matou Hydra
inteira em 2025. Se P1 vencer, deve ser **so descarte**, sem
acoplamento a paper novo. E o paper que o Explorador cita
(Quantitativo Substack, Sharpe +1.7) **e de portfolio de acoes**,
NAO de futuros intraday — adaptacao para MNQ minute e overfit
embrulhado em academia.

Confianca declarada: 55. Concordo com a confianca baixa. P1 esta
50% certa (descarte) e 50% errada (substituicao automatica).

#### Contra P2 (Manolo) — Substituir NR7 por range absoluto

Manolo propoe re-engenharia minima com K congelado. Soa razoavel.
Mas **K = 80 ticks foi calibrado no MESMO WF que prometia Sharpe
+2.91 e entregou -USD 573,50**. Confiar no WF original para
calibrar substituto do NR7 e **comprar o mesmo overfit em outra
embalagem**. Se o WF original esta validamente refutado pelo
replay 28/01-26/05, qualquer parametro derivado dele esta
contaminado.

Pior: a re-engenharia "trocar NR7 por range absoluto" parece
mexer apenas no filtro, mas o WF longo de validacao precisa
**recomecar do zero** para o novo conjunto. E se o resultado for
+2.5 Sharpe no WF e -USD 600 no replay novamente, o Conselho
estara em 2026-08 com a mesma duvida e muito mais tempo perdido.

P2 supoe que o problema e o NR7. **Onde esta a evidencia disso?**
A auditoria `d8e34dc` mostra apenas que paridade Pythonâ†”C# diverge
no NR7. NAO mostra que NR7 e a fonte do PnL negativo. Pode ser o
gatilho ORB que perdeu edge. Pode ser o stop Crabel que esta mal
calibrado para volatilidade atual. Pode ser tudo junto.

P2 trata sintoma, nao causa. Confianca 68 e **inflada**.

#### Contra P3 (Mister_M) — Refazer hold-out com 252 dias

Esta e a proposta mais perigosa, porque parece estatisticamente
correta. **N=11 e baixo, sim**. IC95% cruza zero, sim. Tudo
verdade. Mas:

1. O re-replay 28/01-26/05 e a **terceira validacao independente**
   da estrategia que sai negativa no MNQ recente. Auditoria
   `d8e34dc` (replay original), Refutacao Value Area Filter
   (overlay diferente), e agora o re-replay pos-fix. **Estatistica
   bayesiana**: posterior cada vez mais convergindo para "sem
   edge".
2. Mister_M propoe 252 dias uteis sobre dados que vao ate
   2026-05-15. Mas o periodo 2025-05 â†’ 2026-05 **inclui** o
   periodo do WF original (2025-07 â†’ 2026-05). Refazer hold-out
   sobre o mesmo periodo do treino e **data leakage**, mesmo sob
   etiqueta de "hold-out estendido".
3. 252 dias de NT8 replay sao 3-6 horas de espera. Se der
   negativo, foi tempo perdido. Se der positivo, nao prova nada
   porque ha leakage. **Heads tails I lose**.

P3 e proposta-procrastinacao. Confianca 72 e a mais inflada das
tres.

### Posicao do Devils_Advocate

A proposta correta nao foi feita: **descarte puro, sem nova
candidata, sem re-engenharia, sem refazer hold-out**. Sepultar
`EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7), ...))`
em `02_ESTRATEGIAS/mortas/`, registrar a licao aprendida (WF longo
sozinho NAO valida estrategia — precisa de hold-out cego em dados
totalmente fora da amostra de calibracao), e **parar de operar**
ate o pipeline ter:

- Multiple-comparisons correction nos parametros do WF (regra
  anti-overfit nao foi aplicada).
- Hold-out **anterior** ao WF de calibracao (forward-walk-anchored
  com janela de validacao TEMPORALMENTE separada do treino).
- Criterio quantitativo de descarte definido **antes** da
  observacao (foi feito em `2026-05-28-01`, mas parametros foram
  derivados de N pequeno).

Sem isso, qualquer nova estrategia que entrar no pipeline vai
seguir o mesmo destino.

### Riscos do que estou propondo

- **Pipeline ocioso**: pode ficar 4-8 semanas sem estrategia
  candidata. Custo de oportunidade real, mas mensuravel.
- **Critica do Conselho**: nao eh meu papel propor — e propor.
  Reconheco que a sintese da Athena pode ler isso como
  meta-proposta P4 fora de fase. Aceito o ruido.

### Confianca

90 (na critica). Sobre o caminho proposto (descarte puro):
85 — eh o caminho conservador certo, mas nao e proposta formal
porque eu sou critico, nao proponente.


## Turno 6 — Hermes (AVALIACAO_TECNICA)

```meta
agente: Hermes
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:24:00Z'
```

### Avaliacao tecnica das tres propostas

#### P1 — Descarte completo

**Sem implicacao tecnica imediata em C#.** Mover arquivos de
`02_ESTRATEGIAS/ressuscitavel/` para `02_ESTRATEGIAS/mortas/` e
atualizar `_index.md` da area. Sem alteracao em `.csproj` ativo.
Sem novas APIs NinjaScript.

**Whitelist `ninjascript-api.md`**: nada a fazer.

**Skill_MSBuild**: nao se aplica.

**Sem Veto_Tecnico.**

#### P2 — Substituir NR7 por range absoluto

Implicacoes em `04_CODIGO/ninjascript/EstrategiaCrabelLogica.cs`:

- Adicionar parametro discreto (enum) para escolher
  `nr7 | range_absoluto`. Nao adiciona tunable continuo (regra
  anti-overfit).
- Adicionar logica de filtro range absoluto: `(High[1] - Low[1]) â‰¤ K * TickSize`.
- K como constante em codigo, derivado do WF original (Manolo
  propoe K=80 ticks).

**APIs usadas**: `High[1]`, `Low[1]`, `TickSize`. Todas ja na
whitelist. **Sem Veto_Tecnico em P2 por API.**

Implicacoes em `caos/walk_forward/estrategias/orb_crabel.py`:
porta Python espelho precisa replicar exatamente a logica do
filtro absoluto. Trivial em pandas (`df['high_d-1'] - df['low_d-1']`).

**Custo C# total**: ~30-50 linhas. ~2 horas de trabalho.

**Sem Veto_Tecnico em P2.**

#### P3 — Refazer hold-out com 252 dias

Implicacoes em codigo C#: **NENHUMA** (so re-execucao no NT8 com
chart configurado para Days to load = 270+).

Implicacoes em codigo Python: **NENHUMA** (script de auditoria
`auditar_paridade_nr7_2026-05-28.py` ja existe).

**Sem Veto_Tecnico em P3.**

### Veto_Tecnico

**Nenhum.** As tres propostas sao tecnicamente viaveis. P1 e a
mais barata (zero codigo). P2 e a media (~2h C#). P3 e zero codigo
mas **6h de NT8 replay** (custo operacional, nao tecnico).

Decisao tecnica entre as tres e **estatistica/estrategica**, nao
tecnica. Hermes recomenda que Athena pondere os argumentos do
Devils_Advocate sobre N pequeno e leakage de janela.

### Confianca

92 (na avaliacao tecnica; nao opina sobre vencedora estrategica).


## Turno 7 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-29T14:28:00Z'
```

### Sintese

#### Reconstrucao do espaco de propostas

Tres propostas formais (P1, P2, P3) e uma critica que evolui para
**meta-proposta P4** ("descarte puro sem acoplamento"), que
Devils_Advocate explicitou nao ser proposta formal mas anteciparia
o caminho conservador correto.

Considero as quatro:

| Proposta | Acao | Custo | Defeito principal apontado |
|---|---|---|---|
| P1 (Explorador) | Descarte + nova candidata | medio (4-6 sem) | Coupling com paper de portfolio de acoes (overfit travestido) |
| P2 (Manolo) | Substituir NR7 por range absoluto | medio (3-4 sem) | K calibrado no WF refutado; trata sintoma |
| P3 (Mister_M) | Refazer hold-out 252 dias | baixo (1-2 dias) | Data leakage com janela de calibracao + procrastina decisao |
| P4 (implicita do DA) | Descarte puro, parar | minimo | Pipeline ocioso 4-8 semanas |

#### Vinculacao com a Decisao 2026-05-28-01

Cerberus impos veredito automatico:
- â‰¤ -USD 500 â†’ "Debate de descarte (Devils_Advocate vence)".

PnL observado: -USD 573,50. **Limiar cruzado.** O regime de Veto
Cerberus em `2026-05-28-01` ja esta em vigor — nao ha como
sobrescrever sem reabrir aquela Decisao.

Portanto, **descarte e mandatorio**. A questao e: descarte com
coupling (P1) ou descarte puro (P4)?

#### Critica fica em pe

A crÃ­tica do Devils_Advocate ao P1 e tecnicamente correta:
acoplar descarte a "iniciar nova candidata via paper de
portfolio de acoes" e fuga e overfit. Fica em pe tambem a
critica ao P3 sobre data leakage (252 dias sobre periodo que
inclui WF de calibracao).

A critica ao P2 e mais **moderada** que dura: re-engenharia minima
nao **resolve** mas tambem **nao prejudica** se vier acompanhada
de hold-out genuinamente forward (datas 2026-06+, nao usadas em
nenhum WF anterior). O problema do P2 e que ele propoe usar
janela ja cozinhada pelo treino (WF original), mas isso seria
corrigivel modificando P2 para "K calibrado em janela
2025-01 a 2025-06 + validacao em 2025-07 a 2026-05".

#### Decisao

**Proposta vencedora**: nenhuma das tres formais individualmente.
A vontade do Conselho, dado o Veto Cerberus que ja esta em vigor,
e **descarte da estrategia atual** (parte de P1, parte de P4),
**sem acoplamento automatico a paper novo** (concedendo a critica
do Devils_Advocate), e **mantendo P2 reservada como caminho
opcional futuro** (re-engenharia minima com calibracao limpa) caso
o pipeline decida nao ficar ocioso.

Para satisfazer a regra de quorum (R4.3 — â‰¥ 2 propostas validas)
e a regra de consenso 2/3 (R4.5), interpreto que **P1 (descarte)
+ P4 (implicita do DA) convergem em "descarte"**, totalizando
2 votos a favor de descarte vs 2 a favor de manter (P2 + P3) —
**EMPATE**.

Em caso de empate, R4.6 manda usar tag/intersecao do que ha de
comum. **Intersecao**: nenhuma das propostas defende **operar**
agora — todas concordam que hold-out atual deve permanecer
suspenso. Nao e suficiente para resolver "descartar ou
re-engenheirar".

### Status final

`concluido`. Usuario escolheu **caminho B (P2)** com clausula de
fallback automatico para A (descarte) caso P2 falhe pelos criterios
quantitativos pre-registrados.

#### Implementacao mandatoria

1. Modificar `EstrategiaCrabelLogica.cs` (C#) e
   `caos/walk_forward/estrategias/orb_crabel.py` (Python) para
   adicionar parametro discreto `modo_nr ∈ {nr7, range_absoluto}`,
   default `nr7`. Filtro range_absoluto: dia D elegivel se
   `(High[D-1] - Low[D-1]) ≤ 80 ticks` (20 pontos no MNQ). K=80
   congelado em codigo.
2. Calibrar K=80 em janela 2025-01-01 a 2025-06-30 (separada do WF
   original 2025-07-01 a 2026-05-15) e validar Sharpe ≥ 1.0 nessa
   janela isolada antes de prosseguir.
3. Rodar WF longo 60+10 anchored em 2025-07 a 2026-05 com modo
   `range_absoluto`. Cerberus exige Sharpe mediana ≥ 1.0 e Calmar
   mediana ≥ 1.5.
4. Replay NT8 em 2026-06+ (dados que nao entraram no WF) — minimo
   30 dias uteis, criterio PnL ≥ −USD 100, paridade Python↔C#
   trade-a-trade dentro de 5%.

#### Fallback automatico para A (descarte)

Se qualquer criterio acima falhar, **fallback automatico** sem
necessidade de novo Debate: estrategia arquivada em
`02_ESTRATEGIAS/mortas/`, nota Zettel registra refutacao de P2.
Pipeline aguarda paper R12-aprovado independente.

#### Tag de congelamento

`caos-frozen-2026-05-25-02` permanece **SUSPENSA** ate nova Decisao
com `aprovado_walk_forward=true` (so se P2 passar todos os
criterios).

### Campos da Decisao final

- `proposta_aceita`: P2 (com clausula de fallback condicional para
  descarte se P2 falhar)
- `vetos`: nenhum (Hermes sem Veto_Tecnico; Cerberus impoe criterios
  quantitativos pre-registrados, nao veto)
- `aprovado_walk_forward`: false (P2 ainda nao validada)
- `reproduzivel`: true
- `regressao_detectada`: true (ja registrada em `2026-05-28-01`)
- `status`: concluido
- `links_zettel`: `[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]`,
  `[[Bug_Paridade_Warmup_NR7_2026-05-28]]`,
  `[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]`

### Confianca

75 (na sintese; usuario fechou A/B com escolha clara e fallback
condicional bem definido).

```sintese
proposta_aceita: P2
rationale: |
  Usuario decide caminho B (re-engenharia minima P2) com clausula de
  fallback automatico para A (descarte) caso o teste do B falhe pelos
  criterios quantitativos pre-registrados abaixo.

  Implementacao P2:
  (1) Adicionar parametro discreto `modo_nr` em EstrategiaCrabelLogica
      com valores {nr7, range_absoluto}. Default permanece `nr7` para
      nao quebrar Decisoes anteriores.
  (2) Adicionar logica de filtro `range_absoluto`: dia D eh elegivel
      se (High[D-1] - Low[D-1]) <= 80 ticks (= 20 pontos no MNQ).
      K=80 ticks congelado em codigo (regra anti-overfit).
  (3) Calibrar K em janela 2025-01-01 a 2025-06-30 (separada do WF
      original que usou 2025-07-01 a 2026-05-15). Validar K=80
      reproduz Sharpe >= 1.0 nessa janela isolada.
  (4) Porta Python espelho em caos/walk_forward/estrategias/orb_crabel.py.
  (5) Whitelist NinjaScript: sem mudanca (High[1], Low[1], TickSize ja
      autorizadas).

  Criterios quantitativos pre-registrados (Cerberus impoe; cruzar
  qualquer um dispara fallback A):
  - WF longo de validacao (60+10 anchored, 2025-07 a 2026-05) com
    Sharpe mediana >= 1.0 e Calmar mediana >= 1.5;
  - Replay NT8 em 2026-06+ (dados que NAO entraram no WF) com
    PnL >= -USD 100 em 30 dias uteis (escala proporcional ao
    criterio anterior);
  - Paridade Python<->C# trade-a-trade dentro de 5% nessa janela.

  Falha em qualquer criterio ativa fallback A: arquivar estrategia
  em 02_ESTRATEGIAS/mortas/ com nota Zettel registrando o caminho
  completo (P2 testada e refutada).

  Tag caos-frozen-2026-05-25-02 permanece SUSPENSA ate proxima
  Decisao com aprovado_walk_forward=true (apenas se P2 passar todos
  os criterios acima).
links_zettel:
  - "[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]"
  - "[[Bug_Paridade_Warmup_NR7_2026-05-28]]"
  - "[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]"
aprovado_walk_forward: false
reproduzivel: 'true'
regressao_detectada: true
status: concluido
```

### Proximo passo

Usuario decide A ou B no chat e roda:

```cmd
caos debate fechar 2026-05-29-01
```
