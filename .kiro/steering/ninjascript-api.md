---
data: 2026-05-14
autor: Athena
justificativa: Whitelist mínima de APIs e tipos NinjaScript autorizados para uso em propostas C# do Conselho. Hermes consulta este arquivo para emitir Veto_Tecnico quando uma proposta usa API fora da lista (R6.3).
---

# APIs NinjaScript autorizadas

Esta whitelist é consumida pelo agente Hermes durante a fase
`AVALIACAO_TECNICA` do Debate. Qualquer referência a símbolos NinjaScript
fora desta lista no código C# proposto resulta em `Veto_Tecnico` com
categoria `api_nao_autorizada` (R6.3).

A lista é deliberadamente mínima nesta versão inicial; novos itens só
podem ser adicionados via Decisao_Do_Conselho explícita.

## APIs Autorizadas

- Strategy
- Indicator
- OnBarUpdate
- OnStateChange
- State
- State.Historical
- State.Realtime
- BarsArray
- Bars
- Close
- Open
- High
- Low
- Volume
- Time
- Position
- EnterLong
- EnterShort
- ExitLong
- ExitShort
- SetStopLoss
- SetProfitTarget
- Print

## Como solicitar inclusão de nova API

1. Agente proponente abre Debate com tag `ninjascript-api-whitelist`.
2. Hermes valida que a API existe na documentação oficial do NinjaTrader 8.
3. Cerberus avalia se o uso pretendido aumenta exposição.
4. Decisao_Do_Conselho com `aprovado_walk_forward: true` autoriza a edição
   deste arquivo, que passa a valer no próximo Debate.
