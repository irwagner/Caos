# State of Research — 2026-05-31

> Documento vivo. Substitui `STATE-OF-RESEARCH-2026-05-29.md` (mantido
> como histórico).
>
> **Marco da sessão**: após **três refutações consecutivas** (Crabel
> NR7+ORB+SF+CB, P2 range_absoluto, VVG Late-Session Reversal), o
> Conselho fez síntese estratégica (`Decisao_2026-05-31-01`) e
> identificou a **causa-raiz comum: não-persistência temporal**
> (regime-dependência) dos edges OHLCV-direcionais no MNQ minute.
> Pipeline de estratégias OHLCV-direcionais **PAUSADO por disciplina**.
> Critério de triagem reforçado (steering `criterio-triagem-nao-persistencia`).
> Investigação preliminar gratuita de GEX/Level 2 **não destravou**
> nova classe (dado não é obtenível/barato).

---

## 1. Estado atual do projeto

### Pipeline de estratégias OHLCV-direcionais: PAUSADO

Não por desistência — por **disciplina anti-viés-de-ação**. Três
refutações independentes com causa-raiz comum são um sinal a
respeitar. O ônus da prova inverteu: um candidato agora precisa
provar que merece um Spec.

### Histórico das três refutações (maio/2026)

| Estratégia | Decisão de origem | Modo de falha | Destino |
|---|---|---|---|
| Crabel NR7 + ORB + SF + CB | `Decisao_2026-05-25-02` | Overfit ao WF (re-replay −USD 573,50) | ARQUIVADA (fallback A, `2026-05-29-01`) |
| P2 range_absoluto | `Decisao_2026-05-29-01` (B) | Não-estacionariedade (calibração) | REFUTADA na calibração |
| VVG Late-Session Reversal | `Decisao_2026-05-29-02/03` | Year-stability 1/4 (WF longo) | ARQUIVADA (fallback A, `2026-05-29-04`) |

**Causa-raiz comum** (`Decisao_2026-05-31-01`): não-persistência
temporal. Os modos de falha são distintos, mas todos manifestam
regime-dependência — o edge existe em janelas/regimes específicos e
evapora em outros.

### Artefatos permanentes criados nesta síntese

- `[[Regra_De_Ouro_Negativa_Nao_Persistencia_MNQ_2026-05-31]]` —
  consolida o que NÃO funciona (Zettel).
- Steering `criterio-triagem-nao-persistencia.md` — critério de
  triagem reforçado (R12+), `inclusion: always`.
- `[[Investigacao_Preliminar_GEX_Level2_2026-05-31]]` — investigação
  gratuita que fechou (por ora) a porta de P3.

## 2. Decisão 2026-05-31-01 — rumo do pipeline

Debate de síntese estratégica (6 agentes: Athena, Explorador,
Mister_M, Odin, Devils_Advocate, Cerberus). Proposta vencedora:
**P2 emendada** (consolidar a evidência negativa).

### Conclusões-chave do Debate

- **Mister_M (estatística)**: detectar edge líquido ~0.5 pts/trade
  com sd ~50 exigiria N ≈ 78.000 trades — inalcançável.
- **Odin (estrutural)**: MNQ 2026 mudou (0DTE >50% do volume →
  dealers Long Gamma suprimem volatilidade direcional; algos
  comprimiram edges OHLCV clássicos).
- **Devils_Advocate (insight central)**: a causa das 3 refutações
  NÃO é "edge pequeno" — é **não-persistência temporal**. Qualquer
  caminho futuro deve atacar isso, não o tamanho do edge.
- **Cerberus (risco de recurso)**: P3 (adquirir GEX/L2) tem pior
  perfil risco/recurso → veto condicional (investigação gratuita
  antes de compromisso). P2 (consolidar) tem o melhor → aprovado.

### Critério de triagem reforçado (vinculante)

Candidato futuro DEVE demonstrar como ataca a não-persistência:
(1) mecanismo de adaptação de regime, OU (2) edge estrutural
independente de regime, OU (3) dado novo que mede o regime (sujeito
a veto condicional). Quem não endereçar → rejeitado sem Spec.

## 3. Investigação preliminar GEX/Level 2 — resultado

`[[Investigacao_Preliminar_GEX_Level2_2026-05-31]]` (custo zero):

- **GEX Nasdaq**: sem feed gratuito confiável. Fontes pagas
  ($99-299/mês), SPX-cêntricas. Repos open-source só calculam (e
  exigem chain NDX que também custa).
- **Level 2 histórico MNQ**: não obtenível de graça. NT8 só grava
  prospectivamente; compra é cara; sniffer próprio já falhou.
- **Veredito**: veto condicional do Cerberus **não liberado**. P3
  não vira Spec.
- **Sub-opção de baixo custo registrada** (não recomendação ativa):
  coleta **prospectiva** gratuita de GEX a partir de agora,
  acumulando dataset proprietário por meses. Aposta de meses, exige
  decisão explícita do usuário.

## 4. Histórico de estratégias (acumulado)

| Estratégia | Destino |
|---|---|
| Crabel NR7 + ORB + SF + CB (`2026-05-25-02`) | ARQUIVADA |
| P2 range_absoluto | REFUTADA na calibração |
| VVG Late-Session Reversal | ARQUIVADA (year-stability) |
| Value Area Filter | REFUTADA (`2026-05-27`) |
| OFI direto | REFUTADO (Sharpe −39) |

## 5. Lições aprendidas (acumuladas)

1. **WF longo sozinho NÃO valida** — precisa de hold-out temporal
   real disjunto do treino.
2. **Year-stability pega o que medianas mascaram** — Sharpe/Calmar
   medianas são miragens de N pequeno; consistência trimestral é
   mais difícil de satisfazer por acaso.
3. **Threshold absoluto não funciona em série não-estacionária** —
   Crabel usou janela móvel (NR7) por uma razão.
4. **Stop/target devem casar com o horizonte do trade** — ATR
   diário em trade de 80 min torna os níveis inertes.
5. **A causa-raiz das refutações é não-persistência, não tamanho do
   edge** — qualquer candidato futuro tem que atacar persistência.
6. **"Dado melhor resolveria" é falácia sem base** — só vale se o
   dado for comprovadamente obtenível/confiável/barato (não é, hoje).

## 6. Próxima ação esperada do usuário

Pipeline pausado. Há três caminhos possíveis, todos exigindo
decisão explícita do usuário:

1. **Aceitar a pausa** e aguardar candidato que passe o novo
   critério de triagem (não-persistência). Default disciplinado.
2. **Iniciar coleta prospectiva de GEX** (aposta de meses, custo
   ~zero de setup) para acumular dataset proprietário de regime —
   única porta de baixo custo que sobrou.
3. **Explorar classe de problema não-tocada** (sugestão do
   Devils_Advocate): arbitragem estatística MNQ vs ES/MES/NQ,
   estratégias de volatilidade não-direcionais, market making
   passivo — TODAS sujeitas ao critério de não-persistência na
   triagem.

Nenhuma é "abrir o quarto Spec direcional às cegas" — esse caminho
foi explicitamente fechado pela Decisão.
