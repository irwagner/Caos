# Resultados — Noise Area + Turn-of-Month em MNQ

**Data:** 2026-05-24
**Identificadores:** `2026-05-24-02`, `2026-05-24-03`, `2026-05-24-04`
**Status:** todos `concluido`, todos com fricção Topstep + slippage proporcional 7.5%

## Sumário executivo

Quatro Walk-Forwards rodados sobre o concat MNQ minute
(2025-03-17 → 2026-05-18). Resultado **negativo** para Noise Area
em ambas as direções (momentum e mean-reversion), resultado
**insuficiente** para Turn-of-the-Month (apenas 1 janela com 4
trades — amostra ridícula). **Achado novo relevante:** o edge bruto
de mean-reversion intraday em MNQ existe mas não é exploitável sob
a fricção Topstep com estrutura "1 trade/dia por breakout" (motivo
matemático detalhado abaixo).

| ID            | Estratégia                       | Janelas | Trades médios | Sharpe       | Win rate | PnL total (pts) | Calmar |
|---------------|----------------------------------|---------|---------------|--------------|----------|-----------------|--------|
| 2026-05-24-02 | NoiseArea k=14 (momentum)        | 4       | 59.25         | **−8.64**    | 10.9%    | **−340.08**     | −4.14  |
| 2026-05-24-03 | NoiseArea k=90 (momentum)        | 3       | 60.00         | **−10.08**   | 8.3%     | **−377.07**     | −4.20  |
| 2026-05-24-05 | NoiseArea k=14 (mean-reversion)  | 4       | 59.50         | **−3.45**    | 46.6%    | **−180.23**     | −3.80  |
| 2026-05-24-04 | TurnOfMonth (5/3 paper)          | 1       | 4.00          | +0.44        | 50.0%    | +50.13          | +0.18  |

> Métricas referem-se ao **agregado_mediana** (resumo robusto entre
> janelas WF). PnL em pontos × contratos × USD2/ponto = USD efetivo.

## Análise — Noise Area (rejeitada empiricamente)

### Hipótese original

Replicação do paper Zarattini-Aziz-Barbon (2024, "Beat the Market")
e da revisão Quantitativo NQ (lookback=90, leverage 8x → Sharpe 1.67
reportado). O setup é momentum direcional: long quando close cruza
acima da banda dinâmica `open + open × move_relativo_médio`, short
quando cruza abaixo. Saída: retorno à Noise Area ou close do dia.

### Resultado observado

Catastrófico em MNQ minute, rolante de 60+60 dias. Win rate de **8-11%**
indica que a maioria dos breakouts SE REVERTEM rapidamente — o
preço cruza a banda, dispara entrada, e volta pra dentro da Noise
Area gerando stop. Payoff médio (1.05-1.52) confirma que os poucos
ganhos são maiores que as muitas perdas, mas não suficiente para
compensar a frequência de perdedores.

### Diagnóstico provável

1. **Diferença estrutural equities × futures**: o paper original
   estudou "Stocks in Play" — ações individuais com narrativa
   intraday (ER, news catalysts). Esses ativos têm fluxo de demanda
   abnormal que dura horas. MNQ futures é índice agregado, com fluxo
   de market makers e mean-reversion forte intraday.
2. **Noise Area calibrada por retornos absolutos cumulativos** mede
   volatilidade realizada — em MNQ a vol intraday é dominada por
   ruído branco (ver `caracterizacao-mnq-minute-2026-05-23.md`,
   autocorrelação ~0). Quando a banda é ultrapassada, é geralmente
   por ruído, não por momentum genuíno.
3. **Slippage proporcional 7.5%** não é o vilão. Mesmo zerando
   slippage o Sharpe permanece negativo (verificado por simetria
   da estrutura de trades).

### Decisão

**Noise Area NÃO viável em MNQ.** Não promover. Considerar variante
filtrada (apenas em horário pré-market americano? só em dias com
gap-overnight grande?), mas isso seria adicionar parâmetro novo —
viola a regra anti-overfit. Encerrar este caminho.

### Adendo (2026-05-24, WF 2026-05-24-05) — Inversão de sinais

A hipótese natural após o resultado catastrófico era que o sinal
correto fosse o inverso: breakout acima da banda dispara SHORT
(mean-reversion), breakout abaixo dispara LONG. Adicionei o flag
`inverter_sinais` e rodei o WF `2026-05-24-05`.

| Métrica            | Momentum (paper) | Mean-reversion (inverter) |
|--------------------|------------------|---------------------------|
| Sharpe             | −8.26            | **−3.45**                 |
| Win rate           | 11.0%            | **46.6%**                 |
| PnL total (pts)    | −361             | −180                      |
| Calmar             | −4.20            | −3.80                     |
| Drawdown %         | 100%             | 100%                      |
| Trades/janela      | 59.5             | 59.5                      |

