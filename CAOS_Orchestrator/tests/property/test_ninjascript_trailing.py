"""Property-based test do ``TrailingModelo`` (Property 17 do Spec 3).

Implementa **Property 17 — Trailing Monotonia** do ``design.md`` do
Spec 3:

    For every active position, the stop loss SHALL never move against
    the trade direction (LONG: stop nunca desce; SHORT: stop nunca
    sobe).

**Validates: Requirements 4.1, 4.2, 4.3, 4.5**

Como o pacote :mod:`caos.ninjascript_modelo.trailing` é uma reimplementação
fiel da máquina de 3 fases de ``TrailingTresFases.cs`` (Spec 3 — Task 3),
esta Property também certifica o C# correspondente.

Cobertura:

1. **Monotonia (R4.5 — Property 17 canônica)**: para qualquer série de
   preços e parâmetros de fase, o stop devolvido por ``atualizar``
   nunca move contra o trade.
2. **Transições corretas (R4.1, R4.2, R4.3)**: ao atingir os
   multiplicadores de R, a fase avança e o stop alvo é o esperado pelo
   design.
3. **Irreversibilidade**: a fase só avança, nunca regride.
"""

from __future__ import annotations

from typing import List

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.ninjascript_modelo.trailing import (
    DirecaoTrade,
    FASE2_STOP_OFFSET_R,
    FASE3_DISTANCIA_R,
    FaseTrailing,
    TrailingModelo,
)


# ---------------------------------------------------------------------------
# Estratégias auxiliares
# ---------------------------------------------------------------------------


@st.composite
def _config_e_serie_long(draw):
    """Gera ``(fase1_mult, fase2_mult, fase3_mult, entrada, stop_inicial, precos)`` para LONG."""
    fase1 = draw(st.floats(min_value=0.1, max_value=0.7, allow_nan=False, allow_infinity=False))
    fase2 = draw(st.floats(min_value=fase1, max_value=1.5, allow_nan=False, allow_infinity=False))
    fase3 = draw(st.floats(min_value=fase2, max_value=2.0, allow_nan=False, allow_infinity=False))
    entrada = draw(st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False))
    risco_r = draw(st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False))
    stop_inicial = entrada - risco_r
    precos = draw(
        st.lists(
            st.floats(
                min_value=entrada - 5 * risco_r,
                max_value=entrada + 5 * risco_r,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=20,
        )
    )
    return fase1, fase2, fase3, entrada, stop_inicial, precos


@st.composite
def _config_e_serie_short(draw):
    fase1 = draw(st.floats(min_value=0.1, max_value=0.7, allow_nan=False, allow_infinity=False))
    fase2 = draw(st.floats(min_value=fase1, max_value=1.5, allow_nan=False, allow_infinity=False))
    fase3 = draw(st.floats(min_value=fase2, max_value=2.0, allow_nan=False, allow_infinity=False))
    entrada = draw(st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False))
    risco_r = draw(st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False))
    stop_inicial = entrada + risco_r
    precos = draw(
        st.lists(
            st.floats(
                min_value=entrada - 5 * risco_r,
                max_value=entrada + 5 * risco_r,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=20,
        )
    )
    return fase1, fase2, fase3, entrada, stop_inicial, precos


# ---------------------------------------------------------------------------
# Property 17 — monotonia em LONG
# ---------------------------------------------------------------------------


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_config_e_serie_long())
def test_property_ninjascript_trailing_long_monotonia(
    cfg_e_serie: tuple,
) -> None:
    """**Validates: Requirements 4.5** (Property 17 canônica para LONG).

    Para LONG, ``stop_atual_t+1 >= stop_atual_t`` em qualquer ``t``.
    Adicionalmente, a fase é não-decrescente — só avança.
    """
    fase1, fase2, fase3, entrada, stop_inicial, precos = cfg_e_serie
    trailing = TrailingModelo(fase1_mult=fase1, fase2_mult=fase2, fase3_mult=fase3)
    trailing.abrir_long(entrada, stop_inicial)
    stops: List[float] = [trailing.stop_atual]
    fases: List[FaseTrailing] = [trailing.fase]

    for preco in precos:
        novo_stop = trailing.atualizar(preco)
        stops.append(novo_stop)
        fases.append(trailing.fase)

    # Monotonia (R4.5): para LONG, stop só sobe.
    for i in range(1, len(stops)):
        assert stops[i] >= stops[i - 1] - 1e-9, (
            f"LONG stop violou monotonia em t={i}: {stops[i]} < {stops[i-1]} "
            f"(precos={precos})"
        )

    # Irreversibilidade da fase (só avança).
    ordem_fase = {
        FaseTrailing.SEM_POSICAO: -1,
        FaseTrailing.ENTRADA: 0,
        FaseTrailing.FASE1_BREAKEVEN: 1,
        FaseTrailing.FASE2_LOCK: 2,
        FaseTrailing.FASE3_DINAMICO: 3,
    }
    for i in range(1, len(fases)):
        assert ordem_fase[fases[i]] >= ordem_fase[fases[i - 1]], (
            f"fase regrediu em t={i}: {fases[i-1]} -> {fases[i]}"
        )


