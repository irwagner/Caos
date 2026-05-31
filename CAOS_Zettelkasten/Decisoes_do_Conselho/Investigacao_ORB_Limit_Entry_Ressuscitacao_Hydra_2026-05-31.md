---
tipo: investigacao-preliminar
data: 2026-05-31
gatilho: pedido-direto-usuario (resultado AGORA, minerar Hydra)
custo: zero-spec (experimento exploratorio sobre codigo/dados existentes)
veredito: REFUTADO — limit-entry conserta o slippage mas o edge nao persiste
relacionado:
- "[[Regra_De_Ouro_Negativa_Nao_Persistencia_MNQ_2026-05-31]]"
- "[[Investigacao_Preliminar_GEX_Level2_2026-05-31]]"
- Decisao_2026-05-24-01 (ORB sob slippage proporcional = -USD 13.719)
tags: [orb, limit-entry, hydra, slippage, nao-persistencia, refutado, MNQ]
---

# Investigação ORB Limit-Entry — ressuscitação do Hydra (REFUTADO)

> **Veredito**: a entrada via LIMIT (pullback) **conserta o problema de
> slippage** que matou o ORB do Hydra — exatamente como a nota de
> ressuscitação previa. **Mas o edge bruto do ORB não persiste no MNQ
> minute** (2025-03 a 2026-05): year-stability falha em todos os modelos
> de execução e de custo. Mesma não-persistência das 3 refutações
> anteriores. **Caminho fechado sem gastar Spec.**

## Origem

Pedido direto do usuário (31/mai/2026): *"não quero esperar meses...
quero resultado agora. vamos pegar o que temos hoje do robô que está como
referência [Hydra] e ver se dá pra fazer algo."*

Mineração do `reference_hydra/` revelou o achado-chave em
`02_ESTRATEGIAS/morta_ressuscitavel_head_02_orb.md`: o ORB (Head 2) tinha
edge **real e persistente** documentado (PSR 98.9%, PF 1.87, 8/9 janelas
rolling 3m positivas, 3/3 janelas 6m) e **morreu por slippage** — entrada
via *stop market* no rompimento paga 7.5%–15.8% do or_size de slippage no
gap, derrubando PF 1.87 → 0.94 no cenário pessimista.

A nota lista 4 caminhos de ressuscitação **nunca executados**. O caminho
#1: **migrar de stop market para LIMIT entry no trigger** — captura o move
quando o preço retorna ao nível, sem pagar o gap.

## Hipótese testada

> Se a morte do ORB foi **só** o slippage de execução (não falta de edge),
> então trocar a entrada market→limit deve preservar o edge bruto e
> eliminar a erosão por slippage, devolvendo um ORB lucrativo e estável.

## Desenho do experimento (custo zero)

Investigação preliminar gratuita prescrita pelo Conselho ANTES de
comprometer um Spec (steering `criterio-triagem-nao-persistencia`).
Isolou **uma única variável**: o modelo de execução.

- **Dados**: MNQ minute, 5 contratos concatenados, 412.593 barras,
  2025-03-17 a 2026-05-18 (~14 meses, 6 trimestres parciais).
- **Sinal**: ORB clássico (rompimento do OR). Parâmetros **congelados**
  (defaults), SEM tuning, SEM novos parâmetros otimizáveis.
- **Modelo A (market)**: entra no `close` da barra de rompimento
  (comportamento que matou o Hydra).
- **Modelo B (limit)**: arma LIMIT no nível de rompimento, preenche
  **somente** se uma barra posterior (causal) recuar e tocar o nível;
  cancela se não preencher até a hora de corte / fim de sessão.
- **Custos**: zero (edge bruto), 1 tick/lado (limit realista), e slippage
  proporcional 7.5% do or_size (modelo Hydra v1 — honesto para market).
- **Gate decisivo**: year-stability por trimestre (≥75% positivos), o
  critério que pegou a VVG e que o ORB-Hydra passava.

Dois experimentos: (1) ORB-CAOS default (OR 30min, sem filtros); (2)
config Hydra replicada (OR 9:30–9:45 ET, trigger 9:45–10:30 ET, stop=meio
do OR cap 30pts, target 2×OR_size, saída forçada 15:55 ET).

## Resultados — config Hydra replicada (a do edge persistente)

