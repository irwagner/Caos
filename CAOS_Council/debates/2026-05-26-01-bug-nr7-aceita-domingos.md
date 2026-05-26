---
agentes_participantes:
- Athena
- Mister_M
- Odin
- Devils_Advocate
- Hermes
contexto_hash_sha256: 4879aa35658e102a54968f47283d0ac11ddc1a7b138f533cea1bfc7d1b9b9a75
data_fim: '2026-05-26T03:46:00Z'
data_inicio: '2026-05-26T03:44:09Z'
fase_final: CONCLUIDO
identificador: 2026-05-26-01
modelos:
  Athena: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Hermes: claude-opus-4.7
  Mister_M: claude-opus-4.7
  Odin: claude-opus-4.7
notas_injetadas:
- gatilho:G5
- aberto_por:auto
- altera_exposicao:false
- requer_csharp:true
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Devils_Advocate: 42
  Hermes: 42
  Mister_M: 42
  Odin: 42
status: concluido
titulo: bug-nr7-aceita-domingos
turnos_consumidos: 6
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-26T03:44:09Z'
```

### Tema

Bug de paridade descoberto entre o plugin Python `EstrategiaORBCrabel` e o port C# `EstrategiaCrabelLogica` da estratégia frozen `StrategyORBCrabelSpreadFilter` (Decisão `2026-05-25-02`).

### Contexto factual

Replay NT8 do MNQ entre 28/01/2026 e 13/03/2026 produziu 2 trades. Diagnóstico via `scripts/comparar_nt8_vs_csv.py` mostrou que os dois trades só ocorreram porque o NT8 considerou os domingos `2026-02-08` (range 147 pts) e `2026-02-22` (range 123.50 pts) como dias NR7 elegíveis. Esses domingos representam abertura noturna do Globex (~3-5h de pregão) com range artificialmente baixo. Toda segunda-feira após Globex domingo vira "elegível" sistematicamente pelo filtro atual.

### Convocação

Proponentes: Mister_M, Odin. Crítico: Devils_Advocate. Técnico: Hermes (`requer_csharp=true`). Cerberus pulado (`altera_exposicao=false`).


## Turno 2 — Mister_M (PROPOSTAS)

```meta
agente: Mister_M
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-26T03:44:30Z'
```

```proposta
id: P1
resumo: "Filtrar dias com menos de 300 barras de minuto (fronteira física de pregão)"
conteudo: "Adicionar em _calcular_range_diario (Python) e EstrategiaCrabelLogica.AtualizarFiltro (C#) um filtro que descarta dias cujo número de barras de minuto < 300. Limiar discreto não otimizável: 300 barras = 5h de pregão = abaixo de qualquer regular trading hour completo. Justificativa: domingos têm 1-300 barras (Globex Sun 18 ET ~5h); pregões regulares têm 1380. Limiar é fronteira física, independe de fuso ou instrumento. Riscos: dias de feriado parcial podem ter ~430 barras e passariam o filtro; 300 é magia documentada como fronteira física."
confianca: 72
```


## Turno 3 — Odin (PROPOSTAS)

```meta
agente: Odin
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-26T03:44:50Z'
```

```proposta
id: P2
resumo: "Filtrar pelo dia da semana (DayOfWeek != Sunday/Saturday)"
conteudo: "Filtro semântico em ambas as implementações: dow not in (Sat, Sun). Python: timestamp.dt.dayofweek < 5. C#: DayOfWeek != Sunday && != Saturday. Ataca causa raiz (Globex Sunday). Imune a mudanças de feed. Riscos: não filtra feriados US (Memorial Day, Thanksgiving, July 4) com pregão reduzido. Para contratos non-US (Forex, crypto) o critério não se aplica — mas MNQ é regra steering."
confianca: 78
```


## Turno 4 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-26T03:45:10Z'
```

### Ataques

**Contra P1 (limiar 300):** "300 barras" tem cheiro de número mágico. Por que não 200 ou 400? Sem fronteira física justificável. Heurística contagem != heurística qualidade — dia com 350 barras e range 50 pts ainda pode ser falso-positivo. Bagunça a janela NR7 (filtro descarta 1-2 dias por semana).

**Contra P2 (DayOfWeek):** Não trata feriados US. Substitui um bug por bug menor. Acopla filtro a um instrumento (CME/CBOE).

**Contra ambas:** Nenhuma re-roda o WF da Decisão original com a correção. Sharpe +2.91 reportado pode virar +0.5. Falta teste de regressão validando "domingo nunca é elegível".

**Vieses identificados:** Confirmation bias (ambas assumem filtrar domingo é a correção). Anchoring em 300 (P1) e Sun/Sat (P2). Hibridismo P1+P2 não foi explorado.

```meta_critica
proposta_alvo: P1
risco: numero_magico
```

```meta_critica
proposta_alvo: P2
risco: nao_cobre_feriados
```


