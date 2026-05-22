# Requirements Document

> Spec 1 — Infraestrutura do Conselho Multi-Agente CAOS

## Introduction

Este documento especifica os requisitos da infraestrutura do **Projeto CAOS** — um robô de trading quantitativo em C# (NinjaScript / NinjaTrader 8) operando o contrato MNQ — cujo desenvolvimento será conduzido por um **Conselho Multi-Agente de LLMs** orquestrado dentro do Kiro IDE em ambiente Windows.

O escopo deste spec é **exclusivamente a infraestrutura de desenvolvimento** que destrava os specs subsequentes:

- Definição formal das nove personas-agente em `.kiro/agents/`.
- Protocolo de debate entre agentes (proposta, crítica, síntese, veto).
- Base de conhecimento Zettelkasten em Markdown com isolamento de contexto.
- Conjunto de Skills executáveis (terminal Windows, Git, MSBuild, Web Search, leitor de CSV).
- Governança (orçamento de turnos, filtros antibias, versionamento Git, auditoria).
- Estrutura de pastas do projeto e integração da referência histórica do projeto **Hydra**.

Este spec **não cobre**: lógica de trading, código C# do robô, motor de Walk-Forward, indicadores, gestão de ordens. Esses elementos pertencem aos Specs 2, 3 e 4+.

As propriedades transversais de correção que orientam todos os requisitos são: **determinismo**, **auditabilidade**, **isolamento de contexto**, **veto de risco** e **veto técnico**.

## Glossary

- **Projeto_CAOS**: Iniciativa global que abrange o robô de trading e sua infraestrutura de desenvolvimento.
- **O_Conselho**: Conjunto formado pelos nove agentes-persona definidos abaixo.
- **Athena**: Agente Engenheiro-Chefe e orquestrador do Conselho. Modelo nativo Kiro: Claude Opus 4.7.
- **Odin**: Agente especialista em Order Flow (Footprint, Delta, Liquidity Sweeps). Modelo: Claude Sonnet 4.5.
- **Mister_M**: Agente especialista em Fimathe (Caixas, Z1/Z2, inversão). Modelo: MiniMax M2 ou Qwen3.
- **Manolo**: Agente especialista em macro HTF (Fib D-1, VWAP, Estocástico). Modelo: Claude Haiku 4.5.
- **Rodrigo**: Agente Acelerador Adaptativo que modula agressividade pelo win rate. Modelo: DeepSeek V3.1.
- **Cerberus**: Agente Gerente de Risco (Circuit Breakers, Trailing 3 fases, MFE/MAE). Modelo: Claude Sonnet 4.5.
- **Hermes**: Agente Auditor C# (lint, memory leaks, validação NinjaScript). Modelo: Qwen3-Coder ou DeepSeek V3.1.
- **Explorador**: Agente de R&D (scraping de papers e anomalias estatísticas). Modelo: Claude Sonnet 4.5 com web search habilitado.
- **Devils_Advocate**: Agente que quebra teses e previne groupthink. Modelo: MiniMax M2.
- **Debate**: Ciclo formal de interação entre agentes composto por proposta, crítica, síntese e voto, registrado em arquivo Markdown único.
- **Decisao_Do_Conselho**: Artefato Markdown produzido ao final de um Debate, contendo decisão, votos, vetos aplicados e rationale.
- **Veto_De_Risco**: Bloqueio formal emitido por Cerberus quando uma proposta aumenta exposição sem compensação adequada.
- **Veto_Tecnico**: Bloqueio formal emitido por Hermes quando código C# proposto falha em compilação MSBuild ou viola regras NinjaScript.
- **Zettelkasten**: Base de notas Markdown interligadas localizada em `CAOS_Zettelkasten/`, inspirada no padrão Obsidian e no LLM Wiki de Karpathy.
- **Nota_Zettel**: Arquivo Markdown atômico dentro do Zettelkasten, identificado por título único e referenciado por links wiki-style `[[Titulo]]`.
- **Context_Loader**: Mecanismo que seleciona e injeta no prompt de um agente apenas o subconjunto de Notas_Zettel necessário para a tarefa.
- **Skill**: Ferramenta executável que um agente pode invocar (terminal, Git, MSBuild, web search, leitor CSV).
- **Skill_Terminal**: Skill que executa comandos no shell `cmd` do Windows.
- **Skill_Git**: Skill que executa operações Git (branch, commit, tag, revert).
- **Skill_MSBuild**: Skill que invoca o MSBuild para compilar o projeto NinjaScript em background.
- **Skill_Web_Search**: Skill que consulta fontes externas (arXiv, SSRN) com filtros antibias.
- **Skill_CSV_Reader**: Skill em Python local que lê CSVs de telemetria de backtest. Placeholder neste spec; consumida em Spec 2.
- **Skill_Data_Inspector**: Skill que lê metadados dos arquivos de dados do MNQ em `dados/MNQ/` (datas cobertas, número de barras, gaps, descontinuidades) sem carregar o conteúdo completo dos CSVs.
- **Skill_Data_Integrity**: Skill que valida que os arquivos de dados em `dados/MNQ/` continuam consistentes com o `manifesto.json` por meio de comparação do hash SHA-256 do conteúdo de cada arquivo.
- **Skill_LLM_Cache**: Skill que armazena e recupera respostas de invocações de agentes LLM com base em chave determinística composta de identificador do agente, modelo, hash do prompt, hash do contexto e seed.
- **Skill_Token_Budget**: Skill que contabiliza tokens consumidos por agente e por dia e bloqueia novas invocações quando o orçamento configurado é excedido.
- **Manifesto_Dados**: Arquivo `dados/MNQ/manifesto.json` que registra para cada arquivo de dados sob `dados/MNQ/` o nome, tamanho em bytes, data de modificação ISO 8601, número de linhas, hash SHA-256 do conteúdo, período coberto (data inicial e data final) e instrumento.
- **Orcamento_De_Turnos**: Limite máximo de rodadas de mensagens permitido em um Debate antes de forçar síntese.
- **Tag_De_Congelamento**: Git tag aplicada a um commit que captura o estado de código aceito como input de Walk-Forward.
- **Repositorio_Hydra**: Repositório histórico em `https://github.com/irwagner/hydra-trading/tree/main/04_CODIGO/ninjascript/reference` usado como referência de código NinjaScript anterior.

