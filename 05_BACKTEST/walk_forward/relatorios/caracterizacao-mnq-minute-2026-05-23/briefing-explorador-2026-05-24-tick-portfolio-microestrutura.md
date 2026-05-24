---
agente_autor: Explorador
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T03:00:00Z'
id: briefing-explorador-2026-05-24-tick-portfolio-microestrutura
tags:
- explorador
- microestrutura
- order-flow-imbalance
- portfolio-construction
- turn-of-month
- calendar-effects
titulo: Briefing externo segunda rodada — microestrutura, portfolio, e calendar effects
---

# Briefing externo — segunda rodada de varredura

> O usuário está exportando dados tick e pediu mais varredura externa.
> Este briefing complementa o anterior (commit `259e1cd`, 4 papers
> Zarattini-Aziz-Barbon) cobrindo 3 ângulos não tocados: (1) tick-level
> / microestrutura, (2) construção de portfolio multi-estratégia, (3)
> calendar effects além de FOMC.
>
> Conformidade: nenhuma reprodução verbatim > 30 palavras consecutivas.
> Conteúdo paráfrasado para conformidade com licenciamento.

## Sumário

Total de **4 hipóteses adicionais testáveis** identificadas:

| # | Hipótese | Onde abre | Custo impl | Sinal externo |
|---|---|---|---:|---|
| **D** | **Order Flow Imbalance** (OFI / Kyle's lambda) — sinal preditivo lead 20 ticks antes do preço mover | Tick data | Médio (precisa Tick Replay) | Acadêmico forte (Kyle 1985, Glosten-Milgrom 1985); aplicação retail validada em Math&Markets 2026 |
| **E** | **Spread regime como filtro de scaling** — Sharpe 4× maior em narrow-spread vs wide-spread (V6 Math&Markets) | OHLCV ou tick | Baixo | Academicamente robusto (Amihud-Mendelson 1986, Pastor-Stambaugh 2003) |
| **F** | **Turn-of-the-Month effect** em S&P 500 futures | OHLCV diário | Mínimo | Carchano-Tornero 2011: único calendar effect estatisticamente persistente entre 188 testados |
| **G** | **Mini-portfolio multi-estratégia** com regra √N (HMAQUANT) | Composição | Mínimo | Teórico forte (5 strats Sharpe 1 → portfolio Sharpe 2.24) |

Combinadas com as 3 anteriores (Pre-FOMC, Crabel NR7, Noise Area
momentum) totalizam **7 candidatas** registradas para investigação
quando dados crescerem.

## Achado D: Order Flow Imbalance (OFI) e microestrutura — abre com tick data

### Base acadêmica

Linhagem clássica:
- [Kyle 1985](https://en.wikipedia.org/wiki/Kyle%27s_lambda) — "lambda" = sensibilidade do preço ao fluxo líquido
- [Glosten-Milgrom 1985](https://www.sciencedirect.com/science/article/abs/pii/0304405X85900445) — formação de spread por adverse selection
- [Easley-O'Hara 1992](https://www.jstor.org/stable/2329114) — toxicidade de fluxo
- [Easley-Lopez de Prado-O'Hara 2012](https://www.sciencedirect.com/science/article/abs/pii/S0378426611002263) — VPIN (Flash Crash 2010 warning)
- [Hawkes processes para OFI 2024](https://arxiv.org/abs/2408.03594) — modelo formal para forecasting

### Versão prática para retail

[Math & Markets — "The Plumbing Beneath the Price" (mar/2026)](https://kniyer.substack.com/p/the-plumbing-beneath-the-price-order)

Síntese paráfrasada:

- **OFI lidera o preço em ~20 ticks**: na simulação de microestrutura,
  a pressão vendedora aparece em order flow imbalance ANTES do preço
  cair — diferença visível.
- **Lambda (price impact) varia 10-20× entre regimes calmos e
  estressados**: em SPY, ~0.5-2 bps em mercado calmo, 5-15 bps em
  estresse. Isso significa que **backtests com slippage fixo
  subestimam custos exatamente quando você mais precisa trade-rar**.
- **VPIN é controverso**: Andersen-Bondarenko (2014, Northwestern,
  [SSRN 2292602](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2292602))
  argumentam que VPIN só prevê volatilidade por erros sistemáticos de
  classificação. Não usar como sinal direto.
- **OFI cru** (= bid_volume - ask_volume normalizado por total)
  é mais robusto. Sinal direcional ~30-100ms à frente do preço.

### Implicação prática para o CAOS

Quando os dados tick chegarem, **2 análises iniciais valem ouro**:

1. **OFI vs price drift**: medir correlação entre OFI(t) e
   price_change(t+k) para k=1..30 ticks. Se ρ > 0.05 com N grande,
   sinal real.
2. **Spread regime como filtro**: classificar dias em narrow/normal/
   wide-spread (uso da mediana do spread bid-ask). Aplicar
   estratégias atuais (Crabel NR7, Pre-FOMC) condicionalmente —
   esperar Sharpe 1.5-4× maior em narrow-spread se a teoria
   transferir.

### Caveat estrutural

A base teórica é forte (40+ anos), mas **a maioria do edge OFI é
arbitrada por HFT em microsegundos**. Retail típico (latência
50-300ms) capta apenas o "resíduo" — sinal residual em escalas que
HFT ignora. Vale testar mas com expectativas calibradas.

## Achado E: Spread regime como filtro de scaling

[Math & Markets V6 study](https://kniyer.substack.com/p/the-plumbing-beneath-the-price-order)

Achado replicado em pelo menos 5 estudos acadêmicos
(Amihud-Mendelson 1986, Pastor-Stambaugh 2003, Acharya-Pedersen 2005):
**spreads largos predizem retornos negativos**. Mecanismo:
spread amplo → market makers incertos → fluxo informado ou
inventory risk alto → expectativa negativa.

Estudo de caso V6 (estratégia diária):

- Sharpe **1.33** em períodos de narrow spread.
- Sharpe **0.30** em períodos de wide spread.
- **4× diferença** com a MESMA estratégia, mesmos parâmetros.

### Aplicação imediata para CAOS

Mesmo SEM tick data, isso se aplica. O spread bid-ask diário **pode
ser estimado** a partir das séries `bid.csv`/`ask.csv` que JÁ TEMOS
em `dados/MNQ/<contrato>/<minute|day>/`. Estimativa:

```
spread_diario = mean(close_ask - close_bid) por dia útil
spread_regime = quartil do spread vs últimos 60 dias
```

Para qualquer estratégia futura, scaling proporcional ao quartil do
spread:

- Q1 (narrow): peso 1.5×
- Q2-Q3: peso 1.0×
- Q4 (wide): peso 0.5× ou 0×

**Não é estratégia em si, é filtro de scaling**. Aplicável a todas as
candidatas existentes (Pre-FOMC, Crabel NR7, Noise Area).

## Achado F: Turn-of-the-Month effect em S&P 500 futures

[Carchano & Pardo Tornero 2011 — SSRN 1958587](https://papers.ssrn.com/sol3/Delivery.cfm?abstractid=1958587)

Testaram **188 calendar effects** em ES futures (1982-2010):

- TOTM: long no fechamento do **5º último dia útil do mês**, exit no
  fechamento do **3º dia útil do mês seguinte** (~7 dias úteis).
- Resultado: **27.5% lucro cumulativo líquido** sobre Dez/1991-Abr/2008
  (~16 anos), considerando 0.05% round-trip cost.
- **ÚNICO calendar effect** estatisticamente E economicamente
  significativo E persistente entre os 188 testados via percentile-t
  bootstrap + Monte Carlo.

### Replicação independente

[Quantified Strategies (out/2024)](https://www.quantifiedstrategies.com/turn-of-the-month-trading-strategy/)
e [Maberly-Waggoner 2000 — SSRN 244085](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=244085)
confirmam.

### Por que é compatível com nossa caracterização

- **Frequência**: 12 trades/ano (~1 por mês). Pequeno **mas similar
  ao Pre-FOMC drift** que já implementamos (~8 trades/ano).
- **Holding**: 7 dias úteis = ~1 semana. Holding longo, não 1m-60m
  onde o MNQ é ruído branco.
- **Mecânica anti-overfit**: zero parâmetros otimizáveis. "5º último"
  e "3º próximo" vêm do paper original.
- **Ortogonal ao Pre-FOMC**: meetings FOMC raramente caem nos dias
  da TOTM. Outro candidato a mini-portfolio.

### Custo de implementação no CAOS

Trivial. Mesma arquitetura que `EstrategiaPreFomcDrift`. **~1h** para
implementar `EstrategiaTurnOfMonth` reusando padrões.

## Achado G: regra √N para portfolio multi-estratégia

[HMAQUANT — Portfolio Construction (mar/2026)](https://hmaquant.substack.com/p/portfolio-construction-when-1-1-14)

Resultado matemático conhecido mas raramente articulado claramente
para quem trade retail:

| N estratégias uncorrelated com Sharpe individual 1.0 | Sharpe portfolio |
|---:|---:|
| 1 | 1.00 |
| 2 | 1.41 |
| 3 | 1.73 |
| 5 | 2.24 |
| 10 | 3.16 |

Validação: nosso achado Crabel NR7 + Pre-FOMC com **overlap=0** (commit
`d0a1788`) é instância empírica disso. As datas DISJUNTAS garantem
correlação ≈ 0 — o √N se aplica.

### Estimativa concreta para o CAOS

Se conseguirmos:
- 3 candidatas com Sharpe individual 0.5-0.8 cada
- Correlação < 0.2 entre elas

Sharpe portfolio esperado ≈ 0.65 × √3 ≈ **1.13** (estimativa
conservadora). Match com o que Quantitativo conseguiu em ES+NQ
(portfolio Sharpe 1.57).

### Famílias mais ortogonais entre si (candidatas a pertencer ao mesmo portfolio)

| Par | Correlação esperada | Razão |
|---|---|---|
| Pre-FOMC × Crabel NR7 | 0 | Datas mecanicamente disjuntas (já confirmado) |
| Pre-FOMC × Turn-of-Month | < 0.1 | FOMC raramente coincide com 5º último útil |
| Noise Area momentum × TOTM | < 0.3 | Escalas diferentes (intraday vs holding 7d) |
| Noise Area momentum × OFI/microestrutura | < 0.3 | Escalas diferentes (5min vs ticks) |

**Mini-portfolio de 4 candidatas teoricamente sustentável** se cada
uma passar t-stat individual mínimo.

## Calendar effects além de TOTM (advertência)

[CXO Advisory testou 188 calendar effects em ES futures](https://www.cxoadvisory.com/calendar-effects/stock-index-futures-calendar-effects/):
**apenas 1** (TOTM) sobreviveu rigor estatístico. Outros candidatos
populares NÃO funcionam isoladamente:

- **Weekend effect** (returns negativos na segunda) — desapareceu
  pós-2000 segundo TradingView 2025.
- **Day-of-week effect** — não persistente.
- **Halloween / Sell in May** — funciona em equities buy-and-hold,
  não em futures intraday.
- **Pre-holiday effect** — economicamente marginal pós-2010.

**Não vale investigar nada além de TOTM** sem motivação específica.

## Aviso sobre VPIN, ICT, e order flow vendor-driven

3 famílias que aparecem **muito** em vendor marketing mas têm base
acadêmica fraca ou refutada:

1. **VPIN como sinal direto**: refutado por Andersen-Bondarenko 2014.
   OFI bruto é mais robusto.
2. **ICT/SMC (Sweep/BOS/FVG)**: nenhum paper peer-reviewed em equities
   americanos com walk-forward público. Único estudo encontrado é
   self-published em forex.
3. **CVD divergence + absorption + iceberg**: implementações em
   TradingView abundam, **zero** estudo formal de edge em futures
   americanos. Caveat: pode existir mas escondido em hedge funds.

## Recomendação final atualizada

Lista priorizada agora com 7 candidatas:

| # | Candidata | Status | Custo | Sinal externo |
|---|---|---|---|---|
| 1 | **Noise Area momentum** (Beat the Market) | Implementar AGORA | 2-3h | Sharpe 1.67 NQ replicado |
| 2 | **Turn-of-the-Month** | Implementar (trivial) | 1h | 27.5% cumulativo Carchano 2011 |
| 3 | **VWAP momentum** (não fade) | Implementar | 1-2h | Sharpe 2.1 QQQ Zarattini |
| 4 | **OFI sobre tick data** | Aguardar exportação tick | Médio | Acadêmico forte |
| 5 | Pre-FOMC drift | Já implementado | — | Lucca-Moench replicado |
| 6 | Crabel NR7 ORB | Já implementado | — | Crabel 1990, único positivo no MNQ |
| 7 | **Spread regime filter** (não-estratégia, scaling) | Implementar como overlay | 1h | Amihud-Mendelson |

### Quando dados tick chegarem

5 análises automáticas a fazer em sequência:
1. Caracterização tick (ticks/segundo, distribuição de tick size).
2. Estimativa de spread médio diário do MNQ (vs MGC se tiver).
3. OFI(1m) cumulado vs price change — coeficiente de correlação.
4. Refinamento do modelo `CustosOperacionais` com slippage real
   medido (substituir o 7.5% do Hydra v1 por valor MNQ).
5. Caracterização de "wide spread regimes" para filtro de scaling.

## Conformidade

- Nenhuma reprodução verbatim > 30 palavras consecutivas.
- Conteúdos paráfrasados.
- Citações com link de origem.

## Fontes (relevância decrescente)

- [Math & Markets — Microstructure series Part 1 (mar/2026)](https://kniyer.substack.com/p/the-plumbing-beneath-the-price-order)
- [Carchano-Tornero — Calendar Anomalies in Stock Index Futures (SSRN 1958587)](https://papers.ssrn.com/sol3/Delivery.cfm?abstractid=1958587)
- [Quantitativo — Intraday Momentum for ES and NQ (jan/2025)](https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq)
- [HMAQUANT — Portfolio Construction When 1+1=1.4 (mar/2026)](https://hmaquant.substack.com/p/portfolio-construction-when-1-1-14)
- [Andersen-Bondarenko — Assessing VPIN (SSRN 2292602)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2292602)
- [Forecasting OFI with Hawkes processes (arXiv 2408.03594)](https://arxiv.org/abs/2408.03594)
- [Maberly-Waggoner — TOTM in S&P 500 futures (SSRN 244085)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=244085)
- [CXO Advisory — Stock Index Futures Calendar Effects](https://www.cxoadvisory.com/calendar-effects/stock-index-futures-calendar-effects/)
- [Concretum — You Can Trade (Almost) Like Mulvaney (mar/2026)](https://concretumgroup.substack.com/p/you-can-trade-almost-like-mulvaney)
- [arXiv 2507.15876 — CTA Replication trend factors](https://arxiv.org/html/2507.15876v1)
