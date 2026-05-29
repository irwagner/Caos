# Requirements Document

> **Identificador da feature**: `caos-vvg-late-session-reversal-mnq`
>
> **Status**: rascunho inicial (2026-05-29).
>
> **Decisões precedentes**:
> - `Decisao_2026-05-29-01` (descarte da Crabel NR7 + ORB + SF + CB)
> - `Decisao_2026-05-29-02` (triagem da shopping-list — vencedor: arXiv 2605.11423)
> - Etapa-zero NotebookLM/Gemini (`Etapa_Zero_NotebookLM_Gemini_2026-05-29`)
>
> **Paper-base**: arXiv 2605.11423 (Mesfin) — *A Validated
> Volatility-Volume-Gap Classifier for Regime Identification in MNQ
> Intraday Data*. 947 dias úteis 2021-2025, edge documentado de
> +7.80 pontos/trade líquido (T = 1.46) em dias VVG-positivos.

---

## Introduction

Esta feature implementa a estratégia **VVG Late-Session Reversal**
sobre o instrumento **MNQ** (Micro E-mini Nasdaq-100 Futures, CME),
após o descarte definitivo da estratégia anterior aprovada na
`Decisao_2026-05-25-02` (Crabel NR7 + ORB + SpreadFilter +
CircuitBreaker). O fluxo seguiu o pipeline canônico do Conselho:

1. Re-replay 28/01–26/05/2026 do MNQ 06-26 produziu PnL de
   **−USD 573,50** em 11 trades, cruzando o limiar pré-registrado
   da `Decisao_2026-05-28-01` (≤ −USD 500 → Debate de descarte).
2. `Decisao_2026-05-29-01` aprovou caminho B (re-engenharia P2),
   que foi **refutado empiricamente na fase de calibração** —
   filtro absoluto K não resiste à não-estacionariedade do MNQ.
   Fallback A foi acionado automaticamente.
3. `Decisao_2026-05-29-02` triou a `shopping-list-fontes-notebooklm-2026-05-25.md`
   contra o filtro R12 (Spec 1) e elegeu como vencedor o paper
   arXiv 2605.11423 (Mesfin), com **etapa-zero NotebookLM
   obrigatória** antes de qualquer linha de código.
4. Etapa-zero foi executada e o filtro crítico
   (`Etapa_Zero_NotebookLM_Gemini_2026-05-29`) separou substrato
   sólido (S1–S6) de contaminação LLM (R1–R8 rejeitados).

A estratégia opera sob a premissa de que **dias VVG-positivos no
MNQ exibem reversão sistemática no fim da sessão**, contrariando
o drift formador de preço da manhã. O regime de Long Gamma 0DTE
em vigor desde 2023+ (SSRN 4692190) reforça esta tese ao agir
como força gravitacional de mean-reversion intradiária.

A estratégia herda toda a infraestrutura do **Spec 3
(NinjaScript Núcleo)**: classe base `Strategy_CAOS` com defesas
de warmup já implementadas (`BarsRequiredToTrade=19320`, guard
`CurrentBar < BarsRequiredToTrade` em `EntrarInterno`,
`MfeMaeTracker`, `Trailing_3_Fases`, `Cerberus_CSharp`,
`SetStopLoss` antes de `EnterLong/EnterShort` para evitar erro
"Sell StopMarket acima do mercado").

A estratégia também **reutiliza sem modificação** os overlays
plugáveis do **Spec 4 (ORB)**: `EstrategiaSpreadFilter` e
`EstrategiaCircuitBreaker` (que sobreviveram ao descarte da
estratégia anterior porque são genéricos).

---

## Glossary

- **VVG (Volatility-Volume-Gap)**: classificador de Mesfin
  (arXiv 2605.11423) que identifica dias com choque inicial de
  volatilidade, volume de abertura e gap. Dias VVG-positivos
  são os únicos elegíveis para operar nesta estratégia.
- **RTH (Regular Trading Hours)**: pregão regular do CME para o
  MNQ, das 09:30 às 16:00 horário de Nova York (US/Eastern).
