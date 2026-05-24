---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Manolo
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-24-01-revalidacao-orb-slippage-proporcional-e-crabel-nr.md
decisao_final:
  proposta_aceita: P2
  rationale: "Resultados materiais desta sessao:\n\n1. ORB original sob slippage proporcional\
    \ realista (modelo\n   Hydra v1 / Pomorski 2024) entrega -USD 13.719 em 13 meses.\n\
    \   CONFIRMA a Decisao 2026-05-23-02 (rejeicao da ORB).\n   Slippage fixo Topstep\
    \ (-USD 5.642 positivo) era otimista.\n\n2. ORB Crabel NR7 (variante de Crabel\
    \ 1990 que o Hydra v1 NAO\n   testou) entrega +USD 474 em 35 trades sobre os mesmos\
    \ dados.\n   E' a unica ORB com PnL liquido positivo sob fricao honesta.\n   PnL\
    \ modesto e amostra fraca (N=35) — nao passa criterio\n   institucional Mesfin\
    \ 2026 (T>=2.0).\n\nAceito P2: executar analise de correlacao entre trades da\n\
    Crabel NR7 e da Pre-FOMC drift para informar decisao futura\nsobre mini-portfolio.\
    \ Custo trivial, valor informacional real.\n\nREJEITO P1 nao porque seja errada\
    \ mas porque P2 e' superset:\nfaz a analise barata DE GRACA antes de \"registrar\
    \ e esperar\".\n\nIndependente do resultado da correlacao:\n- aprovado_walk_forward\
    \ = false permanece\n- pausa investigativa de 2026-05-23-02 permanece valida\n\
    - 3 candidatas documentadas para revisita futura: Pre-FOMC\n  drift, Crabel NR7\
    \ ORB, e mini-portfolio condicional\n\nAdicao estrutural CustosOperacionais.slippage_fracao_range\n\
    (modelo proporcional) permanece util independente do veredito\nsobre familias\
    \ estrategicas — beneficia toda revalidacao\nfutura.\n\nLicao de metodo: o Hydra\
    \ v1 testou variantes proprias da ORB\nmas NAO testou a versao classica de Crabel\
    \ com NR4/NR7.\nDocumentar para garantir que proximas iteracoes testam\nvariantes\
    \ consagradas da literatura ANTES de criar versoes\nproprias."
identificador: 2026-05-24-01
links_zettel:
- '[[Decisao_2026-05-24-01_Crabel_NR7_Como_Candidata_Futura]]'
- '[[estudo-robos-referencia-hydra-melhorias-2026-05-23]]'
propostas:
- autor: Mister_M
  confianca: 60
  conteudo: "Análise quantitativa:\n\n- **35 trades em 13 meses** = N pequeno mas\
    \ não trivial.\n  Distribuição por janela WF: 24 janelas, ~1.5 trade/janela.\n\
    \  Estatísticas por janela são inúteis — métrica honesta é PnL\n  agregado da\
    \ série.\n- PnL bruto antes de fricção: ~+USD 513 (35 trades × ~7.3 pts\n  bruto\
    \ médio). Custo proporcional total: ~USD 39. Líquido +USD 474.\n- **Ordem de grandeza\
    \ compatível com Lucca-Moench**: nossas Pre-FOMC\n  rendeu +USD 723 sobre 10 trades\
    \ (CAGR ~7%), Crabel NR7 rendeu\n  +USD 474 sobre 35 trades (CAGR ~3%). Ambas\
    \ no mesmo sample.\n- Win rate 50% em estratégia de breakout é **consistente com\n\
    \  Crabel original** (1990 reporta 45-55% em ES e NQ histórico).\n- Sharpe mediano\
    \ per-window é negativo, mas isso é artefato de\n  janelas com 1-2 trades cada.\
    \ **Sharpe sobre os 35 trades em\n  série**: estimativa ~0.5-0.8 anualizado (não\
    \ rejeita H0 com\n  folga, mas direção certa).\n- PSR esperado com N=35 é baixo.\
    \ Não é nível institucional ainda,\n  mas é DIRECIONAL.\n\nRecomendação: **registrar\
    \ Crabel NR7 como candidata à proxima\nrodada** quando tivermos pelo menos +30\
    \ trades adicionais (~12 meses\nde dados novos). Não promover a paper. Não fazer\
    \ sweep de filtros\nadicionais.\n\nConfiança 60 — temos sinal direcional positivo\
    \ ondeoutras 4\nvariantes da ORB falharam, mas amostra ainda fraca."
  id: P1
  resumo: Crabel NR7 mostra resultado promissor; documentar como direção candidata
    para revalidação quando dados crescerem; manter pausa.
