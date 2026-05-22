"""Context_Loader do Conselho CAOS.

Este módulo seleciona e injeta no prompt de cada agente o subconjunto correto
de Notas_Zettel a partir do texto da tarefa, executando uma busca em largura
(BFS) limitada a 2 saltos sobre o grafo de wiki-links e aplicando truncagem
determinística para no máximo :data:`LIMITE_NOTAS_INJETADAS` notas.

Cobre os critérios R10.1 a R10.9 do ``requirements.md`` e o componente
``Context_Loader`` descrito em ``design.md`` (seções 2 e 5).

Algoritmo (resumo):

1. ``_extrair_referencias`` extrai do texto da tarefa o conjunto de nomes
   referenciados explicitamente — wiki-links ``[[Nome]]`` e menções literais a
   ``arquivo.md`` (R10.6).
2. Constrói o índice global ``stem -> Path`` varrendo
   ``raiz_zettelkasten/**/*.md`` em ordem alfabética determinística.
3. Executa BFS com fila de tuplas ``(salto, nome)`` partindo das referências
   explícitas (salto 0). Para cada nome:
   * se o arquivo não existe → registra em ``notas_ausentes`` (R10.7);
   * faz o parsing via ``python-frontmatter`` e valida o frontmatter contra
     :class:`caos.models.NotaZettel`;
   * em caso de falha, registra em ``notas_invalidas`` com a categoria
     adequada (``frontmatter-ausente``, ``frontmatter-malformado``,
     ``campo-obrigatorio-faltando`` ou ``valor-invalido``) (R10.4);
   * em caso de sucesso, agrega a nota e, se ``salto < MAX_SALTOS``, expande
     os wiki-links extraídos do corpo Markdown para a fila com ``salto + 1``.
4. Computa a contagem de backlinks de cada nota válida varrendo o índice
   global e contando referências entrantes a partir do corpo de qualquer
   outra nota.
5. Trunca para no máximo ``limite_notas`` (default 25) ordenando por
   ``(-backlinks, -timestamp(data_criacao), nome_arquivo_lex_asc)``; as notas
   removidas vão para ``notas_truncadas`` com motivo ``limite-25-excedido``
   (R10.9).
6. Calcula ``contexto_hash_sha256`` aplicando SHA-256 sobre os ``conteudo_bytes``
   das notas válidas concatenados em ordem alfabética por
   ``nome_relativo_posix`` (R10.8 e R9.1).

Convenções de implementação:

- Apenas leitura: o Context_Loader nunca modifica o filesystem.
- Mensagens de erro/auditoria em pt-BR.
- Identificadores públicos em inglês quando idiomáticos em Python.
- ``frozen=True`` em todas as dataclasses de retorno: a estrutura é imutável
  para evitar manipulação acidental por chamadores que registram o resultado
  em logs estruturados.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import frontmatter
from pydantic import ValidationError

from caos.models import NotaZettel

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Limite máximo de Notas_Zettel injetadas em um único contexto (R10.9).
LIMITE_NOTAS_INJETADAS: int = 25

#: Profundidade máxima de expansão da BFS a partir das referências explícitas
#: (R10.5). Salto 0 = referências explícitas; saltos 1 e 2 = expansão.
MAX_SALTOS: int = 2

#: Regex de wiki-link permissivo (aceita aliases ``[[Nome|texto]]``).
#: O grupo capturado pode conter ``|``; o tratamento de alias é feito por
#: :func:`extrair_wiki_links`. Usamos non-greedy para casar o menor par de
#: colchetes possível em entradas com múltiplos links na mesma linha.
_REGEX_WIKI_LINK = re.compile(r"\[\[([^\[\]]+?)\]\]")

#: Regex que identifica menções literais a um arquivo ``.md`` em um texto.
#: Captura apenas o ``stem`` (sem a extensão) — equivalente a um nome de Nota.
_REGEX_ARQUIVO_MD = re.compile(r"\b([\w-]+)\.md\b")


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------

CategoriaInvalidacao = Literal[
    "frontmatter-ausente",
    "frontmatter-malformado",
    "campo-obrigatorio-faltando",
    "valor-invalido",
]
"""Categorias de invalidação registradas em :class:`NotaInvalida` (R10.4)."""


@dataclass(frozen=True)
class WikiLink:
    """Par (nome, fonte) representando um wiki-link extraído de uma nota.

    ``nome`` é o nome-alvo do link (sem extensão ``.md``); ``fonte`` é o
    caminho absoluto do arquivo em que o link aparece.
    """

    nome: str
    fonte: Path


@dataclass(frozen=True)
class NotaInvalida:
    """Registro de uma Nota_Zettel inválida descoberta durante a BFS (R10.4).

    A categoria reflete a falha mais específica encontrada — frontmatter
    YAML ausente, malformado, com campo obrigatório faltando ou com valor
    fora do domínio permitido pelo schema :class:`NotaZettel`.
    """

    caminho: Path
    nome_nota: str
    categoria: CategoriaInvalidacao
    mensagem: str


@dataclass(frozen=True)
class NotaTruncada:
    """Registro de uma Nota_Zettel removida pela truncagem (R10.9)."""

    nome_nota: str
    backlinks: int
    motivo: Literal["limite-25-excedido"]


@dataclass(frozen=True)
class NotaCarregada:
    """Wrapper de :class:`NotaZettel` enriquecido para o Context_Loader.

    Mantém o caminho absoluto da nota, o caminho relativo POSIX dentro de
    ``raiz_zettelkasten`` (usado como chave de ordenação no hash do contexto)
    e o corpo Markdown em bytes UTF-8 (sem o frontmatter), que é o material
    consumido pelo prompt do agente.
    """

    nota: NotaZettel
    caminho: Path
    nome_relativo_posix: str
    conteudo_bytes: bytes


@dataclass(frozen=True)
class ContextoCarregado:
    """Resultado completo do :func:`carregar_contexto` (R10.4–R10.9).

    - ``referencias_explicitas``: tupla com os nomes referenciados no input,
      preservando a ordem de aparecimento e sem duplicatas (R10.6).
    - ``notas_validas``: notas com frontmatter válido, ordenadas por
      ``nome_relativo_posix`` ascendente (a mesma ordem usada para o hash).
    - ``notas_invalidas``: registros de notas com frontmatter inválido
      descobertas durante a BFS, com categoria de invalidação (R10.4).
    - ``notas_ausentes``: nomes referenciados mas inexistentes no
      filesystem do Zettelkasten (R10.7).
    - ``notas_truncadas``: notas válidas removidas pela truncagem para
      ``limite_notas`` (R10.9).
    - ``contexto_hash_sha256``: 64 hex chars do SHA-256 sobre os conteúdos
      concatenados das notas válidas em ordem alfabética (R10.8, R9.1).
    - ``contagem_backlinks``: mapeamento ``stem -> backlinks`` para fins de
      auditoria; contém todas as notas válidas e truncadas.
    """

    referencias_explicitas: tuple[str, ...]
    notas_validas: list[NotaCarregada]
    notas_invalidas: list[NotaInvalida]
    notas_ausentes: list[str]
    notas_truncadas: list[NotaTruncada]
    contexto_hash_sha256: str
    contagem_backlinks: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers públicos de parsing
# ---------------------------------------------------------------------------


def extrair_wiki_links(corpo_markdown: Optional[str]) -> list[str]:
    """Extrai os nomes-alvo dos wiki-links presentes em ``corpo_markdown``.

    Regras:

    - Aceita aliases no formato ``[[Nome|texto]]``: o nome retornado é
      sempre a parte antes do ``|``, com espaços ao redor removidos.
    - Aceita sufixo ``.md`` opcional dentro do link (``[[Nome.md]]``):
      o sufixo é descartado para que o nome casse com o ``stem`` do
      arquivo correspondente.
    - Preserva a ordem de aparecimento e elimina duplicatas mantendo a
      primeira ocorrência.
    - Entradas vazias ou compostas apenas por whitespace são ignoradas.

    O regex utilizado é ``\\[\\[([^\\[\\]]+?)\\]\\]``, deliberadamente
    permissivo para que o tratamento de alias e extensão fique concentrado
    aqui em vez de espalhado em múltiplos regex.
    """
    if not corpo_markdown:
        return []

    vistos: set[str] = set()
    resultado: list[str] = []
    for match in _REGEX_WIKI_LINK.finditer(corpo_markdown):
        bruto = match.group(1).strip()
        if "|" in bruto:
            bruto = bruto.split("|", 1)[0].strip()
        if bruto.lower().endswith(".md"):
            bruto = bruto[:-3].strip()
        if not bruto or bruto in vistos:
            continue
        vistos.add(bruto)
        resultado.append(bruto)
    return resultado


def _extrair_referencias(input_tarefa: Optional[str]) -> list[str]:
    """Extrai do texto da tarefa o conjunto de Notas referenciadas (R10.6).

    Combina duas fontes de referência preservando ordem e deduplicando:

    1. Wiki-links ``[[Nome]]`` (incluindo aliases) — via
       :func:`extrair_wiki_links`.
    2. Menções literais a ``arquivo.md`` — via :data:`_REGEX_ARQUIVO_MD`.

    O nome retornado preserva o ``case`` original (R10.6).
    """
    if not input_tarefa:
        return []

    vistos: set[str] = set()
    resultado: list[str] = []

    for nome in extrair_wiki_links(input_tarefa):
        if nome not in vistos:
            vistos.add(nome)
            resultado.append(nome)

    for match in _REGEX_ARQUIVO_MD.finditer(input_tarefa):
        nome = match.group(1).strip()
        if nome and nome not in vistos:
            vistos.add(nome)
            resultado.append(nome)

    return resultado


def computar_hash_contexto(notas: list[NotaCarregada]) -> str:
    """Calcula o SHA-256 dos conteúdos concatenados em ordem alfabética.

    A ordenação é feita por ``nome_relativo_posix`` ascendente — a mesma
    chave usada por :func:`carregar_contexto` quando entrega
    ``ContextoCarregado.notas_validas``. O retorno é uma string hexadecimal
    de 64 caracteres em minúsculas.

    Para uma lista vazia, retorna o hash do vazio
    (``e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855``),
    que ainda satisfaz a propriedade de "presença obrigatória do hash"
    do invariante R10.8.
    """
    ordenadas = sorted(notas, key=lambda n: n.nome_relativo_posix)
    h = hashlib.sha256()
    for nota in ordenadas:
        h.update(nota.conteudo_bytes)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Implementação interna — parsing e validação de uma única nota
# ---------------------------------------------------------------------------


def _categorizar_validation_error(
    exc: ValidationError,
) -> tuple[CategoriaInvalidacao, str]:
    """Mapeia um ``ValidationError`` do Pydantic para a categoria R10.4.

    Heurística:

    - Se ao menos um erro for ``type == "missing"`` (campo obrigatório
      ausente), classifica como ``campo-obrigatorio-faltando`` e enumera
      os campos faltantes.
    - Caso contrário, classifica como ``valor-invalido`` com a lista de
      pares ``(campo, mensagem)`` reportados pelo Pydantic.
    """
    erros = exc.errors()
    faltantes = [
        ".".join(str(p) for p in err.get("loc", ()))
        for err in erros
        if err.get("type") == "missing"
    ]
    if faltantes:
        nomes = sorted(set(faltantes))
        return (
            "campo-obrigatorio-faltando",
            f"campos obrigatórios faltando: {nomes}",
        )

    detalhes = [
        f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', '')}"
        for err in erros
    ]
    return ("valor-invalido", f"valor inválido: {detalhes}")


def _carregar_e_validar(
    caminho: Path, nome_referencia: str, raiz: Path
) -> tuple[Optional[NotaCarregada], Optional[NotaInvalida]]:
    """Lê um único arquivo ``.md`` e valida-o contra :class:`NotaZettel`.

    Retorna sempre exatamente uma das pontas da tupla preenchida: ou
    ``(NotaCarregada, None)`` em caso de sucesso, ou ``(None, NotaInvalida)``
    em caso de falha. As categorias de falha seguem :data:`CategoriaInvalidacao`.
    """
    # ------------------------------------------------------------------
    # 1. Parsing do frontmatter
    # ------------------------------------------------------------------
    try:
        with open(caminho, "r", encoding="utf-8") as fp:
            post = frontmatter.load(fp)
    except Exception as exc:  # YAMLError, UnicodeDecodeError, OSError
        return None, NotaInvalida(
            caminho=caminho,
            nome_nota=nome_referencia,
            categoria="frontmatter-malformado",
            mensagem=(
                f"frontmatter YAML malformado em {caminho}: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    metadata: dict[str, Any] = dict(post.metadata or {})
    corpo: str = post.content or ""

    # python-frontmatter retorna metadata vazio tanto quando o arquivo não
    # tem frontmatter quanto quando tem um bloco vazio. Distinguimos os
    # dois casos inspecionando o início do arquivo.
    if not metadata:
        try:
            inicio = caminho.read_text(encoding="utf-8").lstrip()
        except OSError:
            inicio = ""
        if not inicio.startswith("---"):
            return None, NotaInvalida(
                caminho=caminho,
                nome_nota=nome_referencia,
                categoria="frontmatter-ausente",
                mensagem=(
                    f"arquivo {caminho} não contém bloco YAML frontmatter "
                    "delimitado por '---'"
                ),
            )

    # ------------------------------------------------------------------
    # 2. Validação contra o schema NotaZettel
    # ------------------------------------------------------------------
    try:
        nota = NotaZettel(**metadata)
    except ValidationError as exc:
        cat, msg = _categorizar_validation_error(exc)
        return None, NotaInvalida(
            caminho=caminho,
            nome_nota=nome_referencia,
            categoria=cat,
            mensagem=f"{msg} (arquivo {caminho})",
        )
    except TypeError as exc:
        # Acontece quando metadata contém estrutura incompatível
        # (chaves não-string, valores não-serializáveis, etc.).
        return None, NotaInvalida(
            caminho=caminho,
            nome_nota=nome_referencia,
            categoria="frontmatter-malformado",
            mensagem=(
                f"frontmatter de {caminho} contém estrutura incompatível: "
                f"{exc}"
            ),
        )

    # ------------------------------------------------------------------
    # 3. Empacotamento em NotaCarregada
    # ------------------------------------------------------------------
    try:
        nome_rel = caminho.relative_to(raiz).as_posix()
    except ValueError:
        # Defensivo: caminho fora de raiz (não deveria acontecer porque o
        # índice é construído via raiz.rglob); cai como caminho absoluto.
        nome_rel = caminho.as_posix()

    return (
        NotaCarregada(
            nota=nota,
            caminho=caminho,
            nome_relativo_posix=nome_rel,
            conteudo_bytes=corpo.encode("utf-8"),
        ),
        None,
    )


def _ler_wiki_links_de_arquivo(caminho: Path) -> list[str]:
    """Lê apenas os wiki-links do corpo de um ``.md`` (sem validar frontmatter).

    Usado durante a pré-computação do índice global para evitar duplicar a
    validação Pydantic em arquivos potencialmente inválidos: nos interessam
    aqui apenas as arestas de saída do grafo, e o validador será aplicado
    novamente quando a BFS visitar a nota.

    Falhas de leitura retornam lista vazia em vez de propagar exceção.
    """
    try:
        with open(caminho, "r", encoding="utf-8") as fp:
            post = frontmatter.load(fp)
    except Exception:
        return []
    return extrair_wiki_links(post.content or "")


# ---------------------------------------------------------------------------
# API pública — função e classe
# ---------------------------------------------------------------------------


def carregar_contexto(
    input_tarefa: str,
    *,
    raiz_zettelkasten: Path,
    limite_notas: int = LIMITE_NOTAS_INJETADAS,
) -> ContextoCarregado:
    """Carrega o contexto completo para um agente a partir de ``input_tarefa``.

    Executa o fluxo descrito no docstring do módulo (extração → BFS →
    backlinks → truncagem → hash). Levanta :class:`ValueError` quando
    ``raiz_zettelkasten`` não é um diretório existente; ``limite_notas`` é
    forçado para ``>= 0``.
    """
    raiz = Path(raiz_zettelkasten)
    if not raiz.is_dir():
        raise ValueError(
            f"raiz_zettelkasten não é um diretório válido: {raiz}"
        )
    if limite_notas < 0:
        raise ValueError(
            f"limite_notas deve ser >= 0; recebido {limite_notas}"
        )

    # ------------------------------------------------------------------
    # 1. Extrair referências explícitas
    # ------------------------------------------------------------------
    referencias = _extrair_referencias(input_tarefa)

    # ------------------------------------------------------------------
    # 2. Construir índice global stem -> Path + cache de wiki-links de saída
    # ------------------------------------------------------------------
    indice: dict[str, Path] = {}
    wiki_links_globais: dict[str, list[str]] = {}
    for caminho_md in sorted(raiz.rglob("*.md")):
        if not caminho_md.is_file():
            continue
        stem = caminho_md.stem
        # Em caso de colisão de stem (mesma nota em pastas distintas), a
        # primeira ocorrência em ordem alfabética vence — comportamento
        # determinístico para reprodutibilidade.
        if stem in indice:
            continue
        indice[stem] = caminho_md
        wiki_links_globais[stem] = _ler_wiki_links_de_arquivo(caminho_md)

    # ------------------------------------------------------------------
    # 3. BFS limitada a MAX_SALTOS
    # ------------------------------------------------------------------
    visitadas: set[str] = set()
    fila: deque[tuple[int, str]] = deque((0, ref) for ref in referencias)
    notas_validas: list[NotaCarregada] = []
    notas_invalidas: list[NotaInvalida] = []
    notas_ausentes: list[str] = []

    while fila:
        salto, nome = fila.popleft()
        if nome in visitadas:
            continue
        visitadas.add(nome)

        if salto > MAX_SALTOS:
            # Defensivo: nunca enfileiramos saltos > MAX_SALTOS, mas se
            # alguma futura modificação fizer isso o limite ainda vale.
            continue

        if nome not in indice:
            notas_ausentes.append(nome)
            continue

        caminho = indice[nome]
        nota_carregada, falha = _carregar_e_validar(caminho, nome, raiz)
        if falha is not None:
            notas_invalidas.append(falha)
            continue
        assert nota_carregada is not None  # narrowing para o type checker
        notas_validas.append(nota_carregada)

        # Expansão: só adiciona próximos saltos enquanto há orçamento.
        if salto < MAX_SALTOS:
            for link in wiki_links_globais.get(nome, []):
                if link not in visitadas:
                    fila.append((salto + 1, link))

    # ------------------------------------------------------------------
    # 4. Backlinks globais (varre o índice inteiro)
    # ------------------------------------------------------------------
    stems_validos = {
        Path(n.nome_relativo_posix).stem for n in notas_validas
    }
    contagem_por_stem: dict[str, int] = {s: 0 for s in stems_validos}
    for src_stem, links in wiki_links_globais.items():
        for link in links:
            if link in contagem_por_stem and link != src_stem:
                contagem_por_stem[link] += 1

    # ------------------------------------------------------------------
    # 5. Truncagem para no máximo `limite_notas`
    # ------------------------------------------------------------------
    notas_truncadas: list[NotaTruncada] = []
    if len(notas_validas) > limite_notas:

        def _chave(n: NotaCarregada) -> tuple[int, float, str]:
            stem = Path(n.nome_relativo_posix).stem
            backlinks = contagem_por_stem.get(stem, 0)
            timestamp = n.nota.data_criacao.timestamp()
            # Ordem: backlinks desc → data_criacao desc → nome lex asc.
            return (-backlinks, -timestamp, n.nome_relativo_posix)

        notas_validas.sort(key=_chave)
        descartadas = notas_validas[limite_notas:]
        notas_validas = notas_validas[:limite_notas]
        for n in descartadas:
            stem = Path(n.nome_relativo_posix).stem
            notas_truncadas.append(
                NotaTruncada(
                    nome_nota=stem,
                    backlinks=contagem_por_stem.get(stem, 0),
                    motivo="limite-25-excedido",
                )
            )

    # ------------------------------------------------------------------
    # 6. Ordena válidas finais por nome alfabético e calcula o hash
    # ------------------------------------------------------------------
    notas_validas.sort(key=lambda n: n.nome_relativo_posix)
    contexto_hash = computar_hash_contexto(notas_validas)

    contagem_dict: dict[str, int] = {}
    for n in notas_validas:
        stem = Path(n.nome_relativo_posix).stem
        contagem_dict[stem] = contagem_por_stem.get(stem, 0)
    for t in notas_truncadas:
        contagem_dict[t.nome_nota] = t.backlinks

    return ContextoCarregado(
        referencias_explicitas=tuple(referencias),
        notas_validas=notas_validas,
        notas_invalidas=notas_invalidas,
        notas_ausentes=notas_ausentes,
        notas_truncadas=notas_truncadas,
        contexto_hash_sha256=contexto_hash,
        contagem_backlinks=contagem_dict,
    )


class ContextLoader:
    """Wrapper orientado a objeto consumido pelo Orchestrator (Athena).

    Permite ao orquestrador validar a raiz uma única vez (no construtor) e
    reutilizar a mesma instância para múltiplas invocações, mantendo a API
    de :func:`carregar_contexto` para baixo.
    """

    def __init__(self, *, raiz_zettelkasten: Path) -> None:
        raiz = Path(raiz_zettelkasten)
        if not raiz.is_dir():
            raise ValueError(
                f"raiz_zettelkasten não é um diretório válido: {raiz}"
            )
        self.raiz: Path = raiz

    def carregar(
        self,
        input_tarefa: str,
        *,
        limite_notas: int = LIMITE_NOTAS_INJETADAS,
    ) -> ContextoCarregado:
        """Delegate para :func:`carregar_contexto` usando ``self.raiz``."""
        return carregar_contexto(
            input_tarefa,
            raiz_zettelkasten=self.raiz,
            limite_notas=limite_notas,
        )


__all__ = [
    # Constantes
    "LIMITE_NOTAS_INJETADAS",
    "MAX_SALTOS",
    # Tipos
    "CategoriaInvalidacao",
    "WikiLink",
    "NotaInvalida",
    "NotaTruncada",
    "NotaCarregada",
    "ContextoCarregado",
    # Helpers
    "extrair_wiki_links",
    "computar_hash_contexto",
    # API principal
    "carregar_contexto",
    "ContextLoader",
]