- **Drift direcional**: variação de preço entre o open do RTH
  (09:30) e o close de uma barra de referência intraday.
- **Late-session reversal**: trade contra-tendência iniciado nos
  últimos minutos do RTH, baseado na premissa de que o drift
  matutino se exaure por profit-taking institucional.
- **EOD (End-of-Day)**: encerramento do pregão. Topstep penaliza
  contas que carregam posição além de 15:50 EST (limite interno
  para evitar problemas de liquidação noturna).
- **Topstep TDD (Trailing Drawdown)**: limite de perda dinâmico
  de USD 2.500 da Topstep, calculado a cada EOD com base no
  saldo de pico da conta.
- **Edge bruto OHLCV**: ganho médio por trade antes da fricção,
  derivado puramente de open/high/low/close/volume. Documentado
  pelo Paper 1 (arXiv 2605.04004) entre 0.07 e 1.5 pts/trade no
  MNQ — abaixo do limiar de 5 pts exigido pela regra-de-ouro do
  CAOS.
- **Edge líquido VVG**: ganho médio por trade em dias
  VVG-positivos após custos transacionais, documentado pelo
  Paper 2 (Mesfin) em **+7.80 pontos** com T = 1.46.
- **Janela de calibração separada**: período usado para fixar
  parâmetros, **disjunto** da janela de WF e da janela de
  hold-out. Para esta feature: 2025-03-17 a 2025-06-30 (dataset
  `_concat_minute_last/01_MNQ_06-25.csv`).

---

## Requirements

### Requirement 1: Classificador VVG

**User Story:**: Como sistema operacional do robô CAOS, eu preciso
classificar cada dia útil do MNQ como VVG-positivo ou
VVG-negativo, para que apenas dias com choque inicial de
volatilidade/volume/gap sejam elegíveis para o trade de reversal
late-session.

#### Acceptance Criteria

1. WHEN o classificador VVG recebe a primeira meia hora do RTH
   (09:30–10:00 EST) de um dia D, THE classificador SHALL calcular
   três features:
   - `volume_morning` = soma do volume de barras de minuto no
     intervalo \[09:30, 10:00\) EST
   - `gap_pct` = `abs(open(09:30) − close(D−1)) / close(D−1)`
   - `volume_baseline` = média móvel de N dias do volume da
     primeira hora (09:30–10:30 EST), calculada com `shift(1)`
     para evitar look-ahead

2. WHEN as três features estão disponíveis para o dia D, THE
   classificador SHALL retornar `vvg_positivo = True` se e
   somente se AMBAS as condições abaixo são verdadeiras:
   - `volume_morning ≥ MULTIPLICADOR_VOLUME × volume_baseline`
   - `gap_pct ≥ THRESHOLD_GAP`

3. THE valores de `MULTIPLICADOR_VOLUME`, `THRESHOLD_GAP` e
   `N_DIAS_BASELINE` SHALL ser **extraídos diretamente do paper
   arXiv 2605.11423 (Mesfin)** durante a fase de design. Se o
   paper não especificar valores precisos, o design SHALL
   calibrá-los UMA vez em janela 2025-03-17 a 2025-06-30
   (dataset `01_MNQ_06-25.csv`) e congelá-los em código como
   constantes nomeadas.

4. WHERE `volume_baseline` ainda não tem N dias completos de
   histórico (warmup incompleto), THE classificador SHALL
   retornar `vvg_positivo = False` (nunca emitir sinal sob
   incerteza estatística).

5. THE classificador SHALL operar exclusivamente sobre dados
   OHLCV de minuto (sem book depth, sem Level 2, sem feed
   externo de VIX), respeitando a restrição R5 da
   `Etapa_Zero_NotebookLM_Gemini_2026-05-29` (item R7
   rejeitado).

6. THE classificador SHALL ter **paridade trade-a-trade exata**
   entre Python (`caos/walk_forward/estrategias/vvg_classifier.py`)
   e C# (`04_CODIGO/ninjascript/EstrategiaVvgClassifierLogica.cs`),
   verificada por teste automatizado.