## Requirements

### Requirement 1: Estrutura de pastas do projeto

**User Story:** Como Engenheiro-Chefe (Athena), quero uma estrutura de pastas estável e padronizada, para que todos os agentes encontrem artefatos nos mesmos locais previsíveis.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `.kiro/agents/` destinado a perfis individuais dos agentes.
2. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `.kiro/steering/` destinado a regras de projeto e gotchas do NinjaScript.
3. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `CAOS_Zettelkasten/` destinado a Notas_Zettel.
4. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `CAOS_Council/` destinado a logs de Debate e Decisao_Do_Conselho.
5. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `04_CODIGO/ninjascript/` como placeholder vazio (contendo apenas um arquivo marcador `.gitkeep` de 0 bytes), reservado para código C# de specs futuros.
6. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `05_BACKTEST/` como placeholder vazio (contendo apenas um arquivo marcador `.gitkeep` de 0 bytes), reservado para CSVs históricos do MNQ e scripts Python de specs futuros.
7. THE Projeto_CAOS SHALL conter, na raiz do projeto, o diretório `dados/MNQ/` destinado aos arquivos de dados históricos do contrato MNQ já armazenados pelo usuário.
8. WHEN o usuário executar o comando de inicialização do projeto e qualquer diretório listado nos critérios 1 a 7 estiver ausente, THE Skill_Terminal SHALL criar o diretório ausente usando comandos `cmd` compatíveis com Windows em até 30 segundos por diretório.
9. IF a criação de qualquer diretório listado nos critérios 1 a 7 falhar por permissão negada, caminho inválido ou colisão com arquivo existente de mesmo nome, THEN THE Skill_Terminal SHALL interromper a operação, exibir mensagem de erro indicando o diretório afetado e a causa da falha, e preservar inalterados todos os diretórios já existentes antes da execução.
10. WHEN a execução do comando de inicialização concluir sem falhas, THE Skill_Terminal SHALL exibir uma lista contendo os 7 caminhos verificados dos critérios 1 a 7 com indicação observável de status (criado ou já existente) para cada caminho.

### Requirement 2: Perfis dos nove agentes do Conselho

**User Story:** Como usuário do Kiro, quero cada agente do Conselho declarado como agente customizado do Kiro, para que eu possa invocá-los individualmente e auditar as suas configurações.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter exatamente nove arquivos de perfil em `.kiro/agents/`, um por agente do Conselho, com nomes de arquivo correspondentes a: Athena, Odin, Mister_M, Manolo, Rodrigo, Cerberus, Hermes, Explorador, Devils_Advocate.
2. THE Projeto_CAOS SHALL declarar em cada arquivo de perfil os seguintes campos obrigatórios: nome do agente, identidade (system prompt com no mínimo 1 caractere e no máximo 8000 caracteres), modelo nativo do Kiro, lista de Skills permitidas (lista podendo ser vazia), escopo de decisão (lista enumerada de tipos de decisão que o agente pode emitir, conforme Requirement 3) e formato de saída esperado.
3. THE Projeto_CAOS SHALL atribuir os modelos exatos: Athena → Claude Opus 4.7; Odin → Claude Sonnet 4.5; Mister_M → MiniMax M2 ou Qwen3; Manolo → Claude Haiku 4.5; Rodrigo → DeepSeek V3.1; Cerberus → Claude Sonnet 4.5; Hermes → Qwen3-Coder ou DeepSeek V3.1; Explorador → Claude Sonnet 4.5 com Skill_Web_Search habilitado; Devils_Advocate → MiniMax M2.
4. WHEN um perfil de agente for criado, THE perfil SHALL declarar formato de saída estruturado em Markdown contendo, nesta ordem, as seções obrigatórias: Proposta, Justificativa, Riscos e Confiança, sendo Confiança um número inteiro no intervalo fechado de 0 a 100.
5. IF um perfil de agente declarar uma Skill que não está listada no Requirement 11, THEN THE Projeto_CAOS SHALL marcar o perfil como inválido, impedir a invocação do agente correspondente e exibir mensagem de erro identificando o nome do agente e a Skill não autorizada, preservando o arquivo de perfil original sem modificação.
6. IF um perfil de agente omitir qualquer campo obrigatório listado no critério 2 ou usar um modelo diferente do atribuído no critério 3, THEN THE Projeto_CAOS SHALL marcar o perfil como inválido, impedir a invocação do agente correspondente e exibir mensagem de erro identificando o nome do agente e o campo ausente ou divergente.

### Requirement 3: Steering rules e gotchas NinjaScript

**User Story:** Como agente do Conselho, quero ter acesso a regras de projeto persistentes e gotchas conhecidos do NinjaScript, para que eu não repita erros conhecidos da plataforma.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter em `.kiro/steering/` ao menos uma regra documentando a distinção entre `State.Historical` e `State.Realtime` no NinjaScript 8, contendo definição textual de cada estado, ao menos um exemplo de código C# por estado e ao menos um gotcha conhecido por estado.
2. THE Projeto_CAOS SHALL conter em `.kiro/steering/` regra exigindo idioma português brasileiro nos seguintes documentos: requirements.md, design.md, tasks.md, arquivos de Debate do Conselho e arquivos de Decisao_Do_Conselho.
3. THE Projeto_CAOS SHALL conter em `.kiro/steering/` regra fixando o sistema operacional alvo como Windows e o shell padrão como `cmd`, vetando explicitamente o uso de PowerShell, bash e instruções dependentes de Linux em scripts e exemplos do projeto.
4. THE Projeto_CAOS SHALL conter em `.kiro/steering/` regra estabelecendo o contrato MNQ como instrumento operacional padrão, com a expansão "Micro E-mini Nasdaq-100 Futures" registrada no próprio arquivo da regra.
5. WHEN uma nova regra de steering for adicionada em `.kiro/steering/`, THE regra SHALL conter cabeçalho com os três campos obrigatórios: `data` no formato YYYY-MM-DD, `autor` restrito aos valores `Athena` ou `usuário`, e `justificativa` com no mínimo uma frase completa.
6. IF uma regra de steering apresentar cabeçalho ausente, com campo obrigatório faltando, com `data` fora do formato YYYY-MM-DD, com `autor` fora do conjunto permitido ou com `justificativa` vazia, THEN THE Projeto_CAOS SHALL classificar a regra como inválida, SHALL impedir sua aplicação no projeto e SHALL sinalizar o nome do arquivo e o campo problemático ao usuário.

