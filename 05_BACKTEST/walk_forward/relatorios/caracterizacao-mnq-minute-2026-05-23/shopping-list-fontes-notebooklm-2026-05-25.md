# Shopping list de fontes para o NotebookLM

**Data:** 2026-05-25
**Para:** alimentar o NotebookLM com material **verificável e
peer-reviewed**, evitando alucinações como "Fractional EMA Kalman".

> **Filosofia da curadoria:** prioridade total para papers acadêmicos
> peer-reviewed, autores com track record, repositórios open-source
> com testes. Sem cursos pagos sem evidência empírica externa.
> Cético com "gurus" sem registro.

---

## Tier 1 — Papers diretamente relevantes (jogar TODOS no NotebookLM)

### Sobre nossa estratégia aprovada

| Paper | URL | Por que vale |
|---|---|---|
| **"Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures"** (arXiv 2605.04004, mar/2026) | https://arxiv.org/abs/2605.04004 | **Literalmente sobre MNQ + intraday + execution constraints**. Provavelmente bate com nossa regra de ouro empírica. **PRIORIDADE 1.** |
| **"Beat the Market" (Zarattini-Aziz-Barbon)** (SSRN 4824172, 2024) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172 | Paper original que tentamos replicar e que refutamos em MNQ. Vale revisitar com olhar crítico. |
| **"Improvements to Intraday Momentum Strategies" (Maróy 2025)** (SSRN 5095349) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095349 | Otimização de parâmetros + diferentes exit strategies sobre Beat the Market. Pode dar variantes não tentadas. |

### Sobre Pre-FOMC (refuta nosso resultado)

| Paper | URL | Por que vale |
|---|---|---|
| **"The Disappearing Pre-FOMC Announcement Drift"** (SSRN 3134546, Kurov-Wolfe-Gilbert) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3134546 | **Documenta empiricamente** que o Pre-FOMC drift desapareceu pós-2015. **Explica nosso resultado** do WF 2026-05-25-04. |
| **"The Pre-FOMC Drift is Alive"** (QuantSeeker, 2025) | https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift | Contraponto do anterior. Mostra condições onde ainda funciona. |
| **"Magnitudes, Channels and Shocks" (Knox-Vissing-Jorgensen 2025)** (SSRN 5233918) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5233918 | Survey atualizado de FOMC effects, incluindo pre-drift. |
| **"Monetary Momentum"** (Neuhierl-Weber, SSRN 3030126) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3030126 | Drift de 25 dias pré-FOMC para surpresas expansionárias. Variante a testar. |

### Sobre Turn-of-Month (refuta nosso resultado)

| Paper | URL | Por que vale |
|---|---|---|
| **"The disappearing turn-of-month effect"** (ResearchGate, 2024) | https://www.researchgate.net/publication/385968274 | **Documenta** que o TOM está desaparecendo. **Explica** porque nosso WF TOM teve variância tão alta. |
| **"Do Calendar Anomalies Still Work?"** (Harbourfront Quant Substack 2024) | https://harbourfrontquant.substack.com/p/do-calendar-anomalies-still-work | Replicação prática + códigos. TOM, TOQ, TOY no S&P 500 atual. |
| **Carchano-Tornero original** (SSRN 1958587) | https://papers.ssrn.com/sol3/Delivery.cfm?abstractid=1958587 | Já temos. Para o NotebookLM ter contexto histórico. |

### Sobre Order Flow Imbalance (refuta nosso achado)

| Paper | URL | Por que vale |
|---|---|---|
| **"Endogeneity, Intraday Variations, and Macroeconomic News Announcements"** (arXiv 2508.06788) | http://arxiv.org/abs/2508.06788v1 | **OFI no S&P E-mini futures** com SVAR. Pode explicar por que nosso OFI direto deu Sharpe -39. |
| **"Cross-Impact of Order Flow Imbalance"** (arXiv 2112.13213) | https://arxiv.org/abs/2112.13213 | Multi-asset OFI. Sugere que OFI sozinho é fraco; precisa de book depth (que NT8 export não dá). |
| **"Order-Flow Filtration and Directional Association"** (arXiv 2507.22712) | https://www.arxiv.org/abs/2507.22712 | Filtragem do OFI por parent orders (não temos esse dado, mas explica limites do nosso). |
| **"Hedging Demand and Market Intraday Momentum"** (Baltussen et al, SSRN 3760365) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365 | Last 30 minutes prediz pelo resto do dia. **NOVA hipótese a testar** em MNQ. |

