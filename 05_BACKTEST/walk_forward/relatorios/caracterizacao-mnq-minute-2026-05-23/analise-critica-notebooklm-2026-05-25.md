# Análise crítica do material NotebookLM (Plano CAOS) + achado OFI

**Data:** 2026-05-25
**Contexto:** usuário trouxe 3 documentos sintetizados pelo NotebookLM
sobre arquitetura CAOS para MNQ (SMC/ICT, Fimathe, microestrutura,
hardware, psicologia). Nesta sessão: análise crítica integrada com o
achado empírico do OFI.

---

## TL;DR

- **OFI direto refutado em MNQ minute.** WF `2026-05-25-06` deu Sharpe
  −39.99, PnL −22 846 pts em janela única. Tese momentum
  empiricamente REFUTADA.
- Edge bruto invertido seria ~3.77 pts/trade (abaixo do threshold de
  4 pts da regra de ouro). **OFI mean-reversion também não viável**
  sob fricção Topstep.
- **Achado que importa:** os 3 documentos do NotebookLM tratam SMC/ICT
  como verdade revelada. Em MNQ minute, **a base empírica sugere que
  microestrutura não tem edge exploitable**. Boa parte da literatura
  SMC parece descrever artefatos pós-hoc, não causalidades.

---

## Análise documento por documento

### Documento 1 — Plano Diretor de Estratégias

**Recomendado adotar:**

- **Setup Fimathe — anatomia da vela** (3.1): "90% das velas de alta
  fecham próximas à máxima" é uma **propriedade testável do MNQ**.
  Adicionar análise estatística sobre nossos dados de minuto. Custo
  ~30min.
- **Virada de Mão Fimathe** (3.4): "preço atinge Take 2 e retorna ao
  open → reversão potente". Algoritmizável e testável. Custo ~3h.
- **Mean Reversion via VWAP em RSI extremos** (2.3): clássico, fácil
  de implementar como overlay sobre a estratégia aprovada.
- **Risk-to-Reward 1:2 com WR 50%+** (4.1): consistente com nossos
  KPIs. Pode ser benchmark formal.

**Cético:**

- **"Win rate histórico de 65% para 50 EMA pullback"** — número muito
  específico sem fonte. Alucinação provável do NotebookLM. Para
  validar, **temos que rodar empiricamente**.
- **"FVG não preenchido por 6 horas vira zona de alta estabilidade"**
  — regra arbitrária sem evidência. Testável mas baixa expectativa.

### Documento 2 — Plano Técnico de Evolução

**Recomendado adotar:**

- **HMM 3-State (Hidden Markov Model)**: classificar regime em
  Trend/MeanRev/Choppy via biblioteca `hmmlearn`. Pode tornar nosso
  Circuit Breaker **inteligente** (pausa em Choppy detectado, libera
  em Trend confirmado). Custo ~6h. **Risco de overfitting alto** —
  exige hold-out cego rigoroso.
- **Volume Spike > 150% da média** como filtro de qualidade: usar
  como overlay sobre Crabel NR7+SF. Trivial de implementar.
- **Daily Loss Limit (3% do equity)**: já temos no Cerberus. Confirma
  abordagem.

**Cético:**

- **"Fractional EMA Kalman Filter"**: combinação esotérica que
  cheira a NotebookLM compondo termos sem evidência. Kalman puro
  seria razoável; combinar com cálculo fracionário é overengineering.
  **Não implementar sem paper acadêmico.**
- **"Neural Weight Oscillator"**: termo sem referência clara. Pular.
- **"Tick Replay denso para backtesting"**: já temos. Validado.

### Documento 3 — Plano Técnico de Evolução (versão expandida)

**Recomendado adotar:**

- **Liquidity Sweep via Old Highs/Lows**: algoritmizável. Detectar
  swing high/low + overshoot + reversão. **Diferente do OFI puro** —
  é estrutural, baseado em níveis. Custo ~4h. Vale rodar.
- **Bollinger Squeeze (Expansion)** com 20 candles + Volume Spike:
  testável, mecânico. Custo ~3h.
- **KPIs empíricos**: PF > 1.5, WR > 50%, Sharpe > 1.0, MDD < 15%.
  Bom benchmark formal — podemos exigir esses thresholds em todas
  as candidatas futuras.
- **Bibliografia**: Mark Douglas (Trading in the Zone), Jared Tendler
  (Mental Game of Trading) são fontes legítimas. Podem complementar
  os achados de Brett Steenbarger no briefing anterior.

**Cético/Refutado:**

- **OFI / Cumulative Delta como momentum**: REFUTADO empiricamente
  na sessão atual. Correlação `tfi_norm` vs retorno futuro = −0.030
  no melhor caso (30min vs 30min). **Magnitude insuficiente** para
  edge sob fricção.
- **"Order Block + Liquidity Sweep + FVG + CHOCH"** como conjunto
  validador: sem paper acadêmico citável que comprove edge em
  futures de equity index. **Hipótese a testar individualmente**,
  não aceitar em bloco.
- **Hardware HFT (i9-14900K, fibra 1Gbps)**: irrelevante pro projeto
  CAOS atual. Nossa estratégia roda em 1m, não milissegundos.

---

## Achado empírico desta sessão: OFI no MNQ refutado

### Caracterização TFI MNQ_06-25

Processado `MNQ_06-25.{Last,Bid,Ask}.txt` (12 GB, 338M linhas, 47 min)
com Lee-Ready algorithm. Output: `ofi_minuto.csv` com 34 365 minutos
contendo `buy_volume`, `sell_volume`, `tfi`, `tfi_norm`.

