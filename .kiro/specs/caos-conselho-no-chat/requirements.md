# Requirements Document

> Spec 5 — Conselho-no-Chat: orquestração autônoma do Conselho CAOS dentro do Kiro IDE

## Introduction

O Spec 1 entregou a infraestrutura completa do Conselho Multi-Agente CAOS (state machine, 9 perfis de agente, 8 skills, Council_Recorder, gravação auditável). Faltava conectar essa infraestrutura a um cérebro real que produzisse os turnos. A ideia original previa uma API externa de subagentes; este Spec 5 adota uma arquitetura diferente, mais barata e direta: **o agente Kiro Claude Opus 4.7 (a IA que conversa com o usuário neste chat) atua como cérebro único interpretando os 9 papéis do Conselho** quando necessário.

A diferença operacional crítica deste spec é a **autonomia de gatilho**. O usuário não precisa solicitar Debate explicitamente. O próprio Kiro detecta quando há tema relevante para Debate (proposta de novo código C#, alteração de exposição, novo paper apurado pelo Explorador, divergência entre estratégias, contradição em Decisão anterior) e abre o Debate sozinho, conduzindo todas as fases até a Decisao_Do_Conselho gravada em `CAOS_Council/decisions/`.

O usuário continua podendo abrir Debate manual quando quiser. Quando o usuário lê uma Decisão e discorda, o freio operacional é **não rodar Walk-Forward para a proposta aprovada** — nada chega a `Sim101` sem aprovação humana via execução do pipeline.

Este spec **não cobre**: integração com APIs LLM externas (DeepSeek, Anthropic, Groq) — fica como Spec 5b futuro caso a Opção A se mostre insuficiente; alteração da máquina de estados do Spec 1 (`INICIADO → PROPOSTAS → CRITICA → AVALIACAO_RISCO → AVALIACAO_TECNICA → SINTESE → CONCLUIDO`); refator do Council_Recorder.

Propriedades transversais: **um cérebro, nove papéis** (Kiro respeita os 9 perfis em `.kiro/agents/`); **gatilhos automáticos** (Kiro detecta condições de abertura sem comando do usuário); **vetos respeitados** (Cerberus e Hermes vetam mesmo que o restante esteja a favor); **auditabilidade total** (todos os turnos gravados em `CAOS_Council/debates/` com hash); **Tag_De_Congelamento como freio** (R8.6 do Spec 1: nada vai a Walk-Forward sem `aprovado_walk_forward=true` na Decisão).

## Glossary

- **Kiro_Brain**: a IA Claude Opus 4.7 que conversa com o usuário neste chat. Atua como cérebro único interpretando os 9 papéis do Conselho.
- **Gatilho_De_Debate**: condição observável que dispara a abertura automática de um Debate. Lista canônica em R2.
- **Steering_Protocolo**: arquivo `.kiro/steering/protocolo-debate-no-chat.md` com `inclusion: always` que carrega automaticamente em toda sessão Kiro. Contém as regras que o Kiro_Brain DEVE seguir para orquestrar um Debate.
- **Debate_Starter**: arquivo Markdown gerado por `caos debate iniciar <slug>` em `CAOS_Council/debates/AAAA-MM-DD-NN-{slug}.md` com cabeçalho YAML pronto. O Kiro_Brain preenche os turnos.
- **Debate_Auto**: Debate aberto pelo Kiro_Brain sozinho, sem comando explícito do usuário. Marcado no frontmatter com `gatilho: <nome_do_gatilho>`.
- **Debate_Manual**: Debate aberto pelo usuário via `caos debate iniciar` ou pedido textual no chat.

## Requirements

### Requirement 1: Steering protocol obrigatório em toda sessão

**User Story:** Como Kiro_Brain, quero ter sempre o protocolo do Conselho carregado na minha context, para nunca esquecer as regras de fase, vocabulário, vetos e gravação.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter `.kiro/steering/protocolo-debate-no-chat.md` com frontmatter `inclusion: always` (carrega em toda sessão Kiro automaticamente).
2. THE protocolo SHALL declarar:
   - Os 5 gatilhos canônicos de abertura automática de Debate (R2 abaixo).
   - O vocabulário Markdown que o Kiro_Brain DEVE usar para registrar turnos (cabeçalhos `## Turno N — Agente (FASE)`, blocos `meta`, blocos `Proposta/Justificativa/Riscos/Confianca`).
   - A obrigação de respeitar os perfis em `.kiro/agents/` (cada agente tem skills permitidas, escopo de decisão, formato de saída).
   - A máquina de estados do Spec 1 (`INICIADO → PROPOSTAS → CRITICA → AVALIACAO_RISCO → AVALIACAO_TECNICA → SINTESE → CONCLUIDO`).
   - A regra: vetos de Cerberus e Hermes são **bloqueantes** — Kiro_Brain NÃO pode sobrescrever.
   - A regra: nada vai a Walk-Forward sem `aprovado_walk_forward=true` na Decisão (R8.6 do Spec 1).
3. THE protocolo SHALL incluir bloco "Como abrir um Debate" em pseudocódigo passo-a-passo, para que o Kiro_Brain saiba o procedimento concreto.
4. WHEN o usuário rodar `caos perfil validar` (Spec 1), THE protocolo SHALL ser também carregado e validado como steering correto (não-ambíguo, sem placeholders).

### Requirement 2: Gatilhos automáticos de abertura de Debate

**User Story:** Como usuário, não quero ter que solicitar Debate explicitamente — quero que o Kiro_Brain detecte o que merece Debate e abra sozinho.

#### Acceptance Criteria

1. THE Kiro_Brain SHALL abrir Debate_Auto quando QUALQUER um dos 5 gatilhos canônicos abaixo se manifestar:
   1. **Proposta de novo código C# em `04_CODIGO/ninjascript/`** — qualquer alteração que adicione classe/método novo, exceto refatoramento estritamente equivalente.
   2. **Alteração de exposição declarada** — mudança em `MaxContratos`, `CircuitBreakerDiarioUSD`, `RangeMinimoPontos` ou parâmetros equivalentes em outras estratégias.
   3. **Resultado novo de Walk-Forward** — execução de `caos walk-forward run` que produza `status="concluido"` ou `status="abortado-por-falhas"` para uma estratégia ainda não decidida pelo Conselho.
   4. **Paper relevante encontrado pelo Explorador** — quando o Kiro_Brain busca via web_search e encontra paper com `status=aprovada` (R12 do Spec 1) que muda direção da estratégia atual.
   5. **Contradição com Decisão anterior** — quando uma proposta nova entra em conflito com decisão `aprovado_walk_forward=true` registrada em `CAOS_Council/decisions/`.
2. THE Kiro_Brain SHALL gravar o gatilho específico no frontmatter do Debate_Auto (`gatilho: <nome_do_gatilho>`).
3. WHEN nenhum gatilho está ativo mas o usuário pede algo via chat, THE Kiro_Brain SHALL avaliar se a tarefa justifica Debate (uso de heurística: "essa decisão muda comportamento operacional, financeiro ou arquitetural?"); se SIM, abre Debate_Auto antes de executar; se NÃO, executa direto.
4. WHEN o usuário pedir Debate explicitamente (mensagem mencionando "Debate", "Conselho", "discutir entre os agentes" ou similar), THE Kiro_Brain SHALL abrir Debate_Manual com `gatilho: usuario`.
5. THE Kiro_Brain SHALL **NÃO** abrir Debate para alterações de pura documentação (README, comentários), formatação ou typo — para essas, executa direto.

### Requirement 3: Subcomando `caos debate iniciar` (refator do stub atual)

**User Story:** Como Kiro_Brain ou usuário, quero gerar um Debate_Starter em `CAOS_Council/debates/` com cabeçalho YAML correto sem montar tudo manualmente.

#### Acceptance Criteria

1. THE CLI `caos debate iniciar <slug>` SHALL substituir o subcomando `caos debate <tema>` atual (que é stub no Spec 1).
2. WHEN executado, THE comando SHALL:
   - Validar `slug` contra regex `^[a-z0-9-]{1,60}$` (mesmo do Council_Recorder).
   - Computar identificador `AAAA-MM-DD-NN` (NN = sequencial dentro do dia, começando em 01).
   - Criar `CAOS_Council/debates/{identificador}-{slug}.md` com cabeçalho YAML válido (campos do schema `Debate` do Spec 1: `identificador`, `titulo`, `data_inicio`, `agentes_participantes` lista vazia inicialmente, `modelos: {Athena: claude-opus-4.7}` por default, `contexto_hash_sha256`, `notas_injetadas`, `seeds`, `orcamento_de_turnos: 12`, `turnos_consumidos: 0`, `fase_final: INICIADO`, `status: em-andamento`, `gatilho: <gatilho>`, `aberto_por: <auto|usuario>`).
   - Imprimir o caminho do arquivo criado e a próxima ação esperada (preencher turnos pelo Kiro_Brain).
3. THE comando SHALL aceitar flags:
   - `--titulo "<texto>"` — título humano completo (default: o slug com hifens substituídos).
   - `--gatilho <nome>` — um dos 5 gatilhos de R2.1, ou `usuario` para Debate manual. Default: `usuario`.
   - `--altera-exposicao` — marca o tema como exigindo fase AVALIACAO_RISCO (Cerberus).
   - `--csharp` — marca o tema como exigindo fase AVALIACAO_TECNICA (Hermes).
   - `--root <path>` — raiz do workspace; default cwd.
4. IF já existe um arquivo com mesmo slug+dia, THEN THE comando SHALL incrementar o NN automaticamente.

### Requirement 4: Subcomando `caos debate fechar`

**User Story:** Como Kiro_Brain ou usuário, quero finalizar um Debate validando o protocolo, gerando a Decisao_Do_Conselho e fazendo commit Git auditável.

#### Acceptance Criteria

1. THE CLI `caos debate fechar <identificador>` SHALL:
   - Localizar o arquivo `CAOS_Council/debates/{identificador}-*.md`.
   - Validar que o frontmatter está coerente com o schema `Debate` do Spec 1 (Pydantic).
   - Validar que há ao menos 2 propostas válidas (R4.3 do Spec 1) a menos que o motivo final seja `sem-quorum` ou `timeout`.
   - Validar que cada turno tem cabeçalho `## Turno N — Agente (FASE)` e bloco `meta` com timestamp, modelo, status.
   - Construir uma `DecisaoDoConselho` (schema do Spec 1) a partir das propostas/vetos/votos extraídos do arquivo.
   - Invocar `CouncilRecorder.gravar(debate, decisao)` (Spec 1) que cria o commit dedicado e a Tag_De_Congelamento se `aprovado_walk_forward=true`.
2. WHEN a validação falhar, THE comando SHALL imprimir os erros estruturados e NÃO executar o commit.
3. WHEN não houver consenso de 2/3 nem veto bloqueante, THE Decisão SHALL ter `status: pendente-usuario` e a tag NÃO ser aplicada.
4. THE comando SHALL aceitar flag `--dry-run` que valida e imprime a Decisão derivada, mas não grava nem commita.

### Requirement 5: Property 21 — Conformidade do Debate gravado

**User Story:** Como Hermes, quero gate automatizado que rejeite Debates malformados antes do commit.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter `tests/property/test_debate_no_chat_conformidade.py` com Property 21:
   - Para todo arquivo em `CAOS_Council/debates/*.md`, o frontmatter SHALL parsear como `Debate` válido (schema Pydantic do Spec 1).
   - Cada turno SHALL ter cabeçalho válido `## Turno N — Agente (FASE)` onde `Agente` ∈ 9 perfis e `FASE` ∈ máquina de estados.
   - A sequência de fases SHALL respeitar a ordem do Spec 1.
   - Quando `fase_final == CONCLUIDO`, SHALL existir Decisão correspondente em `CAOS_Council/decisions/`.
2. THE Property 21 SHALL ser registrada em `tests/property/test_property_coverage.py` sob o spec `caos-conselho-no-chat`.

### Requirement 6: Atualização da máquina-do-agente (Athena profile)

**User Story:** Como Kiro_Brain, quero que o perfil de Athena reflita a nova realidade onde ela é interpretada por Kiro Opus 4.7 dentro do chat.

#### Acceptance Criteria

1. THE `.kiro/agents/Athena.md` SHALL ser atualizado para refletir que `modelo: claude-opus-4.7` agora se concretiza via Kiro IDE.
2. THE atualização SHALL ser não-destrutiva — manter o restante do perfil intacto, adicionar apenas seção curta "Modo de execução: Kiro_Brain interpreta Athena dentro do chat (Spec 5)".
3. WHEN o usuário rodar `caos perfil validar Athena`, THE perfil SHALL continuar passando todas as validações do Spec 1.

### Requirement 7: Debate-prova de ponta a ponta

**User Story:** Como usuário, quero ver o Conselho funcionar em um caso real antes de confiar nele para decisões reais.

#### Acceptance Criteria

1. THE Spec 5 SHALL incluir, como última tarefa, **um Debate real conduzido pelo Kiro_Brain** sobre o tema "**Como aprimorar a estratégia ORB para visar 55-65% de win rate**".
2. THE Debate SHALL passar por todas as fases relevantes (PROPOSTAS, CRITICA, AVALIACAO_RISCO se houver alteração de exposição, AVALIACAO_TECNICA se houver código novo, SINTESE).
3. THE Debate SHALL ter pelo menos:
   - 3 propostas distintas (Mister_M, Manolo, Odin no mínimo).
   - 1 turno de Devil's Advocate por proposta.
   - 1 turno de Cerberus se há alteração de exposição.
   - 1 turno de Hermes se há código novo.
   - Síntese da Athena.
   - Pelo menos 1 ação concreta na Decisão (ex: "implementar variante X em Spec 6", "rejeitar variante Y", "buscar mais dados antes de decidir Z").
4. THE arquivo do Debate SHALL ser commitado com `caos debate fechar <identificador>` e a Decisão SHALL passar a Property 21.
5. WHEN o usuário ler a Decisão, THE conteúdo SHALL ser materialmente útil — não placeholder. O Explorador SHALL ter buscado pelo menos 1 paper real via web_search.

### Requirement 8: Observabilidade e mecanismo de freio

**User Story:** Como usuário, quero confiar que se o Kiro_Brain enlouquecer, eu tenho freios claros para conter danos.

#### Acceptance Criteria

1. THE Kiro_Brain SHALL **NUNCA** rodar `caos walk-forward run` sozinho — apenas o usuário pode disparar Walk-Forward. O Kiro_Brain pode preparar configuração e sugerir a execução, mas não executar.
2. THE Kiro_Brain SHALL **NUNCA** copiar arquivos para `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\` — apenas escrever em `04_CODIGO/ninjascript/` que é cópia versionada.
3. THE Kiro_Brain SHALL **NUNCA** modificar `Decisao_Do_Conselho` ou `Debate` já commitado. Reabertura exige novo Debate com referência ao anterior.
4. WHEN um Debate_Auto for aberto, THE Kiro_Brain SHALL imprimir no chat uma linha resumida do tipo "**[Conselho]** abrindo Debate_Auto `2026-05-22-01-aprimoramento-orb` (gatilho: `walk-forward-resultado-novo`)" antes de começar os turnos, para que o usuário saiba o que está acontecendo.
5. WHEN o usuário pedir "para o Conselho", THE Kiro_Brain SHALL pausar o Debate em andamento, gravar status `em-pausa` no frontmatter, e voltar à conversa normal. Retomar exige comando explícito do usuário.