### Requirement 4: Protocolo de debate do Conselho

**User Story:** Como Engenheiro-Chefe, quero um protocolo de debate fixo, para que cada decisão técnica passe por proposta, crítica e síntese de forma reproduzível.

#### Acceptance Criteria

1. WHEN uma decisão técnica (definida como qualquer escolha que altere arquitetura, dependências, parâmetros de risco, lógica de execução de ordens ou critérios de validação do robô CAOS) for solicitada ao Conselho, THE Athena SHALL iniciar um Debate registrado em `CAOS_Council/debates/AAAA-MM-DD-NN-titulo.md`, onde NN é um sequencial de dois dígitos zero-padded reiniciado a cada dia e `titulo` é uma string em kebab-case com no máximo 60 caracteres ASCII.
2. WHEN um Debate iniciar, THE Athena SHALL definir a fase do Debate como `PROPOSTAS`, SHALL reiniciar o contador de turnos com valor 1, e SHALL executar uma fase de propostas em round-robin em ordem alfabética dos identificadores dos agentes, envolvendo apenas os agentes cujas tags de especialidade declaradas na ficha do agente intersectem ao menos uma das tags do tema do debate, concedendo a cada agente convocado até 5 minutos para submeter sua proposta.
3. IF um agente convocado não submeter proposta dentro do limite de 5 minutos, THEN THE Athena SHALL registrar o turno como `status: ausente`, prosseguir com os demais agentes, e SHALL exigir quórum mínimo de 2 propostas válidas para continuar o Debate ou, caso o quórum não seja atingido, marcar o Debate como `status: sem-quorum` e solicitar arbitragem do usuário.
4. WHEN a fase de propostas terminar com quórum atingido, THE Devils_Advocate SHALL executar uma fase de crítica única produzindo, para cada proposta válida, uma seção que enumere no mínimo um risco, uma falha lógica e um viés identificados, ou justifique explicitamente a ausência de cada item.
5. WHEN a fase de crítica terminar, THE Athena SHALL produzir uma síntese final contendo decisão escolhida, votos nominais por agente classificados em favor, contra ou abstenção, vetos aplicados com identificação do agente que vetou, e rationale com no mínimo um parágrafo justificando a escolha à luz das críticas.
6. THE Athena SHALL definir consenso como aprovação de pelo menos 2/3 dos agentes votantes sem veto aplicado, e em caso de empate THE Athena SHALL aplicar como critério de desempate o voto do agente com maior intersecção de tags de especialidade com o tema do debate.
7. WHEN cada turno do Debate ocorrer, THE Athena SHALL registrar o turno como um bloco Markdown com cabeçalho contendo identificador do agente, identificador do modelo, timestamp em ISO 8601 com fuso horário explícito, e número sequencial do turno iniciando em 1 e incrementando de 1 em 1.
8. IF a síntese não atingir o limiar de consenso de 2/3 dos votantes ou houver veto aplicado sem alternativa aprovada, THEN THE Athena SHALL marcar a Decisao_Do_Conselho como `status: pendente-de-usuario` e SHALL registrar no arquivo do Debate uma solicitação explícita de arbitragem do usuário enumerando os pontos em divergência e as opções remanescentes.

### Requirement 5: Veto de risco por Cerberus

**User Story:** Como Gerente de Risco (Cerberus), quero poder vetar qualquer proposta que aumente exposição sem compensação adequada, para que decisões arriscadas não cheguem ao código.

#### Acceptance Criteria

1. WHEN a fase de propostas do Debate terminar e uma ou mais propostas alterarem limites de exposição, alavancagem, número de contratos, distância de stop ou tamanho de Circuit Breaker, THE Cerberus SHALL iniciar a avaliação dessas propostas e SHALL concluí-la dentro de 60 segundos após o término da fase de propostas e antes do início da síntese da Athena.
2. IF Cerberus identificar aumento de exposição sem compensação adequada, definida como razão retorno/risco esperada ≥ 1,5 documentada na proposta, THEN THE Cerberus SHALL emitir Veto_De_Risco contendo justificativa quantitativa com delta de exposição em percentual, razão retorno/risco calculada e referência à Nota_Zettel correspondente.
3. WHEN um Veto_De_Risco com decisão `bloquear` for emitido, THE Athena SHALL impedir a aceitação da proposta e SHALL registrar o veto na Decisao_Do_Conselho com indicação de bloqueio.
4. WHEN um Veto_De_Risco com decisão `aprovar-com-ressalvas` for emitido, THE Athena SHALL permitir a continuidade da proposta e SHALL registrar as ressalvas na Decisao_Do_Conselho sem bloquear a síntese.
5. THE Cerberus SHALL emitir no máximo um Veto_De_Risco por proposta, contendo decisão binária `bloquear` ou `aprovar-com-ressalvas`.
6. IF Cerberus não emitir Veto_De_Risco dentro de 60 segundos após o término da fase de propostas ou apresentar falha de execução, THEN THE Athena SHALL bloquear a aceitação da proposta e SHALL registrar o evento na Decisao_Do_Conselho com indicação `cerberus-timeout`.

### Requirement 6: Veto técnico por Hermes

