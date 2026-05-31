# State of Research — 2026-05-29 (pós-WF VVG)

> Documento vivo. Atualiza `STATE-OF-RESEARCH-2026-05-29.md` (mantido como
> histórico) com o resultado da **Tarefa 11** do spec
> `caos-vvg-late-session-reversal-mnq`.
>
> **Marco da sessão**: o Walk-Forward longo de validação da estratégia
> **VVG Late-Session Reversal** (CB(SF(VVG))) foi executado sobre
> 2025-07-01 a 2026-05-15 (60+10 anchored, 1 contrato MNQ). Resultado:
> **REFUTADA**. Fallback A acionado automaticamente (R7.4 / R9).
> Estratégia **arquivada**. Detalhes em
> `[[Refutacao_VVG_Late_Session_2026-05-29]]`.

---

## 1. Estado atual do projeto

### Estratégia VVG Late-Session Reversal — ARQUIVADA (2026-05-29)

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaVvgLateSessionReversal(),
        modo="mediana_diaria", warmup=30, running_median=True),
    diario=-250, semanal=-750, janela=-1000)
```

**Status**: ARQUIVADA via fallback A (R7.4 / R9) após refutação no WF
longo. Não avança para R8 (replay NT8). Sem hold-out. Tag
`caos-frozen-*` nunca aplicada.

#### Resultado do WF longo (relatório `2026-05-29-01-vvg-late-session`)

| Critério | Observado | Limiar | Resultado |
|---|---|---|---|
| Sharpe mediana | 2.8305 | >= 1.0 | PASSA |
| Calmar mediana | 16.9941 | >= 1.5 | PASSA |
| **PnL total** | **-8.08 pts (USD -16.16)** | > 0 | **FALHA** |
| **Year-stability** | **1/4 trimestres** | >= 3/4 | **FALHA** |

- 16 janelas, apenas **9 trades** no total. Circuit Breaker não
  descartou nada (estratégia operou pouco por si só).
- Year-stability: 2025-Q3 (0 trades), 2025-Q4 (-276.85 pts, Sharpe
  -5.34), 2026-Q1 (1 trade, +60.38), 2026-Q2 (+208.39, Sharpe +12.80,
  único positivo).
- Sharpe/Calmar medianas altas são **artefato de N pequeno** — a mediana
  entre janelas ignora o PnL agregado negativo e a concentração temporal
  dos ganhos. Os critérios robustos (PnL total + year-stability)
  capturaram a refutação que as medianas mascaravam.

Causa-raiz provável (pré-registrada na [[Calibracao_VVG_2026-05-29]]):
stop/target derivados de ATR(14) **diário** (~23h) aplicados a um trade
de **~80 min** são quase decorativos; a maioria das posições fecha por
encerramento forçado às 15:50 EST, e o edge de reversão não se
materializa de forma consistente.

**Anti-overfit (R10.2)**: NÃO recalibrar. Os 5 parâmetros congelados
ficam como estão. Variante com ATR intradiário seria nova estratégia sob
Decisão formal — não conserto desta.

### Pipeline atual

**Vazio.** A candidata vinda do paper arXiv 2605.11423 (Mesfin), eleita
pela [[Decisao_2026-05-29-02]], foi implementada e **refutada no WF**,
conforme o próprio abstract do paper antecipava ("all tested directional
trading strategies fail institutional validation standards"). Aguarda
nova candidata R12-aprovada.

### Conformidade com a previsão

A [[Decisao_2026-05-29-03]] aceitou implementar a VVG **sabendo** que
poderia ser refutada, sob critérios mais rigorosos (year-stability,
T ≥ 2.0, MaxContratos=1 fixo). A refutação é **resultado válido e
esperado** — o pipeline funcionou como projetado, e o fallback A
automático evitou viés de confirmação do experimentador.

---

## 2. Histórico recente de estratégias

| Estratégia | Decisão de origem | Destino |
|---|---|---|
| Crabel NR7 + ORB + SF + CB | [[Decisao_2026-05-25-02]] | ARQUIVADA (re-replay -USD 573,50, fallback A em 2026-05-29) |
| P2 range_absoluto | [[Decisao_2026-05-29-01]] | REFUTADA na calibração (não-estacionariedade) |
| VVG Late-Session Reversal | [[Decisao_2026-05-29-02]] / `-03` | **ARQUIVADA (refutada no WF longo, 2026-05-29)** |

---

## 3. Lições aprendidas (acréscimo)

### Year-stability provou seu valor na primeira aplicação

A emenda de year-stability (≥ 3/4 trimestres com Sharpe positivo) da
[[Decisao_2026-05-29-03]] capturou exatamente a falha que Sharpe/Calmar
medianas mascaravam: com poucos trades e ganhos temporalmente
concentrados, a mediana entre janelas WF é enganosa. **Critérios de
consistência temporal devem permanecer obrigatórios** para qualquer
próxima candidata direcional.

### Stop/target devem casar com o horizonte do trade

ATR de horizonte muito maior que a duração do trade torna stop/target
inertes — a posição morre por EOD antes de tocá-los. Próximas
estratégias intraday de horizonte curto devem calibrar stop/target em
janela compatível com a duração do trade.

---

## 4. Arquivos relacionados

- `CAOS_Zettelkasten/Decisoes_do_Conselho/Refutacao_VVG_Late_Session_2026-05-29.md` (refutação + fallback A)
- `CAOS_Zettelkasten/Walk_Forwards/Calibracao_VVG_2026-05-29.md` (parâmetros congelados + ressalva de risco)
- `05_BACKTEST/walk_forward/relatorios/2026-05-29-01-vvg-late-session/` (resultado.json, avaliacao_criterios.json, relatorio.md, manifest_hash.txt)
- `CAOS_Orchestrator/scripts/rodar_wf_vvg_late_session.py` (script da Tarefa 11)
- `CAOS_Orchestrator/caos/walk_forward/estrategias/vvg_*.py` (código Python, inativo em qualquer composição aprovada)
- `STATE-OF-RESEARCH-2026-05-29.md` (estado anterior, histórico)

---

## 5. Próxima ação esperada do usuário

Pipeline ocioso. Não há ação imediata.

A shopping-list de fontes ainda tem candidatos não triados. Quando surgir
novo paper R12-aprovado, abrir novo Spec/Debate. As lições acumuladas
(hold-out temporal real, year-stability, stop/target casados ao
horizonte, threshold relativo a regime) devem informar o próximo design.
