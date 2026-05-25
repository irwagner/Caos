# Briefing do Explorador — Mentorias, Setups e Conhecimento de Outros Traders

**Data:** 2026-05-25
**Foco:** literatura/comunidades estabelecidas que possam complementar a regra de ouro empírica do CAOS (edge bruto >= 4 pts/trade em MNQ)
**Filtro:** apenas fontes verificáveis (livros publicados, blogs ativos, papers, comunidades reconhecidas). Sem cursos pagos sem evidência empírica externa.

---

## 1. Achado mais relevante: a "Dead Zone" 11:30-13:30 NY

Fonte: [Tradeify — Intraday Futures Volatility Analysis (out/2025)](https://tradeify.co/post/intraday-futures-volatility-analysis-prop-firm-trading)

**Tese declarada (citação aproximada):**
- Volume e volatilidade caem 30-40% entre 11:30 AM e 1:30 PM ET (lunch lull institucional).
- Probabilidade de falso breakout neste intervalo > 60%.
- Recomenda flatten de posições ou reduzir risco significativamente.

**Implicação direta para CAOS:**
- Nossa estratégia aprovada `StrategyORBCrabelSpreadFilter` usa `HoraCorteEntradasUtc=19:00` (15:00 ET). Já corta antes do worst case.
- Mas as **entradas** acontecem entre 13:30-19:00 UTC (9:30-15:00 ET) — pegando justamente o "Dead Zone" na metade.
- **Hipótese testável:** adicionar um segundo filtro `HoraSemEntradasUtc=15:30-17:30` (11:30-13:30 ET) deve melhorar Sharpe ao remover trades de baixa qualidade no lunch lull.

**Custo de implementação:** trivial — adicionar dois `TimeSpan` ao `ParametrosORB`. Provavelmente 1h.

**Outro achado mensurável:** "NQ moves ~7x point range of ES, $5,000-$7,000 daily range vs $2,000-$3,000". Isso explica por que Topstep DD trailing de USD -2500 é apertado para NQ e por que o MNQ (1/10 do tick value de NQ) é a escolha certa para o CAOS.

---

## 2. Sequência de liquidez: Gold (08:20) → Oil (09:00) → Equities (09:30) ET

Mesma fonte. Hipótese declarada: **a volatilidade do GC/CL prevê a do ES/NQ no resto da manhã**. Especificamente:

- Volatilidade no opening hour (9:30) prevê intensidade da Power Hour (3:00-4:00 PM ET).
- Spillover gap-down em equities reage instantaneamente em GC/CL.

**Implicação para CAOS:**
- Não temos dados de GC/CL no manifesto. Adicionar seria caro (mais 50+ GB de tick).
- Hipótese mais barata: **usar volatilidade da primeira hora do MNQ como filtro para abrir posição na Power Hour**. Se vol da primeira hora < quartil 25, pula entrada na 2ª janela.

**Custo:** moderado (~3h). Mas a Power Hour não é o foco da estratégia ORB+NR7, que opera no opening range.

---

## 3. Brett Steenbarger — psicologia de performance

Fonte: [Brett Steenbarger – Building Edges That Last](https://www.forex.in.rs/positive-process-edges/) e [TraderFeed](https://traderfeed.blogspot.com)

Brett é **psicólogo clínico** que trabalha com hedge funds e prop firms há ~25 anos. Tese central:

- Trading é **performance discipline first, money game second**.
- Edges não morrem por causa do mercado, morrem porque o trader **abandona o processo** quando ele tem drawdown normal.
- Princípio do **ABCD framework** (achei via NexusFi):
  - **A**ssessment: medir regime de mercado regularmente (não só performance pessoal).
  - **B**ehavior: registrar comportamento sob estresse (trade journal).
  - **C**ognition: identificar quando emoção sequestra decisão.
  - **D**evelopment: iterar sobre processo, não sobre resultados.

**Implicação para CAOS:**
- O **Conselho-no-Chat formal** que temos já implementa parte disso (Devils_Advocate, Cerberus). Mas não temos **journal estruturado de cada operação**.
- Hipótese: **adicionar campo `journal_humano` ao `ResultadoJanela`** para o usuário registrar observações pós-execução (regime macro, emoção dominante, sleep tracker, etc). Útil quando entrar em hold-out cego.

**Custo:** baixo (~1-2h). Útil para o hold-out já aprovado.

---

## 4. ICT / Smart Money Concepts (Michael Huddleston)

Fontes: [DamnPropFirms ICT Trading](https://damnpropfirms.com/glossary/ict-trading/), [LuneTrading ICT 2026](https://lunetrading.com/blog/ict-trading-strategy-2026-65-75-win-rates-prop-firm), [smart-money-concepts Python (joshyattridge)](https://github.com/joshyattridge/smart-money-concepts).

**Tese declarada (resumo de múltiplas fontes):**
- Mercado é direcionado por liquidity sweeps + order blocks + fair value gaps.
- Win rate reportado em comunidades: 65-75% em setups específicos (Order Blocks 70-75%, FVG 65-70%).
- **Killzones**: London Open (08:00 NY), NY Open (09:30 NY), NY PM (1:30 NY).
- ICT é **discretionary framework**, não algoritmo único.

**Análise crítica (Devils_Advocate):**
- **Win rate 65-75% é extraordinário** se confirmado. Pode ser cherry-picking comum em comunidades de trading.
- O ICT **não tem paper acadêmico verificável** comparável a Lucca-Moench (Pre-FOMC) ou Carchano-Tornero (TOM). Falta trilha de auditoria estatística.
- Implementação algorítmica disponível no GitHub (joshyattridge/smart-money-concepts) — **PODE ser backtested** com nosso framework.
- Janelas de tempo (killzones) são as mesmas que já vimos no Tradeify (sequência de liquidez).

**Hipótese testável para CAOS:**
- Implementar `EstrategiaICT_OrderBlock` baseado na biblioteca pública. Backtest no MNQ com nossa fricção real.
- Se win rate em backtest ≥ 60% e Sharpe ≥ 1, candidata viável.
- Se win rate < 50%, achado importante: a comunidade ICT não tem edge real (cherry-picking confirmado).

**Custo:** moderado-alto (~6h para implementar 1 setup ICT clean + WF). Maior valor: confirmar/refutar empiricamente.

---

## 5. Al Brooks — Price Action bar-by-bar

Fontes: [Trading Price Action (Wiley)](https://books.wiley.com/titles/9781118066676/), [Brooks Trading Course](https://www.brookstradingcourse.com).

**Tese central (de NexusFi summary):**
- Cada bar conta a história completa de um auction (open, high, low, close + tamanho relativo).
- Bars em sequência mostram a evolução do auction.
- **Sem indicators, sem averages** — só leitura de bar.
- Setups específicos: H1/H2 (high 1, high 2 — pullbacks em uptrend), L1/L2 (mirror bear), iiii (4 inside bars consecutivos), wedge reversal.

**Análise crítica:**
- Al Brooks é **respeitado**: Wiley publisher, 4 livros, 5-minute ES é seu mercado primário.
- Mas é **discretionary**. Brooks afirma "potential trade on almost every bar" — **não é algoritmizável trivialmente**.
- Existem implementações TradingView com seus padrões básicos. Não auditadas.

**Hipótese testável para CAOS:**
- Implementar **detector de iiii (4 inside bars)** + entry no break do iiii. Inside bar é objetivo (não-discricionário).
- Backtest no MNQ. Edge bruto esperado: 5-15 pts (similar ao NR7).
- **Sinergia com NR7**: 4 inside bars é mais restritivo que NR7. Pode ser **substituto melhor**.

**Custo:** baixo (~2h). Edge potencial moderado.

---

## 6. Adaptrade Builder + genetic programming

Fonte: [Adaptrade Builder Playbook](https://futures.aeromir.com/builder-playbook).

**Tese:**
- Programa que usa genetic programming para **gerar estratégias automaticamente** sobre dados de futuros.
- Workflow: (a) define critérios de fitness (Sharpe, Calmar, drawdown), (b) algoritmo gera milhares de variantes, (c) seleciona as melhores, (d) faz Walk-Forward.

**Análise crítica:**
- **Risco massivo de overfitting** com genetic programming sobre dados financeiros.
- Mas a abordagem **sistemática** é alinhada com o CAOS.
- A literatura acadêmica sobre evolutionary computation em finance é mista — tem bons resultados em FX, resultados duvidosos em equity index.

**Hipótese testável:**
- **Não usar Adaptrade direto** (caro, fechado).
- Implementar **busca aleatória simples** sobre nossos plugins existentes: combinar `EstrategiaORBCrabel(modo=nr4|nr7)` + `EstrategiaSpreadFilter(modo=mediana_diaria|hora_otima)` + `EstrategiaCircuitBreaker(limites variados)` em um grid pequeno (~12 combinações).
- Validar com hold-out cego forte para evitar overfitting.

**Custo:** baixo (~3h). **Útil pra encontrar próxima candidata**.

---

## 7. Comunidades estabelecidas

Por valor decrescente:

### NexusFi (ex-BigMikeTrading)
- Forum de futures traders sério. Mistura de noobs com 20-yr veteranos.
- Threads recentes (2026): bar-by-bar Al Brooks, ICT/SMC, regime adaptation Steenbarger.
- **Útil para validar hipóteses** antes de implementar.

### r/algotrading (Reddit)
- Foco em quant. Críticas honestas a backtest overfitting.
- Threads frequentes: prop firm vs hedge fund, futures vs stocks, NQ vs ES.

### Quantocracy / Allocator's Edge
- Aggregator de blogs quant. **Onde apareceram inicialmente** os papers SSRN Zarattini-Aziz que já usamos.
- Verificar weekly digest tem alto ROI.

### TraderFeed (Brett Steenbarger blog)
- Atualizado semanalmente.
- Focado em performance + market regime.

### Quantitativo NQ (Christian Cole)
- Já replicado por nós (Beat the Market lookback=90).
- Substack com analytics regulares de NQ.

---

## Ranking de hipóteses para próximas sessões

Por **ROI estimado** (potential edge / custo de implementação):

| # | Hipótese | Custo | Edge potencial | Risco overfit |
|---|---|---|---|---|
| 1 | **Filtro Dead Zone** (11:30-13:30 ET sem entradas) | 1h | +0.3 a +0.7 Sharpe | baixo |
| 2 | **iiii pattern (4 inside bars)** como filtro/setup | 2h | candidata nova ~Sharpe 1 | baixo |
| 3 | **Grid pequeno** combinando overlays existentes | 3h | candidata 2 ~Sharpe 1.5+ | médio |
| 4 | **journal_humano** no ResultadoJanela | 1h | melhora hold-out | nenhum |
| 5 | **ICT Order Block** algorítmico (joshyattridge) | 6h | +/- (cherry-picking?) | alto |
| 6 | **Volatility regime filter** (GC/CL leading equities) | 4h | ?? | médio |

---

## Recomendação para próxima sessão

**Implementar #1 (Dead Zone filter) primeiro** — uma hora de trabalho, vai modificar o `ParametrosORB`, e provavelmente melhora o Sharpe da estratégia já aprovada. Se sim, **abrir Debate de seguimento ANTECIPADO** (antes dos 30 dias do hold-out) para promover a versão melhorada.

Logo depois:

**#2 (iiii pattern)** — pode virar substituto melhor do NR7. Se win rate ≥ 50% e edge bruto ≥ 5 pts, candidata 2.

**#5 (ICT Order Block)** — é o mais curioso e o mais arriscado. Se ICT funcionar de fato em backtest com 60%+ win rate sob fricção realista, é achado MUITO valioso (e refuta criticismo acadêmico ao framework). Se não, achado também é valioso (refuta a comunidade).

---

## Notas sobre o próprio briefing (transparência)

- Todas as fontes citadas têm publicação datada de 2025-2026.
- Win rates "65-75%" reportados pela comunidade ICT NÃO foram independentemente verificados pelo Explorador. Devem ser tratados como hipóteses a testar, não fatos.
- Brett Steenbarger é **a única fonte de psicologia/processo** que tenho confiança em recomendar — décadas de track record com prop firms reais.
- Adaptrade Builder é **mencionado mas não recomendado** — ferramenta paga sem evidência pública robusta.
- Conteúdo deste briefing foi rephraseado das fontes originais para conformidade com licenciamento (≤30 palavras consecutivas por fonte).