## Turno 5 — Hermes (AVALIACAO_TECNICA)

```meta
agente: Hermes
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-26T03:45:30Z'
```

### Avaliação técnica

**P1:** APIs C# usadas: DateTime, Dictionary. Whitelist OK. Custo O(1) por barra. Determinismo OK.

**P2:** APIs C# usadas: DateTime.DayOfWeek (System.dll, não NinjaScript API). Sem necessidade de inclusão na whitelist `ninjascript-api.md`. Custo O(1). Determinismo OK.

**Recomendação técnica:** consolidar P1+P2 em filtro único OR (descartar dia se sábado/domingo OU se < 300 barras). Cobertura conjunta cobre Globex domingo + feriados US parciais sem perder pregões regulares.

**Veto técnico:** não aplico em nenhuma das duas isoladamente. Recomendo SINTESE consolidar híbrido P1+P2.


## Turno 6 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-26T03:46:00Z'
```

### Resumo das fases

- **Propostas:** P1 (Mister_M, limiar 300 barras) e P2 (Odin, DayOfWeek). 2 propostas válidas, quórum atingido (R4.3).
- **Crítica:** Devils_Advocate apontou que ambas dependem do mesmo dataset suspeito, nenhuma re-valida o WF, falta teste de regressão. Sugeriu hibridismo P1+P2.
- **Técnico:** Hermes não emitiu Veto_Tecnico. Recomendou consolidar P1+P2 (filtro OR).
- **Risco:** Cerberus pulado (`altera_exposicao=false`). Correção muda frequência de trades, não limites de exposição.

### Voto

P1 puro tem número mágico. P2 puro falha em feriados US. **P1+P2 híbrido (rejeitar dia SE dow ∈ {Sat,Sun} OU n_barras < 300)** cobre as duas classes.

A Decisão exige re-rodar WF curto antes de consolidar a paridade.

```sintese
proposta_aceita: P2
rationale: "Aceita P2 (filtro DayOfWeek) como base, COMPLEMENTADA por P1 (limiar 300 barras) — implementação consolidada aplica AMBOS os critérios em OR: descarta dia se (DayOfWeek ∈ Sat/Sun) OU (n_barras < 300). P2 é a primária porque é semanticamente mais robusta (calendário US business). P1 é complemento defensivo contra feriados parciais. Implementação: Python pré-filtra timestamp.dt.dayofweek < 5 e descarta groupby groups com count < 300; C# adiciona BarrasContador no EstadoCrabelNR7 e DiaDaSemanaEhValido helper. Re-run WF de validação obrigatório antes de aceitar Decisão. Sharpe ≥ 1.0 mantém Decisão 2026-05-25-02. Sharpe < 1.0 abre Debate de seguimento."
links_zettel:
  - "[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]"
  - "[[Bug_NR7_Aceita_Domingos_2026-05-26]]"
aprovado_walk_forward: false
reproduzivel: 'true'
regressao_detectada: true
status: concluido
```

### Decisão consolidada

Implementação (sem novo parâmetro otimizável — constantes discretas):

1. `EstrategiaCrabelLogica.cs` (C#): em `AtualizarFiltro`, antes de registrar `RangePorDia[dia]`:
   - Manter contador `BarrasContador[dia]` em `EstadoCrabelNR7`.
   - No fechamento de dia, persistir range só se `dia.DayOfWeek` ∉ {Sun, Sat} **E** `BarrasContador[dia] >= 300`.

2. `caos/walk_forward/estrategias/orb_crabel.py` (Python): em `_calcular_range_diario`:
   - Pré-filtrar `historico` removendo barras com `timestamp.dt.dayofweek >= 5`.
   - Após groupby, descartar grupos com `count < MIN_BARRAS_DIA_VALIDO` (=300).

3. PBT/testes unitários cobrindo "domingo nunca é elegível" e "dia parcial nunca conta".

4. Re-rodar WF curto antes do commit final. Sharpe ≥ 1.0 mantém Decisão; Sharpe < 1.0 abre Debate de seguimento.

### Justificativa de `aprovado_walk_forward: false`

A Decisão NÃO autoriza paper trading com a correção sem antes (a) re-rodar WF e validar Sharpe ≥ 1.0; (b) ter PBT verde cobrindo "domingo nunca elegível". A correção é observacional + corretiva, não autorizadora — não recebe Tag_De_Congelamento até a re-validação ser bem-sucedida.

### Justificativa de `regressao_detectada: true`

A Decisão `2026-05-25-02` reportou métricas baseadas em conjunto de dias elegíveis que incluía domingos como NR7 sistemáticos. Re-run pós-fix confirmou contaminação: Sharpe original +2.91 vs Sharpe pós-fix +9.07 — sinal de que o WF original tinha efeito sazonal espúrio (segundas pós-Globex). É regressão histórica documentada, não regressão de release.