### Requirement 2: Estratégia operável (Late-Session Reversal)

**User Story:**: Como sistema operacional, eu preciso emitir um
único trade contra o drift direcional do dia em dias
VVG-positivos, com stop e target programáticos e encerramento
forçado antes do EOD da Topstep, para capturar a reversão
late-session documentada por Mesfin sem violar o limite de
trailing drawdown.

#### Acceptance Criteria

1. WHEN o dia D é VVG-positivo (R1) AND o relógio do mercado
   atinge `HORA_ENTRADA_EST` (default 14:30 EST, a confirmar no
   paper Mesfin), THE estratégia SHALL calcular o drift
   direcional:
   - `drift = close(HORA_ENTRADA_EST) − open(09:30 EST)`
   - `drift_dir = +1 se drift > 0, −1 se drift ≤ 0`

2. WHEN drift_dir é calculado, THE estratégia SHALL emitir um
   trade na direção **oposta** (`signal = −drift_dir`):
   - `drift_dir = +1` → entrada SHORT
   - `drift_dir = −1` → entrada LONG

3. THE entrada SHALL ser via wrapper `EntrarLong` ou
   `EntrarShort` da classe base `Strategy_CAOS`, que roteia por
   `Cerberus_CSharp` antes de despachar a ordem real (nunca
   chamar `EnterLong/EnterShort` diretamente).

4. THE stop loss e take profit SHALL ser declarados **antes** do
   despacho da ordem (padrão NT8 estabelecido em `Strategy.cs`,
   commit `9ce39dd`), usando `SetStopLoss` e `SetProfitTarget`
   com `CalculationMode.Price`. Magnitudes:
   - `STOP_PONTOS` e `TARGET_PONTOS` SHALL ser extraídos do
     paper Mesfin OU calibrados UMA vez na janela
     2025-03-17 a 2025-06-30. Os valores 20 pts (stop) e 40 pts
     (target) sugeridos pelo Gemini Pro (S6 da etapa-zero)
     **NÃO devem ser aceitos cegamente** — exigem confirmação
     no paper original (R1 do filtro crítico).

5. WHEN o relógio atinge `HORA_ENCERRAMENTO_EST` (default 15:50
   EST), AND a posição ainda está aberta, THE estratégia SHALL
   forçar encerramento via `SairLong` ou `SairShort`, mesmo que
   stop e target não tenham sido atingidos. Esta cláusula
   protege o limite EOD da Topstep.

6. THE estratégia SHALL emitir **no máximo um trade por dia**.
   Se um trade for fechado antes de `HORA_ENCERRAMENTO_EST`
   (por stop ou target), nenhum novo trade é aberto no mesmo
   dia.

7. WHEN `State == State.Historical` (backtest), THE estratégia
   SHALL atualizar a contabilidade interna (Trailing,
   MfeMaeTracker) mas **NÃO enviar ordem real ao broker**,
   conforme R2.3 do Spec 3 e o guard
   `CurrentBar < BarsRequiredToTrade` já presente em
   `EntrarInterno`.

### Requirement 3: Composição com overlays existentes

**User Story:**: Como mantenedor do sistema, eu preciso reutilizar
sem modificação os overlays `SpreadFilter` e `CircuitBreaker` do
Spec 4 (ORB), que sobreviveram ao descarte da estratégia
anterior porque são genéricos a qualquer plugin de entrada.

#### Acceptance Criteria

1. THE estratégia VVG Late-Session Reversal SHALL ser
   composável com `EstrategiaSpreadFilter` (mediana_diaria,
   warmup=30 minutos, running_median=True), na MESMA
   configuração aprovada pela `Decisao_2026-05-25-02`. Spread
   alto bloqueia o trade de 14:30 (mesmo se VVG-positivo).

2. THE estratégia SHALL ser composável com
   `EstrategiaCircuitBreaker` (diario=−250 pts, semanal=−750
   pts, janela=−1000 pts), na MESMA configuração aprovada pela
   `Decisao_2026-05-25-02`.

