"""Bias_Filter do Explorador (R12).

Este módulo aplica os filtros antibias do Conselho CAOS a Notas_Zettel
derivadas de papers científicos antes de serem indexadas no Zettelkasten.
Cobre integralmente os critérios R12.1 a R12.8 do ``requirements.md`` e o
componente ``Bias_Filter`` descrito em ``design.md`` (seção 2 e Property 8).

Responsabilidades:

1. **Atribuição de status** (:func:`avaliar_paper`): aplica em ordem de
   precedência os critérios objetivos do Explorador
   (``dados-incompletos`` > ``rejeitada`` > ``amostra-insuficiente`` >
   ``out-of-sample-insuficiente`` > ``bias-nao-tratado`` > ``aprovada``).
2. **Construção de Nota_Zettel** (:func:`construir_nota_paper`): wrapper que
   primeiro avalia o status e só então instancia :class:`NotaPaper`,
   garantindo que o status atribuído reflete sempre o resultado da
   avaliação automática.
3. **Persistência em Papers/** (:func:`armazenar_em_papers`): grava a
   Nota_Zettel em ``CAOS_Zettelkasten/Papers/{slug}.md`` independentemente
   do status (R12.5).
4. **Guard de wiki-link de entrada** (:func:`validar_link_de_entrada`):
   bloqueia a criação de qualquer link entrante (de outra nota apontando
   para a Nota_Zettel de paper) quando o status final é diferente de
   ``aprovada`` (R12.8 / Property 8).

Convenções:

- Valida o tipo dos campos com cuidado de não aceitar ``bool`` onde se
  espera um ``int`` numérico (em Python ``isinstance(True, int) is True``).
- Mensagens de erro/auditoria em pt-BR.
- Identificadores públicos em inglês quando idiomáticos em Python.
- Usa ``python-frontmatter`` para gravar arquivos com YAML frontmatter
  consistentes com o restante do orquestrador.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import frontmatter

from caos.models import NotaPaper, StatusPaper

# ---------------------------------------------------------------------------
# Constantes (R12.2-R12.7)
# ---------------------------------------------------------------------------

#: Limite mínimo de Sharpe replicado para que um paper possa ser ``aprovada``.
#: Abaixo deste valor o status passa a ``rejeitada`` (R12.2).
LIMITE_SHARPE: float = 0.5

#: Tamanho mínimo de amostra (in-sample) em dias úteis (R12.3).
MINIMO_SAMPLE_SIZE_DIAS_UTEIS: int = 250

#: Período mínimo de validação out-of-sample em dias úteis (R12.7).
MINIMO_OUT_OF_SAMPLE_DIAS_UTEIS: int = 60


# ---------------------------------------------------------------------------
# Tipos de retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoValidacaoLink:
    """Resultado da avaliação de um link de entrada candidato (R12.8).

    - ``autorizado``: ``True`` quando o link de entrada pode ser criado;
      ``False`` quando o guard bloqueia a criação.
    - ``motivo``: mensagem em pt-BR explicando o motivo do bloqueio.
      ``None`` quando ``autorizado`` é ``True``.
    - ``status_alvo``: status corrente da Nota_Zettel-alvo, replicado para
      facilitar auditoria sem que o caller precise inspecionar a nota.
    """

    autorizado: bool
    motivo: Optional[str] = None
    status_alvo: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _eh_numerico(valor: Any) -> bool:
    """Retorna ``True`` se ``valor`` é ``int`` ou ``float`` (e não ``bool``).

    Rejeitar ``bool`` aqui é essencial porque em Python
    ``isinstance(True, int) is True`` — sem essa guarda, um campo
    ``sharpe_replicado=True`` seria interpretado como o Sharpe ``1.0``.
    """
    if isinstance(valor, bool):
        return False
    return isinstance(valor, (int, float))


def _eh_inteiro(valor: Any) -> bool:
    """Retorna ``True`` se ``valor`` é ``int`` estrito (sem ``bool``).

    Rejeita ``float`` mesmo quando inteiro-equivalente: contagens em dias
    úteis são naturais e a presença de ``250.0`` no input geralmente sinaliza
    inconsistência upstream que deve cair em ``dados-incompletos``.
    """
    if isinstance(valor, bool):
        return False
    return isinstance(valor, int)


def _slug_simples(titulo: str) -> str:
    """Converte ``titulo`` em um slug filesystem-safe.

    Estratégia: normaliza para NFKD, remove acentos, troca tudo que não é
    alfanumérico por hífen, colapsa hífens consecutivos e corta em 80
    caracteres. Caso o resultado seja vazio (entrada apenas com símbolos),
    devolve ``nota-sem-titulo`` para evitar arquivos com nome vazio.
    """
    # Normaliza acentos (ex.: "Volatilidade" → "Volatilidade", "ção" → "cao")
    texto = unicodedata.normalize("NFKD", titulo)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    # Substitui qualquer caractere não [a-z0-9] por hífen.
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = texto.strip("-")
    if not texto:
        return "nota-sem-titulo"
    return texto[:80]


# ---------------------------------------------------------------------------
# R12.1-R12.7 — Avaliação automática de status
# ---------------------------------------------------------------------------


def avaliar_paper(
    *,
    sharpe_replicado: Optional[float],
    sample_size: Optional[int],
    out_of_sample_periodo: Optional[int],
    instrumento_testado: Optional[str],
    survivorship_bias_tratado: Optional[bool],
) -> StatusPaper:
    """Atribui ``status`` a uma Nota_Zettel de paper conforme R12.1–R12.7.

    Aplica a precedência exigida pelo critério 1 do Requirement 12:

    1. ``dados-incompletos`` (R12.6): qualquer um dos 5 campos é ``None`` ou
       tem tipo divergente do esperado (ou ``instrumento_testado`` é string
       vazia, equivalente a "valor fora do domínio").
    2. ``rejeitada`` (R12.2): ``sharpe_replicado < LIMITE_SHARPE``.
    3. ``amostra-insuficiente`` (R12.3): ``sample_size <
       MINIMO_SAMPLE_SIZE_DIAS_UTEIS``.
    4. ``out-of-sample-insuficiente`` (R12.7): ``out_of_sample_periodo <
       MINIMO_OUT_OF_SAMPLE_DIAS_UTEIS``.
    5. ``bias-nao-tratado`` (R12.4): ``survivorship_bias_tratado is False``.
    6. ``aprovada``: nenhuma das condições acima dispara.

    A ordem é aplicada **passo a passo** (a primeira regra que dispara
    define o status), conforme o critério 1: não é equivalente a "aplicar
    todas e escolher a mais grave", embora neste conjunto de regras as
    duas semânticas coincidam.
    """
    # ------------------------------------------------------------------
    # R12.6 + R12.1 — dados-incompletos (precedência máxima)
    # ------------------------------------------------------------------
    if sharpe_replicado is None or not _eh_numerico(sharpe_replicado):
        return "dados-incompletos"
    if sample_size is None or not _eh_inteiro(sample_size) or sample_size < 0:
        return "dados-incompletos"
    if (
        out_of_sample_periodo is None
        or not _eh_inteiro(out_of_sample_periodo)
        or out_of_sample_periodo < 0
    ):
        return "dados-incompletos"
    if (
        instrumento_testado is None
        or not isinstance(instrumento_testado, str)
        or not instrumento_testado.strip()
    ):
        return "dados-incompletos"
    if survivorship_bias_tratado is None or not isinstance(
        survivorship_bias_tratado, bool
    ):
        return "dados-incompletos"

    # ------------------------------------------------------------------
    # R12.2 — rejeitada
    # ------------------------------------------------------------------
    if sharpe_replicado < LIMITE_SHARPE:
        return "rejeitada"

    # ------------------------------------------------------------------
    # R12.3 — amostra-insuficiente
    # ------------------------------------------------------------------
    if sample_size < MINIMO_SAMPLE_SIZE_DIAS_UTEIS:
        return "amostra-insuficiente"

    # ------------------------------------------------------------------
    # R12.7 — out-of-sample-insuficiente
    # ------------------------------------------------------------------
    if out_of_sample_periodo < MINIMO_OUT_OF_SAMPLE_DIAS_UTEIS:
        return "out-of-sample-insuficiente"

    # ------------------------------------------------------------------
    # R12.4 — bias-nao-tratado
    # ------------------------------------------------------------------
    if survivorship_bias_tratado is False:
        return "bias-nao-tratado"

    # ------------------------------------------------------------------
    # Passou por todas as regras → aprovada
    # ------------------------------------------------------------------
    return "aprovada"


# ---------------------------------------------------------------------------
# Construção de NotaPaper com status atribuído automaticamente
# ---------------------------------------------------------------------------


def construir_nota_paper(
    *,
    titulo: str,
    tags: list[str],
    data_criacao: Any,
    agente_autor: str,
    sharpe_replicado: Optional[float],
    sample_size: Optional[int],
    out_of_sample_periodo: Optional[int],
    instrumento_testado: Optional[str],
    survivorship_bias_tratado: Optional[bool],
    corpo_markdown: Optional[str] = None,
    wiki_links: Optional[list[str]] = None,
) -> NotaPaper:
    """Cria uma :class:`NotaPaper` com ``status`` atribuído por R12.1–R12.7.

    Sequência de execução:

    1. Invoca :func:`avaliar_paper` sobre os 5 campos antibias.
    2. Se o status resultante for ``dados-incompletos``, normaliza os
       campos faltantes/inválidos para valores neutros aceitáveis pelo
       schema Pydantic (``sharpe_replicado=0.0``, ``sample_size=0``,
       ``out_of_sample_periodo=0``, ``instrumento_testado="desconhecido"``,
       ``survivorship_bias_tratado=False``). Isso permite que a Nota seja
       gravada em ``Papers/`` (R12.5) carregando o motivo do problema no
       próprio campo ``status``, sem perder o registro do paper.
    3. Instancia :class:`NotaPaper` com ``area="Papers"`` (forçado).

    O parâmetro ``area`` deliberadamente **não** é exposto: toda nota
    construída por este helper pertence à área ``Papers`` (design 3.6).
    """
    status = avaliar_paper(
        sharpe_replicado=sharpe_replicado,
        sample_size=sample_size,
        out_of_sample_periodo=out_of_sample_periodo,
        instrumento_testado=instrumento_testado,
        survivorship_bias_tratado=survivorship_bias_tratado,
    )

    # Normalização para casos `dados-incompletos`: mantemos uma Nota
    # gravável em vez de propagar o erro.
    sharpe_norm: float = (
        float(sharpe_replicado)
        if _eh_numerico(sharpe_replicado)
        else 0.0
    )
    sample_norm: int = (
        int(sample_size)
        if _eh_inteiro(sample_size) and isinstance(sample_size, int) and sample_size >= 0
        else 0
    )
    oos_norm: int = (
        int(out_of_sample_periodo)
        if _eh_inteiro(out_of_sample_periodo)
        and isinstance(out_of_sample_periodo, int)
        and out_of_sample_periodo >= 0
        else 0
    )
    instrumento_norm: str = (
        instrumento_testado.strip()
        if isinstance(instrumento_testado, str) and instrumento_testado.strip()
        else "desconhecido"
    )
    bias_norm: bool = (
        survivorship_bias_tratado
        if isinstance(survivorship_bias_tratado, bool)
        else False
    )

    return NotaPaper(
        titulo=titulo,
        area="Papers",
        tags=tags,
        data_criacao=data_criacao,
        agente_autor=agente_autor,
        sharpe_replicado=sharpe_norm,
        sample_size=sample_norm,
        out_of_sample_periodo=oos_norm,
        instrumento_testado=instrumento_norm,
        survivorship_bias_tratado=bias_norm,
        status=status,
        corpo_markdown=corpo_markdown,
        wiki_links=list(wiki_links) if wiki_links else [],
    )


# ---------------------------------------------------------------------------
# R12.5 — Persistência em CAOS_Zettelkasten/Papers/
# ---------------------------------------------------------------------------


def armazenar_em_papers(nota: NotaPaper, raiz_zettelkasten: Path) -> Path:
    """Grava ``nota`` em ``raiz_zettelkasten/Papers/{slug}.md`` (R12.5).

    O arquivo é gravado **independentemente do valor de** ``status`` — o
    Requirement 12.5 é explícito quanto a isso: rejeitar uma Nota_Zettel
    de paper não significa apagá-la, e sim apenas marcar seu status e
    impedir que ela receba links de entrada (responsabilidade do guard
    :func:`validar_link_de_entrada`).

    O conteúdo gravado tem dois blocos:

    1. Frontmatter YAML serializado por ``python-frontmatter``, contendo
       todos os campos do schema :class:`NotaPaper` (incluindo o status
       atribuído pelo Bias_Filter).
    2. Corpo Markdown vindo de ``nota.corpo_markdown`` (string vazia
       quando ``None``).

    Levanta :class:`ValueError` quando ``raiz_zettelkasten`` não é um
    diretório existente.
    """
    raiz = Path(raiz_zettelkasten)
    if not raiz.is_dir():
        raise ValueError(
            f"raiz_zettelkasten não é um diretório válido: {raiz}"
        )

    pasta_papers = raiz / "Papers"
    pasta_papers.mkdir(parents=True, exist_ok=True)

    slug = _slug_simples(nota.titulo)
    arquivo = pasta_papers / f"{slug}.md"

    # Monta os metadados YAML (frontmatter) a partir do schema Pydantic.
    metadados: dict[str, Any] = {
        "titulo": nota.titulo,
        "area": nota.area,
        "tags": list(nota.tags),
        "data_criacao": nota.data_criacao.isoformat().replace(
            "+00:00", "Z"
        ),
        "agente_autor": nota.agente_autor,
        "sharpe_replicado": nota.sharpe_replicado,
        "sample_size": nota.sample_size,
        "out_of_sample_periodo": nota.out_of_sample_periodo,
        "instrumento_testado": nota.instrumento_testado,
        "survivorship_bias_tratado": nota.survivorship_bias_tratado,
        "status": nota.status,
    }

    post = frontmatter.Post(
        nota.corpo_markdown or "",
        **metadados,
    )

    arquivo.write_text(
        frontmatter.dumps(post) + "\n",
        encoding="utf-8",
    )
    return arquivo


# ---------------------------------------------------------------------------
# R12.8 — Guard de wiki-link de entrada (Property 8)
# ---------------------------------------------------------------------------


def validar_link_de_entrada(
    nota_alvo_paper: NotaPaper,
    *,
    permitir_se_aprovada: bool = True,
) -> ResultadoValidacaoLink:
    """Decide se um link de entrada para ``nota_alvo_paper`` pode ser criado.

    Implementa o guard exigido por R12.8 / Property 8: nenhuma Nota_Zettel
    de paper com status diferente de ``aprovada`` pode receber wiki-links
    entrantes a partir de outras notas do Zettelkasten.

    O parâmetro ``permitir_se_aprovada`` é um interruptor defensivo. Em
    operação normal vale ``True`` (default): se o status for ``aprovada``,
    o link é autorizado. Caso o caller queira bloquear *qualquer* link de
    entrada — por exemplo durante uma fase de quarentena administrativa —
    pode passar ``False`` e receber sempre ``autorizado=False``.

    Não faz I/O: a criação efetiva do link é responsabilidade do
    Explorador (componente que persiste as notas que contêm o link
    entrante). Este guard apenas calcula a decisão e deve ser consultado
    *antes* da escrita.
    """
    if nota_alvo_paper.status == "aprovada":
        if permitir_se_aprovada:
            return ResultadoValidacaoLink(
                autorizado=True,
                motivo=None,
                status_alvo="aprovada",
            )
        return ResultadoValidacaoLink(
            autorizado=False,
            motivo=(
                "criação de link de entrada bloqueada por configuração "
                "(permitir_se_aprovada=False)"
            ),
            status_alvo="aprovada",
        )

    return ResultadoValidacaoLink(
        autorizado=False,
        motivo=(
            f"Nota_Zettel de paper {nota_alvo_paper.titulo!r} tem "
            f"status={nota_alvo_paper.status!r}; R12.8 impede criação "
            "de wiki-link de entrada para Notas com status diferente "
            "de 'aprovada'."
        ),
        status_alvo=nota_alvo_paper.status,
    )


__all__ = [
    # Constantes
    "LIMITE_SHARPE",
    "MINIMO_SAMPLE_SIZE_DIAS_UTEIS",
    "MINIMO_OUT_OF_SAMPLE_DIAS_UTEIS",
    # Tipos
    "ResultadoValidacaoLink",
    # API pública
    "avaliar_paper",
    "construir_nota_paper",
    "armazenar_em_papers",
    "validar_link_de_entrada",
]
