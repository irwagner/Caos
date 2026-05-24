# Resultados — Noise Area + Turn-of-Month em MNQ

**Data:** 2026-05-24
**Identificadores:** `2026-05-24-02`, `2026-05-24-03`, `2026-05-24-04`
**Status:** todos `concluido`, todos com fricção Topstep + slippage proporcional 7.5%

## Sumário executivo

Três Walk-Forwards rodados em paralelo sobre o concat MNQ minute
(2025-03-17 → 2026-05-18). Resultado **negativo** para Noise Area
(ambas as variantes, lookback 14 e 90), resultado **insuficiente**
para Turn-of-the-Month (apenas 1 janela com 4 trades — amostra
ridícula).

| ID            | Estratégia               | Janelas | Trades médios | Sharpe | Win rate | PnL total (pts) | Calmar |
|---------------|--------------------------|---------|---------------|--------|----------|-----------------|--------|
| 2026-05-24-02 | NoiseArea lookback=14    | 4       | 59.25         | **-8.64** | 10.9% | **-340.08**     | -4.14  |
| 2026-05-24-03 | NoiseArea lookback=90    | 3       | 60.00         | **-10.08** | 8.3% | **-377.07**     | -4.20  |
| 2026-05-24-04 | TurnOfMonth (5/3 paper)  | 1       | 4.00          | +0.44  | 50.0%    | +50.13          | +0.18  |

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

| Estratégia                     | Status          | Trades/ano | Sharpe       | PnL/ano (USD) |
|--------------------------------|-----------------|------------|--------------|---------------|
| ORB Crabel                     | rejeitada       | ~80        | <0           | negativo      |
| Pre-FOMC drift                 | candidata frágil| 8-10       | ~0.8         | +1k-2k        |
| Crabel NR7                     | candidata frágil| ~30        | ~0.5         | ~+500         |
| Mini-portfolio (PreFOMC+NR7)   | candidata       | ~40        | combinado    | ~+2.5k        |
| **Noise Area (k=14 ou 90)**    | **rejeitada**   | ~250       | **negativo** | **negativo**  |
| **Turn-of-the-Month**          | bloqueada       | ~12        | ?            | ?             |

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
   bid-ask realizado. Se o spread filter ajudar mesmo o NoiseArea
   ruim a virar levemente positivo em dias de spread baixo, vale
   investigar combinatorialmente. Mas dado o resultado catastrófico,
   provavelmente não salva.
2. **Aguardar tick data** — quando completar exportação, rodar:
   - Caracterização tick MNQ
   - Spread médio realizado em sessões diferentes
   - OFI vs price drift
3. **TOM com dados estendidos** — quando dados históricos chegarem.
4. **Não abrir Debate Auto agora**: G3 (resultado novo) ativo mas o
   resultado é claramente negativo, sem proposta de promoção a fazer.
   Atualizar relatório e seguir.