3. THE composição final no Walk-Forward Python SHALL ser:
   ```
   EstrategiaCircuitBreaker(
       EstrategiaSpreadFilter(
           EstrategiaVvgLateSessionReversal(),
           modo="mediana_diaria",
           warmup=30,
           running_median=True
       ),
       diario=-250 pts, semanal=-750 pts, janela=-1000 pts
   )
   ```

4. NEITHER `EstrategiaSpreadFilter` NOR `EstrategiaCircuitBreaker`
   SHALL ser modificada por esta feature. Qualquer modificação
   nelas exige Debate separado (Gatilho G1).

### Requirement 4: Position sizing

**User Story:**: Como sistema operacional sob conta financiada
Topstep, eu preciso operar com posição **fixa e travada** para
sobreviver à alta curtose documentada do paper Mesfin.

#### Acceptance Criteria

1. THE estratégia SHALL operar com `MaxContratos = 1` no
   hold-out inicial. O parâmetro `MaxContratos` continua sendo
   um `[NinjaScriptProperty]` da classe base `Strategy_CAOS`
   (já implementado), mas o valor default desta estratégia
   SHALL ser 1.

2. THE estratégia SHALL **NÃO implementar** position sizing
   dinâmico via fórmula ATR (item R8 da etapa-zero rejeitado).
   Qualquer evolução para 2 contratos exige Decisão formal
   após hold-out passar todos os critérios.

3. THE risco por trade em USD SHALL ser calculado pelo método
   `CalcularRiscoUSD` já existente em `Strategy.cs`, e
   autorizado pelo `Cerberus_CSharp` antes de cada ordem
   (R3.3 do Spec 3).

### Requirement 5: Espelho C# em NinjaScript 8

**User Story:**: Como mantenedor da paridade Python↔C#, eu
preciso de um espelho C# da estratégia que opere no NT8 com a
mesma lógica do Python, herdando da classe base `Strategy_CAOS`.

#### Acceptance Criteria

1. THE espelho C# SHALL consistir em dois arquivos novos em
   `04_CODIGO/ninjascript/`:
   - `EstrategiaVvgClassifierLogica.cs` — classificador VVG puro
     (sem dependência de NT8, testável isoladamente)
   - `StrategyVvgLateSessionReversal.cs` — classe que herda de
     `Strategy_CAOS` e implementa `OnNovaBarra` para acionar a
     entrada/saída

2. THE espelho C# SHALL usar **apenas APIs NinjaScript já
   autorizadas** pelo steering `ninjascript-api.md`. Qualquer
   nova API exige Decisão formal antes do código ser commitado.

3. THE espelho C# SHALL reutilizar:
   - `BarsRequiredToTrade = 19320` (defesa de warmup, commit
     `a281e47`)
   - Guard `CurrentBar < BarsRequiredToTrade` em
     `EntrarInterno` (commit `17450e3`)
   - `RealtimeErrorHandling.IgnoreAllErrors` e
     `StopTargetHandling.PerEntryExecution` (suprime popups
     benignos)
   - Padrão `SetStopLoss + SetProfitTarget` antes de
     `EnterLong/EnterShort` (commit `9ce39dd`)
   - Force-close defensivo de `MfeMae+Trailing` antes de
     reabrir trade (commit `240c089`)

