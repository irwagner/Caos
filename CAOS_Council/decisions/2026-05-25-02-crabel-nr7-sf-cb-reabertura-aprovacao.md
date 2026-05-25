---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Explorador
- Manolo
- Mister_M
aprovado_walk_forward: true
debate_relacionado: 2026-05-25-02-crabel-nr7-sf-cb-reabertura-aprovacao.md
decisao_final:
  proposta_aceita: P3
  rationale: 'P3 (Mister_M) emendada por Cerberus (escala gradual obrigatoria) e Devils_Advocate

    (re-avaliar limites CB apos 30 dias). Veto bloqueante de Cerberus retirado pelas

    emendas. Sharpe +2.91 com Calmar +3.22 e janela 1 dentro do envelope Topstep apos

    CB. Pré-condições operacionais: hold-out cego 60 dias úteis prospectivos,

    MaxContratos=1 nos primeiros 30 dias, liberação 2 contratos exige 30 dias úteis

    sem trigger CB de janela ou semanal, Debate de seguimento obrigatório.'
identificador: 2026-05-25-02
links_zettel:
- '[[Walk_Forward_2026-05-25-05]]'
- '[[Walk_Forward_2026-05-25-02]]'
- '[[Walk_Forward_2026-05-25-03]]'
- '[[Decisao_2026-05-25-01]]'
- '[[Caracterizacao_Spread_MNQ_14_Meses]]'
propostas:
- autor: Explorador
  confianca: 75
  conteudo: 'Sharpe mediana +2.91 em 4 janelas WF rolantes 60+60. Calmar +3.22.

    Todos os critérios bloqueantes da Decisão 2026-05-25-01 cumpridos.

    Composição limpa: 3 overlays plugáveis com testes unitários completos.

    Reproduzível com manifest_hash registrado.'
  id: P1
  resumo: Aprovar Crabel NR7+SF+CB para hold-out cego de 60 dias úteis, sem outras
    restrições.
- autor: Manolo
  confianca: 70
  conteudo: 'Calibração atual de SF (warmup 30) e CB (limites em pontos absolutos)
    é fixa para todo

    WF — não derivada de procedimento estatístico explícito sobre o Treino. Risco
    residual

    de overfitting indireto. Validação cruzada necessária.'
  id: P2
  resumo: Aprovar somente após validação de rolling re-calibration dos parâmetros
    de SF e CB.
- autor: Mister_M
  confianca: 80
  conteudo: 'Janela 1 com CB ainda perdeu -1435 pts (USD -2870 com 1 contrato). Com
    2 contratos

    seria USD -5740, estourando trailing DD Topstep. Não há margem para 2 contratos.

    Liberação para MaxContratos=2 exige 30 dias úteis sem trigger de CB de janela
    ou semanal.'
  id: P3
  resumo: Aprovar P1 com escala gradual MaxContratos=1 nos primeiros 30 dias úteis.
regressao_detectada: false
reproduzivel: 'true'
status: concluido
vetos:
- autor: Cerberus
  decisao: bloquear
  justificativa: 'Janela 1 do WF 2026-05-25-05 perdeu -1435 pts = USD -2870 com 1
    contrato.

    Topstep trailing drawdown típico USD -2500. Margem negativa USD -370.

    Em regime adverso com perdas consistentes pequenas, trailing DD pode ser

    atingido sem trigger explícito de CB diário/semanal/janela. Aprovar P1

    sem escala gradual viola limite de exposição compatível com a corretora alvo.'
  proposta_alvo: P1
  tipo: veto_de_risco
---

# Síntese final

P3 (Mister_M) emendada por Cerberus (escala gradual obrigatoria) e Devils_Advocate
(re-avaliar limites CB apos 30 dias). Veto bloqueante de Cerberus retirado pelas
emendas. Sharpe +2.91 com Calmar +3.22 e janela 1 dentro do envelope Topstep apos
CB. Pré-condições operacionais: hold-out cego 60 dias úteis prospectivos,
MaxContratos=1 nos primeiros 30 dias, liberação 2 contratos exige 30 dias úteis
sem trigger CB de janela ou semanal, Debate de seguimento obrigatório.
