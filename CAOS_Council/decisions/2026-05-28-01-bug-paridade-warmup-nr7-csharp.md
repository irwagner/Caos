---
agentes_participantes:
- Athena
- Cerberus
- Devils_Advocate
- Hermes
- Mister_M
aprovado_walk_forward: false
debate_relacionado: 2026-05-28-01-bug-paridade-warmup-nr7-csharp.md
decisao_final:
  proposta_aceita: P1
  rationale: 'Aceita P1 (hidratacao em State.DataLoaded + BarsRequiredToTrade defensivo)
    como caminho mandatorio para corrigir paridade Python<->C#. Devils_Advocate alerta
    que fix nao salva estrategia automaticamente — 36% win rate sob bug pode ser sintoma
    de estrategia sem edge real. Cerberus impoe Veto_De_Risco condicional: Tag caos-frozen-2026-05-25-02
    suspensa de hold-out ate re-validacao com PnL >= -USD 100 em 105 dias. Implementacao:
    (a) hidratar RangePorDia iterando Bars em State.DataLoaded; (b) BarsRequiredToTrade
    = 7*1380 = 9660 (defesa em camadas); (c) whitelist ninjascript-api.md atualizada
    com Bars.GetTime/GetHigh/GetLow/GetClose, BarsRequiredToTrade, Bars.Count; (d)
    re-replay sobre 28/01-26/05 e comparar trade-a-trade. Re-validacao OBRIGATORIA
    antes de retomar hold-out.'
identificador: 2026-05-28-01
links_zettel:
- '[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]'
- '[[Bug_NR7_Aceita_Domingos_2026-05-26]]'
- '[[Bug_Paridade_Warmup_NR7_2026-05-28]]'
- '[[Replay_Final_Limpo_2026-05-28]]'
propostas:
- autor: Mister_M
  confianca: 82
  conteudo: 'Em Strategy_CAOS.OnStateChange, no caso State.DataLoaded, apos InstanciarComponentes(),
    iterar todas as barras carregadas em Bars (de 0 ate Bars.Count-1) e chamar EstrategiaCrabelLogica.AtualizarFiltro
    para cada uma. Isso popula RangePorDia com todo o historico antes de qualquer
    trade. Pos-fix: NR7 sempre tem janela completa, ja na primeira barra do State.Realtime.
    Sem alteracao de logica de decisao — apenas warmup correto. Custo: O(N_barras)
    uma vez no carregamento, ~100ms para 14 meses de dados.'
  id: P1
  resumo: Hidratar EstadoCrabelNR7 em State.DataLoaded iterando barras historicas
    pre-existentes
regressao_detectada: true
reproduzivel: 'true'
status: concluido
vetos: []
---

# Síntese final

Aceita P1 (hidratacao em State.DataLoaded + BarsRequiredToTrade defensivo) como caminho mandatorio para corrigir paridade Python<->C#. Devils_Advocate alerta que fix nao salva estrategia automaticamente — 36% win rate sob bug pode ser sintoma de estrategia sem edge real. Cerberus impoe Veto_De_Risco condicional: Tag caos-frozen-2026-05-25-02 suspensa de hold-out ate re-validacao com PnL >= -USD 100 em 105 dias. Implementacao: (a) hidratar RangePorDia iterando Bars em State.DataLoaded; (b) BarsRequiredToTrade = 7*1380 = 9660 (defesa em camadas); (c) whitelist ninjascript-api.md atualizada com Bars.GetTime/GetHigh/GetLow/GetClose, BarsRequiredToTrade, Bars.Count; (d) re-replay sobre 28/01-26/05 e comparar trade-a-trade. Re-validacao OBRIGATORIA antes de retomar hold-out.