**User Story:** Como Auditor C# (Hermes), quero poder vetar qualquer código que falhe na compilação MSBuild ou viole regras do NinjaScript, para que código quebrado nunca seja versionado.

#### Acceptance Criteria

1. WHEN uma proposta no Debate incluir um ou mais arquivos C# destinados ao caminho `04_CODIGO/ninjascript/`, THE Hermes SHALL invocar Skill_MSBuild para compilar o projeto, com tempo máximo de execução de 120 segundos, antes que a Athena emita a síntese final da proposta.
2. IF a compilação MSBuild retornar exit code diferente de zero ou exceder o tempo máximo de 120 segundos, THEN THE Hermes SHALL emitir Veto_Tecnico contendo o exit code observado e a saída do compilador (stdout e stderr concatenados) limitada a 64 KB, sinalizando truncamento quando o limite for excedido.
3. IF o código proposto referenciar uma ou mais APIs do NinjaScript fora das listadas em `.kiro/steering/ninjascript-api.md`, THEN THE Hermes SHALL emitir Veto_Tecnico listando cada referência inválida com o nome do arquivo C#, o número da linha e o identificador da API referenciada.
4. IF o arquivo `.kiro/steering/ninjascript-api.md` estiver ausente ou ilegível no momento da verificação, THEN THE Hermes SHALL emitir Veto_Tecnico indicando a indisponibilidade da fonte de APIs autorizadas e SHALL interromper a verificação da proposta até que o arquivo esteja disponível.
5. WHEN um Veto_Tecnico for emitido por Hermes, THE Athena SHALL marcar a proposta com status Rejeitada e SHALL impedir qualquer transição da proposta para o status Aceita enquanto o veto não for substituído por uma nova proposta sem veto técnico.
6. WHEN um Veto_Tecnico for emitido por Hermes, THE Athena SHALL registrar na Decisao_Do_Conselho o identificador da proposta vetada, a categoria do veto (`compilacao_falhou`, `api_nao_autorizada` ou `steering_indisponivel`) e o conteúdo do Veto_Tecnico recebido.

### Requirement 7: Orçamento de turnos por debate

**User Story:** Como usuário, quero limitar o número de turnos de cada Debate, para que agentes não entrem em loops infinitos consumindo tokens.

#### Acceptance Criteria

1. THE Athena SHALL aplicar Orcamento_De_Turnos com valor padrão de 12 turnos por Debate, onde um turno é definido como uma intervenção de agente registrada no arquivo de Debate.
2. THE Athena SHALL aceitar Orcamento_De_Turnos configurável dentro do intervalo de 4 a 100 turnos, inclusive.
3. WHERE o usuário definir Orcamento_De_Turnos dentro do intervalo de 4 a 100 em `.kiro/steering/`, THE Athena SHALL respeitar o valor configurado.
4. IF o valor de Orcamento_De_Turnos configurado em `.kiro/steering/` estiver fora do intervalo de 4 a 100 ou não for um inteiro, THEN THE Athena SHALL tratar a configuração como inválida, SHALL manter o valor padrão de 12 turnos e SHALL sinalizar erro indicando que o valor configurado está fora do intervalo permitido; THE Athena SHALL não emitir erro quando o valor configurado for um inteiro dentro do intervalo de 4 a 100, inclusive.
5. WHEN o Orcamento_De_Turnos for atingido sem síntese concluída, THE Athena SHALL forçar o encerramento do Debate e SHALL produzir síntese parcial marcando a Decisao_Do_Conselho com `status: timeout`.
6. WHEN a síntese parcial for produzida por timeout, THE Athena SHALL incluir nela, no mínimo, os seguintes campos: decisão provisória ou marcação explícita "sem decisão", lista de propostas avaliadas, lista de vetos aplicados, e motivo do timeout.
7. WHEN o Debate for encerrado, THE Athena SHALL registrar no cabeçalho do arquivo de Debate o número de turnos consumidos e o valor de Orcamento_De_Turnos aplicado.

### Requirement 8: Auditabilidade das decisões em Markdown e Git

**User Story:** Como usuário, quero que toda decisão do Conselho fique versionada em Markdown e em Git, para que eu possa reconstruir o raciocínio histórico de qualquer escolha.

#### Acceptance Criteria

1. WHEN o Conselho registrar o estado final de um Debate como concluído, THE Athena SHALL gravar a Decisao_Do_Conselho em `CAOS_Council/decisions/AAAA-MM-DD-NN-titulo.md`, onde AAAA-MM-DD corresponde à data UTC da conclusão, NN é um inteiro sequencial de 01 a 99 dentro do mesmo dia, e `titulo` é um slug contendo apenas caracteres `[a-z0-9-]` com no máximo 60 caracteres.
2. WHEN a Athena gravar uma Decisao_Do_Conselho, THE Athena SHALL incluir no arquivo os campos obrigatórios: identificador único no formato `AAAA-MM-DD-NN`, lista com no mínimo 1 agente participante, no mínimo 1 proposta, lista de vetos (podendo ser vazia), decisão final não vazia e no mínimo 1 link `[[wiki-style]]` para Notas_Zettel relevantes.
3. IF qualquer campo obrigatório definido no critério 2 estiver ausente ou vazio (exceto a lista de vetos), THEN THE Athena SHALL abortar a gravação da Decisao_Do_Conselho, não criar o arquivo em `CAOS_Council/decisions/` e sinalizar erro ao usuário indicando quais campos obrigatórios falharam na validação.
4. WHEN uma Decisao_Do_Conselho for gravada com sucesso, THE Skill_Git SHALL criar um único commit dedicado contendo exclusivamente o arquivo de debate e o arquivo de decisão correspondente que compartilham o mesmo identificador `AAAA-MM-DD-NN`, e a mensagem do commit SHALL incluir esse identificador.
5. IF a operação de commit executada pelo Skill_Git falhar, THEN THE Skill_Git SHALL preservar inalterados o arquivo de debate e o arquivo de Decisao_Do_Conselho no sistema de arquivos e sinalizar erro ao usuário indicando a falha do commit e o identificador `AAAA-MM-DD-NN` afetado.
6. WHEN uma Decisao_Do_Conselho gravada contiver o campo booleano de aprovação para Walk-Forward com valor verdadeiro, THE Skill_Git SHALL aplicar Tag_De_Congelamento no formato `caos-frozen-AAAA-MM-DD-NN` reutilizando o mesmo identificador da Decisao_Do_Conselho.
7. IF já existir uma tag com o nome `caos-frozen-AAAA-MM-DD-NN` no momento da aplicação descrita no critério 6, THEN THE Skill_Git SHALL não sobrescrever a tag existente e sinalizar erro ao usuário indicando a colisão e o identificador envolvido.