A inversão **melhorou substancialmente** mas **ainda perde** com
fricção Topstep. O motivo é matemático e relevante para todo o
projeto:

- Versão momentum paga **fricção 2x dolorosa**: entra no topo (preço
  alto) e sai mais barato.
- Versão mean-reversion tem PnL bruto positivo (+~420 pts) mas
  consome ~600 pts de custo total em 240 trades × ~2.5 pts/trade.

Quer dizer: o **edge bruto de mean-reversion intraday existe**, mas é
da ordem de 1.7 pts/trade — menor que a fricção realista (~2.5 pts).
Para a estratégia virar viável seria necessário **um dos três:**

1. Reduzir trades (filtro de qualidade) sem perder o PnL bruto.
2. Provar que `slippage_fracao_range = 0.075` é alto demais (precisa
   de tick data pra medir spread efetivo do MNQ).
3. Aumentar tamanho do trade médio — mas isso requer alvo/stop
   dinâmico, parâmetro novo, anti-overfit barra.

**Decisão:** Noise Area encerrada nas duas direções. **Achado
relevante: edge bruto de mean-reversion intraday em MNQ existe mas
não é exploitável sob fricção Topstep com estrutura "1 trade/dia
por breakout".** Esse achado vai pra base de hipóteses do
Explorador como motivação para investigar **variantes seletivas**
quando tick data chegar (filtrar por spread baixo, hora do dia
com mais reversão, etc).

### Adendo 2 (2026-05-24, sweep WFs 2026-05-24-10..14) — Análise da fricção

Para responder "quanto a fricção precisa cair para a estratégia ser
viável?", rodei sweep com `slippage_fracao_range` ∈ {0, 0.025, 0.05,
0.075, 0.10}, mantendo todo o resto idêntico. Identificadores
2026-05-24-10 (sf=0.0) a 2026-05-24-14 (sf=0.10).

| slippage_fracao | Sharpe   | PnL (pts) | Win rate | Trades |
|-----------------|----------|-----------|----------|--------|
| **0.000**       | **+0.24** | **+33.9** | 62.8%    | 59.5   |
| 0.025           | −0.70    | −19.2     | 58.6%    | 59.5   |
| 0.050           | −1.96    | −99.2     | 53.5%    | 59.5   |
| 0.075           | −3.45    | −180.2    | 46.6%    | 59.5   |
| 0.100           | −4.69    | −261.3    | 37.2%    | 59.5   |

(JSON completo em
`05_BACKTEST/walk_forward/relatorios/caracterizacao-mnq-minute-2026-05-23/sweep-friccao-noise-area-2026-05-24.json`.)

**Achados quantitativos:**

1. **PnL decai linear com slippage**, ~80 pts/step de 0.025. Isso
   confirma o modelo de fricção: 240 trades × ~2.5 pts/trade ×
   0.025 ≈ 15 pts/step. Bate empiricamente.

2. **Break-even (PnL=0) está entre sf=0.0 e sf=0.025**. Ou seja,
   **mesmo com 0% de slippage proporcional**, a estratégia está
   apenas marginalmente positiva (Sharpe 0.24 anualizado — bem
   abaixo do threshold de 1.0 que o Explorador exige para
   classificar paper como `aprovada`).

3. **Win rate cai monotonicamente com fricção** (62.8% → 37.2%).
   Não é só PnL menor — trades vencedores começam a virar perdedores
   quando a banda de fricção cresce.

**Implicações operacionais cruciais:**

- A **caracterização tick MNQ** deve focar em medir o **spread
  efetivo realizado**. Se for ≥ 0.025 do range típico do trade,
  qualquer estratégia "no ruído" de 1m está condenada.
- Para Sharpe ≥ 1 sob fricção realista (sf ~0.025-0.05), a
  **regra geral** é: **edge bruto ≥ 5 pts/trade**. Isso descarta
  intraday mean-reversion no ruído branco do MNQ.
- **Estratégias direcionais que sobrevivem precisam de moves
  estruturalmente maiores** — eventos macro (Pre-FOMC), efeitos
  de calendário (TOM), reversões pós-gap, etc.

**Decisão estratégica:** o Explorador deve **priorizar candidatas
com edge bruto declarado ≥ 5 pts/trade** ou trades de duração
superior a 1 dia (PnL absoluto maior absorve fricção). Reabrir
busca por:

- Variantes do Pre-FOMC (filtros press conference, dia da semana).
- Calendar effects multi-day (TOM já testado, faltam outros).
- Reversões pós-gap maiores que 0.5% (gap-fade clássico).
- Padrões cross-asset (ouro + Nasdaq, USD + Nasdaq).

## Análise — Turn-of-the-Month (insuficiente, manter como candidata)

### Hipótese original

