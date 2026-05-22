"""Skill_Terminal — execução de comandos via ``cmd /c`` no Windows.

Esta Skill cobre o R11.1 do ``requirements.md`` e a linha correspondente
da tabela em ``design.md`` seção 6:

- Shell alvo: ``cmd`` (regra de steering ``plataforma-windows-cmd``;
  PowerShell e bash estão vetados).
- Timeout máximo: 300 segundos por invocação.
- Captura de stdout, stderr e exit code, truncando cada canal a 10 MB.
- Auditoria estruturada via :class:`RegistroAuditoriaSkill`.

Decisões de implementação relevantes:

- Chamamos ``subprocess.run(["cmd", "/c", comando], ...)`` em vez de
  ``shell=True`` para evitar quoting duplo e injeção via metacaracteres do
  Python; o ``cmd /c`` cuida do parsing nativo do Windows e mantém o
  comportamento que o usuário esperaria de digitar o comando direto no
  Prompt de Comando.
- ``capture_output=True`` com ``text=False`` retorna bytes brutos. Decodificamos
  manualmente como UTF-8 com ``errors='replace'``: o ``cmd`` em Windows
  ainda costuma usar cp1252 (ou o codepage configurado em
  ``chcp``), e tentar interpretar o stream como cp1252 quebraria saídas de
  ferramentas modernas (ex.: ``git``) que já emitem UTF-8. ``replace`` é o
  compromisso aceito: preserva a invocação auditável mesmo sob encoding
  inconsistente.
- ``exit_code == -1`` é a convenção interna para sinalizar timeout ou falha
  de spawn (executável ausente). O R11.1 não impõe um valor específico;
  optamos por ``-1`` por ser inalcançável em códigos de saída legítimos do
  Windows (que vão de 0 a 4294967295).
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
# Resultado público
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoTerminal:
    """Saída estruturada de uma invocação de :class:`SkillTerminal`.

    O conteúdo é totalmente serializável e estável para ser persistido pelo
    Council_Recorder no bloco ``skill_invocada`` do turno (design seção 6).
    """

    comando: str
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


class SkillTerminal:
    """Executa comandos no shell ``cmd`` do Windows com timeout e auditoria.

    Parameters
    ----------
    invocador:
        Identificador do agente que está chamando a Skill. Aparece no campo
        ``invocador`` do :class:`RegistroAuditoriaSkill`. Opcional para uso
        em testes e CLIs utilitárias.
    cwd:
        Diretório de trabalho default das invocações. ``None`` significa
        usar o diretório de trabalho atual do processo Python no momento da
        execução (comportamento do :mod:`subprocess`).
    """

    NOME: str = "Skill_Terminal"
    TIMEOUT_MAXIMO_S: float = 300.0
    TIMEOUT_PADRAO_S: float = 60.0

    def __init__(
        self,
        *,
        invocador: Optional[str] = None,
        cwd: Optional[Path] = None,
    ) -> None:
        if cwd is not None:
            cwd_resolvido = Path(cwd)
            if not cwd_resolvido.is_dir():
                raise ValueError(
                    "cwd default deve apontar para um diretório existente; "
                    f"recebido {cwd!r}"
                )
            self._cwd: Optional[Path] = cwd_resolvido
        else:
            self._cwd = None
        self._invocador = invocador

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def executar(
        self,
        comando: str,
        *,
        timeout_s: Optional[float] = None,
        cwd: Optional[Path] = None,
    ) -> ResultadoTerminal:
        """Executa ``comando`` via ``cmd /c`` e devolve um :class:`ResultadoTerminal`.

        Parameters
        ----------
        comando:
            Linha de comando como seria digitada no Prompt do Windows.
            Exemplo: ``"echo ok"``, ``"dir"``, ``"python script.py"``.
        timeout_s:
            Timeout em segundos. ``None`` aplica :attr:`TIMEOUT_PADRAO_S`.
            Valores acima de :attr:`TIMEOUT_MAXIMO_S` levantam ``ValueError``
            antes de qualquer tentativa de execução (R11.1).
        cwd:
            Diretório de trabalho desta invocação específica. Sobrepõe o
            ``cwd`` default passado ao construtor. Se passado e o caminho
            não existir como diretório, ``ValueError`` é levantado.

        Returns
        -------
        ResultadoTerminal
            Sempre retorna — mesmo em caso de timeout, falha de spawn ou
            exit code não-zero. Erros que impedem a execução (parâmetros
            inválidos) são sinalizados via ``ValueError``.
        """
        # 1. Validações pré-execução. ValueError reflete R3.6: sinaliza ao
        #    usuário com mensagem clara o campo problemático.
        if not isinstance(comando, str) or not comando.strip():
            raise ValueError("comando não pode ser vazio")

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
                f"{int(self.TIMEOUT_MAXIMO_S)}s (R11.1); "
                f"recebido {timeout_efetivo}s"
            )

        cwd_efetivo = cwd if cwd is not None else self._cwd
        if cwd_efetivo is not None:
            cwd_efetivo = Path(cwd_efetivo)
            if not cwd_efetivo.is_dir():
                raise ValueError(
                    "cwd deve apontar para um diretório existente; "
                    f"recebido {cwd!r}"
                )

        # 2. Hash dos parâmetros — feito antes da execução para que o registro
        #    de auditoria exista mesmo se a execução falhar logo no spawn.
        parametros_canonicos = {
            "comando": comando,
            "cwd": str(cwd_efetivo) if cwd_efetivo is not None else "<cwd>",
            "timeout_s": timeout_efetivo,
        }
        hash_params = _hash_parametros_sha256(parametros_canonicos)
        timestamp_inicio = _agora_utc_iso()
        inicio_ns = time.monotonic_ns()

        # 3. Execução. ``shell=False`` (default) com ["cmd","/c",comando] é
        #    o caminho recomendado em Windows para evitar quoting duplo.
        try:
            resultado = subprocess.run(
                ["cmd", "/c", comando],
                capture_output=True,
                timeout=timeout_efetivo,
                text=False,  # bytes — decodificamos manualmente abaixo.
                cwd=cwd_efetivo,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duracao_ms = _ms_desde(inicio_ns)
            stdout_bruto = exc.stdout or b""
            stderr_bruto = exc.stderr or b""
            stdout_str, trunc_out = _decodificar_e_truncar(stdout_bruto)
            stderr_str, trunc_err = _decodificar_e_truncar(stderr_bruto)
            return _montar_resultado(
                comando=comando,
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
            # Cobre executável ausente (raro no Windows com cmd presente),
            # diretório inexistente liberado em race, etc.
            duracao_ms = _ms_desde(inicio_ns)
            mensagem = f"falha ao iniciar processo: {exc}"
            return _montar_resultado(
                comando=comando,
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
            comando=comando,
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
# Helpers internos
# ---------------------------------------------------------------------------


def _agora_utc_iso() -> str:
    """ISO 8601 UTC sem microssegundos, com sufixo ``Z`` (auditável)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _ms_desde(inicio_ns: int) -> int:
    """Diferença em milissegundos desde ``inicio_ns`` (``time.monotonic_ns``)."""
    return max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)


def _decodificar_e_truncar(bruto: bytes) -> tuple[str, bool]:
    """Decodifica ``bruto`` como UTF-8 (errors='replace') e trunca a 10 MB.

    Ver discussão de encoding no docstring do módulo: o ``cmd`` ainda emite
    cp1252 em algumas máquinas, mas usar UTF-8 com ``replace`` é o caminho
    que mantém ferramentas modernas (Git, Python) legíveis sem perder
    auditoria nas legadas.
    """
    texto = bruto.decode("utf-8", errors="replace")
    return _truncar_saida(texto, _LIMITE_BYTES_POR_CANAL)


def _montar_resultado(
    *,
    comando: str,
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
) -> ResultadoTerminal:
    """Constrói :class:`ResultadoTerminal` + :class:`RegistroAuditoriaSkill`.

    Encapsula a montagem para evitar duplicação entre os caminhos
    bem-sucedido, timeout e falha de spawn.
    """
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
    return ResultadoTerminal(
        comando=comando,
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
    "ResultadoTerminal",
    "SkillTerminal",
]
