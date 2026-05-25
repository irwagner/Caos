# State of Research — 2026-05-24

Resumo executivo de tudo que foi descoberto até hoje sobre estratégias
viáveis em MNQ. Documento vivo — atualizado a cada sessão.

## Achados centrais (ranqueados por valor)

### 1. Regra de ouro empírica do projeto

> **Para Sharpe ≥ 1 anualizado em MNQ minute sob fricção Topstep:
> edge bruto necessário ≥ 4 pts/trade.**

(Atualizado 2026-05-24 com tick consolidado de 14 meses: spread RTH
real é 0.37 pts, fricção ~2.0 pts/trade, threshold cai de 5 → 4 pts.)

Derivação:

- Fricção realista: ~2.0 pts/trade (slippage 0.25 absoluto + spread
  efetivo RTH 0.37/2 + comissão 0.62 USD ÷ 2 USD/pt + slippage proporcional
  ~0.08 × range).
- Para 240 trades/ano e Sharpe 1: PnL líquido ≥ 200 pts → edge bruto
  ≥ 2.8 pts/trade. Margem de segurança 50% → 4 pts/trade.

**Validado por:**

- Sweep `2026-05-24-10..14`: Noise Area com sf de 0 a 0.10. Confirmou
  break-even entre sf=0 (Sharpe +0.24) e sf=0.025 (Sharpe -0.70).
- Caracterização tick `2026-05-24` em 5 contratos (14 meses): razão
  real spread/range = 0.0812 ≈ 0.075 do sweep (overestimou só 0.9x).

**Implicação:** estratégias direcionais "no ruído" intraday (1m) do
MNQ estão eliminadas. Caminho viável: **moves estruturalmente
maiores** (eventos macro, calendário, gaps multi-dia).

### 2. Spread efetivo do MNQ por regime

Medido em **210 GB de tick** processados em 5 contratos (~14 meses
contíguos abr/2025 → mai/2026, 351k minutos):

| Regime                  | Spread mediano | p90    |
|-------------------------|---------------|--------|
| **RTH NY (14:30-21:00 UTC)** | **0.37 pts** | 0.56 pts |
| Geral                   | 0.49 pts      | -      |
| Overnight               | 0.52 pts      | 0.76 pts |
| Pico iliquidez (h=22 UTC) | 0.67 pts    | -      |

**Sazonalidade trimestral nova descoberta:**
- Picos antes de cada vencimento (abr 0.64, mar 0.58 pts)
- Mínimos no meio do trimestre (set 0.42, jul 0.44 pts)

**Implicação:** estratégias que operam só RTH NY pagam ~30% menos
fricção. Mas filtrar horário **não recupera** estratégias com edge
bruto pequeno (testado em 2026-05-24-17, Noise Area inverter com
sessão 14:30-19:00 → Sharpe -3.47, igual ao baseline).

### 3. Status das hipóteses testadas

| Família | Hipótese | Status | Sharpe | Comentário |
|---|---|---|---|---|
| Intraday momentum | Noise Area (Zarattini) | rejeitada | -8.6 a -10 | Win rate 11%, frontalmente errada |
| Intraday mean-rev | Noise Area inverter | rejeitada | -3.4 | Edge bruto 1.7 pts < threshold 5 |
| Calendar | Turn-of-Month (Carchano) | bloqueada | varies | Amostra insuficiente; pode ter morrido após 2010 |
| Calendar | Pre-FOMC drift (Lucca-Moench) | **frágil** | +6.75 | Win rate 75%, 2 trades/janela. Único positivo |
| Overnight | Cooper-Cliff-Gulen | rejeitada | -1.07 | Não replica em futures (algos arbitram) |
| Volatility | ORB original | rejeitada | <0 | Confirmado em 4 janelas |
| Volatility | NR7 | frágil | ~0.5 | Sobrevive friccão mas Sharpe baixo |

### 4. Pre-FOMC: degradação com janela maior

WF `2026-05-24-18` testou Pre-FOMC com 120/120 (vs 60/60 base):

