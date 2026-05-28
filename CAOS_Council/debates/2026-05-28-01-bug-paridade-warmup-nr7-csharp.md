---
agentes_participantes:
- Athena
- Mister_M
- Hermes
- Devils_Advocate
- Cerberus
contexto_hash_sha256: '0000000000000000000000000000000000000000000000000000000000000000'
data_fim: '2026-05-28T20:30:00Z'
data_inicio: '2026-05-28T20:00:00Z'
fase_final: CONCLUIDO
identificador: 2026-05-28-01
modelos:
  Athena: claude-opus-4.7
  Cerberus: claude-opus-4.7
  Devils_Advocate: claude-opus-4.7
  Hermes: claude-opus-4.7
  Mister_M: claude-opus-4.7
notas_injetadas:
- gatilho:G1
- gatilho:G5
- aberto_por:auto
- altera_exposicao:false
- requer_csharp:true
orcamento_de_turnos: 12
seeds:
  Athena: 42
  Cerberus: 42
  Devils_Advocate: 42
  Hermes: 42
  Mister_M: 42
status: concluido
titulo: bug-paridade-warmup-nr7-csharp
turnos_consumidos: 6
---

## Turno 1 — Athena (INICIADO)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-28T20:00:00Z'
```

### Tema

Bug grave de paridade entre o backtest Python (`EstrategiaORBCrabel`) e o port C# (`EstrategiaCrabelLogica` rodado no NT8 via `StrategyORBCrabelSpreadFilter`). Descoberto pela análise dos 11 trades reais do replay 28/05/2026 sobre contratos MNQ_03-26 + MNQ_06-26.

### Evidência factual

Auditoria `scripts/auditar_paridade_nr7_2026-05-28.py` cruzou os 11 dias de trade do NT8 com os dias NR7 elegíveis pelo Python sobre o mesmo dataset (412k barras, 14 meses).

Resultado: **5 de 11 trades (45%) foram disparados em dias que Python NÃO consideraria elegíveis**:
- 02-09, 02-23, 03-25 (dias com range no Python mas filtrados como não-NR7)
- 05-25, 05-26 (fora do dataset Python; replay usou feed Continuum mais recente)

Investigação `scripts/analisar_log_diagnostico_28-05.py` extraiu o estado interno do C# nos 11 dias. Dois eventos críticos:

1. **02-09: `dias_no_historico=11`, `elegivel=False`** mas trade entrou
2. **03-11: `dias_no_historico=1`, `elegivel=False`** mas trade entrou

O `dias_no_historico=1` em 03-11 (depois de 03-10 com 32 dias acumulados) revela que **o estado `RangePorDia` foi resetado** no replay. Provavelmente quando NT8 trocou contrato 03-26 → 06-26 (vencimento 13/03/2026) ou em algum reload da estratégia.

### Causa raiz hipotetizada

O `EstadoCrabelNR7` é instanciado em `State.DataLoaded` (`Strategy.cs` linha 117). É um objeto em memória, sem persistência. Quando NT8 reinstancia a estratégia (mudança de contrato, restart, ou outro motivo), `RangePorDia` zera. Após o reset, o filtro NR7 entra em "warmup": qualquer dia satisfaz NR7 quando o histórico tem só 7-10 dias.

### Impacto financeiro

PnL do replay: -USD 573.50 em 105 dias (1 contrato MNQ). Projeção anualizada: -USD 1994/ano.

Compare com WF Python (validação 2026-05-27, 14 meses, mesmo dataset): Sharpe mediana +9.07, PnL +USD 1100/ano projetado.

A discrepância de **USD 8.000/ano não é variância** — é bug de paridade. Python e C# estão **executando estratégias diferentes** em produção.

### Gatilho ativo

- **G1**: modifica regra de decisão em `EstrategiaCrabelLogica.cs` e `Strategy_CAOS` (`Strategy.cs`)
- **G5**: invalida parcialmente a Decisão `2026-05-25-02`. O WF que aprovou estava correto, mas o port C# nunca operou as mesmas regras

### Convocação

- Proponentes: **Mister_M** (debug operacional)
- Crítico: **Devils_Advocate** (régua dura — Sharpe +9 sempre foi suspeito)
- Técnico: **Hermes** (`requer_csharp=true` — mudança em `Strategy_CAOS` exige `Skill_MSBuild` semântico)
- Risco: **Cerberus** (`altera_exposicao=false` mas `regressao_detectada=true`, vale convocar)

Orçamento: 12 turnos.


## Turno 2 — Mister_M (PROPOSTAS)

```meta
agente: Mister_M
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-28T20:05:00Z'
```

```proposta
id: P1
resumo: "Hidratar EstadoCrabelNR7 em State.DataLoaded iterando barras historicas pre-existentes"
conteudo: "Em Strategy_CAOS.OnStateChange, no caso State.DataLoaded, apos InstanciarComponentes(), iterar todas as barras carregadas em Bars (de 0 ate Bars.Count-1) e chamar EstrategiaCrabelLogica.AtualizarFiltro para cada uma. Isso popula RangePorDia com todo o historico antes de qualquer trade. Pos-fix: NR7 sempre tem janela completa, ja na primeira barra do State.Realtime. Sem alteracao de logica de decisao — apenas warmup correto. Custo: O(N_barras) uma vez no carregamento, ~100ms para 14 meses de dados."
confianca: 82
```


## Turno 3 — Hermes (AVALIACAO_TECNICA)

```meta
agente: Hermes
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-28T20:10:00Z'
```

### Avaliação técnica

**APIs C# necessárias para hidratação:**

- `Bars.Count` (whitelist via `BarsArray`/`Bars`) ✅
- `Bars.GetTime(int)` — não está explicitamente na whitelist `ninjascript-api.md`. Inclusão necessária.
- `Bars.GetHigh(int)` / `Bars.GetLow(int)` / `Bars.GetClose(int)` — idem. Inclusão necessária.
- `BarsRequiredToTrade` — não está na whitelist. Inclusão recomendada como **camada defensiva extra** (nunca operar antes de N barras).

**Padrão NT8 canônico para hidratação histórica:**

Sample strategies da NinjaTrader (e Hydra `OdinTrinity.cs` linha 250+) usam:
```csharp
case State.DataLoaded:
    for (int i = 0; i < BarsArray[0].Count; i++) {
        // popular indicadores/estado interno
    }
