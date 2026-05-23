---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Manolo
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-23-02-revisar-orb-com-holdout-cego.md
decisao_final:
  proposta_aceita: P1
  rationale: 'Revogo a Decisao 2026-05-23-01. O Walk-Forward 2026-05-23-03

    (com slippage+comissao + hold-out de 60 dias uteis) entrega

    Sharpe mediano 0.38 sobre 18 janelas, contra 1.31 do

    2026-05-23-02 sem hold-out. Diferenca de 0.93 pontos de Sharpe

    ao remover apenas as 6 janelas finais demonstra que o resultado

    da Decisao anterior estava carregado no periodo Mar-Mai/2026.


    Aceito a parte da P1 que revoga a Decisao anterior. REJEITO a

    parte que recomenda abandonar a familia ORB inteira — o

    Devils_Advocate aponta corretamente que a evidencia atual

    rejeita a configuracao default mas nao rejeita a tese geral

    "rompimento de abertura tem edge".


    REJEITO P2 (filtro ATR como variante imediata): adicionar

    feature correlacionada com o resultado bom ja visto e overfit

    por outro nome.


    Direcao operacional acordada (alinhada com sub-proposta informal

    do Devils_Advocate): PARAR. Sem sweeps, sem novas variantes,

    sem trocar de familia. Coletar mais 6-12 meses de dados MNQ

    conforme novos contratos chegarem (09-26, 12-26) e reabrir

    Debate em ~Q4/2026 com ~24-30 meses de historico, dos quais

    ~6-12 meses como hold-out cego maior.


    Esta Decisao REVOGA 2026-05-23-01 — a Decisao antiga permanece

    no historico Git mas perde forca operacional. Quem ler

    2026-05-23-01 deve obrigatoriamente ler tambem esta.'
identificador: 2026-05-23-02
links_zettel:
- '[[Decisao_2026-05-23-02_Revogacao_ORB_apos_holdout_cego]]'
- '[[Decisao_2026-05-23-01_Walk_Forward_ORB_Default]]'
propostas:
- autor: Mister_M
  confianca: 75
  conteudo: "Análise quantitativa cruzada das 3 execuções:\n\n- Janelas 18-23 (que\
    \ viram hold-out no -03) tiveram, no -02, PnL\n  de +200, -805, +435, +682, +97,\
    \ +629, +345 = +1583 pontos. Isso\n  representa ~52% do PnL total (+3018) sobre\
    \ apenas 25% das\n  janelas. Distribuição altamente skewed pra direita no fim\
    \ da\n  série.\n- Sharpe das janelas reservadas (calculado sobre 6 valores das\n\
    \  janelas 18-23 do -02): mediana 3.55. Sharpe das primeiras 18\n  janelas: mediana\
    \ 0.38. Diferença de quase 1 ponto inteiro de\n  Sharpe entre as duas metades.\n\
    - Razão estatística: Mar→Mai/2026 foi período de alta volatilidade\n  direcional\
    \ do Nasdaq (visível também nos contratos 03-26 e\n  06-26 do MNQ). Estratégias\
    \ breakout naturalmente performam\n  melhor em mercados trending. Não há evidência\
    \ de que a ORB\n  consegue distinguir trending de choppy — ela só apanha o regime\n\
    \  favorável quando ele aparece.\n- Em 18 janelas WF (sem o \"regime bonito\"\
    \ do final), o intervalo\n  de confiança 95% do Sharpe mediano é [-0.7, +1.5].\
    \ O zero está\n  confortavelmente dentro. NÃO podemos rejeitar H0 (Sharpe = 0).\n\
    \nConclusão minha: a Decisão `2026-05-23-01` errou. Não foi má-fé\ndo Conselho\
    \ — foi falta do hold-out cego, que agora sabemos ser\nobrigatório. Mas o veredito\
    \ honesto agora é: **EstrategiaORB com\nconfig default está REJEITADA por evidência\
    \ empírica**, não por\nataque teórico.\n\nNão recomendo sweep paramétrico nem\
    \ variantes — todas as evidências\napontam que o problema não é parâmetro, é a\
    \ tese: \"rompimento da\nabertura tem edge persistente em MNQ\". A tese provavelmente\
    \ é\nfalsa. Recomendo **mudar de família estratégica** (mean-reversion,\nfade\
    \ do gap, etc.)."
  id: P1
  resumo: Revogar Decisão 2026-05-23-01 e congelar EstrategiaORB com config default
    como "rejeitada por evidência empírica". Não fazer sweep.
