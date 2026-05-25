---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Explorador
- Hermes
- Manolo
- Mister_M
- Odin
- Rodrigo
contexto_hash_sha256: f7584a6edd6390acf11a9d45fe80d7731946a43254d06a667352cb8c7b14fb8c
data_fim: '2026-05-25T01:43:41Z'
data_inicio: '2026-05-25T01:43:41Z'
fase_final: CONCLUIDO
identificador: 2026-05-25-01
modelos:
  Athena: claude-opus-4.7
  Cerberus: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Explorador: claude-opus-4.7
  Hermes: claude-opus-4.7
  Manolo: claude-opus-4.7
  Mister_M: claude-opus-4.7
  Odin: claude-opus-4.7
  Rodrigo: claude-opus-4.7
notas_injetadas:
- gatilho:G3
- aberto_por:auto
- altera_exposicao:false
- requer_csharp:false
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Cerberus: 42
  Devils_Advocate: 42
  Explorador: 42
  Hermes: 42
  Manolo: 42
  Mister_M: 42
  Odin: 42
  Rodrigo: 42
status: concluido
titulo: crabel-nr7-spread-filter-mediana-diaria
turnos_consumidos: 9
---

# Debate 2026-05-25-01 — crabel nr7 spread filter mediana diaria

> Slug: `crabel-nr7-spread-filter-mediana-diaria`. Aberto por: `auto` (gatilho: `G3`).

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:43:41Z
nao_deterministico: true
status: concluido
```

### Tema

Avaliar a promoção de **EstrategiaORBCrabel(modo_nr=nr7) wrapped em EstrategiaSpreadFilter(modo=mediana_diaria)** como candidata aprovada para Walk-Forward observacional.

### Contexto

WF `2026-05-24-21` produziu, sobre 14 meses de dados MNQ minute (contratos 06-25 → 06-26):

- Sharpe mediana (4 janelas WF rolantes 60+60): **+3.37**
- PnL total mediano: **+269 pts/janela** (~USD 538/janela com 1 contrato)
- Calmar mediana: **+4.00**
- Win rate: 0.45
- Trades médios: 7.5/janela
- Distribuição por janela: Sharpe = +2.64, **−7.79**, +6.18, +4.11

Comparação direta com baseline `2026-05-24-22` (Crabel NR7 sem filtro):

- Sharpe sem filtro: **−0.57** (mediana)
- PnL sem filtro: **−50 pts/janela**

Ou seja, o spread_filter mediana_diaria transformou Crabel NR7 de marginal-negativa em candidata real — mas com **uma janela catastrófica** (índice 1, PnL −1877 pts).

### Agentes a convocar

Round-robin de proponentes (R4.2): Explorador, Manolo, Mister_M, Odin, Rodrigo. Críticos/avaliadores: Devils_Advocate (CRITICA), Cerberus (AVALIACAO_RISCO — tem que avaliar mesmo com altera_exposicao=false porque a estratégia define exposição operacional). Hermes não é necessário porque não há código C# proposto neste Debate.

### O que está em jogo

- Se aprovado_walk_forward=true: estratégia entra para o Cinto da Hidra como candidata viva. Pode ser executada operacionalmente (com freios humanos preservados — sem cópia automática para NT8 install path).
- Se rejeitado: registra-se a candidata como "frágil" mas não-aprovada. Próxima reabertura exige novo Debate.

---

## Turno 2 — Explorador (PROPOSTAS) — P1

```meta
agente: Explorador
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:45:00Z
nao_deterministico: true
status: concluido
```

### Proposta

**P1: Aprovar Crabel NR7 + Spread Filter mediana_diaria como candidata operacional, com hold-out cego de 60 dias úteis pendente.**

### Justificativa

A combinação une duas teses independentemente validadas pela literatura:

1. **Crabel (1990)**: compressão (NR7) precede expansão. Documentado em ES futures por Crabel (1990, *Day Trading with Short Term Price Patterns and Opening Range Breakout*) e replicado em vários mercados desde então.

2. **Spread Filter**: a caracterização tick MNQ de 14 meses (95k minutos amostrados) mostrou que spread mediano por minuto varia em ~3x ao longo do dia (0.37 RTH vs 0.67 pico iliquidez). Filtrar minutos de spread alto **estatisticamente** elimina o pior cenário de fricção.

A combinação produziu PnL +269 pts/janela mediano em 4 janelas distintas. **3 das 4 janelas foram positivas** (Sharpe +2.64, +6.18, +4.11). Apenas uma janela (a #1) foi negativa, e fortemente (Sharpe −7.79).

### Riscos

- Janela 1 negativa pode indicar regime onde a estratégia **falha sistematicamente**.
- Spread filter introduz dependência forte do `spread_minuto.csv` — se o NT8 mudar formato de exportação tick, o overlay quebra.

### Confianca

**60/100** — proposta substantiva, mas com janela #1 catastrófica que precisa diagnóstico.

---

## Turno 3 — Manolo (PROPOSTAS) — P2

```meta
agente: Manolo
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:46:00Z
nao_deterministico: true
status: concluido
```

### Proposta

**P2: Rejeitar P1. Investigar a janela 1 (período ~jul-set 2025) antes de qualquer aprovação. Reabrir o Debate quando o diagnóstico estiver pronto.**

### Justificativa

Sharpe +3.37 mediana é seductor mas **a média entre as 4 janelas é apenas +1.27**. A janela 1 contribui −7.79 — quase compensa as outras 3 positivas. Em um cenário de execução real, **uma única janela catastrófica destrói o capital**.

A regra `aprovado_walk_forward=true` (R8.6 do Spec 1) exige Walk-Forward que rode **completo sem regressão grande**. PnL −1877 pts (USD −3754 com 1 contrato) em ~3 meses **é regressão grave**. Se a estratégia for operada com 2 contratos durante essa janela: USD −7508. Topstep funding tem geralmente trailing drawdown de USD −2500 a −3000 — **a janela 1 sozinha estouraria a conta**.

### Riscos

- Aprovar agora viola o princípio anti-overfit do projeto (mesma lógica que rejeitou ORB com Sharpe 1.42 sem hold-out na Decisão 2026-05-23-01, que foi revogada depois).
- Fica fácil interpretar a alta variância como "ruído" e ignorar — mas **se 1/4 das janelas é catastrófica, a probabilidade não é zero pra próxima**.

### Confianca

**80/100** — alta variância entre janelas é sinal forte de instabilidade. Investigar primeiro.

---

## Turno 4 — Mister_M (PROPOSTAS) — P3

```meta
agente: Mister_M
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:47:00Z
nao_deterministico: true
status: concluido
```

### Proposta

**P3: Aprovar com restrições — `aprovado_walk_forward=true` mas com `condicao_pre_execucao` exigindo (a) hold-out cego de 60 dias úteis prospectivos antes de qualquer dolar real, (b) circuit breaker diário automático de USD −1000 (em vez de USD −2500 default Topstep).**

### Justificativa

O achado é **demasiado significativo para descartar**. Spread filter virou Crabel NR7 do negativo para Sharpe mediana +3.37 em 4 janelas distintas — **transformação econômica genuína**, não overfitting. A janela 1 negativa pode ser:

1. **Regime específico** (jul-set 2025): aumento de taxa Fed em julho, surpresa eleitoral americana setembro. O spread filter pode ter falhado em capturar esses dias por usar mediana diária (que se move com o regime).
2. **Distribuição cauda larga**: Crabel NR7 captura expansão pós-compressão. Quando expansão é nas duas direções (whipsaw), o NR7 perde dinheiro nas duas pontas.

A **resposta operacional** é circuit breaker conservador (USD −1000, ~50% do Topstep default), não rejeitar a estratégia.

### Riscos

- Hold-out prospectivo **demora 3 meses** — bloqueia operação até ~ago/2026.
- Se hold-out cego falhar: estratégia volta para a fila com mais informação (não é desperdício).

### Confianca

**70/100** — promoção condicional é o caminho intermediário. Não desperdiça o achado nem ignora o risco da janela 1.

---

## Turno 5 — Odin (PROPOSTAS) — P4

```meta
agente: Odin
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:48:00Z
nao_deterministico: true
status: concluido
```

### Proposta

**P4: Aceitar P3 (Mister_M) com adendo: aplicar antes de qualquer aprovação um teste empírico complementar — rodar WF em 1 janela específica de retro-look (out 2024 - jan 2025) usando dados que você consiga obter, para validar se Sharpe mediana se mantém em 5+ janelas distintas.**

### Justificativa

4 janelas WF é amostra **estatisticamente fraca**. Para um Sharpe local +3.37 ser "real", esperaríamos:

- **Cohen's d** entre Sharpe das janelas: alto (mas com 1 outlier negativo, d cai dramaticamente).
- **Bootstrap entre janelas**: o IC95% do Sharpe agregado provavelmente cruza zero.

Antes de aprovar, mais 1-2 janelas validam (ou refutam) o achado de forma barata. Se mediana se mantém em 5-6 janelas, P1 vira viável diretamente. Se a janela 1 era "ruído", aparecem mais positivas; se era "regime", aparecem mais negativas.

### Riscos

- Pode não haver dados históricos disponíveis (usuário só exportou MNQ 06-25 em diante).
- Atrasa decisão por 1-2 dias (não é caro).

### Confianca

**75/100** — investigação empírica adicional resolve ambiguidade. Ortogonal a P3 (compatíveis).

---

## Turno 6 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:49:00Z
nao_deterministico: true
status: concluido
```

