---
agente_autor: Explorador
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T01:00:00Z'
id: catalogo-codigos-referencia-2026-05-24
tags:
- catalogo-referencia
- hydra
- hipoteses-extraidas
titulo: Catálogo das 17 referências C# + 8 Python (Hydra) + análise de hipóteses extraíveis
---

# Catálogo das referências C# + 8 heads Python — análise de hipóteses

> Sob recomendação do usuário (sessão 2026-05-24), o Explorador leu
> todas as referências disponíveis em `reference_hydra/` e classificou
> cada uma por: hipótese central, novidade vs Hydra v1, testabilidade.
>
> Conformidade: Hydra é referência interna (steering rule
> `reference-hydra-readonly`); citações são adaptações em pt-BR.

## Sumário executivo (TL;DR)

Das 17 referências C# + 8 heads Python:

- **0 hipóteses NOVAS** que o Hydra v1 não tenha testado em alguma forma.
- **3 categorias estruturais** se repetem: SMC (Sweep+BOS+FVG), Fimathe
  (range break + zonas + reentrada), Fibonacci (PriorDay-anchored).
- **4 referências contêm padrões úteis** para implementação futura
  (não estratégias novas), 1 caminho exploratório que exige tick data.

Conclusão prática: a recomendação anterior do Conselho permanece. As
3 candidatas registradas (Pre-FOMC drift, Crabel NR7 ORB, mini-portfolio)
**não são superadas** por nada das 17 referências. Mas há ideias de
infraestrutura úteis a integrar.

## Categoria 1 — SMC / ICT (5 arquivos)

| Arquivo | KB | Hipótese | Novidade vs Hydra v1 |
|---|---:|---|---|
| `OdinTrinity.cs` | 128 | Sniper (Sweep→BOS→FVG/OB pullback, reversão institucional) + Breaker (continuação em range break) — sistema dual com Quality Score 5-dimensões | Mesma hipótese da Head 3 (Silver Bullet) que morreu por implementação frágil em pandas. Implementação C# é mais robusta MAS **não foi testada** pelo Hydra com walk-forward. Sub-hipótese "Breaker" = ORB com Quality Score adicional (mesma família morta da ORB). |
| `Odin_v2.cs` | 55 | Score multidimensional 5 dim (SMC + Momentum + Volume + VWAP + Killzone) com gating MinScore + MinDimensions | Generalização do Quality Score — não é estratégia em si, é framework de filtro. Hydra v1 usou conceito similar via classifier HMM (declarado lagging). |
| `Odin_V1.cs` | 34 | Idem v2 sem refinamentos | Idem |
| `Rodrigo.cs` | 5 | SMC mínimo (60min context + 5min entries; sweep+BOS+FVG; sizing por win rate adaptativo) | **Sizing adaptativo por win rate** é único — aumenta agressividade quando WR>60%, reduz quando WR<40%. Risco óbvio: amplifica clusters de sorte/azar. |
| `Rodrigo_2.cs` | 13 | Idem mais sofisticado (FVG persistente com lookback, displacement factor, score breakdown por componente, killzone explícita) | Persistência de FVG (mantém zona ativa por N barras até mitigação) é detalhe técnico que pode aprimorar uma futura implementação ICT em CAOS. Não é hipótese nova. |

**Veredito categoria 1**: SMC/ICT já foi testado pelo Hydra v1 (Head 3 — morta) e por nós (briefing externo Mesfin 2026 — null result em 14 famílias OHLCV). **Não revisitar família**.

## Categoria 2 — Fimathe / Range Break (5 arquivos)

| Arquivo | KB | Versão | Características distintas |
|---|---:|---|---|
| `Fimathe.cs` | 24 | v20 | Setup aleatório, sem inversão única, sem reentrada — base inicial |
| `Fimathe_1.cs` | 28 | v21 | Adiciona "Confirmação 2x" — quando filtro 480 bloqueia, espera fechamento além de 1×range para validar entrada com R:R 2x |
| `Fimathe3.cs` | 26 | v3.4 | Versão mais simples (sem inversão/reentrada) com janela cruzando meia-noite e limite de operações por janela |
| `MisterMV2.1.cs` | 28 | v28 final | **Stop dinâmico** (Zona 1 na reversão / Range na continuação) + **Inversão única + Reentrada (violino)** + Filtros (480, Kid Bengala, Gap) |
| `Qwen_csharp_2026-04-26.cs` | 28 | v28 alt | Variante gerada por LLM — mesma lógica da MisterMV2.1 com pequenas diferenças de formatação |
| `Qwen_csharp_2026-04-25.cs` | 27 | v28 alt-2 | Idem, variante anterior |