4. THE espelho C# SHALL ser sincronizado com a sandbox NT8
   (`%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\caos\`)
   via `04_CODIGO/ninjascript/sincronizar.bat`. Toda escrita
   na sandbox EXIGE espelho versionado em
   `04_CODIGO/ninjascript/` (steering `protocolo-debate-no-chat`,
   freio humano #1).

5. THE classifier C# SHALL acessar a série diária para obter
   `close(D-1)` via `Bars[1].Close` na barra de mudança de dia
   (sem `AddDataSeries` adicional, mantendo o setup atual com
   série primária de 1 minuto). Caso o paper Mesfin exija
   resolução diária separada, o design avalia adicionar
   `AddDataSeries(BarsPeriodType.Day, 1)` e atualizar
   `ninjascript-api.md`.

### Requirement 6: Paridade Python↔C# trade-a-trade

**User Story:**: Como auditoria do projeto, eu preciso garantir
que o backtest Python e o replay NT8 produzem os mesmos trades
nos mesmos dias com o mesmo PnL, dentro de uma tolerância
documentada.

#### Acceptance Criteria

1. THE paridade Python↔C# SHALL ser verificada por script
   automatizado em `scripts/auditar_paridade_vvg_<DATA>.py`
   após cada release do código.

2. THE script de auditoria SHALL comparar, dia a dia VVG-positivo:
   - Direção do trade (LONG/SHORT) — DEVE ser idêntica
   - Timestamp de entrada (resolução: minuto) — DEVE ser idêntico
   - Timestamp de saída — tolerância de 1 minuto
   - PnL por trade — tolerância de 5% (limiar pré-registrado)

3. WHEN qualquer divergência > 5% é detectada, THE auditoria
   SHALL falhar e abrir Debate Auto com gatilho G5 (regressão
   de paridade). Estratégia volta a estar **suspensa** até o
   bug ser identificado e corrigido.

4. THE script de auditoria SHALL reportar também:
   - Número de dias VVG-positivos identificados em cada
     plataforma (DEVE ser idêntico)
   - Soma de PnL no período (tolerância de 5%)

### Requirement 7: Walk-Forward de validação

**User Story:**: Como Conselho do projeto, eu preciso validar a
estratégia em janela longa **antes** de qualquer hold-out real,
respeitando o pipeline canônico do Spec 2.

#### Acceptance Criteria

1. THE WF longo de validação SHALL usar a configuração 60+10
   anchored sobre o período 2025-07-01 a 2026-05-15 (mesma
   janela usada pela estratégia anterior na
   `Decisao_2026-05-25-02`, para comparação direta).

2. THE WF SHALL ser executado via CLI `caos walk-forward run`
   já implementado no Spec 2.

3. THE critério quantitativo de sucesso SHALL ser:
   - **Sharpe mediana ≥ 1.0** sobre os cortes do WF
   - **Calmar mediana ≥ 1.5** sobre os cortes do WF
   - **PnL total > 0** com 1 contrato MNQ

4. WHEN qualquer critério acima falha, THE estratégia SHALL ser
   arquivada em `02_ESTRATEGIAS/mortas/` automaticamente,
   sem novo Debate (cláusula de fallback A pré-registrada).

5. WHEN todos os critérios acima são satisfeitos, THE pipeline
   SHALL emitir uma **confirmação explícita de aprovação do WF**:
   - Gravar nota Zettel
     `Aprovacao_WF_VVG_Late_Session_<DATA>.md` em
     `CAOS_Zettelkasten/Walk_Forwards/` registrando os números
     observados (Sharpe mediana, Calmar mediana, PnL total,
     número de trades, número de dias VVG-positivos)
   - Atualizar o `STATE-OF-RESEARCH` corrente apontando que a
     estratégia avançou para a fase R8 (replay NT8)
   - Os números registrados servem como **baseline** que o
     replay NT8 (R8) deve respeitar dentro de 30% de desvio
   - **NÃO** aplicar tag `caos-frozen-*` neste momento — a tag
     só vem após R7 + R8 ambos aprovados (regra geral do
     projeto, R8.6 do Spec 1)

6. THE relatório do WF SHALL ser gravado em
   `05_BACKTEST/walk_forward/relatorios/AAAA-MM-DD-NN-vvg-late-session/`
   com `resultado.json`, `manifest_hash`, e nota Zettel de
   conclusão.

### Requirement 8: Replay NT8 de validação

**User Story:**: Como Conselho, eu preciso validar a estratégia
em ambiente NT8 real (Sim101) com dados que **não entraram** no
WF, para detectar bugs de paridade ou de execução antes de
qualquer dinheiro real.

#### Acceptance Criteria

1. THE replay NT8 SHALL ser executado em Sim101 sobre dados de
   2026-06+ (período que NÃO entrou no WF longo da R7).

2. THE replay SHALL durar no mínimo **30 dias úteis** corridos
   de mercado.

3. THE critério quantitativo de sucesso SHALL ser:
   - **PnL ≥ −USD 100** em 30 dias úteis com 1 contrato MNQ
   - **Zero erros** do tipo "MfeMaeTracker já tem trade aberto"
     (regressão da `Decisao_2026-05-28-01`)
   - **Zero erros** de stop market acima/abaixo do mercado

4. WHEN o critério de PnL falha, THE estratégia SHALL ser
   arquivada (cláusula de fallback A pré-registrada).

5. THE replay SHALL ser configurado com **Days to load ≥ 44**
   no chart NT8, para satisfazer o `BarsRequiredToTrade=19320`
   (instrução já documentada em
   `04_CODIGO/ninjascript/README_INSTALACAO_HOLDOUT.md`,
   Passo 3.5).

### Requirement 9: Critérios de descarte automático (fallback A)

**User Story:**: Como Conselho, eu preciso de critérios
quantitativos pré-registrados que disparem descarte automático
da estratégia sem necessidade de novo Debate, para evitar viés
de confirmação do experimentador.

#### Acceptance Criteria

1. THE estratégia SHALL ser **arquivada automaticamente** em
   `02_ESTRATEGIAS/mortas/` se qualquer um dos critérios abaixo
   falhar:
   - R7.3: Sharpe mediana WF < 1.0 OR Calmar mediana WF < 1.5
   - R8.3: PnL replay < −USD 100 em 30 dias úteis
   - R6.2: Paridade Python↔C# > 5% de divergência por trade

2. WHEN o arquivamento ocorre, THE Kiro_Brain SHALL:
   - Criar nota Zettel `Refutacao_VVG_Late_Session_<DATA>.md`
     em `CAOS_Zettelkasten/Decisoes_do_Conselho/`
   - Atualizar o `STATE-OF-RESEARCH` corrente
   - Mover qualquer tag `caos-frozen-vvg-*` aplicada para
     status `revogada`

3. NO novo Debate SHALL ser exigido para ativar este fallback.
   O fallback é **automático**.

### Requirement 10: Não-objetivos (Non-Goals) explícitos

**User Story:**: Como mantenedor do projeto, eu preciso documentar
explicitamente o que **NÃO** será implementado nesta feature,
para resistir à tentação de complexificação que matou estratégias
anteriores (lição de `Refutacao_P2_Range_Absoluto_2026-05-29` e
`Refutacao_Value_Area_Filter_2026-05-27`).

#### Acceptance Criteria

1. THE seguinte lista é **rejeitada explicitamente** pelo filtro
   crítico R1–R8 da etapa-zero NotebookLM/Gemini e NÃO faz
   parte do escopo desta feature:
   - HMM (Hidden Markov Model) para classificação de regime
   - VWAP, Cumulative Delta, Whale Trades
   - Order Book Imbalance, processos de Hawkes (não temos book
     depth confiável; sniffer NT8 falhou em capturas anteriores)
   - Pre-FOMC drift (refutado em `Decisao_2026-05-23-03`)
   - Turn-of-the-Month (refutado internamente)
   - Filtros baseados em VIX (não está no dataset OHLCV do MNQ)
   - HRV / Vagal Tone / TraderSync (são para humanos, não
     algoritmos)
   - Position sizing dinâmico via fórmula ATR (manter fixo)

2. THE seguinte lista de **parâmetros** NÃO pode ser introduzida
   como otimizável (regra anti-overfit do projeto):
   - Multiplicador de volume (vem do paper OU calibrado UMA vez)
   - Threshold de gap (vem do paper OU calibrado UMA vez)
   - Stop e target em pontos (vem do paper OU calibrados UMA vez)
   - Hora de entrada e hora de encerramento (vem do paper)
   - Janela do baseline de volume N (vem do paper)

3. THE adição de qualquer item das listas acima exige Debate
   separado com Decisão formal (`aprovado_walk_forward=true`).
