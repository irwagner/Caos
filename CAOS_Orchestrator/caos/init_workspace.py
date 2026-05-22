"""
Lógica idempotente do subcomando ``caos init``.

Este módulo é separado de ``caos.main`` para que a função :func:`executar`
possa ser testada diretamente (incluindo via property-based testing) sem
precisar atravessar o parser de CLI.

Cobre os critérios R1.1 a R1.10 do ``requirements.md``:

* Cria os 8 diretórios-alvo na raiz do projeto se ausentes.
* Cria ``.gitkeep`` (arquivo de 0 bytes) nos placeholders configurados.
* É **estritamente idempotente**: rodar N vezes não destrói nada já existente.
* Falha de forma controlada em ``PermissionError``, colisão com arquivo
  pré-existente de mesmo nome, ou ``OSError`` genérico — preservando o que
  já tiver sido criado nessa execução.
"""

from __future__ import annotations

import concurrent.futures
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Tuple

# Timeout (segundos) por diretório — exigência R1.8 (≤30s por diretório).
# Path.mkdir é praticamente instantâneo, mas envolvemos a chamada num
# ThreadPoolExecutor para conseguir abortar caso o filesystem trave (ex:
# share de rede inalcançável). signal.alarm não está disponível no Windows,
# por isso optamos por concurrent.futures.
_TIMEOUT_POR_DIRETORIO_S = 30.0


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

# Lista canônica dos diretórios-alvo do `caos init`.
#
# Cada entrada é uma tupla (caminho_relativo, gitkeep), onde:
#   - caminho_relativo: caminho POSIX relativo à raiz do workspace.
#   - gitkeep: True se o diretório precisa receber um arquivo .gitkeep
#              vazio (placeholder de versionamento Git).
#
# A ordem é a ordem de processamento e também a ordem de saída humana,
# por isso é estável e definida explicitamente. As 3 áreas que ficarão
# imediatamente populadas por Tasks futuras (.kiro/agents/, .kiro/steering/,
# CAOS_Zettelkasten/) NÃO recebem .gitkeep — outros arquivos serão
# adicionados antes de qualquer commit relevante.
_TARGETS: Tuple[Tuple[str, bool], ...] = (
    (".kiro/agents", False),
    (".kiro/steering", False),
    ("CAOS_Zettelkasten", False),
    ("CAOS_Council/debates", True),
    ("CAOS_Council/decisions", True),
    ("04_CODIGO/ninjascript", True),
    ("05_BACKTEST", True),
    ("dados/MNQ", True),
)


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

StatusVerificacao = Literal["criado", "ja-existente"]
"""Status observável de um caminho após a verificação."""

CategoriaFalha = Literal[
    "permissao-negada",
    "arquivo-no-lugar-de-pasta",
    "timeout",
    "erro-de-io",
]
"""Categorias de falha tratadas pelo init."""


@dataclass(frozen=True)
class VerificacaoPath:
    """Resultado da verificação de um caminho-alvo individual."""

    caminho_relativo: str
    """Caminho relativo à raiz do workspace, sempre em forma POSIX."""

    caminho_absoluto: Path
    """Caminho absoluto resolvido."""

    status_diretorio: StatusVerificacao
    """``"criado"`` se este `executar()` criou o diretório; ``"ja-existente"``
    se já estava lá antes."""

    gitkeep_esperado: bool
    """Se o target exige ``.gitkeep``."""

    status_gitkeep: Optional[StatusVerificacao] = None
    """Status do arquivo ``.gitkeep``, ou ``None`` se não for esperado."""


@dataclass(frozen=True)
class FalhaInicializacao:
    """Descrição estruturada de uma falha durante a execução do init."""

    caminho_relativo: str
    categoria: CategoriaFalha
    mensagem: str


@dataclass(frozen=True)
class ResultadoInicializacao:
    """Retorno de :func:`executar`.

    ``verificados`` contém todas as verificações concluídas com sucesso,
    em ordem de processamento. Se ``falha`` for não-``None``, a execução foi
    interrompida no caminho indicado e ``verificados`` reflete tudo que foi
    processado **antes** da falha.
    """

    raiz: Path
    verificados: list[VerificacaoPath] = field(default_factory=list)
    falha: Optional[FalhaInicializacao] = None

    @property
    def sucesso(self) -> bool:
        """``True`` quando nenhuma falha foi registrada."""
        return self.falha is None


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def listar_targets() -> Tuple[Tuple[str, bool], ...]:
    """Devolve a lista canônica de targets `(caminho_relativo, gitkeep)`.

    Exposta para uso em testes e em comandos auxiliares (ex: ``caos doctor``
    em Tasks futuras).
    """
    return _TARGETS


