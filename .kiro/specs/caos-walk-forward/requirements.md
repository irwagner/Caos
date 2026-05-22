# Requirements Document

> Spec 2 — Pipeline de Walk-Forward em Python sobre dados do MNQ

## Introduction

Este spec especifica o pipeline Python que consome os arquivos históricos do contrato MNQ armazenados em `dados/MNQ/`, executa **Walk-Forward** sobre estratégias propostas pelo Conselho (Spec 1) e gera relatórios estruturados que alimentam decisões de Debate.

O Walk-Forward é dividido em janelas: cada janela tem **Treino** (período em que parâmetros podem ser ajustados) e **Teste** (período "às cegas" usado apenas para avaliação). A janela avança no tempo de forma estritamente cronológica, simulando descoberta sem look-ahead.

Este spec **não cobre**: execução do robô em tempo real, lógica C# do NinjaScript (Spec 3), nem novas estratégias de trading (Specs 4+). Cobre exclusivamente o motor de avaliação Python que valida estatisticamente as estratégias antes do código C# ser tocado.

Propriedades transversais: **reprodutibilidade** (mesmo input + seed = mesmo resultado), **isolamento Treino/Teste** (sem look-ahead), **integridade de dados** (todo backtest valida `manifesto.json` antes de rodar), **auditabilidade** (cada janela gera arquivo Markdown que entra no `CAOS_Council/`).

## Glossary

- **Walk_Forward**: Procedimento de validação estatística com janelas Treino+Teste avançando no tempo.
- **Janela_WF**: Par `(periodo_treino, periodo_teste)` cronologicamente ordenado.
- **Periodo_Treino**: Intervalo `[data_inicio_treino, data_fim_treino]` em que parâmetros podem ser ajustados.
- **Periodo_Teste**: Intervalo `[data_inicio_teste, data_fim_teste]` em que apenas avaliação é permitida.
- **Estrategia**: Implementação Python de uma regra de entrada/saída sobre as barras do MNQ.
- **Resultado_Janela**: Métricas geradas por uma janela (Sharpe, Calmar, drawdown máximo, win rate, MFE/MAE médios, número de trades).
- **Resultado_Walk_Forward**: Agregação de todos os Resultado_Janela em um único relatório.
- **Look_Ahead_Violation**: Acesso a dados do Periodo_Teste durante o Periodo_Treino (proibido).
- **Skill_Data_Reader**: Skill em Python que lê CSVs de `dados/MNQ/` em DataFrames com validação de schema.

## Requirements

### Requirement 1: Estrutura do diretório de Walk-Forward

**User Story:** Como Engenheiro-Chefe, quero que o pipeline de Walk-Forward tenha uma estrutura de pastas estável, para que resultados de janelas sejam encontrados de forma previsível.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter o diretório `05_BACKTEST/walk_forward/` com subpastas `janelas/`, `agregados/` e `relatorios/`.
2. THE Projeto_CAOS SHALL conter o módulo Python `CAOS_Orchestrator/caos/walk_forward/` com submódulos `engine.py`, `metricas.py`, `janelas.py` e `relatorio.py`.
3. WHEN o pipeline for executado, THE caos walk-forward SHALL gravar cada Resultado_Janela em `05_BACKTEST/walk_forward/janelas/AAAA-MM-DD-NN-{slug-estrategia}.json`.

### Requirement 2: Configuração de Walk-Forward

**User Story:** Como Cerberus, quero parâmetros de Walk-Forward configuráveis e auditáveis, para que decisões de risco baseadas em backtest sigam o mesmo protocolo.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL declarar `ConfiguracaoWalkForward` com campos `tamanho_treino_dias_uteis` (60–504), `tamanho_teste_dias_uteis` (10–120), `passo_dias_uteis` (igual ao tamanho_teste por default), `instrumento` (string, default "MNQ"), `granularidade` (`"1m"` ou `"tick"`), e `seed` (int).
2. IF `tamanho_teste_dias_uteis` for maior que `tamanho_treino_dias_uteis`, THEN THE Projeto_CAOS SHALL rejeitar a configuração (Treino sempre ≥ Teste).
3. THE Projeto_CAOS SHALL persistir a `ConfiguracaoWalkForward` no cabeçalho de cada Resultado_Janela.

### Requirement 3: Geração de janelas

**User Story:** Como Engenheiro-Chefe, quero que o pipeline gere janelas Treino+Teste de forma determinística, para que duas execuções com o mesmo input gerem exatamente as mesmas janelas.

#### Acceptance Criteria

1. WHEN a configuração for válida, THE caos walk-forward SHALL gerar Janelas_WF não-sobrepostas (Teste de uma janela ≠ Teste da próxima).
2. WHEN gerar janelas sobre N dias úteis disponíveis, THE caos walk-forward SHALL produzir `floor((N - tamanho_treino) / passo)` janelas, descartando o resto.
3. THE caos walk-forward SHALL ordenar Janelas_WF cronologicamente e atribuir NN sequencial 01..99 dentro do mesmo dia de execução.

### Requirement 4: Integridade dos dados antes da execução