### Correlação TFI × retornos futuros

Grid de correlações sobre 34 165 minutos:

| TFI soma (min) | ret futuro 1m | 5m | 10m | 30m |
|---|---|---|---|---|
| 1 | -0.0008 | -0.0027 | -0.0041 | -0.0052 |
| 5 | -0.0025 | -0.0027 | -0.0097 | -0.0096 |
| 10 | -0.0036 | -0.0092 | -0.0144 | -0.0150 |
| 15 | -0.0063 | -0.0103 | -0.0129 | -0.0190 |
| 30 | -0.0043 | -0.0087 | -0.0143 | **-0.0304** |

**Padrão claro:**

1. **Todas correlações são negativas** — sinal mean-reversion.
2. **Magnitude máxima −0.030** — extremamente fraca.
3. **Cresce com horizonte** — TFI 30m vs ret 30m é o pico.

### WF OFI momentum

`2026-05-25-06`: 1 janela (só 06-25 tinha CSV processado).

| Métrica | Valor |
|---|---|
| Trades | 6 058 |
| PnL total | **−22 846 pts** (USD −45 692) |
| Sharpe | **−39.99** |
| Win rate | 31.5% |
| Edge bruto/trade | **−3.77 pts** |

### Conclusão sobre OFI

**OFI direto não funciona em MNQ minute.** Edge bruto invertido seria
+3.77 pts/trade — **abaixo do threshold de 4 pts** da regra de ouro.
Mesmo a versão mean-reversion não passa a fricção Topstep.

**Por que o NotebookLM e a literatura SMC vendem OFI/Cumulative Delta
como gold standard?**

Hipóteses (não-exclusivas):

1. Funciona em mercados ilíquidos (não MNQ — o MNQ é arbitrado por
   HFT em milissegundos).
2. Funciona em horizontes muito curtos (segundos) que não temos como
   acessar com agregação por minuto.
3. **Cherry-picking**: comunidades SMC mostram apenas trades que
   funcionaram, criando ilusão de edge.
4. **Confluência**: OFI sozinho não funciona, mas combinado com Order
   Block / Liquidity Sweep pode ter sinal. Exige teste empírico de
   cada conjunto, custo alto.

---

## Atualização do backlog (substitui o anterior)

| # | Hipótese | Custo | Edge potencial | Risco overfit | Origem |
|---|---|---|---|---|---|
| 1 | **Dead Zone filter** (11:30-13:30 ET) | 1h | +0.3 a +0.7 Sharpe na aprovada | baixo | Tradeify |
| 2 | **Volume Spike > 150% filtro** | 2h | candidata 2 ~Sharpe 1 | baixo | Doc 2 |
| 3 | **HMM 3-State** como CB inteligente | 6h | candidata 2 com regime adaptativo | **alto** | Doc 2 |
| 4 | **iiii pattern (Al Brooks)** alternativo NR7 | 2h | candidata 2 ~Sharpe 1 | baixo | Briefing anterior |
| 5 | **Fimathe anatomia da vela**: validar 90%-stat | 30min | calibração + filtro | baixo | Doc 1 |
| 6 | **Liquidity Sweep estrutural** (Old H/L) | 4h | candidata genuinamente nova | médio | Doc 3 |
| 7 | **Bollinger Squeeze (20 candles)** | 3h | candidata volatility | médio | Doc 3 |
| 8 | **Variantes Pre-FOMC** (filtros) | 3h | recupera candidata frágil | baixo | Briefing anterior |

### Removidos do backlog (REFUTADOS empiricamente)

- ~~OFI direto (momentum)~~ — `2026-05-25-06` Sharpe −39.99.
- ~~OFI mean-reversion~~ — edge bruto 3.77 pts/trade < 4 (regra de ouro).
- ~~Mini-portfolio Pre-FOMC + NR7+SF~~ — `2026-05-25-03` Sharpe +0.08.
- ~~Noise Area (todas variantes)~~ — anterior.
- ~~Overnight effect (Cooper)~~ — anterior.

### Recomendação para próxima sessão

**#1 (Dead Zone filter) primeiro.** 1h, baixo risco, deve melhorar
estratégia já aprovada. Se confirmar +0.3 Sharpe, abrimos Debate de
seguimento antecipado para promover a v2.

**#2 (Volume Spike > 150%) em paralelo.** 2h, simples, alinhado com
Doc 2 do NotebookLM e literatura clássica.

**#3 (HMM 3-State) com cuidado**, depois que tivermos #1 e #2 testados.
Risco de overfitting alto requer hold-out cego prospectivo dedicado.

---

## Lição metodológica desta sessão

**Documentação gerada por LLM (NotebookLM, ChatGPT etc.) sobre trading
deve ser tratada como hipótese, não verdade.** Todo achado da
literatura SMC/ICT precisa **teste empírico no nosso framework** antes
de ser incorporado. A regra de ouro empírica do projeto (edge bruto
≥ 4 pts/trade) é o filtro que separa hipóteses viáveis de alucinações.

O OFI desta sessão é caso exemplar: **conceitualmente sólido**
(Cont-Larrard 2014 é paper real), **vendido como gold standard** pela
comunidade SMC, **refutado empiricamente** sob fricção real.

Sem dados de tick processados, teríamos seguido a literatura
cegamente. Com os dados, **economizamos meses** de tentativa-erro com
estratégia que jamais funcionaria.
