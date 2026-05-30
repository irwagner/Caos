---
area: Walk_Forwards
data_criacao: '2026-05-29T00:00:00Z'
identificador: calibracao-vvg-2026-05-29
estrategia: EstrategiaVvgLateSessionReversal
status: parametros-congelados
tags:
- walk-forward
- calibracao
- vvg
- late-session-reversal
- anti-overfit
- mesfin
- arxiv-2605-11423
titulo: 'Calibração obrigatória dos parâmetros pendentes da VVG Late-Session Reversal'
---

# Calibração VVG Late-Session Reversal (MNQ)

> Tarefa 1 do spec `caos-vvg-late-session-reversal-mnq`. Executa a
> calibração obrigatória dos parâmetros pendentes UMA única vez, em
> janela separada, e os **congela em código** (regra anti-overfit
> R10.2). Script: `scripts/calibrar_vvg_2026-05-29.py`.
>
> Decisão precedente: [[Decisao_2026-05-29-03]]
> (`CAOS_Council/decisions/2026-05-29-03-paper-mesfin-falha-em-estabilidade.md`).
> Etapa-zero crítica: [[Etapa_Zero_NotebookLM_Gemini_2026-05-29]].
> Paper-base: arXiv 2605.11423 (Mesfin).

## Janela de calibração e por quê

| Item | Valor |
|---|---|
| Janela de calibração (esta nota) | 2025-03-17 a 2025-06-30 (UTC) |
| Extensão real coberta pelo dataset | 2025-03-17 a 2025-06-13 (local NY) |
| Dataset | `dados/MNQ/_concat_minute_last/01_MNQ_06-25.csv` |
| Janela do WF longo (Tarefa 11) | 2025-07-01 a 2026-05-15 |
| Janela do hold-out / replay (R8) | 2026-06+ |

A calibração roda em janela **disjunta** do Walk-Forward longo e do
hold-out. Esse isolamento é o que impede contaminação dos parâmetros
pela mesma janela em que a estratégia será validada — sem ele, qualquer
"aprovação" no WF seria circular. O dataset `01_MNQ_06-25.csv` cobre
2025-03-17 a 2025-06-13, ou seja, toda a sua extensão cai dentro da
janela de calibração pretendida (não há recorte adicional necessário).

## Output completo do script

Comando (Windows + cmd):

```
set PYTHONIOENCODING=utf-8
python scripts\calibrar_vvg_2026-05-29.py
```

Saída integral:

```
======================================================================
 CALIBRACAO VVG LATE-SESSION REVERSAL — 2026-05-29
 Spec: caos-vvg-late-session-reversal-mnq | Tarefa 1
======================================================================
Dataset            : e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv
Janela calibracao  : 2025-03-17 a 2025-06-13 (local NY)
Barras carregadas  : 87,843
Dias no periodo    : 79
Dias uteis validos : 64 (weekday<5 e >= 300 barras)
Dias classificaveis: 54 (com baseline de 10d e gap disponiveis)
Warmup descartado  : 10 dias (baseline/gap incompletos — R1.4)

----------------------------------------------------------------------
 RANGE DIARIO E ATR(14) — em pontos MNQ
----------------------------------------------------------------------
Range 24h Globex : media=  540.32  mediana=  421.12  (n=64)
ATR(14) 24h      : media=  595.99  mediana=  472.18  (n=51)  <- PRESCRITO p/ stop/target
Range RTH-only   : media=  356.52  mediana=  297.12  (n=64)  [sensibilidade]
ATR(14) RTH-only : media=  492.73  mediana=  436.11  (n=51)  [sensibilidade]

----------------------------------------------------------------------
 FEATURES VVG (dias classificaveis) — diagnostico
----------------------------------------------------------------------
volume_morning    : media=     16417.0  mediana=     11804.5
volume_baseline   : media=     16920.4  mediana=     14414.5
razao morning/base: media=       1.057  mediana=       0.750  max=       7.895
gap_pct           : media=      1.257%  mediana=      0.981%  max=   7.914%

----------------------------------------------------------------------
 SWEEP PRINCIPAL (baseline 30 min — segue design.md)
 denominador = dias classificaveis
----------------------------------------------------------------------
mult_volume   threshold_gap   dias VVG+   % elegib.   faixa 15-25%
1.3           0.0015          12          22.2        SIM
1.3           0.003           10          18.5        SIM
1.3           0.0045          9           16.7        SIM
1.5           0.0015          9           16.7        SIM
1.5           0.003           8           14.8        -
1.5           0.0045          7           13.0        -
1.7           0.0015          6           11.1        -
1.7           0.003           5           9.3         -
1.7           0.0045          5           9.3         -

----------------------------------------------------------------------
 SWEEP SENSIBILIDADE (baseline 60 min — literal do enunciado)
 Mistura unidades (morning 30 min vs baseline 60 min) -> vies p/ baixo
----------------------------------------------------------------------
mult_volume   threshold_gap   dias VVG+   % elegib.   faixa 15-25%
1.3           0.0015          1           1.9         -
1.3           0.003           1           1.9         -
1.3           0.0045          1           1.9         -
1.5           0.0015          1           1.9         -
1.5           0.003           1           1.9         -
1.5           0.0045          1           1.9         -
1.7           0.0015          1           1.9         -
1.7           0.003           1           1.9         -
1.7           0.0045          1           1.9         -

----------------------------------------------------------------------
 COMBINACAO SELECIONADA
----------------------------------------------------------------------
multiplicador_volume = 1.5
threshold_gap_pct    = 0.0015
n_dias_baseline      = 10
elegibilidade        = 16.7% (9/54 dias)
-> DENTRO da faixa 15-25% (ancora 17.0%).

----------------------------------------------------------------------
 STOP / TARGET via ATR(14) mediano (PRESCRITO: ATR 24h)
----------------------------------------------------------------------
ATR(14) 24h mediano  = 472.18 pontos
stop_pontos  = round(472.18 x 1.0 / 0.25) x 0.25 = 472.25 pontos
target_pontos= round(472.18 x 2.0 / 0.25) x 0.25 = 944.25 pontos
  (em USD/contrato MNQ: stop ~= USD 944, target ~= USD 1888)

[AVISO DE RISCO] O ATR(14) diario reflete o range de ~23h do
Globex, mas o trade VVG dura ~80 min (14:30->15:50 EST). Stop de
472 pts (USD 944) consome grande fracao do TDD
Topstep (USD 2.500) num unico trade. Vide Zettel para tratamento.

[SENSIBILIDADE] ATR(14) RTH-only mediano = 436.11 pts
  stop_rth = 436.00 pts | target_rth = 872.25 pts

======================================================================
 VALORES FINAIS CONGELADOS (anti-overfit — NAO recalibrar)
======================================================================
multiplicador_volume = 1.5
threshold_gap_pct    = 0.0015
n_dias_baseline      = 10
stop_pontos          = 472.25
target_pontos        = 944.25
elegibilidade        = 16.7% (NA FAIXA 15-25%)
======================================================================
```

