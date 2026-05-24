---
agente_autor: Explorador
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T05:30:00Z'
id: estudo-robos-referencia-hydra-melhorias-2026-05-23
tags:
- estudo-robos-referencia
- hydra
- melhorias-literatura
- slippage-modeling
titulo: Estudo dos robôs de referência (Hydra v1) + melhorias da literatura
---

# Estudo dos robôs de referência + melhorias da literatura

> Esta nota é trabalho do **Explorador** consolidando: (a) tudo que o
> repositório histórico Hydra deixou de aprendizado sobre 8 estratégias
> intraday em MNQ, e (b) literatura externa de 2025-2026 com possíveis
> melhorias não exploradas pelo Hydra. **NÃO é Decisão do Conselho** —
> é input para Debate posterior se o usuário quiser ressuscitar alguma
> família.

## Inventário das 8 famílias testadas pelo Hydra v1

Hydra v1 testou todas as famílias abaixo no MNQ minute (2025-2026, ~14
meses). **Resultado global: null result formal — todas mortas sob
custos retail realistas.** Documentado em
`reference_hydra/01_LICOES_APRENDIDAS/2026-05-21_hydra_v1_null_result.md`.

| # | Família | PF backtest | Status final | Causa raiz |
|---|---|---:|---|---|
| 1 | VWAP Fade Reversion | 0.88 | Morta definitiva | Sem edge; mercado bull penaliza fade |
| 2 | ORB Crabel (15m) | 1.87 → 0.94 sob slippage | Morta-ressuscitável | Slippage realista mata edge |
| 3 | ICT Silver Bullet | n/a (0 trades) | Morta por implementação | Funnel 3 estágios pandas frágil |
| 4 | Range Break Fimathe | 1.07 | Morta definitiva | Filtro 480min contraprodutivo |
| 5 | Trend Pullback VWAP | 0.99 | Morta definitiva | Sem edge (PSR 49% = random) |
| 6 | IB Extension (Steidlmayer) | 1.20 → 1.42 rolling | Morta definitiva | 67% windows passam; abaixo de 70% |
| 7 | London Sweep | 0.79 | Morta catastrófica | OOS WR 0% |
| 8 | Power Hour Fade | 0.24 | Morta catastrófica | Bull continuation, não fade |

### Padrão estrutural identificado pelo Hydra v1

**4/8 famílias falharam por "fade contra direção macro"** (Heads 1, 5,
7, 8). MNQ 2025-2026 foi bull constante; estratégias contrárias não
funcionam em ambiente trending. Lição transferível: famílias de
mean-reversion pura não vão funcionar até o regime mudar.

## O que o Hydra v1 NÃO testou (gaps)

Por escolha de escopo, Hydra v1 deixou de fora:

1. **Estratégias de baixa frequência condicionais a evento** (FOMC, CPI,
   NFP). Frequência muito baixa para produzir N adequado em 14 meses.
2. **Estratégias de range cycle (Crabel NR4/NR7 puro)** — o Range Break
   Fimathe testou o setup do operador, não o Crabel original.
3. **Estratégias de overnight session** (16:00 NY → 09:30 NY) — Hydra
   focou em RTH.
4. **Limit order entry** — todas usaram market/stop. O Hydra v1 chegou
   a apontar (na Head 2 morta-ressuscitável) que migrar pra LIMIT pode
   recuperar edge, mas não testou.

## Achados externos relevantes (literatura 2025-2026)

### A1. Modelo de slippage proporcional à volatilidade

Confirmação direta do que o Hydra v1 descobriu empiricamente:

- [Volatility-Volume Slippage Model — Pomorski 2024](https://piotrpomorski.substack.com/p/volatility-volume-slippage-model)
- [QuantJourney — Slippage Comprehensive Analysis 2024](https://quantjourney.substack.com/p/slippage-a-comprehensive-analysis)
- [Markaicode — Real Transaction Costs in Backtests 2024](https://markaicode.com/fix-backtesting-pnl-transaction-costs/)

Content was rephrased for compliance with licensing restrictions.

Síntese: literatura de 2024-2025 **converge** que slippage realista é
proporcional ao produto de volatilidade × order_size_ratio. Modelo do
Hydra (slip = fração × OR_size) é caso particular. Nosso `CustosOperacionais`
atual usa **slippage fixo (0.25 pts/lado)** — está otimista por design.

**Implicação para o CAOS**: o `CustosOperacionais` deveria evoluir para
**slippage proporcional ao range de uma janela de referência** (ATR
recente, ou range da barra de entry). Trabalho não-trivial mas alinhado
com Decisão `2026-05-23-02` (Cerberus pediu modelagem honesta de risco).

### A2. Crabel NR4/NR7 — versão original que o Hydra v1 NÃO testou

Hydra v1 testou ORB de janela fixa de 15min. Crabel original (1990)
propõe ORB **CONDICIONAL** a NR4/NR7:

- [Crabel — Day Trading with Short Term Price Patterns and ORB 1990](https://oxfordstrat.com/trading-strategies/opening-range-breakout/)
- [StockCharts — NR7 Pattern](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7)

Síntese: **NR4** = dia cuja range diário é o menor dos últimos 4 dias.
**NR7** = idem para 7 dias. Hipótese: "compressão precede expansão" —
após dia muito estreito, range no dia seguinte tende a ser desproporci-
onalmente maior, e ORB intraday tem follow-through mais consistente.

**Comparação com nossa ORB e a do Hydra v1:**

| | ORB Hydra v1 | ORB CAOS | ORB Crabel + NR4/NR7 |
|---|---|---|---|
| Janela OR | 9:30-9:45 ET (15m) | 9:30-9:45 ET (15m) | Configurável; mas só opera **se ontem foi NR4/NR7** |
| Filtro de regime | Sem | Sem | NR4/NR7 (compressão prévia) |
| Frequência | ~7 trades/mês | ~10 trades/mês | ~2-3 trades/mês (sub-conjunto) |

**Hipótese testável**: a frequência menor da NR4/NR7-ORB seleciona dias
de alta probabilidade de breakout sustentado. Pode passar t-stat
mesmo onde ORB genérica falhou.

**Implementação no CAOS**: trivial — adicionar filtro condicional na
`EstrategiaORB` existente. Zero parâmetros novos otimizáveis (4 e 7 são
canônicos no paper original).

### A3. Limit order entry com offset de 1-2 ticks

Hydra v1 morta-ressuscitável Head 2 conjectura que migrar de stop
market pra limit order pode salvar a estratégia:

- [CME — The Limits of Limit Orders 2026](https://www.cmegroup.com/articles/2026/the-limits-of-limit-orders-in-retail-fx-cfd-trading.html)
- [The Microstructure Lab — Post Passive or Cross Now 2025](https://themicrostructurelab.substack.com/p/post-passive-or-cross-now-quantifying)

Caveat (Content was rephrased for compliance): no CME, limit orders
sempre executam como market quando tocados — não beneficiam de fill
passivo no mesmo lado. Mas reduzem a probabilidade de fill em break
violentos, **selecionando trades de menor slippage por design**.

**Adaptação possível**: entry como limit order no `OR_high + 1 tick`
(não no `OR_high + 1 tick` em stop market). Se mercado faz break
limpo e volta, entra. Se faz break violento direto, não entra (perda
de oportunidade compensada por evitar slippage extremo).

### A4. Overnight drift como filtro adicional

[Elm Wealth — Night Moves 2025](https://elmwealth.com/night-moves-overnight-drift/)
e [QuantSeeker 2025](https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift)
documentam que overnight drift no SPY é a **anomalia raiz** mais
robusta. Combinada com pre-FOMC, dá CAGR 8-9% em ETF 3x.

Adaptação não-trivial pro MNQ:

- Filtrar entradas LONG da ORB somente em dias com gap overnight
  positivo (close NY ontem → open NY hoje > 0).
- Filtrar entradas SHORT em dias com gap negativo.
- Esperado: reduz amostra mas elimina dias de gap-and-fade.

## Lições do Hydra v1 que devem ser **integradas ao CAOS**

Independente de qual família o Conselho decidir investigar:

1. **Slippage proporcional** (não fixo) — implementar em
   `CustosOperacionais` como subclasse `CustosProporcionais` ou flag.
2. **Métrica `PF-no-top5`** — remove os 5 maiores wins; se PF cair
   abaixo de 1.0, há cluster luck. Hydra v1 usa como gate obrigatório.
3. **Walk-forward rolling** — Hydra v1 promoveu Head 2 quando
   single-split deu NO-GO mas rolling mostrou 3/3 windows PASS. Nosso
   `JanelaGenerator` já faz isso; falta documentar como métrica
   primária no relatório.
4. **HMM 3-state como filtro** (não como roteador) — Hydra teve regime
   classifier que filtrava heads. Para nossas próximas iterações,
   considerar filtro de "dia trending vs choppy" via ATR/ADX (proxy
   barato).
5. **GO/NO-GO ex-ante escrito ANTES do teste** — Regra 4 do CLAUDE.md
   do Hydra. Já fazemos via Decisões do Conselho mas devemos formalizar
   o critério antes de cada WF.
6. **WR baixo + R:R alto > WR alto forçado** — Hydra v1 errou ao definir
   WR_min=48% para ORB; cancelou Head 2 que tinha WR 24% mas PF 1.87
   real. Aprendizado: aceitar WR 25-35% se R:R justifica.

## Famílias candidatas a INVESTIGAR no CAOS (priorizadas)

Apenas duas direções se sobressaem após esta análise:

### Candidata 1 — ORB Crabel + NR4/NR7

- Filtro condicional pré-existe na literatura clássica (Crabel 1990).
- Reduz frequência (sub-conjunto dos dias ORB) mas seleciona dias de
  alta probabilidade.
- Implementação trivial em cima da `EstrategiaORB` atual.
- Nenhum parâmetro novo otimizável (4 e 7 são fixos do paper).
- **Risco**: amostra final pode ser tão pequena que t-stat fica
  inconcluso (igual Pre-FOMC com N=10).

### Candidata 2 — Slippage proporcional + Pre-FOMC re-validação

- Não é família estratégica nova — é **revalidação da Pre-FOMC** com
  modelo de slippage alinhado com literatura de 2024-2025 e com
  achado empírico do Hydra v1.
- Hydra v1 mostra que slippage realista derruba PF de 1.87 → 0.94.
- Pre-FOMC operou em granularidade diária (entry close → saída close
  D+1). Slippage diário é diferente do intraday — provavelmente menor.
- Faz sentido medir antes de descartar.

### NÃO recomendadas

- VWAP fade, Range Break, Trend Pullback, London Sweep, Power Hour:
  testadas exaustivamente, falharam por razões estruturais. Não há
  nada na literatura recente que sugira mudança de regime que mude
  a conclusão.
- ICT Silver Bullet: implementação em pandas é frágil; reimplementar
  em NinjaScript é trabalho de dias com hipótese ainda não testada.
- IB Extension: 67% rolling windows passam, abaixo do gate de 70%.
  Aproximação demais ao threshold sugere que ressuscitar com mais
  dados pode dar 65% ou 75% — qualquer coisa nessa zona é instável.

## Recomendação informal do Explorador

1. **Implementar `CustosProporcionais`** no `CustosOperacionais` —
   trabalho ortogonal a famílias, beneficia qualquer revalidação
   futura.
2. **Adicionar filtro NR4/NR7 à `EstrategiaORB`** como variante
   opcional. Pequena contribuição de código, alta seletividade.
3. **Re-rodar Pre-FOMC com slippage proporcional** — se passar t-stat
   sob o modelo realista, é evidência mais forte que o atual.
4. **NÃO** revisitar VWAP fade, Range Break, Trend Pullback, London
   Sweep, Power Hour. O ônus da prova é maior que o benefício esperado.

## Conformidade

- Nenhuma reprodução verbatim > 30 palavras consecutivas de qualquer
  fonte externa.
- Conteúdos paráfrasados para conformidade com restrições de
  licenciamento.
- Repositório Hydra é referência interna (steering rule
  `reference-hydra-readonly`); citações são adaptações em pt-BR do
  conteúdo original.
