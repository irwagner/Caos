---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Manolo
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-23-01-resultado-walk-forward-orb-2026-05-22-01.md
decisao_final:
  proposta_aceita: P1
  rationale: 'EstrategiaORB com configuração default sobre 17 meses de MNQ minute

    (5 contratos, 24 janelas WF) entrega Sharpe mediano 1.42 e PnL

    acumulado +3085 pontos × contratos. Quórum atingido, sem vetos

    bloqueantes. Devils_Advocate aponta corretamente que (a) sem

    slippage/comissão modelados o resultado é otimista, (b) z-score

    2.4 não sobrevive a correção de Bonferroni para múltiplas

    estratégias, (c) drawdown 100% intra-janela em 67% das janelas é

    comportamentalmente insustentável. Aceito P1 como proposta

    vencedora (registrar resultado como evidência preliminar) MAS

    declaro `aprovado_walk_forward=false` — esta Decisão não autoriza

    paper trading nem promove a estratégia. Próximo Debate sobre ORB

    deve (1) reprocessar o WF com fricção de execução modelada

    (slippage + comissão), (2) declarar `altera_exposicao=true` para

    ativar avaliação formal de Cerberus, (3) ANTES de qualquer sweep

    paramétrico, isolar 20% dos dados como hold-out cego (split

    treino/validação/teste tripartite).'
identificador: 2026-05-23-01
links_zettel:
- '[[Decisao_2026-05-23-01_Walk_Forward_ORB_Default]]'
propostas:
- autor: Mister_M
  confianca: 55
  conteudo: "Análise quantitativa dos 24 resultados:\n\n- Sharpe mediano de 1.42 sobre\
    \ 24 janelas independentes é\n  estatisticamente acima de zero (z-score aproximado\
    \ ≈ 2.4 sob a\n  hipótese nula H0: Sharpe verdadeiro = 0, considerando desvio\n\
    \  padrão amostral dos Sharpes ≈ 4.3). Mas o intervalo de confiança\n  95% é largo:\
    \ [0.0, 3.4]. Não dá para rejeitar H0 com folga.\n- PnL acumulado de +3085 pontos\
    \ × contratos sobre ~12 meses úteis\n  em 5 contratos diferentes — robustez razoável\
    \ a regimes\n  distintos (bull/bear/lateral cobertos).\n- Distribuição dos PnLs\
    \ por janela: 16 ganhos (média +458),\n  8 perdas (média -384). Razão win/loss\
    \ em magnitude = 1.19,\n  consistente com payoff_medio mediano de 1.17.\n- 5 janelas\
    \ com Sharpe < -2.5 são preocupantes mas não\n  catastróficas: as perdas das 8\
    \ janelas vermelhas representam\n  -3.066 pontos × contratos, quase canceladas\
    \ pelos +6.151 das\n  janelas verdes.\n- **Insuficiência amostral**: 24 janelas\
    \ é o mínimo aceitável\n  (R3.2 do Spec 2). Para conclusão sólida precisaríamos\
    \ de\n  50-100 janelas (~20-40 meses de dados). Hoje temos ~17 meses.\n\nRecomendação:\
    \ **aprovar como evidência preliminar**, NÃO promover\na paper trading nem real,\
    \ e coletar mais dados antes de revisitar."
  id: P1
  resumo: Aprovar EstrategiaORB para Walk-Forward consolidado mas NÃO promover a paper
    trading; coletar mais 6 meses de dados antes de re-avaliar.
- autor: Manolo
  confianca: 70
  conteudo: "Análise comportamental do resultado:\n\n- **Drawdown máximo de 100% em\
    \ 67% das janelas** é um sinal de\n  alerta gravíssimo. Significa que o trader\
    \ que opera essa\n  estratégia vê, dentro de cada bloco de 10 dias úteis, momentos\n\
    \  em que TODO o lucro acumulado evapora. Mesmo que a janela feche\n  positiva,\
    \ o caminho é insustentável psicologicamente.\n- Win rate de 50.0% mediano é a\
    \ definição literal de coin flip.\n  Estratégias ORB clássicas trabalham com 35-45%\
    \ win e payoff\n  2.5-3.0 (cauda direita gorda). Nossa ORB tem payoff 1.17 — está\n\
    \  saindo do trade cedo demais ou entrando tarde demais.\n- Janela 4: -547 pontos\
    \ × contratos (-$1.095). Janela 10: -935\n  (-$1.870). Janela 18: -795 (-$1.590).\
    \ Três janelas concentram\n  -$4.555 — quase o dobro do PnL acumulado total. Cauda\n\
    \  esquerda extremamente gorda; o sistema é frágil a sequências\n  ruins.\n- O\
    \ parâmetro `RangeMinimoPontos=10` foi escolhido sem otimização.\n  Pode estar\
    \ pegando dias de baixa volatilidade onde o range é\n  formado mas o rompimento\
    \ é fraco.\n- O parâmetro `AlvoMultiplicador=2.0` (alvo = 2x stop) é teórico\n\
    \  mas a razão MFE_medio/MAE_medio é 1.05 — o trade médio mal sai\n  do empate.\
    \ O alvo 2.0 raramente é atingido.\n\nRecomendação: **reprovar a config default**.\
    \ Antes de aprovar a\nestratégia, abrir Debates dedicados a sweep de:\n1. RangeMinimoPontos\
    \ ∈ {5, 10, 15, 20, 25}.\n2. AlvoMultiplicador ∈ {1.0, 1.5, 2.0, 2.5, 3.0}.\n\
    3. Janela_Sessao_RTH (testar 09:30-12:00 vs 09:30-16:00).\nCada sweep com Walk-Forward\
    \ separado para evitar overfit cruzado."
  id: P2
  resumo: Reprovar EstrategiaORB com config default; abrir variantes paramétricas
    antes de qualquer aprovação.
regressao_detectada: false
reproduzivel: parcial
status: concluido
vetos: []
---

# Síntese final

EstrategiaORB com configuração default sobre 17 meses de MNQ minute
(5 contratos, 24 janelas WF) entrega Sharpe mediano 1.42 e PnL
acumulado +3085 pontos × contratos. Quórum atingido, sem vetos
bloqueantes. Devils_Advocate aponta corretamente que (a) sem
slippage/comissão modelados o resultado é otimista, (b) z-score
2.4 não sobrevive a correção de Bonferroni para múltiplas
estratégias, (c) drawdown 100% intra-janela em 67% das janelas é
comportamentalmente insustentável. Aceito P1 como proposta
vencedora (registrar resultado como evidência preliminar) MAS
declaro `aprovado_walk_forward=false` — esta Decisão não autoriza
paper trading nem promove a estratégia. Próximo Debate sobre ORB
deve (1) reprocessar o WF com fricção de execução modelada
(slippage + comissão), (2) declarar `altera_exposicao=true` para
ativar avaliação formal de Cerberus, (3) ANTES de qualquer sweep
paramétrico, isolar 20% dos dados como hold-out cego (split
treino/validação/teste tripartite).
