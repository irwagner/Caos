# Relatório CAOS: Síntese Quantitativa MNQ

**Origem:** Resposta do Gemini Pro (NotebookLM) à etapa-zero da
Decisão `2026-05-29-02`.
**Data:** 2026-05-29
**Status:** Documento externo, **não autoritativo**.
**Filtro crítico aplicado em:** `[[Etapa_Zero_NotebookLM_Gemini_2026-05-29]]`

> **Limites Estruturais, Hedging Options (0DTE) e Reversões
> Intradiárias sob Fricção Topstep**
>
> Este documento consolida o conhecimento tático e teórico dos três
> papers requisitados para adequar a infraestrutura de trading do
> Projeto CAOS (em Python e NinjaTrader 8). O foco absoluto é a
> viabilidade matemática em contas financiadas (Topstep, Trailing
> Drawdown de USD 2500).

---

## 1. O Limite do OHLCV e Edges ≥ 5 pts/trade (Pós-Fricção)

O **Paper 1 (arXiv:2605.04004)** documenta o "limite estrutural"
de sinais baseados apenas em OHLCV no Micro E-Mini Nasdaq 100
(MNQ). Ele crava que, na média incondicional, o *edge* bruto
gravita entre **0.07 e 1.5 pontos por trade**. Ao aplicarmos a
fricção de varejo (comissões de ~$1.14 RT no NT8 e *slippage*
agressivo intrínseco aos breakouts), esse *edge* estrutural se
desintegra. Isso invalida sistemas de alta frequência diretos e
sem filtros baseados exclusivamente em preço/volume.

Entretanto, o **Paper 2 (arXiv:2605.11423, Mesfin)** isola uma
anomalia condicional: dias classificados positivamente pelo
modelo **Volatility-Volume-Gap (VVG)**. Nesses dias específicos,
o modelo estatístico de reversão no final da sessão alcançou uma
média líquida documentada de **+7.80 pontos por trade** (T = 1.46),
superando com margem a linha de corte de 5 pontos exigida (mesmo
após custos transacionais).

### Gestão de Risco Topstep (Trailing DD de USD 2500)

O Paper 2 relata que, apesar da média de +7.80 pontos, o modelo
*falha em estabilidade anual para os padrões rigorosos de fundos
institucionais*. Isso significa que ele sofre de alta curtose —
haverá semanas com sequências de drawdowns severos. Como a Topstep
usa um Trailing Drawdown de fim de dia (EOD) estrito de $2500, o
edge de +7.80 pontos ($15.60 por contrato) paga confortavelmente
o slippage, mas a estratégia só sobreviverá se o *position sizing*
for blindado (travado em 1 a no máximo 2 contratos de MNQ).
Alavancar para buscar a aprovação rápida resultará matematicamente
na ruptura do limite da conta durante o regime de baixa
performance.

---

## 2. O Paradoxo do Fim de Pregão: Reversão vs Momentum

Existe um aparente conflito na microestrutura abordada por dois
dos estudos no que tange aos últimos 30-60 minutos de pregão:

- **Paper 3 (SSRN 3760365 — Baltussen et al.):** Demonstra que a
  última meia hora exibe *Momentum* (continuação da tendência
  prévia do dia). A tese é de que a Demanda por Hedging de opções
  força os Market Makers (MMs) a comprar mercados que estão
  subindo, retroalimentando a tendência.
- **Paper 2 (arXiv:2605.11423 — Mesfin):** Afirma que, em dias com
  choque de VVG, há uma *Reversão sistemática (Late-Session
  Reversal)*, contrariando o drift formador de preço da manhã.

### Qual está certo no regime atual?

Ambos descrevem anomalias reais, porém aplicam-se a **estados e
filtros de liquidez diametralmente opostos**. O estudo de
Baltussen avaliou o comportamento *incondicional e sistêmico* de
índices amplos (S&P/NASDAQ), enquanto Mesfin filtrou dias
*condicionais extremos* (Gap Direcional + Volume de Abertura)
unicamente no MNQ.

Em dias com choque de volume inicial (VVG positivo), o mercado
sofre de exaustão; os provedores de liquidez se retraem e os
institucionais de curto prazo que capturaram o drift da manhã
liquidam suas posições antes do fechamento (profit-taking
agressivo), forçando a reversão. Para o seu foco no MNQ (um
instrumento derivativo altamente especulativo com beta alavancado),
o **Paper 2 é o modelo correto para ser operado quando os filtros
VVG estiverem ativos**. Nos dias não-classificados, a mecânica de
hedging incondicional de Baltussen assume a preeminência.

---

## 3. O Efeito do Regime "Gamma 0DTE" no Delta-Hedging

O mercado atual (2026) sofreu uma mudança drástica. O advento das
opções de curtíssimo prazo **0DTE (Zero Days to Expiration)**, que
hoje engolem mais da metade de todo o volume operado de
derivativos do índice, reescreve a premissa de Baltussen.

### Gamma Exposure (GEX) Intradiário

O momentum documentado por Baltussen exige fundamentalmente que
os dealers (Market Makers) estejam *Short Gamma* (situação em que
o delta-hedging obriga a comprar as altas e vender as baixas,
retroalimentando explosões de preço). No entanto, sob o influxo
massivo de venda de opções 0DTE pelo varejo (e MMs como
contraparte), os dealers passam grandes blocos de tempo *Long
Gamma* no intraday.