| Modelo | Custo | N | WR | PF | PnL líq | Year-stability |
|---|---|---|---|---|---|---|
| A.market | zero | 293 | 22.2% | 0.81 | −1.426 USD | 1/6 FALHA |
| A.market | slippage 0.5pt (orig Hydra) | 293 | 22.2% | 0.72 | −2.375 USD | 0/6 |
| A.market | slippage PROP 7.5% | 293 | 22.2% | 0.57 | −4.379 USD | 0/6 |
| **B.limit** | **zero** | 292 | 20.9% | **1.03** | **+168 USD** | **3/6 FALHA** |
| **B.limit** | **1 tick/lado** | 292 | 20.9% | 0.93 | −486 USD | 3/6 FALHA |
| B.limit | slippage PROP 7.5% | 292 | 20.9% | 0.68 | −2.777 USD | 0/6 |

Config ORB-CAOS default (OR 30min) deu PF bruto ~1.18–1.20 e
year-stability 3–4/6 — também FALHA.

## Leitura honesta dos resultados

1. **O fix de execução FUNCIONA.** Sem custo, market PF 0.81 (−1.426 USD)
   → limit PF 1.03 (+168 USD). A entrada limit recuperou exatamente a
   perda que o slippage de gap causava. A hipótese mecânica do Hydra
   estava **correta**.

2. **Mas o edge bruto do ORB não existe na nossa janela.** Mesmo o melhor
   caso (limit, sem custo) é PF 1.03 — empate técnico, não edge. Com 1
   tick de custo realista vira PF 0.93 (negativo). O PF 1.87 do Hydra
   veio de uma janela que a própria nota admite ser *"bull constante"*; na
   nossa janela 2025-2026 o gross edge evaporou.

3. **Year-stability falha em todos os modelos.** Q3/2025, Q1/2026 e
   Q2/2026 são negativos em praticamente todas as variantes. É a **mesma
   assinatura de não-persistência temporal** das 3 refutações anteriores
   (Crabel, P2, VVG). O edge aparece em Q1–Q2/2025 e some depois.

## Conexão com a Regra de Ouro Negativa

Este é o **4º caso** confirmando a
`[[Regra_De_Ouro_Negativa_Nao_Persistencia_MNQ_2026-05-31]]`. O ORB
parecia o candidato mais forte (edge persistente documentado no Hydra),
mas:

- O edge persistente do Hydra era **artefato da janela bull 2025**, não
  uma propriedade estrutural.
- Corrigir a fricção (limit-entry) **não cria edge onde não há** — só evita
  destruir o que existisse.
- O ORB-direcional OHLCV puro está na **mesma classe refutada** pela
  Decisão 2026-05-31-01.

## Por que isto teve valor (apesar do veredito negativo)

- **Custo zero de Spec**: o experimento usou código (`orb_logica`,
  `CustosOperacionais`) e dados já existentes. Economizou semanas que um
  Spec formal `caos-orb-limit-entry` teria consumido.
- **Fechou definitivamente** a porta "ressuscitar o ORB do Hydra via
  limit-entry". Não precisa ser reaberta.
- **Validou o modelo de custo proporcional** (`slippage_fracao_range`) num
  4º caso independente.
- **Confirmou que o critério de triagem funciona**: o ORB-limit NÃO
  demonstrava mecanismo de adaptação de regime nem edge estrutural — só
  "edge documentado em backtest" (numa janela favorável). A triagem o
  teria rejeitado; o experimento provou que a triagem estava certa.

## O que NÃO foi refutado (escopo honesto)

- Não foi rodado o pipeline Walk-Forward formal (engine/janelas/holdout) —
  foi um simulador exploratório direto. O sinal é forte o bastante
  (PF ~1.0 bruto, year-stability falhando em janela longa) para não
  justificar o custo do WF formal. Se o usuário quiser blindagem
  adicional, o próximo passo seria plugar `EstrategiaORB` no
  `WalkForwardEngine` com `CustosOperacionais.topstep_mnq()` — mas a
  expectativa, dada a evidência, é confirmação da refutação.

## Próximas portas (todas sujeitas à triagem de não-persistência)

1. **Arbitragem estatística MNQ vs ES/MES/NQ** (edge estrutural,
   independente de regime — critério #2 da triagem). **Bloqueador atual:
   só temos dados de MNQ** (`dados/` não tem ES/NQ/MES). Exigiria
   aquisição de dados.
2. **Coleta prospectiva de GEX** (aposta de meses — `[[Investigacao_Preliminar_GEX_Level2_2026-05-31]]`).
3. **Aceitar a pausa disciplinada** (default da Decisão 2026-05-31-01).

## Artefatos

- `CAOS_Orchestrator/experimento_orb_limit.py` (ORB-CAOS default).
- `CAOS_Orchestrator/experimento_orb_hydra_limit.py` (config Hydra).
- Ambos são scripts exploratórios, fora da suíte de testes (não plugáveis).
