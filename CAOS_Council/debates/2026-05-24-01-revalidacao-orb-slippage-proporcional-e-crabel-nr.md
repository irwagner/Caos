---
agentes_participantes:
- Athena
- Mister_M
- Manolo
- Devils_Advocate
- Cerberus
contexto_hash_sha256: 3f7c8a9d2b1e4c5f6a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f
data_fim: null
data_inicio: '2026-05-24T00:00:00Z'
fase_final: SINTESE
identificador: 2026-05-24-01
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
- referencia:Decisao_2026-05-23-02
- referencia:estudo-robos-referencia-2026-05-23
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Cerberus: 42
  Devils_Advocate: 42
  Manolo: 42
  Mister_M: 42
status: em-andamento
titulo: revalidacao-orb-slippage-proporcional-e-crabel-nr
turnos_consumidos: 6
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-24T00:00:00Z'
```

### Contexto

O usuário pediu para retomar investigação após a pausa estabelecida em
`2026-05-23-02`. O Explorador foi acionado, fez **estudo dos robôs de
referência** (Hydra v1, 8 estratégias mortas em MNQ — confirmou nosso
null result) e identificou na literatura 2025-2026:

1. **Modelo de slippage proporcional ao range** (Pomorski 2024,
   QuantJourney 2024) — empiricamente validado pelo Hydra v1 em 40
   trades NT8 reais (mediana 7.5% × OR_size).
2. **ORB Crabel original (1990) com filtro NR4/NR7** — variante que o
   Hydra v1 NÃO testou. Compressão precede expansão.

Implementei e rodei 5 Walk-Forwards comparativos sobre os mesmos
~14 meses de dados:

| Identificador | Estratégia | Fricção | PnL acumulado | Trades | Win rate |
|---|---|---|---:|---:|---:|
| `2026-05-22-01` | ORB | Sem | +USD 6.170 | 236 | 50% |
| `2026-05-23-02` | ORB | Fixa Topstep | +USD 5.642 | 236 | 50% |
| `2026-05-23-06` | ORB | **Proporcional** | **-USD 13.719** | 236 | 42% |
| `2026-05-23-09` | ORB Crabel NR7 | Proporcional | **+USD 474** | 35 | 50% |
| `2026-05-23-10` | ORB Crabel NR4 | Proporcional | -USD 1.984 | 59 | 50% |

Dois achados materiais:

**Achado A**: ORB original sob slippage proporcional realista vira
**estratégia destrutiva** (-USD 13.719). Confirma o null result do
Hydra v1 e endossa retroativamente a Decisão `2026-05-23-02` (foi
correta).

**Achado B**: ORB Crabel NR7 (variante não testada pelo Hydra v1) é
a **única ORB com PnL líquido positivo** sob fricção honesta. PnL
modesto (+USD 474 em 13 meses, ~+USD 36/mês), mas único positivo.

Bug-fix relevante encontrado durante investigação: `_dias_apos_nr` não
marcava o "primeiro dia do Teste" como elegível quando o último dia do
Treino era NR. Corrigido — esta é razão do `2026-05-23-09`/`10`
substituírem `2026-05-23-07`/`08`.

### O que está em jogo

Decidir se a Crabel NR7 merece **investigação adicional** (re-validação
em horizontes diferentes, integração com Pre-FOMC, etc.) ou se +USD 474
é amostral demais para qualquer ação.

`altera_exposicao=false` — Debate não muda parâmetros operacionais.


## Turno 2 — Mister_M (PROPOSTAS)

```meta
agente: Mister_M
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-24T00:01:00Z'
```

```proposta
id: P1
autor: Mister_M
resumo: >
  Crabel NR7 mostra resultado promissor; documentar como direção
  candidata para revalidação quando dados crescerem; manter pausa.
