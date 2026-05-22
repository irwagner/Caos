---
data: 2026-05-14
autor: Athena
justificativa: Define orçamentos diários de tokens por agente do Conselho para evitar consumo descontrolado de modelos LLM e bloquear novas invocações quando o limite for excedido (R17).
orcamentos:
  Athena: 1500000
  Cerberus: 800000
  Hermes: 1200000
  Odin: 1000000
  Mister_M: 900000
  Manolo: 700000
  Rodrigo: 600000
  Explorador: 1100000
  Devils_Advocate: 500000
---

# Orçamento diário de tokens por agente

Cobre R17.1, R17.2, R17.3 e R17.6 do `requirements.md`.

## Valores configurados

O campo `orcamentos` no frontmatter mapeia cada um dos 9 agentes ao seu
limite diário de tokens consumidos (input + output). Valores em tokens.

| Agente           | Orçamento diário |
|------------------|------------------|
| Athena           | 1.500.000        |
| Cerberus         | 800.000          |
| Hermes           | 1.200.000        |
| Odin             | 1.000.000        |
| Mister_M         | 900.000          |
| Manolo           | 700.000          |
| Rodrigo          | 600.000          |
| Explorador       | 1.100.000        |
| Devils_Advocate  | 500.000          |

## Default

Agentes não listados em `orcamentos` herdam o default de **1.000.000
tokens/dia**. O default também é aplicado quando esta regra está
ausente do diretório de steering.

## Comportamento em valores inválidos (R17.6)

Para cada agente, o Steering_Engine valida o valor configurado:

- Se não for um inteiro, descarta e aplica o default 1.000.000.
- Se for menor que **10.000**, descarta e aplica o default 1.000.000.

Em ambos os casos, um warning é emitido e o agente recebe o orçamento
default. A regra continua válida para os demais agentes — a falha é
isolada por agente.

## Definição de "dia"

Dia UTC, marcação `AAAA-MM-DD`. O Skill_Token_Budget persiste o consumo
em `CAOS_Orchestrator/.budget/AAAA-MM-DD.json` e zera automaticamente
no rollover de UTC.

## Bloqueio

Quando `tokens_total_consumidos[agente, dia] >= orcamento_diario_tokens`
do agente, o Token_Budget_Guard bloqueia a próxima invocação e o
Orchestrator marca o turno com `status: orcamento-de-tokens-esgotado`
(R17.5).