### Requirement 9: Determinismo e reprodutibilidade

**User Story:** Como usuário, quero que dado o mesmo estado do Conselho e o mesmo input, decisões sejam reproduzíveis, para que eu possa confiar nos resultados e detectar regressões.

#### Acceptance Criteria

1. WHEN um Debate for iniciado, THE Athena SHALL registrar no cabeçalho do arquivo de Debate: lista ordenada de agentes participantes, modelo de cada agente, e hash SHA-256 do conjunto de Notas_Zettel injetadas no contexto computado sobre a concatenação dos conteúdos das notas em ordem alfabética por nome de arquivo; THE Athena SHALL registrar a seed de geração somente para os agentes cujo modelo permita configuração de seed e SHALL omitir o campo seed para os demais agentes sem abortar a inicialização do Debate.
2. WHERE o modelo de um agente não permitir configuração de seed, THE Athena SHALL marcar o turno correspondente como `nao-deterministico: true` no cabeçalho do turno.
3. WHEN dois Debates compartilharem mesma lista de agentes, mesmos modelos, mesmo hash SHA-256 de contexto, mesmo input e mesma seed, THE saída do segundo Debate SHALL ser exatamente igual à do primeiro para todos os turnos não marcados como `nao-deterministico`, considerando como igualdade a comparação byte a byte após normalização de fim de linha CRLF para LF e remoção de whitespace de fim de linha.
4. THE Decisao_Do_Conselho SHALL conter um campo `reproduzivel` derivado dos turnos do Debate da seguinte forma: `true` se nenhum turno estiver marcado como `nao-deterministico`; `parcial` se ao menos um turno mas não todos estiverem marcados como `nao-deterministico`; `false` se todos os turnos estiverem marcados como `nao-deterministico`.
5. WHEN um Debate for reexecutado com o mesmo input, mesmos modelos e mesmo hash SHA-256 de contexto de um Debate anterior, THE Athena SHALL comparar a Decisao_Do_Conselho atual com a Decisao_Do_Conselho anterior e, IF a decisão final ou o conjunto de vetos divergir, THEN THE Athena SHALL marcar a nova Decisao_Do_Conselho com `regressao-detectada: true` e SHALL registrar no arquivo o diff dos campos divergentes.

### Requirement 10: Estrutura Zettelkasten e isolamento de contexto

**User Story:** Como agente do Conselho, quero receber apenas as Notas_Zettel relevantes para a minha tarefa, para que meu contexto não seja poluído por informação irrelevante.

#### Acceptance Criteria

1. THE Zettelkasten SHALL conter, no mínimo, as áreas raiz `Modulo_Institucional/`, `Modulo_Risco/`, `API_NinjaTrader_8_Reference/`, `Papers/` e `Decisoes_do_Conselho/`.
2. THE Zettelkasten SHALL adotar links `[[wiki-style]]` compatíveis com Obsidian para referências entre Notas_Zettel.
3. THE Nota_Zettel SHALL conter cabeçalho YAML frontmatter com os seguintes campos obrigatórios e tipos: `titulo` (string não vazia, comprimento entre 1 e 200 caracteres), `area` (string enumerada restrita ao conjunto exato de áreas raiz definidas no critério 1), `tags` (lista de strings, com no mínimo 1 e no máximo 20 elementos, cada tag entre 1 e 50 caracteres), `data_criacao` (string em formato ISO 8601 `YYYY-MM-DDTHH:MM:SSZ`) e `agente_autor` (string enumerada restrita ao conjunto exato dos 9 agentes do Conselho).
4. IF uma Nota_Zettel apresentar frontmatter YAML ausente, malformado, com campo obrigatório faltando, ou com valor que viole os tipos e enumerações definidos no critério 3, THEN THE Context_Loader SHALL classificar a Nota como inválida, SHALL excluí-la do conjunto injetado no prompt e SHALL registrar explicitamente no cabeçalho do turno o caminho absoluto da Nota inválida e o motivo específico da invalidação (categorias: `frontmatter-ausente`, `frontmatter-malformado`, `campo-obrigatorio-faltando` ou `valor-invalido`), sem suprimir nem adiar esse registro.
5. WHEN um agente for invocado em um Debate, THE Context_Loader SHALL injetar no prompt o conjunto formado por todas as Notas_Zettel referenciadas explicitamente pela tarefa e por todas as Notas_Zettel alcançáveis a partir delas em até dois saltos de links `[[wiki-style]]`, incluindo as Notas alcançadas por expansão mesmo que não tenham sido mencionadas literalmente no input da tarefa.
6. THE Context_Loader SHALL considerar uma Nota_Zettel como "referenciada explicitamente pela tarefa" se, e somente se, o nome do arquivo da Nota (com ou sem extensão `.md`) ou um wiki-link `[[NomeDaNota]]` apontando para ela aparecer literalmente no texto de input da tarefa recebida pelo agente.
7. IF uma Nota_Zettel referenciada explicitamente ou alcançada por expansão de links estiver ausente do filesystem do Zettelkasten, THEN THE Context_Loader SHALL registrar um warning no cabeçalho do turno contendo o nome da Nota ausente e o caminho esperado, SHALL omitir a Nota do conjunto injetado e SHALL prosseguir com a injeção das demais Notas válidas sem abortar a invocação.
8. THE Context_Loader SHALL registrar no cabeçalho do turno a lista exata de Notas_Zettel injetadas e o hash SHA-256 agregado dessa lista.
9. IF uma tarefa solicitar mais de 25 Notas_Zettel após a expansão de até dois saltos, THEN THE Context_Loader SHALL truncar a lista mantendo as 25 Notas com maior contagem de backlinks, SHALL aplicar como critério de desempate a `data_criacao` mais recente (primeiro) e o nome do arquivo em ordem lexicográfica ascendente (segundo) e SHALL registrar no cabeçalho do turno a contagem total antes da truncagem, a lista das Notas removidas e o critério aplicado.

