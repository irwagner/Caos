---
agente_autor: Explorador
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T03:30:00Z'
id: briefing-explorador-2026-05-23-orb-rejeitada-direcoes-com-edge
tags:
- explorador
- caracterizacao-mnq
- orb
- pre-fomc
- overnight-drift
titulo: Briefing externo — direções com edge documentado em índices futuros após rejeição da ORB
---

# Briefing do Explorador — direções com edge documentado em índices futuros

> Esta nota NÃO é Decisão do Conselho. É evidência externa coletada
> sob solicitação do Kiro_Brain após rejeição empírica da ORB
> (Decisão `2026-05-23-02`). Serve como input para futuros Debates de
> seleção de família estratégica. Status: `notas_injetadas`,
> consultivo, não-vinculante.

## Contexto

Após o WF `2026-05-23-03` entregar Sharpe mediano 0.38 sobre
hold-out cego (Decisão `2026-05-23-02` revogou a aprovação
preliminar), a caracterização descritiva da série MNQ minute
mostrou autocorrelação dos log-retornos < 0.01 em todos os lags
1-60min. O Conselho parou de mexer na ORB e o Explorador foi
chamado para varrer literatura sobre o que efetivamente tem edge
documentado em índices futuros intradia, com foco em MNQ/NQ.

Critério de inclusão das fontes: paper acadêmico revisado, ou
estudo aplicado com metodologia walk-forward declarada, ou anomalia
documentada com replicação independente. Excluído: posts de
TradingView, vendor-research sem dados públicos, marketing.

## Achado 1 — falsificação sistemática da OHLCV em MNQ (mai/2026)

**Mesfin, Mathias. _Structural Limits of OHLCV-Based Intraday Signals
in MNQ Futures: A Systematic Falsification Study._ arXiv:2605.04004
[q-fin.TR], 5 mai 2026.**

