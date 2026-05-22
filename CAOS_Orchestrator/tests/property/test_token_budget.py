"""Property 12 — Token Budget Enforcement.

For every agent A and every UTC day D, the sum of ``tokens_total_consumidos``
recorded for A on D SHALL be less than or equal to the configured
``orcamento_diario_tokens`` for A.

**Validates: Requirements 17.3, 17.4, 17.5**

Estratégia:

1. Estratégia gera uma lista de ``(agente, tokens_input, tokens_output)`` e um
   orçamento uniforme aplicado a todos os agentes via
   :class:`_SteeringEngineFake`.
2. Para cada consumo: chamamos :meth:`SkillTokenBudget.verificar`. Se
   ``bloqueado=False``, registramos o consumo via
   :meth:`SkillTokenBudget.registrar_consumo`. Caso contrário, pulamos
   (espelha o comportamento de Athena descrito em R17.4 — turno marcado
   como ``orcamento-de-tokens-esgotado`` e Debate prossegue sem o agente).
3. Ao final, para cada agente que consumiu, verificamos a invariante
   ``tokens_total_consumidos <= orcamento_diario_tokens``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.skills.token_budget import SkillTokenBudget

# ---------------------------------------------------------------------------
# Constantes / estratégias
# ---------------------------------------------------------------------------

#: Conjunto fixo de agentes (R2.1). Hypothesis amostra dele para gerar
#: sequências realistas de invocações em um Debate.
AGENTES: tuple[str, ...] = (
    "Athena",
    "Odin",
    "Mister_M",
    "Manolo",
    "Rodrigo",
    "Cerberus",
    "Hermes",
    "Explorador",
    "Devils_Advocate",
)


class _SteeringEngineFake:
    """Stub mínimo de :class:`SteeringEngine` que retorna orçamento fixo.

    Reflete o cenário onde toda configuração de
    ``orcamento_diario_tokens`` foi unificada para um valor controlado
    pelo teste.
    """

    def __init__(self, orcamento: int) -> None:
        self._orcamento = orcamento

    def get_orcamento_de_tokens(self, agente: str) -> int:
        return self._orcamento


# ---------------------------------------------------------------------------
# Property 12
# ---------------------------------------------------------------------------


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    consumos=st.lists(
        st.tuples(
            st.sampled_from(AGENTES),
            st.integers(min_value=0, max_value=10_000),  # tokens_input
            st.integers(min_value=0, max_value=10_000),  # tokens_output
        ),
        min_size=0,
        max_size=50,
    ),
    orcamento=st.integers(min_value=10_000, max_value=2_000_000),
)
def test_token_budget_enforcement(
    consumos: list[tuple[str, int, int]],
    orcamento: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 17.3, 17.4, 17.5** (Property 12).

    Em qualquer sequência arbitrária de invocações, ao final temos para
    todo agente A e dia D:

        ``tokens_total_consumidos[A, D] <= orcamento_diario_tokens[A]``

    O bloqueio é honrado: invocações que estourariam o orçamento são
    puladas (R17.4); invocações que cabem são registradas (R17.5).
    """
    raiz = tmp_path_factory.mktemp("token_budget")
    engine = _SteeringEngineFake(orcamento)
    skill = SkillTokenBudget(
        diretorio_budget=raiz,
        steering_engine=engine,
    )
    dia = date(2026, 5, 14)

    for agente, tokens_input, tokens_output in consumos:
        estimado = tokens_input + tokens_output
        resultado = skill.verificar(
            agente, tokens_estimados=estimado, dia=dia
        )
        # Sanity da própria verificação: orçamento devolvido é o configurado.
        assert resultado.orcamento_diario == orcamento

        if resultado.bloqueado:
            # Athena pula a invocação (R17.4). NÃO registramos consumo.
            continue

        skill.registrar_consumo(
            agente,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            dia=dia,
        )

    # --- Invariante central da Property 12 ---
    consumo_por_agente = skill.consumo_total_dia(dia)
    for agente, total in consumo_por_agente.items():
        assert total <= orcamento, (
            f"violação de orçamento: agente {agente!r} consumiu {total} "
            f"tokens em {dia}, excedendo orçamento de {orcamento}"
        )

    # Verifica também que a soma input+output bate com total para cada
    # agente (consistência interna do EstadoOrcamento).
    for agente in set(a for a, _, _ in consumos):
        estado = skill.obter_estado(agente, dia=dia)
        assert (
            estado.tokens_total_consumidos
            == estado.tokens_input_consumidos
            + estado.tokens_output_consumidos
        )
        assert estado.tokens_total_consumidos <= orcamento
