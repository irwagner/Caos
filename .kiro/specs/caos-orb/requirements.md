# Requirements Document

> Spec 4 — Estratégia ORB (Opening Range Breakout) sobre MNQ

## Introduction

A ORB é a primeira estratégia plugável real do CAOS. Define o "opening range" como a faixa formada pelos primeiros N minutos após a abertura de cada sessão regular (RTH) e gera sinais de entrada quando o preço rompe a máxima ou a mínima desse range. Existe em duas implementações coordenadas:

- **Versão Python** (`caos.walk_forward.estrategias.orb`) — plugin do `WalkForwardEngine` (Spec 2). Exercita o pipeline completo sobre dados históricos do MNQ ou sobre fixtures sintéticos.
- **Versão C#** (`04_CODIGO/ninjascript/StrategyORB.cs`) — subclasse de `Strategy_CAOS` (Spec 3). Roda no NinjaTrader 8 em conta `Sim101`.

As duas implementações **compartilham a mesma regra de decisão**, declarada em parâmetros idênticos. A Property 19 (validação cruzada Python ↔ C#) garante que ambas tomam exatamente os mesmos sinais para a mesma sequência de barras.

Este spec **não cobre**: lógica de saída sofisticada (fica delegada ao `Trailing_3_Fases` do Spec 3 + take profit em 2R), nem otimização de parâmetros (fica para Specs futuros via Walk-Forward), nem operação em conta real (apenas `Sim101`).

## Glossary

- **Opening Range** ou **OR**: par `(high_or, low_or)` formado pelos primeiros `MinutosOR` minutos após o início da Janela_Sessao_RTH.
- **MinutosOR**: parâmetro inteiro em `[5, 60]`. Default 30.
- **Janela_Sessao_RTH**: janela diária de operação. Default `[13:30, 20:00]` UTC (= 09:30–16:00 ET).
- **Hora_Corte_Entradas**: instante UTC após o qual a estratégia não abre novas posições. Default `19:00` UTC.
- **R_Inicial**: risco inicial do trade em pontos do índice. ORB usa `R_Inicial = (high_or - low_or) * RiscoMultiplicador`. Default `RiscoMultiplicador=1.0`.
- **AlvoMultiplicador**: multiplicador de R para o take profit fixo. Default `2.0`.
- **CooldownMinutos**: minutos de espera após uma saída antes de uma nova entrada na mesma sessão. Default 15.

## Requirements

### Requirement 1: Definição do Opening Range

**User Story:** Como Estrategia_ORB, quero formar o opening range nos primeiros minutos da sessão regular para usar como gatilho do dia.

#### Acceptance Criteria

1. THE Estrategia_ORB SHALL acumular `high_or = max(High[i])` e `low_or = min(Low[i])` para todas as barras `i` cuja `timestamp ∈ [sessao_inicio, sessao_inicio + MinutosOR)`.
2. WHEN o opening range estiver formado (já chegou a primeira barra com `timestamp >= sessao_inicio + MinutosOR`), THE Estrategia_ORB SHALL congelar `high_or` e `low_or` para o restante da sessão.
3. THE Estrategia_ORB SHALL resetar `high_or = -inf`, `low_or = +inf` no início de cada nova sessão (detectado por mudança de `timestamp.date()` em UTC).
4. IF não houver pelo menos 1 barra dentro de `[sessao_inicio, sessao_inicio + MinutosOR)`, THEN THE sessão SHALL ser pulada sem gerar trades (`status="sem-trades"` no Walk-Forward).

### Requirement 2: Geração de sinais

**User Story:** Como Estrategia_ORB, quero gerar 1 entrada LONG ou SHORT por sessão quando o preço romper o opening range.

#### Acceptance Criteria

1. WHEN `Close[0] > high_or` E o range estiver formado E `timestamp <= Hora_Corte_Entradas` E não houver posição corrente E não estiver em cooldown, THE Estrategia_ORB SHALL emitir entrada LONG no fechamento da barra.
2. WHEN `Close[0] < low_or` E o range estiver formado E `timestamp <= Hora_Corte_Entradas` E não houver posição corrente E não estiver em cooldown, THE Estrategia_ORB SHALL emitir entrada SHORT no fechamento da barra.
3. THE entrada SHALL ser **única por sessão** (após a primeira entrada do dia, mesmo após saída, novas entradas só voltam a ser permitidas no dia seguinte). O default `MaxEntradasPorSessao=1` cobre R2.3.
4. IF tanto LONG quanto SHORT estiverem disparáveis na mesma barra (impossível com OR válido, mas defensivo), THEN THE Estrategia_ORB SHALL preferir LONG se `Close[0] - high_or > low_or - Close[0]`, caso contrário SHORT.

### Requirement 3: Cálculo de stop e alvo

**User Story:** Como Cerberus, quero risco e alvo declarados explicitamente para autorizar a entrada.

#### Acceptance Criteria

1. WHEN entrada LONG, THE stop SHALL ser `low_or` e o alvo SHALL ser `Close[0] + R_Inicial * AlvoMultiplicador`.
2. WHEN entrada SHORT, THE stop SHALL ser `high_or` e o alvo SHALL ser `Close[0] - R_Inicial * AlvoMultiplicador`.
3. WHERE `R_Inicial = (high_or - low_or) * RiscoMultiplicador` for menor ou igual a `0.5` ponto (range degenerado), THE Estrategia_ORB SHALL pular a sessão sem gerar trade (R1.4).

### Requirement 4: Cooldown e janela de saída

**User Story:** Como gerente de risco, quero evitar overtrading e exposição em fim de sessão.

#### Acceptance Criteria

1. WHEN um trade for fechado, THE Estrategia_ORB SHALL marcar `cooldown_ate = timestamp_saida + CooldownMinutos`.
2. WHILE `timestamp_atual < cooldown_ate`, THE Estrategia_ORB SHALL recusar novas entradas (R2.1, R2.2 retornam `False`).
3. WHEN `timestamp >= sessao_fim - 1 minuto`, THE Estrategia_ORB SHALL fechar posição corrente (saída forçada de fim-de-sessão).

### Requirement 5: Configuração

**User Story:** Como usuário, quero ajustar parâmetros sem recompilar.

#### Acceptance Criteria

1. THE versão Python SHALL aceitar via construtor: `minutos_or` (5–60, default 30), `risco_multiplicador` (0.5–2.0, default 1.0), `alvo_multiplicador` (0.5–5.0, default 2.0), `cooldown_minutos` (0–120, default 15), `hora_corte_entradas_utc` (default `19:00`), `sessao_inicio_utc` (default `13:30`), `sessao_fim_utc` (default `20:00`).
2. THE versão C# SHALL expor parâmetros idênticos via `[NinjaScriptProperty] [Range(...)]`.
3. WHEN qualquer parâmetro estiver fora dos ranges, THE construtor SHALL levantar `ValueError` (Python) ou rejeição via `[Range]` (C#).

### Requirement 6: Determinismo

**User Story:** Como Property 14 do Spec 2, quero que rodadas idênticas da ORB produzam exatamente os mesmos trades.

#### Acceptance Criteria

1. WHEN duas execuções de `WalkForwardEngine.executar` rodarem com a mesma `EstrategiaORB(...)`, mesma `ConfiguracaoWalkForward` e mesmo manifesto, THE lista de trades emitida SHALL ser byte-a-byte idêntica (mesmos timestamps, mesmos preços de entrada/saída, mesmos PnL).
2. THE Estrategia_ORB SHALL não usar `random` nem nada não-determinístico além da própria sequência de barras.

### Requirement 7: Validação cruzada Python ↔ C#

**User Story:** Como Hermes, quero garantia de que as duas implementações tomam decisões idênticas.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter um pacote Python `caos.estrategias_modelo.orb` com `OrbModelo`: a **mesma** lógica de decisão da `EstrategiaORB`, sem dependências do Walk-Forward (entrada: barra a barra + estado; saída: ação `LONG | SHORT | NADA | FECHAR`).
2. THE versão C# (`StrategyORB.cs`) SHALL chamar a mesma função de decisão (porta direta para C#, em `EstrategiaORBLogica.cs`), com casos de teste no espelho Python validando que os dois lados retornam a mesma ação para a mesma sequência de barras.
3. THE `tests/property/test_orb_python_csharp_paridade.py` SHALL rodar a Property 19: para qualquer sequência aleatória de barras OHLCV gerada por Hypothesis, `OrbModelo` (Python) e `OrbModeloCSharpPort` (Python que reproduz fielmente a função em C#) emitem a mesma sequência de ações.

### Requirement 8: Testes unitários e Walk-Forward integrado

**User Story:** Como Hermes, quero suíte unitária + Walk-Forward de smoke validando o pipeline completo.

#### Acceptance Criteria

1. THE `tests/unit/test_orb.py` SHALL cobrir: range vazio (sessão sem barras no intervalo OR), range degenerado (R<=0.5), rompimento LONG, rompimento SHORT, cooldown ativo, hora de corte ultrapassada, fim de sessão forçando fechamento.
2. THE `tests/unit/test_orb_walk_forward_integrado.py` SHALL rodar `WalkForwardEngine.executar` com `EstrategiaORB` sobre fixture sintético (3+ sessões geradas em memória) e validar que o `ResultadoWalkForward` tem `status="concluido"` e `numero_trades >= 1`.
3. WHEN `pytest tests/` rodar com a ORB integrada, THE total SHALL chegar a 808+ verdes (788 atuais + ~20 novos).

### Requirement 9: Documentação

**User Story:** Como usuário, quero passo-a-passo para usar a ORB no Walk-Forward e no NT8.

#### Acceptance Criteria

1. THE `caos/walk_forward/estrategias/orb.py` SHALL ter docstring de módulo descrevendo a regra de decisão e citando R1–R4.
2. THE `04_CODIGO/ninjascript/StrategyORB.cs` SHALL ter comentário-cabeçalho idêntico em pt-BR, com referência cruzada ao módulo Python.
3. THE `04_CODIGO/ninjascript/README.md` SHALL ganhar uma seção "Estratégias incluídas → ORB" com instrução de habilitação no NT8.
4. THE `README.md` da raiz SHALL listar a ORB no resumo dos Specs implementados.