[arXiv:2605.04004](https://arxiv.org/abs/2605.04004)

Resumo paráfrase do abstract (conformidade < 30 palavras consecutivas):

- Dataset: 947 dias úteis × 5min de MNQ (2021-2025).
- 14 famílias de sinais OHLCV testadas: opening range breakouts,
  gap strategies, volume signals, cross-session momentum, liquidity
  grabs, volatility-conditioned classifiers, news-driven.
- Critério institucional: out-of-sample walk-forward, T-stat ≥ 2.0,
  ≥ 30 trades, retorno líquido positivo após custo fixo de 2 pontos
  round-trip, estabilidade multi-anual.
- Resultado: **nenhum sinal satisfaz todos os critérios
  simultaneamente**.
- Edge bruto disponível em execução next-bar-open: **0.07-1.50
  pontos por trade** — insuficiente para cobrir transação.
- Sinal de gap-continuation atingiu T = 3.23 e +14.52 pontos mas
  falhou no critério de tamanho amostral (N = 22).

Conteúdo paráfrasado para conformidade com licenciamento.

**Implicação direta para o CAOS**: o resultado externo confirma
ponta-a-ponta a Decisão `2026-05-23-02`. Não é coincidência que
a ORB com config default deu Sharpe 0.38 — esse resultado é
consistente com o que paper independente, com 4× mais dados que
nós, encontrou em 14 famílias OHLCV. **OHLCV puro em MNQ
intradia é provavelmente um beco sem saída.**

## Achado 2 — pre-FOMC drift continua vivo

**Lucca, David O., e Emanuel Moench. _The Pre-FOMC Announcement
Drift._ Journal of Finance 70:1, 2015.**

[Lucca-Moench 2015 SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1923197)
e replicação aplicada em [QuantSeeker (fev/2025)](https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift)
— Content was rephrased for compliance with licensing restrictions.

Síntese das fontes:

- S&P 500 acumula retorno positivo abnormal nas 24h anteriores aos
  anúncios oficiais agendados do FOMC. Padrão presente desde
  set/1994 e replicado até dez/2024 com dados pós-publicação.
- Quase metade do retorno realizado em excesso da bolsa americana
  acumulado desde 1994 vem desses 8 dias por ano.
- Não há reversão pós-anúncio — o drift é assimétrico.
- Efeito mais forte em períodos de VIX elevado (consistente com
  hipótese de "resolução de incerteza"); efeito mais fraco em
  meetings sem coletiva de imprensa (Lucca-Moench 2018).
- Estratégia long-flat: comprar fechamento do dia D-1, vender
  fechamento do dia FOMC. Em SPY: CAGR ~4%, Sharpe 0.5-0.6,
  trading em ~5% dos dias. Em ETF 3x alavancado (TQQQ/SPXL):
  CAGR 8-9%, drawdown máximo ~18%.

Crítica: Kurov, Wolfe & Gilbert (2019) — _The Disappearing Pre-FOMC
Announcement Drift_ — argumentam que o efeito enfraqueceu pós-2011.
Lucca-Moench (2018) e QuantSeeker (2025) refutam mostrando que o
drift persiste mas concentrado em meetings com press conference.

**Implicação para o CAOS**:

- Família estratégica COMPATÍVEL com nossa caracterização: efeito
  é em escala de 24h (overnight), não em escala 1m-60m onde MNQ é
  ruído. Não conflita com autocorrelação ~0 que medimos.
- Frequência baixa (8 sinais/ano) é uma DESVANTAGEM operacional
  mas uma VANTAGEM anti-overfit — pouca chance de overfitar 8
  observações por ano.
- Implementação requer calendário externo de meetings FOMC. Não
  introduz parâmetros otimizáveis se a regra é "long do close
  D-1 ao close D+0".

## Achado 3 — overnight drift como anomalia raiz

**Bondt-Hua-Korajczyk via Elm Wealth (mar/2025): _Night Moves: Is
the Overnight Drift the Grandmother of All Market Anomalies?_**

[Elm Wealth — Night Moves](https://elmwealth.com/night-moves-overnight-drift/)
— Content was rephrased for compliance with licensing restrictions.

Síntese:

- O retorno do S&P 500 desde os anos 1990 é **integralmente**
  realizado overnight (close → próximo open). O retorno intraday
  (open → close) é estatisticamente próximo de zero ou levemente
  negativo, dependendo do período.
- Padrão presente em índices, ETFs e individualmente em ações
  (com efeito mais forte em "meme stocks" segundo Elm Wealth 2024).
- Hipóteses: viés de demanda overnight de ETFs passivos com rebalance,
  fluxos de hedge de market makers em options, ausência de retail
  ativo durante a noite.

**Limitação crítica**: estratégia "comprar close, vender open" em
SPY é destruída por slippage e bid-ask spread. O retorno overnight
existe na série teórica mas é difícil de capturar líquido.
Pesquisa aplicada de QuantSeeker e systematicindividualinvestor
(2021) confirma que a versão naive não funciona; versões
condicionais (filtro de VIX, filtro de pós-FOMC) podem funcionar.

## Achado 4 — invariância intraday por trade-size em ES

**Andersen, Bondarenko, Kyle, Obizhaeva (2018): _Intraday Trading
Invariance in the E-Mini S&P 500 Futures Market._**

[SSRN abstract 2693810](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2693810)
— Content was rephrased for compliance with licensing restrictions.

Síntese: a volatilidade por transação no ES é proporcional ao
inverso do quadrado do tamanho médio de trade. Lei empírica
estável intraday.

**Implicação**: não é estratégia em si, mas **fornece estimador
honesto de quanto o mercado mexe quando há fluxo de ordens
grandes**. Útil para cálculo de limite máximo de tamanho que
podemos negociar sem virarmos preço.

## Sumário das 3 direções com edge documentado (priorizadas)

| # | Direção | Edge documentado | Compatível com nossa caracterização? | Custo de implementação |
|---|---|---|---|---|
| 1 | **Pre-FOMC drift** (long em window de 24h pré-FOMC) | Sim, replicado 1994-2024 | Sim (escala 24h, não 1min) | Médio (calendário FOMC + WF) |
| 2 | **Overnight drift condicional** (long close→open com filtros) | Sim na bruta, ainda não validado em forma capturável | Sim (escala overnight) | Alto (precisa modelar slippage carefully) |
| 3 | **Sinais OHLCV intraday em MNQ** | **Não** (Mesfin 2026 falsifica 14 famílias) | Sim | Já gastamos — descartar |

## Recomendação informal

Esta nota é consultiva. Se um proponente quiser abrir Debate sobre
nova família estratégica, **a primeira família a propor é
Pre-FOMC drift** porque (a) compatível com a caracterização do
MNQ que fizemos, (b) menor risco de overfit pela frequência baixa,
(c) literatura externa robusta com replicação independente,
(d) mecanismo causal plausível (resolução de incerteza =
compensação a quem mantém posição em um evento de informação).

Implementação mínima viável:

1. Tabela de datas dos meetings FOMC agendados. Pode vir de calendário
   manual (~8 datas/ano × 30 anos = ~240 linhas em CSV).
2. Estratégia plug Walk-Forward: entra long no close do dia D-1,
   sai no close do dia D+0. Senão flat. Sem parâmetros otimizáveis.
3. Validar: rodar WF na parte JÁ VISTA (até 24/fev/2026). Se Sharpe
   na parte vista >= 0.5 com fricção realista, validar no
   hold-out cego de 60 dias úteis. **NÃO mudar parâmetros entre
   essas duas validações** — esse é o teste honesto.

## Fontes consultadas (ordem de relevância)

- [Mesfin 2026 (arXiv 2605.04004)](https://arxiv.org/abs/2605.04004)
  — falsificação OHLCV em MNQ.
- [Lucca-Moench 2015 (SSRN 1923197)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1923197)
  — pre-FOMC drift seminal.
- [QuantSeeker 2025](https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift)
  — replicação aplicada de Lucca-Moench, dados até dez/2024.
- [Elm Wealth: Night Moves (mar/2025)](https://elmwealth.com/night-moves-overnight-drift/)
  — overnight drift contemporâneo.
- [CXO Advisory: FOMC Drives Global Equity Markets](https://www.cxoadvisory.com/economic-indicators/fomc-drives-global-equity-markets/)
  — sumário do Lucca-Moench.
- [Andersen et al. 2018 (SSRN 2693810)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2693810)
  — invariance no ES.

Conformidade: nenhuma reprodução verbatim > 30 palavras consecutivas
de qualquer fonte. Conteúdos paráfrasados para conformidade com
restrições de licenciamento.
