---
data: 2026-05-14
autor: Athena
justificativa: Fixa o instrumento operacional padrão do robô CAOS para evitar análises e backtests aplicados em contratos divergentes (R3.4).
---

# Instrumento operacional padrão: MNQ

Cobre R3.4 do `requirements.md`.

## Regra

O instrumento operacional padrão do robô CAOS é o **MNQ — Micro E-mini
Nasdaq-100 Futures**, negociado na Chicago Mercantile Exchange (CME).
Todas as propostas, backtests, análises de risco e Decisoes_Do_Conselho
DEVEM assumir MNQ como contrato alvo, salvo quando explicitamente
declarado de outra forma na proposta.

## Especificações relevantes

- Símbolo: `MNQ`.
- Tamanho do contrato: USD 2 por ponto do índice.
- Tick size: 0.25 ponto (= USD 0.50).
- Sessão eletrônica: 23 horas/dia (CME Globex).
- Margem inicial e de manutenção: consultar a corretora; sujeita a alteração.

## Convenções de dados

- Diretório de dados: `dados/MNQ/`.
- Granularidades padrão consideradas: `1m` (minuto) e `tick`.
- Nomes de arquivo CSV são livres, mas o `manifesto.json` é a única fonte
  da verdade sobre integridade (SHA-256) e período coberto (R15).

## Quando trocar de instrumento

Trocar de instrumento (por exemplo, ES, NQ, MES) exige:

1. Decisao_Do_Conselho explícita com `aprovado_walk_forward: true`.
2. Atualização desta regra de steering com nova `data` e `autor`.
3. Reexecução do Walk-Forward completo no novo instrumento.

Sem esses três passos, qualquer agente que propor estratégia em
instrumento diferente recebe Veto_De_Risco automático de Cerberus.