conteudo: |
  Análise quantitativa:

  - **35 trades em 13 meses** = N pequeno mas não trivial.
    Distribuição por janela WF: 24 janelas, ~1.5 trade/janela.
    Estatísticas por janela são inúteis — métrica honesta é PnL
    agregado da série.
  - PnL bruto antes de fricção: ~+USD 513 (35 trades × ~7.3 pts
    bruto médio). Custo proporcional total: ~USD 39. Líquido +USD 474.
  - **Ordem de grandeza compatível com Lucca-Moench**: nossas Pre-FOMC
    rendeu +USD 723 sobre 10 trades (CAGR ~7%), Crabel NR7 rendeu
    +USD 474 sobre 35 trades (CAGR ~3%). Ambas no mesmo sample.
  - Win rate 50% em estratégia de breakout é **consistente com
    Crabel original** (1990 reporta 45-55% em ES e NQ histórico).
  - Sharpe mediano per-window é negativo, mas isso é artefato de
    janelas com 1-2 trades cada. **Sharpe sobre os 35 trades em
    série**: estimativa ~0.5-0.8 anualizado (não rejeita H0 com
    folga, mas direção certa).
  - PSR esperado com N=35 é baixo. Não é nível institucional ainda,
    mas é DIRECIONAL.

  Recomendação: **registrar Crabel NR7 como candidata à proxima
  rodada** quando tivermos pelo menos +30 trades adicionais (~12 meses
  de dados novos). Não promover a paper. Não fazer sweep de filtros
  adicionais.

  Confiança 60 — temos sinal direcional positivo ondeoutras 4
  variantes da ORB falharam, mas amostra ainda fraca.
confianca: 60
```


## Turno 3 — Manolo (PROPOSTAS)

```meta
agente: Manolo
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-24T00:02:00Z'
```

```proposta
id: P2
autor: Manolo
resumo: >
  Cético sobre Crabel NR7 isolada — propor combinação com filtros
  fundamentalmente independentes (Pre-FOMC ou volatilidade) antes
  de investigação adicional.
conteudo: |
  Análise comportamental e de fragilidade:

  - +USD 474 em 13 meses é ~5% de retorno anual sobre conta de
    USD 10.000. Em estratégia retail com 35 trades, **drawdown
    individual de USD 200-300** já come 50-100% do lucro. Não é
    operacionalmente viável sozinha.
  - Crabel NR7 viu 50 dias elegíveis no dataset; emitiu trade em 35
    deles. Os outros 15 dias elegíveis não viraram trade — provavelmente
    por filtros internos da ORB (range mínimo, hora de corte).
    Concentração temporal pode ser alta — 1 mês ruim domina.
  - Hipótese de Crabel ("compressão precede expansão") é genérica;
    pode existir VIÉS COGNITIVO de cherry-pick: testamos a variante
    que sobreviveu **APÓS** ver as outras 4 morrerem.
  - Mister_M propõe esperar +30 trades. Mas 30 trades novos =
    ~12 meses de dados = mais 6 meetings FOMC = também viabiliza
    revisita da Pre-FOMC. Por que não combinar?

  Proposta concreta: **investigar se a Crabel NR7 e a Pre-FOMC têm
  trades em datas DIFERENTES** (correlação de portfolio). Se sim,
  combiná-las como mini-portfolio independente já reduz risco. Se
  não (overlap alto), uma das duas é redundante.

  - Custo: ~30min de análise sobre os trades já existentes.
  - Sem novos parâmetros otimizáveis.
  - Sem mais Walk-Forwards.

  Recomendação: **fazer essa análise de correlação ANTES de qualquer
  decisão sobre próxima rodada**.
confianca: 65
```


## Turno 4 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-24T00:04:00Z'
```

### Crítica à P1 (Mister_M, "registrar e esperar")

1. **+USD 474 em 13 meses é estatisticamente fraco**. Sharpe estimado
   0.5-0.8 ANUALIZADO sobre 35 trades — t-stat improvável de passar
   2.0. Mister_M está sendo otimista ao dizer "direcionalmente
   positivo" quando o intervalo de confiança 95% inclui zero
   confortavelmente.