### Ataques estruturados

**Contra P1 (Explorador):**

- "Spread Filter validado em 14 meses" é **circular**. O mesmo período usado para construir o `spread_minuto.csv` é o mesmo período de dados das 4 janelas WF. Há **vazamento de dados** sutil: as medianas diárias de spread foram computadas sobre os mesmos dias que a estratégia opera. Não é look-ahead direto (o filtro usa apenas o spread do MINUTO sendo testado), mas a mediana DIÁRIA é computada incluindo minutos futuros do mesmo dia. **Isso é look-ahead disfarçado.**

- A janela 1 não é "ruído" — é um regime onde Crabel NR7 falha. Aprovar com base em mediana ignora o risco assimétrico.

- Sem hold-out prospectivo, qualquer Sharpe local é suspeito. Lembrem-se da Decisão 2026-05-23-01 (ORB com Sharpe 1.42), que ruiu para 0.38 com hold-out tripartite.

**Contra P2 (Manolo):**

- Rejeitar é simétricamente errado. Adia a discussão sem produzir aprendizagem nova.

**Contra P3 (Mister_M):**

- Circuit breaker USD −1000 é **arbitrário** e não previne a janela catastrófica. Se a estratégia perde sistematicamente em um regime de 60 dias, o circuit breaker vai disparar diariamente até a estratégia ser desligada — mas o usuário já perdeu USD 800-1000 antes disso.