def executar(root: Path) -> ResultadoInicializacao:
    """Executa o `caos init` na raiz informada, idempotentemente.

    A função:

    1. Resolve a raiz para caminho absoluto (sem exigir que ela exista).
    2. Cria a raiz se necessário.
    3. Itera sobre os targets na ordem canônica, criando cada diretório
       ausente e cada ``.gitkeep`` esperado e ausente.
    4. Em qualquer falha de I/O, retorna imediatamente um
       :class:`ResultadoInicializacao` com ``falha`` preenchida.

    A idempotência vem de:

    * ``Path.mkdir(parents=True, exist_ok=True)`` para diretórios.
    * Verificar a existência de ``.gitkeep`` antes de criar (e nunca
      truncar um ``.gitkeep`` pré-existente, mesmo que tenha conteúdo).

    Parameters
    ----------
    root:
        Raiz do workspace. Caminho relativo é aceito e resolvido contra
        ``Path.cwd()``.
    """
    raiz_absoluta = Path(root).expanduser().resolve()
    verificados: list[VerificacaoPath] = []

    # Garante a raiz antes de qualquer target. Se a raiz não puder ser
    # criada, a falha aponta para uma string vazia (== a própria raiz).
    falha_raiz = _criar_diretorio_com_timeout(raiz_absoluta)
    if falha_raiz is not None:
        return ResultadoInicializacao(
            raiz=raiz_absoluta,
            verificados=verificados,
            falha=FalhaInicializacao(
                caminho_relativo="",
                categoria=falha_raiz[0],
                mensagem=falha_raiz[1],
            ),
        )

    for caminho_relativo, gitkeep in _TARGETS:
        caminho_absoluto = raiz_absoluta / caminho_relativo

        # --- 1. Diretório ---
        ja_existia_dir = caminho_absoluto.is_dir()
        if not ja_existia_dir:
            # Pode ser que já exista um arquivo de mesmo nome — caso
            # explicitamente coberto pelo R1.9.
            if caminho_absoluto.exists():
                return _interromper(
                    raiz_absoluta,
                    verificados,
                    caminho_relativo,
                    "arquivo-no-lugar-de-pasta",
                    f"existe um arquivo (não-diretório) em {caminho_absoluto}",
                )
            falha_dir = _criar_diretorio_com_timeout(caminho_absoluto)
            if falha_dir is not None:
                return _interromper(
                    raiz_absoluta,
                    verificados,
                    caminho_relativo,
                    falha_dir[0],
                    falha_dir[1],
                )

        status_dir: StatusVerificacao = (
            "ja-existente" if ja_existia_dir else "criado"
        )

        # --- 2. .gitkeep ---
        status_gitkeep: Optional[StatusVerificacao] = None
        if gitkeep:
            arquivo_gitkeep = caminho_absoluto / ".gitkeep"
            if arquivo_gitkeep.exists():
                # Idempotência: NÃO sobrescrevemos. Se um humano já
                # colocou conteúdo aqui (ex: anotação), preservamos.
                status_gitkeep = "ja-existente"
            else:
                falha_gk = _criar_arquivo_vazio_com_timeout(arquivo_gitkeep)
                if falha_gk is not None:
                    return _interromper(
                        raiz_absoluta,
                        verificados,
                        caminho_relativo,
                        falha_gk[0],
                        falha_gk[1],
                    )
                status_gitkeep = "criado"

        verificados.append(
            VerificacaoPath(
                caminho_relativo=caminho_relativo,
                caminho_absoluto=caminho_absoluto,
                status_diretorio=status_dir,
                gitkeep_esperado=gitkeep,
                status_gitkeep=status_gitkeep,
            )
        )

    return ResultadoInicializacao(
        raiz=raiz_absoluta,
        verificados=verificados,
        falha=None,
    )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _interromper(
    raiz: Path,
    verificados: list[VerificacaoPath],
    caminho_relativo: str,
    categoria: CategoriaFalha,
    mensagem: str,
) -> ResultadoInicializacao:
    """Empacota uma interrupção controlada como ResultadoInicializacao."""
    return ResultadoInicializacao(
        raiz=raiz,
        verificados=verificados,
        falha=FalhaInicializacao(
            caminho_relativo=caminho_relativo,
            categoria=categoria,
            mensagem=mensagem,
        ),
    )


