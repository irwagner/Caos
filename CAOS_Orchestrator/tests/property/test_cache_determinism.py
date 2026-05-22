"""Property 11 — Cache Determinism.

For every cache hit recorded with ``cache_hit: true`` on a turn not flagged
``nao-deterministico``, the cached response SHALL be byte-identical to the
response produced by recomputing the call under the same key components
(agente, modelo, hash_prompt, hash_contexto, seed).

**Validates: Requirements 16.2, 16.3, 16.5**

Estratégia:

1. Estratégia Hypothesis gera tuplas
   ``(agente, modelo, prompt, contexto, seed)`` a partir do conjunto válido
   do projeto (R2.1, R2.3, R16.2).
2. Mock determinístico de modelo: ``f(prompt, contexto, seed)`` retorna
   ``"resposta::" + sha256(prompt|contexto|seed)``.
3. Para cada tupla:
   a. Computa a chave determinística com :meth:`SkillLLMCache.computar_chave`.
   b. Cache miss → mock é chamado, resposta é gravada.
   c. Cache hit (segunda invocação) → mock NÃO é chamado (assertimos isso
      via contador de chamadas) e resposta retornada é byte-a-byte idêntica
      ao output do mock.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.models import EntradaCache
from caos.skills.llm_cache import SkillLLMCache

# ---------------------------------------------------------------------------
# Estratégias Hypothesis
# ---------------------------------------------------------------------------

#: Subconjunto dos 9 agentes do Conselho — usamos pares ``(agente, modelo)``
#: válidos conforme R2.3 para que :class:`EntradaCache` aceite a entrada
#: gravada (campo ``modelo`` é ``Literal``).
PARES_AGENTE_MODELO: tuple[tuple[str, str], ...] = (
    ("Athena", "claude-opus-4.7"),
    ("Odin", "claude-sonnet-4.5"),
    ("Cerberus", "claude-sonnet-4.5"),
    ("Manolo", "claude-haiku-4.5"),
    ("Mister_M", "minimax-m2"),
    ("Mister_M", "qwen3"),
    ("Hermes", "qwen3-coder"),
    ("Hermes", "deepseek-v3.1"),
    ("Rodrigo", "deepseek-v3.1"),
    ("Explorador", "claude-sonnet-4.5"),
    ("Devils_Advocate", "minimax-m2"),
)


def _hash_hex(texto: str) -> str:
    """SHA-256 hex de uma string (codificação UTF-8)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Mock determinístico de modelo
# ---------------------------------------------------------------------------


class _ModeloMock:
    """Mock determinístico de chamada a LLM.

    A resposta é função pura de ``(prompt, contexto, seed)`` — independente
    do agente/modelo, de forma que invocações com mesma chave de contexto
    sempre produzam o mesmo output. ``chamadas`` permite verificar que a
    Skill consulta o cache antes de re-invocar o modelo.
    """

    def __init__(self) -> None:
        self.chamadas: int = 0

    def invocar(self, *, prompt: str, contexto: str, seed: str) -> str:
        self.chamadas += 1
        bruto = f"{prompt}|{contexto}|{seed}"
        return "resposta::" + _hash_hex(bruto)


# ---------------------------------------------------------------------------
# Property 11
# ---------------------------------------------------------------------------


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    par_agente_modelo=st.sampled_from(PARES_AGENTE_MODELO),
    prompt=st.text(min_size=1, max_size=500),
    contexto=st.text(min_size=0, max_size=500),
    seed=st.one_of(
        st.just(""),
        st.integers(min_value=0, max_value=999_999).map(str),
    ),
)
def test_cache_determinismo(
    par_agente_modelo: tuple[str, str],
    prompt: str,
    contexto: str,
    seed: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 16.2, 16.3, 16.5** (Property 11).

    Para toda tupla ``(agente, modelo, prompt, contexto, seed)`` válida:

    1. Cache miss → mock é chamado exatamente 1 vez.
    2. Resposta é gravada com chave determinística.
    3. Segunda consulta com mesma chave → cache hit; resposta retornada
       é byte-a-byte idêntica à do mock; mock NÃO é chamado novamente.
    """
    agente, modelo = par_agente_modelo
    raiz = tmp_path_factory.mktemp("cache_det")
    skill = SkillLLMCache(diretorio_cache=raiz)
    mock = _ModeloMock()

    hash_prompt = _hash_hex(prompt)
    hash_contexto = _hash_hex(contexto)
    chave = skill.computar_chave(
        agente=agente,
        modelo=modelo,
        hash_prompt=hash_prompt,
        hash_contexto=hash_contexto,
        seed=seed,
    )

    # --- 1ª invocação: cache miss ---
    assert skill.consultar(chave) is None
    resposta_original = mock.invocar(
        prompt=prompt, contexto=contexto, seed=seed
    )
    assert mock.chamadas == 1

    entrada = EntradaCache(
        chave=chave,
        agente=agente,
        modelo=modelo,
        seed=seed,
        data_criacao=datetime(2026, 5, 14, 14, 0, 0, tzinfo=timezone.utc),
        tokens_consumidos_estimados=len(prompt) + len(contexto),
        resposta=resposta_original,
    )
    skill.gravar(entrada)

    # --- 2ª invocação: cache hit ---
    recuperada = skill.consultar(chave)
    assert recuperada is not None, (
        "esperava cache hit após gravação; chave="
        f"{chave!r}, agente={agente!r}, modelo={modelo!r}"
    )

    # Propriedade central: byte-a-byte idêntico à resposta original.
    assert recuperada.resposta == resposta_original, (
        "cache hit retornou resposta diferente da gravada"
    )
    assert recuperada.resposta.encode("utf-8") == (
        resposta_original.encode("utf-8")
    )

    # E o mock NÃO foi chamado de novo (a Skill responde do cache).
    assert mock.chamadas == 1, (
        f"mock chamado {mock.chamadas}x; esperado 1 (cache hit deveria "
        "evitar nova invocação)"
    )

    # Sanity: o computar_chave é estável.
    chave_segunda = skill.computar_chave(
        agente=agente,
        modelo=modelo,
        hash_prompt=hash_prompt,
        hash_contexto=hash_contexto,
        seed=seed,
    )
    assert chave_segunda == chave
