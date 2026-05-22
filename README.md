# Projeto CAOS

Sistema de trading quantitativo para o contrato **MNQ** (Micro E-mini Nasdaq-100 Futures), construído por um **Conselho Multi-Agente** de LLMs orquestrado dentro do Kiro IDE.

Plataforma alvo: **Windows + cmd** + **NinjaTrader 8**. Idioma do projeto: **pt-BR**.

## Estrutura

```
e:\CAOS\
├── .kiro/
│   ├── agents/                # 9 perfis do Conselho (Athena, Odin, ...)
│   ├── steering/              # 8 regras de governança (idioma, plataforma, MNQ, ...)
│   └── specs/
│       ├── caos-conselho-infra/        # Spec 1 — IMPLEMENTADO
│       ├── caos-walk-forward/          # Spec 2 — Pipeline Python (specs prontos)
│       └── caos-ninjascript-nucleo/    # Spec 3 — Núcleo C# (specs prontos)
├── CAOS_Orchestrator/         # Spec 1 — orquestrador Python (540 testes verdes)
├── CAOS_Council/              # Logs de Debate e Decisões do Conselho
├── CAOS_Zettelkasten/         # Notas de conhecimento interligadas
├── 04_CODIGO/ninjascript/     # Spec 3 — código C# (a implementar)
├── 05_BACKTEST/               # Spec 2 — saídas de Walk-Forward
└── dados/MNQ/                 # CSVs históricos do MNQ + manifesto.json
```

## Status dos Specs

| Spec | Status | O que entrega |
|---|---|---|
| **Spec 1** — Infraestrutura do Conselho | ✅ **Implementado** (770 testes verdes, 12 properties via Hypothesis) | Orquestrador Python, 9 agentes, 8 skills, Council_Recorder, state machine completa, CLI com 7 subcomandos |
| **Spec 2** — Pipeline de Walk-Forward | ✅ **Implementado** (130 testes unit + 3 properties novas) | Motor Python que valida estratégias contra os 12 meses de MNQ via Walk-Forward, com agregação por mediana, detecção de look-ahead e relatório auditável |
| **Spec 3** — Núcleo NinjaScript C# | 📋 Specs prontos | Strategy base C#, Cerberus em tempo real, Trailing 3 fases, MFE/MAE tracker |

## Pré-requisitos antes de operar

1. **Python 3.11+** com `pip` (para o orquestrador).
2. **Git** no PATH (Skill_Git e auditoria de Decisões).
3. **NinjaTrader 8** instalado (apenas para Spec 3).
4. **MSBuild** acessível via PATH ou variável `MSBUILD_PATH` (apenas para Spec 3).

## Setup zero-click

A partir de `e:\CAOS\`:

```cmd
cd CAOS_Orchestrator
pip install -e .
caos init --root e:\CAOS
caos perfil validar
```

Isso valida que os 9 perfis dos agentes carregam corretamente e a árvore de pastas está intacta.

## Próximos passos

1. **Recolocar os dados MNQ** em `dados\MNQ\` (1m e/ou tick).
2. Rodar `caos manifesto build --root e:\CAOS` para gerar `dados\MNQ\manifesto.json` com SHA-256 de cada arquivo.
3. Rodar Walk-Forward fim-a-fim contra os dados restaurados:
   ```cmd
   caos walk-forward run ^
     --estrategia caos.walk_forward.estrategias.exemplos:EstrategiaExemplo ^
     --identificador 2026-01-15-01 ^
     --root e:\CAOS
   caos walk-forward status --root e:\CAOS
   ```
4. Implementar **Spec 3** (Núcleo NinjaScript C#) — specs em `.kiro/specs/caos-ninjascript-nucleo/` (requer NinjaTrader 8 + `NT8_REFERENCES`).
5. Após Spec 3 ter a Strategy base, abrir Specs 4+ para cada estratégia plugável (Odin/Mister M/Manolo/Rodrigo) — cada uma vira um módulo em `caos/walk_forward/estrategias/`.

## CLI rápida (Spec 1 + Spec 2)

```cmd
caos init                      # cria estrutura de pastas
caos perfil validar            # valida os 9 agentes
caos manifesto build|verify    # gerencia integridade dos dados MNQ
caos hydra sync                # clona Hydra como referência somente-leitura
caos cache stats               # estatísticas do cache LLM
caos budget status             # consumo diário de tokens por agente
caos debate <tema>             # placeholder do fluxo de Debate
caos walk-forward run ...      # executa Walk-Forward fim-a-fim
caos walk-forward status       # lista relatórios em 05_BACKTEST/walk_forward/
```

Detalhes em `CAOS_Orchestrator/README.md`.

## Disciplina de auditoria

Todo Debate do Conselho gera:
- 1 arquivo Markdown em `CAOS_Council/debates/` com cabeçalho YAML auditável.
- 1 arquivo Markdown em `CAOS_Council/decisions/` com a decisão final, vetos e proposta aceita.
- 1 commit Git dedicado contendo apenas esses dois arquivos.
- (Opcional) 1 tag `caos-frozen-AAAA-MM-DD-NN` quando a decisão é aprovada para Walk-Forward.

Toda Decisão é determinística no nível de turno (Property 1) e tem rastreabilidade completa (Property 2).

## Convenções

- **Idioma**: pt-BR em todo documento, decisão e mensagem de erro. Identificadores Python/C# podem permanecer em inglês quando idiomático.
- **Plataforma**: Windows + cmd. PowerShell e bash são vetados em scripts e exemplos (steering rule `plataforma-windows-cmd`).
- **Instrumento padrão**: MNQ. Outros contratos exigem Decisão do Conselho explícita (steering rule `instrumento-mnq`).
- **`reference_hydra/`**: somente-referência. Edições manuais são revertidas no próximo `caos hydra sync` (steering rule `reference-hydra-readonly`).
