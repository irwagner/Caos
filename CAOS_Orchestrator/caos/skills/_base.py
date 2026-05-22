"""Utilidades compartilhadas pelas Skills do catálogo R11.

Este módulo concentra:

- A constante :data:`_LIMITE_BYTES_POR_CANAL` — limite de 10 MB por canal de
  saída (stdout/stderr) imposto pelo R11.1 (Skill_Terminal) e refletido nas
  demais Skills que executam processos externos.
- A função :func:`_truncar_saida`, que trunca uma string pelo número de bytes
  UTF-8 (e não de caracteres) preservando saída legível.
- A função :func:`_hash_parametros_sha256`, que serializa um ``dict`` de
  parâmetros em JSON canônico e devolve seu SHA-256 hex. Usada pelo bloco
  ``skill_invocada`` registrado em cada turno (design seção 6).
- A dataclass imutável :class:`RegistroAuditoriaSkill`, retornada por todas
  as Skills do catálogo. O Council_Recorder (Task 10) consome ``to_dict()``
  para gravar o bloco de auditoria no arquivo de Debate.

Toda a lógica é determinística (sem leitura de variáveis de ambiente) para
preservar a Property 1 (Determinism) do ``design.md`` quando o conteúdo dos
parâmetros não muda entre execuções.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Limite de 10 MB por canal de saída (stdout/stderr). Vem direto do R11.1.
_LIMITE_BYTES_POR_CANAL: int = 10 * 1024 * 1024


#: Status público de uma invocação de Skill (kebab-case, alinhado ao schema
#: ``skill_invocada`` em ``design.md`` seção 6).
StatusSkill = Literal["skill-ok", "skill-falha", "skill-timeout"]


# ---------------------------------------------------------------------------
# Truncagem por bytes (UTF-8 safe)
# ---------------------------------------------------------------------------


def _truncar_saida(saida: str, limite_bytes: int) -> tuple[str, bool]:
    """Trunca ``saida`` para no máximo ``limite_bytes`` bytes em UTF-8.

    A truncagem é por número de BYTES (não de caracteres) porque o limite do
    R11.1 está expresso em bytes. Caracteres multibyte cortados ao meio são
    substituídos por ``U+FFFD`` (REPLACEMENT CHARACTER) graças ao
    ``errors='replace'`` do decode, mantendo a string final como UTF-8 válido
    e auditável.

    Parameters
    ----------
    saida:
        Texto já decodificado a ser truncado.
    limite_bytes:
        Limite máximo em bytes (positivo). Valores ``<= 0`` resultam em
        retorno vazio com flag de truncagem ligada quando havia conteúdo.

    Returns
    -------
    tuple[str, bool]
        ``(saida_truncada, foi_truncada)``. ``foi_truncada`` é ``True`` se e
        somente se a representação UTF-8 original excedia ``limite_bytes``.
    """
    if limite_bytes <= 0:
        return ("", bool(saida))

    # ``errors='replace'`` no encode protege contra surrogates inválidos
    # provenientes de saídas mal-formadas (ex.: cmd em cp1252 com bytes que
    # não compõem UTF-8). É um compromisso documentado: prefere-se preservar
    # auditoria a abortar a Skill por encoding ruim.
    bytes_originais = saida.encode("utf-8", errors="replace")
    if len(bytes_originais) <= limite_bytes:
        return (saida, False)

    truncados = bytes_originais[:limite_bytes]
    # Decode novamente com replace para sanitizar qualquer multibyte cortado.
    return (truncados.decode("utf-8", errors="replace"), True)


# ---------------------------------------------------------------------------
# Hash determinístico de parâmetros
# ---------------------------------------------------------------------------


def _hash_parametros_sha256(parametros: dict[str, Any]) -> str:
    """Calcula SHA-256 hex sobre os ``parametros`` serializados de forma canônica.

    A serialização usa ``json.dumps(..., sort_keys=True, separators=(",", ":"),
    ensure_ascii=False)`` para garantir representação estável independente da
    ordem de inserção das chaves e do encoding default do interpretador.

    Tipos não serializáveis nativamente (``Path``, ``PurePath``, etc.) devem
    ser convertidos pelo chamador antes da invocação (ex.: ``str(cwd)``).
    Nesta camada, qualquer tipo não-JSON dispara ``TypeError`` propagado pelo
    ``json.dumps``.
    """
    bruto = json.dumps(
        parametros,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Registro de auditoria
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistroAuditoriaSkill:
    """Bloco de auditoria emitido por uma invocação de Skill.

    Reflete o exemplo YAML em ``design.md`` seção 6 (Auditoria de invocação).
    A combinação ``(parametros_hash_sha256, exit_code, status)`` é o que o
    Determinism_Auditor (Task 11) usa para detectar regressões em invocações
    de ferramentas externas.

    Attributes
    ----------
    nome:
        Nome canônico da Skill invocada (ex.: ``"Skill_Terminal"``).
    invocador:
        Nome do agente que originou a invocação. ``None`` quando a Skill é
        chamada fora do fluxo de Debate (testes, CLI utilitária).
    timestamp:
        ISO 8601 UTC do início da invocação (ex.: ``"2026-05-14T14:00:12Z"``).
    parametros_hash_sha256:
        SHA-256 hex sobre os parâmetros canonicalizados (ver
        :func:`_hash_parametros_sha256`).
    exit_code:
        Código de saída do processo. ``None`` quando o processo nem chegou a
        ser iniciado (ex.: validação prévia falhou). Convenção ``-1`` para
        timeouts e falhas de execução, alinhada ao :class:`ResultadoTerminal`.
    duracao_ms:
        Tempo total entre o início e o fim da invocação (incluindo timeout).
    status:
        Um de ``"skill-ok"``, ``"skill-falha"`` ou ``"skill-timeout"``.
    motivo:
        Texto livre em pt-BR explicando ``status != skill-ok``. ``None``
        quando ``status == "skill-ok"``.
    truncado_stdout:
        ``True`` se ``stdout`` excedeu :data:`_LIMITE_BYTES_POR_CANAL`.
    truncado_stderr:
        ``True`` se ``stderr`` excedeu :data:`_LIMITE_BYTES_POR_CANAL`.
    """

    nome: str
    invocador: Optional[str]
    timestamp: str
    parametros_hash_sha256: str
    exit_code: Optional[int]
    duracao_ms: int
    status: StatusSkill
    motivo: Optional[str]
    truncado_stdout: bool
    truncado_stderr: bool

    def to_dict(self) -> dict[str, Any]:
        """Serializa o registro como ``dict`` plain para uso pelo Recorder.

        A escolha de ``asdict`` preserva a ordem dos campos exatamente como
        declarada na dataclass — relevante para o Determinism_Auditor, que
        compara turnos byte-a-byte após normalização CRLF→LF (R9.3).
        """
        return asdict(self)


__all__ = [
    "_LIMITE_BYTES_POR_CANAL",
    "StatusSkill",
    "_truncar_saida",
    "_hash_parametros_sha256",
    "RegistroAuditoriaSkill",
]
