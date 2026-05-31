---
data: 2026-05-31
autor: Athena
justificativa: Estabelece o critério de triagem reforçado (R12+) após três refutações consecutivas com causa-raiz comum (não-persistência temporal). Inverte o ônus da prova de novas candidatas de estratégia para evitar gastar Specs em tentativas previsivelmente fadadas. Decisão de origem 2026-05-31-01.
inclusion: always
---

# Critério de triagem reforçado: atacar a não-persistência

Cobre a `Decisao_2026-05-31-01` e a
`[[Regra_De_Ouro_Negativa_Nao_Persistencia_MNQ_2026-05-31]]`.

## Contexto

Em maio/2026 o pipeline do CAOS refutou **três estratégias
direcionais consecutivas** (Crabel NR7+ORB+SF+CB, P2 range_absoluto,
VVG Late-Session Reversal). Os modos de falha foram distintos
(overfit ao WF; não-estacionariedade; falta de year-stability), mas
a **causa-raiz é comum: não-persistência temporal (regime-dependência)**
dos edges OHLCV-direcionais no MNQ minute sob fricção Topstep.

## Regra (vinculante para qualquer nova candidata de estratégia)

Antes de abrir um Spec para uma nova estratégia, o Kiro_Brain (e o
Conselho na fase de triagem) DEVE verificar que o candidato
**demonstra como ataca a não-persistência temporal**. Um dos três
critérios abaixo precisa ser satisfeito explicitamente:

1. **Mecanismo de adaptação de regime**: o edge se ajusta quando o
   regime de mercado muda, em vez de assumir estacionariedade. Não
   basta um filtro estático calibrado uma vez.

2. **Edge estrutural independente de regime**: o edge vem de uma
   restrição persistente do mercado (ex: arbitragem entre
   instrumentos correlatos MNQ/ES/MES/NQ, restrição de capacidade,
   microestrutura que não oscila com o regime de gamma).

3. **Dado materialmente novo que mede o regime**: GEX (gamma
   exposure), book depth Level 2, ou outro dado que capture
   diretamente o estado de regime. Sujeito ao **veto condicional do
   Cerberus**: investigação preliminar gratuita (web research) DEVE
   provar que o dado é obtenível, confiável e barato ANTES de
   qualquer compromisso de Spec.

## Rejeição automática na triagem

Um candidato que apenas **"tem edge documentado em backtest"** mas
NÃO endereça a persistência é **rejeitado na triagem, sem gastar
Spec**. O ônus da prova inverteu: o candidato precisa provar que
merece o Spec, não o contrário.

## Não-objetivos explícitos (já refutados)

NÃO abrir Spec para:

- Próximo paper de momentum/reversal OHLCV puro (mesma classe das 3
  refutadas; teto de edge bruto ~1.5 pts/trade por arXiv 2605.04004).
- Calendar anomalies (Pre-FOMC, Turn-of-Month) — documentadas como
  desaparecendo pós-2015/2020.
- Order flow sem book depth L2 confiável (sniffer já falhou,
  Sharpe −39; OFI agregado fraco por arXiv 2508.06788).
- Recalibração de qualquer estratégia já refutada (regra
  anti-overfit; variante exige novo Spec sob Decisão formal).

## Critérios de robustez que permanecem obrigatórios

Herdados das Decisões anteriores, continuam valendo para qualquer
candidato que passe a triagem:

- **Year-stability** (`Decisao_2026-05-29-03`): Sharpe positivo em
  ≥ 3/4 trimestres da janela de WF. Provou seu valor ao pegar a VVG
  que as medianas mascaravam.
- **Hold-out temporal real**: validação em janela disjunta do
  treino/calibração.
- **Critério de descarte pré-registrado** antes da observação
  (anti-viés de confirmação).
- **Parâmetros congelados** (anti-overfit): sem recalibração após
  ver o resultado.

## Quando reabrir o pipeline OHLCV-direcional

Somente quando surgir candidato que passe os 3 critérios de triagem
acima. Até lá, o pipeline de estratégias OHLCV-direcionais está
**pausado por disciplina** — não por desistência.
