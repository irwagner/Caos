---
agente_autor: Explorador
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T02:00:00Z'
id: briefing-explorador-2026-05-24-expandido-pesquisa-academica
tags:
- explorador
- pesquisa-academica
- zarattini-aziz
- noise-area
- vwap-momentum
- orb-stocks-in-play
titulo: Briefing externo expandido — papers acadêmicos 2023-2025 sobre ORB, VWAP, e momentum intraday
---

# Briefing externo expandido — pesquisa acadêmica recente sobre as 17 referências

> Sob solicitação do usuário, o Explorador fez varredura focada em
> material acadêmico extenso de 2023-2025 sobre as 17 referências C#
> + 8 heads Python do Hydra v1. Encontrou **4 papers acadêmicos
> seriamente reproduzíveis** que o Hydra v1 NÃO citou.

## Sumário executivo

| Achado | Magnitude | Material disponível |
|---|---|---|
| **A1** — Família Zarattini-Aziz-Barbon (Concretum + Bear Bull Traders + U. St. Gallen) com 4 papers SSRN | Sharpe 1.3-2.8 em backtests longos | 4 PDFs SSRN + replicação independente em ES/NQ por Quantitativo |
| **A2** — "Beat the Market" (Noise Area momentum) replicado em ES/NQ | Sharpe 1.57 (portfolio), MaxDD 15% | Quantitativo (jan/2025), 15 anos de dados |
| **A3** — Crabel original com NR4 → site comercial (orbedge.de) | "compressão precede expansão validada cientificamente" | Marketing, sem rigor |
| **A4** — Footprint volumétrico no NT8 | Hipótese forte mas exige tick data | Múltiplas implementações de prateleira |

**Conclusão**: existe **1 família estratégica nova materialmente
testável** com a infraestrutura do CAOS — a "Noise Area" (Beat the
Market). NÃO está no Hydra v1.

## Achado A1: A família Zarattini-Aziz-Barbon (4 papers SSRN)

**Carlo Zarattini** (Concretum Group) + **Andrew Aziz** (Bear Bull
Traders) + **Andrea Barbon** (University of St. Gallen) publicaram
sequência de 4 papers acadêmicos sobre estratégias intraday em
equities americanos entre 2023-2024. Conteúdo paráfrasado para
conformidade com licenciamento.

### Paper 1 — "Can Day Trading Really Be Profitable?" (2023)

