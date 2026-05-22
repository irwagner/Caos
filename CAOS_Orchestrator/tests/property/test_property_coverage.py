"""Validação por introspecção da cobertura das 15 Properties (Tasks 18 + 9).

**Validates: Requirements — gate de qualidade da suíte PBT** (Task 18 do
``caos-conselho-infra/tasks.md`` e Task 9 do ``caos-walk-forward/tasks.md``).

Este teste NÃO é uma property-based test; é um teste de meta-cobertura
que verifica, lendo o sistema de arquivos, que:

1. Todos os arquivos previstos para as 15 Properties existem em
   ``tests/property/``. As 12 Properties do Spec 1 (caos-conselho-infra)
   são distribuídas em 10 arquivos (Property 4 e 5 compartilham
   ``test_vetos.py``; Property 6 e 7 compartilham
   ``test_quorum_e_orcamento.py``). As 3 Properties do Spec 2
   (caos-walk-forward) ocupam 1 arquivo cada — Property 13/14/15 em
   ``test_walk_forward_no_lookahead.py`` /
   ``test_walk_forward_determinismo.py`` /
   ``test_walk_forward_janelas.py``.
2. Cada arquivo carrega a marca ``**Validates: Requirements`` no
   módulo (docstring ou comentário) — convenção que conecta o teste
   aos requirements cobertos (rastreabilidade).
3. Cada arquivo define ao menos uma função de teste cujo corpo é
   executado pelo Hypothesis (heurística: presença de ``@given(`` na
   forma textual no arquivo) e ao menos uma função ``def test_...``.
4. Os ``design.md`` das duas specs declaram as Properties esperadas:

   - ``caos-conselho-infra/design.md`` declara Property 1..12;
   - ``caos-walk-forward/design.md`` declara Property 13..15.

   Se uma Property nova for adicionada a qualquer spec, este teste
   falha até que :data:`PROPERTIES_ESPERADAS` seja atualizado.

Falhas neste teste indicam um dos cenários:

- Arquivo de property test foi renomeado/movido sem atualizar a Task.
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
# Catálogo: arquivo -> Properties cobertas (numeração dos design.md)
# ---------------------------------------------------------------------------

PROPERTIES_ESPERADAS: dict[str, tuple[int, ...]] = {
    # --- Spec 1: caos-conselho-infra (Properties 1..12) ---
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
    # --- Spec 2: caos-walk-forward (Properties 13..15) ---
    "test_walk_forward_no_lookahead.py": (13,),
    "test_walk_forward_determinismo.py": (14,),
    "test_walk_forward_janelas.py": (15,),
}

NUMEROS_PROPERTY_ESPERADOS = tuple(range(1, 16))  # 1..15

# Cada spec declara um subconjunto contíguo das Properties do catálogo.
DESIGN_MD_PROPERTIES_POR_SPEC: dict[str, tuple[int, ...]] = {
    "caos-conselho-infra": tuple(range(1, 13)),  # 1..12
    "caos-walk-forward": (13, 14, 15),
}

DIR_KIRO_SPECS = Path(__file__).resolve().parents[3] / ".kiro" / "specs"


# ---------------------------------------------------------------------------
# 1. Todos os arquivos esperados existem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_arquivo", list(PROPERTIES_ESPERADAS))
def test_arquivo_de_property_existe(nome_arquivo: str) -> None:
    """Cada arquivo previsto no catálogo deve existir em ``tests/property/``."""
    arquivo = DIR_PROPERTY / nome_arquivo
    assert arquivo.is_file(), (
        f"arquivo de property test ausente: {nome_arquivo}. "
        "Se foi renomeado, atualizar PROPERTIES_ESPERADAS."
    )


# ---------------------------------------------------------------------------
# 2. Cada arquivo tem a marca **Validates: Requirements
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_arquivo", list(PROPERTIES_ESPERADAS))
def test_arquivo_carrega_marca_validates_requirements(nome_arquivo: str) -> None:
    """Cada arquivo deve carregar a marca ``**Validates: Requirements``.

    A marca conecta o teste aos requirements cobertos (rastreabilidade
    dos artefatos de auditoria).
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
# 4. design.md de cada spec declara o subconjunto correto de Properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec_nome, esperado",
    list(DESIGN_MD_PROPERTIES_POR_SPEC.items()),
)
def test_design_md_declara_properties_corretas(
    spec_nome: str, esperado: tuple[int, ...]
) -> None:
    """O ``design.md`` de cada spec declara as Properties que prometeu.

    Se a spec adicionar uma Property nova, este teste falha até que
    :data:`PROPERTIES_ESPERADAS` e
    :data:`DESIGN_MD_PROPERTIES_POR_SPEC` sejam atualizados e o teste
    correspondente seja adicionado.
    """
    design_md = DIR_KIRO_SPECS / spec_nome / "design.md"
    if not design_md.is_file():
        pytest.skip(
            f"design.md não encontrado em {design_md}; "
            "pulando verificação cruzada com a spec."
        )

    texto = design_md.read_text(encoding="utf-8")
    encontrados = sorted(
        {int(m.group(1)) for m in re.finditer(r"###\s+Property\s+(\d+):", texto)}
    )
    assert encontrados == list(esperado), (
        f"{spec_nome}/design.md declara Properties {encontrados}, "
        f"esperado {list(esperado)}. "
        "Atualizar PROPERTIES_ESPERADAS e adicionar/remover testes."
    )


def test_catalogo_cobre_todas_as_properties_sem_lacunas() -> None:
    """O catálogo local deve cobrir Property 1..15 sem lacunas/duplicatas."""
    cobertas: list[int] = []
    for nums in PROPERTIES_ESPERADAS.values():
        cobertas.extend(nums)

    assert sorted(cobertas) == list(NUMEROS_PROPERTY_ESPERADOS), (
        f"catálogo PROPERTIES_ESPERADAS cobre {sorted(cobertas)}, "
        f"esperado {list(NUMEROS_PROPERTY_ESPERADOS)} sem repetições."
    )
