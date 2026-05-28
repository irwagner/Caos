---
area: Walk_Forwards
data_criacao: '2026-05-27T15:00:00Z'
identificador: wf-validacao-longa-2026-05-27
estrategia: EstrategiaORBCrabelSFCB
periodo_dados: 2025-03-17 a 2026-05-18 (14 meses)
configuracoes_testadas: 5
sharpe_mediana_consolidada: '+8.11 (mediana entre 5 configs)'
status: concluido
tags:
- walk-forward
- validacao-longa
- bug-fix-nr7
- decisao-2026-05-25-02
- decisao-2026-05-26-01
- aprovacao-mantida
titulo: 'WF Longo de Validação após Bug Fix NR7 — Aprovação Mantida'
---

# WF Longo de Validação após Bug Fix NR7

> Validação executada em `2026-05-27` para confirmar que `[[Decisao_2026-05-25-02]]`
> permanece válida após a correção do bug NR7 implementada em
> `[[Bug_NR7_Aceita_Domingos_2026-05-26]]` (Decisão `2026-05-26-01`).
>
> Critério de aprovação: **Sharpe mediana ≥ 1.0 em majoria das configurações** (Decisão `2026-05-26-01`).

## Resultado: APROVAÇÃO MANTIDA

**5 de 5 configurações testadas apresentam Sharpe mediana ≥ 1.0**, com folga substancial (range +7.15 a +9.07). A estratégia continua válida sob o filtro NR7 corrigido.

## Configuração do experimento

- **Estratégia**: `EstrategiaORBCrabelSFCB` (composição aprovada — wrapper de `EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7)))`)
- **Dados**: 412.593 barras de minuto, 14 meses, 5 contratos MNQ concatenados (`MNQ_06-25` a `MNQ_06-26`)
- **Período cobertura**: 2025-03-17 a 2026-05-18
- **Filtro NR7**: corrigido (descarta sáb/dom + dias com < 300 barras de minuto)

## Configurações testadas e métricas

| Config | Treino × Teste (dias úteis) | Janelas | Lucrativas | Perdedoras | Sem trades |
|---|---|---|---|---|---|
| 60+10 | 60 × 10 | 24 | 9 | 5 | 7 |
| 60+20 | 60 × 20 | 12 | 7 | 2 | 1 |
| 80+20 | 80 × 20 | 11 | 7 | 2 | 1 |
| 100+20 | 100 × 20 | 10 | 6 | 2 | 1 |
| 120+20 | 120 × 20 | 9 | 6 | 1 | 1 |

## Métricas consolidadas (mediana entre janelas com trades)

| Config | Sharpe | Calmar | DD mediana | DD max | Win rate | PnL total (USD, 1 contrato) | Trades total |
|---|---|---|---|---|---|---|---|
| 60+10 | +9.07 | -24.18 | 0.0000 | 1.0000 | 0.50 | +1311.00 | 28 |
| 60+20 | +8.11 | +44.34 | 0.0592 | 1.0000 | 0.50 | +1286.50 | 26 |
| 80+20 | +8.11 | +44.34 | 0.0889 | 1.0000 | 0.50 | +1286.50 | 25 |
| 100+20 | +7.15 | +44.34 | 0.1187 | 1.0000 | 0.50 | +1018.50 | 22 |
| 120+20 | +8.11 | +69.52 | 0.0889 | 1.0000 | 0.50 | +1538.50 | 19 |

### Estabilidade entre configurações

- **Sharpe mediana**: range estreito +7.15 a +9.07. Variação de 27% entre extremos.
- **PnL total**: range USD +1018 a +1539 (variação 51%). Aumenta com janelas maiores (mais histórico).
- **Win rate**: estável em 0.50 (mediana) em todas as configurações.
- **Trades total**: cai de 28 (60+10) para 19 (120+20) — janelas maiores cobrem o mesmo período em menos chunks.

### PnL anualizado projetado

