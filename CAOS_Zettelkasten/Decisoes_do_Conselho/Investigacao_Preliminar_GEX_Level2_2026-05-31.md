---
tipo: nota_zettel
area: Decisoes_do_Conselho
titulo: Investigação preliminar — viabilidade de dado de regime (GEX / Level 2) para MNQ
data: 2026-05-31
autor: Kiro_Brain
status: investigacao-preliminar-gratuita
decisao_origem: 2026-05-31-01
links:
  - "[[Decisao_2026-05-31-01_Rumo_Do_Pipeline]]"
  - "[[Regra_De_Ouro_Negativa_Nao_Persistencia_MNQ_2026-05-31]]"
tags:
  - investigacao-preliminar
  - gex
  - gamma-exposure
  - level-2
  - book-depth
  - veto-condicional-cerberus
---

# Investigação preliminar — viabilidade de GEX / Level 2 para MNQ

> Cumpre o item 3 da `Decisao_2026-05-31-01` (P3 sob veto condicional
> do Cerberus): investigação **gratuita** (web research) sobre se há
> fonte viável de dado de regime ANTES de qualquer compromisso de
> Spec. **Nenhum custo incorrido.** Esta nota é o resultado.

## Pergunta

Existe fonte **obtenível, confiável e gratuita/barata** de:
(a) Gamma Exposure (GEX) para o Nasdaq-100, ou
(b) book depth Level 2 **histórico** do MNQ para backtest?

Se sim, destrava uma classe de estratégias que ataca a
não-persistência via medição direta do regime (critério 3 do
steering `criterio-triagem-nao-persistencia`).

## Achados

### GEX (Gamma Exposure)

| Fonte | Acesso | Instrumento | Veredito |
|---|---|---|---|
| quantedoptions.com | **Pago** ($99-299/mês) | SPX/VIX | licenciado CBOE, mas caro e SPX-cêntrico |
| gexstream.com | **Pago** | índices | real-time, não histórico barato |
| Cboe DataShop | **Pago** (cotação) | opções index | fonte primária, custo sob consulta |
| jensolson/SPX-Gamma-Exposure (GitHub) | Gratuito (código) | **SPX** | calcula GEX, mas precisa de dado de cadeia de opções (não incluído) e é SPX, não NDX |
| Matteo-Ferrara/gex-tracker (GitHub) | Gratuito (código) | genérico | idem — calcula a partir de chain que você precisa obter |
| barchart.com | Freemium | tem E-mini Nasdaq | dados limitados no free tier; histórico intraday não-trivial |

**Conclusão GEX**: não há feed gratuito e confiável de GEX para o
**Nasdaq-100 (NDX)**. O ecossistema é majoritariamente **SPX/VIX**
(o Nasdaq tem cobertura menor). Os repos open-source apenas
**calculam** GEX — exigem dados de cadeia de opções NDX que também
precisam ser adquiridos. Para o MNQ especificamente, a relação
GEX-NDX → preço-MNQ adiciona uma camada de aproximação não validada.

### Level 2 / book depth histórico do MNQ

| Fonte | Acesso | Cobertura | Veredito |
|---|---|---|---|
| NinjaTrader 8 "market recording for playback" | Gratuito | **só dali pra frente** | grava L2 a partir do momento em que liga — NÃO é retroativo. Inútil para backtest histórico |
| Topstep L1/L2 feed | Incluído na conta | real-time | tempo real, não histórico para backtest |
| PortaraCQG | **Pago** | histórico MNQ | vende histórico, mas L2/DOM histórico é caro e formato não-trivial |
| Sniffer interno (OdinMaxMnqSniffer) | Próprio | — | **já falhou** (Sharpe −39, dados inconsistentes) |

**Conclusão L2**: book depth **histórico** confiável para backtest
do MNQ não é obtenível gratuitamente. O NT8 só grava L2 a partir do
momento da ativação (não retroativo), o que inviabiliza validação
histórica (WF longo). Comprar histórico de L2 é caro e o sniffer
próprio já falhou.

## Veredito da investigação preliminar (veto condicional Cerberus)

**O veto condicional do Cerberus NÃO é liberado.** Nenhuma das duas
fontes de dado de regime é simultaneamente obtenível, confiável e
gratuita/barata:

- **GEX**: pago, SPX-cêntrico, e a ligação NDX→MNQ é aproximação não
  validada. Mesmo o caminho "calcular via repo open-source" exige
  dado de opções NDX que tem o mesmo problema de custo.
- **Level 2 histórico**: não existe de graça para backtest; gravação
  NT8 é só prospectiva; compra é cara; sniffer próprio já falhou.

Portanto, **P3 (adquirir dado de regime) NÃO vira Spec agora**. A
porta fica fechada com honestidade, exatamente como o Devils_Advocate
previu ("se tivéssemos dado melhor teríamos edge" é falácia sem base).

## Caminho que permanece (não-degenerado)

Há **uma** sub-opção de baixo custo que poderia ser explorada no
futuro SEM compromisso de Spec imediato: **GEX prospectivo gratuito**.
Em vez de comprar histórico, ligar uma coleta gratuita de GEX
(ex: scraping diário de uma fonte freemium, ou cálculo via chain
gratuita) **a partir de agora**, acumulando dado prospectivo por
alguns meses. Isso:

- custa ~zero (só tempo de setup de um coletor);
- acumula um dataset proprietário de regime que ninguém mais tem
  alinhado ao MNQ;
- só justifica um Spec de estratégia DEPOIS de ter meses de dado
  acumulado (hold-out temporal real embutido por construção).

Esta sub-opção respeita o veto do Cerberus (custo ~zero) e o critério
de não-persistência (mede o regime diretamente). **Mas é uma aposta
de meses, não de semanas** — fica registrada como possibilidade, não
como recomendação ativa.

## Estado

Pipeline de estratégias OHLCV-direcionais permanece **PAUSADO**
(`criterio-triagem-nao-persistencia`). P3 não destravou. A coleta
prospectiva de GEX é a única porta de baixo custo que sobra, mas
exige decisão explícita do usuário para iniciar (é compromisso de
meses de acúmulo de dado).
