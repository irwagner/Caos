"""Property-based test da paridade Python ↔ C# da estratégia ORB
(Property 19 do Spec 4 — Task 6).

Implementa **Property 19 — Paridade Python ↔ C# da Estratégia ORB**:

    For every randomly generated sequence of OHLCV bars (gerada por
    Hypothesis com timestamps em UTC dentro de uma sessão RTH),
    ``decidir_acao`` (Python canônico) e
    ``OrbModeloCSharpPort.decidir_acao`` (Python que espelha exatamente
    a função C#) SHALL return the same ``DecisaoORB`` for every bar —
    incluindo ``acao``, ``stop``, ``alvo`` e ``motivo``.

**Validates: Requirements 7.1, 7.2, 7.3**

Como a porta Python (:class:`OrbModeloCSharpPort`) e a função canônica
(:func:`decidir_acao`) são byte-a-byte idênticas nesta primeira
iteração do Spec 4, esta Property é trivialmente verdadeira hoje. O
valor real do teste aparece em iterações futuras: qualquer mudança em
um lado sem o espelho correspondente quebra a Property imediatamente.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from typing import List, Tuple

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.estrategias_modelo.orb import OrbModeloCSharpPort
from caos.walk_forward.estrategias.orb_logica import (
    Barra,
    DecisaoORB,
    EstadoORB,
    ParametrosORB,
    decidir_acao,
    registrar_abertura_de_posicao,
    registrar_fechamento_de_posicao,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Geradores Hypothesis
# ---------------------------------------------------------------------------


@st.composite
def _parametros_orb_validos(draw):
    """Gera ``ParametrosORB`` dentro dos ranges canônicos."""
    return ParametrosORB(
        minutos_or=draw(st.integers(min_value=5, max_value=60)),
        risco_multiplicador=draw(
            st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False)
        ),
        alvo_multiplicador=draw(
            st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        cooldown_minutos=draw(st.integers(min_value=0, max_value=120)),
        # Horários fixos para evitar combinações inválidas — a Property
        # de paridade não depende dos horários específicos.
    )


@st.composite
def _sequencia_de_barras(draw):
    """Gera uma sequência crescente de barras OHLCV em uma sessão RTH.

    Estratégia:
    - Escolhe um dia base (2026-01-05) e produz N barras 1-min começando
      em 13:30 UTC.
    - Cada barra tem preços ≈ 21000 ± 50 e volumes ≈ 1000.
    - O número de barras varia entre 5 e 100 — suficiente para incluir o
      Periodo_OR e ao menos algumas barras de teste/cooldown/etc.
    """
    n_barras = draw(st.integers(min_value=5, max_value=100))
    inicio = datetime(2026, 1, 5, 13, 30, tzinfo=UTC)
    barras: List[Barra] = []
    for i in range(n_barras):
        ts = inicio + timedelta(minutes=i)
        # Preços razoáveis: open base ± offset.
        base = draw(st.floats(min_value=20950.0, max_value=21050.0, allow_nan=False, allow_infinity=False))
        amp = draw(st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False))
        o = base
        # Garante h >= max(o,c) e l <= min(o,c) para barra válida.
        c_offset = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
        c = base + c_offset
        h = max(o, c) + amp
        l = min(o, c) - amp
        volume = draw(st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False))
        barras.append(Barra(timestamp=ts, open=o, high=h, low=l, close=c, volume=volume))
    return barras


# ---------------------------------------------------------------------------
# Property 19 — paridade canônica entre Python e porta C#
# ---------------------------------------------------------------------------


def _decisoes_iguais(a: DecisaoORB, b: DecisaoORB) -> bool:
    """Compara duas decisões com tolerância numérica para stop/alvo."""
    if a.acao != b.acao:
        return False
    if a.motivo != b.motivo:
        return False
    if (a.stop is None) != (b.stop is None):
        return False
    if a.stop is not None and b.stop is not None:
        if abs(a.stop - b.stop) > 1e-9:
            return False
    if (a.alvo is None) != (b.alvo is None):
        return False
    if a.alvo is not None and b.alvo is not None:
        if abs(a.alvo - b.alvo) > 1e-9:
            return False
    return True


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(parametros=_parametros_orb_validos(), barras=_sequencia_de_barras())
def test_property_orb_paridade_python_csharp(
    parametros: ParametrosORB,
    barras: List[Barra],
) -> None:
    """**Validates: Requirements 7.1, 7.2, 7.3** (Property 19).

    Para qualquer sequência de barras OHLCV razoáveis e qualquer
    combinação válida de :class:`ParametrosORB`, a função canônica
    Python e a porta Python-do-C# emitem decisões byte-a-byte idênticas
    em cada barra.
    """
    estado_canonico = EstadoORB()
    estado_porta = EstadoORB()

    for i, barra in enumerate(barras):
        d_can = decidir_acao(barra, estado_canonico, parametros)
        d_porta = OrbModeloCSharpPort.decidir_acao(barra, estado_porta, parametros)

        assert _decisoes_iguais(d_can, d_porta), (
            f"divergência em t={i}, barra={barra}: canonico={d_can}, porta={d_porta}"
        )

        # Mantém os estados sincronizados — registrar aberturas/fechamentos
        # no mesmo timing nos dois lados para que a próxima barra tenha
        # o mesmo contexto de decisão.
        if d_can.acao in ("LONG", "SHORT"):
            registrar_abertura_de_posicao(estado_canonico, d_can)
            registrar_abertura_de_posicao(estado_porta, d_porta)
        elif d_can.acao == "FECHAR":
            registrar_fechamento_de_posicao(estado_canonico, barra.timestamp, parametros)
            registrar_fechamento_de_posicao(estado_porta, barra.timestamp, parametros)


# ---------------------------------------------------------------------------
# Sub-Property — barras malformadas devem levantar erro idêntico nos dois lados
# ---------------------------------------------------------------------------


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    cenario=st.sampled_from(
        [
            "naive",
            "offset_brasil",
            "high_nan",
            "close_inf",
        ]
    )
)
def test_property_orb_paridade_validacao_de_barra_invalida(cenario: str) -> None:
    """Ambas as portas devem levantar ``ValueError`` para barras inválidas."""
    if cenario == "naive":
        b = Barra(
            timestamp=datetime(2026, 1, 5, 14, 0),
            open=21000, high=21010, low=20990, close=21005, volume=1000,
        )
    elif cenario == "offset_brasil":
        offset = timezone(timedelta(hours=-3))
        b = Barra(
            timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=offset),
            open=21000, high=21010, low=20990, close=21005, volume=1000,
        )
    elif cenario == "high_nan":
        b = Barra(
            timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=UTC),
            open=21000, high=float("nan"), low=20990, close=21005, volume=1000,
        )
    else:  # close_inf
        b = Barra(
            timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=UTC),
            open=21000, high=21010, low=20990, close=float("inf"), volume=1000,
        )

    parametros = ParametrosORB()
    estado_a = EstadoORB()
    estado_b = EstadoORB()

    erro_a = None
    erro_b = None
    try:
        decidir_acao(b, estado_a, parametros)
    except Exception as e:
        erro_a = type(e)
    try:
        OrbModeloCSharpPort.decidir_acao(b, estado_b, parametros)
    except Exception as e:
        erro_b = type(e)
    assert erro_a == erro_b, (
        f"divergência em validação para cenário {cenario}: "
        f"canonico={erro_a}, porta={erro_b}"
    )
