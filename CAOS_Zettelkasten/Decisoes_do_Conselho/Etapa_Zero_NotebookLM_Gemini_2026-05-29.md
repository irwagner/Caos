---
tipo: nota_zettel
area: Decisoes_do_Conselho
titulo: Etapa-zero NotebookLM/Gemini para a Decisao 2026-05-29-02 — filtro critico
data: 2026-05-29
autor: Kiro_Brain
links:
  - "[[Decisao_2026-05-29-02_Triagem_Shopping_List_Papers]]"
  - "[[Refutacao_P2_Range_Absoluto_2026-05-29]]"
tags:
  - etapa-zero
  - notebook-lm
  - gemini
  - VVG
  - mesfin
  - filtro-critico
---

# Etapa-zero NotebookLM/Gemini — filtro critico do material recebido

## Contexto

A Decisao `2026-05-29-02` aprovou caminho **P1 modificada** (foco em
arXiv 2605.11423 / Mesfin / Volatility-Volume-Gap Classifier) com
**etapa-zero obrigatoria**: carregar 3 papers no NotebookLM com
prompt explicito antes de implementar. O usuario executou a
etapa-zero e devolveu dois documentos:

- `99_FONTES_EXTERNAS/2026-05-29_Blueprint_Tatico_MNQ_Gemini.md`
- `99_FONTES_EXTERNAS/2026-05-29_Sintese_Caos_MNQ_Topstep_Gemini.md`

Esta nota aplica **filtro critico** ao material recebido, separando
**substrato solido** (incorporavel ao Spec novo) de **alucinacao /
contaminacao LLM** (rejeitar).

## SOLIDO — incorporar ao Spec novo

### S1 — Confirmacao independente do limite estrutural OHLCV

arXiv 2605.04004 confirma o que a empiria interna ja sabia
(`[[Refutacao_P2_Range_Absoluto_2026-05-29]]`): edge bruto OHLCV
gravita entre **0.07 e 1.5 pontos por trade** na media incondicional
do MNQ. Apos friccao de varejo (comissoes ~$1.14 RT NT8 +
slippage de breakouts), edge se desintegra. **Sistemas de alta
frequencia OHLCV puros estao matematicamente fora**.

Esta e exatamente a "regra de ouro empirica" de 5 pts/trade que o
projeto adotou em ciclos anteriores.

### S2 — Resolucao do paradoxo Reversal vs Momentum

A Decisao `2026-05-29-02` levantou explicitamente o conflito entre:
- arXiv 2605.11423 (Mesfin): late-session **reversal**
- SSRN 3760365 (Baltussen et al): last 30min **momentum**

Gemini resolve o paradoxo: **as duas teses NAO competem, sao
condicionais a regimes diferentes**:

- **Baltussen** = comportamento *incondicional e sistemico* de
  indices amplos (S&P/Nasdaq cash). Premissa: dealers Short Gamma.
- **Mesfin/VVG** = comportamento *condicional a dias filtrados* por
  Gap Direcional + Volume de Abertura, especifico ao MNQ.

Em dias VVG-positivos: institucionais que capturaram drift da manha
fazem profit-taking agressivo no fim → **reversao**.
Em dias nao-classificados: hedging de Baltussen domina → **momentum**.

**Implicacao tecnica**: a estrategia opera APENAS nos dias
VVG-positivos. Reversao late-session conditional. Os dias
nao-classificados ficam fora do trading (Baltussen funciona em
S&P cash, nao necessariamente em MNQ futuro).

### S3 — Regime atual (2026) favorece reversao via 0DTE Gamma

SSRN 4692190 (0DTEs Gamma) mostra que a explosao de opcoes 0DTE
(maioria do volume de derivativos do indice em 2026) coloca os
dealers **Long Gamma** a maior parte do tempo intraday. Quando o
book esta Long Gamma, o hedge inverte: vendem nas altas, compram
nas quedas → **forca gravitacional de Mean-Reversion**.

Confirma que VVG-reversal (Mesfin) eh o modelo correto para o
regime atual. **Momentum de Baltussen so corrobora em Gamma
Squeeze** (estrutura de opcoes quebra → dealers vao Short Gamma
profundo).

