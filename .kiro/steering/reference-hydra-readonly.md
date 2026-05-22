---
data: 2026-05-14
autor: Athena
justificativa: Estabelece o caráter somente-referência da cópia do projeto Hydra em 04_CODIGO/ninjascript/reference_hydra/, prevenindo que código histórico seja modificado, importado ou compilado junto ao código ativo do CAOS (R13.4).
---

# `reference_hydra/` é somente-referência

Cobre R13.4 do `requirements.md`.

## Regra

O diretório `04_CODIGO/ninjascript/reference_hydra/` é uma cópia
somente-leitura do repositório histórico Hydra
(`https://github.com/irwagner/hydra-trading`, branch `main`). Seu único
propósito é servir como referência consultada pelos agentes Odin,
Mister_M, Manolo, Hermes e Explorador durante Debates.

## Proibições observáveis

As seguintes ações são VETADAS sobre `04_CODIGO/ninjascript/reference_hydra/`:

- **Modificações no conteúdo**: nenhum arquivo dentro deste diretório
  pode ser editado, criado ou excluído fora do fluxo de
  `caos hydra sync`. Edições manuais são revertidas no próximo sync.
- **Inclusão em build**: o `.csproj` ativo do projeto CAOS NÃO DEVE
  referenciar arquivos `.cs` deste diretório, nem por `<Compile Include>`
  nem por `<ProjectReference>`. MSBuild só compila código sob
  `04_CODIGO/ninjascript/` excluindo `reference_hydra/`.
- **Imports diretos no código ativo**: nenhum arquivo C# em
  `04_CODIGO/ninjascript/` (excluindo `reference_hydra/`) pode
  declarar `using` que aponte para namespaces internos do Hydra. A
  referência cruzada só ocorre via cópia explícita aprovada em
  Decisao_Do_Conselho (R13.5).
- **Commits sob esse caminho fora do fluxo de sync**: o Skill_Git
  rejeita stages que toquem em `reference_hydra/` quando o invocador
  não é o `Hydra_Reference_Sync`.

## Fluxo aprovado para usar código do Hydra

1. Agente identifica trecho relevante em `reference_hydra/`.
2. Abre Debate com proposta explícita de copiar o trecho para o código
   ativo (com adaptações se necessário).
3. Hermes valida via Skill_MSBuild.
4. Cerberus valida via Veto_De_Risco se o trecho altera exposição.
5. Decisao_Do_Conselho com `aprovado_walk_forward: true` autoriza a
   cópia. O commit dedicado registra origem, hash do commit do Hydra
   e adaptações aplicadas.

## Justificativa

Manter o Hydra como referência intocada preserva o ground truth
histórico para comparações futuras e impede que bugs herdados sejam
silenciosamente promovidos ao código ativo do CAOS.
