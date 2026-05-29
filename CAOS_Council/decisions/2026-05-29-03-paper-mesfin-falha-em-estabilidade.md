---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Explorador
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-29-03-paper-mesfin-falha-em-estabilidade.md
decisao_final:
  proposta_aceita: P1
  rationale: "Acolhimento de emendas a Decisao 2026-05-29-02 apos descoberta\nno abstract\
    \ do paper Mesfin (arXiv 2605.11423) de que o autor\nclassifica todas as estrategias\
    \ direcionais testadas como\n\"fails year-stability criteria\". Argumento (1)\
    \ original do\nExplorador na Decisao 2026-05-29-02 (\"paper com edge positivo\n\
    documentado\") estava factualmente errado — Explorador admite.\n\nDecisao mantem\
    \ implementacao de P1 (VVG Late-Session Reversal\nno MNQ) MAS com tres emendas\
    \ pre-registradas:\n(a) Year-stability: Sharpe positivo em >= 3/4 trimestres da\n\
    \    janela WF (extensao do Explorador);\n(b) T-statistic >= 2.0 sobre PnL/trade\
    \ no replay 2026-06+,\n    hold-out estendido para 60 dias uteis (extensao do\n\
    \    Mister_M);\n(c) MaxContratos = 1 fixo permanente, nao evoluir para 2.\n\n\
    Decisao reconhece custo elevado de potencialmente refutar\nestrategia que o autor\
    \ original ja diagnosticou como falha,\nmas aceita esse custo em troca de:\n-\
    \ Aprendizado empirico sobre regime atual do MNQ\n- Pipeline em movimento ao inves\
    \ de ocioso\n- Cobertura completa do critico (P3) com IC95%\n  estatistica\n\n\
    Cerberus emite Veto_De_Risco condicional ja satisfeito pelos\ncriterios pre-registrados.\n\
    \nTag caos-frozen permanece SUSPENSA ate validacao formal\ncompleta de P1+P3."
identificador: 2026-05-29-03
links_zettel:
- '[[Decisao_2026-05-29-02_Triagem_Shopping_List_Papers]]'
- '[[Etapa_Zero_NotebookLM_Gemini_2026-05-29]]'
propostas:
- autor: Explorador
  confianca: 65
  conteudo: 'Aceitar que o paper Mesfin diz "fails year-stability" mas

    argumentar que os criterios de "validacao institucional" do

    paper sao incomparaveis ao perfil Topstep (1 contrato, AUM

    individual). Manter implementacao da P1 da Decisao

    2026-05-29-02 com tres modificacoes pre-registradas:

    (a) Sharpe positivo em >= 3/4 anos da janela WF;

    (b) hold-out de 60 dias uteis (nao 30) para acomodar curtose;

    (c) MaxContratos=1 fixo permanente (nao evoluir para 2).

    Custo: 4-6 semanas. Aceitar que pode falhar pelo proprio

    diagnostico do autor.'
  id: P1
  resumo: Manter P1 da Decisao 2026-05-29-02 com criterios MAIS rigorosos pre-registrados
    (year-stability >= 3/4 anos, hold-out 60 dias, 1 contrato fixo permanente).
- autor: Explorador
  confianca: 50
  conteudo: 'Voltar a shopping-list e procurar paper que mencione

    year-stability ou criterio institucional positivo no abstract.

    Beat the Market (SSRN 4824172) Sharpe 1.33 em 2007-2024 eh

    candidato natural. Risco: SPY ETF, nao MNQ futuro — adaptacao

    exige trabalho de pesquisa sem garantia de portabilidade.

    Custo: 6-8 semanas.'
  id: P2
  resumo: Re-triar a shopping-list com olho critico em year-stability; candidato alternativo
    seria Beat the Market (SSRN 4824172) com Sharpe 1.33 em 17 anos (2007-2024).
- autor: Mister_M
  confianca: 70
  conteudo: 'T=1.46 do paper Mesfin gera IC95% que cruza zero. O CAOS

    precisa de mais rigor. Adicionar como criterio Cerberus

    pre-registrado: no replay 2026-06+ exigir T >= 2.0 (= IC95%

    estritamente positivo). Aplicado sobre P1 modificada de

    Explorador (year-stability >= 3/4 anos, hold-out 60 dias,

    1 contrato fixo). Custo zero adicional — apenas calculo

    estatistico no relatorio do replay.'
  id: P3
  resumo: Aceitar P1 + adicionar criterio estatistico T >= 2.0 (IC95% positivo) no
    replay 2026-06+.
regressao_detectada: false
reproduzivel: 'true'
status: concluido
vetos: []
---

# Síntese final

Acolhimento de emendas a Decisao 2026-05-29-02 apos descoberta
no abstract do paper Mesfin (arXiv 2605.11423) de que o autor
classifica todas as estrategias direcionais testadas como
"fails year-stability criteria". Argumento (1) original do
Explorador na Decisao 2026-05-29-02 ("paper com edge positivo
documentado") estava factualmente errado — Explorador admite.

Decisao mantem implementacao de P1 (VVG Late-Session Reversal
no MNQ) MAS com tres emendas pre-registradas:
(a) Year-stability: Sharpe positivo em >= 3/4 trimestres da
    janela WF (extensao do Explorador);
(b) T-statistic >= 2.0 sobre PnL/trade no replay 2026-06+,
    hold-out estendido para 60 dias uteis (extensao do
    Mister_M);
(c) MaxContratos = 1 fixo permanente, nao evoluir para 2.

Decisao reconhece custo elevado de potencialmente refutar
estrategia que o autor original ja diagnosticou como falha,
mas aceita esse custo em troca de:
- Aprendizado empirico sobre regime atual do MNQ
- Pipeline em movimento ao inves de ocioso
- Cobertura completa do critico (P3) com IC95%
  estatistica

Cerberus emite Veto_De_Risco condicional ja satisfeito pelos
criterios pre-registrados.

Tag caos-frozen permanece SUSPENSA ate validacao formal
completa de P1+P3.