Esta nuance NAO eh utilizada pela estrategia (operar so em VVG+
ja eh suficiente), mas **explica por que o paper Mesfin de
2021-2025 deve permanecer valido em 2026+** — o regime de Long
Gamma 0DTE so cresce, nao reverte.

### S4 — Edge documentado VVG: +7.80 pts/trade liquido (T = 1.46)

Numero do paper Mesfin (Paper 2). Eh acima do limiar de 5 pts/trade
da regra de ouro. T = 1.46 eh modesto (significancia ~85%, nao
99%) — sinal valido mas com varianca alta. Confirma a observacao
do Conselho `2026-05-29-02` sobre N pequeno → IC95% precisa ser
re-estimado em janela de validacao real do CAOS.

### S5 — Gestao de risco: 1-2 contratos MNQ travado

Position sizing alavancado quebra a conta Topstep no regime de
baixa performance (alta curtose do paper Mesfin). Travar **1 a 2
contratos** eh recomendacao convergente do Gemini com a Decisao
`2026-05-25-02` historica do CAOS. Sem novidade, mas confirma.

### S6 — Estrutura geral da estrategia

A logica do classificador VVG, conforme decoded pelo Gemini:

1. **Baseline volume**: media movel 10 dias do volume da primeira
   hora de pregao (09:30-10:30 EST).
2. **Filtros do dia (medidos na primeira meia hora de pregao)**:
   - **Volume anomaly**: volume(09:30-10:00) > 1.5 * baseline
   - **Gap anomaly**: |open(09:30) - close(D-1)| / close(D-1) > 0.3%
3. Se ambos satisfeitos → dia eh VVG-positivo.
4. **Drift direcional**: medido do open(09:30) ao close(14:30).
5. **Trade reversal**: 14:30 entry **contra** o drift, com stop
   e alvo (parametros suspeitos — ver R1 abaixo).
6. **Encerramento forcado** as 15:50 EST (proteger Topstep EOD).

Esse esqueleto eh implementavel sem book depth (so OHLCV) e sem
janela movel longa (resolve bug de paridade Python<->C# da
`[[Decisao_2026-05-28-01]]`).

## SUSPEITO — alucinacao / contaminacao LLM, rejeitar

### R1 — Stop fixo 20 pts / Alvo fixo 40 pts NAO sao do paper

O codigo Python do Gemini coloca `stop_loss = entry +/- 20 pts` e
`take_profit = entry +/- 40 pts` como "Stop Fixo" e "Alvo
Otimizado". **Nao ha citacao explicita** dessas magnitudes vindo
do paper Mesfin original — pode ser heuristica do Gemini.

**Acao requerida no Spec**: ler arXiv 2605.11423 diretamente e
extrair os valores de stop/target. Se Mesfin nao especificou
stop/target precisos, derivar de algo invariante (ex: media de
ATR-day do periodo de calibracao 2021-2025). Em hipotese alguma
aceitar 20/40 pts cegamente.

### R2 — Threshold 1.5x volume / 0.3% gap precisa ser confirmado

Os multiplicadores 1.5x e 0.3% **podem** ser do paper, mas a
sintese do Gemini nao cita pagina/secao especifica. **Acao
requerida**: confirmar no paper original. Se nao estiver claro,
calibrar UMA vez na janela 2025-03 a 2025-06 (separada do WF
futuro) e congelar.

### R3 — VWAP, Cumulative Delta, HMM, Whale Trades, Hawkes — RUIDO

Toda a Secao 3-4 do "Blueprint Tatico" (HMM de Markov para
estados de mercado, Whale Trades via volume divergente,
Cumulative Delta, VWAP bandas, Order Book Imbalance via Hawkes)
**nao tem nada a ver com VVG/Mesfin**. Eh agregacao de outros
frameworks que o Gemini misturou.

**Rejeitar inteiramente**. A estrategia eh **VVG puro** com
trade reversal late-session. Adicionar HMM, VWAP ou Cumulative
Delta vai exatamente contra a licao da
`[[Refutacao_P2_Range_Absoluto_2026-05-29]]` (complexificacao →
overfit).

### R4 — Pre-FOMC TQQQ/SPXL e Turn-of-Month — fora de escopo

