# Núcleo C# do CAOS — NinjaScript

Esta pasta contém os 5 arquivos C# que formam o núcleo do robô CAOS no NinjaTrader 8 (Spec 3):

| Arquivo | O que faz | Cobre |
|---|---|---|
| `Strategy.cs` | `Strategy_CAOS` — classe base abstrata; estratégias filhas dos Specs 4+ herdam dela | R2, R6, R8 |
| `Cerberus.cs` | `Cerberus_CSharp` — gestão de risco em tempo real (limite de contratos, circuit breaker diário, rollover UTC) | R3 |
| `TrailingTresFases.cs` | `Trailing_3_Fases` — máquina de 3 fases (breakeven → 0.3R → trailing dinâmico) | R4 |
| `MfeMaeTracker.cs` | `MfeMaeTracker` — acompanha MFE/MAE por trade e exporta CSV em `05_BACKTEST/mfe_mae/` | R5 |
| `Logger.cs` | Logger estruturado em `05_BACKTEST/logs/` com fallback para `Print(...)` | R7 |

Todos os arquivos compartilham o namespace `NinjaTrader.NinjaScript.Strategies.CAOS`, exceto `Strategy.cs` que fica em `NinjaTrader.NinjaScript.Strategies` (exigência do NT8 para que o NinjaScript Editor reconheça a Strategy automaticamente).

## Pré-requisitos

- NinjaTrader 8 instalado em `%USERPROFILE%\Documents\NinjaTrader 8\` (instalação per-user padrão).
- Conta `Sim101` configurada (default do NT8). Outras contas geram avisos repetidos no Output Window (R8.3).

## Procedimento de instalação (caminho operacional)

```cmd
:: 1. Copia os 5 .cs para a pasta de scripts do NT8.
copy 04_CODIGO\ninjascript\*.cs "%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\"

:: 2. Abre o NinjaTrader 8 e o NinjaScript Editor.
::    Tools → Edit NinjaScript → Strategy
::    (ou pressione Ctrl+E na tela principal do NT8)

