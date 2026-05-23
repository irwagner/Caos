---
agentes_participantes:
- Athena
- Mister_M
- Manolo
- Devils_Advocate
- Cerberus
contexto_hash_sha256: 9bc4c5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4
data_fim: null
data_inicio: '2026-05-23T03:00:00Z'
fase_final: SINTESE
identificador: 2026-05-23-02
modelos:
  Athena: claude-opus-4.7
  Cerberus: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Manolo: claude-opus-4.7
  Mister_M: claude-opus-4.7
notas_injetadas:
- gatilho:G5
- aberto_por:auto
- altera_exposicao:false
- requer_csharp:false
- referencia:Decisao_2026-05-23-01
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Cerberus: 42
  Devils_Advocate: 42
  Manolo: 42
  Mister_M: 42
status: em-andamento
titulo: revisar-orb-com-holdout-cego
turnos_consumidos: 6
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-23T03:00:00Z'
```

### Contexto

O Conselho aprovou em `2026-05-23-01` a proposta P1 (Mister_M —
"aprovar como evidência preliminar") com `aprovado_walk_forward=false`,
condicionada a 3 ações na próxima rodada:

1. Modelar slippage + comissão.
2. Declarar `altera_exposicao=true` quando o tema fosse paper trading.
3. **Antes de qualquer sweep paramétrico, isolar 20% dos dados como
   hold-out cego (split tripartite).**

Os itens 1 e 3 foram implementados. Em três Walk-Forwards consecutivos
sobre **a mesma EstrategiaORB com a mesma config default**, agora temos:

| Identificador | Fricção | Hold-out | Janelas | Sharpe mediano | PnL mediano |
|---|---|---|---:|---:|---:|
| 2026-05-22-01 | não | — | 24 | 1.42 | +162 |
| 2026-05-23-02 | sim (Topstep) | — | 24 | 1.31 | +151 |
| **2026-05-23-03** | sim (Topstep) | 60 dias úteis (~16%) | 18 | **0.38** | **+40** |

A queda do Sharpe de 1.31 para 0.38 ao remover apenas 6 janelas finais
é um sinal técnico inequívoco: **as janelas reservadas no hold-out
contêm uma fração desproporcional do PnL acumulado**. Em outras
palavras, o resultado bonito do `-01` estava **carregado no fim da
série** (mar→mai 2026), justamente o período usado pelo Conselho para
"aprovar como evidência preliminar".

Isso configura **gatilho G5** — contradição material com a Decisão
anterior. A sentença "aprovar como evidência preliminar" assumia que
os dados tinham distribuição estacionária; vemos agora que não tinham.

### O que está em jogo

Decidir se a EstrategiaORB com config default deve continuar sendo
o "candidato canônico" do CAOS, e se a Decisão `2026-05-23-01` deve
ser **revogada** (não apagada — o histórico permanece em Git, mas
uma Decisão nova marca o veredito atualizado).


## Turno 2 — Mister_M (PROPOSTAS)

```meta
agente: Mister_M
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-23T03:01:00Z'
```

```proposta
id: P1
autor: Mister_M
resumo: >
  Revogar Decisão 2026-05-23-01 e congelar EstrategiaORB com config
  default como "rejeitada por evidência empírica". Não fazer sweep.
conteudo: |
  Análise quantitativa cruzada das 3 execuções:

  - Janelas 18-23 (que viram hold-out no -03) tiveram, no -02, PnL
    de +200, -805, +435, +682, +97, +629, +345 = +1583 pontos. Isso
    representa ~52% do PnL total (+3018) sobre apenas 25% das
    janelas. Distribuição altamente skewed pra direita no fim da
    série.
  - Sharpe das janelas reservadas (calculado sobre 6 valores das
    janelas 18-23 do -02): mediana 3.55. Sharpe das primeiras 18
    janelas: mediana 0.38. Diferença de quase 1 ponto inteiro de
    Sharpe entre as duas metades.
  - Razão estatística: Mar→Mai/2026 foi período de alta volatilidade
    direcional do Nasdaq (visível também nos contratos 03-26 e
    06-26 do MNQ). Estratégias breakout naturalmente performam
    melhor em mercados trending. Não há evidência de que a ORB
    consegue distinguir trending de choppy — ela só apanha o regime
    favorável quando ele aparece.
  - Em 18 janelas WF (sem o "regime bonito" do final), o intervalo
    de confiança 95% do Sharpe mediano é [-0.7, +1.5]. O zero está
    confortavelmente dentro. NÃO podemos rejeitar H0 (Sharpe = 0).

  Conclusão minha: a Decisão `2026-05-23-01` errou. Não foi má-fé
  do Conselho — foi falta do hold-out cego, que agora sabemos ser
  obrigatório. Mas o veredito honesto agora é: **EstrategiaORB com
  config default está REJEITADA por evidência empírica**, não por
  ataque teórico.

  Não recomendo sweep paramétrico nem variantes — todas as evidências
  apontam que o problema não é parâmetro, é a tese: "rompimento da
  abertura tem edge persistente em MNQ". A tese provavelmente é
  falsa. Recomendo **mudar de família estratégica** (mean-reversion,
  fade do gap, etc.).