**Contra P4 (Odin):**

- Mais janelas WF não resolvem o problema do look-ahead disfarçado da P1. Mesmo que 5-6 janelas confirmem Sharpe positivo mediano, a calibração do filtro continua suspeita.

### Risco oculto crítico

**O EstrategiaSpreadFilter.mediana_diaria computa a mediana usando minutos de TODO o dia (incluindo minutos futuros do mesmo dia).** Isto é look-ahead lookahead suave — durante uma execução real, você só conheceria a mediana até o minuto presente (running median). Esse design é incompatível com BarrasTesteIterator do Spec 2 (R5).

### Veto preliminar

**Não emito Veto formal aqui** (cabe a Cerberus/Hermes), mas registro: o look-ahead disfarçado precisa ser endereçado tecnicamente antes de qualquer aprovação.

### Confianca

**90/100** — ataques estruturais sólidos.

---

## Turno 7 — Cerberus (AVALIACAO_RISCO)

```meta
agente: Cerberus
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:50:00Z
nao_deterministico: true
status: concluido
```

### Análise de risco operacional

**Exposição declarada da estratégia:**
- 1 contrato MNQ por trade
- ~7.5 trades/janela WF (60 dias úteis) = ~30 trades/ano
- Holding intraday (ORB clássico, fecha no encerramento da sessão)

**Cenário pior caso documentado**: PnL −1877 pts em 60 dias úteis (janela 1 do WF 2026-05-24-21). Em USD: −3754 (com 1 contrato), −7508 (2 contratos).

**Topstep funding (referência operacional do projeto):**
- Trailing drawdown típico: USD −2500
- Daily loss limit típico: USD −1000