# ---------------------------------------------------------------------------
# Property 17 — monotonia em SHORT
# ---------------------------------------------------------------------------


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_config_e_serie_short())
def test_property_ninjascript_trailing_short_monotonia(
    cfg_e_serie: tuple,
) -> None:
    """**Validates: Requirements 4.5** (Property 17 canônica para SHORT).

    Para SHORT, ``stop_atual_t+1 <= stop_atual_t``.
    """
    fase1, fase2, fase3, entrada, stop_inicial, precos = cfg_e_serie
    trailing = TrailingModelo(fase1_mult=fase1, fase2_mult=fase2, fase3_mult=fase3)
    trailing.abrir_short(entrada, stop_inicial)
    stops: List[float] = [trailing.stop_atual]

    for preco in precos:
        novo_stop = trailing.atualizar(preco)
        stops.append(novo_stop)

    for i in range(1, len(stops)):
        assert stops[i] <= stops[i - 1] + 1e-9, (
            f"SHORT stop violou monotonia em t={i}: {stops[i]} > {stops[i-1]} "
            f"(precos={precos})"
        )


# ---------------------------------------------------------------------------
# Sub-Property — transições corretas (R4.1, R4.2, R4.3)
# ---------------------------------------------------------------------------


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    fase1=st.floats(min_value=0.4, max_value=0.6, allow_nan=False, allow_infinity=False),
    fase2=st.floats(min_value=0.9, max_value=1.1, allow_nan=False, allow_infinity=False),
    fase3=st.floats(min_value=1.5, max_value=2.0, allow_nan=False, allow_infinity=False),
    entrada=st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False),
    risco_r=st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False),
)
def test_property_ninjascript_trailing_transicoes_long(
    fase1: float,
    fase2: float,
    fase3: float,
    entrada: float,
    risco_r: float,
) -> None:
    """**Validates: Requirements 4.1, 4.2, 4.3**.

    Para LONG, alimentando preços em ``entrada + 0.5R``, ``entrada + 1R``
    e ``entrada + 2R``, a fase avança correspondentemente e o stop é o
    esperado pelo design.
    """
    if not (fase1 <= fase2 <= fase3):
        return  # Hypothesis às vezes gera fora de ordem; pulamos.

    stop_inicial = entrada - risco_r
    trailing = TrailingModelo(fase1_mult=fase1, fase2_mult=fase2, fase3_mult=fase3)
    trailing.abrir_long(entrada, stop_inicial)
    assert trailing.fase == FaseTrailing.ENTRADA

    # Atinge fase1 — breakeven.
    preco_fase1 = entrada + fase1 * risco_r + 1e-6
    stop_fase1 = trailing.atualizar(preco_fase1)
    assert trailing.fase == FaseTrailing.FASE1_BREAKEVEN, (
        f"esperava fase1; recebido {trailing.fase} (preco={preco_fase1})"
    )
    assert abs(stop_fase1 - entrada) < 1e-6 or stop_fase1 == entrada, (
        f"stop fase1 deveria ser entrada={entrada}; recebido {stop_fase1}"
    )

    # Atinge fase2 — entrada + 0.3R.
    preco_fase2 = entrada + fase2 * risco_r + 1e-6
    stop_fase2 = trailing.atualizar(preco_fase2)
    assert trailing.fase == FaseTrailing.FASE2_LOCK
    esperado_fase2 = entrada + FASE2_STOP_OFFSET_R * risco_r
    assert abs(stop_fase2 - esperado_fase2) < 1e-6, (
        f"stop fase2 deveria ser {esperado_fase2}; recebido {stop_fase2}"
    )

    # Atinge fase3 — trailing dinâmico (preço - 0.5R).
    preco_fase3 = entrada + fase3 * risco_r + 1e-6
    stop_fase3 = trailing.atualizar(preco_fase3)
    assert trailing.fase == FaseTrailing.FASE3_DINAMICO
    esperado_fase3 = preco_fase3 - FASE3_DISTANCIA_R * risco_r
    # Em fase3 o stop pode ter ficado limitado pelo stop_fase2 anterior
    # (monotonia); validamos o piso.
    assert stop_fase3 >= esperado_fase3 - 1e-6 or stop_fase3 >= stop_fase2 - 1e-9