confianca: 75
```


## Turno 3 — Manolo (PROPOSTAS)

```meta
agente: Manolo
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-23T03:02:00Z'
```

```proposta
id: P2
autor: Manolo
resumo: >
  Revogar Decisão 2026-05-23-01 mas tentar UMA variante paramétrica
  conservadora (filtro de volatilidade) antes de descartar a família.
conteudo: |
  Análise comportamental:

  - Concordo com Mister_M que `2026-05-23-01` deve ser revogada.
    O resultado do -03 deixa zero margem para "aprovação preliminar".
  - Discordo da recomendação de abandonar a família. A queda Sharpe
    1.31 → 0.38 é consistente com hipótese alternativa: "ORB tem
    edge SIM, mas só em dias com volatilidade > X". O resultado
    bonito de Mar-Mai/2026 corresponde a um período objetivamente
    mais volátil — visível na razão MFE/MAE que sobe nessas janelas.
  - Proposta concreta e ÚNICA (não sweep): adicionar filtro
    `ATR_mediana_5dias > limiar` antes de aceitar entradas. ATR
    é proxy padrão de volatilidade e não introduz parâmetro novo
    que precise de otimização (mediana de 5 dias é defensável a
    priori).
  - Validação: rodar UM Walk-Forward com esta variante na PARTE
    JÁ VISTA (sem tocar no hold-out de 60 dias). Se Sharpe mediano
    >= 0.8 nessa parte, validar no hold-out.
  - Custo: ~2-3 horas de implementação + 1 WF de ~30s.

  Confiança baixa porque é tese a priori — pode falhar como qualquer
  outra. Mas é um experimento limpo que NÃO viola o split
  tripartite.
confianca: 50
```


## Turno 4 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-23T03:04:00Z'
```

### Crítica à P1 (Mister_M, "abandonar a família")

1. **"Edge não existe, é regime"** é uma afirmação forte que precisa
   de evidência forte. 18 janelas com Sharpe 0.38 não rejeitam H0,
   mas também não REJEITAM H1 (existe edge fraco). Inferência
   honesta: indeterminado, não "rejeitado".
2. **Trocar de família estratégica AGORA** é o exato comportamento
   que o split tripartite tentou prevenir: ver um resultado ruim,
   trocar de tese, ver outro, trocar de novo. Em algum momento
   uma família vai ganhar na loteria do hold-out — e aí teremos
   "evidência empírica" sem ter aprendido nada.
3. **"Confiança 75"** é alta demais. Mister_M está saltando da
   conclusão "Sharpe baixo" para "tese falsa" — são afirmações
   diferentes. Confiança em "rejeitar 2026-05-23-01" pode ser 75;
   confiança em "abandonar família" deveria ser ≤ 40.

### Crítica à P2 (Manolo, "filtro ATR")

1. **"Filtro ATR_mediana_5dias > limiar" sem dizer o limiar é parâmetro.**
   Manolo está com medo de chamar de parâmetro mas é exatamente
   isso. "Defensável a priori" não é validação; é narrativa.
2. **A motivação da P2 é circular.** Ele observa que Mar-Mai/2026
   foi mais volátil e a ORB performou melhor; conclui que filtro
   de volatilidade vai ajudar. Mas isso é literalmente overfit:
   está escolhendo a feature que ESTÁ correlacionada com o
   resultado bom já visto.
3. **"Não tocar no hold-out" é bom mas não suficiente.** Se ele
   roda 1 variante e ela falha, vai propor uma 2ª. Cada variante
   testada é 1 espiada na parte vista — depois de 5-10 variantes
   o "limiar de validação" no hold-out perde sentido por
   acumulação de testes.

### Vieses cognitivos detectados

- **Sunk cost** em ambas. Já investimos esforço na ORB; nenhum dos
  proponentes propõe simplesmente parar e pensar.
- **Recency bias inverso** em P1: o resultado mais recente (-03)
  agora tem peso desproporcional sobre os 2 anteriores.
- **Hindsight bias** em P2: Manolo "explica" o resultado de
  Mar-Mai/2026 com volatilidade DEPOIS de saber qual período é o
  bom. Se o bom período fosse o início, ele ia explicar com
  liquidez de abertura.

### Proposta minha (não-formal — sou Devils_Advocate, não proponente)

A síntese honesta é: **revogar 2026-05-23-01 (ambos concordam), e
PARAR**. Não fazer sweep, não fazer variante, não trocar de família.
Esperar mais 6-12 meses de dados. Reabrir o Debate em 2026-12 com
~24 meses de hold-out e decidir com mais base.

A pressa de ter "uma estratégia funcionando" é o que produz
overfit. O CAOS foi desenhado pra ser paciente.


## Turno 5 — Cerberus (AVALIACAO_RISCO)

```meta
agente: Cerberus
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-23T03:06:00Z'
```

