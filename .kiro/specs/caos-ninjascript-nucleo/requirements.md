# Requirements Document

> Spec 3 — Núcleo do Robô C# (NinjaScript base) para o MNQ

## Introduction

Este spec especifica o **núcleo** em C# / NinjaScript do robô CAOS: a Strategy base que opera o MNQ no NinjaTrader 8, gerencia o ciclo de vida de ordens, expõe ganchos para estratégias plugáveis (Specs 4+) e implementa o **gerente de risco Cerberus** (circuit breakers, trailing stop de 3 fases, monitoramento MFE/MAE).

Este spec **não cobre**: lógica de entrada de estratégias específicas (Odin/Mister M/Manolo/Rodrigo virão em Specs 4+), conexão com broker real (apenas `Sim101` para validação), nem integração com o pipeline Walk-Forward (Spec 2 — eles compartilham apenas dados, não código).

Propriedades transversais: **estado bem-definido** (sem ambiguidade entre `State.Historical` e `State.Realtime`), **gestão de ordens idempotente** (não duplica ordens em retries), **risco vetado pelo Cerberus** (qualquer aumento de exposição passa por checagem), **compilação MSBuild limpa** (Hermes do Spec 1 valida).

## Glossary

- **Strategy_CAOS**: Classe C# raiz que estende `NinjaTrader.NinjaScript.Strategies.Strategy`.
- **Estrategia_Plugavel**: Implementação concreta que herda de `Strategy_CAOS` e fornece sinais de entrada.
- **Cerberus_CSharp**: Componente C# que aplica vetos de risco em tempo real (espelha o Cerberus do Spec 1, mas dentro do NT8).
- **Trailing_3_Fases**: Trailing stop em 3 estágios — entrada→breakeven, breakeven→1R, 1R→trailing dinâmico.
- **MFE_MAE**: Maximum Favorable Excursion / Maximum Adverse Excursion por trade.
- **Circuit_Breaker_Diario**: Limite máximo de drawdown diário em USD que, atingido, fecha posição e desativa novas entradas.
- **State_Historical**: Estado em que `OnBarUpdate` rebuilda histórico — ordens NÃO são realmente enviadas.
- **State_Realtime**: Estado em que ordens são enviadas ao broker (em `Sim101` ou conta real).

## Requirements

### Requirement 1: Estrutura do projeto NinjaScript

**User Story:** Como Hermes, quero o projeto C# em estrutura padrão NinjaTrader 8, para que `Skill_MSBuild` consiga compilar via `04_CODIGO/ninjascript/*.csproj`.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter `04_CODIGO/ninjascript/CAOS.csproj` apontando para `Strategy.cs`, `Cerberus.cs`, `TrailingTresFases.cs`, `MfeMaeTracker.cs` e os helpers necessários.
2. THE projeto SHALL referenciar `NinjaTrader.Custom.dll` e `NinjaTrader.Core.dll` da instalação local do NT8 via path relativo configurável em variável de ambiente `NT8_REFERENCES`.
3. WHEN `Skill_MSBuild` for invocada, THE compilação SHALL completar com 0 erros e 0 warnings em até 600 segundos.

### Requirement 2: Strategy_CAOS — esqueleto base

**User Story:** Como Estrategia_Plugavel, quero herdar de `Strategy_CAOS` e receber callbacks bem-definidos, para focar apenas na lógica de entrada.

#### Acceptance Criteria

1. THE `Strategy_CAOS` SHALL declarar métodos virtuais `OnSinalEntrada(...)`, `OnSinalSaida(...)` e `OnNovaBarra(...)` que estratégias filhas sobrescrevem.
2. THE `Strategy_CAOS` SHALL implementar `OnStateChange()` cobrindo `State.SetDefaults`, `State.Configure`, `State.DataLoaded`, `State.Historical` e `State.Realtime`.
3. WHEN `State == State.Historical`, THE `Strategy_CAOS` SHALL recusar invocação de `EnterLong`/`EnterShort` reais — somente simulação interna é permitida.
4. WHEN `State == State.Realtime`, THE `Strategy_CAOS` SHALL permitir envio de ordens, sempre roteadas via `Cerberus_CSharp`.

### Requirement 3: Cerberus_CSharp — gestão de risco em tempo real

**User Story:** Como Gerente de Risco, quero que toda intenção de envio de ordem passe por validação automática.

#### Acceptance Criteria

1. THE `Cerberus_CSharp` SHALL expor `bool PodeAbrirPosicao(int contratos, double stopLossUSD)` que retorna `false` quando o tamanho violar limites configurados.
2. THE `Cerberus_CSharp` SHALL aplicar `Circuit_Breaker_Diario` configurável (default USD 500 de drawdown) — atingido, fecha posição corrente e bloqueia novas entradas até o próximo dia de pregão.
3. IF a Estrategia_Plugavel tentar `EnterLong/EnterShort` sem passar por `Cerberus_CSharp.AutorizarEntrada(...)`, THEN o método base SHALL bloquear e logar `Print("[Cerberus] entrada bloqueada — sem autorização")`.
4. WHEN `Cerberus_CSharp` ativar Circuit Breaker, THE Strategy_CAOS SHALL notificar via Output Window com timestamp e PnL atingido.