Secao 2 do "Blueprint Tatico" cita Pre-FOMC com CAGR 8-9% em
TQQQ/SPXL e Turn-of-Month como anomalias de calendario. **NAO
fazem parte da estrategia VVG**. Sao distracoes.

O proprio CAOS ja refutou TOM internamente (commit historico
do projeto) e abandonou Pre-FOMC apos `[[Refutacao_Value_Area_Filter_2026-05-27]]`
e Decisoes anteriores. **Rejeitar**.

### R5 — arXiv 2507.22712 (Hawkes / order flow filtering) — fora

A primeira secao do "Blueprint Tatico" cita 2507.22712 sobre
filtragem estrutural do fluxo de ordens com Hawkes. Implica
que precisariamos de carimbo de tempo em milissegundos +
analise de ordens "pai" — **nao temos esses dados** (o sniffer
NT8 falhou em capturar Level 2 limpo, ja documentado no
projeto). **Rejeitar**.

### R6 — HRV / Vagal Tone / TraderSync — humanos, nao algoritmos

Secao 6 do "Blueprint Tatico" sugere medicao de Variabilidade
da Frequencia Cardiaca antes de operar. **Nao se aplica a
estrategia 100% algoritmica**. Rejeitar.

### R7 — VIX como regime gate

"Se VIX > 20, aumentar peso da Reversao". VIX **nao esta no
dataset OHLCV do MNQ** — adicionaria dependencia de feed
externo. Rejeitar para o Spec (avaliacao futura possivel se
adicionarmos um feed VIX).

### R8 — Position sizing dinamico via ATR

Secao 5 do "Blueprint Tatico" propoe formula de position sizing
proporcional ao ATR. Em principio, razoavel; **MAS** a regra
de ouro do CAOS pos-`2026-05-29-01` eh travar exposicao:
`MaxContratos=1` no hold-out, evoluir para 2 apenas com
Decisao formal. **Rejeitar a formula dinamica**, manter
posicionamento fixo travado.

## Veredito do filtro

**Substrato a incorporar (S1-S6)**: confirmacao do limite OHLCV,
resolucao do paradoxo Reversal vs Momentum (operar so em VVG+),
regime 0DTE favorece Mean-Reversion, edge +7.80 pts/trade liquido,
1-2 contratos travado, esqueleto da estrategia implementavel sem
book depth.

**Substrato a rejeitar (R1-R8)**: 8 itens de ruido, alucinacao ou
fora de escopo. Chama atencao a quantidade — Gemini misturou
varios frameworks ao responder o prompt, exatamente o tipo de
poluicao que motivou os filtros R12 + criterios complementares
da `[[Refutacao_P2_Range_Absoluto_2026-05-29]]`.

## Acoes proximas

1. **Ler arXiv 2605.11423 diretamente** para extrair:
   - Thresholds exatos (volume multiplier, gap %)
   - Stop/target magnitudes (se especificados pelo paper)
   - Janela de calibracao do paper (2021-2025?)
   - Universe (so MNQ ou outros mais?)
2. **Abrir Spec novo** `caos-vvg-late-session-reversal-mnq` com
   etapa zero de leitura do paper antes de qualquer codigo.
3. **Manter regra anti-overfit**: se o paper nao especificar
   stop/target precisos, calibrar UMA vez em janela
   2025-03 a 2025-06 (separada do WF futuro 2025-07 a 2026-05)
   e congelar em codigo.
4. **Rejeitar explicitamente** todos os elementos R1-R8 no
   Spec — incluir "fora de escopo" na secao de Non-Goals para
   resistir a tentacao de adicionar futuramente.

## Confianca

Filtro: 85.
Substrato S1-S6 com confianca individual:
- S1: 95 (confirmacao independente, ja era empiria)
- S2: 88 (resolucao logica do paradoxo, coerente com Decisao)
- S3: 75 (mecanismo plausivel mas dependente de premissas sobre
  regime 0DTE permanente)
- S4: 70 (depende de leitura direta do paper Mesfin)
- S5: 95 (convergente com `[[Decisao_2026-05-25-02]]`)
- S6: 80 (esqueleto implementavel mas pendente de leitura
  direta do paper para confirmar parametros)

Confianca media S1-S6: **84**.

Forte o bastante para abrir Spec, com etapa zero de leitura
direta do paper antes de qualquer codigo.
