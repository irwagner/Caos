---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Explorador
- Mister_M
- Odin
aprovado_walk_forward: false
debate_relacionado: 2026-05-31-01-rumo-do-pipeline-apos-tres-refutacoes.md
decisao_final:
  proposta_aceita: P2
  rationale: "Apos 3 refutacoes consecutivas (Crabel via overfit-ao-WF; P2 via\nnao-estacionariedade;\
    \ VVG via falta de year-stability), o Conselho\nidentifica a CAUSA-RAIZ COMUM:\
    \ nao-persistencia temporal (regime-\ndependencia) dos edges OHLCV-direcionais\
    \ no MNQ minute. Mister_M\nprovou que detectar edge incondicional exige N~78.000\
    \ trades\n(inalcancavel); Odin explicou a mecanica (0DTE gamma oscilando);\nDevils_Advocate\
    \ corrigiu o escopo (a causa nao e' edge pequeno, e'\nnao-persistencia); Cerberus\
    \ graduou o risco de recurso.\n\nDecisao: aceitar P2 (consolidar a evidencia negativa)\
    \ emendada:\n(1) documentar a \"Regra de Ouro Negativa\" como artefato permanente\n\
    \    (Zettel + steering);\n(2) criar criterio de triagem reforcado (R12+): candidato\
    \ futuro\n    DEVE demonstrar como ataca a nao-persistencia temporal, ou e'\n\
    \    rejeitado sem gastar Spec;\n(3) P3 (adquirir GEX/Level 2) fica como investigacao\
    \ preliminar\n    GRATUITA sob veto condicional do Cerberus — so vira Spec se\
    \ o\n    dado for obtenivel/confiavel/barato;\n(4) pipeline de estrategias OHLCV-direcionais\
    \ PAUSADO — onus da\n    prova invertido.\n\nNao e' desistencia: e' disciplina\
    \ anti-vies-de-acao. Documentar o\nque NAO funciona e' valor permanente e evita\
    \ gastar ciclos numa 4a\nrefutacao previsivel."
identificador: 2026-05-31-01
links_zettel:
- '[[Refutacao_VVG_Late_Session_2026-05-29]]'
- '[[Refutacao_P2_Range_Absoluto_2026-05-29]]'
- '[[Re_Replay_Pos_Fix_Warmup_2026-05-29]]'
propostas:
- autor: Explorador
  confianca: 60
  conteudo: 'Os 3 grupos de candidatos remanescentes têm evidencia negativa:

    direcionais OHLCV (teto 1.5 pts, arXiv 2605.04004), calendar

    anomalies (documentadas como desaparecendo), order flow (exige

    book depth que NT8 nao exporta). Continuar triando a shopping-list

    e'' caçar em poço seco. Mudar de classe de problema exige dado novo

    (book depth/GEX) que nao temos. Sem dado novo, B degenera em C

    (pausar e consolidar).'
  id: P1
  resumo: Mudar de classe de problema — a shopping-list está esgotada como fonte de
    edge direcional OHLCV; o que resta exige dado que não temos (book depth, GEX).
- autor: Mister_M
  confianca: 74
  conteudo: 'As 3 refutacoes falharam por modos distintos (overfit ao WF;

    nao-estacionariedade; falta de year-stability) — nao e'' azar,

    e'' a assinatura de um mercado eficiente onde edges OHLCV sao

    transitorios. Calculo de poder: detectar edge liquido de ~0.5

    pts/trade com sd ~50 exigiria N ~78.000 trades, inalcancavel.

    Consolidar isso como "regra de ouro negativa" permanente: futuro

    candidato precisa superar esse teorema de impossibilidade pratico

    com dado/mecanismo novo, ou e'' rejeitado na triagem sem gastar Spec.'
  id: P2
  resumo: Consolidar formalmente a regra de ouro negativa — edges direcionais OHLCV
    no MNQ minute são estatisticamente indetectaveis com o N gerável sob fricção Topstep.
    Vira critério de triagem.
- autor: Odin
  confianca: 58
  conteudo: 'Mudancas estruturais do MNQ 2026 (0DTE >50% do volume, algos

    comprimindo edges OHLCV, mean-reversion retail nao-estacionaria

    dependente de gamma) implicam que edge remanescente plausivel

    depende de medir GEX ou book depth Level 2. Proponho Spec de

    AQUISICAO e validacao desse dado (CBOE GEX feed, ou reconstrucao

    de DOM com config diferente do sniffer que falhou) antes de mais

    estrategia. Se o dado for obtenivel/confiavel, destrava classe

    nova; se nao, fecha a porta com honestidade e vai-se para C.'
  id: P3
  resumo: Adquirir o dado que falta (GEX/Level 2) antes de mais estratégia — todo
    edge remanescente plausível depende de medir regime de gamma ou book depth, que
    hoje não temos.
regressao_detectada: false
reproduzivel: 'true'
status: concluido
vetos: []
---

# Síntese final

Apos 3 refutacoes consecutivas (Crabel via overfit-ao-WF; P2 via
nao-estacionariedade; VVG via falta de year-stability), o Conselho
identifica a CAUSA-RAIZ COMUM: nao-persistencia temporal (regime-
dependencia) dos edges OHLCV-direcionais no MNQ minute. Mister_M
provou que detectar edge incondicional exige N~78.000 trades
(inalcancavel); Odin explicou a mecanica (0DTE gamma oscilando);
Devils_Advocate corrigiu o escopo (a causa nao e' edge pequeno, e'
nao-persistencia); Cerberus graduou o risco de recurso.

Decisao: aceitar P2 (consolidar a evidencia negativa) emendada:
(1) documentar a "Regra de Ouro Negativa" como artefato permanente
    (Zettel + steering);
(2) criar criterio de triagem reforcado (R12+): candidato futuro
    DEVE demonstrar como ataca a nao-persistencia temporal, ou e'
    rejeitado sem gastar Spec;
(3) P3 (adquirir GEX/Level 2) fica como investigacao preliminar
    GRATUITA sob veto condicional do Cerberus — so vira Spec se o
    dado for obtenivel/confiavel/barato;
(4) pipeline de estrategias OHLCV-direcionais PAUSADO — onus da
    prova invertido.

Nao e' desistencia: e' disciplina anti-vies-de-acao. Documentar o
que NAO funciona e' valor permanente e evita gastar ciclos numa 4a
refutacao previsivel.