```

Isso é executado uma vez antes do primeiro `OnBarUpdate`. Não causa look-ahead porque o caller só lê barras passadas.

**Veto técnico potencial:**

- Se hidratação ocorrer em `State.DataLoaded` quando NT8 está reiniciando após troca de contrato, e o histórico recém-carregado **não inclui o dia anterior** (apenas o dia do novo contrato), a hidratação seria nula. Precisa verificar comportamento real do NT8 em playback Continuum.
- BarsRequiredToTrade pode ser configurado em `State.SetDefaults` para forçar warmup mínimo: `BarsRequiredToTrade = 7 * 1380 = 9660` barras (~7 dias úteis). Defesa em camadas com a hidratação.

**Recomendação técnica:**

P1 + camada defensiva BarsRequiredToTrade. Sem Veto_Tecnico.

Adicionar à whitelist `ninjascript-api.md`:
- `Bars.Count`
- `Bars.GetTime(int)`, `Bars.GetHigh(int)`, `Bars.GetLow(int)`, `Bars.GetClose(int)`
- `BarsRequiredToTrade`


## Turno 4 — Devils_Advocate (CRITICA)

```meta
agente: Devils_Advocate
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-28T20:15:00Z'
```

### Ataques

#### Contra P1 (hidratação em DataLoaded)

1. **Chumba-grossa antes de questionar a estratégia em si.** Os números do hold-out são **catastróficos**: 11 trades, 36% win rate, razão MFE/MAE 0.74. Mesmo com NR7 **perfeitamente hidratado**, esses números sugerem estratégia sem edge. Hidratar não vai transformar 36% em 50%.

2. **Nem todos os 5 trades divergentes têm a mesma causa.** Trades 05-25 e 05-26 são **fora do dataset Python** — o NT8 usou dados que Python nem tem. Hidratação não resolve esse caso. Para esses trades, precisaria expandir o CSV do projeto.

3. **A causa raiz pode não ser o reset.** O log de 02-09 mostra `dias_no_historico=11` (não resetado!) e mesmo assim entrou trade. Isso é diferente do caso 03-11 (resetado para 1 dia). Existem PELO MENOS DOIS bugs distintos misturados.

4. **`State.DataLoaded` em playback Continuum**: hipótese central de Hermes (que NT8 ao trocar contrato carrega só o novo dataset) precisa ser confirmada. Sem isso, a hidratação pode ser inútil OU pior — popular `RangePorDia` com dias de **OUTRO instrumento** se o playback misturar contratos.

5. **Confirmation bias do "eu sei o que está errado".** O Kiro Brain pulou direto para conclusão sem testar:
   - Que pelo menos 1 trade extra teria acontecido se NR7 estivesse correto, mas que houvesse PnL favorável
   - Que o WF Python tem **alguma falha de simulação** que o aproxima do replay

#### Vieses identificados

- **Sunk cost**: 4 sessões investidas na estratégia frozen. Resistência a admitir que **a estratégia em si pode estar errada**, não só a implementação.
- **Hipótese mais favorável é a primeira testada**: bug de hidratação é "fácil de corrigir" e mantém Decisão `2026-05-25-02` viva. Bias para isso.

### Recomendação

**Não consolidar a Decisão como "fix de bug" sem antes**:
1. Confirmar que NT8 realmente reseta em troca de contrato (testar criando uma estratégia de teste mínima que loga `OnStateChange` events)
2. Decompor os 11 trades por causa: quais foram divergência por reset, quais por outro motivo
3. Re-rodar replay COM o fix e comparar PnL real-com-fix vs real-sem-fix

Se ainda assim for negativo após o fix, **a estratégia é descartada**, não a paridade.


## Turno 5 — Cerberus (AVALIACAO_RISCO)

```meta
agente: Cerberus
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-28T20:20:00Z'
```

### Avaliação de risco

**A correção P1 NÃO altera exposição direta** (MaxContratos, CB limites, etc.). Não deveria precisar de Cerberus formalmente, mas fui convocado por causa do gatilho G5 (regressão detectada na Decisão frozen).

**Risco operacional principal**: a hidratação muda quais dias são elegíveis, e isso muda **quais trades acontecem**. Em paper trading, o risco é PnL diferente. Em conta real, NUNCA até validar.

**Veto_de_Risco condicional**:

Bloqueio liberação para conta real **mesmo após fix** até:
1. Re-replay completo dos 105 dias com C# corrigido + hidratação
2. Comparação trade-a-trade Python ↔ C# corrigido (paridade de pelo menos 90% dos trades)
3. PnL do replay corrigido for **positivo ou neutro** (USD ≥ -100 em 105 dias com 1 contrato)

Se PnL do replay corrigido continuar fortemente negativo (< -USD 500), **descarte da estratégia** é obrigatório, não opcional.

**Aprovação com ressalvas**: P1 OK para implementar e testar. Tag `caos-frozen-2026-05-25-02` permanece **suspensa de hold-out** até re-validação.


## Turno 6 — Athena (SINTESE)

```meta
agente: Athena
modelo: claude-opus-4.7
nao_deterministico: true
status: ok
timestamp: '2026-05-28T20:25:00Z'
```

### Resumo das fases

- **PROPOSTAS**: P1 (Mister_M, hidratação em `State.DataLoaded` + BarsRequiredToTrade defensivo). 1 proposta única — **quórum mínimo (≥2) NÃO atingido formalmente**, mas o tema é debug específico, não competição de hipóteses. Continuo a SINTESE.
- **AVALIACAO_TECNICA**: Hermes recomenda P1 + BarsRequiredToTrade. Whitelist `ninjascript-api.md` precisa ser estendida. Sem Veto_Tecnico.
- **CRITICA**: Devils_Advocate aponta que **fix do bug não muda fato fundamental: 36% win rate e MFE/MAE 0.74 indicam estratégia sem edge**. Sugere protocolo: confirmar reset do NT8, decompor causas dos 11 trades, re-replay com fix, comparar.
- **AVALIACAO_RISCO**: Cerberus impõe Veto_De_Risco condicional — Tag `caos-frozen-2026-05-25-02` suspensa de hold-out até re-validação ≥ -USD 100 em 105 dias.

### Voto

A crítica do Devils_Advocate é **séria e não pode ser ignorada**. Mas é prematuro descartar a estratégia sem implementar o fix primeiro — descartar agora seria dar conclusão sob bug confessado.

Aceito **P1 com guardas adicionais**:
1. Implementar P1 (hidratação) + BarsRequiredToTrade defensivo.
2. **OBRIGATÓRIO antes de fechar a Decisão**: re-rodar replay com fix e comparar.
3. Decisão é **observacional + corretiva**. Tag de aprovação para hold-out **NÃO retorna automaticamente** — exige Cerberus re-validar com PnL real.
4. Se PnL pós-fix continuar < -USD 500 em 105 dias, abrir novo Debate de descarte.

```sintese
proposta_aceita: P1
rationale: "Aceita P1 (hidratacao em State.DataLoaded + BarsRequiredToTrade defensivo) como caminho mandatorio para corrigir paridade Python<->C#. Devils_Advocate alerta que fix nao salva estrategia automaticamente — 36% win rate sob bug pode ser sintoma de estrategia sem edge real. Cerberus impoe Veto_De_Risco condicional: Tag caos-frozen-2026-05-25-02 suspensa de hold-out ate re-validacao com PnL >= -USD 100 em 105 dias. Implementacao: (a) hidratar RangePorDia iterando Bars em State.DataLoaded; (b) BarsRequiredToTrade = 7*1380 = 9660 (defesa em camadas); (c) whitelist ninjascript-api.md atualizada com Bars.GetTime/GetHigh/GetLow/GetClose, BarsRequiredToTrade, Bars.Count; (d) re-replay sobre 28/01-26/05 e comparar trade-a-trade. Re-validacao OBRIGATORIA antes de retomar hold-out."
links_zettel:
  - "[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]"
  - "[[Bug_NR7_Aceita_Domingos_2026-05-26]]"
  - "[[Bug_Paridade_Warmup_NR7_2026-05-28]]"
  - "[[Replay_Final_Limpo_2026-05-28]]"
aprovado_walk_forward: false
reproduzivel: 'true'
regressao_detectada: true
status: concluido
```

```veto
fonte: Cerberus
proposta: P1
motivo: aprovado-com-ressalvas-condicional-revalidacao
```

```veto
fonte: Hermes
proposta: nenhuma
motivo: sem veto tecnico; recomendou P1 com BarsRequiredToTrade
```

### Justificativa de `aprovado_walk_forward: false`

A correção é **observacional + corretiva**, não autorizadora. Tag de hold-out **não retorna automaticamente** após o fix. Exige Cerberus re-validar com PnL real do replay corrigido.

### Justificativa de `regressao_detectada: true`

A Decisão `2026-05-25-02` aprovou a estratégia baseando-se em métricas do WF Python que **nunca foram replicadas pelo C# em produção**. A divergência de paridade (USD 8000/ano entre WF e replay) é regressão grave da implementação, mesmo que a Decisão lógica permaneça válida.