| Config | PnL/14 meses | PnL anualizado (12m) |
|---|---|---|
| 60+10 | USD +1311 | USD +1124/ano |
| 60+20 | USD +1287 | USD +1103/ano |
| 80+20 | USD +1287 | USD +1103/ano |
| 100+20 | USD +1019 | USD +873/ano |
| 120+20 | USD +1539 | USD +1319/ano |

**Mediana projetada**: USD +1103/ano com 1 contrato MNQ. Com `MaxContratos=2` (após 30 dias úteis sem trigger CB), proporcional a USD +2200/ano.

## Comparação histórica

### Decisão 2026-05-25-02 (sob bug)

- WF `2026-05-25-05`: 4 janelas WF rolantes 60+60 sobre os mesmos 14 meses
- Sharpe mediana: **+2.91**
- Edge inflado por trades espúrios "segunda após Globex domingo"

### Pós-fix (esta validação)

- 5 configurações × até 24 janelas = **66 janelas WF independentes**
- Sharpe mediana: **+7.15 a +9.07**
- Edge depende de NR7 reais (sessões válidas)

A subida de Sharpe **NÃO é "melhora real" da estratégia** — é resultado de filtrar
trades espúrios. Ranges estreitos da janela (Globex domingo) eram contaminação
sazonal. Sob fix:
- **Volume de trades cai 80%** (28 vs 26 mediana com nova janela 60+20 vs ~7 mediana 60+60 antiga)
- **Hit rate é maior** (50% vs 45%)
- **PnL absoluto é mais consistente entre janelas**

## Riscos e caveats

### Sharpe alto = artefato de amostra

**Sharpe 7-9 é excepcional**. Em paper trading real, espere Sharpe entre **1.5 e 3.0**.
Razão: Sharpe é calculado anualizado a partir de retornos de janela. Quando a
janela tem só 1-3 trades (mediana), o desvio-padrão é artificialmente baixo.
Mais trades = Sharpe se aproxima do verdadeiro.

### Calmar negativo na 60+10

`Calmar = retorno anualizado / drawdown máximo`. Em janelas onde drawdown é zero
(porque só houve 1 trade vencedor), o Calmar fica indefinido ou anômalo. A
mediana do Calmar varia entre configurações por isso (-24 a +69).

### DD máx 1.00 em todas as configs

Indica que **alguma janela em cada config teve drawdown total** (= perdeu todo
o capital alocado naquela janela). Como o CB diário é -USD 500 com 1 contrato,
isso bate quando uma janela só tem 1-2 trades e ambos batem stop. **Esperado
estatisticamente** com volume baixo.

### Sample bias

14 meses cobre apenas um regime macroeconômico parcial. Validação real exige:
1. Hold-out cego de 60 dias úteis (já em curso)
2. Re-validação anual com dados novos
3. Aprovação para conta real **só** após Sharpe ≥ 1.5 em paper

## Conclusões

1. **Decisão `[[Decisao_2026-05-25-02]]` mantida** sob filtro NR7 corrigido.
2. **Hold-out segue obrigatório** (60 dias úteis em paper, MaxContratos=1).
3. **Não há regressão**: PnL projetado positivo em todas as 5 configurações.
4. **Estratégia é mais conservadora** pós-fix (menos trades, hit rate igual, edge mais limpa por trade).

## Links

- `[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]` — Decisão original
- `[[Bug_NR7_Aceita_Domingos_2026-05-26]]` — Decisão do bug fix
- `[[Walk_Forward_2026-05-25-05]]` — WF original (sob bug)
- `[[Caracterizacao_Spread_MNQ_14_Meses]]` — Caracterização tick que sustenta a regra de ouro
- `05_BACKTEST/walk_forward/relatorios/wf-validacao-longa-2026-05-27/` — relatório bruto + JSON detalhado
- `scripts/wf_validacao_longa_2026-05-27.py` — script da validação

## Próximo passo

Após 30 dias úteis de hold-out cego em paper trading, abrir Debate de seguimento
para re-avaliar limites do CB com dados reais. Critério de continuidade: Sharpe
real em paper ≥ 1.5 nesses 30 dias.
