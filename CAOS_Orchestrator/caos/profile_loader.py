"""Carregador de perfis de agente do Conselho CAOS.

Este módulo é responsável por ler os 9 arquivos de perfil em
``.kiro/agents/*.md`` (frontmatter YAML + corpo Markdown contendo o system
prompt), validá-los contra :class:`caos.models.AgentProfile`, e devolver
resultados estruturados que permitem ao orquestrador (Athena) bloquear a
inicialização de um Debate quando qualquer perfil for inválido.

Cobre os critérios R2.1 a R2.6 do ``requirements.md`` e o componente
``Profile_Loader`` descrito em ``design.md`` (seção 2 — Componentes e
Interfaces; seção 3.1 — Modelo de dados).

Premissas de implementação:

- Usa a biblioteca ``python-frontmatter`` (declarada em ``pyproject.toml``)
  para fazer o parsing do bloco YAML inicial e separar o corpo Markdown.
- Não modifica nenhum arquivo: apenas leitura.
- Mensagens de erro em pt-BR e sempre incluem o caminho do arquivo afetado.
- O par ``(nome, modelo)`` é validado pelo próprio
  :class:`AgentProfile`; aqui apenas mapeamos o ``ValidationError`` resultante
  para a categoria ``modelo-divergente`` quando aplicável.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import frontmatter
from pydantic import ValidationError

from caos.models import AGENTES, AgentProfile

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Lista canônica dos 9 nomes de arquivo esperados em ``.kiro/agents/``.
ARQUIVOS_ESPERADOS: tuple[str, ...] = tuple(f"{nome}.md" for nome in AGENTES)

#: Conjunto dos nomes dos 9 agentes (para checagens de pertencimento rápidas).
NOMES_ESPERADOS: frozenset[str] = frozenset(AGENTES)


CategoriaFalha = Literal[
    "arquivo-ausente",
    "frontmatter-ausente",
    "frontmatter-malformado",
    "campo-obrigatorio-faltando",
    "modelo-divergente",
    "skill-nao-autorizada",
    "validacao-pydantic",
    "arquivo-faltando-no-conselho",
    "arquivo-extra",
]
"""Categorias possíveis de falha emitidas pelo carregador.

- ``arquivo-ausente``: o arquivo passado para :func:`carregar_perfil` não
  existe.
- ``frontmatter-ausente``: o arquivo existe mas não contém um bloco
  YAML delimitado por ``---`` no topo.
- ``frontmatter-malformado``: o YAML não pôde ser parseado.
- ``campo-obrigatorio-faltando``: ao menos um campo declarado em
  :class:`AgentProfile` como obrigatório está ausente do frontmatter.
- ``modelo-divergente``: o ``modelo`` declarado não está em
  ``MODELOS_PERMITIDOS[nome]`` (R2.3).
- ``skill-nao-autorizada``: ``skills_permitidas`` contém um nome fora do
  catálogo do Requirement 11.
- ``validacao-pydantic``: outras violações do schema (tipos, ranges, regex,
  ordem de seções obrigatórias, etc.).
- ``arquivo-faltando-no-conselho``: emitido por :func:`carregar_todos` quando
  algum dos 9 nomes esperados não existe em disco.
- ``arquivo-extra``: emitido por :func:`carregar_todos` quando há um arquivo
  ``.md`` em ``.kiro/agents/`` que não corresponde a nenhum dos 9 agentes.