**User Story:** Como usuário, quero que o pipeline aborte se o `manifesto.json` indicar inconsistência, para que backtests não rodem sobre dados modificados silenciosamente.

#### Acceptance Criteria

1. WHEN o pipeline iniciar, THE Skill_Data_Integrity SHALL ser invocada antes da primeira leitura de qualquer CSV.
2. IF Skill_Data_Integrity retornar `manifesto-divergente` ou `arquivo-nao-registrado`, THEN THE caos walk-forward SHALL abortar e SHALL sinalizar erro com lista de arquivos afetados.
3. THE Resultado_Walk_Forward SHALL incluir o hash SHA-256 agregado de todos os arquivos lidos.

### Requirement 5: Isolamento Treino/Teste (sem look-ahead)

**User Story:** Como Cerberus, quero garantia formal de que o Periodo_Teste nunca é acessado pela estratégia durante o Periodo_Treino, para que métricas reportadas sejam genuínas.

#### Acceptance Criteria

1. WHEN uma Estrategia for invocada para uma Janela_WF, THE caos walk-forward SHALL passar à estratégia apenas as barras de `[data_inicio_treino, data_fim_treino]` durante a fase de Treino.
2. WHEN a fase de Teste iniciar, THE caos walk-forward SHALL passar barras barra-a-barra em ordem cronológica, e a Estrategia SHALL NOT poder consultar barras futuras.
3. IF a Estrategia tentar acessar uma barra com `timestamp > barra_atual`, THEN THE pipeline SHALL detectar e marcar `Look_Ahead_Violation` no Resultado_Janela.
4. THE pipeline SHALL incluir um teste de propriedade que verifica ausência de Look_Ahead_Violation em todas as janelas executadas.

### Requirement 6: Métricas mínimas por janela

**User Story:** Como Conselho, quero métricas comparáveis entre estratégias para conduzir Debates baseados em evidência.

#### Acceptance Criteria

1. THE Resultado_Janela SHALL incluir `sharpe_anualizado`, `calmar`, `drawdown_maximo_percentual`, `drawdown_maximo_dias`, `win_rate`, `payoff_medio`, `mfe_medio`, `mae_medio`, `numero_trades`, `pnl_total`.
2. WHEN não houver trades no Periodo_Teste, THE Resultado_Janela SHALL marcar campo `numero_trades=0` e métricas dependentes como `null` (não inventar zeros).
3. THE Resultado_Walk_Forward SHALL agregar métricas via `mediana` (não média) por padrão, com versão `media` disponível para inspeção.

### Requirement 7: Reprodutibilidade

**User Story:** Como usuário, quero rodar o mesmo Walk-Forward duas vezes e obter resultados idênticos byte-a-byte, para detectar regressões silenciosas.

#### Acceptance Criteria

1. WHEN o pipeline rodar com mesmo `seed`, mesma `ConfiguracaoWalkForward`, mesmo `manifesto.json` e mesma versão de Estrategia, THE Resultado_Walk_Forward SHALL ser byte-a-byte idêntico entre execuções.
2. IF qualquer dependência mudar (versão de pandas, numpy, etc.), THEN THE pipeline SHALL registrar essas versões no cabeçalho do Resultado_Walk_Forward para diagnóstico.

### Requirement 8: Integração com o Conselho

**User Story:** Como Athena, quero que cada Resultado_Walk_Forward seja consumível pelo Council_Recorder como evidência de Debate.

#### Acceptance Criteria

1. WHEN um Resultado_Walk_Forward for gerado com sucesso, THE caos walk-forward SHALL gerar arquivo `relatorios/AAAA-MM-DD-NN-{slug-estrategia}.md` com frontmatter compatível com `NotaZettel` (área `Decisoes_do_Conselho`).
2. THE arquivo Markdown SHALL conter tabela das métricas por janela e o agregado, em pt-BR.

### Requirement 9: CLI

**User Story:** Como usuário, quero invocar o pipeline via CLI, sem precisar escrever Python.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL expor `caos walk-forward run --estrategia <nome> [--config <path>] [--root <path>]`.
2. THE Projeto_CAOS SHALL expor `caos walk-forward status [--root <path>]` que lista os últimos 10 Resultado_Walk_Forward gerados.
3. IF `--estrategia` apontar para nome desconhecido, THEN THE CLI SHALL listar estratégias disponíveis e sair com exit code 1.

### Requirement 10: Tratamento de falhas

**User Story:** Como usuário, quero que falhas em uma janela individual não invalidem o Walk-Forward inteiro.

#### Acceptance Criteria

1. IF uma Janela_WF falhar (exceção na Estrategia, dados faltando), THEN THE pipeline SHALL registrar a falha com categoria, prosseguir para a próxima janela, e marcar a janela com `status: falha`.
2. IF mais de 30% das janelas falharem, THEN THE pipeline SHALL abortar e marcar Resultado_Walk_Forward com `status: abortado-por-falhas`.
3. THE pipeline SHALL incluir o stderr truncado a 4096 chars de cada janela falha (mesmo limite do Failure_Handler do Spec 1).
