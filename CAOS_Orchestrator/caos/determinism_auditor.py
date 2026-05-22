"""Determinism_Auditor — auditoria de reprodutibilidade e regressões.

Este módulo implementa a Task 11 do Spec ``caos-conselho-infra`` cobrindo
R9.1–R9.5 do ``requirements.md``:

- :func:`derivar_reproduzivel` deriva o campo ``reproduzivel`` da
  ``Decisao_Do_Conselho`` a partir das marcações ``nao_deterministico``
  dos turnos do Debate (R9.4):

  * ``"true"`` quando nenhum turno é marcado;
  * ``"false"`` quando todos os turnos são marcados;
  * ``"parcial"`` quando ao menos um — mas não todos — é marcado;
  * ``"true"`` quando a lista é vazia (sem turnos, sem violação).

- :func:`normalizar_texto` aplica a normalização exigida por R9.3 antes
  da comparação byte-a-byte: ``CRLF → LF`` e remoção do *trailing
  whitespace* de cada linha. Linhas em branco intermediárias são
  preservadas.

- :func:`comparar_turnos_byte_a_byte` compara dois turnos posicionais de
  duas execuções do mesmo Debate. Se um deles está marcado como
  ``nao_deterministico``, retorna ``pulado-nao-deterministico`` sem
  comparar o conteúdo (R9.2). Caso contrário, valida metadados
  relevantes (``agente``, ``numero``, ``fase``, ``status``,
  ``notas_injetadas`` como conjunto, ``contexto_hash_sha256``) e o
  ``conteudo_markdown`` após normalização (R9.3).

- :func:`detectar_regressao` compara a decisão atual com uma decisão
  anterior similar (mesmo input/contexto, presumido pelo orquestrador),
  considerando apenas ``decisao_final.proposta_aceita`` e o multiset de
  vetos. Quando há divergência, marca ``regressao_detectada=True`` e
  produz o diff dos campos divergentes (R9.5).

Convenções:

- Apenas leitura: o auditor nunca modifica o filesystem nem as instâncias
  recebidas.
- Mensagens de auditoria em pt-BR.
- Retornos imutáveis (``frozen=True``) para evitar mutação acidental por
  chamadores que registram o resultado em logs estruturados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from caos.models import DecisaoDoConselho, Turno, Veto

# ---------------------------------------------------------------------------
# Tipos de resultado
# ---------------------------------------------------------------------------

#: Discriminador estável do resultado de :func:`comparar_turnos_byte_a_byte`.
MotivoComparacao = Literal[
    "iguais",
    "diferentes",
    "pulado-nao-deterministico",
    "metadados-divergentes",
]


@dataclass(frozen=True)
class ResultadoComparacao:
    """Resultado de :func:`comparar_turnos_byte_a_byte` (R9.3).

    Atributos
    ---------
    iguais
        ``True`` somente quando ``motivo == "iguais"``. Em
        ``pulado-nao-deterministico`` o valor é ``False`` por convenção
        (não houve confirmação de igualdade — o turno foi pulado).
    motivo
        Discriminador estável usado pelo orquestrador para decidir como
        registrar a comparação na ``Decisao_Do_Conselho``.
    diff_descricao
        Texto livre em pt-BR descrevendo a primeira divergência encontrada,
        útil para auditoria humana. ``None`` quando ``motivo == "iguais"``
        ou quando o turno foi pulado.
    """

    iguais: bool
    motivo: MotivoComparacao
    diff_descricao: Optional[str] = None


@dataclass(frozen=True)
class ResultadoRegressao:
    """Resultado de :func:`detectar_regressao` (R9.5).

    Atributos
    ---------
    regressao_detectada
        ``True`` quando a decisão atual difere da anterior em
        ``proposta_aceita`` ou no multiset de vetos.
    diff_proposta
        Tupla ``(proposta_aceita_anterior, proposta_aceita_atual)`` quando
        há divergência nesse campo; ``None`` caso contrário.
    diff_vetos
        Tupla ``(apenas_anterior, apenas_atual)`` em que cada elemento é o
        conjunto de tuplas hashables ``(tipo, autor, decisao, proposta_alvo)``
        presentes só no respectivo lado. ``None`` quando os multisets são
        iguais.
    """

    regressao_detectada: bool
    diff_proposta: Optional[tuple[Optional[str], Optional[str]]] = None
    diff_vetos: Optional[tuple[set[tuple[str, str, str, str]], set[tuple[str, str, str, str]]]] = None


# ---------------------------------------------------------------------------
# R9.4 — Derivação do campo `reproduzivel`
# ---------------------------------------------------------------------------


def derivar_reproduzivel(
    turnos: list[Turno],
) -> Literal["true", "parcial", "false"]:
    """Deriva o campo ``reproduzivel`` a partir dos turnos do Debate.

    Regras (R9.4):

    - ``"true"`` se nenhum turno está marcado ``nao_deterministico``;
    - ``"false"`` se todos os turnos estão marcados;
    - ``"parcial"`` em qualquer caso misto.

    Edge case explícito: lista vazia retorna ``"true"`` — sem turnos
    registrados, não há violação de determinismo a reportar.
    """
    if not turnos:
        return "true"
    marcados = [t.nao_deterministico for t in turnos]
    if not any(marcados):
        return "true"
    if all(marcados):
        return "false"
    return "parcial"


# ---------------------------------------------------------------------------
# R9.3 — Normalização de texto
# ---------------------------------------------------------------------------


def normalizar_texto(texto: str) -> str:
    """Aplica a normalização exigida por R9.3 antes da comparação.

    Operações executadas, nesta ordem:

    1. ``CRLF (\\r\\n) → LF (\\n)`` — uniformiza o fim de linha entre
       Windows (CRLF) e Unix (LF).
    2. Para cada linha, remove o *trailing whitespace* (espaços, tabs,
       ``\\r`` e ``\\v`` no final) preservando o conteúdo interno.

    Linhas em branco intermediárias são preservadas (mantêm comprimento
    zero após a remoção do trailing whitespace, o que é exatamente o
    estado em que já estavam). A última linha é tratada como qualquer
    outra: se o texto terminar em ``\\n``, o resultado também termina em
    ``\\n``; se não terminar, o resultado também não termina.
    """
    if not texto:
        return texto
    # 1. CRLF → LF (deliberadamente NÃO normalizamos lone CR, pois o
    #    requisito 9.3 menciona apenas CRLF → LF).
    sem_crlf = texto.replace("\r\n", "\n")
    # 2. Remoção de trailing whitespace por linha. ``str.splitlines(True)``
    #    preserva o terminador (``\n`` ou nada na última linha), de forma
    #    que recompomos o texto exatamente sem inserir/perder linhas.
    linhas: list[str] = []
    for linha in sem_crlf.splitlines(keepends=True):
        if linha.endswith("\n"):
            corpo = linha[:-1]
            linhas.append(corpo.rstrip(" \t\r\v\f") + "\n")
        else:
            linhas.append(linha.rstrip(" \t\r\v\f"))
    return "".join(linhas)


# ---------------------------------------------------------------------------
# R9.3 — Comparação byte-a-byte de turnos
# ---------------------------------------------------------------------------


def comparar_turnos_byte_a_byte(
    t1: Turno, t2: Turno
) -> ResultadoComparacao:
    """Compara dois turnos posicionalmente equivalentes (R9.2/R9.3).

    Ordem de avaliação:

    1. Se ``t1.nao_deterministico`` ou ``t2.nao_deterministico`` é
       ``True``, retorna ``pulado-nao-deterministico`` (R9.2 — não há
       garantia de igualdade para esse turno).
    2. Caso contrário, valida os metadados ``numero``, ``agente``,
       ``fase``, ``status``, ``contexto_hash_sha256`` e ``notas_injetadas``
       (como ``set``). Qualquer divergência dispara ``metadados-divergentes``.
    3. Por fim, compara ``conteudo_markdown`` após
       :func:`normalizar_texto`. Igual → ``iguais``; diferente →
       ``diferentes``.

    Notas vazias (``None``) em ``conteudo_markdown`` são tratadas como
    string vazia para fins de comparação. Notas injetadas são comparadas
    como conjunto porque sua ordem de listagem no cabeçalho do turno não
    é semanticamente significativa.
    """
    if t1.nao_deterministico or t2.nao_deterministico:
        return ResultadoComparacao(
            iguais=False,
            motivo="pulado-nao-deterministico",
            diff_descricao=None,
        )

    # Metadados — ordem fixa para diff determinístico em pt-BR.
    if t1.numero != t2.numero:
        return ResultadoComparacao(
            iguais=False,
            motivo="metadados-divergentes",
            diff_descricao=(
                f"numero divergente: {t1.numero!r} vs {t2.numero!r}"
            ),
        )
    if t1.agente != t2.agente:
        return ResultadoComparacao(
            iguais=False,
            motivo="metadados-divergentes",
            diff_descricao=(
                f"agente divergente: {t1.agente!r} vs {t2.agente!r}"
            ),
        )
    if t1.fase != t2.fase:
        return ResultadoComparacao(
            iguais=False,
            motivo="metadados-divergentes",
            diff_descricao=f"fase divergente: {t1.fase!r} vs {t2.fase!r}",
        )
    if t1.status != t2.status:
        return ResultadoComparacao(
            iguais=False,
            motivo="metadados-divergentes",
            diff_descricao=(
                f"status divergente: {t1.status!r} vs {t2.status!r}"
            ),
        )
    if t1.contexto_hash_sha256 != t2.contexto_hash_sha256:
        return ResultadoComparacao(
            iguais=False,
            motivo="metadados-divergentes",
            diff_descricao=(
                "contexto_hash_sha256 divergente: "
                f"{t1.contexto_hash_sha256!r} vs {t2.contexto_hash_sha256!r}"
            ),
        )
    if set(t1.notas_injetadas) != set(t2.notas_injetadas):
        diff_apenas_t1 = set(t1.notas_injetadas) - set(t2.notas_injetadas)
        diff_apenas_t2 = set(t2.notas_injetadas) - set(t1.notas_injetadas)
        return ResultadoComparacao(
            iguais=False,
            motivo="metadados-divergentes",
            diff_descricao=(
                "notas_injetadas divergem; "
                f"apenas em t1={sorted(diff_apenas_t1)!r}, "
                f"apenas em t2={sorted(diff_apenas_t2)!r}"
            ),
        )

    # Conteúdo — normalizado por R9.3 antes da comparação.
    conteudo_t1 = normalizar_texto(t1.conteudo_markdown or "")
    conteudo_t2 = normalizar_texto(t2.conteudo_markdown or "")
    if conteudo_t1 != conteudo_t2:
        return ResultadoComparacao(
            iguais=False,
            motivo="diferentes",
            diff_descricao=(
                "conteudo_markdown divergente após normalização CRLF→LF "
                "e remoção de trailing whitespace"
            ),
        )

    return ResultadoComparacao(
        iguais=True, motivo="iguais", diff_descricao=None
    )


# ---------------------------------------------------------------------------
# R9.5 — Detecção de regressão entre Decisões similares
# ---------------------------------------------------------------------------


def _veto_para_chave(veto: Veto) -> tuple[str, str, str, str]:
    """Converte um :class:`Veto` numa tupla hashable ordenada.

    O quádruplo ``(tipo, autor, decisao, proposta_alvo)`` é o conjunto
    mínimo de campos que distingue dois vetos para fins de regressão
    (R9.5). Justificativa textual e categoria técnica são deliberadamente
    excluídos: dois vetos com o mesmo veredito mas justificativas
    levemente diferentes não constituem regressão de decisão.
    """
    return (veto.tipo, veto.autor, veto.decisao, veto.proposta_alvo)


def detectar_regressao(
    decisao_atual: DecisaoDoConselho,
    decisao_anterior: Optional[DecisaoDoConselho],
) -> ResultadoRegressao:
    """Compara duas Decisões similares e detecta regressão (R9.5).

    Quando ``decisao_anterior`` é ``None`` (primeiro Debate sobre um
    tema), retorna ``regressao_detectada=False`` sem diff — não há base
    de comparação. O orquestrador é responsável por garantir que
    ``decisao_atual`` e ``decisao_anterior`` correspondam a Debates
    comparáveis (mesmo input, mesmos modelos, mesmo
    ``contexto_hash_sha256``); aqui apenas comparamos os outputs.

    Campos comparados:

    - ``decisao_final.proposta_aceita`` (incluindo ``None`` ↔ ``None``);
    - multiset de vetos representado como ``set[tuple]`` via
      :func:`_veto_para_chave`.
    """
    if decisao_anterior is None:
        return ResultadoRegressao(regressao_detectada=False)

    proposta_atual = decisao_atual.decisao_final.proposta_aceita
    proposta_anterior = decisao_anterior.decisao_final.proposta_aceita
    diff_proposta: Optional[tuple[Optional[str], Optional[str]]] = None
    if proposta_atual != proposta_anterior:
        diff_proposta = (proposta_anterior, proposta_atual)

    chaves_atuais = {_veto_para_chave(v) for v in decisao_atual.vetos}
    chaves_anteriores = {_veto_para_chave(v) for v in decisao_anterior.vetos}
    diff_vetos: Optional[
        tuple[
            set[tuple[str, str, str, str]],
            set[tuple[str, str, str, str]],
        ]
    ] = None
    if chaves_atuais != chaves_anteriores:
        apenas_anterior = chaves_anteriores - chaves_atuais
        apenas_atual = chaves_atuais - chaves_anteriores
        diff_vetos = (apenas_anterior, apenas_atual)

    regressao = diff_proposta is not None or diff_vetos is not None
    return ResultadoRegressao(
        regressao_detectada=regressao,
        diff_proposta=diff_proposta,
        diff_vetos=diff_vetos,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

__all__ = [
    "MotivoComparacao",
    "ResultadoComparacao",
    "ResultadoRegressao",
    "derivar_reproduzivel",
    "normalizar_texto",
    "comparar_turnos_byte_a_byte",
    "detectar_regressao",
]