### Requirement 4: Trailing Stop de 3 Fases

**User Story:** Como Cerberus, quero trailing stop em 3 fases para proteger ganhos progressivamente.

#### Acceptance Criteria

1. WHEN o preço atingir `entrada + 0.5R` (R = risco inicial), THE `Trailing_3_Fases` SHALL mover stop para entrada (breakeven).
2. WHEN o preço atingir `entrada + 1R`, THE `Trailing_3_Fases` SHALL mover stop para `entrada + 0.3R`.
3. WHEN o preço atingir `entrada + 2R`, THE `Trailing_3_Fases` SHALL ativar trailing dinâmico de `0.5 * R` distância do preço corrente.
4. THE `Trailing_3_Fases` SHALL ser configurável via parâmetros `[NinjaScriptProperty]` na Strategy.

### Requirement 5: MFE/MAE Tracker

**User Story:** Como Conselho, quero estatísticas de MFE/MAE por trade exportadas em CSV para análise no Spec 2.

#### Acceptance Criteria

1. THE `MfeMaeTracker` SHALL acompanhar, por trade aberto, `mfe_atual` e `mae_atual` em ticks.
2. WHEN um trade for fechado, THE `MfeMaeTracker` SHALL escrever uma linha em `05_BACKTEST/mfe_mae/AAAA-MM-DD-strategia.csv` com `id_trade`, `entrada_timestamp`, `saida_timestamp`, `direcao`, `mfe_ticks`, `mae_ticks`, `pnl_usd`.
3. THE arquivo CSV SHALL ter header `id_trade,entrada_timestamp,saida_timestamp,direcao,mfe_ticks,mae_ticks,pnl_usd`.

### Requirement 6: Configuração via NinjaScriptProperty

**User Story:** Como usuário, quero ajustar parâmetros do Cerberus e do Trailing direto no NT8 sem recompilar.

#### Acceptance Criteria

1. THE `Strategy_CAOS` SHALL expor parâmetros `[NinjaScriptProperty]`: `MaxContratos` (1–10), `CircuitBreakerDiarioUSD` (50–5000), `TrailingFase1Multiplicador` (0.0–2.0), `TrailingFase2Multiplicador`, `TrailingFase3Multiplicador`.
2. WHEN os parâmetros estiverem fora dos ranges, THE NT8 SHALL exibir erro de validação ao salvar.

### Requirement 7: Logs auditáveis

**User Story:** Como usuário, quero log estruturado de toda decisão do Cerberus e mudança de fase do Trailing.

#### Acceptance Criteria

1. THE `Strategy_CAOS` SHALL gravar em `05_BACKTEST/logs/AAAA-MM-DD-strategia.log` cada evento: entrada autorizada, entrada bloqueada, mudança de fase do trailing, ativação de Circuit Breaker, fechamento de posição.
2. THE log SHALL ser em formato `<timestamp> <nivel> <evento> <payload-json>` para parsing automático no Spec 2.
3. IF o arquivo de log não puder ser escrito, THEN THE `Strategy_CAOS` SHALL fallback para `Print(...)` no Output Window do NT8.

### Requirement 8: Compatibilidade com Sim101

**User Story:** Como usuário, quero validar a estratégia em conta `Sim101` antes de qualquer conta real.

#### Acceptance Criteria

1. THE `Strategy_CAOS` SHALL operar sem modificações em `Sim101` (conta de simulação do NT8).
2. THE `Strategy_CAOS` SHALL detectar a conta ativa via `Account.Name` e gravar nos logs `conta_ativa: Sim101` ou similar.
3. IF a conta ativa NÃO for `Sim101`, THEN THE `Strategy_CAOS` SHALL exibir aviso `[ATENCAO] Strategy operando em conta REAL: <nome>` no Output Window por 5 vezes consecutivas em barras `Realtime`.

### Requirement 9: Integração com whitelist de APIs (R6.3 do Spec 1)

**User Story:** Como Hermes, quero que o código só use APIs declaradas em `.kiro/steering/ninjascript-api.md`.

#### Acceptance Criteria

1. THE código C# do `Strategy_CAOS` SHALL referenciar APIs apenas a partir do whitelist em `.kiro/steering/ninjascript-api.md`.
2. IF Hermes detectar uma API fora do whitelist durante a fase `AVALIACAO_TECNICA` do Conselho, THEN o veto técnico SHALL impedir merge do código.

### Requirement 10: Testes de unidade (NUnit) para componentes puros

**User Story:** Como Hermes, quero testes unitários cobrindo `Cerberus_CSharp`, `Trailing_3_Fases` e `MfeMaeTracker` sem precisar do NT8 rodando.

#### Acceptance Criteria

1. THE Projeto_CAOS SHALL conter `04_CODIGO/ninjascript_tests/CAOS.Tests.csproj` com NUnit.
2. THE testes SHALL cobrir: Cerberus bloqueando exposição excessiva, Trailing transitando entre as 3 fases corretamente, MfeMaeTracker registrando MFE/MAE em série de barras sintéticas.
3. WHEN `Skill_MSBuild` rodar `dotnet test 04_CODIGO/ninjascript_tests/`, THE saída SHALL incluir 0 falhas.
