# Sandbox CAOS dentro do NinjaTrader 8

> Esta pasta é a **sandbox autorizada** do projeto CAOS dentro do
> install do NT8. Espelhamento da pasta-fonte em
> `e:\CAOS\04_CODIGO\ninjascript\` (versionada no Git).

**Regra de governança** (steering `protocolo-debate-no-chat.md`,
freio humano #1 escopado em 25/mai/2026):

- O Kiro_Brain pode criar, editar, copiar e apagar arquivos LIVREMENTE
  dentro de `Strategies\caos\` para fins de backtest replay e
  simulação.
- **Toda escrita aqui exige cópia espelho** em
  `e:\CAOS\04_CODIGO\ninjascript\` versionada no Git.
- Fora desta pasta (qualquer outro arquivo em `Strategies\` ou
  subpastas-irmãs como `Indicators\`, `AddOns\`), a regra original
  vale: instalação manual do usuário.

## Estratégia presente

`StrategyORBCrabelSpreadFilter` — aprovada pela Decisão
`2026-05-25-02` (commit `7eddd30`, tag `caos-frozen-2026-05-25-02`).

Composição:

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaORBCrabel(modo_nr="nr7"),
        modo="mediana_diaria", warmup=30, running median
    ),
    diario=-250 pts, semanal=-750 pts, janela=-1000 pts
)
```

## Arquivos

- `Strategy.cs` — Strategy_CAOS base (Spec 3)
- `Cerberus.cs` — risk gate (Spec 3)
- `TrailingTresFases.cs` — trailing stop 3 fases
- `MfeMaeTracker.cs` — MFE/MAE em tempo real
- `Logger.cs` — logging estruturado em `05_BACKTEST/logs/`
- `EstrategiaORBLogica.cs` — ORB pura (testável)
- `EstrategiaCrabelLogica.cs` — filtro NR7 (Crabel 1990)
- `SpreadFilterLogica.cs` — running median com warmup
- `CircuitBreakerEstendido.cs` — CB diário/semanal/janela
- `StrategyORB.cs` — Strategy ORB simples (referência)
- **`StrategyORBCrabelSpreadFilter.cs`** — estratégia aprovada

## Como rodar Backtest replay

1. Abra **NinjaTrader 8**.
2. **Tools → Edit NinjaScript → Strategy** → pressione **F5** para compilar.
3. Se aparecer erro de namespace duplicado, verifique se não há
   cópias antigas em outras pastas de `Strategies\`.
4. Após compilar:
   - **New → Strategy Analyzer** (ou `Ctrl+F11`).
   - Selecione `StrategyORBCrabelSpreadFilter`.
   - Instrument: **MNQ** (contrato corrente, ex: `MNQ 09-26`).
   - Bars: **1 minute**.
   - Period: o range que quiser testar.
   - Calculate: **OnBarClose**.
   - Parâmetros: deixe os defaults (são os aprovados pela Decisão).
   - **Run Backtest**.
5. Após backtest validado:
   - Abra **chart** do MNQ 1m em conta **Sim101**.
   - Aplique `StrategyORBCrabelSpreadFilter`.
   - Habilite. Estratégia opera live em paper.

## Como sincronizar com o repo CAOS

Sempre que o Kiro_Brain alterar um arquivo aqui, **uma cópia espelho**
deve estar em `e:\CAOS\04_CODIGO\ninjascript\`. O script
`sincronizar.bat` (nesta pasta) faz isso bidirecionalmente:

```cmd
sincronizar.bat caos-para-repo
sincronizar.bat repo-para-caos
sincronizar.bat verificar
```

Use `verificar` antes de compilar para confirmar que não há
divergência entre a sandbox e o repo.

## O que NÃO fazer

- Editar arquivos fora desta pasta esperando que o Kiro_Brain
  conheça/replique a mudança. Ele só toca aqui.
- Criar arquivos com mesmo nome em outra subpasta de `Strategies\`
  (gera erro "duplicate definition" no NT8).
- Operar em conta funded sem cumprir o hold-out cego de 60 dias úteis
  exigido pela Decisão `2026-05-25-02`.
