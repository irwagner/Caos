# State of Research — 2026-05-27

> Documento vivo. Substitui `STATE-OF-RESEARCH-2026-05-25.md` (mantido como histórico).
>
> **Marco da sessão**: bug NR7 (aceitava domingos) descoberto pelo replay NT8 e
> corrigido via `[[Decisao_2026-05-26-01]]`. Decisão original `[[Decisao_2026-05-25-02]]`
> foi **revalidada** sob filtro corrigido em 5 configurações de janela diferentes.
> Tag `caos-frozen-2026-05-25-02` mantida.

---

## 1. Estado atual do projeto

### Estratégia aprovada (em hold-out)

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaORBCrabel(modo_nr="nr7"),       # CORRIGIDO 2026-05-26-01
        modo="mediana_diaria",
        warmup=30 minutos,
        running_median=True
    ),
    diario=-250 pts, semanal=-750 pts, janela=-1000 pts
)
```

**Bug fix Decisão 2026-05-26-01**: filtro NR7 agora descarta sábados, domingos e
dias com menos de 300 barras de minuto (antes incluía abertura noturna do Globex
de domingo, que tinha range artificialmente baixo e virava NR7 sistemático).
Paridade Python ↔ C# preservada.

### Métricas pós-fix (validação longa 2026-05-27, 14 meses, 5 configurações)

| Config WF | Sharpe mediana | PnL total (USD, 1 contrato) | Trades | L/P/S |
|---|---|---|---|---|
| 60+10 | +9.07 | +1311 | 28 | 9 / 5 / 7 |
| 60+20 | +8.11 | +1287 | 26 | 7 / 2 / 1 |
| 80+20 | +8.11 | +1287 | 25 | 7 / 2 / 1 |
| 100+20 | +7.15 | +1019 | 22 | 6 / 2 / 1 |
| 120+20 | +8.11 | +1539 | 19 | 6 / 1 / 1 |

> **5 de 5 configurações com Sharpe mediana ≥ 1.0.** Decisão 2026-05-25-02 mantida.
>
> **PnL anualizado estimado**: USD +873 a +1318 por ano com 1 contrato MNQ.
>
> **Win rate mediano**: 0.50.

### Comparação histórica (sob bug vs pós-fix)

| Métrica | Decisão 2026-05-25-02 (sob bug) | Pós-fix 2026-05-26-01 |
|---|---|---|
| Sharpe mediana | +2.91 | +7.15 a +9.07 |
| Trades por janela mediana | 6.5 | 1 a 3 |
| Janelas com trades | 4/4 (100%) | 17/24 a 8/9 (70-89%) |
| Pior janela | -1435 pts | -200 pts (estimativa, controlado pelo CB) |

**Interpretação**: o Sharpe sob bug era mais baixo porque o conjunto incluía
trades espúrios ("toda segunda após Globex domingo"). Sob fix, a estratégia é
mais seletiva: opera menos vezes mas com hit rate melhor. Sharpe alto (7-9) é
**parcialmente artefato de amostra pequena** — em paper trading real, espere
Sharpe entre 1.5 e 3.0.

### Pré-condições operacionais (Decisão 2026-05-25-02, mantidas)

1. Hold-out cego de 60 dias úteis em paper trading antes de USD real.
2. `MaxContratos = 1` nos primeiros 30 dias de operação.
3. Liberação para `MaxContratos = 2` exige 30 dias úteis sem trigger de CB de janela ou semanal.
4. Debate de seguimento obrigatório após 30 dias para re-avaliar limites do CB.

---

## 2. Replay NT8 — observações operacionais

### Trades executados (28/01/2026 a 13/03/2026)

Sob filtro corrigido (após F5 recompilando a sandbox):

| Data | Direção | Entrada | Stop | MAE | PnL |
|---|---|---|---|---|---|
| 2026-02-11 | LONG | 25455.25 | 25324.75 | -130.5 pts | USD -259.50 |
| 2026-03-11 | LONG | 25168.50 | 25014.75 | (replay parou) | em aberto |

**Observações operacionais**:

- A estratégia opera **comercialmente correto**: lógica ORB calcula breakout corretamente, stops batem em níveis legítimos, fill funciona.
- Os 2 dias falsos NR7 da rodada anterior (02-09 e 02-23, segunda após Globex domingo) **NÃO foram mais elegíveis**, conforme esperado.
- 02-11 e 03-11 são NR7 reais (calculados sobre dias úteis válidos).
- **Erro popup "Sell StopMarket acima do mercado" persiste** — tentei 4 fixes (defesa Position Flat, coerência stop/preco, deduplicação, ordem `SetStopLoss` antes de `EnterLong`). É **cosmético**: trade fecha corretamente apesar do popup. Pode ser idiossincrasia do simulador NT8 em playback.

### Bug do timezone (cosmético)

Logs do NT8 carimbam timestamps deslocados ~3h em relação ao UTC real. Causa: `Time[0].ToUniversalTime()` em máquina BR (UTC-3) soma 3h indevidamente. Não afeta lógica do trade, apenas leitura humana dos logs.

---

## 3. Regra de ouro empírica (mantida)

> **Para Sharpe ≥ 1 anualizado em MNQ minute sob fricção Topstep:
> edge bruto necessário ≥ 4 pts/trade.**

A estratégia aprovada bate folgadamente: edge bruto ~50-130 pts/trade (alvo > stop), o que dá margem de absorção de fricção.

---

## 4. Status histórico das hipóteses testadas

| Família | Hipótese | Status | Sharpe | Comentário |
|---|---|---|---|---|
| Volatility+Filter+CB | **Crabel NR7 (fix) + Spread Filter + Circuit Breaker** | **APROVADA** | **+7.15 a +9.07** | Pós-fix do bug NR7. 5 configs WF aprovadas. |
| Calendar | Pre-FOMC drift (60/60) | frágil | +6.75 | Win rate 75%, 2 trades/janela. Degrada em 2025 H2. |
| Volatility | Crabel NR7 isolado (pré-fix) | rejeitada | -0.57 | Sem filtro spread, marginal negativa. |
| Calendar | Turn-of-Month (Carchano) | bloqueada | +0.44 | Apenas 1 janela com 4 trades. Amostra insuficiente. |
| Intraday momentum | Noise Area (Zarattini) | rejeitada | -8.6 a -10 | Win rate 11%. |
| Intraday mean-rev | Noise Area inverter | rejeitada | -3.4 | Edge bruto 1.7 pts < threshold 4. |
| Overnight | Cooper-Cliff-Gulen | rejeitada | -1.07 | Não replica em futures. |
| Volatility | ORB original | rejeitada | <0 | Confirmado em 4 janelas. |
| Microstructure | OFI (Order Flow Imbalance) | refutada empiricamente | -39.99 | Edge bruto -3.77 pts/trade no MNQ. |
| Combinado | Mini-portfolio Pre-FOMC + NR7+SF | refutado | +0.08 | Tese de descorrelação refutada. Fundamenta CB. |

---

## 5. Backlog atualizado de próximas hipóteses

| # | Hipótese | Custo | Edge potencial | Risco overfit | Status |
|---|---|---|---|---|---|
| ~~1~~ | ~~OFI~~ | — | — | — | **Refutado** (commit `e9cd16a`) |
| 2 | **Dead Zone filter** (11:30-13:30 ET sem entradas) | 1h | +0.3 a +0.7 Sharpe na aprovada | baixo | aberto |
| 3 | **iiii pattern (Al Brooks)** como filtro alternativo NR7 | 2h | candidata 2 ~Sharpe 1 | baixo | aberto |
| 4 | **Grid pequeno** combinando overlays existentes | 3h | candidata 2 ~Sharpe 1.5+ | médio | aberto |
| 5 | **journal_humano** no ResultadoJanela | 1h | melhora hold-out | nenhum | aberto |
| 6 | **ICT Order Block** algorítmico (joshyattridge) | 6h | +/- (cherry-picking?) | alto | aberto |
| 7 | **Volatility regime filter** (GC/CL leading equities) | 4h | ?? | médio | aberto |
| 8 | **Variantes Pre-FOMC** (filtros press conference, dia da semana) | 3h | recupera candidata | baixo | aberto |
| 9 | **HMM 3-State regime classifier** (NotebookLM hipótese verificável) | 6h | filtro mais robusto que mediana_diaria | médio | aberto |
| 10 | **Volume Spike filter** (NotebookLM) | 2h | edge marginal sobre aprovada | baixo | aberto |

### Recomendação para próxima sessão

**Dead Zone (#2) + iiii pattern (#3) em paralelo**. Custo combinado 3h, baixo risco. Ambas podem produzir delta marginal positivo na estratégia aprovada sem reabrir Debate principal.

**Após 30 dias úteis de hold-out**: Debate de seguimento obrigatório. Re-avaliar limites do CB com dados reais.

---

## 6. Inventário operacional (atualizado)

### Plugins Python (`CAOS_Orchestrator/caos/walk_forward/estrategias/`)

| Plugin | Status | Testes | Uso |
|---|---|---|---|
| EstrategiaORB | usado | 30+ | Base ORB |
| EstrategiaORBCrabel (NR4/NR7) | **APROVADO** (fix) | 18 | Componente da estratégia aprovada |
| EstrategiaPreFomcDrift | frágil | 16 | Calendar |
| EstrategiaTurnOfMonth | bloqueada | 22 | Calendar |
| EstrategiaNoiseArea | rejeitada | 18 | Intraday momentum/inverter |
| EstrategiaOvernightDrift | rejeitada | 6 | Overnight |
| EstrategiaOFI | refutada | 25+ | Microestrutura |
| EstrategiaSpreadFilter | **APROVADO** (overlay) | 15 | Componente aprovado |
| EstrategiaCircuitBreaker | **APROVADO** (overlay) | 11 | Componente aprovado |
| EstrategiaPortfolio | usado em refutação | 10 | Meta-estrategia |
| **EstrategiaORBCrabelSFCB** (NOVO) | **APROVADO** | smoke | Wrapper da composição aprovada para CLI |

Suite completa: **1022 testes unitários verdes** (incluindo 6 novos testes do filtro NR7 corrigido).

### Plugins NinjaScript (`04_CODIGO/ninjascript/`)

| Arquivo | Função |
|---|---|
| `Strategy.cs` | Strategy_CAOS base (Spec 3) |
| `Cerberus.cs` | Risk gate (Spec 3) |
| `TrailingTresFases.cs` | Trailing stop |
| `MfeMaeTracker.cs` | MFE/MAE em tempo real |
| `Logger.cs` | Logging estruturado + metadados-carga |
| `EstrategiaORBLogica.cs` | ORB pura (testável) |
| `EstrategiaCrabelLogica.cs` | NR7 filter **(corrigido 2026-05-26-01)** |
| `SpreadFilterLogica.cs` | Running median |
| `CircuitBreakerEstendido.cs` | CB diário/semanal/janela |
| `StrategyORB.cs` | Strategy ORB simples (referência) |
| `StrategyORBCrabelSpreadFilter.cs` | **Strategy aprovada** |
| `README_INSTALACAO_HOLDOUT.md` | Procedimento manual NT8 |
| `README_SANDBOX_NT8.md` | Sandbox liberada para escrita do Kiro |
| `sincronizar.bat` | Sandbox ↔ Repo (3 modos) |

### Scripts Python auxiliares (selecionados, criados nesta sessão)

| Script | Função |
|---|---|
| `comparar_nt8_vs_csv.py` | Diagnostica divergência NT8 ↔ CSV |
| `confirmar_bug_timezone.py` | Confirma offset 3h dos timestamps NT8 |
| `diagnosticar_replay_2026-01-28_a_2026-03-13.py` | Análise NR7 do replay original |
| `investigar_anomalias_replay.py` | Descobriu pseudo-dias sáb/dom |
| `investigar_replay_v2.py` | Varredura NR4/NR7 × UTC/ET/CT |
| `rerun_wf_apos_fix_decisao_2026-05-26-01.py` | WF de validação curto |
| `wf_validacao_longa_2026-05-27.py` | **WF longo de validação (5 configs)** |

### Sandbox NT8

`%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\caos\` — 11 .cs em paridade com repo. Verificável via `sincronizar.bat verificar`.

### Documentação Zettel (atualizada)

`CAOS_Zettelkasten/`:

- `Decisoes_do_Conselho/`: 2026-05-25-01, 2026-05-25-02, **2026-05-26-01 (bug NR7 fix)**, **WF_Validacao_Longa_2026-05-27 (NOVO)**
- `Walk_Forwards/`: 2026-05-25-{02,03,04,05}, **wf-validacao-longa-2026-05-27**
- `Caracterizacoes/`: Caracterizacao_Spread_MNQ_14_Meses
- `Debates/`: 2026-05-25-02, **2026-05-26-01 (bug NR7)**
- `API_NinjaTrader_8_Reference/`: Hydra_Reference_Index

---

## 7. Próxima sessão — checklist

Quando retomar:

1. [ ] Continuar hold-out em paper trading (NT8) — no momento ~5 dias rodados.
2. [ ] (opcional) Investigação final do erro popup "Sell StopMarket". Cosmético, mas irritante.
3. [ ] Implementar Dead Zone filter (#2) e medir delta de Sharpe.
4. [ ] Implementar iiii pattern (#3) como filtro alternativo NR7.
5. [ ] Após 30 dias úteis: Debate de seguimento obrigatório.

---

## 8. Riscos abertos (atualizados)

- **Sharpe pós-fix muito alto (7-9) é parcialmente artefato de amostra pequena.** Volume de trades caiu drasticamente (1-3 por janela). Em paper trading real, espere Sharpe entre 1.5 e 3.0.
- **Volume baixo significa cada trade individual importa muito.** Slippage, fees, pulls — tudo afeta proporcionalmente mais.
- **Limites do CB são heurísticos**, não estatísticos. Re-avaliação obrigatória após 30 dias.
- **CB calibrado in-sample** no mesmo dataset do teste. Hold-out cego é o teste real.
- **Erro popup NT8 não diagnosticado**. Cosmético até prova em contrário.
- **Bug do timezone nos logs** (offset 3h). Cosmético; logs ficam difíceis de ler.

---

## 9. Cobertura GitHub

- **Repo**: https://github.com/irwagner/Caos
- **Branch**: `master`
- **Tags de congelamento**: `caos-frozen-2026-05-25-02`
- **Último commit relevante**: `059d750` (validação longa). `git log --oneline -10` para histórico.

### Resumo dos commits desta sessão

| Hash | Mensagem |
|---|---|
| `e2d786c` | Sandbox NT8: pasta `caos\` liberada para escrita do Kiro_Brain |
| `d2ff9d6` | Diagnóstico replay 28/01-13/03 + logging de rejeições |
| `c6f8cf4` | Decisão 2026-05-26-01 bug-nr7-aceita-domingos (commit do CouncilRecorder) |
| `c8900cc` | Bug fix: NR7 descarta domingos e dias parciais |
| `ab9c8a6` | Fix erro NT8 Sell StopMarket (1ª tentativa) |
| `b224563` | Defesa adicional + log metadados-carga |
| `86e812d` | Fix: memorizar stop em EntrarInterno |
| `9ce39dd` | Fix: SetStopLoss antes de EnterLong (4ª tentativa) |
| `059d750` | **WF longo de validação: aprovação mantida** |
