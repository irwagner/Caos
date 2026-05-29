---
agentes_participantes:
- Athena
- Devils_Advocate
- Explorador
- Hermes
- Manolo
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-29-01-descarte-ou-reengenharia-crabel-nr7-orb-sf-cb.md
decisao_final:
  proposta_aceita: P2
  rationale: "Usuario decide caminho B (re-engenharia minima P2) com clausula de\n\
    fallback automatico para A (descarte) caso o teste do B falhe pelos\ncriterios\
    \ quantitativos pre-registrados abaixo.\n\nImplementacao P2:\n(1) Adicionar parametro\
    \ discreto `modo_nr` em EstrategiaCrabelLogica\n    com valores {nr7, range_absoluto}.\
    \ Default permanece `nr7` para\n    nao quebrar Decisoes anteriores.\n(2) Adicionar\
    \ logica de filtro `range_absoluto`: dia D eh elegivel\n    se (High[D-1] - Low[D-1])\
    \ <= 80 ticks (= 20 pontos no MNQ).\n    K=80 ticks congelado em codigo (regra\
    \ anti-overfit).\n(3) Calibrar K em janela 2025-01-01 a 2025-06-30 (separada do\
    \ WF\n    original que usou 2025-07-01 a 2026-05-15). Validar K=80\n    reproduz\
    \ Sharpe >= 1.0 nessa janela isolada.\n(4) Porta Python espelho em caos/walk_forward/estrategias/orb_crabel.py.\n\
    (5) Whitelist NinjaScript: sem mudanca (High[1], Low[1], TickSize ja\n    autorizadas).\n\
    \nCriterios quantitativos pre-registrados (Cerberus impoe; cruzar\nqualquer um\
    \ dispara fallback A):\n- WF longo de validacao (60+10 anchored, 2025-07 a 2026-05)\
    \ com\n  Sharpe mediana >= 1.0 e Calmar mediana >= 1.5;\n- Replay NT8 em 2026-06+\
    \ (dados que NAO entraram no WF) com\n  PnL >= -USD 100 em 30 dias uteis (escala\
    \ proporcional ao\n  criterio anterior);\n- Paridade Python<->C# trade-a-trade\
    \ dentro de 5% nessa janela.\n\nFalha em qualquer criterio ativa fallback A: arquivar\
    \ estrategia\nem 02_ESTRATEGIAS/mortas/ com nota Zettel registrando o caminho\n\
    completo (P2 testada e refutada).\n\nTag caos-frozen-2026-05-25-02 permanece SUSPENSA\
    \ ate proxima\nDecisao com aprovado_walk_forward=true (apenas se P2 passar todos\n\
    os criterios acima)."
identificador: 2026-05-29-01
links_zettel:
- '[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]'
- '[[Bug_Paridade_Warmup_NR7_2026-05-28]]'
- '[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]'
propostas:
- autor: Explorador
  confianca: 55
  conteudo: 'Re-replay 28/01-26/05/2026 do MNQ 06-26 confirma: estrategia nao

    tem edge fora da janela de WF original. Win-rate 36,4% em mercado

    tendencial recente, MFE/MAE 0,74 (assimetrico desfavoravel) — sintomas

    classicos de overfit ao WF de caracterizacao. Acao: arquivar em

    02_ESTRATEGIAS/mortas/, abrir Spec novo "caos-momentum-probabilistico-mnq"

    com Walk-Forward longo em paralelo. Tres papers do shopping-list

    NotebookLM atendem R12 (arXiv 2605.04004, Quantitativo Substack,

    arXiv 2508.06788). Custo: ~3 semanas de Conselho.'
  id: P1
  resumo: Descartar a estrategia atual e iniciar pipeline de nova candidata a partir
    de paper academico que atenda filtro R12.
