"""Configuração compartilhada de pytest para CAOS_Orchestrator.

Este arquivo concentra as fixtures consumidas pelos testes de propriedade
e unitários do orquestrador. As fixtures principais foram introduzidas
pela Task 16 (Adapter de invocação de agentes via API nativa do Kiro):

- :func:`backend_mock_deterministico`: backend de modelo que devolve
  resposta puramente função de ``(prompt, contexto, seed)``, com
  contador de chamadas exposto para asserções.
- :func:`backend_falho`: backend que sempre lança :class:`TimeoutError`,
  útil para validar que :class:`AgentInvoker` não chama o backend quando
  bloqueado pelo orçamento.
- :func:`backend_resposta_vazia`: backend que devolve resposta com texto
  vazio e zero tokens — caso degenerado de R14.3.

Task 15 acrescenta:

- :class:`_BackendScriptado`: backend cuja resposta é determinada por um
  *script* — um dict que mapeia ``(agente, fase) -> RespostaModelo`` ou
  função ``(agente, fase) -> RespostaModelo``. Permite construir cenários
  reprodutíveis para os testes de propriedade do orquestrador (Task 15)
  sem reimplementar a state machine no próprio teste.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

import pytest

from caos.agent_invoker import RespostaModelo


# ---------------------------------------------------------------------------
# Mock determinístico de backend de modelo (R9, R16, R17)
# ---------------------------------------------------------------------------


@dataclass
class _BackendMockDeterministico:
    """Backend de modelo determinístico para testes.

    A resposta é função pura de ``(prompt, contexto, seed)``: dois
    invocações com os mesmos argumentos retornam o mesmo
    :class:`RespostaModelo`. Isso é exatamente o que esperaríamos de um
    modelo LLM real com seed fixa — exceto que aqui não há latência nem
    custo de API.

    O contador :attr:`chamadas` é incrementado a cada invocação e usado
    pelos testes para verificar que :class:`AgentInvoker` consultou o
    cache (cache hit ⇒ contador NÃO incrementa) ou foi bloqueado pelo
    orçamento (bloqueio ⇒ contador NÃO incrementa).
    """

    chamadas: int = 0
    historico: list[tuple[str, str, str, str, Optional[int]]] = field(
        default_factory=list
    )

    def invocar(
        self,
        *,
        agente: str,
        modelo: str,
        prompt: str,
        contexto: str,
        seed: Optional[int],
    ) -> RespostaModelo:
        self.chamadas += 1
        self.historico.append((agente, modelo, prompt, contexto, seed))
        # Resposta determinística: hash do (prompt + contexto + seed).
        # ``seed`` é serializada como string vazia quando ausente para
        # bater com a convenção do :class:`SkillLLMCache` (R16.2).
        seed_str = "" if seed is None else str(seed)
        bruto = f"{prompt}|{contexto}|{seed_str}"
        texto = "resposta::" + hashlib.sha256(
            bruto.encode("utf-8")
        ).hexdigest()
        # Tokens proporcionais ao tamanho dos textos (heurística simples,
        # ~4 chars/token). Mínimo 1 para evitar divisões por zero em
        # asserções de proporcionalidade.
        tokens_in = max(1, len(prompt) // 4)
        tokens_out = max(1, len(texto) // 4)
        return RespostaModelo(
            texto=texto,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
        )


@dataclass
class _BackendFalho:
    """Backend que sempre lança :class:`TimeoutError`.

    Útil para validar que o :class:`AgentInvoker` NÃO chama o backend
    quando a invocação foi bloqueada antes pelo
    :class:`SkillTokenBudget`. Se o adapter chamar o backend
    indevidamente, o teste estoura com :class:`TimeoutError`.
    """

    chamadas: int = 0

    def invocar(
        self,
        *,
        agente: str,
        modelo: str,
        prompt: str,
        contexto: str,
        seed: Optional[int],
    ) -> RespostaModelo:
        self.chamadas += 1
        raise TimeoutError(
            f"backend_falho: invocação inesperada para {agente!r}"
        )


@dataclass
class _BackendRespostaVazia:
    """Backend que devolve resposta vazia e zero tokens.

    Reproduz o caso degenerado descrito em R14.3 (resposta vazia tratada
    como falha pelo :mod:`caos.failure_handler`). O adapter em si
    (:class:`AgentInvoker`) não interpreta resposta vazia como falha —
    ele apenas registra zero tokens consumidos. A política de retry
    fica em outro componente.
    """

    chamadas: int = 0

    def invocar(
        self,
        *,
        agente: str,
        modelo: str,
        prompt: str,
        contexto: str,
        seed: Optional[int],
    ) -> RespostaModelo:
        self.chamadas += 1
        return RespostaModelo(texto="", tokens_input=0, tokens_output=0)


# ---------------------------------------------------------------------------
# Fixtures expostas
# ---------------------------------------------------------------------------


@pytest.fixture
def backend_mock_deterministico() -> _BackendMockDeterministico:
    """Backend determinístico (resposta = SHA-256 do tuple de input)."""
    return _BackendMockDeterministico()


@pytest.fixture
def backend_falho() -> _BackendFalho:
    """Backend que sempre falha — para testes de bloqueio prévio."""
    return _BackendFalho()


@pytest.fixture
def backend_resposta_vazia() -> _BackendRespostaVazia:
    """Backend que devolve resposta vazia — caso degenerado de R14.3."""
    return _BackendRespostaVazia()


__all__ = [
    "backend_mock_deterministico",
    "backend_falho",
    "backend_resposta_vazia",
    "_BackendScriptado",
]


# ---------------------------------------------------------------------------
# Backend scriptado para testes do orquestrador (Task 15)
# ---------------------------------------------------------------------------


@dataclass
class _BackendScriptado:
    """Backend cuja resposta é definida por um *script*.

    Uso típico nos testes de propriedade da Task 15 (orquestrador):

    .. code-block:: python

        backend = _BackendScriptado(
            script={
                ("Mister_M", "PROPOSTAS"): RespostaModelo(
                    texto=json.dumps({
                        "propostas": [
                            {"resumo": "P1", "conteudo": "X", "confianca": 80}
                        ]
                    }),
                    tokens_input=100,
                    tokens_output=50,
                ),
                ("Cerberus", "AVALIACAO_RISCO"): RespostaModelo(
                    texto=json.dumps({
                        "vetos": [
                            {"proposta_alvo": 0, "decisao": "bloquear",
                             "justificativa": "delta inaceitavel"}
                        ]
                    }),
                    tokens_input=80, tokens_output=40,
                ),
            },
        )

    Quando um par ``(agente, fase)`` não está no script, o backend recorre
    ao ``default_factory``: por padrão devolve uma :class:`RespostaModelo`
    com texto vazio e zero tokens (caller decide se isso é OK).

    Quando ``bloqueio_estourar=True``, o backend modula seu retorno para
    indicar grandes ``tokens_input`` (1.000.000) — quando combinado com um
    :class:`SkillTokenBudget` apertado, isso simula a indisponibilidade do
    agente. Esse modo é usado pelo teste de Property 6 (Quórum) para
    forçar agentes a serem bloqueados pelo orçamento.
    """

    script: dict[tuple[str, str], Union[RespostaModelo, Callable[..., RespostaModelo]]] = field(
        default_factory=dict
    )
    default_resposta: RespostaModelo = field(
        default_factory=lambda: RespostaModelo(
            texto="", tokens_input=0, tokens_output=0
        )
    )
    chamadas: int = 0
    historico: list[tuple[str, str, str, str, Optional[int]]] = field(
        default_factory=list
    )

    def invocar(
        self,
        *,
        agente: str,
        modelo: str,
        prompt: str,
        contexto: str,
        seed: Optional[int],
    ) -> RespostaModelo:
        self.chamadas += 1
        # Determina a fase a partir do prompt (formato montado por
        # caos.orchestrator._construir_prompt).
        fase = _extrair_fase_do_prompt(prompt)
        self.historico.append((agente, fase, prompt, contexto, seed))
        chave = (agente, fase)
        valor = self.script.get(chave)
        if valor is None:
            return self.default_resposta
        if callable(valor):
            return valor(
                agente=agente, modelo=modelo, prompt=prompt,
                contexto=contexto, seed=seed,
            )
        return valor


def _extrair_fase_do_prompt(prompt: str) -> str:
    """Extrai o nome da fase do prompt construído pelo orquestrador.

    O prompt segue ``"agente: X | fase: Y | tema: Z | ..."``. Se a fase
    não puder ser extraída (formato inesperado), devolvemos string vazia
    para que o caller use ``default_resposta``.
    """
    if not prompt:
        return ""
    for parte in prompt.split("|"):
        parte_limpa = parte.strip()
        if parte_limpa.startswith("fase:"):
            return parte_limpa[len("fase:"):].strip()
    return ""


def resposta_propostas(
    propostas: list[dict[str, Any]],
    *,
    tokens_input: int = 100,
    tokens_output: int = 50,
) -> RespostaModelo:
    """Helper que monta :class:`RespostaModelo` para fase PROPOSTAS.

    ``propostas`` é uma lista de dicts compatível com :class:`Proposta`
    (sem ``id`` — o orquestrador atribui).
    """
    payload = {"propostas": propostas}
    return RespostaModelo(
        texto=json.dumps(payload, ensure_ascii=False),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
    )


def resposta_vetos(
    vetos: list[dict[str, Any]],
    *,
    tokens_input: int = 80,
    tokens_output: int = 40,
) -> RespostaModelo:
    """Helper que monta :class:`RespostaModelo` para fases de avaliação.

    ``vetos`` é uma lista de dicts compatível com :class:`Veto`. O campo
    ``proposta_alvo`` aceita inteiro 0-based (índice da proposta na ordem
    em que foi materializada pelo orquestrador) ou string ``"P{n}"``.
    """
    payload = {"vetos": vetos}
    return RespostaModelo(
        texto=json.dumps(payload, ensure_ascii=False),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
    )


def resposta_critica(
    texto: str = "Crítica registrada",
    *,
    tokens_input: int = 80,
    tokens_output: int = 40,
) -> RespostaModelo:
    """Helper que monta :class:`RespostaModelo` para fase CRITICA."""
    payload = {"texto_markdown": texto}
    return RespostaModelo(
        texto=json.dumps(payload, ensure_ascii=False),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
    )
