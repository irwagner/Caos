---
data: 2026-05-22
autor: Athena
justificativa: Whitelist mínima de APIs e tipos NinjaScript autorizados para uso em propostas C# do Conselho. Hermes consulta este arquivo para emitir Veto_Tecnico quando uma proposta usa API fora da lista (R6.3). Atualizada com as APIs novas exigidas pelo núcleo C# do Spec 3 (State.* expandido, Account, MarketPosition, CalculationMode, helpers de tick e barra corrente).
---

# APIs NinjaScript autorizadas

Esta whitelist é consumida pelo agente Hermes durante a fase
`AVALIACAO_TECNICA` do Debate. Qualquer referência a símbolos NinjaScript
fora desta lista no código C# proposto resulta em `Veto_Tecnico` com
categoria `api_nao_autorizada` (R6.3).

A lista é deliberadamente mínima; novos itens só podem ser adicionados
via Decisao_Do_Conselho explícita ou no escopo de um spec ativo.

## APIs Autorizadas

### Tipos base
- Strategy
- Indicator

### Ciclo de vida (OnStateChange)
- OnBarUpdate
- OnStateChange
- State
- State.SetDefaults
- State.Configure
- State.DataLoaded
- State.Historical
- State.Realtime
- Calculate
- IsExitOnSessionCloseStrategy

### Acesso a barras e séries
- BarsArray
- Bars
- Close
- Open
- High
- Low
- Volume
- Time
- CurrentBar
- CurrentBars
- GetCurrentAsk
- GetCurrentBid
- TickSize

### Posição e conta
- Position
- MarketPosition
- Account

### Envio de ordens
- EnterLong
- EnterShort
- ExitLong
- ExitShort
- SetStopLoss
- SetProfitTarget
- CalculationMode

### Diagnóstico
- Print
- RealtimeErrorHandling
- StopTargetHandling
- BarsRequiredToTrade

## Como solicitar inclusão de nova API

1. Agente proponente abre Debate com tag `ninjascript-api-whitelist`.
2. Hermes valida que a API existe na documentação oficial do NinjaTrader 8.
3. Cerberus avalia se o uso pretendido aumenta exposição.
4. Decisao_Do_Conselho com `aprovado_walk_forward: true` autoriza a edição
   deste arquivo, que passa a valer no próximo Debate.

## Histórico de alterações

- **2026-05-22**: Adicionadas para o núcleo do Spec 3 (Strategy_CAOS):
  `State.SetDefaults`, `State.Configure`, `State.DataLoaded`,
  `Calculate`, `IsExitOnSessionCloseStrategy`, `CurrentBar`,
  `CurrentBars`, `GetCurrentAsk`, `GetCurrentBid`, `TickSize`,
  `MarketPosition`, `Account`, `CalculationMode`.
- **2026-05-27**: Adicionados `RealtimeErrorHandling` e
  `StopTargetHandling` em diagnóstico, autorizados pelo escopo
  operacional do hold-out (não alteram exposição). Suprimem popup
  benigno "Sell StopMarket acima do mercado" gerado quando
  `Calculate.OnBarClose` faz stop ser processado no close da próxima
  barra abaixo do stop original. Sem Debate formal — auto-resolved
  por categoria de severidade.
- **2026-05-28**: Adicionado `BarsRequiredToTrade` em diagnóstico
  (Decisão `2026-05-28-01`). Defesa contra reset de estado em troca
  de contrato Continuum no NT8 — quando a instância da strategy é
  destruída e recriada, `BarsRequiredToTrade` força warmup de
  19320 barras (14 dias úteis) antes de aceitar qualquer
  `EnterLong/Short`. Bloqueio nativo NT8, não exige código próprio.
