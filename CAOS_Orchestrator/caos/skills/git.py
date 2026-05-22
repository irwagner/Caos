"""Skill_Git — operações Git restritas a uma whitelist de 7 subcomandos.

Cobre o R11.2 do ``requirements.md`` e a linha correspondente da tabela em
``design.md`` seção 6:

- Whitelist estrita: ``branch``, ``checkout``, ``add``, ``commit``, ``tag``,
  ``revert``, ``log`` — qualquer outro subcomando é rejeitado antes da
  execução com :class:`SkillGitNaoAutorizada`.
- Timeout máximo: 120 segundos por operação.
- Captura de stdout, stderr e exit code, truncando cada canal a 10 MB
  (mesma regra do Skill_Terminal).
- Auditoria estruturada via :class:`RegistroAuditoriaSkill`.

A invocação chama o binário ``git`` diretamente — sem passar por ``cmd /c``
— porque ``git.exe`` é um executável nativo no Windows e não precisa do
parser do prompt para ser disparado. Isso evita o risco de injeção via
metacaracteres do shell em ``args``.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from caos.skills._base import (
    _LIMITE_BYTES_POR_CANAL,
    RegistroAuditoriaSkill,
    StatusSkill,
    _hash_parametros_sha256,
    _truncar_saida,
)

# ---------------------------------------------------------------------------
# Whitelist de subcomandos
# ---------------------------------------------------------------------------

#: Tupla imutável dos 7 subcomandos Git permitidos pelo R11.2.
#:
#: Ordem reflete a do ``requirements.md`` para preservar leitura humana ao
#: imprimir mensagens de erro. Para verificações ``in`` o custo é O(7), o
#: que é irrelevante para o caso de uso.
OPERACOES_PERMITIDAS: tuple[str, ...] = (
    "branch",
    "checkout",
    "add",
    "commit",
    "tag",
    "revert",
    "log",
)


def is_subcomando_permitido(subcomando: str) -> bool:
    """Retorna ``True`` se ``subcomando`` consta na whitelist do R11.2.

    Função utilitária exposta para uso externo (CLI ``caos perfil validar``,
    Council_Recorder ao montar comandos, etc.) sem precisar instanciar uma
    :class:`SkillGit`.
    """
    return subcomando in OPERACOES_PERMITIDAS


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------


class SkillGitNaoAutorizada(ValueError):
    """Subcomando Git fora da whitelist do R11.2.

    A subclasse de :class:`ValueError` mantém compatibilidade com chamadores
    que tratam erros de validação como ``ValueError`` — é o mesmo contrato
    aplicado a ``timeout_s`` excedido e a parâmetros vazios.
    """

    def __init__(self, subcomando: str, permitidos: tuple[str, ...]) -> None:
        self.subcomando = subcomando
        # Cópia tupla para evitar mutação acidental do estado interno.
        self.permitidos: tuple[str, ...] = tuple(permitidos)
        mensagem = (
            f"subcomando {subcomando!r} não está na whitelist do Skill_Git "
            f"(R11.2); permitidos: {list(self.permitidos)}"
        )
        super().__init__(mensagem)


# ---------------------------------------------------------------------------
# Resultado público
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoGit:
    """Saída estruturada de uma invocação de :class:`SkillGit`.

    Espelha :class:`caos.skills.terminal.ResultadoTerminal` adicionando
    ``subcomando`` e ``args`` para que o Council_Recorder consiga
    reconstituir a operação Git exata sem reparsear ``comando``.
    """

    comando: str
    subcomando: str
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    truncado_stdout: bool
    truncado_stderr: bool
    duracao_ms: int
    status: StatusSkill
    auditoria: RegistroAuditoriaSkill


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillGit:
    """Executa subcomandos Git autorizados com timeout e auditoria.

    Parameters
    ----------
    invocador:
        Identificador do agente que está chamando a Skill (ex.: ``"Athena"``,
        ``"Hydra_Reference_Sync"``). Aparece no campo ``invocador`` do
        :class:`RegistroAuditoriaSkill`. Opcional.
    repo_dir:
        Repositório alvo das operações. ``None`` significa usar o diretório
        de trabalho atual do processo Python no momento da execução.
    """

    NOME: str = "Skill_Git"
    TIMEOUT_MAXIMO_S: float = 120.0
    TIMEOUT_PADRAO_S: float = 60.0

    def __init__(
        self,
        *,
        invocador: Optional[str] = None,
        repo_dir: Optional[Path] = None,
    ) -> None:
        if repo_dir is not None:
            repo_resolvido = Path(repo_dir)
            if not repo_resolvido.is_dir():
                raise ValueError(
                    "repo_dir deve apontar para um diretório existente; "
                    f"recebido {repo_dir!r}"
                )
            self._repo_dir: Optional[Path] = repo_resolvido
        else:
            self._repo_dir = None
        self._invocador = invocador

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def executar(
        self,
        subcomando: str,
        *args: str,
        timeout_s: Optional[float] = None,
    ) -> ResultadoGit:
        """Executa ``git <subcomando> <args>`` e devolve um :class:`ResultadoGit`.

        Parameters
        ----------
        subcomando:
            Um dos 7 valores em :data:`OPERACOES_PERMITIDAS`. Qualquer outro
            valor levanta :class:`SkillGitNaoAutorizada` antes de qualquer
            tentativa de execução.
        args:
            Argumentos posicionais passados ao Git. Strings apenas;
            é responsabilidade do chamador validar conteúdo (ex.: nome de
            branch, mensagem de commit).
        timeout_s:
            Timeout em segundos. ``None`` aplica :attr:`TIMEOUT_PADRAO_S`.
            Valores acima de :attr:`TIMEOUT_MAXIMO_S` levantam ``ValueError``.

        Returns
        -------
        ResultadoGit
            Sempre retorna em caminhos válidos — mesmo quando o ``git`` em
            si retorna exit code não-zero (ex.: ``git log`` em repo vazio).
            O chamador inspeciona ``status`` para decidir.
        """
        # 1. Validação da whitelist — antes de qualquer outra checagem para
        #    que o erro mais informativo seja o primeiro a aparecer.
        if not isinstance(subcomando, str) or not subcomando:
            raise ValueError("subcomando não pode ser vazio")
        if not is_subcomando_permitido(subcomando):
            raise SkillGitNaoAutorizada(subcomando, OPERACOES_PERMITIDAS)

        # 2. Validação de tipos dos args.
        for indice, arg in enumerate(args):
            if not isinstance(arg, str):
                raise TypeError(
                    "todos os args devem ser strings; "
                    f"args[{indice}]={arg!r} é {type(arg).__name__}"
                )

        # 3. Timeout dentro do limite do R11.2 (120s).
        timeout_efetivo = (
            self.TIMEOUT_PADRAO_S if timeout_s is None else float(timeout_s)
        )
        if timeout_efetivo <= 0:
            raise ValueError(
                f"timeout_s deve ser positivo; recebido {timeout_s!r}"
            )
        if timeout_efetivo > self.TIMEOUT_MAXIMO_S:
            raise ValueError(
                "timeout_s excede o limite de "
                f"{int(self.TIMEOUT_MAXIMO_S)}s (R11.2); "
                f"recebido {timeout_efetivo}s"
            )

        cmd = ["git", subcomando, *args]
        comando_str = " ".join(cmd)

        # 4. Hash dos parâmetros antes da execução, para que a auditoria
        #    sobreviva a falhas de spawn.
        parametros_canonicos = {
            "subcomando": subcomando,
            "args": list(args),
            "repo_dir": (
                str(self._repo_dir) if self._repo_dir is not None else "<cwd>"
            ),
            "timeout_s": timeout_efetivo,
        }
        hash_params = _hash_parametros_sha256(parametros_canonicos)
        timestamp_inicio = _agora_utc_iso()
        inicio_ns = time.monotonic_ns()

        try:
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_efetivo,
                text=False,
                cwd=self._repo_dir,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duracao_ms = _ms_desde(inicio_ns)
            stdout_str, trunc_out = _decodificar_e_truncar(exc.stdout or b"")
            stderr_str, trunc_err = _decodificar_e_truncar(exc.stderr or b"")
            return _montar_resultado(
                comando=comando_str,
                subcomando=subcomando,
                args=args,
                exit_code=-1,
                stdout=stdout_str,
                stderr=stderr_str,
                truncado_stdout=trunc_out,
                truncado_stderr=trunc_err,
                duracao_ms=duracao_ms,
                status="skill-timeout",
                motivo=(
                    "timeout excedido após "
                    f"{int(timeout_efetivo)}s"
                ),
                nome=self.NOME,
                invocador=self._invocador,
                timestamp=timestamp_inicio,
                hash_params=hash_params,
            )
        except OSError as exc:
            # ``git`` não encontrado no PATH é o caso mais provável aqui.
            duracao_ms = _ms_desde(inicio_ns)
            mensagem = f"falha ao iniciar git: {exc}"
            return _montar_resultado(
                comando=comando_str,
                subcomando=subcomando,
                args=args,
                exit_code=-1,
                stdout="",
                stderr=mensagem,
                truncado_stdout=False,
                truncado_stderr=False,
                duracao_ms=duracao_ms,
                status="skill-falha",
                motivo=mensagem,
                nome=self.NOME,
                invocador=self._invocador,
                timestamp=timestamp_inicio,
                hash_params=hash_params,
            )

        duracao_ms = _ms_desde(inicio_ns)
        stdout_str, trunc_out = _decodificar_e_truncar(resultado.stdout or b"")
        stderr_str, trunc_err = _decodificar_e_truncar(resultado.stderr or b"")

        if resultado.returncode == 0:
            status: StatusSkill = "skill-ok"
            motivo = None
        else:
            status = "skill-falha"
            motivo = f"exit_code={resultado.returncode}"

        return _montar_resultado(
            comando=comando_str,
            subcomando=subcomando,
            args=args,
            exit_code=resultado.returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            truncado_stdout=trunc_out,
            truncado_stderr=trunc_err,
            duracao_ms=duracao_ms,
            status=status,
            motivo=motivo,
            nome=self.NOME,
            invocador=self._invocador,
            timestamp=timestamp_inicio,
            hash_params=hash_params,
        )


# ---------------------------------------------------------------------------
# Helpers internos (espelham os de terminal.py — mantidos locais para evitar
# dependência cruzada entre Skills).
# ---------------------------------------------------------------------------


def _agora_utc_iso() -> str:
    """ISO 8601 UTC sem microssegundos, com sufixo ``Z``."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _ms_desde(inicio_ns: int) -> int:
    return max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)