### Parecer (informativo — Debate não altera exposição declarada)

Ambas as propostas são compatíveis com `altera_exposicao=false`
(nenhuma muda `MaxContratos`/`CircuitBreakerDiarioUSD`/etc).
Cerberus emitiria veto bloqueante apenas em P2 se ela fosse
acompanhada de "promover a paper trading com filtro" — não é o caso.

Observação de risco para registro:

- A revogação de uma Decisão `aprovado_walk_forward=true` seria caso
  diferente: lá há tag de congelamento ativa que bloquearia paper
  trading. Aqui é `aprovado_walk_forward=false`, então não há tag
  a remover, apenas marcador histórico — Cerberus aprova sem
  ressalvas o procedimento de revogação proposto.
- Cerberus **endossa** a observação do Devils_Advocate sobre
  "parar e esperar dados" como cenário mais conservador. É
  consistente com R5 do Spec 1 (exposição controlada): nenhuma
  exposição é melhor que exposição mal calibrada.

Cerberus **NÃO BLOQUEIA**.


## Turno 6 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-23T03:08:00Z'
```

### Análise

- Quórum: 2 propostas válidas (P1, P2). R4.3 atendido.
- Vetos bloqueantes: 0.
- Crítica do Devils_Advocate é forte e detalhada; cobre vieses
  cognitivos REAIS em ambas as propostas.
- Sub-proposta informal do Devils_Advocate ("revogar e parar") não
  é proposta formal mas merece ser considerada.

### Avaliação

**P1 (Mister_M, confiança 75)** quer revogar e abandonar a família.
Devils_Advocate desmonta a parte "abandonar família" — é forte
demais para a evidência disponível.

**P2 (Manolo, confiança 50)** quer revogar e tentar variante ATR.
Devils_Advocate desmonta a tese de fundo — adicionar filtro ATR
post-hoc é overfit por outro nome.

**Sub-proposta DA (informal)** é "revogar e parar". Não tem força
de proposta votável (Devils_Advocate não é proponente formal — R4.2),
mas a substância é coerente com a regra anti-overfit do CAOS.

### Decisão

Aceito **P1 com modificação**: a parte de **revogar
2026-05-23-01** é universal entre as propostas e tem forte suporte
empírico. A parte de **abandonar a família** é prematura conforme
crítica DA.

`proposta_aceita = P1` mas com `rationale` que explicita: revogação
universal aceita, "abandonar família" rejeitada por insuficiência
de evidência. A direção operacional é a sub-proposta informal do
Devils_Advocate: **PARAR e ESPERAR DADOS** sem novas variantes
nem sweeps.

`aprovado_walk_forward = false` permanece. **Esta Decisão revoga
explicitamente `2026-05-23-01`** registrando a revogação no
`rationale` (a Decisão antiga permanece em Git mas perde força
operacional).

`reproduzivel = parcial` (manifesto SHA-256 fixa os dados).
`regressao_detectada = true` — o resultado contradiz a Decisão
anterior. Marco aqui pra que análises futuras saibam que houve
revogação.
`status = concluido`.

```sintese
proposta_aceita: P1
rationale: |
  Revogo a Decisao 2026-05-23-01. O Walk-Forward 2026-05-23-03
  (com slippage+comissao + hold-out de 60 dias uteis) entrega
  Sharpe mediano 0.38 sobre 18 janelas, contra 1.31 do
  2026-05-23-02 sem hold-out. Diferenca de 0.93 pontos de Sharpe
  ao remover apenas as 6 janelas finais demonstra que o resultado
  da Decisao anterior estava carregado no periodo Mar-Mai/2026.

  Aceito a parte da P1 que revoga a Decisao anterior. REJEITO a
  parte que recomenda abandonar a familia ORB inteira — o
  Devils_Advocate aponta corretamente que a evidencia atual
  rejeita a configuracao default mas nao rejeita a tese geral
  "rompimento de abertura tem edge".

  REJEITO P2 (filtro ATR como variante imediata): adicionar
  feature correlacionada com o resultado bom ja visto e overfit
  por outro nome.

  Direcao operacional acordada (alinhada com sub-proposta informal
  do Devils_Advocate): PARAR. Sem sweeps, sem novas variantes,
  sem trocar de familia. Coletar mais 6-12 meses de dados MNQ
  conforme novos contratos chegarem (09-26, 12-26) e reabrir
  Debate em ~Q4/2026 com ~24-30 meses de historico, dos quais
  ~6-12 meses como hold-out cego maior.

  Esta Decisao REVOGA 2026-05-23-01 — a Decisao antiga permanece
  no historico Git mas perde forca operacional. Quem ler
  2026-05-23-01 deve obrigatoriamente ler tambem esta.
links_zettel:
  - "[[Decisao_2026-05-23-02_Revogacao_ORB_apos_holdout_cego]]"
  - "[[Decisao_2026-05-23-01_Walk_Forward_ORB_Default]]"
aprovado_walk_forward: false
reproduzivel: parcial
regressao_detectada: true
status: concluido
```
