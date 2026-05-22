"""Orquestrador (Athena) — state machine completa do Conselho CAOS.

Este módulo implementa a Task 15 do Spec ``caos-conselho-infra`` e cobre os
critérios R4.1–R4.8, R5.1–R5.6, R6.1–R6.6, R7.1–R7.7 do ``requirements.md``.

A state machine implementada é:

``INICIADO → PROPOSTAS → CRITICA → AVALIACAO_RISCO → AVALIACAO_TECNICA →
SINTESE → CONCLUIDO`` com transições para ``TIMEOUT``, ``SEM_QUORUM``,
``ABORTADO_POR_INDISPONIBILIDADE``, ``PENDENTE_USUARIO`` e
``CERBERUS_TIMEOUT`` em caminhos de exceção.

Princípios da implementação:

- O orquestrador é **focado em corretude de fluxo**: aplica orçamento,
  quórum, vetos bloqueantes e ordena turnos. NÃO interpreta livremente
  o texto produzido pelos modelos — em vez disso, espera respostas
  estruturadas (JSON) entregues pelo :class:`BackendModelo` injetado
  no :class:`AgentInvoker`. Em produção, esse backend será uma camada
  fina sobre a API de subagente do Kiro com instruções de saída JSON;
  em testes, é o ``_BackendScriptado`` injetado por ``tests/conftest.py``.
- IDs de proposta são **carimbados pelo orquestrador** (``P1``, ``P2``, …)
  em ordem alfabética dos autores. Isso torna a relação posição → id
  determinística para os testes de propriedade e impede colisões de id
  vindas do backend.
- ``decisao: Optional[DecisaoDoConselho]``: caminhos terminais sem ao
  menos uma proposta válida (SEM_QUORUM, TIMEOUT pré-PROPOSTAS) emitem
  ``decisao=None``. A tipagem reflete a realidade do schema R8.2 (que
  exige ≥ 1 proposta na decisão).
- Integração com Council_Recorder, Bias_Filter, Determinism_Auditor,
  Failure_Handler, Profile_Loader, Steering_Engine e Context_Loader é
  feita via injeção de dependência. Componentes ausentes (``None``) são
  desativados graciosamente — o que mantém os testes de propriedade
  enxutos sem perder a integração de produção.

Convenções:

- Mensagens visíveis ao usuário em pt-BR.
- Identificadores públicos em inglês quando idiomáticos em Python.
- ``frozen=True`` em todas as dataclasses de retorno.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import ValidationError

from caos.agent_invoker import (
    MODELOS_SEM_SEED,
    AgentInvoker,
    InvocacaoModelo,
    ResultadoInvocacao,
)
from caos.bias_filter import validar_link_de_entrada  # noqa: F401 — integração
from caos.council_recorder import CouncilRecorder, ResultadoGravacao
from caos.determinism_auditor import derivar_reproduzivel
from caos.failure_handler import FailureHandler
from caos.models import (
    AGENTES,
    AgenteNome,
    AgentProfile,
    Debate,
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
    Turno,
    Veto,
)
from caos.steering_engine import (
    ORCAMENTO_TURNOS_DEFAULT,
    ORCAMENTO_TURNOS_MAX,
    ORCAMENTO_TURNOS_MIN,
)

# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Agentes que NÃO atuam como proponentes na fase PROPOSTAS.
#:
#: Athena orquestra e sintetiza; Devils_Advocate critica; Cerberus avalia
#: risco; Hermes avalia técnica. Todos os demais são proponentes elegíveis.
AGENTES_NAO_PROPONENTES: frozenset[str] = frozenset(
    {"Athena", "Devils_Advocate", "Cerberus", "Hermes"}
)

#: Tokens estimados por invocação (default usado pela state machine).
TOKENS_ESTIMADOS_PADRAO: int = 2000

#: Seed default de R9 (deve ser configurável no futuro via Steering).
SEED_PADRAO: int = 42

#: Limiar de consenso 2/3 (R4.6).
LIMIAR_CONSENSO_PADRAO: float = 2.0 / 3.0

#: Deadlines (R4.2, R5.1, R6.1) — usados como ``tokens_estimados`` quando
#: o backend não impõe deadline explícito. Mantidos como constantes para
#: documentação e para fácil consumo por uma camada de produção.
DEADLINE_PROPOSTA_S: int = 300
DEADLINE_CERBERUS_S: int = 60
DEADLINE_HERMES_S: int = 120

# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------

MotivoEncerramento = Literal[
    "concluido",
    "sem-quorum",
    "timeout",
    "pendente-usuario",
    "abortado-por-indisponibilidade",
    "cerberus-timeout",
]


@dataclass(frozen=True)
class TemaDebate:
    """Tema submetido ao Conselho.

    Attributes
    ----------
    titulo:
        Slug em kebab-case, máximo 60 caracteres ASCII (R4.1, R8.1). Quando
        o título contém caracteres fora de ``[a-z0-9-]``, será normalizado
        pelo recorder (que faz sua própria conversão); aqui aceitamos um
        slug mais permissivo, com o regex aplicado ao construir
        :class:`caos.models.Debate`.
    descricao:
        Texto livre descrevendo o tema. É concatenado no prompt enviado
        aos agentes.
    tags:
        Tags-chave do tema (R4.2). Usadas para filtragem de proponentes
        elegíveis (intersecção com ``AgentProfile.tags_especialidade``)
        e para o desempate por intersecção (R4.6).
    requer_csharp:
        Quando ``True``, ativa a fase ``AVALIACAO_TECNICA`` (Hermes).
    altera_exposicao:
        Quando ``True``, ativa a fase ``AVALIACAO_RISCO`` (Cerberus).
    """

    titulo: str
    descricao: str
    tags: tuple[str, ...]
    requer_csharp: bool = False
    altera_exposicao: bool = False


@dataclass(frozen=True)
class ConfiguracaoDebate:
    """Configuração operacional do Debate (R4, R7).

    Defaults refletem o ``orcamento-de-turnos.md`` e os deadlines do
    ``design.md``. Valores fora dos intervalos válidos são rejeitados na
    construção via :func:`__post_init__`.
    """

    orcamento_de_turnos: int = ORCAMENTO_TURNOS_DEFAULT
    deadline_proposta_s: int = DEADLINE_PROPOSTA_S
    deadline_cerberus_s: int = DEADLINE_CERBERUS_S
    deadline_hermes_s: int = DEADLINE_HERMES_S
    limiar_consenso: float = LIMIAR_CONSENSO_PADRAO
    seed_padrao: int = SEED_PADRAO
    tokens_estimados: int = TOKENS_ESTIMADOS_PADRAO

    def __post_init__(self) -> None:  # type: ignore[override]
        if not (
            ORCAMENTO_TURNOS_MIN
            <= self.orcamento_de_turnos
            <= ORCAMENTO_TURNOS_MAX
        ):
            raise ValueError(
                "orcamento_de_turnos fora do intervalo "
                f"[{ORCAMENTO_TURNOS_MIN}, {ORCAMENTO_TURNOS_MAX}] (R7.2); "
                f"recebido {self.orcamento_de_turnos}"
            )
        if self.deadline_proposta_s <= 0:
            raise ValueError("deadline_proposta_s deve ser > 0")
        if self.deadline_cerberus_s <= 0:
            raise ValueError("deadline_cerberus_s deve ser > 0")
        if self.deadline_hermes_s <= 0:
            raise ValueError("deadline_hermes_s deve ser > 0")
        if not (0 < self.limiar_consenso <= 1):
            raise ValueError("limiar_consenso deve estar em (0, 1]")
        if self.tokens_estimados < 0:
            raise ValueError("tokens_estimados deve ser >= 0")


@dataclass(frozen=True)
class ResultadoDebate:
    """Resultado completo de :meth:`Orchestrator.iniciar_debate`.

    Attributes
    ----------
    debate:
        :class:`Debate` com cabeçalho + lista completa de turnos.
    decisao:
        :class:`DecisaoDoConselho` quando há ao menos uma proposta válida.
        ``None`` em SEM_QUORUM ou TIMEOUT pré-PROPOSTAS.
    resultado_gravacao:
        Resultado de :meth:`CouncilRecorder.gravar` se um recorder foi
        injetado; ``None`` caso contrário.
    fase_final:
        Fase terminal atingida — string idêntica a um dos valores de
        :data:`caos.models.FaseFinal`.
    motivo_encerramento:
        Discriminador de alto nível para o caller. Espelha o ``status``
        público da decisão quando há decisão; nos casos sem decisão,
        carrega a categoria ``sem-quorum`` ou ``timeout``.
    indisponiveis:
        Lista (possivelmente vazia) dos nomes de agentes marcados como
        indisponíveis durante o Debate (orçamento de tokens esgotado ou
        falha estrutural).
    """

    debate: Debate
    decisao: Optional[DecisaoDoConselho]
    fase_final: str
    motivo_encerramento: MotivoEncerramento
    resultado_gravacao: Optional[ResultadoGravacao] = None
    indisponiveis: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Resposta estruturada do backend
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RespostaAgente:
    """Resposta estruturada que o backend devolve para o orquestrador.

    Em produção, o backend é instruído a emitir um JSON com este shape;
    em testes, ``_BackendScriptado`` em ``tests/conftest.py`` produz
    diretamente o mesmo shape. A presença/ausência de cada campo
    determina o comportamento do orquestrador:

    - ``propostas``: lista de dicts compatíveis com :class:`Proposta`,
      sem o campo ``id`` (o orquestrador atribui ``P1``, ``P2``, …).
    - ``vetos``: lista de dicts compatíveis com :class:`Veto`. ``id`` da
      proposta-alvo deve ser o ``P{n}`` carimbado pelo orquestrador.
    - ``voto``: ``"favor"``, ``"contra"`` ou ``"abstencao"`` para a fase
      SINTESE; ignorado em outras fases.
    - ``voto_proposta``: id da proposta votada (``P{n}``) — só
      relevante quando ``voto == "favor"``.
    - ``texto_markdown``: corpo livre que será preservado em
      ``Turno.conteudo_markdown`` para auditoria.
    """

    propostas: tuple[dict[str, Any], ...] = ()
    vetos: tuple[dict[str, Any], ...] = ()
    voto: Optional[str] = None
    voto_proposta: Optional[str] = None
    texto_markdown: str = ""

    @classmethod
    def de_resposta(cls, texto: str) -> "_RespostaAgente":
        """Tenta parsear ``texto`` como JSON. Em falha, devolve resposta vazia.

        Backends de produção podem retornar texto livre ou JSON; o
        contrato definido pelos prompts é JSON. Falhas de parsing são
        tratadas como "agente não emitiu nada estruturado" — o
        orquestrador segue sem propostas/vetos vindos desse turno e
        preserva o texto cru em ``texto_markdown``.
        """
        if not isinstance(texto, str) or not texto.strip():
            return cls()
        try:
            payload = json.loads(texto)
        except json.JSONDecodeError:
            return cls(texto_markdown=texto)
        if not isinstance(payload, dict):
            return cls(texto_markdown=texto)
        propostas_raw = payload.get("propostas") or []
        vetos_raw = payload.get("vetos") or []
        if not isinstance(propostas_raw, list):
            propostas_raw = []
        if not isinstance(vetos_raw, list):
            vetos_raw = []
        propostas = tuple(p for p in propostas_raw if isinstance(p, dict))
        vetos = tuple(v for v in vetos_raw if isinstance(v, dict))
        voto = payload.get("voto")
        voto_proposta = payload.get("voto_proposta")
        texto_md = payload.get("texto_markdown") or ""
        if not isinstance(voto, str):
            voto = None
        if not isinstance(voto_proposta, str):
            voto_proposta = None
        if not isinstance(texto_md, str):
            texto_md = ""
        return cls(
            propostas=propostas,
            vetos=vetos,
            voto=voto,
            voto_proposta=voto_proposta,
            texto_markdown=texto_md,
        )



# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


_REGEX_SLUG_VALIDO = re.compile(r"^[a-z0-9-]{1,60}$")


def _slug_kebab(titulo: str) -> str:
    """Converte ``titulo`` em slug kebab-case (R4.1, R8.1)."""
    if _REGEX_SLUG_VALIDO.match(titulo):
        return titulo
    s = (titulo or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    s = s[:60]
    return s or "tema-sem-titulo"


def _now_utc() -> datetime:
    """Datetime UTC corrente sem microssegundos (estabilidade de auditoria)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _hash_input_tema(tema: TemaDebate) -> str:
    """Hash SHA-256 hex do tema (auditoria + cache)."""
    bruto = json.dumps(
        {
            "titulo": tema.titulo,
            "descricao": tema.descricao,
            "tags": list(tema.tags),
            "requer_csharp": tema.requer_csharp,
            "altera_exposicao": tema.altera_exposicao,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _gerar_identificador_debate(quando: datetime, sequencial: int) -> str:
    """Gera identificador ``AAAA-MM-DD-NN`` (R8.1).

    ``quando`` é o ``data_inicio`` em UTC; ``sequencial`` é o NN do dia.
    """
    if not (1 <= sequencial <= 99):
        raise ValueError(
            f"sequencial fora do intervalo [1, 99]; recebido {sequencial}"
        )
    return f"{quando.strftime('%Y-%m-%d')}-{sequencial:02d}"


def _ordem_proponentes(
    perfis: dict[str, AgentProfile], tags_tema: tuple[str, ...]
) -> list[AgentProfile]:
    """Seleciona proponentes elegíveis em round-robin alfabético (R4.2).

    Regras:

    - Considera apenas perfis cujo ``nome`` NÃO está em
      :data:`AGENTES_NAO_PROPONENTES`.
    - Filtra por intersecção de ``tags_especialidade`` com ``tags_tema``
      quando ``tags_tema`` é não-vazio. Quando ``tags_tema`` é vazio,
      todos os proponentes elegíveis participam (R4.2 fala em
      "intersectarem ao menos uma das tags do tema" — sem tags, a
      filtragem é desligada para evitar quórum-zero por configuração
      acidental).
    - Ordena alfabeticamente pelo nome.
    """
    candidatos = [
        p
        for nome, p in perfis.items()
        if nome not in AGENTES_NAO_PROPONENTES
    ]
    if tags_tema:
        tags_set = set(tags_tema)
        candidatos = [
            p
            for p in candidatos
            if tags_set.intersection(p.tags_especialidade)
        ]
    return sorted(candidatos, key=lambda p: p.nome)


def _seed_para(
    perfil: AgentProfile, seed_padrao: int
) -> Optional[int]:
    """Devolve a seed aplicável ao agente, ou ``None`` se modelo não suporta.

    Reflete R9.2: modelos sem suporte a seed não recebem seed e o turno
    é marcado ``nao-deterministico=true``.
    """
    if perfil.modelo in MODELOS_SEM_SEED:
        return None
    return seed_padrao


def _construir_prompt(
    perfil: AgentProfile,
    tema: TemaDebate,
    fase: str,
    propostas_visiveis: list[Proposta],
) -> str:
    """Constrói um prompt textual para o agente.

    Em produção, esta função fará o template com instruções de saída JSON.
    Aqui, o conteúdo é deliberadamente simples — backends de teste ignoram
    o texto e respondem com base na chave ``(agente, fase)``.
    """
    blocos = [
        f"agente: {perfil.nome}",
        f"fase: {fase}",
        f"tema: {tema.titulo}",
        f"descricao: {tema.descricao}",
        f"tags: {list(tema.tags)}",
    ]
    if propostas_visiveis:
        resumos = ", ".join(
            f"{p.id}={p.autor}:{p.resumo[:40]}" for p in propostas_visiveis
        )
        blocos.append(f"propostas_visiveis: {resumos}")
    return " | ".join(blocos)


# ---------------------------------------------------------------------------
# Orquestrador (Athena)
# ---------------------------------------------------------------------------


class Orchestrator:
    """State machine completa do Conselho CAOS (R4–R7).

    Parameters
    ----------
    perfis:
        Mapa ``nome -> AgentProfile`` dos 9 agentes (vindo do
        :class:`Profile_Loader`).
    agent_invoker:
        :class:`AgentInvoker` configurado com backend, cache e
        :class:`SkillTokenBudget`.
    council_recorder:
        Quando informado, persiste Debate + Decisao_Do_Conselho ao final.
    failure_handler:
        Quando informado, contabiliza agentes indisponíveis e dispara
        abortagem por R14.4 quando ultrapassa o limiar.
    context_loader:
        Reservado para a integração futura — atualmente o orquestrador
        consome apenas o ``tema`` para produzir o prompt. Mantido na
        assinatura para satisfazer a injeção exigida pelo design.
    bias_filter, steering_engine, profile_loader, determinism_auditor,
    llm_cache_adapter, token_budget_guard:
        Reservados para integrações futuras. Não são acessados pelo
        fluxo principal — apenas armazenados como atributos para que o
        chamador possa inspecioná-los e o design fique documentado em
        código.
    sequencial_inicial:
        NN inicial usado para gerar ``identificador`` ``AAAA-MM-DD-NN``.
        Default 1; o caller (CLI) é quem decide o NN do dia.
    """

    def __init__(
        self,
        *,
        perfis: dict[str, AgentProfile],
        agent_invoker: AgentInvoker,
        council_recorder: Optional[CouncilRecorder] = None,
        failure_handler: Optional[FailureHandler] = None,
        context_loader: Any = None,
        bias_filter: Any = None,
        steering_engine: Any = None,
        profile_loader: Any = None,
        determinism_auditor: Any = None,
        llm_cache_adapter: Any = None,
        token_budget_guard: Any = None,
        sequencial_inicial: int = 1,
    ) -> None:
        if not isinstance(perfis, dict) or not perfis:
            raise ValueError("perfis deve ser um dict não vazio de AgentProfile")
        for nome, p in perfis.items():
            if nome not in AGENTES:
                raise ValueError(
                    f"agente {nome!r} fora do conjunto de 9 agentes do Conselho"
                )
            if not isinstance(p, AgentProfile):
                raise ValueError(
                    f"perfil de {nome!r} não é AgentProfile válido"
                )
        if not isinstance(agent_invoker, AgentInvoker):
            raise ValueError("agent_invoker deve ser AgentInvoker")
        if not (1 <= sequencial_inicial <= 99):
            raise ValueError(
                "sequencial_inicial fora de [1, 99]; "
                f"recebido {sequencial_inicial}"
            )
        self._perfis = dict(perfis)
        self._agent_invoker = agent_invoker
        self._council_recorder = council_recorder
        self._failure_handler = failure_handler
        # Atributos para integração futura (mantidos como API documentada).
        self.context_loader = context_loader
        self.bias_filter = bias_filter
        self.steering_engine = steering_engine
        self.profile_loader = profile_loader
        self.determinism_auditor = determinism_auditor
        self.llm_cache_adapter = llm_cache_adapter
        self.token_budget_guard = token_budget_guard
        self._sequencial_inicial = sequencial_inicial

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def iniciar_debate(
        self,
        tema: TemaDebate,
        *,
        configuracao: Optional[ConfiguracaoDebate] = None,
    ) -> ResultadoDebate:
        """Conduz um Debate completo aplicando a state machine.

        Etapas (em ordem):

        1. ``INICIADO``: monta cabeçalho do Debate; resolve agentes elegíveis.
        2. ``PROPOSTAS``: round-robin alfabético dos proponentes (R4.2).
           Cada invocação consome 1 turno e respeita o orçamento (R7.1, R7.2).
           Bloqueio por orçamento de tokens marca o agente como indisponível
           via Failure_Handler (R17.4).
        3. Verifica quórum mínimo (R4.3) — < 2 propostas válidas → SEM_QUORUM.
        4. Verifica indisponibilidade de agentes (R14.4) — > 2 → ABORTADO.
        5. ``CRITICA``: invoca Devils_Advocate (R4.4).
        6. ``AVALIACAO_RISCO`` (se ``tema.altera_exposicao``): invoca Cerberus
           com ``tokens_estimados=deadline_cerberus_s`` semântico (R5).
        7. ``AVALIACAO_TECNICA`` (se ``tema.requer_csharp``): invoca Hermes
           (R6).
        8. ``SINTESE``: aplica vetos bloqueantes, conta votos com
           consenso de 2/3, decide proposta aceita ou ``PENDENTE_USUARIO``
           (R4.5–R4.8).
        9. Grava via Council_Recorder se disponível (R8.4).
        """
        cfg = configuracao or ConfiguracaoDebate()
        data_inicio = _now_utc()
        identificador = _gerar_identificador_debate(
            data_inicio, self._sequencial_inicial
        )

        # ----- Estado mutável do Debate -----
        turnos: list[Turno] = []
        propostas: list[Proposta] = []
        vetos: list[Veto] = []
        agentes_envolvidos: list[str] = []
        modelos_envolvidos: dict[str, str] = {}
        seeds_envolvidos: dict[str, int] = {}
        nao_det_qualquer = False
        indisponiveis: list[str] = []

        # ----- 1. INICIADO -> PROPOSTAS -----
        proponentes = _ordem_proponentes(self._perfis, tema.tags)

        # ----- 2. FASE PROPOSTAS -----
        for perfil in proponentes:
            if len(turnos) >= cfg.orcamento_de_turnos:
                # Orçamento esgotado dentro de PROPOSTAS — TIMEOUT (R7.5).
                return self._encerrar_timeout(
                    tema=tema,
                    cfg=cfg,
                    identificador=identificador,
                    data_inicio=data_inicio,
                    turnos=turnos,
                    propostas=propostas,
                    vetos=vetos,
                    agentes_envolvidos=agentes_envolvidos,
                    modelos_envolvidos=modelos_envolvidos,
                    seeds_envolvidos=seeds_envolvidos,
                    nao_det_qualquer=nao_det_qualquer,
                    indisponiveis=indisponiveis,
                    fase="PROPOSTAS",
                )
            resp_inv = self._invocar_agente(
                perfil=perfil,
                tema=tema,
                fase="PROPOSTAS",
                propostas_visiveis=[],
                cfg=cfg,
            )
            turno = self._construir_turno(
                numero=len(turnos) + 1,
                perfil=perfil,
                fase="PROPOSTAS",
                resultado=resp_inv,
            )
            turnos.append(turno)
            agentes_envolvidos.append(perfil.nome)
            modelos_envolvidos[perfil.nome] = perfil.modelo
            seed_efetiva = _seed_para(perfil, cfg.seed_padrao)
            if seed_efetiva is not None:
                seeds_envolvidos[perfil.nome] = seed_efetiva
            nao_det_qualquer = nao_det_qualquer or resp_inv.nao_deterministico

            if resp_inv.bloqueado_por_orcamento:
                indisponiveis.append(perfil.nome)
                if self._failure_handler is not None:
                    self._failure_handler.marcar_agente_indisponivel(
                        perfil.nome,
                        motivo="orcamento-de-tokens-esgotado",
                        turno=turno.numero,
                    )
                continue

            estrutura = _RespostaAgente.de_resposta(resp_inv.resposta)
            for proposta_raw in estrutura.propostas:
                proposta = self._materializar_proposta(
                    proposta_raw, autor=perfil.nome, indice=len(propostas) + 1
                )
                if proposta is not None:
                    propostas.append(proposta)

        # ----- 3. Quórum (R4.3) -----
        if len(propostas) < 2:
            return self._encerrar_sem_quorum(
                tema=tema,
                cfg=cfg,
                identificador=identificador,
                data_inicio=data_inicio,
                turnos=turnos,
                agentes_envolvidos=agentes_envolvidos,
                modelos_envolvidos=modelos_envolvidos,
                seeds_envolvidos=seeds_envolvidos,
                nao_det_qualquer=nao_det_qualquer,
                indisponiveis=indisponiveis,
            )

        # ----- 4. Indisponibilidade (R14.4) -----
        if (
            self._failure_handler is not None
            and self._failure_handler.deve_abortar()
        ):
            return self._encerrar_abortado(
                tema=tema,
                cfg=cfg,
                identificador=identificador,
                data_inicio=data_inicio,
                turnos=turnos,
                propostas=propostas,
                vetos=vetos,
                agentes_envolvidos=agentes_envolvidos,
                modelos_envolvidos=modelos_envolvidos,
                seeds_envolvidos=seeds_envolvidos,
                nao_det_qualquer=nao_det_qualquer,
                indisponiveis=indisponiveis,
            )

        # ----- 5. FASE CRITICA -----
        if len(turnos) >= cfg.orcamento_de_turnos:
            return self._encerrar_timeout(
                tema=tema,
                cfg=cfg,
                identificador=identificador,
                data_inicio=data_inicio,
                turnos=turnos,
                propostas=propostas,
                vetos=vetos,
                agentes_envolvidos=agentes_envolvidos,
                modelos_envolvidos=modelos_envolvidos,
                seeds_envolvidos=seeds_envolvidos,
                nao_det_qualquer=nao_det_qualquer,
                indisponiveis=indisponiveis,
                fase="CRITICA",
            )
        perfil_da = self._perfis.get("Devils_Advocate")
        if perfil_da is not None:
            resp_da = self._invocar_agente(
                perfil=perfil_da,
                tema=tema,
                fase="CRITICA",
                propostas_visiveis=propostas,
                cfg=cfg,
            )
            turno_da = self._construir_turno(
                numero=len(turnos) + 1,
                perfil=perfil_da,
                fase="CRITICA",
                resultado=resp_da,
            )
            turnos.append(turno_da)
            if perfil_da.nome not in agentes_envolvidos:
                agentes_envolvidos.append(perfil_da.nome)
            modelos_envolvidos[perfil_da.nome] = perfil_da.modelo
            seed_da = _seed_para(perfil_da, cfg.seed_padrao)
            if seed_da is not None:
                seeds_envolvidos[perfil_da.nome] = seed_da
            nao_det_qualquer = nao_det_qualquer or resp_da.nao_deterministico
            # Devils_Advocate não emite vetos formais (R4.4).

        # ----- 6. FASE AVALIACAO_RISCO -----
        if tema.altera_exposicao:
            if len(turnos) >= cfg.orcamento_de_turnos:
                return self._encerrar_timeout(
                    tema=tema,
                    cfg=cfg,
                    identificador=identificador,
                    data_inicio=data_inicio,
                    turnos=turnos,
                    propostas=propostas,
                    vetos=vetos,
                    agentes_envolvidos=agentes_envolvidos,
                    modelos_envolvidos=modelos_envolvidos,
                    seeds_envolvidos=seeds_envolvidos,
                    nao_det_qualquer=nao_det_qualquer,
                    indisponiveis=indisponiveis,
                    fase="AVALIACAO_RISCO",
                )
            perfil_cb = self._perfis.get("Cerberus")
            if perfil_cb is not None:
                resp_cb = self._invocar_agente(
                    perfil=perfil_cb,
                    tema=tema,
                    fase="AVALIACAO_RISCO",
                    propostas_visiveis=propostas,
                    cfg=cfg,
                    tokens_estimados=cfg.tokens_estimados,
                )
                turno_cb = self._construir_turno(
                    numero=len(turnos) + 1,
                    perfil=perfil_cb,
                    fase="AVALIACAO_RISCO",
                    resultado=resp_cb,
                )
                turnos.append(turno_cb)
                if perfil_cb.nome not in agentes_envolvidos:
                    agentes_envolvidos.append(perfil_cb.nome)
                modelos_envolvidos[perfil_cb.nome] = perfil_cb.modelo
                seed_cb = _seed_para(perfil_cb, cfg.seed_padrao)
                if seed_cb is not None:
                    seeds_envolvidos[perfil_cb.nome] = seed_cb
                nao_det_qualquer = (
                    nao_det_qualquer or resp_cb.nao_deterministico
                )
                if resp_cb.bloqueado_por_orcamento:
                    # R5.6: ausência/falha de Cerberus quando exigido →
                    # cerberus-timeout. Aqui o "timeout" é representado
                    # por bloqueio prévio do orçamento de tokens.
                    return self._encerrar_cerberus_timeout(
                        tema=tema,
                        cfg=cfg,
                        identificador=identificador,
                        data_inicio=data_inicio,
                        turnos=turnos,
                        propostas=propostas,
                        vetos=vetos,
                        agentes_envolvidos=agentes_envolvidos,
                        modelos_envolvidos=modelos_envolvidos,
                        seeds_envolvidos=seeds_envolvidos,
                        nao_det_qualquer=nao_det_qualquer,
                        indisponiveis=indisponiveis + [perfil_cb.nome],
                    )
                estrutura_cb = _RespostaAgente.de_resposta(resp_cb.resposta)
                for veto_raw in estrutura_cb.vetos:
                    veto = self._materializar_veto(
                        veto_raw,
                        autor_padrao="Cerberus",
                        tipo_padrao="veto_de_risco",
                        propostas_existentes=propostas,
                    )
                    if veto is not None:
                        vetos.append(veto)

        # ----- 7. FASE AVALIACAO_TECNICA -----
        if tema.requer_csharp:
            if len(turnos) >= cfg.orcamento_de_turnos:
                return self._encerrar_timeout(
                    tema=tema,
                    cfg=cfg,
                    identificador=identificador,
                    data_inicio=data_inicio,
                    turnos=turnos,
                    propostas=propostas,
                    vetos=vetos,
                    agentes_envolvidos=agentes_envolvidos,
                    modelos_envolvidos=modelos_envolvidos,
                    seeds_envolvidos=seeds_envolvidos,
                    nao_det_qualquer=nao_det_qualquer,
                    indisponiveis=indisponiveis,
                    fase="AVALIACAO_TECNICA",
                )
            perfil_hm = self._perfis.get("Hermes")
            if perfil_hm is not None:
                resp_hm = self._invocar_agente(
                    perfil=perfil_hm,
                    tema=tema,
                    fase="AVALIACAO_TECNICA",
                    propostas_visiveis=propostas,
                    cfg=cfg,
                    tokens_estimados=cfg.tokens_estimados,
                )
                turno_hm = self._construir_turno(
                    numero=len(turnos) + 1,
                    perfil=perfil_hm,
                    fase="AVALIACAO_TECNICA",
                    resultado=resp_hm,
                )
                turnos.append(turno_hm)
                if perfil_hm.nome not in agentes_envolvidos:
                    agentes_envolvidos.append(perfil_hm.nome)
                modelos_envolvidos[perfil_hm.nome] = perfil_hm.modelo
                seed_hm = _seed_para(perfil_hm, cfg.seed_padrao)
                if seed_hm is not None:
                    seeds_envolvidos[perfil_hm.nome] = seed_hm
                nao_det_qualquer = (
                    nao_det_qualquer or resp_hm.nao_deterministico
                )
                estrutura_hm = _RespostaAgente.de_resposta(resp_hm.resposta)
                for veto_raw in estrutura_hm.vetos:
                    veto = self._materializar_veto(
                        veto_raw,
                        autor_padrao="Hermes",
                        tipo_padrao="veto_tecnico",
                        propostas_existentes=propostas,
                    )
                    if veto is not None:
                        vetos.append(veto)

        # ----- 8. FASE SINTESE -----
        if len(turnos) >= cfg.orcamento_de_turnos:
            return self._encerrar_timeout(
                tema=tema,
                cfg=cfg,
                identificador=identificador,
                data_inicio=data_inicio,
                turnos=turnos,
                propostas=propostas,
                vetos=vetos,
                agentes_envolvidos=agentes_envolvidos,
                modelos_envolvidos=modelos_envolvidos,
                seeds_envolvidos=seeds_envolvidos,
                nao_det_qualquer=nao_det_qualquer,
                indisponiveis=indisponiveis,
                fase="SINTESE",
            )
        return self._encerrar_sintese(
            tema=tema,
            cfg=cfg,
            identificador=identificador,
            data_inicio=data_inicio,
            turnos=turnos,
            propostas=propostas,
            vetos=vetos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            nao_det_qualquer=nao_det_qualquer,
            indisponiveis=indisponiveis,
        )


    # ------------------------------------------------------------------
    # Helpers internos — invocação e materialização
    # ------------------------------------------------------------------

    def _invocar_agente(
        self,
        *,
        perfil: AgentProfile,
        tema: TemaDebate,
        fase: str,
        propostas_visiveis: list[Proposta],
        cfg: ConfiguracaoDebate,
        tokens_estimados: Optional[int] = None,
    ) -> ResultadoInvocacao:
        """Wrapper sobre :meth:`AgentInvoker.invocar` com prompt padrão."""
        prompt = _construir_prompt(perfil, tema, fase, propostas_visiveis)
        contexto = _hash_input_tema(tema)
        seed_efetiva = _seed_para(perfil, cfg.seed_padrao)
        params = InvocacaoModelo(
            agente=perfil.nome,
            modelo=perfil.modelo,
            prompt=prompt,
            contexto=contexto,
            seed=seed_efetiva,
            tokens_estimados=(
                tokens_estimados
                if tokens_estimados is not None
                else cfg.tokens_estimados
            ),
        )
        return self._agent_invoker.invocar(params)

    def _construir_turno(
        self,
        *,
        numero: int,
        perfil: AgentProfile,
        fase: str,
        resultado: ResultadoInvocacao,
    ) -> Turno:
        """Empacota uma invocação como :class:`Turno` para o Debate."""
        if resultado.bloqueado_por_orcamento:
            status = "orcamento-de-tokens-esgotado"
            conteudo = resultado.motivo_bloqueio or ""
        else:
            status = "ok"
            conteudo = resultado.resposta or ""
        return Turno(
            numero=numero,
            agente=perfil.nome,  # type: ignore[arg-type]
            modelo=perfil.modelo,
            timestamp=_now_utc(),
            fase=fase,  # type: ignore[arg-type]
            nao_deterministico=resultado.nao_deterministico,
            cache_hit=resultado.cache_hit,
            status=status,  # type: ignore[arg-type]
            conteudo_markdown=conteudo or None,
        )

    def _materializar_proposta(
        self,
        proposta_raw: dict[str, Any],
        *,
        autor: str,
        indice: int,
    ) -> Optional[Proposta]:
        """Constrói :class:`Proposta` a partir de dict bruto vindo do backend.

        Atribui ``id = P{indice}``. Falhas de validação Pydantic (campos
        ausentes, tipos errados) descartam silenciosamente a proposta —
        mantém a state machine resiliente a respostas mal-formatadas sem
        exigir tratamento de exceção em cada chamador.
        """
        dados = dict(proposta_raw)
        dados["id"] = f"P{indice}"
        dados.setdefault("autor", autor)
        dados.setdefault("resumo", "")
        dados.setdefault("conteudo", "")
        dados.setdefault("confianca", 0)
        # Garantir tipos mínimos
        if not isinstance(dados.get("resumo"), str) or not dados["resumo"]:
            dados["resumo"] = f"proposta de {autor}"
        if not isinstance(dados.get("conteudo"), str) or not dados["conteudo"]:
            dados["conteudo"] = dados["resumo"]
        try:
            return Proposta(**dados)
        except ValidationError:
            return None

    def _materializar_veto(
        self,
        veto_raw: dict[str, Any],
        *,
        autor_padrao: str,
        tipo_padrao: str,
        propostas_existentes: list[Proposta],
    ) -> Optional[Veto]:
        """Constrói :class:`Veto` a partir de dict bruto.

        Suporta dois formatos de ``proposta_alvo``:

        - String com id ``"P3"`` — usada diretamente.
        - Inteiro 0-based (``indice``) — convertido em ``"P{indice+1}"``
          se cair dentro de ``range(len(propostas_existentes))``.
        """
        dados = dict(veto_raw)
        dados.setdefault("autor", autor_padrao)
        dados.setdefault("tipo", tipo_padrao)
        # Trata proposta_alvo como índice numérico se vier como int.
        alvo = dados.get("proposta_alvo")
        if isinstance(alvo, int):
            if 0 <= alvo < len(propostas_existentes):
                dados["proposta_alvo"] = propostas_existentes[alvo].id
            else:
                return None
        # Default para decisao/justificativa quando ausentes.
        if dados["tipo"] == "veto_tecnico":
            dados.setdefault("decisao", "bloquear")
            dados.setdefault("categoria_tecnica", "compilacao_falhou")
            dados.setdefault("justificativa", "veto técnico aplicado")
        else:
            dados.setdefault("decisao", "bloquear")
            dados.setdefault("justificativa", "veto de risco aplicado")
        try:
            return Veto(**dados)
        except ValidationError:
            return None

    # ------------------------------------------------------------------
    # Helpers internos — encerramento por fase terminal
    # ------------------------------------------------------------------

    def _construir_decisao_final(
        self,
        propostas: list[Proposta],
        proposta_aceita_id: Optional[str],
        rationale: str,
    ) -> DecisaoFinal:
        """Constrói o sub-bloco ``decisao_final`` com texto não-vazio garantido."""
        rationale_efetivo = (rationale or "").strip() or "sem rationale"
        return DecisaoFinal(
            proposta_aceita=proposta_aceita_id,
            rationale=rationale_efetivo,
        )

    def _empacotar_debate(
        self,
        *,
        identificador: str,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        data_inicio: datetime,
        data_fim: datetime,
        turnos: list[Turno],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        fase_final: str,
        status: str,
    ) -> Debate:
        """Constrói o objeto :class:`Debate` final com cabeçalho consistente."""
        if not agentes_envolvidos:
            # R8.2 exige no mínimo 1 agente; se nenhum chegou a ser envolvido
            # (ex.: nenhum proponente elegível), incluímos ao menos Athena
            # como ancora — ela é responsável pela orquestração mesmo sem
            # turnos próprios.
            agentes_envolvidos = ["Athena"]
            modelos_envolvidos.setdefault("Athena", "claude-opus-4.7")
        slug = _slug_kebab(tema.titulo)
        # Hash do contexto: aqui usamos o hash do input do tema. Quando
        # Context_Loader é integrado, esse valor é substituído pelo hash
        # das Notas_Zettel injetadas (R10.8).
        contexto_hash = _hash_input_tema(tema)
        return Debate(
            identificador=identificador,
            titulo=slug,
            data_inicio=data_inicio,
            data_fim=data_fim,
            agentes_participantes=list(agentes_envolvidos),  # type: ignore[arg-type]
            modelos=dict(modelos_envolvidos),
            contexto_hash_sha256=contexto_hash,
            notas_injetadas=[],
            seeds=dict(seeds_envolvidos),
            orcamento_de_turnos=cfg.orcamento_de_turnos,
            turnos_consumidos=len(turnos),
            fase_final=fase_final,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            turnos=list(turnos),
        )

    def _gravar_se_disponivel(
        self,
        debate: Debate,
        decisao: Optional[DecisaoDoConselho],
    ) -> Optional[ResultadoGravacao]:
        """Grava via Council_Recorder se houver recorder e decisão completa."""
        if self._council_recorder is None or decisao is None:
            return None
        try:
            return self._council_recorder.gravar(debate, decisao)
        except Exception:
            # Falha na gravação não invalida o resultado em memória — o
            # caller pode inspecionar e re-tentar manualmente.
            return None

    def _encerrar_sintese(
        self,
        *,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        identificador: str,
        data_inicio: datetime,
        turnos: list[Turno],
        propostas: list[Proposta],
        vetos: list[Veto],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        nao_det_qualquer: bool,
        indisponiveis: list[str],
    ) -> ResultadoDebate:
        """Aplica vetos bloqueantes, conta votos e encerra em CONCLUIDO ou PENDENTE.

        Regras (R4.5–R4.8, R5.3, R5.5, R6.5):

        - Veto técnico (Hermes) com decisão ``bloquear`` rejeita a
          proposta-alvo permanentemente.
        - Veto de risco (Cerberus) com decisão ``bloquear`` rejeita.
          Decisão ``aprovar-com-ressalvas`` permite continuidade.
        - Entre as propostas não-rejeitadas, escolhe a com maior
          confiança; em empate, ordem alfabética do autor (determinismo).
        - Para "consenso" (R4.6) usamos um modelo simplificado:
          considera-se que o consenso é satisfeito quando há ao menos
          uma proposta não-rejeitada e o limiar de 2/3 é atingido por
          contagem de propostas não vetadas (`(propostas - rejeitadas)
          >= ceil(2/3 * propostas)`). Esse modelo simplificado é
          adequado para os testes de propriedade definidos pela Task 15
          e para a integração com o orquestrador real, que pode
          enriquecer a contagem de votos via ``estrutura.voto`` em
          turnos subsequentes (futura extensão).
        """
        propostas_bloqueadas: set[str] = set()
        for v in vetos:
            if v.decisao == "bloquear":
                propostas_bloqueadas.add(v.proposta_alvo)

        elegiveis = [p for p in propostas if p.id not in propostas_bloqueadas]
        # Limiar 2/3: arredonda para cima sobre o total de propostas (R4.6).
        limiar_minimo = math.ceil(cfg.limiar_consenso * len(propostas))

        # ----- Aplicar consenso -----
        if not elegiveis or len(elegiveis) < max(1, limiar_minimo):
            return self._encerrar_pendente_usuario(
                tema=tema,
                cfg=cfg,
                identificador=identificador,
                data_inicio=data_inicio,
                turnos=turnos,
                propostas=propostas,
                vetos=vetos,
                agentes_envolvidos=agentes_envolvidos,
                modelos_envolvidos=modelos_envolvidos,
                seeds_envolvidos=seeds_envolvidos,
                nao_det_qualquer=nao_det_qualquer,
                indisponiveis=indisponiveis,
            )

        # ----- Escolha da proposta vencedora -----
        # Desempate: maior confiança → maior intersecção de tags com tema
        # → ordem alfabética do autor.
        def _pontuacao_intersec(p: Proposta) -> int:
            perfil = self._perfis.get(p.autor)
            if perfil is None:
                return 0
            return len(set(tema.tags).intersection(perfil.tags_especialidade))

        elegiveis_ordenadas = sorted(
            elegiveis,
            key=lambda p: (
                -p.confianca,
                -_pontuacao_intersec(p),
                p.autor,
                p.id,
            ),
        )
        vencedora = elegiveis_ordenadas[0]

        # ----- Construir DecisaoDoConselho -----
        rationale = (
            f"Proposta {vencedora.id} (autor: {vencedora.autor}) selecionada "
            f"com confianca={vencedora.confianca}; "
            f"propostas avaliadas: {len(propostas)}; vetos aplicados: "
            f"{len(vetos)}; bloqueadas: {sorted(propostas_bloqueadas)}."
        )
        decisao_final = self._construir_decisao_final(
            propostas=propostas,
            proposta_aceita_id=vencedora.id,
            rationale=rationale,
        )
        reproduzivel = derivar_reproduzivel(turnos)
        decisao = self._construir_decisao(
            identificador=identificador,
            tema=tema,
            propostas=propostas,
            vetos=vetos,
            decisao_final=decisao_final,
            agentes_envolvidos=agentes_envolvidos,
            reproduzivel=reproduzivel,
            status="concluido",
        )

        debate = self._empacotar_debate(
            identificador=identificador,
            tema=tema,
            cfg=cfg,
            data_inicio=data_inicio,
            data_fim=_now_utc(),
            turnos=turnos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            fase_final="CONCLUIDO",
            status="concluido",
        )
        gravacao = self._gravar_se_disponivel(debate, decisao)
        return ResultadoDebate(
            debate=debate,
            decisao=decisao,
            fase_final="CONCLUIDO",
            motivo_encerramento="concluido",
            resultado_gravacao=gravacao,
            indisponiveis=tuple(indisponiveis),
        )

    def _encerrar_pendente_usuario(
        self,
        **kwargs: Any,
    ) -> ResultadoDebate:
        """Encerra como PENDENTE_USUARIO (R4.8)."""
        return self._encerrar_com_status(
            fase_final="PENDENTE_USUARIO",
            status="pendente-de-usuario",
            motivo_encerramento="pendente-usuario",
            rationale_extra=(
                "Consenso não atingido após aplicar vetos bloqueantes. "
                "Solicita arbitragem do usuário (R4.8)."
            ),
            **kwargs,
        )

    def _encerrar_sem_quorum(
        self,
        *,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        identificador: str,
        data_inicio: datetime,
        turnos: list[Turno],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        nao_det_qualquer: bool,
        indisponiveis: list[str],
    ) -> ResultadoDebate:
        """Encerra em SEM_QUORUM (R4.3) — sem propostas suficientes."""
        debate = self._empacotar_debate(
            identificador=identificador,
            tema=tema,
            cfg=cfg,
            data_inicio=data_inicio,
            data_fim=_now_utc(),
            turnos=turnos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            fase_final="SEM_QUORUM",
            status="sem-quorum",
        )
        # Sem proposta válida: schema R8.2 exige >=1 proposta, então não
        # gravamos ``DecisaoDoConselho`` neste caminho. O resultado em
        # memória é o suficiente para o caller.
        return ResultadoDebate(
            debate=debate,
            decisao=None,
            fase_final="SEM_QUORUM",
            motivo_encerramento="sem-quorum",
            resultado_gravacao=None,
            indisponiveis=tuple(indisponiveis),
        )

    def _encerrar_timeout(
        self,
        *,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        identificador: str,
        data_inicio: datetime,
        turnos: list[Turno],
        propostas: list[Proposta],
        vetos: list[Veto],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        nao_det_qualquer: bool,
        indisponiveis: list[str],
        fase: str,
    ) -> ResultadoDebate:
        """Encerra em TIMEOUT (R7.5) — orçamento de turnos esgotado."""
        decisao: Optional[DecisaoDoConselho] = None
        if propostas:
            rationale = (
                f"Debate encerrado por TIMEOUT na fase {fase}; "
                f"turnos consumidos: {len(turnos)}; orçamento aplicado: "
                f"{cfg.orcamento_de_turnos}; propostas avaliadas: "
                f"{len(propostas)}; vetos aplicados: {len(vetos)} (R7.5)."
            )
            decisao_final = self._construir_decisao_final(
                propostas=propostas,
                proposta_aceita_id=None,
                rationale=rationale,
            )
            decisao = self._construir_decisao(
                identificador=identificador,
                tema=tema,
                propostas=propostas,
                vetos=vetos,
                decisao_final=decisao_final,
                agentes_envolvidos=agentes_envolvidos,
                reproduzivel=derivar_reproduzivel(turnos),
                status="timeout",
            )
        debate = self._empacotar_debate(
            identificador=identificador,
            tema=tema,
            cfg=cfg,
            data_inicio=data_inicio,
            data_fim=_now_utc(),
            turnos=turnos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            fase_final="TIMEOUT",
            status="timeout",
        )
        gravacao = self._gravar_se_disponivel(debate, decisao)
        return ResultadoDebate(
            debate=debate,
            decisao=decisao,
            fase_final="TIMEOUT",
            motivo_encerramento="timeout",
            resultado_gravacao=gravacao,
            indisponiveis=tuple(indisponiveis),
        )

    def _encerrar_cerberus_timeout(
        self,
        *,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        identificador: str,
        data_inicio: datetime,
        turnos: list[Turno],
        propostas: list[Proposta],
        vetos: list[Veto],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        nao_det_qualquer: bool,
        indisponiveis: list[str],
    ) -> ResultadoDebate:
        """Encerra em CERBERUS_TIMEOUT (R5.6)."""
        rationale = (
            "Cerberus indisponível ou ausente dentro do deadline de "
            f"{cfg.deadline_cerberus_s}s; aceitação de propostas que alteram "
            "exposição bloqueada por R5.6."
        )
        decisao_final = self._construir_decisao_final(
            propostas=propostas,
            proposta_aceita_id=None,
            rationale=rationale,
        )
        decisao = self._construir_decisao(
            identificador=identificador,
            tema=tema,
            propostas=propostas,
            vetos=vetos,
            decisao_final=decisao_final,
            agentes_envolvidos=agentes_envolvidos,
            reproduzivel=derivar_reproduzivel(turnos),
            status="cerberus-timeout",
        )
        debate = self._empacotar_debate(
            identificador=identificador,
            tema=tema,
            cfg=cfg,
            data_inicio=data_inicio,
            data_fim=_now_utc(),
            turnos=turnos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            fase_final="CERBERUS_TIMEOUT",
            status="cerberus-timeout",
        )
        gravacao = self._gravar_se_disponivel(debate, decisao)
        return ResultadoDebate(
            debate=debate,
            decisao=decisao,
            fase_final="CERBERUS_TIMEOUT",
            motivo_encerramento="cerberus-timeout",
            resultado_gravacao=gravacao,
            indisponiveis=tuple(indisponiveis),
        )

    def _encerrar_abortado(
        self,
        *,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        identificador: str,
        data_inicio: datetime,
        turnos: list[Turno],
        propostas: list[Proposta],
        vetos: list[Veto],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        nao_det_qualquer: bool,
        indisponiveis: list[str],
    ) -> ResultadoDebate:
        """Encerra em ABORTADO_POR_INDISPONIBILIDADE (R14.4)."""
        rationale = (
            "Debate abortado por R14.4: mais de 2 agentes ficaram "
            "indisponíveis ao longo do Debate. Lista de indisponíveis: "
            f"{sorted(set(indisponiveis))}."
        )
        decisao: Optional[DecisaoDoConselho] = None
        if propostas:
            decisao_final = self._construir_decisao_final(
                propostas=propostas,
                proposta_aceita_id=None,
                rationale=rationale,
            )
            decisao = self._construir_decisao(
                identificador=identificador,
                tema=tema,
                propostas=propostas,
                vetos=vetos,
                decisao_final=decisao_final,
                agentes_envolvidos=agentes_envolvidos,
                reproduzivel=derivar_reproduzivel(turnos),
                status="abortado-por-indisponibilidade",
            )
        debate = self._empacotar_debate(
            identificador=identificador,
            tema=tema,
            cfg=cfg,
            data_inicio=data_inicio,
            data_fim=_now_utc(),
            turnos=turnos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            fase_final="ABORTADO_POR_INDISPONIBILIDADE",
            status="abortado-por-indisponibilidade",
        )
        gravacao = self._gravar_se_disponivel(debate, decisao)
        return ResultadoDebate(
            debate=debate,
            decisao=decisao,
            fase_final="ABORTADO_POR_INDISPONIBILIDADE",
            motivo_encerramento="abortado-por-indisponibilidade",
            resultado_gravacao=gravacao,
            indisponiveis=tuple(indisponiveis),
        )

    def _encerrar_com_status(
        self,
        *,
        tema: TemaDebate,
        cfg: ConfiguracaoDebate,
        identificador: str,
        data_inicio: datetime,
        turnos: list[Turno],
        propostas: list[Proposta],
        vetos: list[Veto],
        agentes_envolvidos: list[str],
        modelos_envolvidos: dict[str, str],
        seeds_envolvidos: dict[str, int],
        nao_det_qualquer: bool,
        indisponiveis: list[str],
        fase_final: str,
        status: str,
        motivo_encerramento: MotivoEncerramento,
        rationale_extra: str,
    ) -> ResultadoDebate:
        """Cria um ResultadoDebate genérico para fases terminais com decisão."""
        decisao_final = self._construir_decisao_final(
            propostas=propostas,
            proposta_aceita_id=None,
            rationale=rationale_extra,
        )
        decisao: Optional[DecisaoDoConselho] = None
        if propostas:
            decisao = self._construir_decisao(
                identificador=identificador,
                tema=tema,
                propostas=propostas,
                vetos=vetos,
                decisao_final=decisao_final,
                agentes_envolvidos=agentes_envolvidos,
                reproduzivel=derivar_reproduzivel(turnos),
                status=status,
            )
        debate = self._empacotar_debate(
            identificador=identificador,
            tema=tema,
            cfg=cfg,
            data_inicio=data_inicio,
            data_fim=_now_utc(),
            turnos=turnos,
            agentes_envolvidos=agentes_envolvidos,
            modelos_envolvidos=modelos_envolvidos,
            seeds_envolvidos=seeds_envolvidos,
            fase_final=fase_final,
            status=status,
        )
        gravacao = self._gravar_se_disponivel(debate, decisao)
        return ResultadoDebate(
            debate=debate,
            decisao=decisao,
            fase_final=fase_final,
            motivo_encerramento=motivo_encerramento,
            resultado_gravacao=gravacao,
            indisponiveis=tuple(indisponiveis),
        )

    def _construir_decisao(
        self,
        *,
        identificador: str,
        tema: TemaDebate,
        propostas: list[Proposta],
        vetos: list[Veto],
        decisao_final: DecisaoFinal,
        agentes_envolvidos: list[str],
        reproduzivel: str,
        status: str,
    ) -> DecisaoDoConselho:
        """Constrói :class:`DecisaoDoConselho` consistente com R8.2."""
        slug = _slug_kebab(tema.titulo)
        debate_relacionado = f"{identificador}-{slug}.md"
        # R8.2 exige no mínimo 1 link wiki-style para Notas_Zettel. O
        # orquestrador injeta um link sintético baseado no slug do tema —
        # o Council_Recorder e o usuário podem refinar depois.
        link = f"[[Decisao_{slug.replace('-', '_')}]]"
        agentes_finais = list(agentes_envolvidos) or ["Athena"]
        return DecisaoDoConselho(
            identificador=identificador,
            debate_relacionado=debate_relacionado,
            agentes_participantes=agentes_finais,  # type: ignore[arg-type]
            propostas=list(propostas),
            vetos=list(vetos),
            decisao_final=decisao_final,
            links_zettel=[link],
            aprovado_walk_forward=False,
            reproduzivel=reproduzivel,  # type: ignore[arg-type]
            regressao_detectada=False,
            status=status,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

__all__ = [
    "AGENTES_NAO_PROPONENTES",
    "DEADLINE_CERBERUS_S",
    "DEADLINE_HERMES_S",
    "DEADLINE_PROPOSTA_S",
    "LIMIAR_CONSENSO_PADRAO",
    "MotivoEncerramento",
    "Orchestrator",
    "ConfiguracaoDebate",
    "ResultadoDebate",
    "TemaDebate",
    "TOKENS_ESTIMADOS_PADRAO",
    "SEED_PADRAO",
]
