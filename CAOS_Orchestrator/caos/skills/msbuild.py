"""Skill_MSBuild — invocação do MSBuild sobre projetos NinjaScript.

Cobre o R11.3 do ``requirements.md`` e a linha correspondente da tabela em
``design.md`` seção 6 (Skill_MSBuild):

- Invoca o ``MSBuild.exe`` diretamente (sem ``cmd /c``) sobre um ``.csproj``
  localizado em ``04_CODIGO/ninjascript/`` por padrão.
- Timeout máximo: 600 segundos por invocação (R11.3).
- Captura de stdout/stderr truncada a 10 MB por canal (compatível com a
  política das demais Skills).
- Parse estruturado de erros e warnings em :class:`ItemMSBuild` com campos
  ``arquivo``, ``linha``, ``coluna``, ``codigo``, ``mensagem`` e ``severidade``.
- Auditoria estruturada via :class:`RegistroAuditoriaSkill`.

Decisões de implementação relevantes:

- **Projeto inexistente**: quando nenhum ``.csproj`` é encontrado em
  ``diretorio_projeto`` (não-recursivo), retorna :class:`ResultadoMSBuild`
  com ``csproj=None``, ``exit_code=-2``, ``status="skill-ok"``,
  ``motivo="csproj-ausente"``. O ``.csproj`` ativo só será criado em Spec 3
  (ver nota de implementação no ``tasks.md``); ainda assim o adapter já
  precisa existir para o Hermes (Task 16+) e os testes determinísticos.
- **Múltiplos ``.csproj``**: usa o primeiro alfabeticamente (ordem POSIX
  estável) e adiciona um warning textual ao ``stderr`` para que o caller
  perceba a ambiguidade. A política de reorganização do projeto só será
  endereçada quando o build virar realmente parte do fluxo do Conselho.
- **Parse de saída**: regex multiline tolerante. O formato canônico do
  MSBuild é ``arquivo(linha,coluna): severidade codigo: mensagem [projeto]``.
  Aceitamos também o formato sem coluna (``arquivo(linha):``) emitido por
  algumas versões antigas. Linhas que não casam são silenciosamente
  ignoradas — o objetivo é extrair sinal estruturado, não preservar 100%
  da saída textual (essa fica em ``stdout`` para auditoria).
- **Codepage**: como no Skill_Terminal/Skill_Git, decodificamos o stream
  como UTF-8 com ``errors='replace'``. MSBuild moderno emite UTF-8 quando
  ``/utf8output`` é passado ou quando a console code page é compatível.
- **Falha de spawn**: ``OSError`` (executável ausente) retorna
  ``status="skill-falha"``, ``exit_code=-1`` e ``motivo`` descritivo, sem
  levantar exceção — preserva auditabilidade.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from caos.skills._base import (
    _LIMITE_BYTES_POR_CANAL,
    RegistroAuditoriaSkill,
    StatusSkill,
    _hash_parametros_sha256,
    _truncar_saida,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Timeout máximo permitido pelo R11.3 (10 minutos).
TIMEOUT_MAXIMO_S: float = 600.0

#: Timeout default quando o caller não especifica.
TIMEOUT_PADRAO_S: float = 120.0

#: Pasta default sugerida pelo design seção 6 (Skill_MSBuild).
DIRETORIO_PROJETO_PADRAO: Path = Path("04_CODIGO/ninjascript")

#: Sentinela para ``exit_code`` quando o ``.csproj`` não existe.
_EXIT_CODE_CSPROJ_AUSENTE: int = -2

#: Sentinela para ``exit_code`` quando o processo nem chegou a iniciar
#: (timeout antes do término ou OSError no spawn).
_EXIT_CODE_FALHA_GENERICA: int = -1

#: Severidades reconhecidas pelo parser de saída do MSBuild.
SeveridadeItem = Literal["error", "warning"]

# Regex para parse de erros/warnings do MSBuild. Tolerante a:
# - presença ou ausência de coluna: ``Arquivo.cs(10,5)`` ou ``Arquivo.cs(10)``;
# - sufixo opcional ``[Caminho.csproj]`` que o MSBuild adiciona em build
#   multiprojeto;
# - espaço em branco após ``severidade``.
#
# Grupos nomeados:
#   arquivo   — caminho do .cs (qualquer string sem '(' antes do paren).
#   linha     — inteiro positivo.
#   coluna    — inteiro positivo (opcional).
#   severidade — "error" ou "warning".
#   codigo    — identificador no formato CS####, MSB####, etc.
#   mensagem  — texto da mensagem (sem o sufixo entre colchetes).
_REGEX_ITEM_MSBUILD = re.compile(
    r"^(?P<arquivo>[^()\r\n]+?)"
    r"\((?P<linha>\d+)(?:,(?P<coluna>\d+))?\):\s+"
    r"(?P<severidade>error|warning)\s+"
    r"(?P<codigo>[A-Za-z]+\d+):\s+"
    r"(?P<mensagem>.*?)"
    r"(?:\s+\[[^\[\]\r\n]+\])?\s*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Modelos públicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemMSBuild:
    """Erro ou warning estruturado extraído da saída do MSBuild.

    Espelha a tabela do design seção 6 (``cada item com (arquivo, linha,
    codigo, mensagem)``) e adiciona ``coluna`` quando disponível para
    facilitar a navegação no editor pelo Hermes.

    Attributes
    ----------
    arquivo:
        Caminho como reportado pelo MSBuild. Pode ser ``None`` em itens
        gerados por uma severidade global (raro), preservando legibilidade.
    linha:
        Número da linha (1-based). ``None`` quando não reportado.
    coluna:
        Coluna da posição (1-based). ``None`` quando o formato omite.
    codigo:
        Código MSBuild/Roslyn (ex.: ``CS0103``, ``MSB3027``).
    mensagem:
        Texto da mensagem, já sem o sufixo ``[Caminho.csproj]``.
    severidade:
        ``"error"`` ou ``"warning"``.
    """

    arquivo: Optional[str]
    linha: Optional[int]
    coluna: Optional[int]
    codigo: str
    mensagem: str
    severidade: SeveridadeItem


@dataclass(frozen=True)
class ResultadoMSBuild:
    """Saída estruturada de :meth:`SkillMSBuild.executar`.

    Attributes
    ----------
    diretorio_projeto:
        Diretório onde o ``.csproj`` foi procurado.
    csproj:
        Arquivo ``.csproj`` efetivamente usado. ``None`` quando o projeto
        ainda não existe (ver ``motivo='csproj-ausente'``).
    exit_code:
        Código de saída do MSBuild. ``-1`` em timeout/falha de spawn,
        ``-2`` quando o ``.csproj`` não foi encontrado.
    stdout, stderr:
        Saídas truncadas a 10 MB por canal (UTF-8 com replace).
    truncado_stdout, truncado_stderr:
        Indicam se a truncagem ocorreu de fato.
    erros, warnings:
        Listas de :class:`ItemMSBuild` parseados a partir do ``stdout``.
    duracao_ms:
        Tempo total entre o início e o fim da invocação.
    status:
        ``"skill-ok"`` (sucesso ou csproj ausente), ``"skill-falha"`` (exit
        diferente de zero, falha de spawn) ou ``"skill-timeout"``.
    auditoria:
        :class:`RegistroAuditoriaSkill` para o Council_Recorder.
    motivo:
        Texto livre em pt-BR explicando ``status != skill-ok`` ou
        situações especiais (``"csproj-ausente"``, ``"multiplos-csproj"``).
    """

    diretorio_projeto: Path
    csproj: Optional[Path]
    exit_code: int
    stdout: str
    stderr: str
    truncado_stdout: bool
    truncado_stderr: bool
    erros: list[ItemMSBuild] = field(default_factory=list)
    warnings: list[ItemMSBuild] = field(default_factory=list)
    duracao_ms: int = 0
    status: StatusSkill = "skill-ok"
    auditoria: Optional[RegistroAuditoriaSkill] = None
    motivo: Optional[str] = None


class SkillMSBuildError(RuntimeError):
    """Falha que impede o build de sequer ser tentado.

    Reservada para erros de **validação** (ex.: ``timeout_s`` fora do limite
    do R11.3); ``exit_code != 0`` do MSBuild **NÃO** levanta esta exceção,
    sai como :class:`ResultadoMSBuild` com ``status='skill-falha'``.
    """


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillMSBuild:
    """Invoca o MSBuild sobre o projeto NinjaScript com timeout e auditoria.

    Parameters
    ----------
    invocador:
        Identificador do agente que chama a Skill (tipicamente ``"Hermes"``).
        Aparece no campo ``invocador`` do :class:`RegistroAuditoriaSkill`.
    diretorio_projeto:
        Diretório onde procurar o ``.csproj`` (default ``04_CODIGO/ninjascript``).
        Deve existir como diretório.
    msbuild_executavel:
        Caminho do executável do MSBuild. Default ``"MSBuild.exe"`` (lookup
        no PATH). Útil para injetar um stub (script Python) em testes.
    """

    NOME: str = "Skill_MSBuild"
    TIMEOUT_MAXIMO_S: float = TIMEOUT_MAXIMO_S
    TIMEOUT_PADRAO_S: float = TIMEOUT_PADRAO_S

    def __init__(
        self,
        *,
        diretorio_projeto: Path,
        invocador: Optional[str] = None,
        msbuild_executavel: Optional[str] = None,
    ) -> None:
        if diretorio_projeto is None:
            raise ValueError("diretorio_projeto é obrigatório")
        diretorio_resolvido = Path(diretorio_projeto)
        if not diretorio_resolvido.is_dir():
            raise ValueError(
                "diretorio_projeto deve apontar para um diretório existente; "
                f"recebido {diretorio_projeto!r}"
            )
        self._diretorio_projeto = diretorio_resolvido
        self._invocador = invocador
        self._msbuild_executavel = (
            msbuild_executavel if msbuild_executavel else "MSBuild.exe"
        )

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def diretorio_projeto(self) -> Path:
        """Diretório alvo da busca por ``.csproj``."""
        return self._diretorio_projeto

    @property
    def invocador(self) -> Optional[str]:
        """Agente invocador, se informado no construtor."""
        return self._invocador

    @property
    def msbuild_executavel(self) -> str:
        """Caminho ou nome do binário do MSBuild que será invocado."""
        return self._msbuild_executavel

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def executar(
        self,
        *,
        target: Optional[str] = None,
        configuration: str = "Release",
        timeout_s: Optional[float] = None,
    ) -> ResultadoMSBuild:
        """Compila o ``.csproj`` em :attr:`diretorio_projeto`.

        Parameters
        ----------
        target:
            Target opcional (ex.: ``"Build"``, ``"Rebuild"``). Quando
            informado, é passado como ``/t:<target>``.
        configuration:
            Configuração de build (default ``"Release"``). Passada como
            ``/p:Configuration=<valor>``.
        timeout_s:
            Timeout em segundos. ``None`` aplica :attr:`TIMEOUT_PADRAO_S`.
            Valores acima de :attr:`TIMEOUT_MAXIMO_S` levantam
            ``ValueError`` antes de qualquer tentativa de execução (R11.3).

        Returns
        -------
        ResultadoMSBuild
            Sempre retorna em parâmetros válidos — mesmo em caso de timeout,
            falha de spawn ou ``.csproj`` ausente.
        """
        # 1. Validação de timeout (R11.3).
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
                f"{int(self.TIMEOUT_MAXIMO_S)}s (R11.3); "
                f"recebido {timeout_efetivo}s"
            )

        # 2. Validação de tipos básicos.
        if not isinstance(configuration, str) or not configuration:
            raise ValueError(
                "configuration deve ser string não vazia; "
                f"recebido {configuration!r}"
            )
        if target is not None and (not isinstance(target, str) or not target):
            raise ValueError(
                "target deve ser string não vazia ou None; "
                f"recebido {target!r}"
            )

        # 3. Hash dos parâmetros — calculado antes da execução para que a
        #    auditoria sobreviva a falhas de spawn.
        parametros_canonicos = {
            "diretorio_projeto": str(self._diretorio_projeto),
            "msbuild_executavel": self._msbuild_executavel,
            "target": target,
            "configuration": configuration,
            "timeout_s": timeout_efetivo,
        }
        hash_params = _hash_parametros_sha256(parametros_canonicos)
        timestamp_inicio = _agora_utc_iso()
        inicio_ns = time.monotonic_ns()

        # 4. Localiza o .csproj no diretório (não-recursivo). Ordena
        #    alfabeticamente para determinismo.
        candidatos = sorted(
            (p for p in self._diretorio_projeto.glob("*.csproj") if p.is_file()),
            key=lambda p: p.name,
        )

        # 5. Caso "csproj-ausente": retorno especial sem falhar (R11.3 + nota
        #    no design seção 6 — o .csproj só virá em Spec 3).
        if not candidatos:
            duracao_ms = _ms_desde(inicio_ns)
            return _montar_resultado(
                diretorio_projeto=self._diretorio_projeto,
                csproj=None,
                exit_code=_EXIT_CODE_CSPROJ_AUSENTE,
                stdout="",
                stderr="",
                truncado_stdout=False,
                truncado_stderr=False,
                erros=[],
                warnings=[],
                duracao_ms=duracao_ms,
                status="skill-ok",
                motivo="csproj-ausente",
                nome=self.NOME,
                invocador=self._invocador,
                timestamp=timestamp_inicio,
                hash_params=hash_params,
            )

        csproj_alvo = candidatos[0]

        # 6. Aviso textual de múltiplos .csproj — entra no stderr final para
        #    ser preservado na auditoria sem falhar a invocação.
        warning_multiplos: Optional[str] = None
        if len(candidatos) > 1:
            outros = ", ".join(p.name for p in candidatos[1:])
            warning_multiplos = (
                f"AVISO: múltiplos .csproj encontrados em {self._diretorio_projeto}; "
                f"usando {csproj_alvo.name}; ignorados: {outros}\n"
            )

        # 7. Constrói args para o MSBuild. Invocação direta (sem cmd /c).
        args: list[str] = [
            self._msbuild_executavel,
            str(csproj_alvo),
            f"/p:Configuration={configuration}",
            "/nologo",
            "/v:minimal",
        ]
        if target is not None:
            args.append(f"/t:{target}")

        try:
            resultado = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout_efetivo,
                text=False,
                cwd=self._diretorio_projeto,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duracao_ms = _ms_desde(inicio_ns)
            stdout_str, trunc_out = _decodificar_e_truncar(exc.stdout or b"")
            stderr_bruto = exc.stderr or b""
            stderr_str, trunc_err = _decodificar_e_truncar(stderr_bruto)
            if warning_multiplos:
                stderr_str = warning_multiplos + stderr_str
            return _montar_resultado(
                diretorio_projeto=self._diretorio_projeto,
                csproj=csproj_alvo,
                exit_code=_EXIT_CODE_FALHA_GENERICA,
                stdout=stdout_str,
                stderr=stderr_str,
                truncado_stdout=trunc_out,
                truncado_stderr=trunc_err,
                erros=_extrair_itens(stdout_str, severidade="error"),
                warnings=_extrair_itens(stdout_str, severidade="warning"),
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
            # Cobre executável ausente (MSBuild fora do PATH), permissão
            # negada, etc. Retorno tipificado para preservar auditoria.
            duracao_ms = _ms_desde(inicio_ns)
            mensagem = f"falha ao iniciar msbuild: {exc}"
            stderr_str = mensagem
            if warning_multiplos:
                stderr_str = warning_multiplos + stderr_str
            return _montar_resultado(
                diretorio_projeto=self._diretorio_projeto,
                csproj=csproj_alvo,
                exit_code=_EXIT_CODE_FALHA_GENERICA,
                stdout="",
                stderr=stderr_str,
                truncado_stdout=False,
                truncado_stderr=False,
                erros=[],
                warnings=[],
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
        if warning_multiplos:
            stderr_str = warning_multiplos + stderr_str

        erros = _extrair_itens(stdout_str, severidade="error")
        warnings = _extrair_itens(stdout_str, severidade="warning")

        if resultado.returncode == 0:
            status: StatusSkill = "skill-ok"
            motivo: Optional[str] = (
                "multiplos-csproj" if warning_multiplos else None
            )
        else:
            status = "skill-falha"
            motivo = f"exit_code={resultado.returncode}"

        return _montar_resultado(
            diretorio_projeto=self._diretorio_projeto,
            csproj=csproj_alvo,
            exit_code=resultado.returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            truncado_stdout=trunc_out,
            truncado_stderr=trunc_err,
            erros=erros,
            warnings=warnings,
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
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _ms_desde(inicio_ns: int) -> int:
    """Diferença em milissegundos desde ``inicio_ns`` (``time.monotonic_ns``)."""
    return max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)


def _decodificar_e_truncar(bruto: bytes) -> tuple[str, bool]:
    """Decodifica ``bruto`` como UTF-8 (``errors='replace'``) e trunca a 10 MB."""
    texto = bruto.decode("utf-8", errors="replace")
    return _truncar_saida(texto, _LIMITE_BYTES_POR_CANAL)


def _extrair_itens(stdout: str, *, severidade: SeveridadeItem) -> list[ItemMSBuild]:
    """Aplica o regex de parse e devolve a lista de :class:`ItemMSBuild`.

    Filtra pela ``severidade`` solicitada (``error`` ou ``warning``).
    Linhas que não casam com o padrão são ignoradas — a saída textual
    completa permanece em ``stdout`` para auditoria humana.
    """
    if not stdout:
        return []

    itens: list[ItemMSBuild] = []
    for match in _REGEX_ITEM_MSBUILD.finditer(stdout):
        if match.group("severidade") != severidade:
            continue
        arquivo = match.group("arquivo").strip()
        linha_str = match.group("linha")
        coluna_str = match.group("coluna")
        try:
            linha = int(linha_str) if linha_str else None
        except ValueError:  # pragma: no cover - regex já garante \d+
            linha = None
        try:
            coluna = int(coluna_str) if coluna_str else None
        except ValueError:  # pragma: no cover - regex já garante \d+
            coluna = None
        codigo = match.group("codigo")
        mensagem = match.group("mensagem").strip()
        itens.append(
            ItemMSBuild(
                arquivo=arquivo or None,
                linha=linha,
                coluna=coluna,
                codigo=codigo,
                mensagem=mensagem,
                severidade=severidade,
            )
        )
    return itens


def _montar_resultado(
    *,
    diretorio_projeto: Path,
    csproj: Optional[Path],
    exit_code: int,
    stdout: str,
    stderr: str,
    truncado_stdout: bool,
    truncado_stderr: bool,
    erros: list[ItemMSBuild],
    warnings: list[ItemMSBuild],
    duracao_ms: int,
    status: StatusSkill,
    motivo: Optional[str],
    nome: str,
    invocador: Optional[str],
    timestamp: str,
    hash_params: str,
) -> ResultadoMSBuild:
    """Monta :class:`ResultadoMSBuild` + :class:`RegistroAuditoriaSkill`.

    Encapsula a montagem para evitar duplicação entre os caminhos
    bem-sucedido, csproj-ausente, timeout e falha de spawn.
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
    return ResultadoMSBuild(
        diretorio_projeto=diretorio_projeto,
        csproj=csproj,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        truncado_stdout=truncado_stdout,
        truncado_stderr=truncado_stderr,
        erros=erros,
        warnings=warnings,
        duracao_ms=duracao_ms,
        status=status,
        auditoria=auditoria,
        motivo=motivo,
    )


__all__ = [
    "DIRETORIO_PROJETO_PADRAO",
    "ItemMSBuild",
    "ResultadoMSBuild",
    "SeveridadeItem",
    "SkillMSBuild",
    "SkillMSBuildError",
    "TIMEOUT_MAXIMO_S",
    "TIMEOUT_PADRAO_S",
]