def _criar_diretorio_com_timeout(
    caminho: Path,
) -> Optional[Tuple[CategoriaFalha, str]]:
    """Tenta criar ``caminho`` como diretório, com timeout.

    Retorna ``None`` em sucesso ou uma tupla ``(categoria, mensagem)`` em falha.
    """

    def _trabalho() -> None:
        caminho.mkdir(parents=True, exist_ok=True)

    return _executar_com_timeout(caminho, _trabalho)


def _criar_arquivo_vazio_com_timeout(
    caminho: Path,
) -> Optional[Tuple[CategoriaFalha, str]]:
    """Cria um arquivo vazio (0 bytes), com timeout.

    Usa ``open(..., 'x')`` para falhar de forma explícita se outro processo
    criar o arquivo em paralelo, evitando sobrescrever conteúdo alheio.
    """

    def _trabalho() -> None:
        # 'x' = exclusive create. Se outro processo criar entre o check e
        # o open, levanta FileExistsError, que será tratado abaixo.
        try:
            with open(caminho, "xb"):
                pass
        except FileExistsError:
            # Corrida benigna: alguém criou o arquivo no intervalo. Como
            # o destino esperado já existe, consideramos sucesso silencioso.
            return

    return _executar_com_timeout(caminho, _trabalho)


def _executar_com_timeout(
    caminho: Path,
    trabalho,
) -> Optional[Tuple[CategoriaFalha, str]]:
    """Executa ``trabalho()`` num executor isolado e mapeia exceções."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
            future = exe.submit(trabalho)
            try:
                future.result(timeout=_TIMEOUT_POR_DIRETORIO_S)
            except concurrent.futures.TimeoutError:
                return (
                    "timeout",
                    f"operação excedeu {_TIMEOUT_POR_DIRETORIO_S:.0f}s em {caminho}",
                )
    except PermissionError as exc:
        return ("permissao-negada", f"permissão negada em {caminho}: {exc}")
    except FileExistsError as exc:
        # Tipicamente: existe um arquivo onde deveria ser pasta.
        return (
            "arquivo-no-lugar-de-pasta",
            f"colisão com arquivo existente em {caminho}: {exc}",
        )
    except OSError as exc:
        return ("erro-de-io", f"erro de I/O em {caminho}: {exc}")
    return None


# ---------------------------------------------------------------------------
# Formatação humana (usada pela CLI)
# ---------------------------------------------------------------------------

def formatar_relatorio(resultado: ResultadoInicializacao) -> str:
    """Formata o resultado para saída human-friendly em pt-BR.

    Mantida aqui (e não em ``main.py``) para ser testável sem CLI.
    """
    linhas: list[str] = []
    linhas.append(f"Raiz do workspace: {resultado.raiz}")
    linhas.append("")
    linhas.append("Verificação dos diretórios-alvo:")
    for v in resultado.verificados:
        marca = "+" if v.status_diretorio == "criado" else "="
        linha = f"  [{marca}] {v.caminho_relativo}/  ({v.status_diretorio})"
        if v.gitkeep_esperado:
            gk = v.status_gitkeep or "?"
            linha += f"   .gitkeep: {gk}"
        linhas.append(linha)

    if resultado.falha is not None:
        linhas.append("")
        linhas.append("FALHA:")
        linhas.append(
            f"  caminho:    {resultado.falha.caminho_relativo or '<raiz>'}"
        )
        linhas.append(f"  categoria:  {resultado.falha.categoria}")
        linhas.append(f"  mensagem:   {resultado.falha.mensagem}")
    else:
        linhas.append("")
        linhas.append("Estrutura do workspace verificada com sucesso.")

    return os.linesep.join(linhas)
