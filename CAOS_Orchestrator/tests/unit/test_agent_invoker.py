"""Testes unitários do :class:`caos.agent_invoker.AgentInvoker` (Task 16).

Cobre R9.2, R16.5, R17.3–R17.5.

Estratégia: composição direta com :class:`SkillLLMCache` e
:class:`SkillTokenBudget` reais sobre diretórios temporários (``tmp_path``).
Não mockamos as Skills — assim os testes exercitam a integração ponta-a-ponta
do encadeamento Token_Budget → Cache → Backend → Cache write.

O backend é injetado como mock determinístico via fixtures de
``conftest.py`` (:func:`backend_mock_deterministico`,
:func:`backend_falho`, :func:`backend_resposta_vazia`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from caos.agent_invoker import (
    MODELOS_SEM_SEED,
    AgentInvoker,
    InvocacaoModelo,
    ResultadoInvocacao,
)
from caos.skills.llm_cache import SkillLLMCache
from caos.skills.token_budget import SkillTokenBudget
from caos.steering_engine import ORCAMENTO_TOKENS_DEFAULT


# ---------------------------------------------------------------------------
# Helpers de montagem
# ---------------------------------------------------------------------------


def _montar_invoker(
    tmp_path: Path,
    backend,
    *,
    orcamentos: dict[str, int] | None = None,
) -> tuple[AgentInvoker, SkillLLMCache, SkillTokenBudget]:
    """Constrói :class:`AgentInvoker` com Skills reais sobre ``tmp_path``.

    Retorna a tripla ``(invoker, cache, budget)`` para que os testes possam
    inspecionar o estado de cada Skill após a invocação.
    """
    cache = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
    budget = SkillTokenBudget(
        diretorio_budget=tmp_path / ".budget",
        steering_engine=_SteeringEngineFake(orcamentos or {}),
    )
    invoker = AgentInvoker(
        backend=backend,
        cache=cache,
        token_budget=budget,
    )
    return invoker, cache, budget


class _SteeringEngineFake:
    """Steering engine mínimo, devolve orçamento por agente do dict."""

    def __init__(self, orcamentos: dict[str, int]) -> None:
        self._orcamentos = dict(orcamentos)

    def get_orcamento_de_tokens(self, agente: str) -> int:
        return self._orcamentos.get(agente, ORCAMENTO_TOKENS_DEFAULT)


# ---------------------------------------------------------------------------
# Constantes auxiliares
# ---------------------------------------------------------------------------


class TestConstantes:
    def test_modelos_sem_seed_contem_minimax_e_qwen3(self) -> None:
        assert "minimax-m2" in MODELOS_SEM_SEED
        assert "qwen3" in MODELOS_SEM_SEED
        # Modelos com seed presumida NÃO estão no set:
        assert "claude-opus-4.7" not in MODELOS_SEM_SEED
        assert "claude-sonnet-4.5" not in MODELOS_SEM_SEED


# ---------------------------------------------------------------------------
# Caminho feliz: invocação determinística com seed
# ---------------------------------------------------------------------------


class TestInvocacaoDeterministica:
    def test_invocar_sucesso_com_seed(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Backend determinístico, modelo com seed → cache_hit=False na 1ª."""
        invoker, _, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="proposta de circuit breaker",
            contexto="Modulo_Risco/Trailing.md",
            seed=42,
            tokens_estimados=500,
        )
        resultado = invoker.invocar(params)

        assert isinstance(resultado, ResultadoInvocacao)
        assert resultado.cache_hit is False
        assert resultado.bloqueado_por_orcamento is False
        assert resultado.nao_deterministico is False
        assert resultado.resposta.startswith("resposta::")
        assert resultado.tokens_input_consumidos > 0
        assert resultado.tokens_output_consumidos > 0
        assert resultado.chave_cache is not None
        assert resultado.motivo_bloqueio is None
        assert backend_mock_deterministico.chamadas == 1

    def test_invocar_segunda_vez_retorna_cache(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Mesmo input → 2ª invocação é cache hit; backend não é re-chamado."""
        invoker, _, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="proposta X",
            contexto="contexto Y",
            seed=42,
        )
        primeiro = invoker.invocar(params)
        segundo = invoker.invocar(params)

        assert primeiro.cache_hit is False
        assert segundo.cache_hit is True
        # Resposta byte-a-byte idêntica (R16.3, Property 11).
        assert segundo.resposta == primeiro.resposta
        # Backend chamado exatamente 1x (cache evita re-invocação).
        assert backend_mock_deterministico.chamadas == 1
        # Cache hit reusa a mesma chave.
        assert segundo.chave_cache == primeiro.chave_cache

    def test_invocar_chave_cache_difere_quando_seed_muda(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Seeds diferentes → chaves diferentes; cada uma cacheada à parte."""
        invoker, _, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        base = dict(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="P",
            contexto="C",
        )
        r42 = invoker.invocar(InvocacaoModelo(**base, seed=42))
        r99 = invoker.invocar(InvocacaoModelo(**base, seed=99))
        assert r42.chave_cache != r99.chave_cache
        assert r42.cache_hit is False
        assert r99.cache_hit is False
        assert backend_mock_deterministico.chamadas == 2


# ---------------------------------------------------------------------------
# Modelos sem seed e seed ausente (R9.2)
# ---------------------------------------------------------------------------


class TestNaoDeterministico:
    def test_invocar_modelo_sem_seed_marca_nao_deterministico(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """``modelo='minimax-m2'`` → nao_deterministico=True; sem cache."""
        invoker, cache, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Mister_M",
            modelo="minimax-m2",
            prompt="proposta Fimathe",
            contexto="ctx",
            seed=42,  # Mesmo com seed, MODELOS_SEM_SEED ignora
        )
        resultado = invoker.invocar(params)

        assert resultado.nao_deterministico is True
        assert resultado.cache_hit is False
        assert resultado.chave_cache is None
        # Cache deve estar vazio: não gravamos turnos não-determinísticos.
        assert list(cache.diretorio_cache.glob("*.json")) == []

    def test_invocar_segunda_vez_modelo_sem_seed_chama_backend_de_novo(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Chamadas repetidas com modelo sem seed sempre invocam backend."""
        invoker, _, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Mister_M",
            modelo="qwen3",
            prompt="P",
            contexto="C",
            seed=None,
        )
        invoker.invocar(params)
        invoker.invocar(params)
        invoker.invocar(params)
        # Sem cache → 3 chamadas de backend.
        assert backend_mock_deterministico.chamadas == 3

    def test_invocar_seed_none_em_modelo_compativel_marca_nd(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Modelo aceita seed mas seed=None → nao_deterministico=True."""
        invoker, cache, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="P",
            contexto="C",
            seed=None,
        )
        resultado = invoker.invocar(params)
        assert resultado.nao_deterministico is True
        assert resultado.cache_hit is False
        assert resultado.chave_cache is None
        assert list(cache.diretorio_cache.glob("*.json")) == []

    def test_invocar_modelo_sem_seed_seed_none_segue_nao_deterministico(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Combinação modelo sem seed + seed=None: ND, sem cache."""
        invoker, cache, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Devils_Advocate",
            modelo="minimax-m2",
            prompt="critica",
            contexto="",
            seed=None,
        )
        resultado = invoker.invocar(params)
        assert resultado.nao_deterministico is True
        assert resultado.cache_hit is False
        assert list(cache.diretorio_cache.glob("*.json")) == []


# ---------------------------------------------------------------------------
# Bloqueio por orçamento (R17.3, R17.4)
# ---------------------------------------------------------------------------


class TestBloqueioOrcamento:
    def test_invocar_bloqueio_de_orcamento(
        self, tmp_path: Path, backend_falho
    ) -> None:
        """Pré-popular budget perto do limite → próxima invocação bloqueia.

        Usa :func:`backend_falho` para garantir que o backend NÃO é chamado:
        se o adapter chamar, o teste estoura com :class:`TimeoutError`.
        """
        # Orçamento pequeno: 50.000 tokens para Manolo.
        invoker, _, budget = _montar_invoker(
            tmp_path,
            backend_falho,
            orcamentos={"Manolo": 50_000},
        )
        # Pré-popula consumo perto do limite.
        budget.registrar_consumo(
            "Manolo", tokens_input=49_000, tokens_output=500
        )
        # Estimativa que estouraria o orçamento (49500 + 2000 > 50000).
        params = InvocacaoModelo(
            agente="Manolo",
            modelo="claude-haiku-4.5",
            prompt="P",
            contexto="C",
            seed=42,
            tokens_estimados=2000,
        )
        resultado = invoker.invocar(params)

        assert resultado.bloqueado_por_orcamento is True
        assert resultado.resposta == ""
        assert resultado.tokens_input_consumidos == 0
        assert resultado.tokens_output_consumidos == 0
        assert resultado.cache_hit is False
        assert resultado.motivo_bloqueio is not None
        assert "Manolo" in resultado.motivo_bloqueio
        # Backend NÃO foi chamado (caso contrário, TimeoutError seria
        # propagado).
        assert backend_falho.chamadas == 0

    def test_invocar_bloqueio_preserva_nao_deterministico_flag(
        self, tmp_path: Path, backend_falho
    ) -> None:
        """Mesmo bloqueado, o resultado expõe ``nao_deterministico`` correto.

        Útil para que o caller possa registrar o turno corretamente.
        """
        invoker, _, budget = _montar_invoker(
            tmp_path,
            backend_falho,
            orcamentos={"Mister_M": 20_000},
        )
        budget.registrar_consumo(
            "Mister_M", tokens_input=20_000, tokens_output=0
        )
        # Modelo sem seed: deveria ser ND mesmo bloqueado.
        params = InvocacaoModelo(
            agente="Mister_M",
            modelo="minimax-m2",
            prompt="P",
            contexto="C",
            seed=42,
            tokens_estimados=1000,
        )
        resultado = invoker.invocar(params)
        assert resultado.bloqueado_por_orcamento is True
        assert resultado.nao_deterministico is True
        assert backend_falho.chamadas == 0


# ---------------------------------------------------------------------------
# Contabilização de tokens (R17.5)
# ---------------------------------------------------------------------------


class TestContabilizacaoTokens:
    def test_invocar_registra_tokens_apos_sucesso(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Após invocação bem-sucedida, budget reflete tokens reais."""
        invoker, _, budget = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="proposta com algum tamanho razoável " * 5,
            contexto="contexto " * 3,
            seed=42,
        )
        resultado = invoker.invocar(params)

        estado = budget.obter_estado("Athena")
        assert estado.tokens_input_consumidos == (
            resultado.tokens_input_consumidos
        )
        assert estado.tokens_output_consumidos == (
            resultado.tokens_output_consumidos
        )
        assert estado.tokens_total_consumidos == (
            resultado.tokens_input_consumidos
            + resultado.tokens_output_consumidos
        )

    def test_invocar_cache_hit_nao_incrementa_tokens(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Cache hit não double-conta tokens (já contados na 1ª gravação)."""
        invoker, _, budget = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="P",
            contexto="C",
            seed=42,
        )
        invoker.invocar(params)
        consumo_apos_primeira = budget.obter_estado(
            "Athena"
        ).tokens_total_consumidos

        # 2ª invocação: cache hit
        segundo = invoker.invocar(params)
        assert segundo.cache_hit is True
        assert segundo.tokens_input_consumidos == 0
        assert segundo.tokens_output_consumidos == 0

        # Budget não mudou.
        consumo_apos_segunda = budget.obter_estado(
            "Athena"
        ).tokens_total_consumidos
        assert consumo_apos_primeira == consumo_apos_segunda

    def test_invocar_modelo_sem_seed_incrementa_tokens(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Modelo sem seed também conta tokens (R17.5 vale para ND também)."""
        invoker, _, budget = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Mister_M",
            modelo="minimax-m2",
            prompt="P qualquer",
            contexto="C qualquer",
            seed=None,
        )
        resultado = invoker.invocar(params)
        assert resultado.nao_deterministico is True
        estado = budget.obter_estado("Mister_M")
        assert estado.tokens_total_consumidos > 0
        assert estado.tokens_total_consumidos == (
            resultado.tokens_input_consumidos
            + resultado.tokens_output_consumidos
        )


# ---------------------------------------------------------------------------
# Backend falhando / resposta vazia (compatibilidade com R14)
# ---------------------------------------------------------------------------


class TestBackendDegenerado:
    def test_invocar_propaga_excecao_do_backend(
        self, tmp_path: Path, backend_falho
    ) -> None:
        """Exceção do backend propaga (retry é responsabilidade externa).

        Confirma que :class:`AgentInvoker` é uma camada de plumbing —
        decisões sobre retry/marcação de turno como
        ``agente-indisponivel`` ficam em :mod:`caos.failure_handler`.
        """
        invoker, _, _ = _montar_invoker(
            tmp_path,
            backend_falho,
            orcamentos={"Athena": 1_000_000},
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="P",
            contexto="C",
            seed=42,
        )
        with pytest.raises(TimeoutError):
            invoker.invocar(params)

    def test_invocar_resposta_vazia_registra_zero_tokens(
        self, tmp_path: Path, backend_resposta_vazia
    ) -> None:
        """Backend que devolve resposta vazia → zero tokens, sem crash."""
        invoker, cache, budget = _montar_invoker(
            tmp_path, backend_resposta_vazia
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="P",
            contexto="C",
            seed=42,
        )
        resultado = invoker.invocar(params)
        assert resultado.resposta == ""
        assert resultado.tokens_input_consumidos == 0
        assert resultado.tokens_output_consumidos == 0
        # Cache é gravado mesmo com resposta vazia (R16.4 não condiciona
        # gravação ao conteúdo). Verificação estrutural:
        assert resultado.chave_cache is not None
        assert (
            cache.diretorio_cache / f"{resultado.chave_cache}.json"
        ).is_file()
        # Budget não incrementou (zero tokens).
        assert budget.obter_estado("Athena").tokens_total_consumidos == 0


# ---------------------------------------------------------------------------
# Validações estruturais
# ---------------------------------------------------------------------------


class TestEstrutura:
    def test_invocador_propagado(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """Campo ``invocador`` é apenas um carimbo de auditoria opcional."""
        cache = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        budget = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        invoker = AgentInvoker(
            backend=backend_mock_deterministico,
            cache=cache,
            token_budget=budget,
            invocador="Athena",
        )
        assert invoker.invocador == "Athena"

    def test_resultado_invocacao_e_imutavel(
        self, tmp_path: Path, backend_mock_deterministico
    ) -> None:
        """:class:`ResultadoInvocacao` é frozen (não pode ser mutado)."""
        invoker, _, _ = _montar_invoker(
            tmp_path, backend_mock_deterministico
        )
        params = InvocacaoModelo(
            agente="Athena",
            modelo="claude-opus-4.7",
            prompt="P",
            contexto="C",
            seed=42,
        )
        resultado = invoker.invocar(params)
        with pytest.raises(Exception):  # FrozenInstanceError em dataclass
            resultado.resposta = "outro valor"  # type: ignore[misc]