## Valores finais escolhidos (CONGELADOS)

| Parâmetro | Valor congelado | Origem |
|---|---|---|
| `multiplicador_volume` | **1.5** | sweep, faixa 15-25% (16.7%) |
| `threshold_gap_pct` | **0.0015** | sweep, faixa 15-25% (16.7%) |
| `n_dias_baseline` | **10** | prescrito (design.md / R1.1) |
| `stop_pontos` | **472.25** | ATR(14) 24h mediano × 1.0, arred. tick |
| `target_pontos` | **944.25** | ATR(14) 24h mediano × 2.0, arred. tick |

Elegibilidade resultante: **16.7%** (9 de 54 dias classificáveis) —
**dentro** da faixa-alvo 15-25% e muito próxima da âncora de ~17% do
abstract de Mesfin.

## Justificativa de cada escolha

### `multiplicador_volume = 1.5` e `threshold_gap_pct = 0.0015`

No sweep principal, duas combinações empataram em 16.7% (a mais próxima
de 17%): `(1.3, 0.0045)` e `(1.5, 0.0015)`. O desempate é
**determinístico** e documentado no script: prefere-se a combinação mais
próxima dos defaults antecipados no `design.md` (`mult=1.5`,
`gap=0.003`), priorizando manter o multiplicador de volume já
pré-registrado. Isso seleciona `(1.5, 0.0015)`. Ambas produzem o mesmo
número de dias VVG-positivos (9/54), então a escolha não altera a
elegibilidade — apenas mantém o multiplicador de volume alinhado ao
placeholder original do design.

### `n_dias_baseline = 10`

Valor prescrito no `design.md` (`ParametrosVvg.n_dias_baseline = 10`) e
em R1.1. Não foi varrido — é constante de janela do baseline rolling.
Com 10 dias de warmup, 10 dos 64 dias úteis válidos ficam fora do
denominador (warmup incompleto, R1.4), restando 54 dias classificáveis.

### `stop_pontos = 472.25` e `target_pontos = 944.25`

Derivados pela fórmula **prescrita** na Tarefa 1 e em R2.4:
`stop = ATR(14) mediano × 1.0`, `target = ATR(14) mediano × 2.0`,
arredondados ao tick MNQ (0.25). O ATR(14) diário mediano da janela é
472.18 pts.

> **Nota metodológica importante**: os valores foram congelados pela
> fórmula prescrita por **fidelidade ao spec** (R2.4 + design.md), mas a
> seção de risco abaixo registra forte ressalva. A troca da metodologia
> de ATR (ex.: usar janela intradiária do horizonte do trade) exigiria
> Decisão formal do Conselho e **não** foi feita aqui.

## Decisão de interpretação — discrepância tarefa vs design (baseline)

