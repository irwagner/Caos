---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T04:30:00Z'
id: anexo-inspecao-trades-pre-fomc-2026-05-23
relacionado: Decisao_2026-05-23-03
tags:
- inspecao-implementacao
- pre-fomc
- walk-forward
titulo: Anexo de inspeção dos trades — WF Pre-FOMC 2026-05-23-04
---

# Anexo de inspeção — WF Pre-FOMC 2026-05-23-04

> Este anexo cumpre a Decisão `2026-05-23-03` (P2 vencedora):
> "inspecionar manualmente os 8 trades emitidos para validar
> implementação". Não é Decisão por si — apenas registra evidência
> de validação.

## Veredito

**Implementação CORRETA.** Critério Athena (≥ 7/8 trades com saída
em data FOMC oficial) atingido com **10/10**. Bug de fuso
descartado.

## Achado adicional (não previsto na Decisão)

A re-execução da estratégia sobre a série **inteira** (sem janelas
WF) emite **10 trades**, não 8. Os 2 trades faltantes no WF original
correspondem a meetings cuja entrada (close D-1) e saída (close D)
caíram em janelas WF DIFERENTES — o Engine isola cada janela e
descarta posições incompletas, comportamento correto e
documentado.

Implicação: **WF com janelas curtas (60d) descarta ~20% dos sinais
de baixa frequência**. Para estratégias como a Pre-FOMC (8
meetings/ano), métrica honesta é PnL agregado da série completa,
não Sharpe mediano por janela WF.

## Tabela dos 10 trades (ordem cronológica, série completa)

| # | Entrada | Saída | Dia entrada | Dia saída | PnL bruto (pts) | OK? |
|---:|---|---|---|---|---:|:---:|
| 0 | 2025-03-18 | 2025-03-19 | Tue | Wed | +244.00 | ✓ |
| 1 | 2025-05-06 | 2025-05-07 | Tue | Wed | +108.00 | ✓ |
| 2 | 2025-06-17 | 2025-06-18 | Tue | Wed | +13.75 | ✓ |
| 3 | 2025-07-29 | 2025-07-30 | Tue | Wed | +207.50 | ✓ |
| 4 | 2025-09-16 | 2025-09-17 | Tue | Wed | -35.75 | ✓ |
| 5 | 2025-10-28 | 2025-10-29 | Tue | Wed | +57.00 | ✓ |
| 6 | 2025-12-09 | 2025-12-10 | Tue | Wed | +122.75 | ✓ |
| 7 | 2026-01-27 | 2026-01-28 | Tue | Wed | +102.75 | ✓ |
| 8 | 2026-03-17 | 2026-03-18 | Tue | Wed | -412.75 | ✓ |
| 9 | 2026-04-28 | 2026-04-29 | Tue | Wed | -34.25 | ✓ |

**PnL bruto total**: +372.50 pontos.
**Custos** (10 trades × 1.12 pts/trade Topstep): -11.20 pontos.
**PnL líquido**: **+361.30 pontos × USD 2 = +USD 722.60** sobre
13 meses úteis.
**Win rate**: 7/10 = **70%**.

## Observações estatísticas

- Distribuição assimétrica: 7 vencedores (+855.75) vs 3 perdedores
  (-482.75). Razão wins/losses em magnitude = 1.77, payoff
  consistente com literatura.
- 1 trade catastrófico (-412.75 em mar/2026) responde por 86% das
  perdas totais. Essa é a janela em que o Devils_Advocate previu
  ataque de "explicar perda com VIX baixo" que NÃO investigamos.
- 10 trades é amostra pequena para Sharpe, mas **suficiente para
  rejeitar H0 com t-stat se PnL liquido continuar positivo em
  dobrar a amostra** (~20 trades sob critério institucional).

## Próxima ação informal recomendada

A Decisão `2026-05-23-03` mandou pausar até implementação ser
validada. Validação concluída. Mas continua valendo "amostra
pequena demais para promover a paper".

Caminho mais barato pra amadurecer evidência: aguardar 6-8 meses
úteis adicionais (mais ~5 meetings) para ter ~15 trades. Próximo
WF/inspeção pode ser feito em ~Q4/2026 sem violar split tripartite
(porque essa estratégia é nova; não há "hold-out" anterior dela).

Em paralelo, vale **retesetar a estratégia em ES e SPY** quando
houver dados, porque o paper Lucca-Moench testa SPY originalmente —
seria comparação direta com baseline da literatura.