- autor: Manolo
  confianca: 65
  conteudo: "Análise comportamental e de fragilidade:\n\n- +USD 474 em 13 meses é\
    \ ~5% de retorno anual sobre conta de\n  USD 10.000. Em estratégia retail com\
    \ 35 trades, **drawdown\n  individual de USD 200-300** já come 50-100% do lucro.\
    \ Não é\n  operacionalmente viável sozinha.\n- Crabel NR7 viu 50 dias elegíveis\
    \ no dataset; emitiu trade em 35\n  deles. Os outros 15 dias elegíveis não viraram\
    \ trade — provavelmente\n  por filtros internos da ORB (range mínimo, hora de\
    \ corte).\n  Concentração temporal pode ser alta — 1 mês ruim domina.\n- Hipótese\
    \ de Crabel (\"compressão precede expansão\") é genérica;\n  pode existir VIÉS\
    \ COGNITIVO de cherry-pick: testamos a variante\n  que sobreviveu **APÓS** ver\
    \ as outras 4 morrerem.\n- Mister_M propõe esperar +30 trades. Mas 30 trades novos\
    \ =\n  ~12 meses de dados = mais 6 meetings FOMC = também viabiliza\n  revisita\
    \ da Pre-FOMC. Por que não combinar?\n\nProposta concreta: **investigar se a Crabel\
    \ NR7 e a Pre-FOMC têm\ntrades em datas DIFERENTES** (correlação de portfolio).\
    \ Se sim,\ncombiná-las como mini-portfolio independente já reduz risco. Se\nnão\
    \ (overlap alto), uma das duas é redundante.\n\n- Custo: ~30min de análise sobre\
    \ os trades já existentes.\n- Sem novos parâmetros otimizáveis.\n- Sem mais Walk-Forwards.\n\
    \nRecomendação: **fazer essa análise de correlação ANTES de qualquer\ndecisão\
    \ sobre próxima rodada**."
  id: P2
  resumo: Cético sobre Crabel NR7 isolada — propor combinação com filtros fundamentalmente
    independentes (Pre-FOMC ou volatilidade) antes de investigação adicional.
regressao_detectada: false
reproduzivel: parcial
status: concluido
vetos: []
---

# Síntese final

Resultados materiais desta sessao:

1. ORB original sob slippage proporcional realista (modelo
   Hydra v1 / Pomorski 2024) entrega -USD 13.719 em 13 meses.
   CONFIRMA a Decisao 2026-05-23-02 (rejeicao da ORB).
   Slippage fixo Topstep (-USD 5.642 positivo) era otimista.

2. ORB Crabel NR7 (variante de Crabel 1990 que o Hydra v1 NAO
   testou) entrega +USD 474 em 35 trades sobre os mesmos dados.
   E' a unica ORB com PnL liquido positivo sob fricao honesta.
   PnL modesto e amostra fraca (N=35) — nao passa criterio
   institucional Mesfin 2026 (T>=2.0).

Aceito P2: executar analise de correlacao entre trades da
Crabel NR7 e da Pre-FOMC drift para informar decisao futura
sobre mini-portfolio. Custo trivial, valor informacional real.

REJEITO P1 nao porque seja errada mas porque P2 e' superset:
faz a analise barata DE GRACA antes de "registrar e esperar".

Independente do resultado da correlacao:
- aprovado_walk_forward = false permanece
- pausa investigativa de 2026-05-23-02 permanece valida
- 3 candidatas documentadas para revisita futura: Pre-FOMC
  drift, Crabel NR7 ORB, e mini-portfolio condicional

Adicao estrutural CustosOperacionais.slippage_fracao_range
(modelo proporcional) permanece util independente do veredito
sobre familias estrategicas — beneficia toda revalidacao
futura.

Licao de metodo: o Hydra v1 testou variantes proprias da ORB
mas NAO testou a versao classica de Crabel com NR4/NR7.
Documentar para garantir que proximas iteracoes testam
variantes consagradas da literatura ANTES de criar versoes
proprias.
