"""Property-based test do Bias_Filter (Property 8 do design).

Implementa **Property 8 — Antibias Filter Soundness** do ``design.md``:

    For every Nota_Zettel of paper origin with ``status != aprovada``, the
    count of inbound ``[[wiki-style]]`` links SHALL be zero.

**Validates: Requirements 12.1, 12.8**

A estratégia gera entradas arbitrárias de paper (com qualquer combinação de
``None``/inválido nos 5 campos antibias) e cria, no filesystem, ``n_outras_notas``
notas que tentam apontar wiki-links para o paper-alvo. O sistema responsável
pela escrita (``Explorador``) é simulado aqui pelo helper
:func:`_explorador_escrever_link_se_autorizado`, que **antes** de escrever o
link consulta :func:`caos.bias_filter.validar_link_de_entrada`. Após processar
todas as candidatas, contamos os backlinks reais escritos no filesystem via
:func:`caos.context_loader.carregar_contexto` e validamos:

* se o status final do paper é ``aprovada`` → backlinks == ``n_outras_notas``;
* caso contrário → backlinks == 0 (enunciado direto da Property 8).

Mantemos ``max_examples=50`` e ``deadline=None`` para que a suíte permaneça
executável em CI Windows sem pesar no orçamento de tempo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.bias_filter import (
    armazenar_em_papers,
    avaliar_paper,
    construir_nota_paper,
    validar_link_de_entrada,
)
from caos.context_loader import carregar_contexto

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frontmatter_outra_nota(nome: str, alvo_titulo: str) -> str:
    """Frontmatter mínimo válido para uma Nota_Zettel auxiliar.

    A Nota fica em ``Modulo_Institucional/`` e o corpo contém um wiki-link
    para o paper-alvo (``[[<titulo do paper>]]``).
    """
    return (
        "---\n"
        f"titulo: {nome}\n"
        "area: Modulo_Institucional\n"
        "tags:\n"
        "  - antibias-property\n"
        "data_criacao: 2026-05-14T10:00:00Z\n"
        "agente_autor: Athena\n"
        "---\n"
        f"# {nome}\n\n"
        f"Aponta para [[{alvo_titulo}]].\n"
    )


def _explorador_escrever_link_se_autorizado(
    *,
    raiz: Path,
    nome_outra: str,
    paper_titulo: str,
    paper_status: str,
) -> bool:
    """Simula a escrita do Explorador respeitando o guard R12.8.

    Retorna ``True`` quando o arquivo foi efetivamente escrito (ou seja,
    quando o status do paper é ``aprovada``), ``False`` quando o guard
    bloqueou a criação do link.
    """
    # Reconstrói uma Nota_Zettel mínima do paper apenas para obter o status
    # — usamos diretamente o status pois o guard só consulta esse campo.
    class _PaperStub:  # pylint: disable=too-few-public-methods
        titulo = paper_titulo
        status = paper_status

    resultado = validar_link_de_entrada(_PaperStub())  # type: ignore[arg-type]
    if not resultado.autorizado:
        return False

    pasta = raiz / "Modulo_Institucional"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{nome_outra}.md"
    arquivo.write_text(
        _frontmatter_outra_nota(nome_outra, paper_titulo),
        encoding="utf-8",
    )
    return True


def _contar_backlinks_para_paper(raiz: Path, paper_titulo: str) -> int:
    """Conta backlinks reais do filesystem para o paper-alvo.

    Reutiliza :func:`carregar_contexto` para obter a contagem de backlinks
    sobre o ``stem`` do arquivo do paper — que é o slug derivado de
    :func:`caos.bias_filter._slug_simples`.
    """
    res = carregar_contexto(
        f"[[{paper_titulo}]]",
        raiz_zettelkasten=raiz,
    )
    # O contexto_loader indexa por stem do arquivo. O paper foi gravado em
    # Papers/<slug>.md, então recuperamos o stem via res.contagem_backlinks.
    # Caso não seja encontrado (paper nunca chegou ao FS), trata como 0.
    if not res.contagem_backlinks:
        return 0
    # Esperamos exatamente 1 chave (o paper-alvo) ou nenhuma.
    return sum(res.contagem_backlinks.values())


# ---------------------------------------------------------------------------
# Property 8 — Antibias Filter Soundness
# ---------------------------------------------------------------------------


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    sharpe=st.one_of(
        st.floats(
            min_value=-2.0, max_value=5.0,
            allow_nan=False, allow_infinity=False,
        ),
        st.none(),
    ),
    sample=st.one_of(
        st.integers(min_value=0, max_value=1000),
        st.none(),
    ),
    oos=st.one_of(
        st.integers(min_value=0, max_value=300),
        st.none(),
    ),
    survivorship=st.one_of(st.booleans(), st.none()),
    n_outras_notas=st.integers(min_value=0, max_value=10),
)
def test_property_filtros_antibias(
    sharpe: Optional[float],
    sample: Optional[int],
    oos: Optional[int],
    survivorship: Optional[bool],
    n_outras_notas: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 12.1, 12.8** (Property 8).

    Para todo paper gerado com qualquer combinação de campos válidos /
    ``None`` / inválidos:

    1. Avalia o status via :func:`avaliar_paper` (R12.1).
    2. Cria ``n_outras_notas`` notas que tentam apontar wiki-link para o
       paper, cada uma passando por :func:`validar_link_de_entrada` antes
       da escrita (Explorador-simulado).
    3. Conta os backlinks reais escritos no FS.
    4. Garante:

       * ``status == 'aprovada'``  → backlinks ``== n_outras_notas``;
       * ``status != 'aprovada'``  → backlinks ``== 0`` (R12.8 / Property 8).
    """
    raiz = tmp_path_factory.mktemp("zettel_antibias")

    paper_titulo = "Property Antibias Paper"
    instrumento_testado: Any = "MNQ"

    # 1) Avaliação automática do status.
    status_paper = avaliar_paper(
        sharpe_replicado=sharpe,
        sample_size=sample,
        out_of_sample_periodo=oos,
        instrumento_testado=instrumento_testado,
        survivorship_bias_tratado=survivorship,
    )

    # 2) Constrói + grava a Nota_Zettel do paper (R12.5: grava sempre).
    nota_paper = construir_nota_paper(
        titulo=paper_titulo,
        tags=["antibias-property"],
        data_criacao="2026-05-14T15:00:00Z",
        agente_autor="Explorador",
        sharpe_replicado=sharpe,
        sample_size=sample,
        out_of_sample_periodo=oos,
        instrumento_testado=instrumento_testado,
        survivorship_bias_tratado=survivorship,
    )
    assert nota_paper.status == status_paper, (
        "construir_nota_paper deve refletir o status de avaliar_paper"
    )
    armazenar_em_papers(nota_paper, raiz)

    # 3) Para cada uma das n_outras_notas, tenta criar link de entrada.
    autorizados = 0
    for i in range(n_outras_notas):
        criou = _explorador_escrever_link_se_autorizado(
            raiz=raiz,
            nome_outra=f"OutraNota_{i:03d}",
            paper_titulo=paper_titulo,
            paper_status=status_paper,
        )
        if criou:
            autorizados += 1

    # 4) Conta backlinks reais escritos no FS.
    total_backlinks = _contar_backlinks_para_paper(raiz, paper_titulo)

    if status_paper == "aprovada":
        assert total_backlinks == n_outras_notas, (
            f"paper aprovada deveria ter {n_outras_notas} backlinks; "
            f"obtido {total_backlinks} (autorizados={autorizados})"
        )
        assert autorizados == n_outras_notas, (
            "todos os links deveriam ter sido autorizados quando aprovada"
        )
    else:
        # **Enunciado direto da Property 8 / R12.8.**
        assert total_backlinks == 0, (
            f"paper com status={status_paper!r} deveria ter 0 backlinks; "
            f"obtido {total_backlinks}"
        )
        assert autorizados == 0, (
            "guard R12.8 falhou: nenhum link deveria ter sido autorizado "
            f"para status={status_paper!r}"
        )