- autor: Manolo
  confianca: 50
  conteudo: "Análise comportamental:\n\n- Concordo com Mister_M que `2026-05-23-01`\
    \ deve ser revogada.\n  O resultado do -03 deixa zero margem para \"aprovação\
    \ preliminar\".\n- Discordo da recomendação de abandonar a família. A queda Sharpe\n\
    \  1.31 → 0.38 é consistente com hipótese alternativa: \"ORB tem\n  edge SIM,\
    \ mas só em dias com volatilidade > X\". O resultado\n  bonito de Mar-Mai/2026\
    \ corresponde a um período objetivamente\n  mais volátil — visível na razão MFE/MAE\
    \ que sobe nessas janelas.\n- Proposta concreta e ÚNICA (não sweep): adicionar\
    \ filtro\n  `ATR_mediana_5dias > limiar` antes de aceitar entradas. ATR\n  é proxy\
    \ padrão de volatilidade e não introduz parâmetro novo\n  que precise de otimização\
    \ (mediana de 5 dias é defensável a\n  priori).\n- Validação: rodar UM Walk-Forward\
    \ com esta variante na PARTE\n  JÁ VISTA (sem tocar no hold-out de 60 dias). Se\
    \ Sharpe mediano\n  >= 0.8 nessa parte, validar no hold-out.\n- Custo: ~2-3 horas\
    \ de implementação + 1 WF de ~30s.\n\nConfiança baixa porque é tese a priori —\
    \ pode falhar como qualquer\noutra. Mas é um experimento limpo que NÃO viola o\
    \ split\ntripartite."
  id: P2
  resumo: Revogar Decisão 2026-05-23-01 mas tentar UMA variante paramétrica conservadora
    (filtro de volatilidade) antes de descartar a família.
regressao_detectada: true
reproduzivel: parcial
status: concluido
vetos: []
---

# Síntese final

Revogo a Decisao 2026-05-23-01. O Walk-Forward 2026-05-23-03
(com slippage+comissao + hold-out de 60 dias uteis) entrega
Sharpe mediano 0.38 sobre 18 janelas, contra 1.31 do
2026-05-23-02 sem hold-out. Diferenca de 0.93 pontos de Sharpe
ao remover apenas as 6 janelas finais demonstra que o resultado
da Decisao anterior estava carregado no periodo Mar-Mai/2026.

Aceito a parte da P1 que revoga a Decisao anterior. REJEITO a
parte que recomenda abandonar a familia ORB inteira — o
Devils_Advocate aponta corretamente que a evidencia atual
rejeita a configuracao default mas nao rejeita a tese geral
"rompimento de abertura tem edge".

REJEITO P2 (filtro ATR como variante imediata): adicionar
feature correlacionada com o resultado bom ja visto e overfit
por outro nome.

Direcao operacional acordada (alinhada com sub-proposta informal
do Devils_Advocate): PARAR. Sem sweeps, sem novas variantes,
sem trocar de familia. Coletar mais 6-12 meses de dados MNQ
conforme novos contratos chegarem (09-26, 12-26) e reabrir
Debate em ~Q4/2026 com ~24-30 meses de historico, dos quais
~6-12 meses como hold-out cego maior.

Esta Decisao REVOGA 2026-05-23-01 — a Decisao antiga permanece
no historico Git mas perde forca operacional. Quem ler
2026-05-23-01 deve obrigatoriamente ler tambem esta.