:: 3. No NinjaScript Editor, pressione F5 para compilar.
::    A janela de Output deve mostrar "Compile succeeded".
```

Depois disso, os componentes `Strategy_CAOS`, `Cerberus_CSharp`, etc. ficam disponíveis para qualquer estratégia filha que o usuário criar.

## Configuração do workspace CAOS

Por default os logs e CSVs são gravados em `%USERPROFILE%\CAOS\05_BACKTEST\` (subpasta `logs/` para o `Logger` e `mfe_mae/` para o `MfeMaeTracker`). Para redirecionar para outro caminho (por exemplo `e:\CAOS\`), ajuste a propriedade `CaosWorkspaceRoot` da estratégia diretamente no NT8 (Strategies → Parameters → "Workspace CAOS").

## Como criar uma estratégia filha (Specs 4+)

Exemplo mínimo de estratégia que herda de `Strategy_CAOS`:

```csharp
#region Using declarations
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class MinhaEstrategiaCAOS : Strategy_CAOS
    {
        protected override void OnNovaBarra()
        {
            // Lógica de sinal — exemplo: rompimento de máxima das 5 últimas barras.
            if (Position.MarketPosition != MarketPosition.Flat) return;
            if (CurrentBar < 5) return;
            if (Close[0] > High[1] && Close[0] > High[2] && Close[0] > High[3] && Close[0] > High[4] && Close[0] > High[5])
            {
                double stop  = Low[0] - TickSize * 4;
                double alvo  = Close[0] + (Close[0] - stop) * 2.0;
                EntrarLong(MaxContratos, stop, alvo, "BreakoutLong");
            }
        }
    }
}
```

Salve em `Strategies\MinhaEstrategiaCAOS.cs` ao lado dos arquivos do núcleo, F5 no NinjaScript Editor, e a estratégia aparece na lista de Strategies do NT8 para configurar e habilitar em chart.

## Validação automatizada (Properties 16, 17, 18)

A correção semântica do núcleo é validada por testes em Python (Hypothesis) sobre uma reimplementação fiel da lógica pura em `caos.ninjascript_modelo`:

```cmd
cd CAOS_Orchestrator
pytest tests/property/test_ninjascript_cerberus.py -v   :: Property 16 — Cerberus Soundness
pytest tests/property/test_ninjascript_trailing.py -v   :: Property 17 — Trailing Monotonia
pytest tests/property/test_ninjascript_mfe_mae.py -v    :: Property 18 — MFE/MAE conv. e não-negatividade
```

A validação **não exige .NET SDK, MSBuild externo, NUnit, Visual Studio**. O NT8 é o único compilador C# do escopo (via NinjaScript Editor + F5).

## Disciplina de divergência C# ↔ Python

O modelo Python em `caos.ninjascript_modelo` é o **espelho de correção** dos arquivos C# nesta pasta. Qualquer mudança em um lado deve ser replicada no outro; divergências viram veto técnico durante revisão de código.

Mapeamento direto:

| Arquivo C# | Espelho Python |
|---|---|
| `Cerberus.cs` | `caos/ninjascript_modelo/cerberus.py` |
| `TrailingTresFases.cs` | `caos/ninjascript_modelo/trailing.py` |
| `MfeMaeTracker.cs` | `caos/ninjascript_modelo/mfe_mae.py` |

## APIs NinjaScript usadas

A whitelist consumida por Hermes durante a fase `AVALIACAO_TECNICA` está em `.kiro/steering/ninjascript-api.md`. Qualquer API fora dessa lista provoca veto técnico.

## Estratégias incluídas

### ORB — Opening Range Breakout (Spec 4)

Primeira estratégia plugável real do CAOS. Implementa Opening Range Breakout: define o "opening range" como a faixa formada pelos primeiros N minutos após a abertura da sessão regular (RTH) e gera 1 entrada por sessão quando o preço rompe o range.

| Arquivo | O que faz |
|---|---|
| `EstrategiaORBLogica.cs` | Função pura `DecidirAcao` (porta direta de `caos/walk_forward/estrategias/orb_logica.py`) |
| `StrategyORB.cs` | Subclasse de `Strategy_CAOS` que delega a regra de decisão para `EstrategiaORBLogica` e despacha via `EntrarLong`/`EntrarShort`/`SairLong`/`SairShort` da base |

Parâmetros configuráveis no painel de Strategies do NT8 (todos `[NinjaScriptProperty]` com `[Range]`):

- `MinutosOR` (5–60, default 30)
- `RiscoMultiplicador` (0.5–2.0, default 1.0)
- `AlvoMultiplicador` (0.5–5.0, default 2.0)
- `CooldownMinutos` (0–120, default 15)
- `SessaoInicioUtc` / `SessaoFimUtc` / `HoraCorteEntradasUtc` (HH:mm UTC, defaults `13:30` / `20:00` / `19:00`)
- `RangeMinimoPontos` (default 0.5 — abaixo disso a sessão é pulada)

#### Como habilitar no NT8

```cmd
:: 1. Garantir que TODOS os 7 .cs do núcleo + ORB estão na pasta de Strategies.
copy 04_CODIGO\ninjascript\*.cs "%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\"

:: 2. F5 no NinjaScript Editor.

:: 3. No NT8: Strategies → Add Strategy → "StrategyORB".
::    Configurar conta = Sim101 e instrumento = MNQ 03-26 (ou contrato vigente).
::    Ajustar parâmetros se necessário; defaults rodam direto.
```

#### Como rodar via Walk-Forward (Python)

```cmd
cd CAOS_Orchestrator
caos walk-forward run ^
  --estrategia caos.walk_forward.estrategias.orb:EstrategiaORB ^
  --identificador 2026-04-15-01 ^
  --root e:\CAOS
```

#### Validação automatizada

```cmd
pytest tests/unit/test_orb.py -v                        :: 30 unit tests da regra pura
pytest tests/unit/test_orb_walk_forward_integrado.py -v :: integração com WalkForwardEngine
pytest tests/property/test_orb_python_csharp_paridade.py -v   :: Property 19 — paridade Py↔C#
pytest tests/property/test_orb_determinismo.py -v             :: Property 20 — determinismo end-to-end
```
