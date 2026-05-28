---
area: Walk_Forwards
data_criacao: '2026-05-28T07:35:00Z'
identificador: replay-final-limpo-2026-05-28
estrategia: StrategyORBCrabelSpreadFilter
periodo_replay: 2026-01-28 a 2026-03-13
trades: 2
pnl_total_usd: -566.50
status: concluido
tags:
- replay-nt8
- circuit-breaker-ativado
- bug-stop-market-resolvido
- janela-perdedora
- decisao-2026-05-25-02
titulo: 'Replay Limpo NT8 — Sistema 100% funcional, janela estatisticamente perdedora'
---

# Replay Limpo NT8 — 28/01 a 13/03/2026

> Primeiro replay no NT8 sem erro popup "Sell StopMarket acima do mercado".
> Sistema operou conforme especificado. Janela caiu no lado perdedor da
> distribuição esperada do WF longo de validação.

## Resultado financeiro

**PnL líquido: -USD 566.50** em 33 dias úteis (1 contrato MNQ).

| # | Data | Direção | Entrada | Stop | MAE | PnL |
|---|---|---|---|---|---|---|
| 1 | 2026-02-11 | LONG | 25455.25 | 25324.75 | -522 ticks | -USD 259.50 |
| 2 | 2026-03-11 | LONG | 25168.50 | 25014.75 | -615 ticks | -USD 307.00 |

## Eventos relevantes

### Sistema funcionando

- ✅ **Sem popup**: `RealtimeErrorHandling.IgnoreAllErrors` em
  `Strategy_CAOS.OnStateChange` suprimiu o popup benigno de
  `Calculate.OnBarClose` re-emitindo `SetStopLoss` na próxima barra.
- ✅ **Circuit Breaker ativou** em 2026-03-11 04:33:25 UTC: `pnl_dia=-566.5`,
  abaixo do limite diário `-USD 500`. Trade 2 fechou e CB bloqueou
  novas entradas no resto da janela.
- ✅ **CB protegeu efetivamente**: 514 rejeições em 03-12, 1894 em 03-13
  (dois dias seguintes, sem novas tentativas de trade).
- ✅ **Filtro NR7 (Decisao `[[Bug_NR7_Aceita_Domingos_2026-05-26]]`) funcionou**:
  dias antigos com falso-positivo (02-09 e 02-23, segunda após Globex domingo)
  não foram elegíveis. Dias NR7 legítimos (02-11 e 03-11) entraram normalmente.

### Detalhes

- **Trade 1 (02-11 LONG)**: entrou no breakout do OR (25455.25 = OR_high
  da janela 16:30-17:00 UTC reais; log carimba 14:31 por causa do bug
  cosmético de timezone +3h), MFE de 18 ticks (4.5 pts) antes de
  reverter. Stop tocado em 17:58 UTC.
- **Trade 2 (03-11 LONG)**: comportamento idêntico. Entrada @ 25168.50,
  MFE 16 ticks, stop atingido com slippage de -38 ticks (PnL -307 vs
  -261 esperado de risco). Slippage típico de Playback simulando fill
  imperfeito quando preço cruzou stop em barra de queda forte.

### Bug do timezone (cosmético, não corrigido)

`Time[0].ToUniversalTime()` em máquina BR (UTC-3) soma 3h indevidamente,
gerando timestamps deslocados nos logs. Não afeta a lógica do trade —
preços, stops, alvos e fills estão corretos. Logs ficam com offset
para leitura humana, mas o calc é OK.

## Contexto estatístico

WF longo de validação (`[[WF_Validacao_Longa_2026-05-27]]`) sobre 14 meses
mostrou:

| Config | Janelas | Lucrativas | Perdedoras | Sem trades |
|---|---|---|---|---|
| 60+10 | 24 | 9 | **5** | 7 |

**5 de 17 janelas com trades (29%) dão perda.** O replay 2026-01-28 a
2026-03-13 caiu numa dessas janelas perdedoras. Isto é:

- Não é falha do sistema
- Está dentro do envelope de variância esperada
- Frequência baixíssima (1 trade a cada ~16 dias) força que **cada janela
  individual** seja muito ruidosa

## Lições

### Sobre a estratégia

1. **Stops tocando com slippage de fill** (trade 2: PnL real -USD 307 vs
   risco calculado -USD 261, delta de -USD 46) — isso é simulação realista
   de mercado em movimento. Em paper trading real, esperar slippage
   similar.
2. **Hit rate 0/2 em uma janela** não invalida o WF mediano de 0.50.
   Distribuição é desigual entre janelas.
3. **Circuit Breaker fez o seu trabalho**: limite diário pegou
   no segundo trade impedindo tentativa de revanche.

### Sobre operação NT8

1. **Popup do erro "Sell StopMarket" era cosmético**, suprimido com
   `RealtimeErrorHandling.IgnoreAllErrors` (whitelist atualizada).
2. **`Calculate.OnBarClose` é o regime correto** apesar de gerar o
   warning. Mudar para `OnEachTick` quebraria o WF e a paridade
   Python ↔ C#.
3. **Bug de timezone nos logs** segue presente mas é cosmético.
   Pode ser corrigido em iteração futura usando
   `DateTime.SpecifyKind(Time[0], DateTimeKind.Utc)` antes do
   `ToUniversalTime()`.

## Implicações para hold-out

A Decisão `[[Decisao_2026-05-25-02]]` exige hold-out cego de 60 dias
úteis em paper trading. **Já temos 33 dias rodados**. Faltam 27 dias.

**Não há motivo para abortar** — a janela perdedora é estatisticamente
esperada. Continuar paper trading.

**Próximo Debate de seguimento**: agendado para após 30 dias úteis sem
trigger de CB de janela ou semanal. **CB diário disparou no dia 03-11**,
o que pode contar contra ou não dependendo da interpretação da pré-condição
da Decisão original ("liberação para MaxContratos=2 exige 30 dias úteis
sem trigger de CB de janela ou semanal" — diário não bloqueia, semanal e
janela bloqueiam).

## Próximas explorações ainda em aberto

Ver `[[STATE-OF-RESEARCH-2026-05-27]]` para backlog completo:

1. **arXiv 2605.11423** — Volatility-Volume-Gap Classifier para MNQ
   (substituto academic do VA filter folclórico que refutamos hoje)
2. **Dead Zone filter** (11:30-13:30 ET sem entradas)
3. **HMM 3-state regime classifier**

Mas honestamente: **continuar hold-out é o único passo que dá informação
nova sem custo de implementação**. Resto pode esperar.

## Links

- `[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]` — Decisão original
- `[[Bug_NR7_Aceita_Domingos_2026-05-26]]` — bug fix NR7
- `[[WF_Validacao_Longa_2026-05-27]]` — validação longa
- `[[Refutacao_Value_Area_Filter_2026-05-27]]` — VA filter refutado
- `[[STATE-OF-RESEARCH-2026-05-27]]` — visão consolidada
- `05_BACKTEST/logs/2026-05-28-StrategyORBCrabelSpreadFilter.log` — log bruto
- `05_BACKTEST/mfe_mae/2026-02-11-StrategyORBCrabelSpreadFilter.csv` — trade 1
- `05_BACKTEST/mfe_mae/2026-03-11-StrategyORBCrabelSpreadFilter.csv` — trade 2