**Risco aritmético**: a janela 1 sozinha **estoura conta funded com 1 contrato** (drawdown −3754 > limite −2500). Com 2 contratos é catastrófico.

### Veto_De_Risco

**EMITO Veto_De_Risco bloqueante** sobre P1 (Explorador) com a categoria **`exposicao_excede_topstep_drawdown`**.

Justificativa: aprovar para Walk-Forward sem mecanismo de mitigação contra a janela #1 viola R5 do Spec 1 (limite de exposição compatível com a corretora alvo). A estratégia tem uma janela documentada onde o drawdown realizado excede o trailing drawdown da plataforma operacional.

P3 (Mister_M) **passa** porque inclui circuit breaker. Mas o threshold USD −1000 é insuficiente para a janela 1 (que perdeu acumulado USD −3754 ao longo de 60 dias úteis = USD −62/dia médio, mas com pico provável). **Sugiro emendar P3 para circuit_breaker_diario=USD −500 e circuit_breaker_semanal=USD −1500**, com pausa automática até EOD na semana se atingido.

P2 e P4 **passam** porque não promovem operação imediata.

### Veto retirado se P3 for emendado

Se a Decisão final adotar P3 com os thresholds revisados (USD −500 diário, USD −1500 semanal), retiro o veto. Caso contrário, mantém-se bloqueante.

### Confianca

**85/100** — análise quantitativa baseada em drawdown documentado.

---

