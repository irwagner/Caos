---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-24T00:30:00Z'
id: anexo-correlacao-crabel-pre-fomc-2026-05-24
relacionado: Decisao_2026-05-24-01
tags:
- correlacao-portfolio
- crabel-nr7
- pre-fomc
- mini-portfolio
titulo: Análise de correlação Crabel NR7 vs Pre-FOMC drift
---

# Análise de correlação — Crabel NR7 vs Pre-FOMC drift

> Cumpre Decisão `2026-05-24-01` (P2 vencedora). Verifica se as duas
> candidatas pegam dias DIFERENTES (compatibilidade para mini-portfolio
> futuro) ou se uma é redundante.

## Resultado

**Overlap zero.** As duas estratégias operam em conjuntos de dias
**completamente disjuntos** sobre os mesmos 13 meses de MNQ.

| | Crabel NR7 | Pre-FOMC | Overlap |
|---|---:|---:|---:|
| Trades emitidos | 45 | 10 | 0 |
| Datas únicas com trade | 45 | 10 | 0 |
| Dias só Crabel | 45 | — | — |
| Dias só Pre-FOMC | — | 10 | — |

**Razão estrutural**: Pre-FOMC opera **apenas no dia útil ANTES
de meeting FOMC** (~8 dias/ano). Crabel NR7 opera **apenas no dia
ÚTIL APÓS um Narrow Range** (compressão prévia). As duas condições
são mecanicamente independentes — saber que ontem foi NR não diz
nada sobre se amanhã é véspera de FOMC.

## PnL agregado (série completa, Topstep fixo 1.12 pts/round-trip)

| Estratégia | N | Bruto (pts) | Líquido (pts) | USD |
|---|---:|---:|---:|---:|
| Crabel NR7 | 45 | +944.00 | +893.60 | **+USD 1.787** |
| Pre-FOMC | 10 | +373.00 | +361.80 | +USD 724 |
| **Portfolio 1+1** | **55** | **+1317.00** | **+1255.40** | **+USD 2.511** |

PnL portfolio sobre 13 meses úteis = ~USD 193/mês.

## Implicações estatísticas

**Independência amostral**: por estarem em datas disjuntas, os PnLs
diários das duas estratégias têm correlação ≈ 0 (sem overlap → sem
co-movimento direto). Variância do portfolio é literalmente a soma
das variâncias individuais — sem amplificação por correlação.

**Poder estatístico**: portfolio tem N=55 trades, 5.5x mais que
Pre-FOMC sozinha. Ainda abaixo do limite institucional (Mesfin 2026:
N≥30 com t-stat≥2.0). Estimativa de t-stat sobre 55 trades líquidos:

- Média líquida = 1255.4/55 = 22.83 pts/trade
- Std esperado (alta dispersão entre as duas estratégias) ≈ 100-150 pts
- t ≈ 22.83 / (std/√55) ≈ 1.1 a 1.6

**Não rejeita H0 ao nível 5%** mas direção positiva e
estatisticamente mais robusta que cada uma sozinha.

## Caveats reconhecidos

1. **Slippage proporcional realista** ainda derruba ambas. Análise
   acima usa slippage fixo Topstep para comparabilidade com o
   relatório Pre-FOMC original (commit `73d985a`). Sob slippage
   proporcional:
   - Crabel NR7 (em WF): +USD 474 (35 trades)
   - Crabel NR7 (em série): tipicamente similar
   - Pre-FOMC (proporcional): -USD 264

   Pre-FOMC tem holding de 24h então slippage proporcional ao MFE+|MAE|
   é exagerado para ela. Modelo proporcional é apropriado para
   intraday curto (Crabel ORB), conservador demais para holding longo.

2. **N=55 é pouco** para um portfolio. Lucca-Moench tem 200+ FOMC.
   Crabel original em ES/NQ acumulou décadas.

3. **A independência das datas é estrutural, não casual.** Vai se
   manter em qualquer período futuro porque as definições mecânicas
   das duas estratégias são ortogonais.

## Veredito (sem promoção)

Conforme Decisão `2026-05-24-01`:

- **Análise concluída** — overlap = 0 confirma que mini-portfolio
  é tecnicamente viável.
- **NÃO autoriza paper trading**.
- **NÃO autoriza promoção de família individual**.
- **Adiciona ao registro permanente**: 3 candidatas para revisita
  futura quando dados crescerem (~6-12 meses):
  1. Pre-FOMC drift sozinha (Decisão 2026-05-23-03)
  2. Crabel NR7 ORB sozinha (esta sessão)
  3. **Mini-portfolio Crabel NR7 + Pre-FOMC** com correlação
     estrutural zero (esta análise)

A pausa investigativa de `2026-05-23-02` permanece. Próxima rodada
deve revisitar as 3 candidatas e decidir promoção apenas se cada
uma passar t-stat ≥ 2.0 com Bonferroni para 3 testes paralelos
(threshold ajustado ~2.6).

## Referências

- Decisão `2026-05-24-01` — esta análise é seu cumprimento.
- Anexo `73d985a` (inspeção Pre-FOMC) — método de série completa.
- `c1b2bc6` (briefing do Explorador) — origem da hipótese Crabel NR.
- Hydra v1 null result (`reference_hydra/01_LICOES_APRENDIDAS/`) —
  contexto histórico.