### Requirement 11: Catálogo de Skills executáveis

**User Story:** Como agente do Conselho, quero um catálogo declarado de Skills, para que invocações de ferramentas sejam previsíveis e auditáveis.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL declarar Skill_Terminal capaz de executar comandos no shell `cmd` do Windows com timeout configurável de no máximo 300 segundos por invocação e SHALL capturar stdout, stderr e exit code, truncando cada canal de saída a no máximo 10 MB.
2. THE Projeto_CAOS SHALL declarar Skill_Git capaz de executar exclusivamente as operações `branch`, `checkout`, `add`, `commit`, `tag`, `revert` e `log`, com timeout configurável de no máximo 120 segundos por operação, e SHALL rejeitar qualquer outro subcomando do Git.
3. THE Projeto_CAOS SHALL declarar Skill_MSBuild capaz de invocar o MSBuild sobre o projeto NinjaScript localizado em `04_CODIGO/ninjascript/` com timeout configurável de no máximo 600 segundos e SHALL retornar exit code, lista de erros e lista de warnings, contendo cada item os campos arquivo, linha, código e mensagem.
4. THE Projeto_CAOS SHALL declarar Skill_Web_Search capaz de consultar arXiv e SSRN com filtros de termo de busca, intervalo de datas (ano inicial e ano final entre 1900 e o ano corrente) e lista de autores, retornando no máximo 50 resultados por consulta dentro de timeout de 60 segundos, em metadados estruturados contendo título, autores, ano, DOI ou URL e abstract.
5. THE Projeto_CAOS SHALL declarar Skill_CSV_Reader em Python local capaz de ler CSVs de telemetria de até 100 MB sem executá-los, marcada como `status: placeholder` neste spec e consumida em Spec 2.
6. THE Projeto_CAOS SHALL declarar Skill_Data_Inspector capaz de ler metadados de arquivos sob `dados/MNQ/` (nome, tamanho em bytes, data de modificação, número de linhas, período coberto, instrumento) sem carregar o conteúdo completo dos arquivos, com timeout máximo de 60 segundos por arquivo.
7. THE Projeto_CAOS SHALL declarar Skill_Data_Integrity capaz de validar que cada arquivo listado em `dados/MNQ/manifesto.json` mantém o hash SHA-256 registrado, retornando lista de divergências quando houver, com timeout máximo de 120 segundos para validação completa.
8. THE Projeto_CAOS SHALL declarar Skill_LLM_Cache capaz de armazenar e recuperar respostas de agentes em chave determinística `(agente, modelo, hash_prompt, hash_contexto, seed)`, com tempo máximo de busca de 1 segundo por chave e armazenamento local em `CAOS_Orchestrator/.cache/`.
9. THE Projeto_CAOS SHALL declarar Skill_Token_Budget capaz de contabilizar tokens consumidos por agente e por dia, com persistência em `CAOS_Orchestrator/.budget/AAAA-MM-DD.json`, suportando consulta de saldo e bloqueio de invocações quando o orçamento diário do agente é atingido.
10. WHEN um agente invocar uma Skill, THE Projeto_CAOS SHALL registrar a invocação no turno correspondente do Debate com nome da Skill, identificador do agente, timestamp em formato ISO 8601, parâmetros de entrada hashados em SHA-256, exit code e duração em milissegundos.
11. IF um agente tentar invocar uma Skill não listada no perfil em `.kiro/agents/`, THEN THE Projeto_CAOS SHALL bloquear a invocação e SHALL emitir entrada de auditoria com `status: skill-nao-autorizada` contendo nome da Skill solicitada e identificador do agente.
12. IF a execução de uma Skill exceder o timeout configurado ou lançar exceção não tratada, THEN THE Projeto_CAOS SHALL interromper a invocação, SHALL emitir entrada de auditoria com `status: skill-falha` indicando a causa (timeout ou exceção) e SHALL retornar erro ao agente sem alterar o estado do Debate.

### Requirement 12: Filtros antibias do Explorador

**User Story:** Como Engenheiro-Chefe, quero que papers trazidos pelo Explorador passem por filtros mínimos antes de virarem Notas_Zettel, para que survivorship bias e overfitting não contaminem o Conselho.

#### Acceptance Criteria