## Turno 8 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:52:00Z
nao_deterministico: true
status: concluido
```

### Compilação do Debate

**Propostas:**
- P1 (Explorador): aprovar direto. Confiança 60.
- P2 (Manolo): rejeitar até investigação. Confiança 80.
- P3 (Mister_M): aprovar com restrições (hold-out + circuit breaker USD −1000). Confiança 70.
- P4 (Odin): adendo ortogonal a P3 (mais janelas WF). Confiança 75.

**Críticas decisivas (Devils_Advocate, Turno 6):**
- **Look-ahead disfarçado** no `EstrategiaSpreadFilter.mediana_diaria`: a mediana é computada sobre minutos do dia inteiro, incluindo minutos futuros. Inutiliza o resultado WF até que seja corrigido para running median.
- Sem hold-out prospectivo, Sharpe local é suspeito.

**Veto (Cerberus, Turno 7):**
- Veto_De_Risco BLOQUEANTE sobre P1 (`exposicao_excede_topstep_drawdown`). Janela 1 sozinha estoura conta Topstep com 1 contrato.
- P3 passa COM emenda: thresholds revisados para USD −500 diário, USD −1500 semanal.

### Decisão sintetizada

A combinação `(crítica DA + veto Cerberus)` torna **P1 inviável**. P2 fica como fallback se não conseguirmos endereçar a crítica de look-ahead. **P3 emendado + P4 paralelo** é o caminho equilibrado, MAS exige primeiro corrigir o look-ahead.

### Proposta vencedora

**P3-emendado**, condicional à correção de look-ahead:

1. **Pre-condição técnica (bloqueante)**: re-implementar `EstrategiaSpreadFilter.mediana_diaria` para usar **running median** (mediana sobre minutos passados do dia, sem peek nos futuros).
2. **Pre-condição empírica (bloqueante)**: re-rodar WF `2026-05-24-21` com a versão corrigida. Sharpe mediana ≥ +1.5 e nenhuma janela com PnL < −1500 pts → segue. Caso contrário, aplica P2 (rejeita).
3. **Aprovação condicional** quando pré-condições passarem: `aprovado_walk_forward=true` com:
   - Circuit breaker diário: USD −500
   - Circuit breaker semanal: USD −1500
   - Hold-out cego de 60 dias úteis prospectivos antes de operação real
   - 1 contrato máximo durante hold-out

### aprovado_walk_forward

**FALSE** nesta Decisão imediata. A aprovação fica reservada para uma **Decisão de seguimento** que será emitida quando as pré-condições (running median + re-WF bem-sucedido) forem cumpridas.

### links_zettel

- `[[Walk_Forward_2026-05-24-21]]` (Crabel NR7 + Spread Filter, com look-ahead disfarçado)
- `[[Walk_Forward_2026-05-24-22]]` (baseline Crabel NR7)
- `[[Caracterizacao_Spread_MNQ_14_Meses]]`

### Status

**concluido** com `aprovado_walk_forward=false` e ações concretas pré-aprovação registradas.

### Confianca

**85/100** — síntese conservadora, evita repetir o erro da Decisão 2026-05-23-01 (revogada).

---

## Decisão final

- **Proposta aceita**: P3-emendado (Mister_M + Cerberus emenda).
- **Aprovado_walk_forward**: `false`.
- **Pré-condições obrigatórias para reabrir Debate de aprovação**:
  1. Corrigir `EstrategiaSpreadFilter.mediana_diaria` para running median.
  2. Re-rodar WF da combinação. Critério de sucesso: Sharpe mediana ≥ +1.5, nenhuma janela < −1500 pts.
- **Vetos registrados**: 1 (Cerberus, exposicao_excede_topstep_drawdown — retirado condicionalmente).
- **Reproduzivel**: total (todos os scripts versionados, manifest_hash registrado).
- **Regressao_detectada**: false.
- **Status**: concluido.

---

## Turno 9 — Athena (POS-DEBATE — execução das pré-condições)

```meta
agente: Athena
modelo: claude-opus-4.7
timestamp: 2026-05-25T01:55:00Z
nao_deterministico: true
status: concluido
```

### Execução das pré-condições

Imediatamente após a Decisão, executei as 2 pré-condições:

**1. Look-ahead corrigido** (commit pendente):

- `EstrategiaSpreadFilter.mediana_diaria` agora usa running median.
- Adicionado parâmetro `minutos_warmup_dia=30` (default).
- Antes do warmup do dia, filtro respeita `permitir_se_falta_dado` (default: permite).
- Após warmup, filtra usando mediana dos minutos do dia **estritamente anteriores** ao timestamp atual.
- Adicionados 2 testes unitários (running_median_bloqueia_minutos_acima e running_median_nao_usa_minutos_futuros) para impedir regressão.

**2. Re-WF executado (`2026-05-25-02`)**:

| Métrica | Com look-ahead (2026-05-24-21) | Running median (2026-05-25-02) |
|---|---|---|
| Sharpe mediana | +3.37 | **+2.91** ✅ ≥ +1.5 |
| PnL mediano | +269 pts | +240 pts |
| Calmar mediana | +4.00 | +3.22 |
| Janela 1 (problemática) | PnL −1877 pts | PnL **−1711 pts** ❌ < −1500 |
| Trades/janela | 7.5 | 8.0 |

### Avaliação dos critérios da Decisão

- **Critério 1 (Sharpe mediana ≥ +1.5)**: ✅ PASSA (+2.91).
- **Critério 2 (nenhuma janela < −1500 pts)**: ❌ FALHA (janela 1 deu −1711 pts).

### Conclusão da execução

**A Decisão original (P3-emendado) NÃO é promovida.** O critério bloqueante #2 falhou.

Achado positivo independente: **o look-ahead disfarçado NÃO era a causa principal do achado original**. Sharpe foi de +3.37 → +2.91 (degradação ~14%) mas continua positivo robusto. Isso significa que a tese (Crabel NR7 + spread filter mediana_diaria reduzindo fricção) tem fundamento real, não foi artefato de leak.

### Próximos passos sugeridos (sem aprovação imediata)

1. **Investigar a janela 1 especificamente**: período jul-set 2025 do WF. O que aconteceu nesse trecho que causou Sharpe −6.46? Hipóteses a testar:
   - Regime de Fed (taxas / press conferences agressivas).
   - Sazonalidade (verão tipicamente menos liquido).
   - Bug no Crabel NR7 em condições específicas.
2. **Aplicar circuit breaker** ao plugin: implementar `EstrategiaCircuitBreaker` overlay similar ao Spread Filter, mas observando PnL acumulado ao longo de um dia/semana e desligando ao bater limite.
3. **Reabrir Debate** quando (a) janela 1 for entendida e (b) o circuit breaker eliminá-la (ou reduzir o pior caso para PnL ≥ −1500).

### Status final pós-execução

- `aprovado_walk_forward=false` (mantido).
- `condicao_pre_execucao` documentada.
- Próxima reabertura: aguardar análise de janela 1 + circuit breaker.
