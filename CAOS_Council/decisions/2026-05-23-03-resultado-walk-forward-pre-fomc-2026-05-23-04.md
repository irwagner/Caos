---
agentes_participantes:
- Athena
- Devils_Advocate
- Manolo
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-23-03-resultado-walk-forward-pre-fomc-2026-05-23-04.md
decisao_final:
  proposta_aceita: P2
  rationale: 'Resultado preliminar do WF Pre-FOMC drift (8 trades, +12 pts

    liquidos sobre 12 meses) e'' estatisticamente fraco (N=131 no

    paper, N=8 aqui). Antes de qualquer continuacao investigativa

    (P1) ou desistencia precoce, P2 propoe inspecao manual barata

    dos 8 trades para validar se a implementacao esta CORRETA.

    Devils_Advocate confirma que esta e'' a acao mais honesta.


    Aceito P2 com criterio formal de validacao: ao menos 7 dos 8

    trades devem ter entrada_timestamp em dia util de calendario NY

    imediatamente anterior a uma data FOMC, e saida_timestamp na

    tarde do dia FOMC. Se >= 7 baterem, implementacao OK e o

    resultado neutro vai para arquivo aguardando mais dados (~Q4/2026

    apos novos contratos chegarem). Se < 7 baterem, abre Debate

    dedicado a refatorar.


    Nao aprovo Walk-Forward para paper trading. Nao aprovo filtros

    ou variantes (P1) ate que (a) implementacao seja validada e

    (b) amostra cresca para >= 30 trades.


    Esta e'' decisao registrada de PAUSA investigativa, nao de

    desistencia. Diferente da Decisao 2026-05-23-02 (rejeicao da

    ORB por evidencia empirica), aqui a evidencia e'' insuficiente

    pra qualquer veredito empirico.'
identificador: 2026-05-23-03
links_zettel:
- '[[Decisao_2026-05-23-03_Pausa_Investigativa_Pre_FOMC]]'
- '[[briefing-explorador-2026-05-23-orb-rejeitada-direcoes-com-edge]]'
propostas:
- autor: Mister_M
  confianca: 50
  conteudo: "Análise do que temos:\n\n- 8 trades sobre 12 meses úteis. Lucca-Moench\
    \ (1994-2024) trabalham\n  com N=131-200+ meetings. Nossa amostra é 4-6% disso.\n\
    - PnL acumulado liquido +12 pts × USD 2 = +USD 24. Bruto seria\n  ~+22 pts (custo\
    \ total = 8 trades × 1.12 pts/trade ≈ -9 pts).\n  Ainda positivo bruto, mas insignificante.\n\
    - Win rate 62.5% (5/8) é compatível com a literatura (Lucca-Moench\n  reportam\
    \ efeito presente mas não 100% de win rate).\n- O único trade catastrófico (-449\
    \ pts na janela 3) é compatível\n  com o achado de QuantSeeker (2025) de que o\
    \ efeito é mais forte\n  em VIX alto e desaparece em VIX baixo. Não temos VIX\
    \ integrado\n  aqui — pode ser um meeting com VIX baixo.\n- Sharpe das janelas\
    \ (7.49 mediano) NÃO É confiável com N=2 trades\n  por janela. Métrica certa aqui\
    \ é PnL acumulado total.\n\nRecomendação: continuar investigando. Não desistir\
    \ com 8 trades\nporque isso é baixíssimo poder estatístico — e a literatura externa\n\
    é robusta. Próximo passo deveria ser: (a) integrar dados de VIX no\ncaracterizador,\
    \ (b) re-rodar restringindo aos meetings com VIX no\nquartil superior na entrada\
    \ (paramétrico, mas o limiar VIX>P75\nvem de Lucca-Moench, não otimizado), (c)\
    \ coletar mais 18-24 meses\nde dados quando contratos novos chegarem (09-26, 12-26,\
    \ 03-27...).\n\nNÃO recomendo paper trading nesta amostra."
  id: P1
  resumo: Continuar investigando Pre-FOMC drift; coletar mais 18-24 meses de dados
    antes de WF definitivo; não promover a paper.
- autor: Manolo
  confianca: 60
  conteudo: "Análise comportamental:\n\n- O paper Lucca-Moench reporta **CAGR ~4%\
    \ no SPY** com a estratégia\n  long-flat. Em 12 meses isso seria ~4% sobre o capital\
    \ alocado.\n- Nosso resultado: +12 pts × USD 2 = USD 24 sobre 12 meses. Em uma\n\
    \  conta com USD 10.000 (margem MNQ típica), isso é 0.24% — muito\n  abaixo dos\
    \ 4% reportados.\n- A diferença pode vir de 3 fontes: (a) MNQ é Nasdaq-100, paper\n\
    \  testa SPY (S&P 500); (b) paper testa close[D-1] → close[D],\n  nossa implementação\
    \ faz isso mas com base no calendário UTC\n  (close NY ≠ close UTC). MNQ futures\
    \ fecha 17h ET = 21h UTC; pode\n  estar pegando o close 21:00 UTC do dia D-1 BRT\
    \ errado se houver\n  deslocamento; (c) custos: paper assume 5bps; nós assumimos\
    \ 1.12\n  pts por contrato (~5bps em preço de 25000 = 22 pts → equivale).\n  Custo\
    \ está no mesmo nível.\n- Hipótese: PODE haver bug de fuso na implementação. Quando\n\
    \  convertemos os timestamps NT8 (BRT) para UTC, o \"close do dia\"\n  vira 24:00\
    \ UTC = 00:00 do DIA SEGUINTE. Isso deslocaria todos os\n  trades em 1 dia.\n\
    - Validação proposta: (1) inspecionar manualmente os 8 trades\n  emitidos — checar\
    \ entrada/saída em data civil. (2) Se data civil\n  bate com calendário NY, o\
    \ resultado é defensável. Se não bate,\n  REIMPLEMENTAR.\n\nRecomendação: pausa\
    \ investigativa, não decisão prematura. Olhar os\ntrades crus."
  id: P2
  resumo: Antes de buscar mais dados, validar se a implementação está CORRETA — comparar
    com baseline do paper original.
regressao_detectada: false
reproduzivel: parcial
status: concluido
vetos: []
---

# Síntese final

Resultado preliminar do WF Pre-FOMC drift (8 trades, +12 pts
liquidos sobre 12 meses) e' estatisticamente fraco (N=131 no
paper, N=8 aqui). Antes de qualquer continuacao investigativa
(P1) ou desistencia precoce, P2 propoe inspecao manual barata
dos 8 trades para validar se a implementacao esta CORRETA.
Devils_Advocate confirma que esta e' a acao mais honesta.

Aceito P2 com criterio formal de validacao: ao menos 7 dos 8
trades devem ter entrada_timestamp em dia util de calendario NY
imediatamente anterior a uma data FOMC, e saida_timestamp na
tarde do dia FOMC. Se >= 7 baterem, implementacao OK e o
resultado neutro vai para arquivo aguardando mais dados (~Q4/2026
apos novos contratos chegarem). Se < 7 baterem, abre Debate
dedicado a refatorar.

Nao aprovo Walk-Forward para paper trading. Nao aprovo filtros
ou variantes (P1) ate que (a) implementacao seja validada e
(b) amostra cresca para >= 30 trades.

Esta e' decisao registrada de PAUSA investigativa, nao de
desistencia. Diferente da Decisao 2026-05-23-02 (rejeicao da
ORB por evidencia empirica), aqui a evidencia e' insuficiente
pra qualquer veredito empirico.
