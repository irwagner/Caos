"""Property-based test do ``CerberusModelo`` (Property 16 do Spec 3).

Implementa **Property 16 — Cerberus C# Soundness** do ``design.md``
do Spec 3:

    For every entry attempt, ``CerberusModelo.autorizar_entrada(contratos,
    risco_usd)`` SHALL return ``False`` whenever ``contratos < 1`` OR
    ``contratos > max_contratos`` OR ``risco_usd <= 0`` OR the circuit
    breaker is active.

**Validates: Requirements 3.1, 3.2, 3.5**

Como o pacote :mod:`caos.ninjascript_modelo.cerberus` é uma reimplementação
fiel da lógica pura de ``Cerberus.cs`` (Spec 3 — Task 2), esta Property
também certifica o C# correspondente.

Cobertura adicional:

1. **Decisão pura (R3.1)**: para qualquer combinação de
   ``(max_contratos, contratos, risco_usd)``, o resultado da função
   bate com a regra de decisão idempotente fora da classe.
2. **Circuit breaker (R3.2)**: alimentando PnL realizado cumulativo
   negativo, ``circuit_breaker_ativo`` vira ``True`` e bloqueia
   entradas futuras.
3. **Rollover diário (R3.5)**: injetando um clock fake que avança o
   dia, ``pnl_diario_realizado`` zera e ``circuit_breaker_ativo``
   fica ``False`` mesmo após ter sido ativado no dia anterior.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.ninjascript_modelo.cerberus import CerberusModelo

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decisao_de_referencia(
    *,
    contratos: int,
    risco_usd: float,
    max_contratos: int,
    circuit_breaker_ativo: bool,
) -> bool:
    """Réplica da regra de decisão de :meth:`CerberusModelo.autorizar_entrada`.

    Implementação independente — se o modelo divergir desta função, a
    Property falha (e indica bug em um dos lados).
    """
    import math

    if circuit_breaker_ativo:
        return False
    if contratos < 1 or contratos > max_contratos:
        return False
    if math.isnan(risco_usd) or math.isinf(risco_usd):
        return False
    if risco_usd <= 0.0:
        return False
    return True


# ---------------------------------------------------------------------------
# Property 16 — Cerberus C# Soundness
# ---------------------------------------------------------------------------


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    max_contratos=st.integers(min_value=1, max_value=10),
    circuit_breaker_usd=st.floats(min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    contratos=st.integers(min_value=-5, max_value=15),
    risco_usd=st.one_of(
        st.floats(min_value=-100.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        st.just(0.0),
    ),
    pnl_realizado_acumulado=st.floats(min_value=-10000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
)
def test_property_ninjascript_cerberus(
    max_contratos: int,
    circuit_breaker_usd: float,
    contratos: int,
    risco_usd: float,
    pnl_realizado_acumulado: float,
) -> None:
    """**Validates: Requirements 3.1, 3.2, 3.5** (Property 16).

    Para qualquer combinação ``(max_contratos, circuit_breaker_usd,
    contratos, risco_usd, pnl_realizado_acumulado)`` válida pelos
    ranges de R6.1, o resultado de ``autorizar_entrada`` é exatamente
    o ditado pela função de decisão pura :func:`_decisao_de_referencia`.
    """
    cerberus = CerberusModelo(
        max_contratos=max_contratos,
        circuit_breaker_usd=circuit_breaker_usd,
    )
    cerberus.registrar_pnl_realizado(pnl_realizado_acumulado)

    esperado_breaker_ativo = pnl_realizado_acumulado <= -circuit_breaker_usd
    assert cerberus.circuit_breaker_ativo == esperado_breaker_ativo, (
        f"circuit_breaker_ativo divergiu: "
        f"esperado {esperado_breaker_ativo} para pnl={pnl_realizado_acumulado}, "
        f"limite={circuit_breaker_usd}; recebido {cerberus.circuit_breaker_ativo}"
    )

    autorizado = cerberus.autorizar_entrada(contratos, risco_usd)
    esperado = _decisao_de_referencia(
        contratos=contratos,
        risco_usd=risco_usd,
        max_contratos=max_contratos,
        circuit_breaker_ativo=esperado_breaker_ativo,
    )
    assert autorizado == esperado, (
        f"divergência em autorizar_entrada: esperado {esperado} para "
        f"contratos={contratos}, risco_usd={risco_usd}, "
        f"max_contratos={max_contratos}, breaker_ativo={esperado_breaker_ativo}; "
        f"recebido {autorizado}"
    )


# ---------------------------------------------------------------------------
# Property complementar — rollover diário (R3.5)
# ---------------------------------------------------------------------------


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    circuit_breaker_usd=st.floats(min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    pnl_dia_anterior=st.floats(min_value=-10000.0, max_value=-50.0, allow_nan=False, allow_infinity=False),
    pnl_dia_novo=st.floats(min_value=-10000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    horas_avanco=st.integers(min_value=24, max_value=72),
)
def test_property_ninjascript_cerberus_rollover_diario(
    circuit_breaker_usd: float,
    pnl_dia_anterior: float,
    pnl_dia_novo: float,
    horas_avanco: int,
) -> None:
    """**Validates: Requirements 3.5** — rollover de dia UTC reseta estado.

    Após o rollover, mesmo que o circuit breaker tenha sido ativado no
    dia anterior, ``circuit_breaker_ativo`` volta a ``False`` e
    ``pnl_diario_realizado`` zera. A regra de decisão volta a operar
    sobre o PnL acumulado novo.
    """
    # Clock injetável que vai avançar manualmente entre as 2 fases do teste.
    instante: List[datetime] = [datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)]

    def agora() -> datetime:
        return instante[0]

    cerberus = CerberusModelo(
        max_contratos=5,
        circuit_breaker_usd=circuit_breaker_usd,
        agora_utc=agora,
    )

    # Dia 1: dispara breaker.
    cerberus.registrar_pnl_realizado(pnl_dia_anterior)
    if pnl_dia_anterior <= -circuit_breaker_usd:
        assert cerberus.circuit_breaker_ativo, (
            f"breaker deveria estar ativo para pnl={pnl_dia_anterior}, limite={circuit_breaker_usd}"
        )

    # Avança o clock para um novo dia UTC.
    instante[0] = instante[0] + timedelta(hours=horas_avanco)

    # Acessar qualquer property dispara o rollover; verificamos o reset.
    assert cerberus.pnl_diario_realizado == 0.0, (
        f"pnl_diario_realizado deveria zerar após rollover; recebido {cerberus.pnl_diario_realizado}"
    )
    assert cerberus.circuit_breaker_ativo is False, (
        "circuit_breaker_ativo deveria virar False após rollover"
    )

    # Registra novo PnL no dia novo e valida que a decisão é a esperada.
    cerberus.registrar_pnl_realizado(pnl_dia_novo)
    esperado_breaker = pnl_dia_novo <= -circuit_breaker_usd
    assert cerberus.circuit_breaker_ativo == esperado_breaker