"""


# ---------------------------------------------------------------------------
# Estruturas de retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FalhaCarregamento:
    """Descrição estruturada de uma falha de carregamento.

    ``caminho`` aponta para o arquivo afetado quando aplicável; pode ser
    ``None`` em falhas globais (por exemplo, ausência total da pasta).
    ``detalhes`` carrega informação suplementar (lista de campos faltantes,
    erros do Pydantic, etc.) para registro em log e auditoria.
    """

    categoria: CategoriaFalha
    mensagem: str
    caminho: Optional[Path] = None
    detalhes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoCarregamentoPerfil:
    """Resultado do carregamento de um único arquivo de perfil.

    Em caso de sucesso, ``perfil`` contém a instância validada de
    :class:`AgentProfile` e ``falha`` é ``None``. Em caso de falha,
    ``perfil`` é ``None`` e ``falha`` está preenchido.
    """

    caminho: Path
    perfil: Optional[AgentProfile] = None
    falha: Optional[FalhaCarregamento] = None

    @property
    def sucesso(self) -> bool:
        """``True`` quando nenhuma falha foi registrada."""
        return self.falha is None


@dataclass(frozen=True)
class ResultadoCarregamentoTodos:
    """Resultado da varredura completa de ``.kiro/agents/``.

    ``perfis`` mapeia ``nome do agente -> AgentProfile`` para os perfis que
    foram carregados com sucesso. ``falhas`` enumera todas as falhas
    encontradas, sem interrupção precoce: assim, o orquestrador pode reportar
    todos os problemas de uma vez ao usuário.
    """

    diretorio: Path
    perfis: dict[str, AgentProfile] = field(default_factory=dict)
    falhas: list[FalhaCarregamento] = field(default_factory=list)

    @property
    def sucesso(self) -> bool:
        """``True`` quando os 9 perfis foram carregados sem falhas."""
        return not self.falhas and len(self.perfis) == len(AGENTES)


# ---------------------------------------------------------------------------
# Carregamento individual
# ---------------------------------------------------------------------------


def carregar_perfil(caminho: Path) -> ResultadoCarregamentoPerfil:
    """Carrega e valida um único arquivo de perfil de agente.

    O fluxo é:

    1. Verifica se o arquivo existe; caso contrário, retorna
       ``arquivo-ausente``.
    2. Faz o parsing via ``frontmatter.load``; falhas de YAML retornam
       ``frontmatter-malformado``. Ausência total de bloco YAML retorna
       ``frontmatter-ausente``.
    3. Constrói :class:`AgentProfile` a partir do dict de metadata, injetando
       o corpo do arquivo em ``system_prompt``. Erros são mapeados para a
       categoria mais específica possível.

    Parameters
    ----------
    caminho:
        Caminho absoluto ou relativo para o arquivo ``.md``.
    """
    caminho_resolvido = Path(caminho)

    if not caminho_resolvido.exists() or not caminho_resolvido.is_file():
        return ResultadoCarregamentoPerfil(
            caminho=caminho_resolvido,
            falha=FalhaCarregamento(
                categoria="arquivo-ausente",
                mensagem=f"perfil de agente não encontrado em {caminho_resolvido}",
                caminho=caminho_resolvido,
            ),
        )

    # ------------------------------------------------------------------
    # 1. Parsing do frontmatter
    # ------------------------------------------------------------------
    try:
        # ``frontmatter.load`` aceita ``Path`` e devolve um ``Post`` com
        # ``metadata`` (dict) e ``content`` (str).
        with open(caminho_resolvido, "r", encoding="utf-8") as fp:
            post = frontmatter.load(fp)
    except Exception as exc:  # YAMLError, UnicodeDecodeError, etc.
        return ResultadoCarregamentoPerfil(
            caminho=caminho_resolvido,
            falha=FalhaCarregamento(
                categoria="frontmatter-malformado",
                mensagem=(
                    f"frontmatter YAML malformado em {caminho_resolvido}: {exc}"
                ),
                caminho=caminho_resolvido,
                detalhes={"excecao": type(exc).__name__, "erro": str(exc)},
            ),
        )

    metadata = dict(post.metadata or {})
    corpo = (post.content or "").strip()

    # python-frontmatter retorna ``metadata == {}`` quando o arquivo não
    # contém um bloco YAML delimitado por '---'. Distinguimos isso de um
    # frontmatter presente porém vazio inspecionando o início do arquivo.
    if not metadata:
        try:
            primeiras_linhas = caminho_resolvido.read_text(
                encoding="utf-8"
            ).lstrip()
        except OSError:
            primeiras_linhas = ""
        if not primeiras_linhas.startswith("---"):
            return ResultadoCarregamentoPerfil(
                caminho=caminho_resolvido,
                falha=FalhaCarregamento(
                    categoria="frontmatter-ausente",
                    mensagem=(
                        f"arquivo {caminho_resolvido} não contém bloco "
                        "YAML frontmatter delimitado por '---'"
                    ),
                    caminho=caminho_resolvido,
                ),
            )

    # ------------------------------------------------------------------
    # 2. Validação via Pydantic
    # ------------------------------------------------------------------
    dados = {**metadata, "system_prompt": corpo}
    try:
        perfil = AgentProfile(**dados)
    except ValidationError as exc:
        falha = _mapear_validation_error(caminho_resolvido, metadata, exc)
        return ResultadoCarregamentoPerfil(
            caminho=caminho_resolvido,
            falha=falha,
        )
    except TypeError as exc:
        # Acontece quando metadata contém algum tipo que o Pydantic não
        # aceita (ex: chave não-string). Tratamos como frontmatter malformado.
        return ResultadoCarregamentoPerfil(
            caminho=caminho_resolvido,
            falha=FalhaCarregamento(
                categoria="frontmatter-malformado",
                mensagem=(
                    f"frontmatter de {caminho_resolvido} contém estrutura "
                    f"incompatível: {exc}"
                ),
                caminho=caminho_resolvido,
                detalhes={"erro": str(exc)},
            ),
        )

    return ResultadoCarregamentoPerfil(caminho=caminho_resolvido, perfil=perfil)


def _mapear_validation_error(
    caminho: Path, metadata: dict[str, Any], exc: ValidationError
) -> FalhaCarregamento:
    """Mapeia um ``ValidationError`` do Pydantic para uma categoria mais
    específica de :data:`CategoriaFalha`.

    Heurística:

    - Se algum erro for ``missing`` (campo obrigatório ausente), retorna
      ``campo-obrigatorio-faltando``.
    - Se algum erro for em ``modelo`` ou na consistência par ``(nome, modelo)``
      (validador ``_check_modelo_consistente``), retorna ``modelo-divergente``.
    - Se algum erro for em ``skills_permitidas`` (Skill fora do catálogo do
      Requirement 11), retorna ``skill-nao-autorizada``.
    - Caso contrário, retorna ``validacao-pydantic`` com os erros completos
      em ``detalhes``.
    """
    erros = exc.errors()
    campos_faltando: list[str] = []
    tem_problema_modelo = False
    tem_problema_skill = False

    for erro in erros:
        loc = erro.get("loc", ())
        tipo = erro.get("type", "")
        if tipo == "missing":
            # ``loc`` é uma tupla; tomamos o primeiro componente como nome do
            # campo. Para campos aninhados, ainda assim é informativo o suficiente.
            if loc:
                campos_faltando.append(str(loc[0]))
        if "modelo" in tuple(str(x) for x in loc):
            tem_problema_modelo = True
        if "skills_permitidas" in tuple(str(x) for x in loc):
            tem_problema_skill = True
        # O validador ``_check_modelo_consistente`` produz erros sem ``modelo``
        # em ``loc`` (vai como erro do model_validator); inspecionamos a
        # mensagem.
        msg = erro.get("msg", "")
        if "agente" in msg and "modelo" in msg:
            tem_problema_modelo = True

    if campos_faltando:
        return FalhaCarregamento(
            categoria="campo-obrigatorio-faltando",
            mensagem=(
                f"perfil em {caminho} tem campos obrigatórios faltando: "
                f"{sorted(set(campos_faltando))}"
            ),
            caminho=caminho,
            detalhes={
                "campos_faltando": sorted(set(campos_faltando)),
                "erros_pydantic": erros,
            },
        )

    if tem_problema_modelo:
        return FalhaCarregamento(
            categoria="modelo-divergente",
            mensagem=(
                f"perfil em {caminho} declara modelo divergente do permitido "
                f"para o agente: {metadata.get('modelo')!r}"
            ),
            caminho=caminho,
            detalhes={
                "modelo_declarado": metadata.get("modelo"),
                "agente_declarado": metadata.get("nome"),
                "erros_pydantic": erros,
            },
        )

    if tem_problema_skill:
        return FalhaCarregamento(
            categoria="skill-nao-autorizada",
            mensagem=(
                f"perfil em {caminho} declara Skill não autorizada em "
                f"skills_permitidas: {metadata.get('skills_permitidas')!r}"
            ),
            caminho=caminho,
            detalhes={
                "skills_declaradas": metadata.get("skills_permitidas"),
                "erros_pydantic": erros,
            },
        )

    return FalhaCarregamento(
        categoria="validacao-pydantic",
        mensagem=(
            f"perfil em {caminho} falhou validação do schema AgentProfile: "
            f"{exc.error_count()} erro(s)"
        ),
        caminho=caminho,
        detalhes={"erros_pydantic": erros},
    )


# ---------------------------------------------------------------------------
# Carregamento em lote
# ---------------------------------------------------------------------------


def carregar_todos(diretorio_agents: Path) -> ResultadoCarregamentoTodos:
    """Carrega os 9 perfis esperados de ``.kiro/agents/``.

    Implementa as duas camadas de verificação exigidas por R2.1 e R2.6:

    1. **Completude**: os 9 nomes esperados existem; ausências viram
       ``arquivo-faltando-no-conselho``.
    2. **Pureza**: nenhum arquivo extra ``.md`` está na pasta; arquivos extras
       viram ``arquivo-extra``.

    Em ambos os casos, a função NÃO interrompe o processamento: continua
    carregando os perfis válidos para que o usuário receba uma lista completa
    de problemas. O atributo :attr:`ResultadoCarregamentoTodos.sucesso` só é
    ``True`` quando os 9 perfis carregam sem falhas.
    """
    diretorio = Path(diretorio_agents)
    falhas: list[FalhaCarregamento] = []
    perfis: dict[str, AgentProfile] = {}

    if not diretorio.exists() or not diretorio.is_dir():
        falhas.append(
            FalhaCarregamento(
                categoria="arquivo-ausente",
                mensagem=(
                    f"diretório de perfis {diretorio} não existe ou não é "
                    "uma pasta"
                ),
                caminho=diretorio,
            )
        )
        return ResultadoCarregamentoTodos(
            diretorio=diretorio, perfis=perfis, falhas=falhas
        )

    arquivos_md = sorted(p for p in diretorio.iterdir() if p.suffix == ".md")
    nomes_em_disco = {p.name for p in arquivos_md}

    # 1. Detectar arquivos extras (.md fora da lista canônica).
    for arquivo in arquivos_md:
        if arquivo.name not in ARQUIVOS_ESPERADOS:
            falhas.append(
                FalhaCarregamento(
                    categoria="arquivo-extra",
                    mensagem=(
                        f"arquivo extra em {diretorio}: {arquivo.name} "
                        "(não corresponde a nenhum dos 9 agentes do Conselho)"
                    ),
                    caminho=arquivo,
                    detalhes={"esperados": list(ARQUIVOS_ESPERADOS)},
                )
            )

    # 2. Detectar arquivos esperados que estão faltando.
    for esperado in ARQUIVOS_ESPERADOS:
        if esperado not in nomes_em_disco:
            falhas.append(
                FalhaCarregamento(
                    categoria="arquivo-faltando-no-conselho",
                    mensagem=(
                        f"arquivo esperado {esperado} não encontrado em "
                        f"{diretorio}"
                    ),
                    caminho=diretorio / esperado,
                )
            )

    # 3. Carregar cada arquivo válido (somente os esperados).
    for esperado in ARQUIVOS_ESPERADOS:
        caminho = diretorio / esperado
        if not caminho.exists():
            continue
        resultado = carregar_perfil(caminho)
        if resultado.sucesso and resultado.perfil is not None:
            perfis[resultado.perfil.nome] = resultado.perfil
        elif resultado.falha is not None:
            falhas.append(resultado.falha)

    return ResultadoCarregamentoTodos(
        diretorio=diretorio, perfis=perfis, falhas=falhas
    )


__all__ = [
    "ARQUIVOS_ESPERADOS",
    "NOMES_ESPERADOS",
    "CategoriaFalha",
    "FalhaCarregamento",
    "ResultadoCarregamentoPerfil",
    "ResultadoCarregamentoTodos",
    "carregar_perfil",
    "carregar_todos",
]
