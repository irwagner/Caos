"""Validador de invocações de Skill por agente do Conselho CAOS.

Em tempo de invocação, verifica se a Skill solicitada está na lista
``skills_permitidas`` do :class:`caos.models.AgentProfile`. Cobre R2.5 e
R11.7 do ``requirements.md`` e o componente ``Skill_Validator`` descrito em
``design.md`` (seção 2 — Componentes e Interfaces; seção 6 —
Skill_Validator).

A validação é puramente estrutural: não invoca a Skill em si, apenas garante
que o agente tem autorização para isso. A política de auditoria (registrar o
bloqueio no turno do Debate) é aplicada via :func:`registrar_auditoria_bloqueio`
e consumida pelo orquestrador em Tasks futuras.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional, get_args

from caos.models import AgentProfile, SkillNome

# ---------------------------------------------------------------------------
# Conjunto de Skills do catálogo (R11)
# ---------------------------------------------------------------------------

#: Conjunto exato dos nomes de Skill declarados em :data:`caos.models.SkillNome`.
#:
#: Computado uma única vez na importação, via :func:`typing.get_args`, evitando
#: duplicação literal e mantendo o catálogo sincronizado com ``models.py``.
SKILLS_DO_CATALOGO: frozenset[str] = frozenset(get_args(SkillNome))


CategoriaBloqueio = Literal["skill-nao-autorizada", "skill-desconhecida"]
"""Categorias possíveis de bloqueio:

- ``skill-desconhecida``: a Skill solicitada NÃO existe no catálogo do
  Requirement 11. Indica erro de programação no agente ou typo no nome.
- ``skill-nao-autorizada``: a Skill existe no catálogo, mas o agente não a
  declarou em ``skills_permitidas`` (R2.5).
"""


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoValidacaoSkill:
    """Resultado de :func:`validar_invocacao`.

    ``autorizada == True`` implica ``categoria is None`` e ``motivo is None``.
    ``autorizada == False`` sempre acompanha ``categoria`` e ``motivo``
    preenchidos.
    """

    autorizada: bool
    skill_solicitada: str
    agente: str
    categoria: Optional[CategoriaBloqueio] = None
    motivo: Optional[str] = None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def validar_invocacao(
    perfil: AgentProfile, skill_nome: str
) -> ResultadoValidacaoSkill:
    """Valida se ``perfil`` pode invocar ``skill_nome``.

    Aplica em ordem:

    1. Se ``skill_nome`` não está em :data:`SKILLS_DO_CATALOGO`, retorna
       ``categoria="skill-desconhecida"`` (a Skill nem existe).
    2. Se ``skill_nome`` está no catálogo mas não em
       ``perfil.skills_permitidas``, retorna ``categoria="skill-nao-autorizada"``.
    3. Caso contrário, retorna ``autorizada=True``.

    Não levanta exceção: o orquestrador decide o que fazer com o resultado
    (registrar bloqueio + recusar invocação, ou prosseguir).
    """
    if skill_nome not in SKILLS_DO_CATALOGO:
        return ResultadoValidacaoSkill(
            autorizada=False,
            skill_solicitada=skill_nome,
            agente=perfil.nome,
            categoria="skill-desconhecida",
            motivo=(
                f"Skill {skill_nome!r} não existe no catálogo do "
                "Requirement 11; verifique o nome ou atualize o catálogo."
            ),
        )

    if skill_nome not in perfil.skills_permitidas:
        return ResultadoValidacaoSkill(
            autorizada=False,
            skill_solicitada=skill_nome,
            agente=perfil.nome,
            categoria="skill-nao-autorizada",
            motivo=(
                f"agente {perfil.nome!r} não declara {skill_nome!r} em "
                "skills_permitidas; invocação bloqueada por R2.5/R11.7."
            ),
        )

    return ResultadoValidacaoSkill(
        autorizada=True,
        skill_solicitada=skill_nome,
        agente=perfil.nome,
    )


def registrar_auditoria_bloqueio(
    perfil: AgentProfile,
    skill_nome: str,
    categoria: CategoriaBloqueio,
    *,
    timestamp: Optional[datetime] = None,
    parametros_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Gera um dicionário de auditoria pronto para ser anexado ao turno.

    O orquestrador (Athena) é quem persiste este registro no arquivo Markdown
    do Debate, sob o bloco ``skill_invocada`` do turno (R11.7 e design seção
    6 — "Auditoria de invocação"). Aqui apenas montamos a estrutura.

    Parameters
    ----------
    perfil:
        Perfil do agente que tentou invocar a Skill.
    skill_nome:
        Nome da Skill solicitada (pode estar fora do catálogo).
    categoria:
        Resultado da validação que motivou o bloqueio.
    timestamp:
        Timestamp do bloqueio. Se ``None``, usa ``datetime.now(timezone.utc)``.
    parametros_hash:
        Hash SHA-256 dos parâmetros que seriam passados à Skill, se conhecido.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    status = (
        "skill-nao-autorizada"
        if categoria == "skill-nao-autorizada"
        else "skill-desconhecida"
    )
    return {
        "nome": skill_nome,
        "invocador": perfil.nome,
        "modelo": perfil.modelo,
        "timestamp": timestamp.isoformat(),
        "parametros_hash_sha256": parametros_hash,
        "status": status,
        "exit_code": None,
        "duracao_ms": 0,
    }


__all__ = [
    "SKILLS_DO_CATALOGO",
    "CategoriaBloqueio",
    "ResultadoValidacaoSkill",
    "validar_invocacao",
    "registrar_auditoria_bloqueio",
]
