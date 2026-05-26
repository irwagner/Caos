---
agentes_participantes:
- Athena
- Devils_Advocate
- Hermes
- Mister_M
- Odin
aprovado_walk_forward: false
debate_relacionado: 2026-05-26-01-bug-nr7-aceita-domingos.md
decisao_final:
  proposta_aceita: P2
  rationale: 'Aceita P2 (filtro DayOfWeek) como base, COMPLEMENTADA por P1 (limiar
    300 barras) — implementação consolidada aplica AMBOS os critérios em OR: descarta
    dia se (DayOfWeek ∈ Sat/Sun) OU (n_barras < 300). P2 é a primária porque é semanticamente
    mais robusta (calendário US business). P1 é complemento defensivo contra feriados
    parciais. Implementação: Python pré-filtra timestamp.dt.dayofweek < 5 e descarta
    groupby groups com count < 300; C# adiciona BarrasContador no EstadoCrabelNR7
    e DiaDaSemanaEhValido helper. Re-run WF de validação obrigatório antes de aceitar
    Decisão. Sharpe ≥ 1.0 mantém Decisão 2026-05-25-02. Sharpe < 1.0 abre Debate de
    seguimento.'
identificador: 2026-05-26-01
links_zettel:
- '[[Decisao_2026-05-25-02_Crabel_NR7_SF_CB]]'
- '[[Bug_NR7_Aceita_Domingos_2026-05-26]]'
propostas:
- autor: Mister_M
  confianca: 72
  conteudo: 'Adicionar em _calcular_range_diario (Python) e EstrategiaCrabelLogica.AtualizarFiltro
    (C#) um filtro que descarta dias cujo número de barras de minuto < 300. Limiar
    discreto não otimizável: 300 barras = 5h de pregão = abaixo de qualquer regular
    trading hour completo. Justificativa: domingos têm 1-300 barras (Globex Sun 18
    ET ~5h); pregões regulares têm 1380. Limiar é fronteira física, independe de fuso
    ou instrumento. Riscos: dias de feriado parcial podem ter ~430 barras e passariam
    o filtro; 300 é magia documentada como fronteira física.'
  id: P1
  resumo: Filtrar dias com menos de 300 barras de minuto (fronteira física de pregão)
- autor: Odin
  confianca: 78
  conteudo: 'Filtro semântico em ambas as implementações: dow not in (Sat, Sun). Python:
    timestamp.dt.dayofweek < 5. C#: DayOfWeek != Sunday && != Saturday. Ataca causa
    raiz (Globex Sunday). Imune a mudanças de feed. Riscos: não filtra feriados US
    (Memorial Day, Thanksgiving, July 4) com pregão reduzido. Para contratos non-US
    (Forex, crypto) o critério não se aplica — mas MNQ é regra steering.'
  id: P2
  resumo: Filtrar pelo dia da semana (DayOfWeek != Sunday/Saturday)
regressao_detectada: true
reproduzivel: 'true'
status: concluido
vetos: []
---

# Síntese final

Aceita P2 (filtro DayOfWeek) como base, COMPLEMENTADA por P1 (limiar 300 barras) — implementação consolidada aplica AMBOS os critérios em OR: descarta dia se (DayOfWeek ∈ Sat/Sun) OU (n_barras < 300). P2 é a primária porque é semanticamente mais robusta (calendário US business). P1 é complemento defensivo contra feriados parciais. Implementação: Python pré-filtra timestamp.dt.dayofweek < 5 e descarta groupby groups com count < 300; C# adiciona BarrasContador no EstadoCrabelNR7 e DiaDaSemanaEhValido helper. Re-run WF de validação obrigatório antes de aceitar Decisão. Sharpe ≥ 1.0 mantém Decisão 2026-05-25-02. Sharpe < 1.0 abre Debate de seguimento.
