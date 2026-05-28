---
area: Walk_Forwards
data_criacao: '2026-05-27T18:00:00Z'
identificador: refutacao-value-area-filter-2026-05-27
estrategia: EstrategiaValueAreaFilter
status: refutada
tags:
- walk-forward
- refutacao
- value-area
- market-profile
- folclore-profissional
- caos-engine-manifesto
titulo: 'Refutação Empírica do Value Area Filter sobre Estratégia Aprovada'
---

# Refutação do Value Area Filter

> Inspirado pelo manifesto "CAOS Engine" recebido via NotebookLM/Gemini Pro
> em 27/05/2026. Camada 1 do manifesto propunha classificação TREND/RANGE
> via abertura fora/dentro da Value Area do dia anterior (80% rule de
> J. Peter Steidlmayer / James Dalton).

## Hipótese testada

Estratégias de breakout (como `EstrategiaORBCrabelSFCB`) deveriam ter
performance superior em **dias TREND** (abertura fora da Value Area) vs.
**dias RANGE** (abertura dentro da Value Area). Adicionar overlay que
filtra entradas apenas em dias TREND deveria melhorar Sharpe e PnL.

## Implementação

`EstrategiaValueAreaFilter` (arquivo `caos/walk_forward/estrategias/value_area_filter.py`):

- Calcula Value Area por dia útil (POC + expansão simétrica até cobrir
  70% do volume diário, constante de Market Profile / CME Group).
- Classifica regime do dia atual com base na abertura vs. VA do dia anterior:
  - Open > VA_high OU < VA_low → TREND
  - VA_low ≤ Open ≤ VA_high → RANGE
- Modo `trend` libera entradas em dias TREND, modo `range` libera em RANGE.
- 17 testes unitários cobrindo cálculo de VA, classificação e filtragem.

## Resultado WF (24 janelas, 14 meses, 412k barras MNQ)

| Variante | Sharpe mediana | PnL total (USD) | Trades |
|---|---|---|---|
| Baseline (sem filtro) | **+9.07** | **+1311** | **28** |
| Modo TREND | -11.22 | +469 | 15 |
| Modo RANGE | +6.05 | **-1257** | 17 |

**Ambos os modos degradam.** O modo TREND reduz PnL em 64% e inverte
Sharpe; o modo RANGE leva a PnL negativo absoluto.

## Por que não funciona (hipóteses)

1. **Filtro NR7 já faz papel de regime**: Crabel só seleciona dias após
   compressão, que tendem a ser TREND naturalmente. Adicionar VA filter
   é filtro duplo redundante e remove trades viáveis.
2. **VA overnight não é preditiva em futuros 23h**: diferente do ES/NQ
   pit clássico, o Globex 23h dilui o conceito de "abertura RTH". Open
   fora da VA pode ser ruído de overnight sem direção persistente.
3. **MNQ Nasdaq é mais técnico que ES/CL/GC**: instrumento jovem,
   dominado por algos. Heurísticas de Market Profile dos anos 80
   podem ter degradado neste ativo específico.

## Contexto: avaliação do manifesto CAOS Engine

O manifesto Gemini propunha 3 camadas:

1. **Context Brain** (Value Area + FOMC + 0DTE Gamma) — REFUTADO em parte
   (Value Area não funciona; FOMC e 0DTE não testados aqui)
2. **Quantum Fimathe** (FVG/OB com Displacement Factor) — NÃO IMPLEMENTADO,
   stops de 50-100 pts inviáveis em MNQ 1 contrato
3. **Order Flow Imbalance** — JÁ REFUTADO (commit `e9cd16a`, Sharpe -39.99)

O manifesto serviu como inspiração estratégica. O Gemini concordou em 5/5
críticas técnicas após Q&A:
- OFI agregado sem L2 não tem edge
- Tick Replay + VolumetricBars inviabiliza WF
- `delta < -500` é ruído normal RTH
- Stops largos via FVG = ruína
- Value Area filter degradou empiricamente

## Diálogo Kiro ↔ Gemini

A defesa do Gemini **revelou meu erro de procedência**: acusei de
"alucinação" arquivos que existiam de fato em locais que eu não busquei
(`reference_hydra/04_CODIGO/ninjascript/reference/Rodrigo_2.cs` tem
`DisplacementFactor = 1.8`; arquivo `OdinMaxMnqSniffer` pode ser local não-versionado).
Lição operacional: na próxima acusação de alucinação, checar
**todos os caminhos plausíveis** (incluindo zonas read-only e
arquivos soltos do usuário).

## Veredito

**Família Market Profile / Value Area: REJEITADA empiricamente como
filtro sobre `EstrategiaORBCrabelSFCB` no MNQ minute.**

Plugin `EstrategiaValueAreaFilter` fica disponível no repo para uso
futuro (ex: meta-estratégia que combine sinais com regimes
complementares), mas não entra na composição aprovada pela
Decisão `[[Decisao_2026-05-25-02]]`.

## Próxima fronteira de exploração

Em vez de Value Area folclórico, vale investigar:

- **arXiv 2605.11423** — "Volatility-Volume-Gap Classifier para MNQ
  Intraday" (947 dias 2021-2025, paper acadêmico). Versão academic
  rigorosa do que tentamos com VA. Pode produzir filtro mais robusto.
- **arXiv 2605.04004** — "Structural Limits of OHLCV-Based Intraday
  Signals in MNQ Futures". Confirma estrutura: edge OHLCV bruto =
  0.5-1.5 pts/trade, alinhado com nossa regra de ouro empírica
  (≥ 4 pts).
- **arXiv 2508.06788** — "Endogeneity, Intraday Variations, and
  Macroeconomic News" (LOB filtering). Confirma que OFI agregado não
  tem edge — só "ordens parentais" filtradas têm sinal. Inviável sem
  Level 2 DOM.

## Links

- `[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]` — Decisão original
- `[[Bug_NR7_Aceita_Domingos_2026-05-26]]` — bug fix
- `[[WF_Validacao_Longa_2026-05-27]]` — validação longa que mantém aprovação
- `05_BACKTEST/walk_forward/relatorios/wf-value-area-overlay-2026-05-27/` — relatório bruto
- `scripts/wf_value_area_overlay_2026-05-27.py` — script da validação
- `caos/walk_forward/estrategias/value_area_filter.py` — plugin (refutado mas mantido)
- `tests/unit/test_value_area_filter.py` — 17 testes verdes