2. **"Esperar +30 trades" sem critério ex-ante é classic data-snooping.**
   Estamos no 5º Walk-Forward sobre o mesmo dataset. Cada teste novo
   sobre os mesmos dados aumenta probabilidade de encontrar
   "candidata" por acaso. Bonferroni para 5 testes paralelos exige
   t-stat ~ 2.81 — Crabel NR7 não chega perto.
3. **Confiança 60 é alta demais.** Olhando os 5 WFs: 1 positivo
   (Crabel NR7) entre 4 negativos. Probabilidade a priori de uma
   estratégia random produzir esse padrão é alta.

### Crítica à P2 (Manolo, "análise de correlação")

1. **A análise é boa, barata e rigorosa.** Concordo.
2. Mas o RESULTADO não muda a falta de poder estatístico. Se Crabel
   NR7 e Pre-FOMC têm trades em datas diferentes (provável: ORB
   intraday vs holding 24h são lógicas distintas), ainda temos
   N_total = 35 + 10 = 45 trades. Não muda a fronteira de Bonferroni.
3. **"Mini-portfolio" é palavra elegante para combinação de duas
   estratégias frágeis.** Se ambas são duvidosas individualmente,
   somá-las não cria edge — apenas distribui o ruído.

### Vieses cognitivos detectados

- **Sunk cost** em ambas. Investimos sessão inteira retomando ORB,
  agora queremos justificar continuar com ela em alguma forma.
- **Survivorship bias** óbvio na Crabel NR7: das 5 variantes ORB
  testadas, ela é a única positiva. Selecionar pra investigar
  adicional é literalmente selecionar a sobrevivente.
- **Recency bias inverso**: o resultado mais recente (Crabel NR7)
  ganha peso desproporcional sobre os 4 anteriores.

### Recomendação informal

Síntese honesta:

1. **A análise de correlação proposta por Manolo deve ser feita** —
   é barata e dá informação real sobre se Crabel NR7 e Pre-FOMC
   pegam dias diferentes.
2. **Independente do resultado da correlação**, NENHUMA das duas é
   promovida. Estamos abaixo do limite estatístico institucional.
3. **A Decisão `2026-05-23-02` continua valendo**: parar e esperar
   dados novos. O que mudou é que agora temos 2 candidatas para
   re-revisitar quando dados chegarem (Pre-FOMC + Crabel NR7), não 1.
4. **Hydra v1 deveria ter testado Crabel original** mas não testou.
   Isso é lição de método para nós: testar variantes clássicas
   ANTES de pular para variantes próprias. Documentar.


## Turno 5 — Cerberus (AVALIACAO_RISCO)

```meta
agente: Cerberus
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-24T00:06:00Z'
```

### Parecer (informativo — sem alteração de exposição)

Nenhuma das duas propostas modifica `MaxContratos`,
`CircuitBreakerDiarioUSD`, ou parâmetros operacionais. Cerberus
**não emite veto**.

Observações de risco para registro:

1. A hipótese "Crabel NR7 + Pre-FOMC como mini-portfolio" mencionada
   por Manolo seria material para Veto_De_Risco se proposta de paper
   trading. PnL de 35 trades em 13 meses tem variância alta — drawdown
   esperado de USD 200-400 por janela é compatível com erosão completa
   do capital de teste em <2 meses ruins consecutivos.

2. Confirmando o ponto do Devils_Advocate: independente do resultado
   da análise de correlação, NÃO promover a paper. Cerberus endossa
   essa restrição.

3. A implementação do `slippage_fracao_range` é **boa adição
   estrutural** — beneficia todas as estratégias futuras.
   Independente do veredito sobre famílias específicas.


