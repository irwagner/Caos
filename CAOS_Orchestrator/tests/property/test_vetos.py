"""Property 4 — Risk Veto Soundness; Property 5 — Technical Veto Soundness.

**Validates: Requirements 5.3, 5.5, 6.2, 6.5, 6.6**

- Property 4: Nenhuma proposta com ``Veto_De_Risco.decisao == "bloquear"``
  resulta em ``decisao_final.proposta_aceita == essa_proposta`` em
  qualquer Decisao_Do_Conselho concluída (R5.3, R5.5).
- Property 5: Nenhuma proposta com ``Veto_Tecnico`` é selecionada como
  ``decisao_final.proposta_aceita`` (R6.2, R6.5, R6.6) — proposta
  bloqueada por veto técnico jamais transita para Aceita.

Estratégia:

1. Construímos um Debate com tema que ativa AVALIACAO_RISCO e
   AVALIACAO_TECNICA simultaneamente.
2. Variamos:

   - ``n_propostas`` em [2, 4]: número de propostas geradas.
   - ``cerberus_bloqueia_indice`` em [None, 0..3]: índice da proposta
     vetada por Cerberus (None significa sem veto de risco).
   - ``hermes_bloqueia_indice`` análogo para Hermes.

3. Asserções:

   - Property 4: se cerberus bloqueou uma proposta, ela não é a aceita.
   - Property 5: se hermes bloqueou uma proposta, ela não é a aceita.
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
    resposta_vetos,
)

# ---------------------------------------------------------------------------
# Construção de perfis em memória (mesma de test_quorum_e_orcamento)
# ---------------------------------------------------------------------------


_FORMATO_PADRAO = FormatoDeSaida(
    secoes_obrigatorias=["Proposta", "Justificativa", "Riscos", "Confianca"],
)
_SYSTEM_PROMPT_MIN = (
    "Identidade mínima do agente para os testes de propriedade do orquestrador."
)


def _perfil(
    nome: str, modelo: str, tags: list[str], skills: list[str], escopo: list[str]
) -> AgentProfile:
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
    return {
        "Athena": _perfil(
            "Athena", "claude-opus-4.7", ["orquestracao"], [], ["sintese_final"],
        ),
        "Odin": _perfil(
            "Odin", "claude-sonnet-4.5", ["order-flow"], [], ["proposta_estrategia"],
        ),
        "Mister_M": _perfil(
            "Mister_M", "minimax-m2", ["fimathe"], [], ["proposta_estrategia"],
        ),
        "Manolo": _perfil(
            "Manolo", "claude-haiku-4.5", ["htf"], [], ["proposta_contexto"],
        ),
        "Rodrigo": _perfil(
            "Rodrigo", "deepseek-v3.1", ["acelerador"], [], ["ajuste_agressividade"],
        ),
        "Cerberus": _perfil(
            "Cerberus", "claude-sonnet-4.5", ["risco"], [], ["veto_de_risco"],
        ),
        "Hermes": _perfil(
            "Hermes", "qwen3-coder", ["csharp"], [], ["veto_tecnico"],
        ),
        "Explorador": _perfil(
            "Explorador", "claude-sonnet-4.5", ["r-and-d"], [], ["proposta_paper"],
        ),
        "Devils_Advocate": _perfil(
            "Devils_Advocate", "minimax-m2", ["critica"], [], ["critica_sistematica"],
        ),
    }


def _proponentes_em_ordem() -> list[str]:
    perfis = _construir_perfis()
    return sorted(n for n in perfis if n not in AGENTES_NAO_PROPONENTES)


def _montar_invoker(tmp_path: Path, backend: object) -> AgentInvoker:
    cache = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
    budget = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
    return AgentInvoker(
        backend=backend,  # type: ignore[arg-type]
        cache=cache,
        token_budget=budget,
    )


def _proposta_dict(autor: str, indice: int, confianca: int) -> dict:
    return {
        "autor": autor,
        "resumo": f"proposta de {autor} (#{indice})",
        "conteudo": f"conteudo {indice}",
        "confianca": confianca,
    }


# ---------------------------------------------------------------------------
# Property 4 + 5
# ---------------------------------------------------------------------------


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_propostas=st.integers(min_value=2, max_value=4),
    cerberus_bloqueia_indice=st.one_of(
        st.none(), st.integers(min_value=0, max_value=3)
    ),
    hermes_bloqueia_indice=st.one_of(
        st.none(), st.integers(min_value=0, max_value=3)
    ),
)
def test_property_vetos(
    n_propostas: int,
    cerberus_bloqueia_indice: Optional[int],
    hermes_bloqueia_indice: Optional[int],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 5.3, 5.5, 6.2, 6.5, 6.6** (Properties 4 e 5).

    Para qualquer combinação de vetos bloqueantes emitidos por Cerberus
    (Property 4) ou Hermes (Property 5), a proposta-alvo do veto NUNCA
    aparece como ``decisao_final.proposta_aceita``.
    """
    raiz = tmp_path_factory.mktemp("vetos")

    # Saneamento: índices fora do range de propostas são equivalentes a
    # "sem veto" — eles serão descartados pela materialização do Veto.
    def _normalizar(idx: Optional[int]) -> Optional[int]:
        if idx is None or idx >= n_propostas:
            return None
        return idx

    cb_idx = _normalizar(cerberus_bloqueia_indice)
    hm_idx = _normalizar(hermes_bloqueia_indice)

    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()

    # Cada proponente (até n_propostas) emite 1 proposta. Confiança
    # deliberadamente uniforme (50) para que a desempate fique
    # determinístico via ordem alfabética do autor.
    script: dict = {}
    for i, nome in enumerate(proponentes):
        if i < n_propostas:
            script[(nome, "PROPOSTAS")] = resposta_propostas(
                [_proposta_dict(nome, i + 1, confianca=50)],
            )
        else:
            script[(nome, "PROPOSTAS")] = RespostaModelo(
                texto="", tokens_input=5, tokens_output=5
            )
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()

    # Vetos: Cerberus emite veto_de_risco bloqueando proposta cb_idx;
    # Hermes emite veto_tecnico bloqueando proposta hm_idx.
    if cb_idx is not None:
        script[("Cerberus", "AVALIACAO_RISCO")] = resposta_vetos(
            [
                {
                    "proposta_alvo": cb_idx,
                    "decisao": "bloquear",
                    "tipo": "veto_de_risco",
                    "justificativa": (
                        f"delta de exposição inaceitável na proposta "
                        f"P{cb_idx + 1}"
                    ),
                }
            ],
        )
    else:
        script[("Cerberus", "AVALIACAO_RISCO")] = RespostaModelo(
            texto="", tokens_input=5, tokens_output=5
        )

    if hm_idx is not None:
        script[("Hermes", "AVALIACAO_TECNICA")] = resposta_vetos(
            [
                {
                    "proposta_alvo": hm_idx,
                    "decisao": "bloquear",
                    "tipo": "veto_tecnico",
                    "categoria_tecnica": "compilacao_falhou",
                    "justificativa": (
                        f"compilação MSBuild falhou na proposta P{hm_idx + 1}"
                    ),
                }
            ],
        )
    else:
        script[("Hermes", "AVALIACAO_TECNICA")] = RespostaModelo(
            texto="", tokens_input=5, tokens_output=5
        )

    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(raiz, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(
        titulo="tema-vetos",
        descricao="teste de vetos",
        tags=(),
        requer_csharp=True,
        altera_exposicao=True,
    )
    cfg = ConfiguracaoDebate(orcamento_de_turnos=20)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    # Sem decisão (timeout, sem-quorum, etc.) → propriedade trivialmente
    # satisfeita.
    if resultado.decisao is None:
        return

    proposta_aceita = resultado.decisao.decisao_final.proposta_aceita

    # ---------- Property 4 ----------
    if cb_idx is not None:
        id_bloqueada = f"P{cb_idx + 1}"
        assert proposta_aceita != id_bloqueada, (
            f"violação Property 4: proposta {id_bloqueada} foi vetada por "
            f"Cerberus mas aparece como proposta_aceita; "
            f"vetos={[v.model_dump() for v in resultado.decisao.vetos]}"
        )

    # ---------- Property 5 ----------
    if hm_idx is not None:
        id_bloqueada = f"P{hm_idx + 1}"
        assert proposta_aceita != id_bloqueada, (
            f"violação Property 5: proposta {id_bloqueada} foi vetada por "
            f"Hermes mas aparece como proposta_aceita; "
            f"vetos={[v.model_dump() for v in resultado.decisao.vetos]}"
        )


# ---------------------------------------------------------------------------
# Casos unitários determinísticos (smoke tests)
# ---------------------------------------------------------------------------


def test_veto_risco_bloqueia_unica_proposta_resulta_pendente(
    tmp_path: Path,
) -> None:
    """Com 2 propostas onde Cerberus bloqueia ambas, decisão fica pendente."""
    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()
    script: dict = {}
    for i, nome in enumerate(proponentes):
        if i < 2:
            script[(nome, "PROPOSTAS")] = resposta_propostas(
                [_proposta_dict(nome, i + 1, confianca=50)]
            )
        else:
            script[(nome, "PROPOSTAS")] = RespostaModelo(
                texto="", tokens_input=5, tokens_output=5
            )
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()
    script[("Cerberus", "AVALIACAO_RISCO")] = resposta_vetos(
        [
            {"proposta_alvo": 0, "decisao": "bloquear", "tipo": "veto_de_risco",
             "justificativa": "x"},
            {"proposta_alvo": 1, "decisao": "bloquear", "tipo": "veto_de_risco",
             "justificativa": "y"},
        ]
    )
    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(tmp_path, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(
        titulo="todas-bloqueadas", descricao="x", tags=(),
        altera_exposicao=True,
    )
    cfg = ConfiguracaoDebate(orcamento_de_turnos=20)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    assert resultado.motivo_encerramento == "pendente-usuario"
    assert resultado.decisao is not None
    assert resultado.decisao.decisao_final.proposta_aceita is None


def test_veto_risco_aprovar_com_ressalvas_nao_bloqueia(tmp_path: Path) -> None:
    """Veto de risco com 'aprovar-com-ressalvas' não rejeita a proposta."""
    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()
    script: dict = {}
    for i, nome in enumerate(proponentes):
        if i < 2:
            script[(nome, "PROPOSTAS")] = resposta_propostas(
                [_proposta_dict(nome, i + 1, confianca=80 - i)]
            )
        else:
            script[(nome, "PROPOSTAS")] = RespostaModelo(
                texto="", tokens_input=5, tokens_output=5
            )
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()
    script[("Cerberus", "AVALIACAO_RISCO")] = resposta_vetos(
        [
            {
                "proposta_alvo": 0,
                "decisao": "aprovar-com-ressalvas",
                "tipo": "veto_de_risco",
                "justificativa": "aceitável",
            }
        ]
    )
    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(tmp_path, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(
        titulo="ressalvas", descricao="x", tags=(), altera_exposicao=True,
    )
    cfg = ConfiguracaoDebate(orcamento_de_turnos=20)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    assert resultado.motivo_encerramento == "concluido"
    assert resultado.decisao is not None
    assert resultado.decisao.decisao_final.proposta_aceita == "P1"


def test_veto_tecnico_bloqueia_proposta(tmp_path: Path) -> None:
    """Veto técnico bloqueante remove a proposta da seleção.

    Usa 3 propostas para que, com 1 bloqueada, o limiar de consenso 2/3
    (ceil(2/3 * 3) = 2) ainda seja satisfeito por 2 propostas elegíveis.
    """
    perfis = _construir_perfis()
    proponentes = _proponentes_em_ordem()
    script: dict = {}
    for i, nome in enumerate(proponentes):
        if i < 3:
            script[(nome, "PROPOSTAS")] = resposta_propostas(
                [_proposta_dict(nome, i + 1, confianca=80 - i)]
            )
        else:
            script[(nome, "PROPOSTAS")] = RespostaModelo(
                texto="", tokens_input=5, tokens_output=5
            )
    script[("Devils_Advocate", "CRITICA")] = resposta_critica()
    script[("Hermes", "AVALIACAO_TECNICA")] = resposta_vetos(
        [
            {
                "proposta_alvo": 0,
                "decisao": "bloquear",
                "tipo": "veto_tecnico",
                "categoria_tecnica": "compilacao_falhou",
                "justificativa": "MSBuild falhou",
            }
        ]
    )
    backend = _BackendScriptado(script=script)
    invoker = _montar_invoker(tmp_path, backend)
    orchestrator = Orchestrator(perfis=perfis, agent_invoker=invoker)

    tema = TemaDebate(
        titulo="veto-tecnico", descricao="x", tags=(), requer_csharp=True,
    )
    cfg = ConfiguracaoDebate(orcamento_de_turnos=20)
    resultado = orchestrator.iniciar_debate(tema, configuracao=cfg)

    assert resultado.motivo_encerramento == "concluido"
    assert resultado.decisao is not None
    assert resultado.decisao.decisao_final.proposta_aceita != "P1"
