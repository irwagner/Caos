"""Property 6 — Quórum Enforcement; Property 7 — Turn Budget Enforcement.

**Validates: Requirements 4.3, 7.1, 7.2, 7.5**

- Property 6: Nenhum Debate avança para a fase ``CRITICA`` com menos de 2
  propostas válidas (R4.3). O orquestrador deve marcar a Decisao_Do_Conselho
  como ``sem-quorum`` quando essa condição é violada.
- Property 7: Para todo Debate, ``debate.turnos_consumidos <=
  orcamento_de_turnos`` (R7.1, R7.2, R7.5).

Estratégia:

1. Construímos os 9 perfis em memória (sem depender do disco).
2. Variamos ``n_proponentes_disponiveis`` (0..5) — número de proponentes
   que efetivamente emitem proposta válida. Os 5 proponentes do Conselho
   são Explorador, Manolo, Mister_M, Odin e Rodrigo.
3. Variamos ``orcamento`` em [4, 30].
4. Asserções:

   a. Property 7 sempre: ``turnos_consumidos <= orcamento``.
   b. Property 6 condicional ao motivo de encerramento:

      - Se ``motivo == "timeout"`` (orçamento esgotado durante PROPOSTAS),
        a quórum-check ainda pode não ter sido alcançada → não há decisão
        a fazer aqui sobre quórum.
      - Caso contrário:

        * Se ``decisao`` é ``None`` → orchestrador identificou
          ``sem-quorum`` corretamente; o número de propostas válidas que
          efetivamente foram colhidas é < 2.
        * Se ``decisao`` não é ``None`` → orchestrador colheu >= 2
          propostas válidas e seguiu para CRITICA.

Observação: a definição operacional de "proposta válida" é "proposta
materializada em :class:`Proposta` pelo orquestrador". Quando o backend
devolve resposta sem o campo ``propostas``, o orquestrador emite turno
mas não cria proposta; a quórum-check leva isso em conta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.agent_invoker import AgentInvoker, RespostaModelo
from caos.models import AgentProfile, FormatoDeSaida
from caos.orchestrator import (
    AGENTES_NAO_PROPONENTES,
    ConfiguracaoDebate,
    Orchestrator,
    TemaDebate,
)
from caos.skills.llm_cache import SkillLLMCache
from caos.skills.token_budget import SkillTokenBudget

from tests.conftest import (  # type: ignore[import-not-found]
    _BackendScriptado,
    resposta_critica,
    resposta_propostas,
)

# ---------------------------------------------------------------------------
# Construção de perfis em memória
# ---------------------------------------------------------------------------


_FORMATO_PADRAO = FormatoDeSaida(
    secoes_obrigatorias=["Proposta", "Justificativa", "Riscos", "Confianca"],
)

_SYSTEM_PROMPT_MIN = (
    "Identidade mínima do agente para os testes de propriedade do "
    "orquestrador. Conteúdo deliberadamente curto."
)


def _perfil(
    nome: str, modelo: str, tags: list[str], skills: list[str], escopo: list[str]
) -> AgentProfile:
    """Constrói um :class:`AgentProfile` mínimo válido."""
    return AgentProfile(
        nome=nome,  # type: ignore[arg-type]
        modelo=modelo,  # type: ignore[arg-type]
        tags_especialidade=tags,
        skills_permitidas=skills,  # type: ignore[arg-type]
        escopo_de_decisao=escopo,
        formato_de_saida=_FORMATO_PADRAO,
        system_prompt=_SYSTEM_PROMPT_MIN,
    )


def _construir_perfis() -> dict[str, AgentProfile]:
    """Cria os 9 perfis canônicos para testes."""
    return {
        "Athena": _perfil(
            "Athena", "claude-opus-4.7",
            ["orquestracao"], [], ["sintese_final"],
        ),
        "Odin": _perfil(
            "Odin", "claude-sonnet-4.5",
            ["order-flow"], [], ["proposta_estrategia"],
        ),
        "Mister_M": _perfil(
            "Mister_M", "minimax-m2",
            ["fimathe"], [], ["proposta_estrategia"],
        ),
        "Manolo": _perfil(
            "Manolo", "claude-haiku-4.5",
            ["htf"], [], ["proposta_contexto"],
        ),
        "Rodrigo": _perfil(
            "Rodrigo", "deepseek-v3.1",
            ["acelerador"], [], ["ajuste_agressividade"],
        ),
        "Cerberus": _perfil(
            "Cerberus", "claude-sonnet-4.5",
            ["risco"], [], ["veto_de_risco"],
        ),
        "Hermes": _perfil(
            "Hermes", "qwen3-coder",
            ["csharp"], [], ["veto_tecnico"],
        ),
        "Explorador": _perfil(
            "Explorador", "claude-sonnet-4.5",
            ["r-and-d"], [], ["proposta_paper"],
        ),
        "Devils_Advocate": _perfil(
            "Devils_Advocate", "minimax-m2",
            ["critica"], [], ["critica_sistematica"],
        ),
    }


def _proponentes_em_ordem() -> list[str]:
    """Lista os proponentes em ordem alfabética (a mesma usada pelo orchestrator)."""
    perfis = _construir_perfis()
    nomes = sorted(
        n for n in perfis if n not in AGENTES_NAO_PROPONENTES
    )
    return nomes


# ---------------------------------------------------------------------------
# Helpers de montagem do AgentInvoker
# ---------------------------------------------------------------------------


def _montar_invoker(
    tmp_path: Path, backend: object
) -> AgentInvoker:
    """Cria :class:`AgentInvoker` com Skills sobre ``tmp_path``."""
    cache = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
    budget = SkillTokenBudget(
        diretorio_budget=tmp_path / ".budget",
    )
    return AgentInvoker(
        backend=backend,  # type: ignore[arg-type]
        cache=cache,
        token_budget=budget,
    )


def _proposta_dict(
    autor: str, indice: int, confianca: int = 60
) -> dict:
    """Constrói um dict compatível com :class:`Proposta` (sem id)."""
    return {
        "autor": autor,
        "resumo": f"proposta de {autor} (#{indice})",
        "conteudo": f"conteudo da proposta {indice} de {autor}",
        "confianca": confianca,
    }


# ---------------------------------------------------------------------------
# Property 6 e 7
# ---------------------------------------------------------------------------


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_proponentes_disponiveis=st.integers(min_value=0, max_value=5),
    orcamento=st.integers(min_value=4, max_value=30),
)
def test_property_quorum_e_orcamento(
    n_proponentes_disponiveis: int,
    orcamento: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 4.3, 7.1, 7.2, 7.5** (Properties 6 e 7).

    - Property 7: ``turnos_consumidos <= orcamento`` em qualquer Debate.
    - Property 6: orchestrator emite ``sem-quorum`` quando, sem timeout
      antes do fim de PROPOSTAS, há menos de 2 propostas válidas; e NÃO
      emite ``sem-quorum`` quando há ao menos 2.
    """
    raiz = tmp_path_factory.mktemp("debate")
    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()

    # Backend: primeiros N proponentes emitem proposta; os demais devolvem
    # resposta vazia (não geram proposta válida).
    script: dict = {}
    for i, nome in enumerate(proponentes):
        if i < n_proponentes_disponiveis:
            script[(nome, "PROPOSTAS")] = resposta_propostas(
                [_proposta_dict(nome, i + 1, confianca=70)],
                tokens_input=10,
                tokens_output=10,
            )
        else:
            # Resposta vazia: o orquestrador consome 1 turno mas NÃO
            # materializa proposta para esse agente.
            script[(nome, "PROPOSTAS")] = RespostaModelo(
                texto="", tokens_input=10, tokens_output=10
            )
    # CRITICA do Devils_Advocate (resposta neutra).
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()

    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(raiz, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(
        titulo="tema-quorum-orcamento",
        descricao="teste de propriedade",
        tags=(),
        requer_csharp=False,
        altera_exposicao=False,
    )
    cfg = ConfiguracaoDebate(orcamento_de_turnos=orcamento)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    # ---------- Property 7 (R7.1, R7.2, R7.5): orçamento de turnos ----------
    assert resultado.debate.turnos_consumidos <= cfg.orcamento_de_turnos, (
        "violação Property 7: "
        f"turnos_consumidos={resultado.debate.turnos_consumidos} > "
        f"orcamento_de_turnos={cfg.orcamento_de_turnos}"
    )

    # ---------- Property 6 (R4.3): quórum mínimo de 2 propostas ----------
    motivo = resultado.motivo_encerramento
    if motivo == "timeout":
        # TIMEOUT pode ter ocorrido durante PROPOSTAS antes do check de
        # quórum — não há violação a verificar para Property 6 nesse caso.
        return

    if resultado.decisao is None:
        # Sem decisão e sem timeout → tem que ser sem-quorum (R4.3).
        assert motivo == "sem-quorum", (
            "violação Property 6: decisao=None mas motivo "
            f"!= 'sem-quorum' (motivo={motivo!r})"
        )
    else:
        # Há decisão → deve haver >= 2 propostas (R4.3).
        n_propostas = len(resultado.decisao.propostas)
        assert n_propostas >= 2, (
            "violação Property 6: decisao com "
            f"{n_propostas} proposta(s) mas avançou além de PROPOSTAS"
        )
        assert motivo != "sem-quorum"


# ---------------------------------------------------------------------------
# Casos unitários determinísticos (smoke tests)
# ---------------------------------------------------------------------------


def test_orcamento_4_com_5_proponentes_dispara_timeout(
    tmp_path: Path,
) -> None:
    """Com 5 proponentes e orçamento 4, orchestrator atinge TIMEOUT."""
    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()
    script = {
        (nome, "PROPOSTAS"): resposta_propostas(
            [_proposta_dict(nome, i + 1)]
        )
        for i, nome in enumerate(proponentes)
    }
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()
    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(tmp_path, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(
        titulo="tema-budget-pequeno",
        descricao="teste",
        tags=(),
    )
    cfg = ConfiguracaoDebate(orcamento_de_turnos=4)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    assert resultado.motivo_encerramento == "timeout"
    assert resultado.debate.turnos_consumidos == 4


def test_zero_proponentes_dispara_sem_quorum(tmp_path: Path) -> None:
    """0 propostas → SEM_QUORUM, sem decisao, motivo correto."""
    perfis = _construir_perfis()
    backend = _BackendScriptado()  # tudo default → respostas vazias
    invoker = _montar_invoker(tmp_path, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(titulo="tema-vazio", descricao="teste", tags=())
    cfg = ConfiguracaoDebate(orcamento_de_turnos=12)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    assert resultado.motivo_encerramento == "sem-quorum"
    assert resultado.decisao is None
    assert resultado.fase_final == "SEM_QUORUM"


def test_dois_proponentes_avancam_alem_de_propostas(tmp_path: Path) -> None:
    """Com >=2 propostas, orchestrator não emite sem-quorum."""
    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()
    script = {}
    for i, nome in enumerate(proponentes):
        if i < 2:
            script[(nome, "PROPOSTAS")] = resposta_propostas(
                [_proposta_dict(nome, i + 1)]
            )
        else:
            script[(nome, "PROPOSTAS")] = RespostaModelo(
                texto="", tokens_input=5, tokens_output=5
            )
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()
    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(tmp_path, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(titulo="tema-quorum-ok", descricao="teste", tags=())
    cfg = ConfiguracaoDebate(orcamento_de_turnos=12)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    assert resultado.motivo_encerramento != "sem-quorum"
    assert resultado.decisao is not None
    assert len(resultado.decisao.propostas) >= 2
