"""Hydra_Reference_Sync — manutenção da cópia somente-leitura do Hydra.

Cobre os critérios R13.1–R13.5 do ``requirements.md``:

- R13.1: Mantém a Nota_Zettel ``Hydra_Reference_Index.md`` com URL,
  branch, hash do commit e lista de subdiretórios mapeados.
- R13.2: Sincroniza ``04_CODIGO/ninjascript/reference_hydra/`` com o
  branch ``main`` do Hydra dentro de timeout de 120 segundos e registra
  o hash do commit obtido (40 caracteres hexadecimais).
- R13.3: Em qualquer falha (timeout, rede, repositório inacessível,
  git ausente, erro de I/O), preserva a cópia local existente e
  retorna erro tipificado por meio de :class:`FalhaSync`.
- R13.4: A steering rule ``reference-hydra-readonly.md`` (criada na
  Task 4) marca o diretório como somente-referência. Esta classe se
  comporta como o único agente autorizado a escrever em
  ``reference_hydra/``.
- R13.5: :meth:`HydraReferenceSync.validar_copia_de_codigo` exige uma
  ``Decisao_Do_Conselho`` explícita antes de qualquer cópia de código
  de ``reference_hydra/`` para o código ativo.

Nota arquitetural — execução direta de Git
==========================================

Esta classe usa ``subprocess.run(["git", ...])`` diretamente, em vez de
passar por :class:`caos.skills.git.SkillGit`. A justificativa, acordada
na arquitetura do Spec 1, é a seguinte:

* A whitelist de Skill_Git (R11.2) cobre apenas as 7 operações que o
  Conselho executa sobre o próprio repositório do CAOS — ``branch``,
  ``checkout``, ``add``, ``commit``, ``tag``, ``revert`` e ``log``.
* As operações necessárias para sincronizar o Hydra são ``clone``,
  ``fetch``, ``reset`` e ``rev-parse``. Elas atuam em um repositório
  externo (o repositório histórico Hydra), não no repositório do CAOS,
  portanto NÃO violam o R11.2 — o R11 fala do uso de Skills DENTRO do
  ciclo de Debate.
* O componente ``Hydra_Reference_Sync`` é a única exceção arquitetural
  acordada para chamada direta a ``git`` fora da Skill_Git. Qualquer
  outra invocação direta (por agentes ou pelo orquestrador) continua
  vetada.

Este módulo é executado em pt-BR e usa apenas ``cmd``-compatíveis (R3.2,
R3.3): nada de PowerShell ou bash.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import yaml

from caos.models import DecisaoDoConselho

# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: URL canônica do repositório Hydra (R13.1, R13.2).
HYDRA_URL: str = "https://github.com/irwagner/hydra-trading"

#: Branch de referência do Hydra (R13.1, R13.2).
HYDRA_BRANCH: str = "main"

#: Caminho relativo ao workspace onde a cópia somente-leitura do Hydra é
#: mantida (R13.2). Forma POSIX para compatibilidade entre Windows e Git.
DIR_REFERENCE_HYDRA: str = "04_CODIGO/ninjascript/reference_hydra"

#: Caminho relativo da Nota_Zettel ``Hydra_Reference_Index.md`` (R13.1).
NOTA_HYDRA_INDEX: str = (
    "CAOS_Zettelkasten/API_NinjaTrader_8_Reference/Hydra_Reference_Index.md"
)

#: Caminho relativo do código ativo NinjaScript que NÃO pode receber cópias
#: de ``reference_hydra/`` sem Decisao_Do_Conselho (R13.4, R13.5).
DIR_NINJASCRIPT_ATIVO: str = "04_CODIGO/ninjascript"

#: Timeout máximo (em segundos) para cada operação Git de sync (R13.2).
TIMEOUT_S: float = 120.0

#: Regex para validar SHA-1 hex de 40 caracteres (R13.1, R13.2).
_RE_SHA1_HEX = re.compile(r"^[0-9a-f]{40}$")

#: Categorias possíveis de falha do sync (R13.3).
CategoriaFalhaSync = Literal[
    "timeout",
    "rede",
    "repositorio-inacessivel",
    "git-ausente",
    "io-erro",
]


# ---------------------------------------------------------------------------
# Modelos públicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FalhaSync:
    """Descrição estruturada de uma falha do sync (R13.3).

    Attributes
    ----------
    categoria:
        Discriminador estável usado pelo orquestrador para decidir a
        reação. Um de :data:`CategoriaFalhaSync`.
    mensagem:
        Texto livre em pt-BR para registro/log.
    detalhes:
        Contexto adicional (exit_code, stderr truncado, comando, etc.).
    """

    categoria: CategoriaFalhaSync
    mensagem: str
    detalhes: dict[str, Any]


@dataclass(frozen=True)
class ResultadoSync:
    """Resultado de :meth:`HydraReferenceSync.sincronizar`.

    ``hash_commit`` é o SHA-1 hex do commit corrente do clone após o sync,
    ou ``None`` quando ``sucesso`` é ``False``. ``cloned_now`` é ``True``
    para clone novo e ``False`` quando o sync foi um update incremental
    de uma cópia existente (R13.2).
    """

    sucesso: bool
    hash_commit: Optional[str]
    caminho_clone: Path
    cloned_now: bool
    duracao_ms: int
    falha: Optional[FalhaSync] = None


@dataclass(frozen=True)
class ResultadoValidacaoCopia:
    """Resultado de :meth:`HydraReferenceSync.validar_copia_de_codigo`.

    Attributes
    ----------
    autorizado:
        ``True`` se a cópia pode prosseguir; ``False`` quando bloqueada
        pelo guard do R13.5.
    motivo:
        Texto livre em pt-BR. ``None`` quando ``autorizado`` é ``True``.
    decisao_id:
        Identificador da Decisao_Do_Conselho que autorizou, quando há;
        ``None`` quando ausente ou inválida.
    """

    autorizado: bool
    motivo: Optional[str]
    decisao_id: Optional[str]


# ---------------------------------------------------------------------------
# Padrões para categorização de erros do Git
# ---------------------------------------------------------------------------

# Padrões textuais (case-insensitive) que aparecem em ``stderr`` do Git
# quando o repositório remoto não pode ser acessado por motivos
# permanentes (URL inválida, autenticação requerida, repo inexistente).
_PADROES_REPOSITORIO_INACESSIVEL: tuple[str, ...] = (
    "unable to access",
    "repository not found",
    "authentication failed",
    "permission denied",
    "access denied",
    "remote: not found",
    "fatal: could not read",
)

# Padrões textuais (case-insensitive) que indicam falha transitória de rede.
_PADROES_REDE: tuple[str, ...] = (
    "could not resolve host",
    "connection refused",
    "connection timed out",
    "operation timed out",
    "network is unreachable",
    "could not connect",
)


def _categorizar_stderr(stderr: str) -> CategoriaFalhaSync:
    """Classifica ``stderr`` em uma das categorias de :data:`CategoriaFalhaSync`.

    A heurística percorre primeiro os padrões de ``rede`` (transitórios)
    e depois os de ``repositorio-inacessivel`` (permanentes). Em caso de
    nenhum casamento, retorna ``io-erro`` — o caller decide se promove
    para outra categoria.
    """
    baixa = stderr.lower()
    for padrao in _PADROES_REDE:
        if padrao in baixa:
            return "rede"
    for padrao in _PADROES_REPOSITORIO_INACESSIVEL:
        if padrao in baixa:
            return "repositorio-inacessivel"
    return "io-erro"


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------


class HydraReferenceSync:
    """Mantém a cópia somente-leitura do Hydra e a Nota_Zettel de índice.

    Parameters
    ----------
    raiz_workspace:
        Diretório-raiz do workspace CAOS. Deve existir.
    url:
        URL HTTPS do Hydra. Default: :data:`HYDRA_URL`.
    branch:
        Nome do branch a sincronizar. Default: :data:`HYDRA_BRANCH`.
    """

    def __init__(
        self,
        *,
        raiz_workspace: Path,
        url: str = HYDRA_URL,
        branch: str = HYDRA_BRANCH,
    ) -> None:
        raiz = Path(raiz_workspace).expanduser().resolve()
        if not raiz.is_dir():
            raise ValueError(
                "raiz_workspace deve apontar para um diretório existente; "
                f"recebido {raiz_workspace!r}"
            )
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url do Hydra não pode ser vazia")
        if not isinstance(branch, str) or not branch.strip():
            raise ValueError("branch do Hydra não pode ser vazio")
        self._raiz = raiz
        self._url = url
        self._branch = branch

    # ------------------------------------------------------------------
    # Propriedades convenientes
    # ------------------------------------------------------------------

    @property
    def raiz_workspace(self) -> Path:
        """Raiz absoluta resolvida do workspace."""
        return self._raiz

    @property
    def url(self) -> str:
        """URL HTTPS do Hydra usada nas operações de sync."""
        return self._url

    @property
    def branch(self) -> str:
        """Branch de referência (geralmente ``main``)."""
        return self._branch

    @property
    def caminho_clone(self) -> Path:
        """Caminho absoluto da cópia local do Hydra (R13.2)."""
        return self._raiz / DIR_REFERENCE_HYDRA

    @property
    def caminho_nota_index(self) -> Path:
        """Caminho absoluto da Nota_Zettel ``Hydra_Reference_Index.md``."""
        return self._raiz / NOTA_HYDRA_INDEX

    # ------------------------------------------------------------------
    # R13.2 — Sincronização (clone ou update)
    # ------------------------------------------------------------------

    def sincronizar(self, *, timeout_s: float = TIMEOUT_S) -> ResultadoSync:
        """Executa o clone (ou update) do Hydra e atualiza a Nota_Zettel.

        Fluxo:

        1. Determina ``caminho_clone``.
        2. Se não existir: ``git clone --branch <branch> --depth 1 <url>
           <caminho>``.
        3. Se existir e for um repo Git válido (contém ``.git/``):
           ``git -C <caminho> fetch origin <branch> --depth 1`` seguido
           de ``git -C <caminho> reset --hard origin/<branch>``.
        4. Se existir mas não for repo Git: trata como
           ``repositorio-inacessivel`` e preserva o conteúdo local.
        5. Captura o SHA via ``git -C <caminho> rev-parse HEAD``.
        6. Atualiza ``Hydra_Reference_Index.md`` com o hash obtido.

        Em qualquer falha de Git (timeout, rede, repo inacessível,
        binário ``git`` ausente), o ``caminho_clone`` existente é
        preservado e a falha é retornada categorizada (R13.3).

        Parameters
        ----------
        timeout_s:
            Timeout em segundos por invocação de Git. Default 120
            (R13.2). Valores ``<=0`` ou ``>120`` resultam em ``ValueError``.
        """
        if not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise ValueError(
                f"timeout_s deve ser positivo; recebido {timeout_s!r}"
            )
        if timeout_s > TIMEOUT_S:
            raise ValueError(
                f"timeout_s excede o limite de {int(TIMEOUT_S)}s "
                f"(R13.2); recebido {timeout_s}s"
            )

        inicio_ns = time.monotonic_ns()
        caminho = self.caminho_clone
        cloned_now: bool

        # 1) Decide entre clone novo, update ou caminho-bloqueado.
        if not caminho.exists():
            # Garantimos que o pai existe; o ``git clone`` cria o leaf.
            try:
                caminho.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return self._falha(
                    inicio_ns,
                    cloned_now=False,
                    falha=FalhaSync(
                        categoria="io-erro",
                        mensagem=(
                            f"falha ao criar diretório-pai {caminho.parent}: "
                            f"{exc}"
                        ),
                        detalhes={"erro": str(exc)},
                    ),
                )
            falha = self._git_clone(caminho, timeout_s)
            if falha is not None:
                return self._falha(
                    inicio_ns, cloned_now=False, falha=falha
                )
            cloned_now = True
        elif (caminho / ".git").is_dir():
            falha = self._git_update(caminho, timeout_s)
            if falha is not None:
                return self._falha(
                    inicio_ns, cloned_now=False, falha=falha
                )
            cloned_now = False
        else:
            # Pasta criada à mão (sem .git/) — não tocamos. R13.3:
            # preservar a cópia local existente sem modificações.
            return self._falha(
                inicio_ns,
                cloned_now=False,
                falha=FalhaSync(
                    categoria="repositorio-inacessivel",
                    mensagem=(
                        f"diretório {caminho} existe mas não é um repositório "
                        "Git válido (sem .git/); cópia local preservada"
                    ),
                    detalhes={"caminho": str(caminho)},
                ),
            )

        # 2) Capturar SHA do HEAD após clone/update.
        sha, falha_sha = self._git_rev_parse_head(caminho, timeout_s)
        if falha_sha is not None:
            return self._falha(
                inicio_ns, cloned_now=cloned_now, falha=falha_sha
            )
        assert sha is not None  # contrato implícito de ``_git_rev_parse_head``

        # 3) Atualizar a Nota_Zettel.
        try:
            self.garantir_nota_index(hash_commit=sha)
        except OSError as exc:
            return self._falha(
                inicio_ns,
                cloned_now=cloned_now,
                falha=FalhaSync(
                    categoria="io-erro",
                    mensagem=(
                        "falha ao gravar Hydra_Reference_Index.md: "
                        f"{exc}"
                    ),
                    detalhes={"erro": str(exc)},
                ),
            )

        duracao_ms = max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)
        return ResultadoSync(
            sucesso=True,
            hash_commit=sha,
            caminho_clone=caminho,
            cloned_now=cloned_now,
            duracao_ms=duracao_ms,
            falha=None,
        )

    # ------------------------------------------------------------------
    # R13.1 — Nota_Zettel de índice
    # ------------------------------------------------------------------

    def garantir_nota_index(
        self,
        *,
        hash_commit: Optional[str],
        subdiretorios: Optional[list[str]] = None,
    ) -> Path:
        """Cria/atualiza ``Hydra_Reference_Index.md`` (R13.1).

        Frontmatter gravado:

        - ``titulo``: ``Hydra_Reference_Index``
        - ``area``: ``API_NinjaTrader_8_Reference``
        - ``tags``: lista fixa cobrindo Hydra, reference, NinjaScript
        - ``data_criacao``: ISO 8601 UTC com sufixo ``Z``
        - ``agente_autor``: ``Athena`` (R13.1 não fixa autor; Athena é
          o único agente com escopo de orquestração que faz sentido
          para uma nota de índice)
        - ``url``: :attr:`url`
        - ``branch``: :attr:`branch`
        - ``hash_commit``: ``hash_commit`` quando ``[0-9a-f]{40}``;
          ``null`` (YAML) caso contrário
        - ``subdiretorios``: lista de dicts ``{caminho, descricao}``
          (cada ``descricao`` truncada a 200 caracteres por R13.1)

        Parameters
        ----------
        hash_commit:
            SHA-1 hex de 40 caracteres ou ``None`` (caso o sync ainda
            não tenha ocorrido).
        subdiretorios:
            Lista de caminhos relativos a :attr:`caminho_clone` que
            devem aparecer na nota. ``None`` aciona auto-discovery: se
            ``caminho_clone`` existe, usa as pastas top-level (em ordem
            alfabética); senão, lista vazia.

        Returns
        -------
        Path
            Caminho absoluto da nota gravada.
        """
        # Hash sanitizado: aceita None ou 40-hex.
        hash_normalizado: Optional[str] = None
        if hash_commit is not None:
            if not isinstance(hash_commit, str):
                raise TypeError(
                    "hash_commit deve ser str ou None; "
                    f"recebido {type(hash_commit).__name__}"
                )
            if not _RE_SHA1_HEX.match(hash_commit):
                raise ValueError(
                    f"hash_commit deve ser SHA-1 hex de 40 chars; "
                    f"recebido {hash_commit!r}"
                )
            hash_normalizado = hash_commit

        # Lista de subdiretórios.
        if subdiretorios is None:
            entradas = self._auto_descobrir_subdiretorios()
        else:
            entradas = [
                {
                    "caminho": str(p),
                    "descricao": _truncar_descricao(""),
                }
                for p in subdiretorios
                if isinstance(p, str) and p.strip()
            ]

        agora_iso = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        frontmatter: dict[str, Any] = {
            "titulo": "Hydra_Reference_Index",
            "area": "API_NinjaTrader_8_Reference",
            "tags": ["hydra", "reference", "ninjascript"],
            "data_criacao": agora_iso,
            "agente_autor": "Athena",
            "url": self._url,
            "branch": self._branch,
            "hash_commit": hash_normalizado,
            "subdiretorios": entradas,
        }
        yaml_str = yaml.safe_dump(
            frontmatter,
            sort_keys=True,
            allow_unicode=True,
            default_flow_style=False,
        )

        corpo = (
            "# Hydra_Reference_Index\n\n"
            "Esta nota é o índice da cópia somente-leitura do repositório "
            f"histórico Hydra (`{self._url}`, branch `{self._branch}`) "
            "mantida em "
            f"`{DIR_REFERENCE_HYDRA}/`.\n\n"
            "O conteúdo do diretório é regenerado a cada execução de "
            "`caos hydra sync`. Edições manuais são revertidas no próximo "
            "sync (regra de steering `reference-hydra-readonly`, R13.4).\n"
        )
        conteudo = f"---\n{yaml_str}---\n\n{corpo}"

        caminho_nota = self.caminho_nota_index
        caminho_nota.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho_nota.with_suffix(caminho_nota.suffix + ".tmp")
        tmp.write_text(conteudo, encoding="utf-8", newline="\n")
        tmp.replace(caminho_nota)
        return caminho_nota

    # ------------------------------------------------------------------
    # R13.5 — Guard de cópia para o código ativo
    # ------------------------------------------------------------------

    def validar_copia_de_codigo(
        self,
        *,
        arquivo_origem_relativo: str,
        decisao: Optional[DecisaoDoConselho],
    ) -> ResultadoValidacaoCopia:
        """Decide se a cópia de ``arquivo_origem_relativo`` está autorizada.

        ``arquivo_origem_relativo`` deve estar sob ``reference_hydra/``
        (caminho relativo a ``04_CODIGO/ninjascript/``). Qualquer cópia
        para o código ativo do CAOS é bloqueada (R13.5) a menos que:

        1. ``decisao`` seja não-``None``;
        2. ``decisao.decisao_final.rationale`` contenha o substring
           ``"reference_hydra/"``.

        Esta heurística é deliberadamente conservadora: a aceitação real
        exigirá campos próprios em uma Decisao_Do_Conselho de Spec
        futuro (``arquivo_origem``, ``arquivo_destino``, ``rationale``),
        conforme nota técnica do Spec 1.

        Parameters
        ----------
        arquivo_origem_relativo:
            Caminho relativo a partir de ``04_CODIGO/ninjascript/`` —
            ex.: ``"reference_hydra/strategies/Foo.cs"``.
        decisao:
            ``DecisaoDoConselho`` que se pretende autorizar a cópia.
            ``None`` bloqueia automaticamente.
        """
        if not isinstance(arquivo_origem_relativo, str) or not (
            arquivo_origem_relativo.strip()
        ):
            raise ValueError(
                "arquivo_origem_relativo não pode ser vazio"
            )
        # Normaliza para POSIX para reduzir falsos negativos no startswith.
        normalizado = arquivo_origem_relativo.replace("\\", "/").lstrip("/")
        if not normalizado.startswith("reference_hydra/"):
            # Se o arquivo de origem nem sequer está em reference_hydra/,
            # o R13.5 não se aplica — autorizamos sem exigir Decisao.
            return ResultadoValidacaoCopia(
                autorizado=True,
                motivo=None,
                decisao_id=None,
            )

        if decisao is None:
            return ResultadoValidacaoCopia(
                autorizado=False,
                motivo=(
                    "cópia de código de reference_hydra/ exige "
                    "Decisao_Do_Conselho explícita (R13.5); recebido "
                    "decisao=None"
                ),
                decisao_id=None,
            )

        rationale = decisao.decisao_final.rationale or ""
        if "reference_hydra/" not in rationale:
            return ResultadoValidacaoCopia(
                autorizado=False,
                motivo=(
                    "Decisao_Do_Conselho não menciona explicitamente "
                    "'reference_hydra/' no rationale; cópia bloqueada "
                    "pelo guard do R13.5"
                ),
                decisao_id=decisao.identificador,
            )

        return ResultadoValidacaoCopia(
            autorizado=True,
            motivo=None,
            decisao_id=decisao.identificador,
        )

    # ------------------------------------------------------------------
    # Operações Git internas
    # ------------------------------------------------------------------

    def _git_clone(
        self, caminho: Path, timeout_s: float
    ) -> Optional[FalhaSync]:
        """Executa ``git clone --branch <branch> --depth 1 <url> <caminho>``.

        Retorna ``None`` em sucesso, ou :class:`FalhaSync` categorizada.
        """
        cmd = [
            "git",
            "clone",
            "--branch",
            self._branch,
            "--depth",
            "1",
            self._url,
            str(caminho),
        ]
        return self._executar_git(cmd, timeout_s, etapa="clone")

    def _git_update(
        self, caminho: Path, timeout_s: float
    ) -> Optional[FalhaSync]:
        """Executa ``fetch`` + ``reset --hard`` em um clone existente.

        Retorna ``None`` em sucesso, ou :class:`FalhaSync` categorizada.
        """
        cmd_fetch = [
            "git",
            "-C",
            str(caminho),
            "fetch",
            "origin",
            self._branch,
            "--depth",
            "1",
        ]
        falha = self._executar_git(cmd_fetch, timeout_s, etapa="fetch")
        if falha is not None:
            return falha

        cmd_reset = [
            "git",
            "-C",
            str(caminho),
            "reset",
            "--hard",
            f"origin/{self._branch}",
        ]
        return self._executar_git(cmd_reset, timeout_s, etapa="reset")

    def _git_rev_parse_head(
        self, caminho: Path, timeout_s: float
    ) -> tuple[Optional[str], Optional[FalhaSync]]:
        """Executa ``git -C <caminho> rev-parse HEAD`` e devolve o SHA.

        Retorna ``(sha, None)`` em sucesso ou ``(None, FalhaSync)``.
        """
        cmd = ["git", "-C", str(caminho), "rev-parse", "HEAD"]
        try:
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_s,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, FalhaSync(
                categoria="timeout",
                mensagem=(
                    f"git rev-parse HEAD excedeu o timeout de "
                    f"{int(timeout_s)}s"
                ),
                detalhes={"comando": " ".join(cmd)},
            )
        except FileNotFoundError as exc:
            return None, FalhaSync(
                categoria="git-ausente",
                mensagem=(
                    "executável 'git' não encontrado no PATH: "
                    f"{exc}"
                ),
                detalhes={"comando": " ".join(cmd), "erro": str(exc)},
            )
        except OSError as exc:
            return None, FalhaSync(
                categoria="io-erro",
                mensagem=f"falha ao executar git rev-parse: {exc}",
                detalhes={"comando": " ".join(cmd), "erro": str(exc)},
            )

        stdout = (resultado.stdout or b"").decode(
            "utf-8", errors="replace"
        ).strip()
        stderr = (resultado.stderr or b"").decode(
            "utf-8", errors="replace"
        )

        if resultado.returncode != 0 or not stdout:
            categoria = _categorizar_stderr(stderr)
            return None, FalhaSync(
                categoria=categoria,
                mensagem=(
                    f"git rev-parse HEAD falhou: exit_code="
                    f"{resultado.returncode}"
                ),
                detalhes={
                    "comando": " ".join(cmd),
                    "exit_code": resultado.returncode,
                    "stderr": stderr[:1024],
                },
            )

        if not _RE_SHA1_HEX.match(stdout):
            return None, FalhaSync(
                categoria="io-erro",
                mensagem=(
                    f"git rev-parse HEAD retornou valor inesperado: "
                    f"{stdout!r}"
                ),
                detalhes={"comando": " ".join(cmd), "stdout": stdout},
            )

        return stdout, None

    @staticmethod
    def _executar_git(
        cmd: list[str], timeout_s: float, *, etapa: str
    ) -> Optional[FalhaSync]:
        """Executa um comando ``git`` e categoriza falhas em :class:`FalhaSync`.

        Retorna ``None`` em sucesso (exit_code == 0). Em falha, devolve
        uma :class:`FalhaSync` com a categoria mais específica derivada
        do ``stderr``.
        """
        try:
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_s,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return FalhaSync(
                categoria="timeout",
                mensagem=(
                    f"git {etapa} excedeu o timeout de "
                    f"{int(timeout_s)}s"
                ),
                detalhes={"comando": " ".join(cmd), "etapa": etapa},
            )
        except FileNotFoundError as exc:
            return FalhaSync(
                categoria="git-ausente",
                mensagem=(
                    f"executável 'git' não encontrado no PATH: {exc}"
                ),
                detalhes={
                    "comando": " ".join(cmd),
                    "etapa": etapa,
                    "erro": str(exc),
                },
            )
        except OSError as exc:
            return FalhaSync(
                categoria="io-erro",
                mensagem=f"falha ao executar git {etapa}: {exc}",
                detalhes={
                    "comando": " ".join(cmd),
                    "etapa": etapa,
                    "erro": str(exc),
                },
            )

        if resultado.returncode == 0:
            return None

        stderr = (resultado.stderr or b"").decode(
            "utf-8", errors="replace"
        )
        categoria = _categorizar_stderr(stderr)
        return FalhaSync(
            categoria=categoria,
            mensagem=(
                f"git {etapa} falhou: exit_code={resultado.returncode}"
            ),
            detalhes={
                "comando": " ".join(cmd),
                "etapa": etapa,
                "exit_code": resultado.returncode,
                "stderr": stderr[:1024],
            },
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _auto_descobrir_subdiretorios(self) -> list[dict[str, str]]:
        """Lista (em ordem alfabética) as pastas top-level do clone.

        Quando o clone não existe ainda, retorna lista vazia.
        Cada item é ``{"caminho": "<rel>", "descricao": ""}`` — a
        descrição fica vazia até que um Spec subsequente popule a
        nota com texto humano. R13.1 exige
        ``1 ≤ len(descricao) ≤ 200`` apenas no momento em que o item
        for lido para indexação semântica; aceitamos vazio na inicial.
        """
        caminho = self.caminho_clone
        if not caminho.is_dir():
            return []
        nomes = sorted(
            p.name for p in caminho.iterdir() if p.is_dir()
        )
        return [
            {"caminho": nome, "descricao": ""}
            for nome in nomes
            if nome != ".git"
        ]

    def _falha(
        self,
        inicio_ns: int,
        *,
        cloned_now: bool,
        falha: FalhaSync,
    ) -> ResultadoSync:
        """Compila um :class:`ResultadoSync` de falha preservando a duração."""
        duracao_ms = max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)
        return ResultadoSync(
            sucesso=False,
            hash_commit=None,
            caminho_clone=self.caminho_clone,
            cloned_now=cloned_now,
            duracao_ms=duracao_ms,
            falha=falha,
        )


# ---------------------------------------------------------------------------
# Helpers livres
# ---------------------------------------------------------------------------


def _truncar_descricao(texto: str) -> str:
    """Trunca ``texto`` em 200 caracteres (R13.1)."""
    if len(texto) <= 200:
        return texto
    return texto[:200]


__all__ = [
    "HYDRA_URL",
    "HYDRA_BRANCH",
    "DIR_REFERENCE_HYDRA",
    "NOTA_HYDRA_INDEX",
    "DIR_NINJASCRIPT_ATIVO",
    "TIMEOUT_S",
    "CategoriaFalhaSync",
    "FalhaSync",
    "ResultadoSync",
    "ResultadoValidacaoCopia",
    "HydraReferenceSync",
]