def _decodificar_e_truncar(bruto: bytes) -> tuple[str, bool]:
    texto = bruto.decode("utf-8", errors="replace")
    return _truncar_saida(texto, _LIMITE_BYTES_POR_CANAL)


def _montar_resultado(
    *,
    comando: str,
    subcomando: str,
    args: tuple[str, ...],
    exit_code: int,
    stdout: str,
    stderr: str,
    truncado_stdout: bool,
    truncado_stderr: bool,
    duracao_ms: int,
    status: StatusSkill,
    motivo: Optional[str],
    nome: str,
    invocador: Optional[str],
    timestamp: str,
    hash_params: str,
) -> ResultadoGit:
    auditoria = RegistroAuditoriaSkill(
        nome=nome,
        invocador=invocador,
        timestamp=timestamp,
        parametros_hash_sha256=hash_params,
        exit_code=exit_code,
        duracao_ms=duracao_ms,
        status=status,
        motivo=motivo,
        truncado_stdout=truncado_stdout,
        truncado_stderr=truncado_stderr,
    )
    return ResultadoGit(
        comando=comando,
        subcomando=subcomando,
        args=tuple(args),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        truncado_stdout=truncado_stdout,
        truncado_stderr=truncado_stderr,
        duracao_ms=duracao_ms,
        status=status,
        auditoria=auditoria,
    )


__all__ = [
    "OPERACOES_PERMITIDAS",
    "ResultadoGit",
    "SkillGit",
    "SkillGitNaoAutorizada",
    "is_subcomando_permitido",
]
