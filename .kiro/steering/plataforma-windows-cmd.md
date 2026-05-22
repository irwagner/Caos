---
data: 2026-05-14
autor: Athena
justificativa: Fixa o sistema operacional e o shell padrão do projeto CAOS para evitar inconsistências entre exemplos, scripts e instruções dos agentes (R3.3).
---

# Plataforma alvo: Windows + `cmd`

Cobre R3.3 do `requirements.md`.

## Regra

- Sistema operacional alvo do projeto CAOS: **Windows 10 ou Windows 11**.
- Shell padrão para scripts e exemplos: **`cmd` (Command Prompt)**.

## Vetos explícitos

Os seguintes shells e instruções dependentes de Linux estão vetados em
scripts, exemplos de documentação e propostas dos agentes:

- **PowerShell** (`*.ps1`, `pwsh`, `powershell.exe`).
- **Bash / sh / zsh** (`*.sh`, `bash -c`, redirecionamentos `<<`).
- **WSL** (`wsl`, distribuições Linux dentro do Windows).
- Comandos exclusivos de Linux (`grep`, `awk`, `sed`, `chmod`, `chown`,
  `tar`, paths absolutos `/usr/...`, `/etc/...`).

## Casos permitidos

- Comandos `cmd` nativos: `dir`, `cd`, `mkdir`, `del`, `copy`, `move`,
  `findstr`, `set`, `type`.
- Invocação de Python via `python ...` ou `py -3.11 ...`.
- Invocação de Git via `git ...`.
- Invocação de MSBuild via `MSBuild.exe ...` (com path absoluto quando
  fora do `PATH`).

## Justificativa

O usuário do projeto CAOS opera diretamente em Windows + cmd. Misturar
shells diferentes nos exemplos quebra a reprodutibilidade dos passos e
introduz dependências escondidas (path style, encoding, line endings).