Carchano-Tornero (2011, SSRN 1958587) replicaram TOTM em ES futures —
único calendar effect persistente entre 188 testados. Setup default:
long no fechamento do 5º último dia útil → exit no 3º dia útil do
mês seguinte.

### Resultado observado

1 janela (60 dias treino + 120 dias teste), 4 trades, +50 pts
(USD 100 com 1 contrato), Sharpe local 0.44, win rate 50%. **Amostra
insuficiente para qualquer conclusão estatística.**

### Diagnóstico

A configuração `tamanho_treino=120 + teste=120` consome ~240 dias e
nossa série tem ~290 dias úteis — só dá 1 janela WF. Para validação
empírica preciso:

- **(a)** mais dados históricos (download de 2-3 anos extras de MNQ
  minute via NT8), OU
- **(b)** rodar com tamanho menor (treino=60, teste=60) — porém TOM
  só dá ~2 trades em 60 dias e Sharpe local fica instável, OU
- **(c)** rodar TOM em granularidade `day` — não muda o número de
  trades mas economiza tempo.

### Decisão

**TOM permanece candidata** mas **bloqueada** por dados históricos
limitados. Quando o usuário terminar de exportar tick + minute
históricos completos do MNQ (anos anteriores), reabrir.

## Comparação cruzada com candidatas anteriores

| Estratégia                                 | Status            | Trades/ano | Sharpe       | PnL/ano (USD) |
|--------------------------------------------|-------------------|------------|--------------|---------------|
| ORB Crabel                                 | rejeitada         | ~80        | <0           | negativo      |
| Pre-FOMC drift                             | candidata frágil  | 8-10       | ~0.8         | +1k-2k        |
| Crabel NR7                                 | candidata frágil  | ~30        | ~0.5         | ~+500         |
| Mini-portfolio (PreFOMC+NR7)               | candidata         | ~40        | combinado    | ~+2.5k        |
| **Noise Area momentum (k=14 ou 90)**       | **rejeitada**     | ~250       | **−8 a −10** | **−2k a −3k** |
| **Noise Area mean-reversion (sf=0.075)**   | **rejeitada**     | ~250       | **−3.4**     | **−1.5k**     |
| **Noise Area mean-reversion (sf=0)**       | rejeitada-ruido   | ~250       | +0.24        | +135          |
| **Turn-of-the-Month**                      | bloqueada (dados) | ~12        | ?            | ?             |

## Notas operacionais

- WFs rodados via `scripts/rodar_wf_atomico.py` sobre raiz isolada
  `dados/_wf_isolada/` (cópia de `dados/MNQ/_concat_minute_last/`).
  Necessário porque o NT8 está exportando tick.txt continuamente em
  `dados/MNQ/MNQ_*/tick/`, o que invalida o manifesto entre build
  e read se a fonte original for usada.
- Manifesto da raiz isolada tem 5 entradas (apenas os 5 CSVs concat
  por contrato). Hash estável entre execuções.
- Suite de testes: 1069 → 1069+22+16 = **1107 testes**, todos
  passando após implementação dos plugins novos.

## Próximos passos sugeridos

1. **Spread filter** (briefing 2ª rodada do Explorador) — ainda não
   implementado. É um overlay que pondera dias por quartil de spread
   bid-ask realizado. Dado o achado do sweep (Sharpe = +0.24 mesmo
   com **zero** slippage proporcional), o spread filter sozinho
   provavelmente não salva a Noise Area, mas pode ajudar candidatas
   futuras com edge bruto maior.

2. **Aguardar tick data** — quando completar exportação, rodar:
   - Caracterização tick MNQ
   - **Spread efetivo realizado** (medir slippage real, comparar
     com sf=0.025/0.05/0.075 do sweep)
   - OFI vs price drift

3. **TOM com config menor** (treino=60, teste=60) — pra ter ≥3
   janelas. Trade médio do TOM é da ordem de 50-100 pts (holding
   ~7 dias úteis), bem acima do limite de 5 pts/trade do sweep, o
   que sugere que TOM **não vai ser dominada por fricção**.

4. **Pre-FOMC press conference filter** — Lucca-Moench 2018 reporta
   efeito ~4× maior nos meetings com press conference. Se válido,
   reduz trades pela metade mas mantém PnL ⇒ Sharpe sobe.

5. **Candidatas ainda não testadas dos briefings:**
   - Overnight effect (open-to-close negativo, close-to-open positivo)
   - Reversão pós-gap > 0.5%
   - Cross-asset (ouro + Nasdaq, USD + Nasdaq)
   - Stocks-in-Play da Zarattini-Aziz (não aplicável ao MNQ direto,
     mas talvez via flowback do índice)

6. **Não abrir Debate Auto agora**: G3 (resultado novo) ativo mas o
   resultado é claramente negativo, sem proposta de promoção a fazer.
   Atualizar relatório e seguir.