### Sobre 0DTE / gamma effects (contexto novo de 2024-2025)

| Paper | URL | Por que vale |
|---|---|---|
| **"0DTEs: Trading, Gamma Risk and Volatility Propagation"** (SSRN 4692190, 2024) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4692190 | Mostra que **MM gamma muda regime intraday**. Pode explicar por que o regime de mercado mudou recentemente vs literatura pré-2020. |

---

## Tier 2 — Substacks ativos com replicação (assinatura free + paid)

| Substack | URL | Por que vale |
|---|---|---|
| **Quantitativo** (Cole) | https://www.quantitativo.com/ | **Replicou Beat the Market** que tentamos. Posts regulares com código + walk-forward. Tem post "Intraday Momentum for ES and NQ" (jan/2025). |
| **QuantSeeker** | https://www.quantseeker.com/ | Curador de papers com replicação. Post sobre Pre-FOMC (fev/2025). Hedge fund + academia. |
| **Harbourfront Quant** | https://harbourfrontquant.substack.com/ | Replicação de calendar anomalies + factor strategies. |
| **QuantifiedStrategies** | https://substack.com/@quantifiedstrategies | Estratégias short-term backtested. |

---

## Tier 3 — Blogs e fontes de psicologia (já sabemos que valem)

| Fonte | URL | Por que vale |
|---|---|---|
| **TraderFeed** (Brett Steenbarger) | http://traderfeed.blogspot.com/ | Blog ativo. **A única fonte de psicologia/processo** que recomendo com confiança. ~25 anos de track record com hedge funds. |
| **NexusFi** (forum) | https://nexusfi.com/ | Comunidade de futures traders sérios. Threads sobre regime adaptation, ICT/SMC backtest, Al Brooks bar-by-bar. |
| **Brett Steenbarger livros**: *The Daily Trading Coach*, *Trading Psychology 2.0*, *Positive Trading Psychology* | (vários) | Para profundidade. |

---

## Tier 4 — Repositórios de código verificáveis

| Repo | URL | Por que vale |
|---|---|---|
| **smart-money-concepts** (joshyattridge) | https://github.com/joshyattridge/smart-money-concepts | Implementação Python de ICT/SMC indicators. **Útil para BACKTEST do framework SMC** que tantos vendem. Se não der edge no nosso framework, refuta empiricamente. |
| **backtesting.py** (kernc) | https://github.com/kernc/backtesting.py | Framework Python alternativo. Útil para sanity check do nosso framework (rodar mesmo plugin nos dois). |
| **Zipline** (Quantopian, antigo) | https://github.com/quantopian/zipline | Framework descontinuado mas estável. Boa referência arquitetural. |

---

## Tier 5 — Livros clássicos que ainda valem

| Livro | Autor | Por que vale |
|---|---|---|
| **Trading in the Zone** | Mark Douglas | Mentalidade probabilística. Citado pelo NotebookLM com razão. |
| **The Mental Game of Trading** | Jared Tendler | Modelo Inchworm. Ferramenta prática para drawdowns. |
| **Trading Price Action** (3 volumes) | Al Brooks | Bar-by-bar reading. Discricionário mas útil para entender contexto. |
| **Day Trading with Short Term Price Patterns** | Toby Crabel (1990) | Origem do NR4/NR7 que está na nossa estratégia aprovada. |
| **Technical Analysis of the Financial Markets** | John Murphy | Referência clássica para inter-market analysis. |
| **Algorithmic Trading: Winning Strategies** | Ernie Chan | Foco em quant retail. Mean reversion, pairs trading, sazonalidades. |

---

## O que NÃO recomendo (e por quê)

