# Blueprint Tático MNQ: Estratégia Quantitativa para NinjaTrader 8 (Topstep)

**Origem:** Resposta do Gemini Pro (NotebookLM) à etapa-zero da
Decisão `2026-05-29-02`.
**Data:** 2026-05-29
**Status:** Documento externo, **não autoritativo**. Material para
triagem do Conselho — não confundir com Decisão.
**Filtro crítico aplicado em:** `[[Etapa_Zero_NotebookLM_Gemini_2026-05-29]]`

---

## 1. Limites Estruturais e Microestrutura de Mercado

A premissa fundamental para a negociação do contrato MNQ (Micro
E-mini Nasdaq-100) baseia-se na evidência de que os dados puramente
OHLCV (Open, High, Low, Close, Volume) são insuficientes devido à
densidade de ordens transitórias que degradam o sinal direcional.
Conforme o paper **arXiv 2507.22712**, a eficácia de uma estratégia
quantitativa depende da filtragem estrutural do fluxo de ordens
(tempo de vida, contagem e timing de modificação).

Para isolar o edge, o sistema deve aplicar uma escada diagnóstica
de três etapas:

1. **Correlações Contemporâneas:** Medição da relação imediata
   entre o *Order Book Imbalance* (OBI) e o preço.
2. **Associação Linear entre Regimes Discretizados:** Identificação
   de dependências entre estados de desequilíbrio e retornos.
3. **Excitação Hawkes em Tempo de Evento:** Modelagem de como fluxos
   de ordens passados (especialmente ordens "pai" de trades
   executados) catalisam movimentos de preço subsequentes.

### Tabela: Edge vs. Fricção (MNQ)

| Componente de Microestrutura | Impacto no Edge Estrutural | Justificação Técnica |
|---|---|---|
| Alvos > 5 Pontos | Irrelevância Estatística | Fricção de custos e slippage em ordens a mercado corroem a expectativa matemática em alvos curtos |
| Filtragem de Fluxo Agregado | Ganho Marginal | O ruído de ordens transitórias mascara o desequilíbrio real no Limit Order Book (LOB) |
| Filtragem de Ordens "Pai" | Ganho Sistemático | A associação direcional é significativamente mais forte ao filtrar ordens que geram execuções reais (arXiv 2507.22712) |
| Bid-Ask Spread | Custo de Liquidez | Operar a mercado no MNQ força o trader a pagar o spread, resultando em edge negativo |

### Requisitos Técnicos para Execução Limitada

- **Prioridade de Fila:** O algoritmo deve atuar como provedor de
  liquidez via ordens limitadas para capturar o spread.
- **Identificação de OBI:** Utilizar exclusivamente dados de Nível 1
  para calcular o desequilíbrio, focando na pressão
  compradora/vendedora persistente.
- **Sincronização de Precisão:** Requer carimbo de tempo em
  milissegundos para validar a excitação de eventos Hawkes antes
  da entrada.

---

## 2. Anomalias de Calendário e Regimes de Volatilidade

A dinâmica de preços no MNQ é ditada pela resolução de incerteza
macroeconômica e ciclos de liquidez institucional, e não apenas
por indicadores técnicos isolados.

### Regime de Expansão (Pre-FOMC Announcement Drift)

Conforme documentado por **QuantSeeker**, o mercado exibe um viés
positivo anormal nas 24 horas que antecedem as decisões do FOMC.

- **Métrica de Performance:** Retornos médios excedentes em ETFs
  alavancados (TQQQ/SPXL) entregam um **CAGR de 8-9%** operando
  apenas 5% do tempo.
- **Hipótese de Resolução de Incerteza:** O drift é estatisticamente
  mais forte quando o VIX está em quartis elevados.

### Regime de Reversão (Turn-of-the-Month — TOM)

As anomalias de calendário como o efeito TOM (janela de 4 dias no
fechamento/abertura do mês) persistem devido a fluxos de fundos
de pensão e rebalanceamento institucional
(**Harbourfront Quantitative Finance**).

- **Lógica de Reversão:** Retornos negativos na última sexta-feira
  do mês tendem a correlacionar-se com reversões positivas no
  mês subsequente, alinhando-se ao ciclo de pagamentos e aportes
  sistemáticos.

---

## 3. Lógica de Decisão Hierárquica (Last 30 Min)

Nos últimos 30 minutos de pregão, o conflito entre o momentum de
fecho e o rebalanceamento institucional exige uma árvore de decisão
ponderada:

**Árvore de Decisão Ponderada (Weighted Decision Tree):**

- **IF** (Data == Turn-of-the-Month Window)
- **THEN** Priorizar momentum institucional (seguir o fluxo de
  entrada de fundos).
- **ELSE IF** (Preço fora da Value Area AND Divergência no
  Cumulative Delta)
- **THEN** Ignorar momentum; Executar estratégia de **Mean Reversion**
  para o VWAP.
- **IF** (VIX > 20)
- **THEN** Aumentar peso da Reversão (distorção por volatilidade).
- **ELSE** Execução cautelosa com 50% da posição.
- **ELSE**
- **THEN** Encerrar operações; evitar ruído de liquidação de
  *day traders* de varejo.

**Condições para Ignorar Momentum:**

1. Cumulative Delta atinge picos de exaustão sem renovação de
   máximas/mínimas (absorção).
2. Preço atinge bandas de desvio padrão do VWAP (2.0+) em regime
   de baixa volatilidade.

---

## 4. Arquitetura Lógica e Implementação em Python

A lógica deve ser implementada no NinjaTrader 8 via integração
Python, focando em processamento de fluxo de ordens de Nível 1.

### Modelo de Markov Oculto (HMM) para Estados de Mercado

O filtro HMM deve classificar o mercado em estados (Trending vs.
Ranging) utilizando retornos logarítmicos e transições baseadas em
ATR:

- **Estado 0 (Trending):** Baixa volatilidade relativa, retornos
  logarítmicos consistentes em uma direção.
- **Estado 1 (Ranging):** Alta volatilidade (ATR Spike), retornos
  logarítmicos com média zero.

### Detecção de "Whale Trades" (Whale Liquidity and Absorption Profile)

Em vez de depender do DOM (Level 2), utilizamos a lógica de
absorção intrabarra:

- **IF** (Volume da Barra > Média das últimas 20 barras * 1.5) **AND**
  (Delta Divergente do deslocamento de preço)
- **THEN** Identificar zona como "Institutional Absorption".
- **Booleano de Entrada:** IF (Price < VWAP) AND (HMM_State == "Ranging")
  AND (Absorption_Detected == True) THEN Signal_Buy_Limit_at_Support.

---

## 5. Gestão de Risco e Restrições Topstep (USD 2500 Trailing DD)

Para proteger o limite de USD 2500 de Trailing Drawdown, aplicamos
o modelo de dimensionamento de posição baseado em risco de conta
(`Risk_acc`).

**Fórmula de Position Sizing:**

```
Position Size (Contracts) = floor(
  Risk_acc × Account Equity
  / (ATR(14) × 2 × Tick Value)
)
```

**Configurações de Risco Rigorosas:**

- **Risco por Operação (`Risk_acc`):** Máximo de 0.5% a 1% do saldo.
- **Tamanho Máximo de Posição:** **2 contratos MNQ**.
- **Daily Loss Limit:** **USD 500**. Ao atingir 20% do drawdown
  total permitido, o sistema deve cessar execuções para evitar o
  "revenge trading".
- **Stop-Loss:** Definido pelo ATR (Average True Range). Nunca mover
  o stop-loss a favor do prejuízo.

---

## 6. Checklist de Execução e Validação Diária

- **Validação de Contexto Macro:**
  - Verificar calendário econômico (High-impact news / Red Folders).
  - Identificar proximidade de reuniões do FOMC (Ativar viés de
    Pre-FOMC Drift se VIX > Quartil 3).
  - Verificar janela Turn-of-the-Month (TOM).
- **Monitoramento de Volatilidade e Estrutura:**
  - Avaliar estado HMM (Trending vs. Mean Reversion).
  - Confirmar localização do preço em relação ao VWAP e Bandas de
    Desvio.
- **Checklist Psico-Fisiológico:**
  - Medição de Variabilidade da Frequência Cardíaca (HRV) ou Vagal
    Tone. Se o nível de stress for elevado (HRV baixo), operar
    apenas via automação total.
- **Análise Pós-Sessão:**
  - Cálculo de Sharpe Ratio e Profit Factor diário.
  - Log de execuções no TraderSync; auditar se as saídas ocorreram
    por estratégia ou impulsividade emocional.

> Este Blueprint é uma arquitetura técnica baseada em evidências
> empíricas e microestrutura. A execução deve priorizar a
> disciplina algorítmica sobre a discricionariedade subjetiva.
