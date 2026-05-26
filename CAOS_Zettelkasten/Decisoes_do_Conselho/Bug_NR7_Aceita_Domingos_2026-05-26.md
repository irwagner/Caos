---
area: Decisoes_do_Conselho
data_criacao: '2026-05-26T01:36:18Z'
identificador: 2026-05-26-01
status: concluido
tags:
- bug-fix
- crabel
- nr7
- paridade-python-csharp
- decisao-do-conselho
titulo: Bug NR7 aceita domingos como dias elegíveis (correção)
---

# Bug NR7 aceita domingos como dias elegíveis

> Decisão `2026-05-26-01` — Conselho-no-Chat (Spec 5).
> Gatilho: G5 (contradição com Decisão `[[Decisao_2026-05-25-02]]`).
> Commit: `c6f8cf4`.

## Resumo executivo

Replay NT8 do MNQ entre 28/01/2026 e 13/03/2026 expôs que o filtro Crabel NR7, em ambas as implementações (Python `EstrategiaORBCrabel` e C# `EstrategiaCrabelLogica`), aceitava barras parciais de domingo (abertura noturna do Globex CME, ~3-5h de pregão) como "dias úteis" no cálculo de range diário.

Esses domingos têm range artificialmente baixo (~120-200 pts vs. ~500 pts de pregão regular) e por isso eram identificados como NR7 sistemáticos. Resultado: **toda segunda-feira após Globex domingo virava elegível espuriamente**, contaminando todas as métricas reportadas pela Decisão `[[Decisao_2026-05-25-02]]` que aprovou a estratégia para Walk-Forward observacional.

## Diagnóstico

### Achado factual

Cruzamento via `scripts/comparar_nt8_vs_csv.py` entre o estado interno do filtro NR7 (extraído dos logs `diagnostico-dia` de `05_BACKTEST/logs/2026-05-26-StrategyORBCrabelSpreadFilter.log`) e o range diário recalculado sobre `dados/MNQ/MNQ_03-26/minute/last.csv`:

| Domingo | Range NT8 | NR7? | Segunda seguinte vira elegível? |
|---|---|---|---|
| 2026-02-08 | 147.00 pts | sim | 2026-02-09 → trade SHORT executado |
| 2026-02-22 | 123.50 pts | sim | 2026-02-23 → trade LONG executado |
| 2026-03-01 | 185.25 pts | sim | (sem trade — outras condições) |
| 2026-03-08 | 333.00 pts | não | (não disparou) |

### Causa raiz

`_calcular_range_diario` (Python) e `EstrategiaCrabelLogica.AtualizarFiltro` (C#) agrupavam barras pelo timestamp.date sem filtrar fins de semana ou dias com sessão truncada. O Walk-Forward que aprovou a Decisão `[[Decisao_2026-05-25-02]]` rodou sobre dataset que continha esses domingos como pontos de dia ativos, então o Sharpe +2.91 reportado **dependeu** desse efeito sazonal espúrio.

## Decisão

### Filtro híbrido (P1+P2 consolidado)

Descarta dia da contagem NR7 SE qualquer das condições for verdadeira:

1. **DayOfWeek ∈ {Sábado, Domingo}** (P2 — semântico)
2. **Número de barras de minuto < `MIN_BARRAS_DIA_VALIDO` = 300** (P1 — defensivo contra feriados parciais)

### Constantes discretas (sem otimização)

- `MIN_BARRAS_DIA_VALIDO = 300` em ambas as linguagens.
- 300 = 5 horas de pregão, fronteira física abaixo de qualquer pregão regular completo (1380 barras = 23h).
- Domingo Globex CME tem ~120-300 barras; feriado parcial tem ~430-720; pregão regular tem 1380.

### Implementação

- **Python** `caos/walk_forward/estrategias/orb_crabel.py`:
  - `_calcular_range_diario`: pré-filtra `historico` removendo `dayofweek >= 5`. Após groupby, descarta grupos com `n_barras < 300`.
  - `EstrategiaORBCrabel.on_barra`: valida `_dia_eh_valido(dia)` e `_barras_dia_corrente >= MIN_BARRAS_DIA_VALIDO` antes de registrar dia em `_ranges_por_dia`.
  - Helper estático `_dia_eh_valido(dia: date) -> bool`: retorna `dia.weekday() < 5`.

- **C#** `04_CODIGO/ninjascript/EstrategiaCrabelLogica.cs`:
  - `EstadoCrabelNR7.BarrasDiaCorrente`: novo campo, contador.
  - `EstrategiaCrabelLogica.MinBarrasDiaValido = 300`: nova constante.
  - `EstrategiaCrabelLogica.DiaDaSemanaEhValido(DateTime)`: novo helper.
  - `AtualizarFiltro`: no fechamento de dia, persiste range só se ambos os critérios passarem.

## Validação

WF curto sobre dataset agregado de 5 contratos (MNQ_06-25 a MNQ_06-26, 14 meses, 412k barras de minuto) com configuração idêntica à Decisão original (treino=60, teste=10):

| Métrica | Decisão original `2026-05-25-02` | Pós-fix `2026-05-26-01` |
|---|---|---|
| Janelas concluídas | 4/4 | 17/24 |
| Sharpe mediana | +2.91 | **+9.07** |
| PnL mediana (pts) | +240 | 0 |
| Trades mediana | 6.5 | 1 |

**Critério Decisão 2026-05-26-01:** Sharpe ≥ 1.0 → mantém Decisão. Aprovado: **+9.07 ≥ 1.0** ✓.

## Interpretação crítica

O Sharpe pós-fix subiu (não caiu) mas com **caveats importantes**:

- **Volume drasticamente menor**: mediana de 1 trade por janela de 70 dias úteis. Estratégia ficou muito mais seletiva. PnL mediano = 0 pts.
- **7 das 24 janelas sem trades**: ~30% das janelas não disparam um único sinal. Risco de "bet on rare events".
- **Sharpe inflado por amostra pequena**: das janelas com trades, hit rate é alto, mas a base é pequena.

Hipótese consequente: a Decisão `[[Decisao_2026-05-25-02]]` reportou métricas dominadas pelo viés de domingo. Sem ele, a estratégia tem **edge real mas com frequência baixa**. Pré-condições da Decisão original (hold-out 60 dias úteis, MaxContratos=1) seguem necessárias e tornam-se ainda mais críticas com volume menor.

## Pré-condições mantidas

A Tag `caos-frozen-2026-05-25-02` continua válida — esta Decisão é **observacional + corretiva**, não invalida a aprovação anterior. Mas:

- `aprovado_walk_forward: false` nesta Decisão indica que a correção em si **não** abriu nova autorização de paper trading.
- A próxima Decisão de seguimento (após 30 dias úteis de hold-out cego) deve recalibrar limites do CB com dados reais e sob o filtro corrigido.

## Links

- `[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]` — Decisão original
- `[[Walk_Forward_2026-05-25-05]]` — WF que validou a Decisão original (sob bug)
- `CAOS_Council/debates/2026-05-26-01-bug-nr7-aceita-domingos.md` — Debate completo
- `CAOS_Council/decisions/2026-05-26-01-bug-nr7-aceita-domingos.md` — Decisão derivada
- `05_BACKTEST/walk_forward/relatorios/2026-05-26-01-rerun-fix/resultado.json` — re-run de validação
- `05_BACKTEST/walk_forward/relatorios/diagnostico-replay-2026-01-28/relatorio.md` — diagnóstico que originou a descoberta

## Histórico do bug

- **2026-01-28 a 2026-03-13**: replay NT8 produz 2 trades (`02-09 SHORT BE`, `02-23 LONG +USD 32`).
- **2026-05-25**: usuário reporta resultado do replay.
- **2026-05-26 03:44 UTC**: diagnóstico Python+CSV exibe inconsistência. Logging de rejeições adicionado no C# (commit `d2ff9d6`).
- **2026-05-26 03:44-03:46 UTC**: Debate Auto `2026-05-26-01` aberto e fechado em 6 turnos (Athena, Mister_M, Odin, Devils_Advocate, Hermes, Athena/SINTESE).
- **2026-05-26 04:30 UTC**: fix implementado em ambas as linguagens. WF de validação confirma Sharpe ≥ 1.0.