- **Cursos pagos individuais (Marcelo Ferreira, Inner Circle Trader courses)**: sem evidência empírica externa. Comunidades replicam mas com cherry-picking documentado.
- **Influencers Twitter/YouTube de daytrading**: sem registro CFTC, sem track record auditável.
- **Wyckoff, Elliott Waves**: frameworks complexos com **muitas variáveis livres** (overfit por construção). Difíceis de algoritmizar de forma falsificável.
- **"AI/ML black box"** sem código aberto e sem walk-forward: sem replicabilidade.

---

## Como usar isso no NotebookLM

**Sugestão de fluxo:**

1. **Carregar Tier 1 inteiro** (10 papers) no NotebookLM — esses são o "fundamento sólido".
2. **Fazer perguntas direcionadas:**
   - "Qual o consenso atual sobre Pre-FOMC drift em MNQ minute pós-2020?"
   - "Quais strategies tem edge bruto > 5 pts/trade documentado em MNQ?"
   - "Como filtrar OFI para que tenha sinal preditivo? Que dados são necessários (book depth)?"
   - "Por que TOM funcionou em ES até 2010 e não funciona mais? Há sub-períodos onde ainda funciona?"
3. **Comparar respostas com nossos achados empíricos** (regra de ouro 4 pts/trade, OFI refutado, TOM bloqueado).
4. **Adicionar Tier 2 (Substacks)** depois — para análises mais práticas e códigos.
5. **Tier 3 (psicologia) por último** — durante o hold-out cego, esse é o que mais ajuda.

---

## Termo de busca útil pra achar mais papers

Se quiser caçar mais material:

```
SSRN: "intraday momentum futures" "execution constraints"
SSRN: "order flow imbalance" "MNQ" OR "Nasdaq futures"
SSRN: "calendar anomaly" "decline" OR "disappearing" "futures"
arXiv: "limit order book" "futures" "predictability"
arXiv: "prop trading" "intraday" "drawdown"
Google Scholar: "NQ futures" "high frequency" 2024
```

---

## Lição da sessão para a curadoria

**Filtros que separa hipótese viável de alucinação:**

1. **Existe paper acadêmico peer-reviewed?** (não apenas Substack)
2. **Existe replicação independente?** (autor original + outros 1-2 autores)
3. **Existe código aberto?** (GitHub, ou supplementary materials do paper)
4. **Os dados de validação cobrem 2020+?** (regime pós-pandemia + algos modernos)
5. **A magnitude do edge é > 5 pts/trade ou Sharpe > 1 documentado?** (compatível com nossa regra de ouro)

Se a hipótese passa nos 5 filtros, vale implementar e rodar WF.
Se passa em 3-4, vale jogar no NotebookLM e analisar criticamente.
Se passa em <3, **provavelmente é alucinação ou cherry-picking**.

---

## TL;DR para o usuário

**Pega esses 10 links e joga no NotebookLM:**

1. https://arxiv.org/abs/2605.04004 (Structural Limits MNQ)
2. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172 (Beat the Market)
3. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3134546 (Disappearing Pre-FOMC)
4. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5233918 (Magnitudes FOMC)
5. https://www.researchgate.net/publication/385968274 (Disappearing TOM)
6. https://harbourfrontquant.substack.com/p/do-calendar-anomalies-still-work (Calendar replication)
7. http://arxiv.org/abs/2508.06788v1 (OFI in S&P E-mini)
8. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365 (Hedging Demand Intraday)
9. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4692190 (0DTEs Gamma)
10. https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq (Quantitativo replication)

Pede pra ele:
> "Sintetize esses 10 papers para um trader de MNQ futures usando
> NinjaTrader 8 com fricção Topstep (USD 2500 trailing DD). Foque em:
> (a) edges documentados ≥ 5 pts/trade após fricção, (b) por que
> Pre-FOMC e TOM degradaram pós-2020, (c) que dados são necessários
> para fazer OFI funcionar (book depth?), (d) padrões intraday que
> sobreviveram a 2024-2025."

Esse prompt é **MUITO mais difícil de alucinar** que o original que
você usou, porque pede números específicos verificáveis.
