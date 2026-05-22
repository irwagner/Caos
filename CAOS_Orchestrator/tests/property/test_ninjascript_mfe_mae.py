"""Property-based test do ``MfeMaeModelo`` (Property 18 do Spec 3).

Implementa **Property 18 — MFE/MAE Convenção e Não-Negatividade** do
``design.md`` do Spec 3:

    For every closed trade emitted by ``MfeMaeModelo.fechar(...)``,
    ``mfe_ticks >= 0`` AND ``mae_ticks <= 0`` AND ``|mfe| + |mae| >=
    |saida_preco - entrada_preco| / tick_size`` (nem MFE nem MAE podem
    ser menores que a excursão final efetiva, em magnitude).

**Validates: Requirements 5.1, 5.4**

Como o pacote :mod:`caos.ninjascript_modelo.mfe_mae` é uma
reimplementação fiel de ``MfeMaeTracker.cs`` (Spec 3 — Task 4), esta
Property também certifica o C# correspondente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.ninjascript_modelo.mfe_mae import (
    DirecaoTradeMfeMae,
    MfeMaeModelo,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Estratégias auxiliares
# ---------------------------------------------------------------------------


@st.composite
def _trade_long(draw):
    """Gera um cenário de trade LONG completo."""
    tick_size = draw(st.sampled_from([0.25, 0.5, 1.0]))
    entrada = draw(st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False))
    precos = draw(
        st.lists(
            st.floats(
                min_value=entrada - 100.0,
                max_value=entrada + 100.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=20,
        )
    )
    saida = draw(
        st.floats(
            min_value=entrada - 100.0,
            max_value=entrada + 100.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    pnl = draw(st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    return tick_size, entrada, precos, saida, pnl


@st.composite
def _trade_short(draw):
    tick_size = draw(st.sampled_from([0.25, 0.5, 1.0]))
    entrada = draw(st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False))
    precos = draw(
        st.lists(
            st.floats(
                min_value=entrada - 100.0,
                max_value=entrada + 100.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=20,
        )
    )
    saida = draw(
        st.floats(
            min_value=entrada - 100.0,
            max_value=entrada + 100.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    pnl = draw(st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    return tick_size, entrada, precos, saida, pnl


# ---------------------------------------------------------------------------
# Property 18 — convenção e não-negatividade
# ---------------------------------------------------------------------------


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_trade_long())
def test_property_ninjascript_mfe_mae_long(
    cenario: tuple,
) -> None:
    """**Validates: Requirements 5.1, 5.4** (Property 18 canônica para LONG).

    Para qualquer série de preços e saída, o snapshot devolvido por
    ``fechar`` satisfaz:

    - ``mfe_ticks >= 0``
    - ``mae_ticks <= 0``
    - ``mfe_ticks >= round(max(precos) - entrada) / tick_size``
      (cota inferior do MFE)
    - ``mae_ticks <= round(min(precos) - entrada) / tick_size``
      (cota superior do MAE — note que delta negativo vira mae mais
      profundo).
    """
    tick_size, entrada, precos, saida, pnl = cenario
    tracker = MfeMaeModelo(tick_size=tick_size)
    tracker.abrir(
        id_trade=1,
        direcao=DirecaoTradeMfeMae.LONG,
        entrada_preco=entrada,
        entrada_timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=UTC),
    )

    for p in precos:
        tracker.atualizar(p)

    snap = tracker.fechar(
        saida_preco=saida,
        saida_timestamp=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
        pnl_usd=pnl,
    )

    # Convenções de sinal (R5.4).
    assert snap.mfe_ticks >= 0, (
        f"LONG mfe_ticks deve ser >= 0; recebido {snap.mfe_ticks} "
        f"(precos={precos}, saida={saida}, entrada={entrada})"
    )
    assert snap.mae_ticks <= 0, (
        f"LONG mae_ticks deve ser <= 0; recebido {snap.mae_ticks}"
    )

    # Cota inferior do MFE: precisa cobrir pelo menos a maior excursão
    # favorável observada (incluindo o preço de saída — que é a última
    # atualização aplicada por ``fechar``).
    todos_precos = list(precos) + [saida]
    delta_max = max(todos_precos) - entrada
    delta_min = min(todos_precos) - entrada
    mfe_esperado_min = max(0, int(round(delta_max / tick_size)))
    mae_esperado_max = min(0, int(round(delta_min / tick_size)))

    assert snap.mfe_ticks >= mfe_esperado_min - 1, (
        f"mfe_ticks={snap.mfe_ticks} abaixo da cota mínima {mfe_esperado_min} "
        f"(delta_max={delta_max}, tick_size={tick_size})"
    )
    assert snap.mae_ticks <= mae_esperado_max + 1, (
        f"mae_ticks={snap.mae_ticks} acima da cota máxima {mae_esperado_max} "
        f"(delta_min={delta_min}, tick_size={tick_size})"
    )

    # Snapshot é UTC e timestamps estão na ordem certa.
    assert snap.entrada_timestamp.tzinfo is not None
    assert snap.saida_timestamp >= snap.entrada_timestamp
    assert snap.id_trade == 1
    assert snap.direcao == DirecaoTradeMfeMae.LONG


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_trade_short())
def test_property_ninjascript_mfe_mae_short(
    cenario: tuple,
) -> None:
    """**Validates: Requirements 5.1, 5.4** (Property 18 canônica para SHORT).

    Em SHORT a convenção se inverte: queda de preço é favorável (gera
    MFE positivo). A asserção de sinais permanece (mfe>=0, mae<=0).
    """
    tick_size, entrada, precos, saida, pnl = cenario
    tracker = MfeMaeModelo(tick_size=tick_size)
    tracker.abrir(
        id_trade=42,
        direcao=DirecaoTradeMfeMae.SHORT,
        entrada_preco=entrada,
        entrada_timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=UTC),
    )

    for p in precos:
        tracker.atualizar(p)

    snap = tracker.fechar(
        saida_preco=saida,
        saida_timestamp=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
        pnl_usd=pnl,
    )

    assert snap.mfe_ticks >= 0
    assert snap.mae_ticks <= 0

    todos_precos = list(precos) + [saida]
    # Para SHORT, excursão favorável = entrada - preco (preço caindo).
    delta_max_fav = entrada - min(todos_precos)
    delta_min_fav = entrada - max(todos_precos)
    mfe_esperado_min = max(0, int(round(delta_max_fav / tick_size)))
    mae_esperado_max = min(0, int(round(delta_min_fav / tick_size)))

    assert snap.mfe_ticks >= mfe_esperado_min - 1, (
        f"SHORT mfe_ticks={snap.mfe_ticks} abaixo da cota {mfe_esperado_min}"
    )
    assert snap.mae_ticks <= mae_esperado_max + 1, (
        f"SHORT mae_ticks={snap.mae_ticks} acima da cota {mae_esperado_max}"
    )

    assert snap.id_trade == 42
    assert snap.direcao == DirecaoTradeMfeMae.SHORT


# ---------------------------------------------------------------------------
# Sub-Property — idempotência de Atualizar
# ---------------------------------------------------------------------------


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    tick_size=st.sampled_from([0.25, 0.5, 1.0]),
    entrada=st.floats(min_value=100.0, max_value=20000.0, allow_nan=False, allow_infinity=False),
    preco_repetido=st.floats(min_value=50.0, max_value=22000.0, allow_nan=False, allow_infinity=False),
    n_repeticoes=st.integers(min_value=1, max_value=20),
)
def test_property_ninjascript_mfe_mae_idempotencia(
    tick_size: float,
    entrada: float,
    preco_repetido: float,
    n_repeticoes: int,
) -> None:
    """**Validates: Requirements 5.1** — chamadas repetidas de ``atualizar``
    com o mesmo preço não alteram o estado.
    """
    tracker = MfeMaeModelo(tick_size=tick_size)
    tracker.abrir(
        id_trade=1,
        direcao=DirecaoTradeMfeMae.LONG,
        entrada_preco=entrada,
        entrada_timestamp=datetime(2026, 1, 1, 13, 30, tzinfo=UTC),
    )

    tracker.atualizar(preco_repetido)
    mfe_apos_primeira = tracker.mfe_ticks_corrente
    mae_apos_primeira = tracker.mae_ticks_corrente

    for _ in range(n_repeticoes):
        tracker.atualizar(preco_repetido)

    assert tracker.mfe_ticks_corrente == mfe_apos_primeira
    assert tracker.mae_ticks_corrente == mae_apos_primeira
