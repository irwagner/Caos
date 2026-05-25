# State of Research — 2026-05-25

> Documento vivo. Substitui `STATE-OF-RESEARCH-2026-05-24.md` (mantido como histórico).
>
> **Marco da sessão**: primeira aprovação plena do projeto via `[[Decisao_2026-05-25-02]]`.
> Tag `caos-frozen-2026-05-25-02` aplicada. Hold-out cego de 60 dias úteis em paper trading deve começar.

---

## 1. Estado atual do projeto

### Estratégia aprovada (em hold-out)

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaORBCrabel(modo_nr="nr7"),
        modo="mediana_diaria",
        warmup=30 minutos,
        running_median=True
    ),
    diario=-250 pts, semanal=-750 pts, janela=-1000 pts
)
```

**Métricas consolidadas (WF 2026-05-25-05, 4 janelas WF rolantes 60+60 sobre 14 meses):**

| Métrica | Valor |
|---|---|
| Sharpe mediana | +2.91 |
| Calmar mediana | +3.22 |
| PnL mediano por janela | +240 pts (USD +480) |
| Win rate mediano | 0.45 |
| Trades por janela | 6.5 (mediana) |
| Edge bruto por trade | ~30 pts |
| Pior janela documentada | −1435 pts (USD −2870, dentro do envelope Topstep) |

**Arquivos:**

- Python: `CAOS_Orchestrator/caos/walk_forward/estrategias/{orb_crabel,spread_filter,circuit_breaker}.py` + ORB base.
- C#: `04_CODIGO/ninjascript/StrategyORBCrabelSpreadFilter.cs` + 4 overlays + Strategy_CAOS base.
- Hold-out manual: `04_CODIGO/ninjascript/README_INSTALACAO_HOLDOUT.md`.

### Pré-condições operacionais (Decisão 2026-05-25-02)

1. Hold-out cego de 60 dias úteis em paper trading antes de USD real.
2. `MaxContratos = 1` nos primeiros 30 dias de operação.
3. Liberação para `MaxContratos = 2` exige 30 dias úteis sem trigger de CB de janela ou semanal.
4. Debate de seguimento obrigatório após 30 dias para re-avaliar limites do CB.

---

## 2. Regra de ouro empírica (validada por tick real)

> **Para Sharpe ≥ 1 anualizado em MNQ minute sob fricção Topstep:
> edge bruto necessário ≥ 4 pts/trade.**

Validação:

- **Caracterização tick MNQ 14 meses** (351k minutos amostrados em 5 contratos): `[[Caracterizacao_Spread_MNQ_14_Meses]]`. Spread RTH NY mediano = 0.37 pts. Razão spread/range = 0.0812.
- **Sweep de fricção** `2026-05-24-10..14`: confirmou break-even entre sf=0 (Sharpe +0.24) e sf=0.025 (−0.70). PnL decai linear com sf, ~80 pts/step de 0.025.
- O `slippage_fracao_range = 0.075` usado no sweep é praticamente o valor real (overestimou só 0.9x).

---

## 3. Status histórico das hipóteses testadas

| Família | Hipótese | Status | Sharpe | Comentário |
|---|---|---|---|---|
| Volatility+Filter+CB | **Crabel NR7 + Spread Filter + Circuit Breaker** | **APROVADA** | **+2.91** | Primeira aprovação plena. Hold-out cego. |
| Calendar | Pre-FOMC drift (60/60) | frágil | +6.75 | Win rate 75%, 2 trades/janela. Degrada em 2025 H2. |
| Volatility | Crabel NR7 isolado | rejeitada | -0.57 | Sem filtro spread, marginal negativa. |
| Calendar | Turn-of-Month (Carchano) | bloqueada | +0.44 | Apenas 1 janela com 4 trades. Amostra insuficiente. |
| Intraday momentum | Noise Area (Zarattini) | rejeitada | -8.6 a -10 | Win rate 11%. |
| Intraday mean-rev | Noise Area inverter | rejeitada | -3.4 | Edge bruto 1.7 pts < threshold 4. |
| Overnight | Cooper-Cliff-Gulen | rejeitada | -1.07 | Não replica em futures. |
| Volatility | ORB original | rejeitada | <0 | Confirmado em 4 janelas. |
| Combinado | **Mini-portfolio Pre-FOMC + NR7+SF** | **REFUTADO** | +0.08 | Tese de descorrelação refutada. Fundamenta CB. |

---

## 4. Backlog de próximas hipóteses (ranking por ROI)

Construído a partir do `briefing-explorador-2026-05-25-mentorias-setups.md`.

| # | Hipótese | Custo | Edge potencial | Risco overfit |
|---|---|---|---|---|
| 1 | **OFI (Order Flow Imbalance)** com tick bid/ask | 6h | candidata nova >>5 pts/trade | médio |
| 2 | **Dead Zone filter** (11:30-13:30 ET sem entradas) | 1h | +0.3 a +0.7 Sharpe na aprovada | baixo |
| 3 | **iiii pattern (Al Brooks)** como filtro alternativo NR7 | 2h | candidata 2 ~Sharpe 1 | baixo |
| 4 | **Grid pequeno** combinando overlays existentes | 3h | candidata 2 ~Sharpe 1.5+ | médio |
| 5 | **journal_humano** no ResultadoJanela | 1h | melhora hold-out | nenhum |
| 6 | **ICT Order Block** algorítmico (joshyattridge) | 6h | +/- (cherry-picking?) | alto |
| 7 | **Volatility regime filter** (GC/CL leading equities) | 4h | ?? | médio |
| 8 | **Variantes Pre-FOMC** (filtros press conference, dia da semana) | 3h | recupera candidata | baixo |

### Recomendação para próxima sessão

**OFI primeiro** (#1). Fundamentos:

- Já temos tick bid/ask processado em `dados/MNQ/MNQ_*/tick/spread_minuto.csv` (351k minutos).
- OFI é a única abordagem que pode produzir edge > 5 pts/trade **estruturalmente diferente** das outras testadas.
- Se OFI passar a regra de ouro, vira candidata 2 com **alta diversidade** com a aprovada (Crabel é volatility, OFI é microstructure).

**Dead Zone + iiii em paralelo** (#2 + #3). Custo combinado 3h, baixo risco.

---

## 5. Inventário operacional

### Plugins implementados (`CAOS_Orchestrator/caos/walk_forward/estrategias/`)

| Plugin | Status | Testes | Uso |
|---|---|---|---|
| EstrategiaORB | usado | 30+ | Base ORB |
| EstrategiaORBCrabel (NR4/NR7) | **APROVADO** | sim | Componente da estratégia aprovada |
| EstrategiaPreFomcDrift | frágil | 16 | Calendar |
| EstrategiaTurnOfMonth | bloqueada | 22 | Calendar |
| EstrategiaNoiseArea | rejeitada | 18 | Intraday momentum/inverter |
| EstrategiaOvernightDrift | rejeitada | 6 | Overnight |
| EstrategiaSpreadFilter | **APROVADO** (overlay) | 15 | Componente aprovado |
| EstrategiaCircuitBreaker | **APROVADO** (overlay) | 11 | Componente aprovado |
| EstrategiaPortfolio | usado em refutação | 10 | Meta-estrategia |

Suite completa: 1100+ testes verdes.

### Plugins NinjaScript (`04_CODIGO/ninjascript/`)

| Arquivo | Função |
|---|---|
| `Strategy.cs` | Strategy_CAOS base (Spec 3) |
| `Cerberus.cs` | Risk gate (Spec 3) |
| `TrailingTresFases.cs` | Trailing stop |
| `MfeMaeTracker.cs` | MFE/MAE em tempo real |
| `Logger.cs` | Logging estruturado |
| `EstrategiaORBLogica.cs` | ORB pura (testável) |
| `EstrategiaCrabelLogica.cs` | NR7 filter (NOVO) |
| `SpreadFilterLogica.cs` | Running median (NOVO) |
| `CircuitBreakerEstendido.cs` | CB diário/semanal/janela (NOVO) |
| `StrategyORBCrabelSpreadFilter.cs` | **Strategy aprovada** (NOVO) |
| `README_INSTALACAO_HOLDOUT.md` | Procedimento manual NT8 |

### Scripts Python auxiliares (`scripts/`)

| Script | Função |
|---|---|
| `rodar_wf_atomico.py` | Build manifesto + run WF (raiz isolada) |
| `rodar_wf_spread_filter.py` | Wrap em SpreadFilter |
| `rodar_wf_nr7_sf_cb.py` | Estratégia aprovada |
| `rodar_wf_portfolio.py` | Mini-portfolio (refutado) |
| `sweep_friccao_noise_area.py` | Varia sf, mede impacto |
| `agregar_spread_tick.py` | Streaming tick.txt → spread_minuto.csv |
| `analisar_spread_mnq.py` | Estatística de spread + relatório |
| `comparar_spread_contratos.py` | Spread evolução temporal |
| `comparar_wfs.py` | Tabela comparativa entre IDs WF |

### Documentação Zettel

`CAOS_Zettelkasten/`:

- `Decisoes_do_Conselho/`: 2026-05-25-01, 2026-05-25-02
- `Walk_Forwards/`: 2026-05-25-{02,03,04,05}
- `Caracterizacoes/`: Caracterizacao_Spread_MNQ_14_Meses
- `Debates/`: Debate_2026-05-25-02
- `API_NinjaTrader_8_Reference/`: Hydra_Reference_Index

---

## 6. Próxima sessão — checklist

Quando retomar:

1. [ ] Status do hold-out (você precisa rodar Caminho A em paper).
2. [ ] Implementar OFI (#1 do backlog).
3. [ ] Se OFI funcionar: abrir Debate Auto formal (gatilho G3).
4. [ ] Implementar Dead Zone filter (#2) — aplicar à estratégia aprovada e medir delta de Sharpe.
5. [ ] Após 30 dias úteis: Debate de seguimento obrigatório.

---

## 7. Riscos abertos

Lista das críticas não-bloqueantes da Decisão 2026-05-25-02 (Devils_Advocate):

- **4 janelas WF é amostra crítica**. Bootstrap entre janelas provavelmente cruza zero. Hold-out vai dizer.
- **Limites do CB são heurísticos**, não estatísticos. Re-avaliação obrigatória após 30 dias.
- **CB calibrado in-sample** no mesmo dataset do teste. Hold-out cego é o teste real.

---

## 8. Cobertura GitHub

- **Repo**: https://github.com/irwagner/Caos
- **Branch**: `master`
- **Tags de congelamento**: `caos-frozen-2026-05-25-02`
- **Último commit**: ver `git log --oneline -5`.
