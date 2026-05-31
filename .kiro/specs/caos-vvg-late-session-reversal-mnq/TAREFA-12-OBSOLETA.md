# Tarefa 12 — obsoleta pelo fallback A da Tarefa 11

> Nota de fechamento do spec `caos-vvg-late-session-reversal-mnq`.
> Data: 2026-05-29.

## Por que a Tarefa 12 não foi executada

A **Tarefa 12** ("Sincronizar sandbox NT8 + README do replay") tinha
como único propósito **preparar o replay NT8 (R8)** da estratégia VVG
Late-Session Reversal.

A **Tarefa 11** (Walk-Forward longo de validação) **REFUTOU** a
estratégia e acionou o **fallback A automático** (R7.4 / R9):

- PnL total: −8.08 pts (critério: > 0) → FALHA
- Year-stability: 1/4 trimestres positivos (critério: ≥ 3/4) → FALHA

Pela cláusula pré-registrada (R9.3), a estratégia é **arquivada sem
novo Debate** e **NÃO avança para R8 (replay NT8)**. Ver
`[[Refutacao_VVG_Late_Session_2026-05-29]]`.

## Consequência

Executar a Tarefa 12 — sincronizar a estratégia refutada para a
sandbox NT8 ativa (`Strategies\caos\`) e escrever um README de replay —
**contradiria o fallback A**. A sandbox ativa só deve conter
estratégias em hold-out ou em validação corrente; uma estratégia
arquivada não pertence lá.

Portanto, a Tarefa 12 é **obsoleta** e foi marcada como concluída sem
execução do conteúdo original.

## O que permanece versionado (e o que NÃO)

- **Permanece** em `04_CODIGO/ninjascript/` (Git): os 3 arquivos C#
  (`EstrategiaVvgLateSessionLogica.cs`,
  `EstrategiaVvgClassifierLogica.cs`,
  `StrategyVvgLateSessionReversal.cs`) ficam como **histórico
  inativo** — mesmo tratamento dado ao código da P2 refutada. Servem
  de referência se uma futura variante (ex.: ATR intradiário) for
  aprovada por Decisão formal.
- **NÃO sincronizado** para a sandbox NT8: a estratégia não roda em
  Sim101 nem em conta real.
- **NÃO atualizado** o `README_INSTALACAO_HOLDOUT.md`: não há hold-out
  desta estratégia.
- **Tag `caos-frozen-*`**: nunca aplicada (só viria após R7 + R8
  ambos aprovados).

## Estado final do spec

| Tarefa | Status |
|---|---|
| 1. Calibração | concluída (parâmetros congelados) |
| 2. vvg_logica.py | concluída |
| 3. vvg_classifier.py | concluída |
| 4. plugin Walk-Forward | concluída |
| 5. porta de referência | concluída |
| 6. EstrategiaVvgLateSessionLogica.cs | concluída |
| 7. EstrategiaVvgClassifierLogica.cs | concluída |
| 8. testes unitários (79 testes) | concluída |
| 9. property test paridade (200 exemplos, 0 divergências) | concluída |
| 10. StrategyVvgLateSessionReversal.cs | concluída |
| 11. Walk-Forward longo | concluída — **REFUTOU** a estratégia |
| 12. sincronizar sandbox + README replay | **obsoleta** (fallback A) |

A estratégia foi implementada de forma completa e correta (paridade
Python↔C# verificada), mas **não tem edge** sob os critérios
pré-registrados — exatamente como o paper Mesfin (arXiv 2605.11423)
antecipava. O pipeline funcionou como projetado.
