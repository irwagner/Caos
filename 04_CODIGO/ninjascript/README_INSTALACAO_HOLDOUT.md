# Instalação no NinjaTrader 8 — Hold-out cego de 60 dias úteis

**Estratégia aprovada:** `StrategyORBCrabelSpreadFilter`
**Decisão de aprovação:** `2026-05-25-02` (commit `7eddd30`, tag `caos-frozen-2026-05-25-02`)
**Pré-condições operacionais:** ver `CAOS_Council/decisions/2026-05-25-02-*.md`

---

## Passo 1 — Copiar arquivos

Copie os 9 arquivos `.cs` deste diretório (`04_CODIGO/ninjascript/`) **EXCETO** o subdiretório `reference_hydra/`:

```
Strategy.cs
Cerberus.cs
TrailingTresFases.cs
MfeMaeTracker.cs
Logger.cs
EstrategiaORBLogica.cs
EstrategiaCrabelLogica.cs
SpreadFilterLogica.cs
CircuitBreakerEstendido.cs
StrategyORBCrabelSpreadFilter.cs
```

Para o caminho de instalação do NinjaTrader 8:

```
%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\
```

> **Atenção (freio humano #1):** essa cópia é manual. Eu (Kiro_Brain) nunca copio arquivos para esse diretório automaticamente.

## Passo 2 — Compilar

1. Abra NinjaTrader 8.
2. Menu **Tools → Edit NinjaScript → Strategy**.
3. Pressione **F5** para compilar.
4. Se aparecerem erros de namespace, confira que todos os 9 arquivos foram copiados.

## Passo 3 — Configurar conta paper trading

1. Faça login em sua conta `Sim101` (ou simulador NT8 / Topstep paper).
2. **Não use conta real durante o hold-out.** A estratégia ainda está em hold-out cego — não foi liberada para USD real (Decisão 2026-05-25-02).
3. Configure margens equivalentes a Topstep funded (USD 50 inicial / USD 2500 trailing DD para conta de USD 50k).

## Passo 4 — Habilitar a estratégia

1. **New Strategy → Strategies →** procure `StrategyORBCrabelSpreadFilter`.
2. Configure no chart:
   - **Instrument**: MNQ (ativo do contrato corrente — ex.: `MNQ 09-26` em jul/2026).
   - **Bars**: 1 minute.
   - **Calculate**: OnBarClose (default).
3. Parâmetros (deixe os defaults — eles são as configurações aprovadas):
   - `MaxContratos = 1`
   - `CircuitBreakerDiarioUSD = 500`
   - `CircuitBreakerSemanalUSD = 1500`
   - `CircuitBreakerJanelaUSD = 2000`
   - `MinutosOR = 30`
   - `RiscoMultiplicador = 1.0`
   - `AlvoMultiplicador = 2.0`
   - `CooldownMinutos = 15`
   - `SessaoInicioUtc = 13:30`
   - `SessaoFimUtc = 20:00`
   - `HoraCorteEntradasUtc = 19:00`
   - `RangeMinimoPontos = 0.5`
   - `SpreadFilterWarmup = 30`

## Passo 5 — Hold-out cego

A estratégia opera automaticamente nas próximas 60 dias úteis.

**Anotar diariamente:**

- PnL realizado do dia (USD).
- Quantos trades aconteceram.
- Mensagens `[CAOS] Trade fechado` no Output Window.
- Triggers de Circuit Breaker (mensagens com `bloq=diario|semanal|janela`).

## Passo 6 — Marcos de avaliação

- **Após 30 dias úteis sem trigger de CB de janela ou semanal**: você pode liberar `MaxContratos=2`. Atenção: o CB diário disparou? Tudo bem se sim — só precisa não ter disparado o semanal nem o de janela.
- **Após 60 dias úteis**: chame Debate de seguimento (próximo Conselho-no-Chat). Eu reabro o Debate com os dados reais e re-avalio limites do CB.

## Comportamento esperado (do Walk-Forward)

Baseado no WF `2026-05-25-05` (4 janelas WF rolantes 60+60 sobre dados 2025-04 → 2026-05):

| Métrica | Valor mediano | Variação observada |
|---|---|---|
| Trades por janela | 6.5-8 | 2-9 |
| PnL por janela | +240 pts (+USD 480) | -1435 a +1339 |
| Sharpe local | +2.91 | -6.5 a +6.9 |
| Win rate | 0.45 | 0.18 a 0.70 |

**Pior caso documentado:** janela 1 com PnL -1435 pts (-USD 2870 com 1 contrato). O CB ativou e salvou da janela bruta de -1711 pts.

**Cenário esperado em 60 dias úteis:**
- 2-4 trades por semana em dias após NR7.
- PnL diário tipicamente entre -USD 500 e +USD 800.
- Triggers de CB diário (-USD 500) podem acontecer ~1x por mês.

## Se algo der errado

- **Estratégia não roda**: confirme que o instrumento é MNQ 1m e que `Sim101` está habilitada.
- **Nenhum trade aparece**: provavelmente nenhum dia recente foi NR7. O Crabel filtra agressivamente.
- **CB ativa o tempo todo**: regime adverso. Pare a estratégia e abra Debate de seguimento.
- **Stop não disparou**: confira que `MaxContratos` está em 1 e que `Cerberus` autorizou. Ver mensagens no Output Window.

## Contato com o Conselho

Quando precisar reabrir Debate de seguimento, traga os dados:

1. CSV ou screenshot dos trades dos 60 dias.
2. PnL diário acumulado.
3. Triggers de CB (datas + magnitude).
4. Quaisquer eventos macro relevantes (FOMC, NFP, eleições) que afetaram performance.

Eu (Kiro_Brain) levo isso para o próximo Debate Auto e re-avaliamos os limites do CB com dados reais.