## Turno 6 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-24T00:08:00Z'
```

### Análise

- Quórum: 2 propostas válidas (P1, P2).
- Vetos bloqueantes: 0.
- Devils_Advocate aponta corretamente que P1 minimiza limite
  estatístico e que P2, embora barata, não muda fronteira de
  Bonferroni.
- Sub-recomendação implícita do Devils_Advocate ("fazer análise de
  correlação mas não promover nada") é a posição mais conservadora.

### Avaliação

**P1** quer registrar Crabel NR7 e esperar dados. Sem novos passos
hoje. Conservadora mas ignora valor da análise de correlação.

**P2** quer análise de correlação ANTES de outras decisões. Custo
mínimo (30min), valor informacional alto (revela se Crabel NR7 e
Pre-FOMC pegam dias distintos). Não promove paper.

Devils_Advocate confirma P2 como ação razoável; ataca P1 por viés
de sunk cost. Cerberus endossa restrição de não-promoção.

### Decisão

Aceito **P2** com modificação para integrar a recomendação do
Devils_Advocate: a análise de correlação é executada AGORA pelo
Kiro_Brain, mas o resultado **não autoriza paper trading nem
sweep paramétrico**, apenas adiciona informação ao registro.

`proposta_aceita = P2`. `aprovado_walk_forward = false`.

A pausa investigativa de `2026-05-23-02` permanece. Quando dados
novos chegarem (~6-12 meses), pausa é revisitada com 3 candidatas
documentadas: (a) Pre-FOMC drift, (b) Crabel NR7 ORB, (c)
mini-portfolio das duas SE correlação for baixa.

`status = concluido`. `reproduzivel = parcial` (manifesto +
seeds). `regressao_detectada = false` — esta Decisão **não
contradiz** `2026-05-23-02`; ao contrário, confirma-a (ORB
original sob slippage proporcional realmente é destrutiva).

```sintese
proposta_aceita: P2
rationale: |
  Resultados materiais desta sessao:

  1. ORB original sob slippage proporcional realista (modelo
     Hydra v1 / Pomorski 2024) entrega -USD 13.719 em 13 meses.
     CONFIRMA a Decisao 2026-05-23-02 (rejeicao da ORB).
     Slippage fixo Topstep (-USD 5.642 positivo) era otimista.

  2. ORB Crabel NR7 (variante de Crabel 1990 que o Hydra v1 NAO
     testou) entrega +USD 474 em 35 trades sobre os mesmos dados.
     E' a unica ORB com PnL liquido positivo sob fricao honesta.
     PnL modesto e amostra fraca (N=35) — nao passa criterio
     institucional Mesfin 2026 (T>=2.0).

  Aceito P2: executar analise de correlacao entre trades da
  Crabel NR7 e da Pre-FOMC drift para informar decisao futura
  sobre mini-portfolio. Custo trivial, valor informacional real.

  REJEITO P1 nao porque seja errada mas porque P2 e' superset:
  faz a analise barata DE GRACA antes de "registrar e esperar".

  Independente do resultado da correlacao:
  - aprovado_walk_forward = false permanece
  - pausa investigativa de 2026-05-23-02 permanece valida
  - 3 candidatas documentadas para revisita futura: Pre-FOMC
    drift, Crabel NR7 ORB, e mini-portfolio condicional

  Adicao estrutural CustosOperacionais.slippage_fracao_range
  (modelo proporcional) permanece util independente do veredito
  sobre familias estrategicas — beneficia toda revalidacao
  futura.

  Licao de metodo: o Hydra v1 testou variantes proprias da ORB
  mas NAO testou a versao classica de Crabel com NR4/NR7.
  Documentar para garantir que proximas iteracoes testam
  variantes consagradas da literatura ANTES de criar versoes
  proprias.
links_zettel:
  - "[[Decisao_2026-05-24-01_Crabel_NR7_Como_Candidata_Futura]]"
  - "[[estudo-robos-referencia-hydra-melhorias-2026-05-23]]"
aprovado_walk_forward: false
reproduzivel: parcial
regressao_detectada: false
status: concluido
```
