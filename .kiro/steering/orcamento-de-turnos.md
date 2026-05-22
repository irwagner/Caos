---
data: 2026-05-14
autor: Athena
justificativa: Define o orçamento padrão de turnos por Debate do Conselho, evitando loops infinitos de propostas e críticas que consumiriam tokens sem produzir Decisao_Do_Conselho concluída (R7).
orcamento: 12
---

# Orçamento de turnos por Debate

Cobre R7.1, R7.2 e R7.3 do `requirements.md`.

## Valor configurado

O campo `orcamento` no frontmatter desta regra define o
`Orcamento_De_Turnos` aplicado por Athena em cada novo Debate.

- Valor atual: **12 turnos**.
- Faixa válida: inteiro entre **4 e 100**, inclusive (R7.2).
- Default aplicado quando esta regra está ausente: **12 turnos** (R7.1).

## Comportamento em valores inválidos (R7.4)

Se o valor configurado em `orcamento` estiver fora da faixa [4, 100] ou
não for um inteiro, o Steering_Engine descarta o valor configurado,
emite warning e Athena passa a aplicar o default 12. O arquivo da regra
permanece em disco — a invalidação é apenas semântica.

## Definição de turno

Um turno é uma intervenção de agente registrada como bloco Markdown no
arquivo de Debate, com cabeçalho `agente`, `modelo`, `timestamp` e
número sequencial (R4.7).

## Quando ajustar

Aumentar o orçamento (até 100) é apropriado quando:

- O tema do Debate envolve mais de 5 agentes especialistas.
- Há propostas que dependem de iteração com Skill_MSBuild ou
  Skill_Web_Search que pode falhar e exigir nova rodada.

Diminuir o orçamento (até 4) é apropriado quando:

- O tema é binário e o usuário quer forçar decisão rápida.
- Há restrição de orçamento de tokens (R17) que torna debates longos
  inviáveis.