Quando o book institucional está longo em Gamma, o hedge inverte:
eles vendem nas altas e compram nas quedas para zerar o risco de
delta. Esse fluxo atua como um teto e um piso artificiais de
supressão de volatilidade, atuando como uma força gravitacional
de **Mean-Reversion**. Portanto, o regime de 0DTE contemporâneo
favorece pesadamente a **Reversão intradiária (Validando o Paper
2)** na maior parte dos cenários, e só corrobora o Momentum
(Paper 3) em dias de *Gamma Squeeze* (quando a estrutura de
opções quebra e inverte os dealers para Short Gamma profundo).

---

## 4. Lógica Python Implementável (Sem Book Depth / Nível 2)

Como o *OdinMaxMnqSniffer* de seu projeto apontou o "sufoco" e as
inconsistências nos dados de Book/Level 2, a estratégia precisa
depender unicamente do *Datafeed OHLCV* limpo. A lógica a seguir
implementa o classificador VVG e a inversão para ser rodada e
testada no Python (DataFrame) antes de ser migrada ao C#
NinjaTrader.

```python
import pandas as pd
import numpy as np

def generate_vvg_reversal_signals(df_5m, df_daily):
    """
    Aplica o classificador Volatility-Volume-Gap (arXiv:2605.11423).
    Requer: df_5m (OHLCV 5 min) e df_daily (Contexto fechamento).
    """
    signals = []

    # Baseline de Volume (Media Movel 10 dias da primeira 1 hora)
    df_5m['Time'] = df_5m.index.time
    mask_1h = (df_5m['Time'] >= pd.to_datetime('09:30').time()) & \
              (df_5m['Time'] < pd.to_datetime('10:30').time())

    vol_1h = df_5m[mask_1h].groupby(df_5m.index.date)['Volume'].sum()
    rolling_vol = vol_1h.rolling(window=10).mean().shift(1)

    for date in df_5m.index.date.unique():
        day_data = df_5m[df_5m.index.date == date]
        if len(day_data) < 70:
            continue

        # Filtros e Gaps OHLCV
        try:
            # Obtem Fechamento D-1 diretamente
            prev_close = df_daily[df_daily.index.date < date]['Close'].iloc[-1]
        except IndexError:
            continue

        open_price = day_data.iloc[0]['Open']
        gap_pct = abs((open_price - prev_close) / prev_close)

        # Monitora a abertura (9:30 as 10:00)
        morning_data = day_data[
            (day_data['Time'] >= pd.to_datetime('09:30').time()) &
            (day_data['Time'] < pd.to_datetime('10:00').time())
        ]
        if morning_data.empty:
            continue

        # Condicao 1: Anomalia de Volume (> 1.5x Baseline)
        # Condicao 2: Gap Anormal (> 0.3%)
        today_vol = morning_data['Volume'].sum()
        baseline_vol = rolling_vol.get(date, np.nan)

        vol_anomaly = (today_vol > 1.5 * baseline_vol) if pd.notna(baseline_vol) else False
        gap_anomaly = gap_pct > 0.003

        if vol_anomaly and gap_anomaly:
            # VVG Classificador Positivo -> Reversao Tardia
            # Mede o drift do inicio ate as 14:30
            drift_mask = day_data['Time'] <= pd.to_datetime('14:30').time()
            if not day_data[drift_mask].empty:
                drift_end = day_data[drift_mask]['Close'].iloc[-1]
                drift_dir = 1 if drift_end > open_price else -1

                # Setup: Vende se subiu (1), Compra se caiu (-1)
                entry_price = drift_end
                stop_loss = entry_price + (20 * drift_dir)   # Stop Fixo: 20 pts
                take_profit = entry_price - (40 * drift_dir) # Alvo: 40 pts

                signals.append({
                    'Date': date,
                    'Entry_Time': '14:30',
                    'Signal': -drift_dir,
                    'Entry': entry_price,
                    'Stop': stop_loss,
                    'Target': take_profit,
                })

    return pd.DataFrame(signals)
```

### Recomendações Práticas e Limitações (Arquitetura NinjaTrader)

1. **Encerramento Topstep e Fechamento:** Para o ambiente C# do
   NT8, vincule o fechamento de posições baseadas neste modelo
   ao método `OnBarUpdate()` validando a aproximação de 15:50 EST
   (Liquidação forçada), já que a Topstep penaliza com a quebra
   de conta falhas no encerramento EOD.
2. **Filtro Anti-Squeeze:** Como as reversões falharão gravemente
   quando houver inversão violenta de dealers para Short Gamma,
   o Stop de 20 pontos deve ser sagrado e programático.
   Absolutamente sem martingales ou reprecificações.
3. **State Reconstruction (Erro NR7 resolvido):** Conforme as
   especificações do Kiro no repositório CAOS, certifique-se de
   configurar a série histórica diária como secundária
   (`AddDataSeries(BarsPeriodType.Day, 1)`) no NinjaTrader.
   Assegure o *Recálculo na Inicialização* para preencher as
   médias de volume do baseline sem criar "estados fantasmas".

> Projeto CAOS — Fimathe Trading Systems & SMC Quant Extensions |
> Relatório Gerado em 29/05/2026