- 60/60: Sharpe 6.75, win rate 75%, 8 trades em 4 janelas
- 120/120: Sharpe -0.58, win rate 50%, 4 trades em 1 janela

**Hipótese:** o drift Pre-FOMC original (Lucca-Moench 2015, dados
1994-2011) pode estar **mudando de regime** em 2025. Fed mais
transparente → pricing mais antecipado → drift menor. Meetings 2025
com cortes/aumentos abruptos invalidam o long-only.

**Próximo passo:** filtrar Pre-FOMC por:
- Tipo de decisão (cut/raise/hold)
- Surpresa de taxa documentada (CSV externo)
- Magnitude de move pré-meeting

## Inventário operacional

### Plugins implementados (`caos/walk_forward/estrategias/`)

| Plugin | Status | Testes |
|---|---|---|
| EstrategiaORB | usado | sim |
| EstrategiaORBCrabel (NR4/NR7) | usado | sim |
| EstrategiaPreFomcDrift | usado | 16 testes |
| EstrategiaNoiseArea (+ inverter, sessão custom) | usado | 18 testes |
| EstrategiaTurnOfMonth | usado | 22 testes |
| EstrategiaOvernightDrift | usado | 6 testes |

Total: ~110 testes passando, suite de 1100+ testes verde.

### Scripts auxiliares (`scripts/`)

| Script | Função |
|---|---|
| `rodar_wf_atomico.py` | Build manifesto + run WF em raiz isolada (evita NT8 escrevendo) |
| `sweep_friccao_noise_area.py` | Varia sf, mede impacto na Sharpe |
| `agregar_spread_tick.py` | Streaming de tick.txt → spread_minuto.csv (3-way merge Last/Bid/Ask) |
| `analisar_spread_mnq.py` | Estatística de spread + relatório markdown |
| `comparar_wfs.py` | Tabela comparativa entre IDs WF |

### Configs YAML (`05_BACKTEST/walk_forward/configs/`)

13 configs cobrindo todas as variantes. Formato canônico:
treino+teste em dias úteis, granularidade 1m, custos Topstep com
slippage_fracao_range 0.075 (validado por tick).

### WFs commitados (commits chave)

- `527f3f6`: Noise Area + TOM iniciais
- `fcf0067`: Noise Area inverter (mean-reversion)
- `991b24c`: Sweep de fricção
- `2877a92`: TOM 60+60 + Overnight
- `635b912`: Caracterização spread tick MNQ_06-25
- `cfbb7e4`: Filtro horário ótimo + Pre-FOMC 120/120

## Próximos passos por categoria

### A) Quando background tick terminar (~3-4h)

1. Rodar `analisar_spread_mnq.py` em cada contrato → 5 relatórios.
2. Consolidar spread médio temporal (ago/2025 → jun/2026).
3. Verificar se **spread melhorou ou piorou** ao longo do ano.

### B) Implementação OFI (Order Flow Imbalance)

Hipótese (papers SSRN Cont-Larrard 2014): pressão líquida bid/ask
prediz move curto. Pode dar edge >> 5 pts em janelas de 5-15 min.

Tem dados (Bid+Ask tick por minuto). Implementação ~2h.

### C) Variantes Pre-FOMC

1. Filtrar só meetings de "decisão neutra" (Fed mantém taxa).
2. Filtrar por dia da semana (qua mais frequente).
3. Janela ampliada D-2 → D+1 (Lucca-Moench 2018).

### D) Aguardar mais dados históricos do MNQ

A janela 2025-2026 é apenas 14 meses. Para TOM e Pre-FOMC, dados
de 2018-2024 daria amostra estatística suficiente para test-of-form.

## Decisões pendentes (Conselho)

Nenhuma agora. Todos os achados são **negativos** (rejeitam hipóteses)
ou **calibrações** (edge de mean-reversion existe mas é insuficiente).
Nenhuma proposta de promoção a candidata aprovada. Gatilho G3
permanece ativo mas sem necessidade de Debate Auto até que apareça
candidata com Sharpe ≥ 1 em 4+ janelas.