O enunciado da Tarefa 1 define `volume_baseline` sobre a **primeira hora**
`[09:30, 10:30)` (60 min), enquanto `volume_morning` é medido em 30 min
`[09:30, 10:00)`. Comparar soma de 30 min contra média de soma de 60 min
mistura unidades e enviesa a razão para baixo. Resultado literal (sweep
de sensibilidade): elegibilidade colapsa para **1.9%** em todas as 9
combinações — fora da faixa-alvo e estatisticamente inútil (1 único dia).

O `design.md` desta spec **já anteviu e resolveu** essa ambiguidade:

> "Note que o paper Mesfin pode usar 09:30-10:30 OU 09:30-10:00 — a
> implementação adota 09:30-10:00 (= mesma janela do volume_morning)
> para simplicidade."

Portanto, o sweep **principal** usa o baseline na **mesma janela de 30
min** do `volume_morning` (decisão alinhada ao design), o que recupera a
faixa pretendida (16.7%). O baseline de 60 min é mantido apenas como
**sensibilidade** no relatório, para transparência da discrepância. Os
arquivos de código da Tarefa 2+ (`vvg_classifier.py`) devem usar a
janela de 30 min para os dois — coerente com este congelamento.

## AVISO ANTI-OVERFIT (vinculante)

Estes valores são **CONGELADOS**. A calibração roda **UMA única vez**.

- Se o WF longo da Tarefa 11 (2025-07 a 2026-05) for ruim — falhar em
  Sharpe mediana ≥ 1.0, Calmar mediana ≥ 1.5, PnL total > 0, ou
  year-stability ≥ 3/4 trimestres — **NÃO recalibrar**.
- O descarte é **automático** (fallback A, R9): arquivar em
  `02_ESTRATEGIAS/mortas/`, criar `Refutacao_VVG_Late_Session_<DATA>.md`,
  atualizar `STATE-OF-RESEARCH`. Sem novo Debate.
- Não existe "tentar de novo com multiplicador/threshold/stop/target
  diferente". Qualquer alteração nestes 5 valores exige Decisão formal
  (`aprovado_walk_forward=true`), não recalibração silenciosa.

## Ressalva de risco — stop/target vs. horizonte do trade (Cerberus)

> Parecer de risco registrado para a futura validação. **Não** altera os
> valores congelados nesta tarefa; sinaliza o que monitorar.

A estratégia entra às 14:30 EST e força saída às 15:50 EST — um trade de
**~80 minutos**. Os stop/target derivados do ATR(14) **diário** (range de
~23h do Globex) ficam desproporcionais a esse horizonte:

- `stop_pontos = 472.25` ⇒ **USD 944,50/contrato** no MNQ (USD 2/pt).
- `target_pontos = 944.25` ⇒ **USD 1.888,50/contrato**.
- O Trailing Drawdown da Topstep é USD 2.500. Um único stop consome
  ~38% do TDD; dois stops seguidos praticamente esgotam a conta.
- Mesmo o ATR RTH-only (sensibilidade) dá stop de 436 pts — ainda
  grande para o horizonte.

Implicações práticas a observar na Tarefa 11:
- Com `MaxContratos=1` fixo (R4.1) e force-close às 15:50, é provável que
  a maioria dos trades feche por **encerramento forçado** antes de tocar
  stop ou target — o que torna stop/target quase decorativos no recorte
  de ~80 min. Isso por si só pode degradar o edge esperado.
- Se o WF longo falhar, esta é uma das causas-raiz mais prováveis. Pela
  regra anti-overfit, a resposta correta é **descarte automático**, e não
  reabertura do stop/target. Uma eventual variante com ATR intradiário
  seria uma **nova estratégia** sob Decisão formal, não um conserto desta.

## Limitações da janela

- O dataset cobre **~3 meses** (2025-03-17 a 2025-06-13), não os ~3,5
  prometidos pela janela nominal até 2025-06-30. São **64 dias úteis
  válidos**; após o warmup de 10 dias do baseline, restam **54 dias
  classificáveis**.
- ATR(14): há **51** observações de ATR (precisa de 14 dias válidos +
  1 para o close anterior). Suficiente para a mediana, mas é amostra
  curta — outra razão para tratar o WF longo como o juiz real.
- A janela está inteiramente em horário de verão americano (EDT,
  UTC−4); o DST é tratado via `zoneinfo.ZoneInfo("America/New_York")`,
  sem offset hardcoded. A transição EDT↔EST só apareceria em janelas que
  cruzam março/novembro — não é o caso aqui, mas o código já trata.

## Links

- [[Decisao_2026-05-29-03]] — emendas (year-stability, T ≥ 2.0, MaxContratos=1 fixo)
- [[Etapa_Zero_NotebookLM_Gemini_2026-05-29]] — filtro crítico S1-S6 / R1-R8
- `scripts/calibrar_vvg_2026-05-29.py` — script desta calibração
- `.kiro/specs/caos-vvg-late-session-reversal-mnq/design.md` — seção "Calibração obrigatória"
- `dados/MNQ/_concat_minute_last/01_MNQ_06-25.csv` — dataset de calibração
