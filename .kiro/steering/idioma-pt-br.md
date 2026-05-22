---
data: 2026-05-14
autor: Athena
justificativa: Garante que a documentação formal e os artefatos de governança do projeto fiquem em português brasileiro, evitando ambiguidade em decisões revisáveis pelo usuário humano (R3.2).
---

# Idioma do projeto: português brasileiro

Cobre R3.2 do `requirements.md`.

## Regra

Os seguintes documentos e artefatos do projeto CAOS DEVEM ser escritos em
português brasileiro:

- `requirements.md` de qualquer spec.
- `design.md` de qualquer spec.
- `tasks.md` de qualquer spec.
- Arquivos de Debate em `CAOS_Council/debates/`.
- Arquivos de Decisao_Do_Conselho em `CAOS_Council/decisions/`.
- Mensagens de erro e warnings exibidas ao usuário pelo orquestrador.
- Comentários e docstrings em código Python do orquestrador.

## Exceções

- Identificadores de código (variáveis, funções, classes) podem permanecer
  em inglês quando idiomático no ecossistema (Python, C#, NinjaScript).
- Termos técnicos consagrados (`order flow`, `walk-forward`, `MFE`, `MAE`)
  são mantidos em inglês para preservar precisão.
- Mensagens de log internas usadas apenas em testes automatizados podem
  estar em inglês para compatibilidade com ferramentas de CI.
