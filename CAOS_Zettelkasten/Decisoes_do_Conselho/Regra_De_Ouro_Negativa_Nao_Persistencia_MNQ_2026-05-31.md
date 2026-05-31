---
tipo: nota_zettel
area: Decisoes_do_Conselho
titulo: Regra de Ouro Negativa — Não-Persistência dos edges OHLCV no MNQ minute
data: 2026-05-31
autor: Kiro_Brain
status: artefato-permanente
decisao_origem: 2026-05-31-01
links:
  - "[[Decisao_2026-05-31-01_Rumo_Do_Pipeline]]"
  - "[[Refutacao_VVG_Late_Session_2026-05-29]]"
  - "[[Refutacao_P2_Range_Absoluto_2026-05-29]]"
  - "[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]"
tags:
  - regra-de-ouro-negativa
  - nao-persistencia
  - regime-dependencia
  - mnq-minute
  - criterio-de-triagem
  - anti-vies-de-acao
---

# Regra de Ouro Negativa — Não-Persistência dos edges OHLCV no MNQ minute

> Artefato **permanente** do projeto CAOS, estabelecido pela
> `[[Decisao_2026-05-31-01_Rumo_Do_Pipeline]]` após três refutações
> consecutivas em maio/2026. Consolida o que **NÃO funciona** —
> valor de longo prazo que evita repetir ciclos perdidos.

## Enunciado

> **Edges direcionais baseados em OHLCV puro no MNQ minute, sob
> fricção Topstep, falham por NÃO-PERSISTÊNCIA TEMPORAL
> (regime-dependência) — não por tamanho insuficiente do edge.**

O edge, quando existe, aparece em janelas/regimes específicos e
evapora em outros. Detectá-lo de forma incondicional exige amostra
inalcançável; explorá-lo de forma condicional esbarra na falta de
persistência entre regimes.

## Evidência acumulada (3 refutações + 2 papers)

### As três refutações — modos distintos, causa comum

| Estratégia | Modo de falha | Causa-raiz |
|---|---|---|
| Crabel NR7 + ORB + SF + CB | Aprovou no WF (+2.91 Sharpe), falhou no re-replay (−USD 573,50) | Overfit ao WF → regime do hold-out difere do treino |
| P2 range_absoluto | Refutada na calibração (0 ou elegibilidade instável) | Threshold absoluto não-estacionário (vol variou 37% no P17 entre 2 trimestres) |
| VVG Late-Session Reversal | Aprovou Sharpe/Calmar/PnL, falhou year-stability (1/4) | Edge concentrado em 1 trimestre, negativo nos outros 3 |

Três modos de falha diferentes **não são azar repetido**. São três
manifestações do mesmo fenômeno: **regime-dependência**. O edge não
sobrevive à troca de regime de mercado.

### Os dois papers que corroboram

- **arXiv 2605.04004** (Structural Limits OHLCV MNQ): edge bruto
  intraday gravita entre 0.07 e 1.5 pts/trade. Após fricção
  (~1 pt round-trip), edge líquido ~0.5 pts — estatisticamente
  indistinguível de zero com N gerável.
- **arXiv 2605.11423** (Mesfin/VVG): mesmo o melhor setup
  condicional (+7.80 pts/trade, T=1.46) "fails ... multi-year
  consistency requirements". O próprio autor admite a
  não-persistência.

### Cálculo de poder (Mister_M)

Para detectar edge líquido de ~0.5 pts/trade com sd ~50 pts/trade
(observado na VVG) a 95% de significância e 80% de poder:
**N ≈ 78.000 trades**. Nenhuma estratégia direcional gera isso em
janela testável. Para edges condicionais maiores (ex: +7.80 pts da
VVG), o N cai, mas aí o limitante passa a ser a **não-persistência**
(o edge só aparece num subconjunto de regimes).

### Mecânica estrutural (Odin)

O MNQ de 2026 difere estruturalmente do pré-2020:

1. **0DTE engole >50% do volume de derivativos do índice** →
   dealers passam mais tempo Long Gamma → volatilidade direcional
   suprimida (a força que estratégias direcionais precisam).
2. **Algos institucionais comprimiram edges OHLCV clássicos** →
   follow-through de breakout arbitrado em milissegundos (NR7/Crabel
   funcionava em 1990 porque o mercado era mais lento).
3. **Mean-reversion retail via 0DTE é real mas não-estacionária** →
   depende do posicionamento de gamma do dia, que não medimos.

## Critério de triagem reforçado (R12+)

Estabelecido pela Decisão `2026-05-31-01`. **Vinculante** para
qualquer candidato futuro:

> Antes de gastar um Spec, o candidato DEVE demonstrar, na triagem,
> **como ataca a não-persistência temporal**. Opções aceitáveis:
>
> 1. **Mecanismo de adaptação de regime** explícito (o edge se
>    ajusta quando o regime muda, em vez de assumir estacionariedade).
> 2. **Edge estrutural que não dependa de regime** (ex: arbitragem
>    entre instrumentos correlatos, restrição de capacidade,
>    microestrutura persistente).
> 3. **Dado materialmente novo** que meça o regime diretamente
>    (GEX, book depth L2) — sujeito ao veto condicional do Cerberus
>    (investigação preliminar gratuita primeiro).
>
> Candidato que apenas "tem edge documentado em backtest" mas não
> endereça persistência é **rejeitado na triagem, sem Spec**. O
> ônus da prova inverteu: o candidato prova que merece o Spec, não
> o contrário.

## O que NÃO fazer (lições operacionais)

- **Não** triar a shopping-list cegamente atrás do próximo paper de
  momentum/reversal — é a mesma classe das 3 refutadas.
- **Não** caçar calendar anomalies (Pre-FOMC, TOM) — documentadas
  como desaparecendo pós-2015/2020.
- **Não** tentar order flow sem book depth L2 confiável — o sniffer
  já falhou (Sharpe −39); arXiv 2508.06788 mostra que OFI agregado
  é fraco mesmo com book.
- **Não** recalibrar parâmetros de estratégia refutada (regra
  anti-overfit) — variante exige novo Spec sob Decisão formal.
- **Não** confundir Sharpe/Calmar medianas altas com validade —
  são miragens de N pequeno; year-stability é o critério que pega.

## O que vale fazer (caminhos abertos)

1. **Investigação preliminar GRATUITA** sobre viabilidade de dado
   de regime (GEX/L2) para MNQ — sem compromisso de Spec até provar
   obtenibilidade/confiabilidade/custo (veto condicional Cerberus).
2. **Classes de problema nunca tocadas** (sugeridas pelo
   Devils_Advocate, todas sujeitas ao critério de triagem acima):
   arbitragem estatística MNQ vs ES/MES/NQ; estratégias de
   volatilidade não-direcionais; market making passivo.
3. **Consolidação/infraestrutura**: melhorar o próprio pipeline de
   validação (o year-stability provou seu valor — que outros
   critérios de robustez faltam?).

## Status do pipeline

**Estratégias OHLCV-direcionais: PAUSADO** por disciplina
anti-viés-de-ação. Não é desistência — é reconhecer que três
refutações independentes com causa-raiz comum são um sinal a
respeitar, não um convite para uma quarta tentativa apressada.
