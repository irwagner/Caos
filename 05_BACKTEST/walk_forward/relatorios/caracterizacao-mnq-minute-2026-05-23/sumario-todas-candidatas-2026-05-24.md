# Sumário consolidado — todas as candidatas testadas em MNQ minute

**Data:** 2026-05-24
**Período de dados:** 2025-03-17 → 2026-05-18 (~290 dias úteis)
**Fricção:** Topstep (slippage 0.25 pt/lado + comissão USD 0.62/contrato/lado + slippage_fracao_range 0.075)

## Tabela mestre

| ID            | Estratégia                              | Janelas | Trades/jan | Sharpe | Win rate | PnL pts | Edge bruto/trade | Status         |
|---------------|------------------------------------------|---------|------------|--------|----------|---------|------------------|----------------|
| 2026-05-22-01 | ORB Crabel original                      | 4       | ~80/ano    | <0     | <50%     | <0      | <2.5 pts         | rejeitada      |
| 2026-05-23-01 | ORB s/ fricção (deprecated)              | -       | -          | 1.42   | -        | +6170   | -                | revogada       |
| 2026-05-23-03 | ORB c/ hold-out                          | 4       | -          | 0.38   | -        | -       | -                | rejeitada      |
| 2026-05-23-04 | Pre-FOMC (slippage fixo, 60/60)          | 4       | 2          | **+7.49** | 75% | +119  | ~60 pts          | candidata frágil |
| 2026-05-23-05 | Pre-FOMC (slippage proporcional, 60/60)  | 4       | 2          | **+6.75** | 75% | +96   | ~50 pts          | candidata frágil |
| (NR7)         | EstrategiaORBCrabel modo=nr7             | -       | ~30/ano    | ~0.5   | -        | +474    | ~10 pts          | candidata frágil |
| 2026-05-24-02 | NoiseArea k=14 (momentum)                | 4       | 59.25      | **−8.64** | 10.9% | −340 | ~-1.4 pts | rejeitada |
| 2026-05-24-03 | NoiseArea k=90 (momentum)                | 3       | 60.00      | **−10.08** | 8.3% | −377 | ~-2.1 pts | rejeitada |
| 2026-05-24-04 | TurnOfMonth (120+120, 1 janela)          | 1       | 4.00       | +0.44  | 50%      | +50    | ~50 pts          | bloqueada (dados) |
| 2026-05-24-05 | NoiseArea k=14 (mean-reversion)          | 4       | 59.50      | **−3.45** | 46.6% | −180 | ~-0.8 pts | rejeitada |
| 2026-05-24-10..14 | Sweep fricção (NoiseArea inverter)   | 4 ea    | 59.5       | -4.7 a +0.24 | varies | varies | -      | analítico      |
| 2026-05-24-15 | TurnOfMonth (60+60, 4 janelas)           | 4       | 2.5        | **−1.07** | 50% | −85 | ~-34 pts/trade | rejeitada |
| 2026-05-24-16 | OvernightDrift (Cooper 2008)             | 4       | 49.50      | **−1.07** | 49.9% | −487 | ~-9.8 pts | rejeitada |
| 2026-05-24-17 | NoiseArea inverter h=14:30-19:00 UTC     | 4       | 59.50      | **−3.47** | 50.0% | −193 | ~-0.8 pts | rejeitada |
| 2026-05-24-18 | Pre-FOMC 120/120 (1 janela)              | 1       | 4          | **−0.58** | 50% | −10 | ~-2.6 pts/trade | rejeitada (esta config) |

## Achados gerais

### 1. Regra de ouro empírica do projeto

**Edge bruto necessário ≥ 5 pts/trade sob fricção Topstep para Sharpe ≥ 1.**

Derivação do sweep `2026-05-24-10..14`:

- 240 trades × 2.5 pts/trade de fricção = 600 pts/ano de custo
- Para Sharpe ≥ 1 anualizado em 4 janelas WF, precisa PnL líquido ≥ ~200 pts
- Logo edge bruto necessário ≥ (600 + 200) / 240 ≈ 3.3 pts/trade no mínimo
- Margem de segurança 50% → 5 pts/trade

Estratégias com edge bruto < 5 pts/trade (intraday no ruído):
- Noise Area momentum: edge bruto NEGATIVO (~-1.4 pts)
- Noise Area mean-reversion: edge bruto +1.7 pts (insuficiente)
- ORB Crabel original: edge bruto < 2.5 pts

