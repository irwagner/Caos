"""Property-based test do :mod:`caos.determinism_auditor` (Property 1).

Implementa **Property 1 — Determinism** do ``design.md``:

    For every Debate executed twice with the same input, same context
    SHA-256 hash, and same seed set, all turns not flagged
    ``nao-deterministico`` SHALL be byte-identical after CRLF→LF
    normalization.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

Estratégia (alinhada à Task 11 do ``tasks.md``):

- A Task 16 (Agent_Invoker via Kiro API) ainda não está concluída — o
  mock determinístico de agente em ``conftest.py`` virá com aquela
  tarefa. Aqui, embutimos um **mock determinístico local de execução
  de Debate**: dada uma seed, geramos a mesma lista de turnos byte-a-byte
  em chamadas distintas. Esse mock é deliberadamente isolado em
  ``_executar_debate_mock`` para que a Task 16 possa substituí-lo sem
  alterar a propriedade.

- Geramos ``n_turnos`` (1–8) e uma fração de turnos marcados
  ``nao_deterministico`` (controlada por ``fracao_nao_deterministicos``).

- Rodamos o "Debate" 2x com a mesma ``seed`` → produzimos duas listas
  ``t1`` e ``t2`` de turnos.

- Validamos:

  1. Para cada par ``(t1[i], t2[i])`` com ``nao_deterministico == False``,
     :func:`comparar_turnos_byte_a_byte` retorna ``iguais=True`` (R9.3).
  2. Para cada par com ``nao_deterministico == True``,
     :func:`comparar_turnos_byte_a_byte` retorna
     ``motivo="pulado-nao-deterministico"`` (R9.2).
  3. ``derivar_reproduzivel(t1) == derivar_reproduzivel(t2)`` (R9.4).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.determinism_auditor import (
    comparar_turnos_byte_a_byte,
    derivar_reproduzivel,
)
from caos.models import Turno


# ---------------------------------------------------------------------------
# Mock determinístico local de execução de Debate
# ---------------------------------------------------------------------------


_AGENTES = [
    "Athena",
    "Odin",
    "Mister_M",
    "Manolo",
    "Rodrigo",
    "Cerberus",
    "Hermes",
    "Explorador",
    "Devils_Advocate",
]
_FASES = ["PROPOSTAS", "CRITICA", "AVALIACAO_RISCO", "AVALIACAO_TECNICA"]
_HASH_FIXO = "c" * 64


def _executar_debate_mock(
    *,
    seed: int,
    n_turnos: int,
    fracao_nao_deterministicos: float,
) -> list[Turno]:
    """Simula uma execução determinística de Debate.

    Dado o trio ``(seed, n_turnos, fracao_nao_deterministicos)``,
    retorna sempre a mesma lista de :class:`Turno`. Isso é exatamente o
    que esperaríamos de um modelo LLM com seed fixa: repetir a invocação
    com os mesmos parâmetros produz a mesma sequência de respostas.

    Os turnos marcados ``nao_deterministico=True`` recebem
    ``conteudo_markdown`` deterministicamente também — a propriedade
    importante é que o auditor PULE esses turnos durante a comparação,
    independente do que esteja no conteúdo. Isso é reforçado em
    :func:`_executar_debate_mock_com_ruido_em_nd` abaixo.
    """
    rng = random.Random(seed)
    base_timestamp = datetime(2026, 5, 14, 14, 0, 0, tzinfo=timezone.utc)
    turnos: list[Turno] = []
    for i in range(n_turnos):
        # Decide determinísticamente, a partir do RNG semeado, se o turno
        # i é marcado como não-determinístico.
        marcado_nd = rng.random() < fracao_nao_deterministicos
        agente = _AGENTES[i % len(_AGENTES)]
        # Modelo coerente com o agente (usamos sempre o primeiro modelo
        # permitido). O modelo em si não é validado pela propriedade —
        # apenas precisa ser uma string não-vazia.
        modelo = "claude-opus-4.7"
        fase = _FASES[i % len(_FASES)]
        conteudo = (
            f"Turno {i + 1} — agente {agente}\n"
            f"  conteúdo determinístico semeado por {seed}\n"
            f"  índice {i} de {n_turnos}\n"
        )
        turnos.append(
            Turno(
                numero=i + 1,
                agente=agente,  # type: ignore[arg-type]
                modelo=modelo,
                timestamp=base_timestamp + timedelta(seconds=i),
                fase=fase,  # type: ignore[arg-type]
                nao_deterministico=marcado_nd,
                notas_injetadas=[f"Modulo_Risco/Nota_{i}.md"],
                contexto_hash_sha256=_HASH_FIXO,
                status="ok",
                conteudo_markdown=conteudo,
            )
        )
    return turnos


def _executar_debate_mock_com_ruido_em_nd(
    *,
    seed: int,
    n_turnos: int,
    fracao_nao_deterministicos: float,
    ruido_seed: int,
) -> list[Turno]:
    """Variante: turnos marcados ``nao_deterministico=True`` recebem ruído.

    Mantém os turnos determinísticos byte-a-byte iguais ao
    :func:`_executar_debate_mock` original (a marcação é decidida pelo
    mesmo RNG semeado por ``seed``). Apenas para os turnos marcados
    ``nao_deterministico=True``, o ``conteudo_markdown`` é alterado por
    um RNG independente (``ruido_seed``).

    Esse cenário é a *raison d'être* de R9.2: simular dois replays do
    mesmo Debate com um modelo que não suporta seed — o conteúdo desses
    turnos pode divergir, mas os turnos determinísticos devem permanecer
    bit-exatos.
    """
    base = _executar_debate_mock(
        seed=seed,
        n_turnos=n_turnos,
        fracao_nao_deterministicos=fracao_nao_deterministicos,
    )
    rng_ruido = random.Random(ruido_seed)
    com_ruido: list[Turno] = []
    for turno in base:
        if turno.nao_deterministico:
            com_ruido.append(
                turno.model_copy(
                    update={
                        "conteudo_markdown": (
                            (turno.conteudo_markdown or "")
                            + f"\nruído #{rng_ruido.randint(0, 999_999)}\n"
                        )
                    }
                )
            )
        else:
            com_ruido.append(turno)
    return com_ruido


# ---------------------------------------------------------------------------
# Property 1 — Determinism
# ---------------------------------------------------------------------------


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_turnos=st.integers(min_value=1, max_value=8),
    fracao_nao_deterministicos=st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    seed=st.integers(min_value=0, max_value=10000),
)
def test_property_determinismo(
    n_turnos: int,
    fracao_nao_deterministicos: float,
    seed: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 9.1, 9.2, 9.3, 9.4** (Property 1).

    Para todo Debate executado 2x com mesma ``seed``:

    - Turnos não marcados ``nao_deterministico`` são byte-idênticos
      após normalização CRLF→LF (R9.3).
    - Turnos marcados são pulados pelo auditor (R9.2).
    - ``derivar_reproduzivel`` é estável entre as duas execuções (R9.4).
    """
    # Duas execuções com a mesma seed → mesma sequência de turnos.
    t1 = _executar_debate_mock(
        seed=seed,
        n_turnos=n_turnos,
        fracao_nao_deterministicos=fracao_nao_deterministicos,
    )
    t2 = _executar_debate_mock(
        seed=seed,
        n_turnos=n_turnos,
        fracao_nao_deterministicos=fracao_nao_deterministicos,
    )

    assert len(t1) == len(t2) == n_turnos, "duas execuções devem ter o mesmo n_turnos"

    for i, (turno1, turno2) in enumerate(zip(t1, t2)):
        # Decisão de marcação é função pura de (seed, i).
        assert turno1.nao_deterministico == turno2.nao_deterministico, (
            f"marcação nao_deterministico divergiu no turno {i + 1}"
        )
        res = comparar_turnos_byte_a_byte(turno1, turno2)
        if turno1.nao_deterministico:
            assert res.motivo == "pulado-nao-deterministico", (
                f"turno {i + 1} marcado nao_deterministico deveria ser "
                f"pulado, mas resultou em {res!r}"
            )
            assert res.iguais is False
        else:
            assert res.motivo == "iguais", (
                f"turno {i + 1} determinístico divergiu: {res!r}"
            )
            assert res.iguais is True
            assert res.diff_descricao is None

    # Reprodutibilidade derivada deve ser idêntica entre execuções.
    assert derivar_reproduzivel(t1) == derivar_reproduzivel(t2)


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_turnos=st.integers(min_value=1, max_value=8),
    seed=st.integers(min_value=0, max_value=10000),
    ruido_seed=st.integers(min_value=10001, max_value=20000),
)
def test_property_determinismo_pula_nd_mesmo_com_ruido(
    n_turnos: int,
    seed: int,
    ruido_seed: int,
) -> None:
    """**Validates: Requirements 9.2, 9.3** (variante de Property 1).

    Cenário de stress de R9.2: dois replays do mesmo Debate em que
    apenas os turnos marcados ``nao_deterministico`` divergem (ruído
    realista de modelos sem suporte a seed). O auditor deve:

    - Pular turnos marcados (motivo ``pulado-nao-deterministico``);
    - Confirmar igualdade byte-a-byte dos turnos determinísticos.

    Forçamos ``fracao_nao_deterministicos = 0.5`` para garantir uma
    mistura significativa em quase todas as amostras (com ``n_turnos``
    pequeno, ``random()`` pode produzir 0 marcados ou todos marcados;
    a propriedade trata ambos os limites corretamente).
    """
    fracao_nd = 0.5
    t1 = _executar_debate_mock(
        seed=seed,
        n_turnos=n_turnos,
        fracao_nao_deterministicos=fracao_nd,
    )
    t2 = _executar_debate_mock_com_ruido_em_nd(
        seed=seed,
        n_turnos=n_turnos,
        fracao_nao_deterministicos=fracao_nd,
        ruido_seed=ruido_seed,
    )
    assert len(t1) == len(t2)

    for i, (a, b) in enumerate(zip(t1, t2)):
        res = comparar_turnos_byte_a_byte(a, b)
        if a.nao_deterministico:
            assert res.motivo == "pulado-nao-deterministico", (
                f"turno {i + 1} marcado deveria ser pulado, recebido {res!r}"
            )
        else:
            assert res.motivo == "iguais", (
                f"turno {i + 1} determinístico divergiu sob ruído: {res!r}"
            )
            assert res.iguais is True