1. WHEN o Explorador propuser uma Nota_Zettel derivada de um paper, THE Explorador SHALL incluir os campos obrigatórios `sharpe_replicado` (numérico), `sample_size` (inteiro, em dias úteis), `out_of_sample_periodo` (inteiro, em dias úteis), `instrumento_testado` (string não vazia), `survivorship_bias_tratado` (booleano) e `status` (enumerado restrito aos valores `aprovada`, `rejeitada`, `amostra-insuficiente`, `bias-nao-tratado`, `out-of-sample-insuficiente`, `dados-incompletos`), aplicando a ordem de precedência `dados-incompletos` > `rejeitada` > `amostra-insuficiente` > `out-of-sample-insuficiente` > `bias-nao-tratado` quando múltiplas condições de rejeição forem aplicáveis simultaneamente à mesma Nota_Zettel; a verificação de completude e tipo dos campos obrigatórios é realizada pelo critério 6 e este critério 1 assume que tal verificação ocorrerá em separado para fins de atribuição de status.
2. IF o valor de `sharpe_replicado`, computado sobre o conjunto de dados de treino reportado pelo paper, for inferior a 0,5, THEN THE Explorador SHALL atribuir `status: rejeitada` à Nota_Zettel.
3. IF o valor de `sample_size` corresponder a menos de 250 dias úteis de dados, THEN THE Explorador SHALL atribuir `status: amostra-insuficiente` à Nota_Zettel.
4. IF o valor de `survivorship_bias_tratado` for `false`, THEN THE Explorador SHALL atribuir `status: bias-nao-tratado` à Nota_Zettel.
5. THE Explorador SHALL armazenar todas as Notas_Zettel derivadas de papers no diretório `CAOS_Zettelkasten/Papers/` independentemente do valor de `status`.
6. IF qualquer campo obrigatório listado no critério 1 estiver ausente, com tipo divergente do especificado ou com valor fora do domínio permitido em uma Nota_Zettel derivada de paper, THEN THE Explorador SHALL atribuir `status: dados-incompletos` à Nota_Zettel.
7. IF o valor de `out_of_sample_periodo` for inferior a 60 dias úteis, THEN THE Explorador SHALL atribuir `status: out-of-sample-insuficiente` à Nota_Zettel.
8. IF o `status` final de uma Nota_Zettel derivada de paper for diferente de `aprovada`, THEN THE Explorador SHALL impedir a criação de links de entrada para essa Nota_Zettel a partir de quaisquer outras notas do Zettelkasten.

### Requirement 13: Integração da referência histórica do Hydra

**User Story:** Como agente do Conselho, quero acesso ao código do Repositorio_Hydra como referência consultável, para que decisões aproveitem aprendizados anteriores sem reimportar dívida técnica.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter a Nota_Zettel `CAOS_Zettelkasten/API_NinjaTrader_8_Reference/Hydra_Reference_Index.md` com os campos obrigatórios: URL `https://github.com/irwagner/hydra-trading/tree/main/04_CODIGO/ninjascript/reference`, nome do branch de referência `main`, hash do commit referência (string hexadecimal de 40 caracteres) e lista de subdiretórios mapeados, cada subdiretório contendo descrição com no mínimo 1 e no máximo 200 caracteres.
2. WHEN o usuário solicitar consulta a um arquivo do Repositorio_Hydra, THE Skill_Git SHALL clonar ou atualizar uma cópia somente-leitura do branch `main` em `04_CODIGO/ninjascript/reference_hydra/` dentro de timeout máximo de 120 segundos e SHALL registrar o hash do commit obtido (40 caracteres hexadecimais) na Nota_Zettel `Hydra_Reference_Index.md`.
3. IF a operação de clone ou atualização do Repositorio_Hydra falhar por timeout, falha de rede ou repositório inacessível, THEN THE Skill_Git SHALL abortar a operação, preservar a cópia local existente em `04_CODIGO/ninjascript/reference_hydra/` sem modificações e retornar erro tipificado identificando a causa da falha.
4. THE Projeto_CAOS SHALL conter em `.kiro/steering/` regra que marca o diretório `04_CODIGO/ninjascript/reference_hydra/` como somente-referência, vetando observavelmente: modificação de arquivos do diretório, inclusão de qualquer arquivo do diretório no build do projeto e imports diretos no código ativo do Projeto_CAOS.
5. IF um agente propuser cópia direta de código do diretório `reference_hydra/` para o código ativo do Projeto_CAOS, THEN THE Hermes SHALL bloquear a operação até existir Decisao_Do_Conselho explícita autorizando a cópia, contendo os campos obrigatórios: arquivo de origem (caminho relativo dentro de `reference_hydra/`), arquivo de destino (caminho relativo dentro de `04_CODIGO/ninjascript/`) e rationale com no mínimo 1 frase e no máximo 2000 caracteres justificando a adoção.

### Requirement 14: Tratamento de erros e fallback dos Debates

**User Story:** Como usuário, quero que falhas em Skills ou em chamadas de modelo não corrompam o estado do Conselho, para que o histórico de debates permaneça consistente.

#### Acceptance Criteria

1. IF uma Skill invocada durante um Debate retornar exit code diferente de zero ou exceder o timeout de 120 segundos, THEN THE Athena SHALL registrar no turno correspondente o nome da Skill, o exit code (ou indicação de timeout) e a saída padrão truncada em 4096 caracteres.
2. WHEN o erro de uma Skill for registrado em um turno, THE Athena SHALL prosseguir o Debate disponibilizando o registro de falha como contexto de entrada para os turnos subsequentes dos agentes.
3. IF a chamada ao modelo de um agente falhar três vezes consecutivas no mesmo turno, considerando como falha (a) timeout superior a 60 segundos, (b) exceção de transporte de rede ou (c) resposta vazia, e respeitando intervalo mínimo de 2 segundos entre tentativas, THEN THE Athena SHALL marcar o turno como `status: agente-indisponivel` e SHALL prosseguir o Debate sem o agente afetado.
4. IF mais de dois agentes ficarem com `status: agente-indisponivel` no mesmo Debate, THEN THE Athena SHALL abortar o Debate e SHALL gravar Decisao_Do_Conselho com `status: abortado-por-indisponibilidade`, incluindo a lista dos agentes indisponíveis e o número do turno em que ocorreu a abortagem.
5. WHEN um Debate for abortado, THE Skill_Git SHALL commitar o arquivo de Debate contendo todos os turnos registrados até o momento da abortagem e o arquivo Decisao_Do_Conselho contendo o status final de abortagem.

### Requirement 15: Manifesto e integridade dos dados de mercado do MNQ

