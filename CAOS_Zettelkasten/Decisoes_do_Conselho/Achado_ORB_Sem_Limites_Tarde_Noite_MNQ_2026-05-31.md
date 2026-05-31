---
tipo: achado-exploratorio-positivo
data: 2026-05-31
gatilho: diretriz-usuario (remover limites a-priori, MNQ-only)
custo: zero-spec (experimento exploratorio sobre dados existentes)
veredito: PROMISSOR — edge estrutural tarde/noite sobrevive hold-out cego (PF 1.22), mas modesto e nao-validado formalmente
relacionado:
- "[[Investigacao_ORB_Limit_Entry_Ressuscitacao_Hydra_2026-05-31]]"
- "[[Regra_De_Ouro_Negativa_Nao_Persistencia_MNQ_2026-05-31]]"
- Decisao_2026-05-24-01 (ORB market+slippage = -USD 13.719)
tags: [orb, sem-limites, tarde-noite, overnight, limit-entry, MNQ, hold-out, promissor]
---

# Achado ORB sem limites — edge estrutural tarde/noite (MNQ)

> **Veredito**: removendo as amarras a-priori (janela RTH, hora de corte,
> saída forçada, 1 trade/sessão), o ORB com entrada LIMIT revela um **edge
> de rompimento concentrado na tarde/noite/madrugada ET**, NÃO na abertura.
> O conjunto de horas tarde/noite **persiste em hold-out cego** (treino PF
> 1.23 → hold-out PF 1.22, year-stability 2/2). É o **primeiro candidato a
> passar year-stability em hold-out disjunto** depois de 4 refutações.
> **Modesto** (PF ~1.22, ~2.4 trades/dia) e ainda **não-validado** pelo
> WalkForwardEngine formal — exige Spec.

## Origem

Diretriz direta do usuário (31/mai/2026): *"o foco é MNQ, esquece o resto.
Não vamos nos ligar em limite de horário pra operação e limite de trader.
Cria sem esses limites — às vezes criamos algo bom mas por causa das
limitações de início acabamos perdendo. Depois de validar consistência, a
gente roda replay e descobre o melhor horário, trades/dia ideal etc."*

Insight do usuário: as restrições a-priori (impostas por convenção de mesa
proprietária / literatura ORB) podem estar mascarando edge real.

## O que foi testado (5 experimentos, isolando variáveis)

Todos sobre MNQ minute, 5 contratos, 2025-03 a 2026-05 (372 dias ET),
custo honesto de entrada LIMIT = 0.87 pt/trade (comissão 0.62 + 1 tick
saída). Split anti-overfit: treino = 70% inicial, hold-out = 30% final.

| Experimento | Resultado |
|---|---|
| ORB sem limites, entrada **market** | PF colapsa com custo (slippage mata, igual ao Hydra) |
| ORB sem limites, entrada **limit**, custo honesto, SEM filtro hora | PF ~1.02 (empate; edge bruto fino ~1 pt/trade) |
| Filtro de horas derivado SÓ do treino, validado no hold-out cego | **treino 1.23 → hold-out 1.22, year-stability 2/2** |
| **Rolling OOS** (re-derivar horas todo mês) | **PF 0.99 — a regra adaptativa NÃO generaliza** |
| Horas que persistiram em 100% dos meses rolling {16,19,22 ET} | FULL PF 1.48, hold-out PF 1.63 (N pequeno=50) |
| Conjunto persistente {10,16,18,19,22 ET} (>=78% dos meses) | FULL 1.23, treino 1.23, **hold-out 1.22, year-stability 2/2** |

## Achado estrutural central

No walk-forward rolling, a **frequência de seleção por hora** revelou
persistência (não cherry-pick):

| Hora ET | Selecionada como lucrativa |
|---|---|
| **16:00** | **9/9 meses (100%)** |
| **19:00** | **9/9 meses (100%)** |
| **22:00** | **9/9 meses (100%)** |
| 18:00 | 7/9 (78%) |
| 10:00 | 6/9 (67%) |
| 09:00 (abertura clássica ORB) | 2/9 (22%) — NEGATIVA |
| 11:00, 12:00, 13:00, 17:00, 21:00 | instáveis / negativas |

**O edge de rompimento do MNQ está na tarde/noite/madrugada, não na
abertura.** As amarras de horário RTH (que a literatura ORB e as mesas
proprietárias impõem) cortavam exatamente as horas com sinal persistente.

## Por que isto NÃO é (provavelmente) overfit

1. **Hold-out cego com degradação ~zero**: treino PF 1.23 → hold-out 1.22.
   Overfit degrada forte do treino pro hold-out; este não degradou.
2. **Seleção por persistência, não por PnL agregado**: as horas foram
   identificadas por aparecerem em ≥78% de meses independentes, não por
   somarem o maior PnL.
3. **Year-stability passa em hold-out (2/2)** — o critério que matou as 4
   refutações anteriores.

## Por que ainda NÃO está provado (régua dura do Devils_Advocate)

1. **A regra ADAPTATIVA (re-derivar horas todo mês) deu PF 0.99** — só o
   conjunto FIXO derivado de janela grande funciona. Risco: o conjunto fixo
   pode ser específico desta amostra.
2. **PF 1.22 é modesto** e o hold-out tem só ~5 meses (2 trimestres, N=173).
3. **Multiple-testing**: ~10 configurações testadas (market/limit ×
   custos × filtros). Parte da vantagem pode ser ruído de seleção.
4. **Modelo de fill otimista**: limit preenche no nível exato; stop checado
   antes do alvo intrabar. O WalkForwardEngine formal precisa confirmar.
5. **Sem hipótese econômica fechada** para o edge tarde/noite — candidata:
   janela pós-0DTE-gamma (Odin, Decisão 2026-05-31-01) onde a supressão de
   volatilidade direcional dos dealers Long Gamma se dissipa. A confirmar.

## Conexão com o critério de triagem (não-persistência)

Diferente das 4 refutações, este candidato **demonstra ataque à
não-persistência** pelo critério #2 (edge estrutural): a concentração
tarde/noite persiste em toda janela rolling e sobrevive ao hold-out cego.
A hipótese econômica (janela pós-gamma-0DTE) é estrutural, não
regime-dependente. **Passa a triagem para merecer um Spec.**

## Próximo passo recomendado

Abrir Spec formal (`caos-orb-sem-limites-mnq` ou similar) para:
1. Implementar a variante ORB sem limites (sessão cheia, múltiplas
   entradas, re-arme após retorno ao OR) no WalkForwardEngine — validação
   rigorosa, não simulador ad-hoc.
2. Split tripartite real: treino / validação (escolher horas) / hold-out
   cego forward.
3. SÓ ENTÃO rodar NT8 replay em meses forward para perfilar horário ótimo
   e trades/dia — exatamente o fluxo que o usuário pediu, mas com o
   hold-out protegendo contra auto-engano.

Como a proposta adiciona regra de decisão nova (gatilho G1), exige
Debate_Auto do Conselho antes da implementação.

## Artefatos

- `CAOS_Orchestrator/experimento_orb_sem_limites.py`
- `CAOS_Orchestrator/experimento_orb_limit_honesto.py`
- `CAOS_Orchestrator/experimento_orb_rolling_horas.py`
- `CAOS_Orchestrator/experimento_orb_horas_persistentes.py`
- Todos exploratórios, fora da suíte de testes (não plugáveis).