### 2. MNQ futures NÃO replica overnight effect de equity ETFs/ações

OvernightDrift (Cooper 2008) em MNQ deu Sharpe −1.07 com win rate 50%
exatamente coin-flip. MFE/MAE simétricos (+123/−122 pts).

Hipótese: arbitragem algorítmica no MNQ overnight elimina o drift
que persiste em ações individuais ilíquidas. Confirma achado de
Berkman-Liu (2017) que o efeito é menor em futures.

### 3. Calendar effects em MNQ recente: pouca evidência

TOM (Carchano-Tornero 2011): mediana Sharpe −1.07 em 4 janelas
60+60 (9 trades totais). Janela 1 deu Sharpe +9.59 (efeito sample
size com 2 trades), janelas 0/2/3 negativas. Variância altíssima.

Hipótese: efeito calendar pode ter desaparecido em ES/MNQ desde
~2010 (algos comeram); ou amostra <10 trades é insuficiente.

### 4. As únicas candidatas frágeis sobreviventes

- **Pre-FOMC drift (60/60)**: ~2 trades/janela, Sharpe local +6.75 a +7.49,
  win rate 75%, edge bruto ~50-60 pts/trade. Edge bem acima do
  threshold de 5 pts. Frágil só por baixa frequência (4 janelas
  com 8 trades totais). Configurações maiores (120/120) **degradam**
  o resultado — provavelmente porque incluem meetings 2025 com
  cortes/aumentos abruptos que invalidam o drift.
- **Crabel NR7**: ~30 trades/ano, edge bruto ~10 pts/trade, Sharpe ~0.5.

### 5. Caracterização tick MNQ (2026-05-24, contrato 06-25)

Processado 12 GB de tick (~338M linhas, 43 min em ~131k lin/s puro
Python) → spread_minuto.csv com 34k minutos.

**Spread efetivo medido:**

| Regime           | Spread mediano | Spread p90 |
|------------------|---------------|------------|
| Geral            | 0.5145 pts    | 0.7344 pts |
| **RTH NY (14-19h UTC)** | **0.40-0.41 pts** | 0.61 pts |
| Overnight        | 0.5455 pts    | 0.7693 pts |
| Pico de iliquidez (h=22 UTC) | 0.6683 pts | - |

**Razão spread / range_minuto:** mediana 0.0812. **Validado: o
`slippage_fracao_range=0.075` usado no sweep é praticamente o
valor real.** Não foi exagero — a regra de ouro de 5 pts/trade está
empiricamente correta.

**Achado operacional:** filtro de horário ótimo (sessão restrita
14:30-19:00 UTC) **não melhorou** o resultado da Noise Area
mean-reversion (WF 2026-05-24-17, Sharpe −3.47 vs −3.45 da sessão
completa). O lockout pré-fechamento de 30 min já protege contra os
horários de maior fricção. **Confirma:** o problema é edge bruto,
não calibração de fricção.

### 5. Padrão claro

**Estratégias direcionais "no ruído" estão eliminadas.** O caminho
viável passa por:

- Eventos macro com edge bruto > 50 pts (Pre-FOMC).
- Padrões multi-day de holding longo (NR7 que dura ~5 dias úteis).
- Quando tick chegar: medir spread efetivo, refinar fricção, possivelmente
  resgatar candidatas que estão na fronteira (sf=0 → +0.24 da NoiseArea).

## Próximos passos sugeridos

1. **Combinar Pre-FOMC + NR7 em mini-portfolio explícito** — já feito em
   commit `d0a1788` mas vale rerodar com dados mais recentes (4 janelas).
2. **Spread Filter overlay** — implementar mas não esperar milagre.
   Pode reanimar candidatas marginais.
3. **Aguardar tick data** — a regra de ouro tem 1 fragilidade: assumimos
   `slippage_fracao_range=0.075` como real. Se medirmos sf=0.02 (spread
   menor), Noise Area mean-reversion volta pra mesa (Sharpe ~+0.0
   pelo sweep — ainda fraca, mas nem tudo está condenado).
4. **Variantes Pre-FOMC**: filtros por dia da semana do meeting,
   janela ampliada (D-2 a D+1), só sobre meetings com surpresa de
   taxa documentada.
5. **NÃO abrir Debate Auto** — todos os resultados são negativos
   (gatilho G3 ativo mas sem proposta de promoção).