**User Story:** Como usuário, quero que os arquivos de dados históricos do MNQ tenham integridade verificável, para que execuções de Walk-Forward em Specs futuros não sejam invalidadas por edições silenciosas dos arquivos.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter o arquivo `dados/MNQ/manifesto.json` registrando, para cada arquivo de dados sob `dados/MNQ/` (excluindo o próprio `manifesto.json`), os campos obrigatórios: `nome_arquivo` (caminho relativo), `tamanho_bytes` (inteiro não negativo), `mtime` (ISO 8601 UTC), `num_linhas` (inteiro não negativo), `hash_sha256` (string hexadecimal de 64 caracteres), `periodo_inicial` e `periodo_final` (ambos ISO 8601 ou null), e `instrumento` (string, padrão `MNQ`).
2. WHEN o usuário executar o comando de geração ou atualização do Manifesto_Dados, THE Skill_Data_Inspector SHALL varrer recursivamente `dados/MNQ/`, computar o hash SHA-256 do conteúdo de cada arquivo, derivar `tamanho_bytes`, `mtime`, `num_linhas`, `periodo_inicial` e `periodo_final` a partir dos arquivos, e gravar o resultado em `dados/MNQ/manifesto.json` em formato JSON ordenado deterministicamente por `nome_arquivo` ascendente.
3. IF um arquivo sob `dados/MNQ/` apresentar formato inesperado ou erro de leitura durante a geração do Manifesto_Dados, THEN THE Skill_Data_Inspector SHALL registrar o arquivo problemático em uma lista `falhas` no `manifesto.json` com a categoria do erro e SHALL prosseguir com os demais arquivos sem abortar a operação.
4. WHEN qualquer Skill que leia dados sob `dados/MNQ/` for invocada, THE Skill_Data_Integrity SHALL ser executada antes do consumo dos dados e SHALL comparar o hash SHA-256 atual de cada arquivo lido com o hash registrado em `dados/MNQ/manifesto.json`.
5. IF Skill_Data_Integrity detectar divergência entre o hash atual e o hash registrado para um ou mais arquivos, THEN THE Skill_Data_Integrity SHALL retornar erro tipificado `manifesto-divergente` listando cada arquivo divergente, e THE invocador SHALL abortar a operação de leitura sem consumir os dados afetados.
6. IF um arquivo presente em `dados/MNQ/` não constar em `dados/MNQ/manifesto.json` no momento da validação, THEN THE Skill_Data_Integrity SHALL retornar erro tipificado `arquivo-nao-registrado` indicando o arquivo afetado.

### Requirement 16: Cache determinístico de respostas LLM

**User Story:** Como usuário, quero que respostas determinísticas de agentes sejam cacheadas localmente, para reduzir custo de tokens em re-execuções de Debates idênticos.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL armazenar o cache do Skill_LLM_Cache em `CAOS_Orchestrator/.cache/` em formato JSON, com um arquivo por entrada e nome de arquivo derivado do hash SHA-256 da chave de cache.
2. THE Skill_LLM_Cache SHALL definir a chave de cache como o hash SHA-256 da concatenação canônica dos campos `agente`, `modelo`, `hash_prompt` (SHA-256 do prompt completo), `hash_contexto` (SHA-256 das Notas_Zettel injetadas, computado conforme Requirement 9.1) e `seed` (string vazia quando o modelo não suporta seed).
3. WHEN um agente for invocado, THE Skill_LLM_Cache SHALL consultar o cache pela chave do critério 2 antes de chamar o modelo, e IF houver entrada existente, THEN THE Skill_LLM_Cache SHALL retornar a resposta cacheada e registrar no turno o campo `cache_hit: true`.
4. IF não houver entrada de cache para a chave, THEN THE Skill_LLM_Cache SHALL permitir a chamada ao modelo, gravar a resposta retornada com a chave correspondente após a invocação bem-sucedida, e registrar no turno o campo `cache_hit: false`.
5. WHERE o turno tiver sido marcado como `nao-deterministico: true` no cabeçalho do turno conforme Requirement 9.2, THE Skill_LLM_Cache SHALL não consultar nem gravar entrada de cache para esse turno.
6. THE Skill_LLM_Cache SHALL registrar em cada entrada de cache os campos: `chave`, `agente`, `modelo`, `seed`, `data_criacao` ISO 8601, `tokens_consumidos_estimados` e `resposta`.
7. IF a leitura de uma entrada de cache existente exceder 1 segundo ou retornar JSON inválido, THEN THE Skill_LLM_Cache SHALL tratar a entrada como ausente, registrar `cache_hit: false` no turno e prosseguir com a chamada ao modelo.

### Requirement 17: Orçamento diário de tokens por agente

**User Story:** Como usuário, quero limitar o consumo diário de tokens por agente, para que loops multi-LLM não gerem custo descontrolado.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL persistir o estado diário do Skill_Token_Budget em `CAOS_Orchestrator/.budget/AAAA-MM-DD.json`, contendo para cada agente os campos `agente`, `tokens_input_consumidos`, `tokens_output_consumidos`, `tokens_total_consumidos` e `orcamento_diario_tokens`.
2. THE Skill_Token_Budget SHALL aplicar orçamento diário padrão de 1.000.000 tokens por agente, com possibilidade de configuração diferente por agente em `.kiro/steering/orcamento-de-tokens.md`.
3. WHEN um agente for invocado, THE Skill_Token_Budget SHALL ser consultada antes da chamada ao modelo e SHALL retornar `bloqueado: true` se o orçamento diário do agente já estiver atingido ou seria estourado pela invocação estimada.
4. IF Skill_Token_Budget retornar `bloqueado: true`, THEN THE Athena SHALL marcar o turno do agente afetado como `status: orcamento-de-tokens-esgotado`, prosseguir o Debate sem o agente afetado, e SHALL contabilizar essa indisponibilidade junto às demais para fins do Requirement 14.4.
5. WHEN uma invocação a modelo for concluída, THE Skill_Token_Budget SHALL atualizar `tokens_input_consumidos` e `tokens_output_consumidos` do agente correspondente para o dia atual em UTC e SHALL persistir o estado atualizado em até 1 segundo.
6. IF a configuração de `orcamento_diario_tokens` em `.kiro/steering/orcamento-de-tokens.md` apresentar valor não inteiro ou inferior a 10.000 tokens, THEN THE Skill_Token_Budget SHALL classificar a configuração como inválida, manter o valor padrão de 1.000.000 tokens e sinalizar erro ao usuário.