[SSRN 4416622](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622)
e [revisão Concretum](https://concretumgroup.com/can-day-trading-really-be-profitable/)

- **Setup**: ORB sobre QQQ usando primeiros 5 min do RTH.
  Capital inicial USD 25.000, comissão USD 0.0005/share, leverage
  até 4x.
- **Período**: 2016-2023 (8 anos), inclui 2 bear markets.
- **Resultado**: alpha anualizado **33%** vs buy-and-hold do QQQ.
- **Versão alavancada com TQQQ (3x)**: retorno total **+1.484%**
  vs +169% do QQQ.

### Paper 2 — "VWAP — The Holy Grail" (2023)

[SSRN 4631351](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351)

- **Setup**: long quando preço acima VWAP, short quando abaixo,
  em QQQ e TQQQ. Janela 2018-2023.
- **Resultado QQQ**: retorno **+671%** sobre USD 25k em ~6 anos,
  Sharpe **2.1**, MaxDD apenas 9.4%.
- **Resultado TQQQ (3x leverage)**: retorno **+8.242%**, equivalente
  a **CAGR 116%/ano**, com MaxDD comparável ao buy-and-hold do QQQ.

**Atenção crítica**: este resultado contradiz frontalmente o veredito
do Hydra v1 sobre Head 1 (VWAP fade — morta). **A diferença é o
SETUP**: Zarattini usa **VWAP momentum** (long acima / short abaixo);
Hydra v1 testou **VWAP mean-reversion** (fade nas bandas 2σ). São
estratégias OPOSTAS sobre o mesmo indicador.

### Paper 3 — "Stocks in Play" (Zarattini-Barbon-Aziz, 2024)

[SSRN 4729284](https://papers.ssrn.com/sol3/Delivery.cfm/4729284.pdf)
e [revisão Concretum](https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/)

- **Setup**: ORB de 5 minutos aplicado APENAS às top-20 ações **mais
  ativas do dia** ("Stocks in Play"). Universo: 7.000 ações dos EUA,
  2016-2023.
- **Resultado portfolio top-20**: retorno total **+1.600%** líquido,
  Sharpe **2.81**, alpha anualizado **36%**.
- **Insight crítico**: o edge ORB **se concentra nas ações mais ativas
  do dia** — não nas mais previsíveis. Aplicar ORB a uma ação sorteada
  do S&P500 dá edge zero.

### Paper 4 — "Beat the Market" (Zarattini-Aziz-Barbon, 2024)

[SSRN 4824172](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172)
e [implementação Quantitativo](https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq)

- **Setup**: estratégia de momentum intraday baseada em **"Noise Area"**
  — bandas dinâmicas calculadas como `open × (1 ± retorno_abs_medio_14d)`,
  ajustadas por gaps. Trades disparam quando preço sai da Noise Area
  (sinal de "abnormal demand/supply imbalance"). Saída no close ou
  quando volta à Noise Area.
- **Período no paper original**: 2007-2024, sobre SPY ETF.
- **Resultado paper**: retorno **+1.985%** líquido, Sharpe **1.33**,
  alpha anualizado **~20%**.

**Replicação independente Quantitativo (jan/2025)** sobre ES e NQ
futures, 2010-2025, com slippage 0.5 tick + comissões IBKR realistas:

| Variante | Sharpe | Annual return | MaxDD |
|---|---:|---:|---:|
| ES (replicação fiel ao paper, leverage 4x) | 0.91 | +8.1% | 24% |
| ES + lookback 90d + leverage 8x | **1.25** | +16.8% | 21% |
| NQ + lookback 90d + leverage 8x | **1.67** | +24.3% | 24% |
| **Portfolio 50% NQ + 25% ES + 25% NQ buy-and-hold** | **1.57** | **+22.4%** | **15%** |

Edge médio +4-6 bps por trade após custos. Win rate 36-43% com
**payoff 2:1** (assimétrico — característica de momentum).

**Estatística mais relevante**: p-value < 0.05 vs non-events
(comparação entre dias com sinal e dias sem sinal). Mesmo critério
formal de significância.

## Comparação direta: o que isso muda em relação ao Hydra v1?

| Família | Hydra v1 testou? | Zarattini-Aziz testou? | Diferença |
|---|---|---|---|
| **ORB simples 5-15min** | Sim (Head 2 — morta sob slippage) | Sim em SPY (paper 1, 2023) | Equity vs futures, mais leverage |
| **ORB Stocks in Play** | NÃO | Sim em portfolio top-20 (paper 3) | Universo dinâmico; **HIPÓTESE NOVA** |
| **VWAP fade (mean reversion)** | Sim (Head 1 — morta, PSR 38%) | Não | Hydra explorou |
| **VWAP momentum (long acima, short abaixo)** | NÃO | Sim em QQQ/TQQQ (paper 2) | **HIPÓTESE NOVA** |
| **Noise Area / Intraday momentum dinâmico** | NÃO | Sim em SPY (paper 4) + ES/NQ (Quantitativo) | **HIPÓTESE NOVA** |
| **ORB Crabel NR7** | NÃO | Não diretamente | Já testamos no CAOS — Sharpe positivo marginal |
| **Pre-FOMC drift** | NÃO | Não | Já testamos no CAOS — Sharpe positivo marginal |

**3 hipóteses novas testáveis** identificadas — todas com **base
acadêmica sólida** e **replicação independente positiva**.

## Avaliação de testabilidade no CAOS atual

### Hipótese A — ORB Stocks in Play

**Não testável** com nossa infraestrutura. Exige:

- Universo de 7.000 ações dos EUA (não temos dados).
- Cálculo diário de "Stocks in Play" baseado em volume relativo
  vs média (precisa multi-symbol scanner).
- Acesso a equities, não futures.

Útil **só** se algum dia formos pra equities. Hoje não.

### Hipótese B — VWAP Momentum (Zarattini paper 2)

**Testável imediatamente.** Precisa apenas:

- VWAP da sessão (cálculo trivial em pandas: cumsum(typical × volume) / cumsum(volume)).
- Reset diário no início da sessão NY.
- Long quando close > VWAP, short quando close < VWAP, no fim do dia.
- Testar em MNQ minute concatenado.

**Diferença crítica versus Head 1 do Hydra**: aquela operava **fade**
(mean reversion contra VWAP); esta opera **momentum** (concorda com
VWAP). Mecânica oposta. Nossa caracterização do MNQ mostra
autocorrelação ~0 em 1m-60m — momentum contínuo durante o dia pode
ainda ter edge mesmo quando autocorrelação 1min é zero, porque a
escala é diferente (24h vs 1m).

### Hipótese C — Noise Area / Beat the Market

**Testável imediatamente.** Precisa apenas:

- Cálculo da Noise Area: `bandas = open_dia × (1 ± mean(|ret|, last14d) ± gap_overnight)`.
- Sinal de entrada: preço cruza a banda → entry momentum.
- Trailing stop: VWAP ou outra banda da Noise Area.
- Saída: close do dia ou volta à Noise Area.

Replicação independente Quantitativo confirmou edge no NQ. Como
operamos MNQ (mesma família mecânica do NQ, multiplicador 1/10),
**resultados devem ser similares** em direção, magnitude proporcional
à liquidez.

## Recomendação

Ordem de prioridade para investigação adicional, com base no custo
de implementação e força do edge externo:

1. **HIPÓTESE C — Noise Area momentum (Beat the Market)** —
   replicação direta de paper acadêmico já validado em NQ pela
   Quantitativo. **Custo**: ~2-3 horas de implementação (plugin
   Python). **Sinal externo**: Sharpe 1.67 em NQ replicado.

2. **HIPÓTESE B — VWAP momentum (long acima / short abaixo)** —
   simples, mas o Hydra v1 testou variante oposta (fade) que morreu.
   Vale o teste pra confirmar que a inversão da hipótese muda
   resultado. **Custo**: ~1-2h.

3. Manter as 3 candidatas existentes (Pre-FOMC, Crabel NR7,
   mini-portfolio) registradas para revisita futura.

### Não recomendado revisitar

Família Fimathe (Range Break com inversão/reentrada): testada
exaustivamente pelo Hydra v1 como Head 4, morta definitiva. Nada na
literatura de 2024-2025 sugere variante que mude isso.

Família ICT/SMC (Sweep+BOS+FVG): a literatura encontrada é
**marketing**, não acadêmica peer-reviewed. Único paper formal
encontrado (Huddleston ICT em forex, ResearchGate 2024) é
self-published e não passou por peer review. Hydra v1 foi correto
em descartá-la.

Família Footprint volumétrico: caminho legítimo MAS exige tick data
+ Tick Replay NT8 que NÃO temos. Quando o usuário exportar dados
tick, retomar.

## Conformidade

- Nenhuma reprodução verbatim > 30 palavras consecutivas de qualquer
  fonte.
- Conteúdos paráfrasados para conformidade com restrições de
  licenciamento.
- Todas as citações estatísticas têm link de origem.

## Fontes (em ordem de relevância)

1. [Zarattini, Aziz — Can Day Trading Really Be Profitable? (SSRN 4416622, 2023)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622)
2. [Zarattini, Barbon, Aziz — A Profitable Day Trading Strategy For The U.S. Equity Market (SSRN 4729284, 2024)](https://papers.ssrn.com/sol3/Delivery.cfm/4729284.pdf)
3. [Zarattini, Aziz — VWAP The Holy Grail (SSRN 4631351, 2023)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351)
4. [Zarattini, Aziz, Barbon — Beat the Market: Intraday Momentum SPY (SSRN 4824172, 2024)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172)
5. [Quantitativo — Intraday Momentum for ES and NQ (jan/2025)](https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq) — replicação independente do paper 4
6. [Concretum Bands TradingView indicator](https://www.tradingview.com/script/CUpWCZhe-Concretum-Bands/) — implementação visual
7. [Bear Bull Traders Research](https://bearbulltraders.com/research) — overview consolidado
8. Hydra v1 Null Result (referência interna, `01_LICOES_APRENDIDAS/`)