- autor: Manolo
  confianca: 68
  conteudo: 'Bug de paridade Python<->C# tem causa raiz estrutural: NR7 exige

    saber "este dia tem o menor range dos 7 dias anteriores", e isso

    quebra quando NT8 troca contrato em playback. Filtro de range

    absoluto resolve: dia eh elegivel se (High[1] - Low[1]) <= 80

    ticks (= 20 pontos no MNQ). Nao depende de janela, paridade

    Python<->C# trivial. K congelado em codigo, sem novo tunable

    (regra anti-overfit). Manter ORB + SpreadFilter + CircuitBreaker

    inalterados. Custo: ~30-50 linhas em EstrategiaCrabelLogica.cs +

    porta Python espelho. Novo WF longo de validacao obrigatorio.'
  id: P2
  resumo: Re-engenharia minima — substituir filtro NR7 por filtro de range absoluto
    fixo K=80 ticks (sem dependencia de janela).
- autor: Mister_M
  confianca: 72
  conteudo: '11 trades NAO eh amostra valida para concluir descarte. IC95% sobre

    PnL total fica em [-USD 1.700, +USD 553] — cruza zero. O proprio

    re-replay 28/01-26/05 tem warmup insuficiente (Days to load do

    chart cobriu so ~43 dias uteis), invalidando o teste do

    BarsRequiredToTrade=19320. Caminho: refazer replay sobre 252 dias

    uteis (2025-05 -> 2026-05) com chart configurado para Days to

    load = 270+. N esperado: 30-50 trades. Criterio Cerberus calibrado

    proporcionalmente: PnL >= -USD 250 retoma; <= -USD 1.250 descarte.

    Custo: 1-2 dias.'
  id: P3
  resumo: Refazer hold-out com janela de 252 dias uteis (1 ano) sobre dados ja existentes;
    N=11 do replay e estatisticamente irrelevante.
regressao_detectada: true
reproduzivel: 'true'
status: concluido
vetos: []
---

# Síntese final

Usuario decide caminho B (re-engenharia minima P2) com clausula de
fallback automatico para A (descarte) caso o teste do B falhe pelos
criterios quantitativos pre-registrados abaixo.

Implementacao P2:
(1) Adicionar parametro discreto `modo_nr` em EstrategiaCrabelLogica
    com valores {nr7, range_absoluto}. Default permanece `nr7` para
    nao quebrar Decisoes anteriores.
(2) Adicionar logica de filtro `range_absoluto`: dia D eh elegivel
    se (High[D-1] - Low[D-1]) <= 80 ticks (= 20 pontos no MNQ).
    K=80 ticks congelado em codigo (regra anti-overfit).
(3) Calibrar K em janela 2025-01-01 a 2025-06-30 (separada do WF
    original que usou 2025-07-01 a 2026-05-15). Validar K=80
    reproduz Sharpe >= 1.0 nessa janela isolada.
(4) Porta Python espelho em caos/walk_forward/estrategias/orb_crabel.py.
(5) Whitelist NinjaScript: sem mudanca (High[1], Low[1], TickSize ja
    autorizadas).

Criterios quantitativos pre-registrados (Cerberus impoe; cruzar
qualquer um dispara fallback A):
- WF longo de validacao (60+10 anchored, 2025-07 a 2026-05) com
  Sharpe mediana >= 1.0 e Calmar mediana >= 1.5;
- Replay NT8 em 2026-06+ (dados que NAO entraram no WF) com
  PnL >= -USD 100 em 30 dias uteis (escala proporcional ao
  criterio anterior);
- Paridade Python<->C# trade-a-trade dentro de 5% nessa janela.

Falha em qualquer criterio ativa fallback A: arquivar estrategia
em 02_ESTRATEGIAS/mortas/ com nota Zettel registrando o caminho
completo (P2 testada e refutada).

Tag caos-frozen-2026-05-25-02 permanece SUSPENSA ate proxima
Decisao com aprovado_walk_forward=true (apenas se P2 passar todos
os criterios acima).
