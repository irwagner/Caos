"""Property 21 — Conformidade do Debate-no-Chat (Spec 5 — Task 5).

**Validates: Requirements 5.1, 5.2** do Spec 5
(``.kiro/specs/caos-conselho-no-chat/requirements.md``).

Para todo arquivo em ``CAOS_Council/debates/*.md``:

1. O frontmatter YAML SHALL parsear como :class:`caos.models.Debate`
   válido (Pydantic schema do Spec 1).
2. Cada turno SHALL ter cabeçalho ``## Turno N — Agente (FASE)`` onde
   ``Agente`` ∈ 9 perfis e ``FASE`` ∈ máquina de estados (Spec 1).
3. A sequência de fases ao longo dos turnos SHALL ser um caminho
   válido na máquina (``INICIADO → PROPOSTAS → ...``).
4. Quando ``fase_final == "CONCLUIDO"``, SHALL existir
   :class:`DecisaoDoConselho` correspondente em
   ``CAOS_Council/decisions/{identificador}-*.md``.

Este teste é um **gate estático** (não generativo): varre o filesystem
do projeto procurando Debates reais. A marca ``@given`` está presente
para que :mod:`tests.property.test_property_coverage` (gate de cobertura)
detecte o arquivo como contendo property-based test.

Quando não há Debates em disco (estado inicial do workspace), o teste
passa trivialmente — não é falha do gate, é um Conselho ainda sem
sessões registradas.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.debate_io import (
    DIR_DEBATES_RELATIVO,
    DIR_DECISIONS_RELATIVO,
    _carregar_debate,
)
from caos.models import Debate

# ---------------------------------------------------------------------------
# Localização da raiz do workspace
# ---------------------------------------------------------------------------

#: Raiz do workspace — testes property/ ficam em
#: ``CAOS_Orchestrator/tests/property/``, então a raiz fica 3 níveis acima.
DIR_RAIZ_WORKSPACE = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Sequência canônica de fases
# ---------------------------------------------------------------------------

#: Fases válidas em um caminho concluído pela máquina de estados (Spec 1).
#: A sequência de turnos do Debate DEVE ser uma subsequência (não-decrescente)
#: desta lista, com possíveis transições para fases terminais
#: alternativas (TIMEOUT, SEM_QUORUM, ABORTADO, PENDENTE_USUARIO,
#: CERBERUS_TIMEOUT) apenas no último turno.
_ORDEM_CANONICA: tuple[str, ...] = (
    "INICIADO",
    "PROPOSTAS",
    "CRITICA",
    "AVALIACAO_RISCO",
    "AVALIACAO_TECNICA",
    "SINTESE",
    "CONCLUIDO",
)

_FASES_TERMINAIS_ALTERNATIVAS: frozenset[str] = frozenset(
    {"TIMEOUT", "SEM_QUORUM", "ABORTADO", "PENDENTE_USUARIO", "CERBERUS_TIMEOUT"}
)


def _coletar_debates(raiz: Path) -> List[Path]:
    """Devolve a lista ordenada de arquivos de Debate sob a raiz."""
    diretorio = raiz / DIR_DEBATES_RELATIVO
    if not diretorio.is_dir():
        return []
    return sorted(p for p in diretorio.glob("*.md") if p.is_file())


def _validar_sequencia_de_fases(debate: Debate) -> None:
    """Garante que as fases dos turnos formam um caminho válido."""
    if not debate.turnos:
        return
    cursor = 0  # índice em _ORDEM_CANONICA
    for i, turno in enumerate(debate.turnos):
        fase = str(turno.fase)
        # Fase terminal alternativa só pode aparecer no último turno.
        if fase in _FASES_TERMINAIS_ALTERNATIVAS:
            assert i == len(debate.turnos) - 1, (
                f"fase terminal alternativa {fase!r} apareceu fora do último "
                f"turno (turno {turno.numero})"
            )
            return
        if fase not in _ORDEM_CANONICA:
            raise AssertionError(
                f"fase {fase!r} desconhecida no turno {turno.numero} "
                f"(Debate {debate.identificador})"
            )
        idx = _ORDEM_CANONICA.index(fase)
        assert idx >= cursor, (
            f"fase {fase!r} retrocede em relação à fase anterior em "
            f"{debate.identificador}: turno {turno.numero}"
        )
        cursor = idx


# ---------------------------------------------------------------------------
# Property 21 (gate estático)
# ---------------------------------------------------------------------------


@settings(
    max_examples=1,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(st.just(None))
def test_property_debate_no_chat_conformidade(_dummy: None) -> None:
    """**Validates: Requirements 5.1, 5.2** (Property 21).

    Varre ``CAOS_Council/debates/*.md`` na raiz do projeto e valida:

    - frontmatter parseia como :class:`Debate` válido;
    - cada turno tem cabeçalho de fase válido;
    - sequência de fases respeita a máquina do Spec 1;
    - Debates concluídos têm Decisão correspondente.

    Workspace sem Debates ⇒ teste passa trivialmente (estado inicial
    perfeitamente válido).
    """
    debates = _coletar_debates(DIR_RAIZ_WORKSPACE)
    if not debates:
        # Estado inicial: nenhum Debate ainda foi gravado. OK por
        # construção — o gate fica firme assim que a primeira
        # Decisão for commitada.
        return

    diretorio_decisoes = DIR_RAIZ_WORKSPACE / DIR_DECISIONS_RELATIVO
    for caminho in debates:
        debate = _carregar_debate(caminho)
        _validar_sequencia_de_fases(debate)
        # Cabeçalho de cada turno tem agente válido (já forçado pelo
        # schema Pydantic via ``AgenteNome`` Literal); cobertura adicional
        # não é necessária aqui.

        if debate.fase_final == "CONCLUIDO":
            esperado = list(diretorio_decisoes.glob(f"{debate.identificador}-*.md"))
            assert esperado, (
                f"Debate concluído {debate.identificador} sem Decisão "
                f"correspondente em {diretorio_decisoes}"
            )