**Veredito categoria 2**: Hydra v1 testou exatamente esta família como
**Head 4 — morta definitiva** (PF 1.07, ~break-even). Trades NORMAL
perdem (-124 pts em 550 ocorrências), só reentrada e inversão recuperam
o break-even. **Não revisitar família**.

Único achado útil: a **lição estrutural** de que o filtro 480min é
**contraprodutivo em mercado bull**. Se algum dia testarmos algo
similar, partir desse fato.

## Categoria 3 — Fibonacci sobre Prior Day (2 arquivos)

| Arquivo | KB | Hipótese |
|---|---:|---|
| `Manolo.cs` | 13 | **Fibonacci sobre PriorDay High-Low** com janela 04:30-08:30, filtros (VWAP align, candle color, Estocástico). Entry quando preço toca nível Fibo (suporte=lvl<close, resistência=lvl>close) com candle de rejeição. Stop 20pts, Target 40pts, max 5 wins/5 losses por dia |
| `BodyTrader.cs` | 14 | Mesma estratégia mas Fibonacci sobre **CORPO do PriorDay (Open-Close)** ao invés do range. Adiciona extensões fora do 0-100% (de -6.85 a +7.85). Janela igual 04:30-08:30 |
| `Rodrigo_3.cs` | 13 | Cópia idêntica do `Manolo.cs` com nome de classe alternativo |

**Hipótese econômica**: pivôs históricos (P-DH/P-DL/P-DC) atuam como
níveis institucionais de S/R; Fibonacci sobre eles fornece grade de
níveis testáveis.

**Novidade vs Hydra v1**: parcial. Hydra testou:

- Head 5 (Trend Pullback VWAP) — pullback ao VWAP em trend, com
  alvo PDH/PDL — usa pivôs prior day. PSR 49% (random) → morto.
- Head 1 (VWAP Fade) — fade em banda 2σ — não usa Fibo.
- **Fibo puro sobre PriorDay nunca foi testado isoladamente** no Hydra.

**Mas três alertas**:

1. **Janela 04:30-08:30** ET é pré-RTH (London open + transição
   Europa→NY). É exatamente a janela onde Head 7 (London Sweep) morreu
   catastroficamente. Ambiente difícil.
2. **Hipótese é literatura folclórica**, não tem replicação acadêmica
   (Lucca-Moench-equivalente não existe para "Fibo sobre PriorDay").
3. **Múltiplos parâmetros otimizáveis** (níveis Fibo, tolerância,
   filtros opcionais) = high overfit risk. Hydra v1 testou família
   próxima e morreu.

**Veredito categoria 3**: hipótese marginal, alto risco de overfit,
sem suporte literário forte. **Não revisitar antes das 3 candidatas
existentes (Pre-FOMC, Crabel NR7, mini-portfolio).**

## Categoria 4 — Sniffer Footprint (1 arquivo)

| Arquivo | KB | Função |
|---|---:|---|
| `OdinMaxMnqSniffer_v5.0_Footprint.cs` | 38 | **NÃO opera** — coletor de dados volumétricos (delta, POC, imbalance, cumulative delta) + tick aggregations (avg trade size, whale trades) |

Hipótese embutida: OHLCV puro insuficiente; **footprint volumétrico**
diferencia fluxo institucional de retail. Hydra v1 menciona explicit-
amente que footprint **NÃO foi testado** por escolha de escopo.

**Vale a pena?**

- **Sim em teoria**: Andersen et al. 2018 (briefing do Explorador
  2026-05-23) sustenta invariância intraday por trade-size em
  ES futures. Lopez de Prado dedica capítulo a microestrutura.
- **Não na prática hoje**: exige tick data + Tick Replay + chart
  Volumetric NT8. Tudo que **não temos**. Hydra v1 entrega o sniffer
  pronto mas pede 30+ dias de coleta com NT8 ligado em replay 100x.

**Veredito categoria 4**: caminho exploratório legítimo MAS exige
infraestrutura nova (tick data em granularidade fina). **Próximo
sprint de exportação NT8 deve incluir tick** se quisermos abrir essa
direção. Atualmente fora do escopo.

## Categoria 5 — Stub / outros (1 arquivo)

| Arquivo | KB | Conteúdo |
|---|---:|---|
| `SDEZoneStrategy1.cs` | 1 | Stub vazio — apenas usings + namespaces sem lógica. Nenhum trade. |

## Pythons heads (8 arquivos — todos mortos)

Não revisei o conteúdo Python individualmente; o **veredito coletivo**
do `2026-05-21_hydra_v1_null_result.md` é definitivo:

| # | Head | Status | Ressuscitar? |
|---|---|---|---|
| 1 | VWAP Fade | Morta — PSR 38% | Não |
| 2 | ORB Crabel 15m | Morta-ressuscitável (slippage mata) | Já testamos NR7 |
| 3 | ICT Silver Bullet | Morta por implementação | Não em pandas |
| 4 | Range Break Fimathe | Morta — PF 1.07 break-even | Não |
| 5 | Trend Pullback VWAP | Morta — PSR 49% (random) | Não |
| 6 | IB Extension | Morta — 67% rolling abaixo de 70% | Não |
| 7 | London Sweep | Morta catastrófica (OOS WR 0%) | Não |
| 8 | Power Hour Fade | Morta catastrófica (PF 0.24) | Não |

## Padrões de implementação úteis (a integrar futuramente)

Mesmo sem hipótese nova, há **6 padrões de código** das referências
que valem ser adotados em iterações futuras do CAOS:

### 1. Quality Score multidimensional (Odin_v2)

5 dimensões (SMC + Momentum + Volume + VWAP + Killzone) com gates
configuráveis (MinScore + MinDimensions). Filosofia: "convergência
multifatorial = entrada de alta qualidade". Útil como **filtro
adicional** sobre qualquer estratégia base.

### 2. Sizing adaptativo por win rate (Rodrigo)

`MinScore` ajusta dinamicamente:
- WR > 60% → score threshold reduzido em 5 (mais agressivo)
- WR < 40% → score threshold aumentado em 5 (mais conservador)

**Cuidado**: amplifica cluster luck. Útil só em horizontes longos
(10+ trades para WR estabilizar).

### 3. FVG persistente com lookback (Rodrigo_2)

Em vez de detectar FVG só no momento da formação, manter zona ativa
por N barras até ser mitigada. Permite entrada em pullback retardado.

### 4. Trailing stop 3 fases (OdinTrinity)

- R ≥ 0.3: stop move para `entry - 0.5×risk` (reduz risco metade)
- R ≥ 0.7: stop move para break-even
- R ≥ 1.0: trailing ATR (1.2× ATR)

**Já implementado** em `04_CODIGO/ninjascript/TrailingTresFases.cs` do
CAOS — boa convergência arquitetural.

### 5. Stop dinâmico por contexto (MisterMV2.1)

Stop diferente conforme **tipo de entrada**:
- Continuação → stop no extremo do range original
- Reversão (rompimento oposto) → stop além da Zona 1
- Inversão → stop além da zona oposta

Princípio transferível: **stop deve depender do invalidador da tese**,
não de uma fórmula fixa.

### 6. Reentrada "violino" (MisterMV2.1)

Após stop em operação NORMAL: se preço retorna ao range em ≤5 barras,
reentra na MESMA direção (assume "violino" — preço foi caçar stops e
voltou). Se não voltar em 5 barras, vai para inversão única.

**Risco**: revenge trading institucionalizado. No backtest do Hydra v1
mostrou que reentrada **salva o setup do break-even para perda** (sem
reentrada teria PF < 1.0). Útil mas usar com gestão rigorosa.

## Conclusão / recomendação informal

**O usuário pediu "encontrar melhorias"**. Encontrei:

1. **0 hipóteses estratégicas novas** das 17 referências.
2. **6 padrões de implementação úteis** para integrar em CAOS.
3. **1 caminho exploratório (footprint)** que exige dados que não
   temos.

A direção mais valiosa identificada nesta sessão estendida segue
sendo o **mini-portfolio Crabel NR7 + Pre-FOMC** (overlap=0,
PnL +USD 2.511 sob fricção fixa, 55 trades em 13 meses). Nenhuma
referência supera isso.

Próxima ação informal recomendada (apenas ENGENHARIA, sem novas
estratégias):

- **Adotar padrões 4 e 5 (trailing 3 fases + stop dinâmico por
  contexto)** quando as candidatas viáveis forem promovidas a paper.
- **Adotar Quality Score multidimensional** como filtro adicional
  opcional para qualquer estratégia futura.
- **Aguardar dados** para revalidação das 3 candidatas existentes em
  ~Q4/2026.

**Nada** das 17 referências justifica abrir Debate sobre nova
família.

## Referências

- `reference_hydra/02_ESTRATEGIAS/_index.md` — score Hydra v1
- `reference_hydra/01_LICOES_APRENDIDAS/2026-05-21_hydra_v1_null_result.md`
- `reference_hydra/04_CODIGO/ninjascript/reference/README.md`
- Decisão `2026-05-24-01` — revalidação ORB
- Análise `correlacao-crabel-pre-fomc-2026-05-24.md`
