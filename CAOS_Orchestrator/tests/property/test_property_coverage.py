"""Validação por introspecção da cobertura das 12 Properties (Task 18).

**Validates: Requirements 18.x — gate de qualidade da suíte PBT** (Task 18
do tasks.md).

Este teste NÃO é uma property-based test; é um teste de meta-cobertura
que verifica, lendo o sistema de arquivos, que:

1. Todos os 10 arquivos previstos para as 12 Properties (Property 4 e 5
   compartilham ``test_vetos.py``; Property 6 e 7 compartilham
   ``test_quorum_e_orcamento.py``) existem em ``tests/property/``.
2. Cada arquivo carrega a marca ``**Validates: Requirements`` no
   módulo (docstring ou comentário) — convenção que conecta o teste
   aos requirements cobertos (R8.4 / disciplina de rastreabilidade).
3. Cada arquivo define ao menos uma função de teste cujo corpo é
   executado pelo Hypothesis (heurística: presença de ``@given`` na
   forma textual ``@given(`` no arquivo) e ao menos uma função
   ``def test_...``.
4. O ``design.md`` da spec ``caos-conselho-infra`` declara
   exatamente 12 Properties, casando com o catálogo abaixo.

Falhas neste teste indicam um dos cenários:

- Arquivo de property test foi renomeado/movido sem atualizar a Task 18.
- Marca ``**Validates: Requirements`` foi perdida em refator.
- Property nova foi adicionada ao ``design.md`` sem teste correspondente
  (ou vice-versa).

Em qualquer cenário, abrir um Debate com Hermes para reavaliar o gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DIR_PROPERTY = Path(__file__).parent

# ---------------------------------------------------------------------------
# Catálogo: arquivo -> Properties cobertas (numeração do design.md §10)
# ---------------------------------------------------------------------------

PROPERTIES_ESPERADAS: dict[str, tuple[int, ...]] = {
    "test_determinismo.py": (1,),
    "test_auditabilidade.py": (2,),
    "test_isolamento_contexto.py": (3,),
    "test_vetos.py": (4, 5),
    "test_quorum_e_orcamento.py": (6, 7),
    "test_filtros_antibias.py": (8,),
    "test_idempotencia.py": (9,),
    "test_data_manifest_integrity.py": (10,),
    "test_cache_determinism.py": (11,),
    "test_token_budget.py": (12,),
}

NUMEROS_PROPERTY_ESPERADOS = tuple(range(1, 13))  # 1..12

DESIGN_MD = (
    Path(__file__).resolve().parents[3]
    / ".kiro"
    / "specs"
    / "caos-conselho-infra"
    / "design.md"
)


# ---------------------------------------------------------------------------
# 1. Todos os arquivos esperados existem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_arquivo", list(PROPERTIES_ESPERADAS))
def test_arquivo_de_property_existe(nome_arquivo: str) -> None:
    """Cada arquivo previsto na Task 18 deve existir em ``tests/property/``."""
    arquivo = DIR_PROPERTY / nome_arquivo
    assert arquivo.is_file(), (
        f"arquivo de property test ausente: {nome_arquivo}. "
        "Se foi renomeado, atualizar Task 18 e este catálogo."
    )


# ---------------------------------------------------------------------------
# 2. Cada arquivo tem a marca **Validates: Requirements
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_arquivo", list(PROPERTIES_ESPERADAS))
def test_arquivo_carrega_marca_validates_requirements(nome_arquivo: str) -> None:
    """Cada arquivo deve carregar a marca ``**Validates: Requirements``.

    A marca conecta o teste aos requirements cobertos (rastreabilidade
    dos artefatos de auditoria — R8.4 e disciplina geral de rastreio).
    """
    texto = (DIR_PROPERTY / nome_arquivo).read_text(encoding="utf-8")
    assert "**Validates: Requirements" in texto, (
        f"arquivo {nome_arquivo} não carrega a marca "
        "'**Validates: Requirements ...**' no docstring/comentário do módulo."
    )


# ---------------------------------------------------------------------------
# 3. Cada arquivo declara ao menos uma função test_ + um @given
# ---------------------------------------------------------------------------


_REGEX_DEF_TEST = re.compile(r"^\s*def\s+test_\w+", re.MULTILINE)


@pytest.mark.parametrize("nome_arquivo", list(PROPERTIES_ESPERADAS))
def test_arquivo_tem_funcao_de_teste_e_given(nome_arquivo: str) -> None:
    """Cada arquivo deve ter ao menos um ``def test_...`` e um ``@given(``.

    A presença de ``@given(`` é a marca textual de teste property-based
    em Hypothesis. Não casamos com ``@settings`` porque alguns testes
    declaram ``@given`` sem ``@settings`` explícito (herdando o profile).
    """
    texto = (DIR_PROPERTY / nome_arquivo).read_text(encoding="utf-8")

    casamentos_def_test = _REGEX_DEF_TEST.findall(texto)
    assert casamentos_def_test, (
        f"arquivo {nome_arquivo} não declara nenhuma função 'def test_...'."
    )

    assert "@given(" in texto, (
        f"arquivo {nome_arquivo} não usa '@given(' — "
        "esperado pelo menos um teste property-based via Hypothesis."
    )


# ---------------------------------------------------------------------------
# 4. design.md declara exatamente 12 Properties numeradas
# ---------------------------------------------------------------------------


def test_design_md_declara_12_properties() -> None:
    """O ``design.md`` da spec deve declarar Property 1..12 (sem lacunas).

    Se a spec adicionar uma Property nova, este teste falha até que o
    catálogo ``PROPERTIES_ESPERADAS`` seja atualizado e o teste
    correspondente seja adicionado.
    """
    if not DESIGN_MD.is_file():
        pytest.skip(
            f"design.md não encontrado em {DESIGN_MD}; "
            "pulando verificação cruzada com a spec."
        )

    texto = DESIGN_MD.read_text(encoding="utf-8")
    encontrados = sorted(
        {
            int(m.group(1))
            for m in re.finditer(r"###\s+Property\s+(\d+):", texto)
        }
    )
    assert encontrados == list(NUMEROS_PROPERTY_ESPERADOS), (
        f"design.md declara Properties {encontrados}, "
        f"esperado {list(NUMEROS_PROPERTY_ESPERADOS)}. "
        "Atualizar PROPERTIES_ESPERADAS e adicionar/remover testes."
    )


def test_catalogo_cobre_todas_as_12_properties() -> None:
    """O catálogo local deve cobrir Property 1..12 sem lacunas/duplicatas."""
    cobertas: list[int] = []
    for nums in PROPERTIES_ESPERADAS.values():
        cobertas.extend(nums)

    assert sorted(cobertas) == list(NUMEROS_PROPERTY_ESPERADOS), (
        f"catálogo PROPERTIES_ESPERADAS cobre {sorted(cobertas)}, "
        f"esperado {list(NUMEROS_PROPERTY_ESPERADOS)} sem repetições."
    )
