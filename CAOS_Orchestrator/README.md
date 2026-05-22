# CAOS_Orchestrator

Orquestrador Python do **Conselho Multi-Agente do CAOS**. Coordena os 9
agentes-LLM nativos do Kiro IDE que constroem, em colaboração, o robô
de trading C# / NinjaTrader 8 que opera o contrato MNQ (Micro E-mini
Nasdaq-100 Futures).

Plataforma alvo: **Windows + cmd**. Idioma do projeto: **pt-BR**.

## O que está pronto nesta etapa

- Esqueleto do pacote `caos/` com CLI completa (Tasks 1–17 do Spec 1).
- 7 subcomandos: `init`, `manifesto`, `hydra`, `debate`, `perfil`,
  `cache`, `budget`.
- Componentes principais entregues: Profile_Loader, Steering_Engine,
  Catálogo de Skills (Terminal, Git, Data_Inspector, Data_Integrity,
  LLM_Cache, Token_Budget, MSBuild, Web_Search), Context_Loader,
  Council_Recorder, Determinism_Auditor, Bias_Filter,
  Hydra_Reference_Sync, Failure_Handler, Orchestrator state machine e
  Agent_Invoker.
- Suite de testes (`pytest` + `hypothesis`) cobrindo 12 propriedades
  transversais e os componentes individuais.

## Instalação local

A partir da raiz do workspace (`e:\CAOS\`):

```cmd
cd CAOS_Orchestrator
pip install -e .
```

A instalação editável expõe o entry point `caos` no PATH do venv.
Alternativamente, sem instalar globalmente, todos os comandos podem ser
chamados com `python -m caos.main ...`.

## Uso da CLI

Em todos os subcomandos, `--root <pasta>` aceita uma raiz de workspace
alternativa; quando omitido, usa a `cwd`. Caminhos relativos são
resolvidos contra a `cwd`.

### `caos init`

Cria de forma idempotente os 8 diretórios do Spec 1 (`.kiro/agents/`,
`.kiro/steering/`, `CAOS_Zettelkasten/`, `CAOS_Council/debates/`,
`CAOS_Council/decisions/`, `04_CODIGO/ninjascript/`, `05_BACKTEST/`,
`dados/MNQ/`), com `.gitkeep` nos placeholders. Roda quantas vezes for
necessário sem destruir nada.

```cmd
caos init
caos init --root C:\caminho\para\outro\workspace
```

### `caos manifesto build|verify`

Gerência do `dados/MNQ/manifesto.json` — fonte da verdade sobre
integridade dos arquivos de dados (R15).

```cmd
caos manifesto build
caos manifesto build --instrumento MNQ
caos manifesto verify
```

`build` (re)gera o `manifesto.json` calculando SHA-256 via streaming.
`verify` recomputa os hashes e reporta divergências, arquivos ausentes
e arquivos não registrados. Exit `0` em sucesso, `1` em qualquer
divergência detectada.

### `caos hydra sync`

Sincroniza a cópia somente-leitura do repositório histórico Hydra
(`https://github.com/irwagner/hydra-trading`, branch `main`) em
`04_CODIGO/ninjascript/reference_hydra/`. Na primeira execução faz
`git clone --depth 1`; nas subsequentes, `git fetch` + `git reset --hard
origin/main`. Timeout total de 120 s.

```cmd
caos hydra sync
caos hydra sync --root C:\caminho\para\outro\workspace
```

A saída humana inclui o tipo de operação (clone novo / update
incremental), o hash do commit, o caminho do clone e a duração em ms.
Em caso de falha (timeout, rede, repo inacessível, git ausente), a
cópia local é preservada e a categoria do erro é reportada em stderr.

A regra de steering `reference-hydra-readonly` veda qualquer outra forma
de modificar `reference_hydra/`.

### `caos debate <tema_titulo>`

Placeholder do fluxo de Debate ponta-a-ponta no Spec 1. Documenta o
formato de argumentos esperado pelo orquestrador em modo de produção;
não chama o backend de subagente nesta versão. Para testes
automatizados de orquestração, use a suíte property-based em
`CAOS_Orchestrator/tests/property/`.

```cmd
caos debate "Adicionar filtro de horario"
caos debate "Refatorar setup ORB" ^
  --descricao "Estudo da abertura de Nova York" ^
  --tags ninjascript,risco ^
  --csharp ^
  --exposicao
```

Argumentos:

- `tema_titulo` (obrigatório): título curto.
- `--descricao <txt>`: descrição livre.
- `--tags tag1,tag2`: tags separadas por vírgula.
- `--csharp`: marca o Debate como envolvendo código C#.
- `--exposicao`: marca o Debate como envolvendo alteração de exposição.

Exit code: sempre `0` neste estágio.

### `caos perfil validar [nome]`

Valida arquivos de perfil em `.kiro/agents/` contra o schema
`AgentProfile`. Sem argumento: valida os 9 perfis canônicos do
Conselho. Com `<nome>` (ex.: `Athena`): valida apenas
`.kiro/agents/<nome>.md`.

```cmd
caos perfil validar
caos perfil validar Athena
caos perfil validar Cerberus --root C:\workspaces\projeto
```

Exit `0` quando todos os perfis pertinentes carregam sem falhas;
exit `1` quando há ao menos uma falha (modelo divergente, campo
obrigatório faltando, Skill não autorizada, etc.).

### `caos cache stats`

Lê `CAOS_Orchestrator/.cache/` (entradas do `Skill_LLM_Cache`, R16) e
imprime contagem de arquivos `*.json` e tamanho total em bytes.

```cmd
caos cache stats
caos cache stats --root C:\workspaces\projeto
```

Exit code: sempre `0`. Diretório ausente é tratado como cache vazio.

### `caos budget status`

Lê `CAOS_Orchestrator/.budget/<data>.json` (estado do
`Skill_Token_Budget`, R17) e imprime consumo input/output/total e saldo
restante por agente. Default da `--data` é hoje UTC.

```cmd
caos budget status
caos budget status --data 2026-01-15
caos budget status --data 2026-01-15 --root C:\workspaces\projeto
```

Exit `0` em sucesso; `2` quando `--data` está em formato inválido (não
é `AAAA-MM-DD`).

## Testes

A partir de `CAOS_Orchestrator/`:

```cmd
pytest
pytest tests/unit/test_cli.py -v
pytest tests/property/ -v
```

Os testes de propriedade ficam em `tests/property/` e os unitários em
`tests/unit/`. O `pyproject.toml` já configura `pythonpath = ["."]`,
então não é necessário `pip install -e .` para rodar a suíte.
