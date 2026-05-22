"""Adapter de invocação de agentes via API nativa do Kiro (Task 16).

Este módulo concentra o **encadeamento canônico** que envolve toda chamada
a um agente do Conselho durante um Debate:

1. **Token_Budget_Guard** (pré): consulta :class:`SkillTokenBudget` e
   bloqueia a invocação se ``tokens_estimados`` estouraria o orçamento
   diário do agente (R17.3, R17.4).
2. **LLM_Cache_Adapter** (pré): quando o turno é determinístico (modelo
   suporta seed e ``seed is not None``), consulta :class:`SkillLLMCache`
   pela chave canônica e devolve a resposta cacheada com
   ``cache_hit=True`` (R16.3, R16.5).
3. **Invocação real**: chama um :class:`BackendModelo` (em produção, uma
   implementação que aciona a API de subagente do Kiro; em testes, um
   mock determinístico).
4. **Registro de tokens consumidos**: aplica
   :meth:`SkillTokenBudget.registrar_consumo` com os tokens efetivamente
   reportados pelo backend (R17.5).
5. **Gravação no cache**: quando determinístico, persiste a entrada via
   :meth:`SkillLLMCache.gravar` (R16.4).

Para os modelos sem suporte a seed (R9.2 — variantes da família MiniMax/
Qwen3 expostas ao Conselho), o turno é automaticamente marcado como
``nao_deterministico=True`` e o cache é desativado para essa invocação.
A mesma política se aplica quando o caller invoca o adapter sem seed
(``seed=None``) em modelos que aceitariam seed: sem seed não há como
reproduzir, então não cacheamos.

O adapter NÃO conhece a state machine do Debate — quem registra
``status: orcamento-de-tokens-esgotado`` no turno é o orquestrador
(Athena), a partir do campo :attr:`ResultadoInvocacao.bloqueado_por_orcamento`
devolvido aqui.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol

from caos.models import EntradaCache
from caos.skills.llm_cache import SkillLLMCache
from caos.skills.token_budget import SkillTokenBudget

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Modelos cuja API conhecida não expõe parâmetro de seed (R9.2).
#:
#: Os turnos rodando sob esses modelos são automaticamente marcados como
#: ``nao_deterministico: true`` e o cache é desativado para eles, sem
#: consulta nem gravação. Os demais modelos da R2.3 são presumidos como
#: aceitando seed.
MODELOS_SEM_SEED: frozenset[str] = frozenset({"minimax-m2", "qwen3"})


# ---------------------------------------------------------------------------
# Tipos públicos: backend
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RespostaModelo:
    """Saída tipada do :class:`BackendModelo`.

    Attributes
    ----------
    texto:
        Resposta textual do modelo (formato Markdown estruturado segundo
        o ``formato_de_saida`` do agente — esta camada não interpreta).
    tokens_input:
        Tokens de input efetivamente consumidos. Inteiro não-negativo.
    tokens_output:
        Tokens de output efetivamente consumidos. Inteiro não-negativo.
    """

    texto: str
    tokens_input: int
    tokens_output: int


class BackendModelo(Protocol):
    """API mínima esperada do backend que invoca o modelo de fato.

    Em produção, será uma implementação que chama a API de subagente do
    Kiro (não acessível neste Spec). Em testes, usamos um mock
    determinístico (ver :mod:`tests.conftest`).

    Implementações DEVEM ser síncronas e DEVEM devolver
    :class:`RespostaModelo` válida ou levantar exceção. Esta camada NÃO
    aplica retries — isso é responsabilidade do
    :mod:`caos.failure_handler` quando integrado ao orquestrador.
    """

    def invocar(  # pragma: no cover - Protocol
        self,
        *,
        agente: str,
        modelo: str,
        prompt: str,
        contexto: str,
        seed: Optional[int],
    ) -> RespostaModelo:
        ...


# ---------------------------------------------------------------------------
# Tipos públicos: invocação e resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvocacaoModelo:
    """Parâmetros de uma invocação de agente.

    Attributes
    ----------
    agente:
        Nome canônico do agente (R2.1) — ex.: ``"Athena"``.
    modelo:
        Identificador do modelo (R2.3) — ex.: ``"claude-opus-4.7"``.
    prompt:
        Texto do prompt enviado ao modelo (não inclui o contexto).
    contexto:
        Texto agregado das Notas_Zettel injetadas — input para
        :func:`_hash_sha256`.
    seed:
        Seed numérica quando o modelo suporta. ``None`` força
        ``nao_deterministico=True`` e desativa o cache.
    tokens_estimados:
        Estimativa de tokens consumidos pela invocação, usada na
        verificação de orçamento (R17.3). Default = 1000.
    """

    agente: str
    modelo: str
    prompt: str
    contexto: str
    seed: Optional[int] = None
    tokens_estimados: int = 1000


@dataclass(frozen=True)
class ResultadoInvocacao:
    """Saída do encadeamento Token_Budget → Cache → Backend.

    Attributes
    ----------
    agente:
        Eco do :attr:`InvocacaoModelo.agente`.
    modelo:
        Eco do :attr:`InvocacaoModelo.modelo`.
    resposta:
        Texto retornado (vazio quando ``bloqueado_por_orcamento=True``).
    cache_hit:
        ``True`` quando a resposta veio do :class:`SkillLLMCache`
        (R16.3); ``False`` em qualquer outro caso (incluindo turnos
        não-determinísticos e bloqueios de orçamento).
    bloqueado_por_orcamento:
        ``True`` quando :class:`SkillTokenBudget` rejeitou a invocação
        (R17.3, R17.4). Nesse caso o backend NÃO foi chamado e tokens
        consumidos são zero.
    nao_deterministico:
        ``True`` quando ``modelo`` está em :data:`MODELOS_SEM_SEED` ou
        ``seed is None`` (R9.2). O caller deve marcar o turno
        correspondente no arquivo de Debate.
    tokens_input_consumidos, tokens_output_consumidos:
        Tokens efetivamente registrados no :class:`SkillTokenBudget`.
        Em cache hit ambos são zero (a contagem já ocorreu quando a
        entrada foi gravada — não double-counting).
    chave_cache:
        Chave SHA-256 hex usada na consulta/gravação (apenas em turnos
        determinísticos); ``None`` quando o cache foi desativado.
    motivo_bloqueio:
        Mensagem humana explicando o bloqueio (apenas quando
        ``bloqueado_por_orcamento=True``).
    """

    agente: str
    modelo: str
    resposta: str
    cache_hit: bool
    bloqueado_por_orcamento: bool
    nao_deterministico: bool
    tokens_input_consumidos: int
    tokens_output_consumidos: int
    chave_cache: Optional[str] = None
    motivo_bloqueio: Optional[str] = None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


@dataclass
class AgentInvoker:
    """Encadeia Token_Budget → Cache → Backend → Cache write.

    Parameters
    ----------
    backend:
        Implementação concreta de :class:`BackendModelo`. Em produção,
        wrapper sobre a API de subagente do Kiro; em testes, mock
        determinístico (ver :mod:`tests.conftest`).
    cache:
        Instância de :class:`SkillLLMCache` apontando para
        ``CAOS_Orchestrator/.cache/`` (R16.1).
    token_budget:
        Instância de :class:`SkillTokenBudget` apontando para
        ``CAOS_Orchestrator/.budget/`` (R17.1).
    invocador:
        Identificador opcional do agente invocador, propagado para
        auditoria pelo caller.
    """

    backend: BackendModelo
    cache: SkillLLMCache
    token_budget: SkillTokenBudget
    invocador: Optional[str] = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def invocar(self, params: InvocacaoModelo) -> ResultadoInvocacao:
        """Executa o pipeline canônico para uma invocação de agente.

        Pipeline:

        1. Determina ``nao_deterministico`` (R9.2): ``True`` se
           ``params.modelo in MODELOS_SEM_SEED`` ou ``params.seed is None``.
        2. :meth:`SkillTokenBudget.verificar` (R17.3): se bloqueado,
           devolve resultado vazio com ``bloqueado_por_orcamento=True``.
        3. Quando determinístico (R16.5):
           a. Computa chave via :meth:`SkillLLMCache.computar_chave`.
           b. Consulta cache; em hit, devolve a resposta sem chamar o
              backend e sem incrementar o budget (tokens já contados na
              gravação anterior).
        4. Invoca :meth:`BackendModelo.invocar`.
        5. Registra tokens via :meth:`SkillTokenBudget.registrar_consumo`
           (R17.5).
        6. Quando determinístico, persiste a entrada via
           :meth:`SkillLLMCache.gravar` (R16.4).
        7. Devolve :class:`ResultadoInvocacao` com ``cache_hit=False``.
        """
        nao_det = (
            params.modelo in MODELOS_SEM_SEED or params.seed is None
        )

        # --- 1. Token_Budget_Guard (pré) ---
        verificacao = self.token_budget.verificar(
            params.agente, tokens_estimados=params.tokens_estimados
        )
        if verificacao.bloqueado:
            motivo = (
                f"orçamento diário de tokens esgotado para {params.agente!r}: "
                f"{verificacao.tokens_consumidos}+{verificacao.tokens_estimados} "
                f"> {verificacao.orcamento_diario}"
            )
            return ResultadoInvocacao(
                agente=params.agente,
                modelo=params.modelo,
                resposta="",
                cache_hit=False,
                bloqueado_por_orcamento=True,
                nao_deterministico=nao_det,
                tokens_input_consumidos=0,
                tokens_output_consumidos=0,
                chave_cache=None,
                motivo_bloqueio=motivo,
            )

        # --- 2. LLM_Cache_Adapter (pré) — apenas em turnos determinísticos ---
        chave: Optional[str] = None
        if not nao_det:
            chave = self._computar_chave_cache(params)
            entrada_cacheada = self.cache.consultar(chave)
            if entrada_cacheada is not None:
                # Cache hit: NÃO contamos tokens (já contados na gravação).
                return ResultadoInvocacao(
                    agente=params.agente,
                    modelo=params.modelo,
                    resposta=entrada_cacheada.resposta,
                    cache_hit=True,
                    bloqueado_por_orcamento=False,
                    nao_deterministico=False,
                    tokens_input_consumidos=0,
                    tokens_output_consumidos=0,
                    chave_cache=chave,
                    motivo_bloqueio=None,
                )

        # --- 3. Invocação real ---
        seed_efetiva = None if nao_det else params.seed
        resposta = self.backend.invocar(
            agente=params.agente,
            modelo=params.modelo,
            prompt=params.prompt,
            contexto=params.contexto,
            seed=seed_efetiva,
        )

        # --- 4. Registro de tokens consumidos (R17.5) ---
        self.token_budget.registrar_consumo(
            params.agente,
            tokens_input=resposta.tokens_input,
            tokens_output=resposta.tokens_output,
        )

        # --- 5. Gravação no cache (apenas determinístico) ---
        if not nao_det and chave is not None:
            entrada = EntradaCache(
                chave=chave,
                agente=params.agente,  # type: ignore[arg-type]
                modelo=params.modelo,  # type: ignore[arg-type]
                seed=str(params.seed) if params.seed is not None else "",
                data_criacao=datetime.now(timezone.utc),
                tokens_consumidos_estimados=(
                    resposta.tokens_input + resposta.tokens_output
                ),
                resposta=resposta.texto,
            )
            self.cache.gravar(entrada)

        return ResultadoInvocacao(
            agente=params.agente,
            modelo=params.modelo,
            resposta=resposta.texto,
            cache_hit=False,
            bloqueado_por_orcamento=False,
            nao_deterministico=nao_det,
            tokens_input_consumidos=resposta.tokens_input,
            tokens_output_consumidos=resposta.tokens_output,
            chave_cache=chave,
            motivo_bloqueio=None,
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _computar_chave_cache(self, params: InvocacaoModelo) -> str:
        """Calcula a chave canônica do cache (R16.2).

        Hash SHA-256 hex sobre ``(agente, modelo, hash_prompt,
        hash_contexto, seed)`` na codificação canônica usada pela
        :meth:`SkillLLMCache.computar_chave`. ``seed`` é serializada
        como ``str(int)`` para modelos com suporte a seed; modelos sem
        suporte nunca chegam aqui (curto-circuito em
        ``nao_deterministico``).
        """
        hash_prompt = _hash_sha256(params.prompt)
        hash_contexto = _hash_sha256(params.contexto)
        seed_str = str(params.seed) if params.seed is not None else ""
        return self.cache.computar_chave(
            agente=params.agente,
            modelo=params.modelo,
            hash_prompt=hash_prompt,
            hash_contexto=hash_contexto,
            seed=seed_str,
        )


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------


def _hash_sha256(s: str) -> str:
    """SHA-256 hex de ``s`` codificada em UTF-8."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


__all__ = [
    "MODELOS_SEM_SEED",
    "AgentInvoker",
    "BackendModelo",
    "InvocacaoModelo",
    "RespostaModelo",
    "ResultadoInvocacao",
]
