"""
Property-based tests para o subcomando ``caos init``.

Implementa **Property 9 — Initialization Idempotence** do ``design.md``:

    Running the project initialization command N times SHALL produce the same
    final directory tree without destroying existing directories or contents.

**Validates: Requirements 1.8, 1.9, 1.10**

A estratégia gera estados iniciais arbitrários da árvore (subconjunto dos
8 targets já existentes, ``.gitkeep`` com conteúdos arbitrários, e
arquivos externos com bytes aleatórios em paths que NÃO colidem com os
targets) e roda ``executar()`` ``1 + N`` vezes (``N ∈ [1, 5]``). Após cada
sequência, validamos quatro invariantes:

1. Os 8 caminhos-alvo existem como diretórios.
2. Os 5 placeholders têm ``.gitkeep`` presente; quando o init criou
   o arquivo, ele tem 0 bytes; quando o teste pré-criou, o conteúdo
   original é preservado byte-a-byte.
3. Arquivos externos (fora dos paths-alvo) são preservados byte-a-byte
   (hash SHA-256 estável).
4. ``executar()`` reporta sucesso em todas as chamadas.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos import init_workspace

# ---------------------------------------------------------------------------
# Targets (cópia local para o teste ser independente da estrutura interna).
# ---------------------------------------------------------------------------

TARGETS: Tuple[Tuple[str, bool], ...] = init_workspace.listar_targets()
"""Snapshot dos targets canônicos: tuplas (caminho_relativo, gitkeep)."""

INDICES_GITKEEP: Tuple[int, ...] = tuple(
    i for i, (_, gk) in enumerate(TARGETS) if gk
)
"""Índices dos targets que recebem ``.gitkeep``."""


# ---------------------------------------------------------------------------
# Estratégias Hypothesis
# ---------------------------------------------------------------------------

# Nomes de arquivo simples e ASCII para evitar problemas de codificação no
# Windows e colisões com nomes reservados (`con`, `nul`, etc.).
_nome_simples = st.from_regex(r"\A[a-z0-9_]{1,10}\Z", fullmatch=True)


def _caminho_externo() -> st.SearchStrategy[str]:
    """Caminho relativo sob ``_externo/`` (NUNCA colide com targets)."""
    return st.lists(_nome_simples, min_size=1, max_size=3).map(
        lambda partes: "_externo/" + "/".join(partes) + ".bin"
    )


_estrategia_arquivos_externos = st.lists(
    st.tuples(_caminho_externo(), st.binary(min_size=0, max_size=64)),
    max_size=5,
    unique_by=lambda par: par[0],
)

_estrategia_pre_dirs = st.sets(st.integers(min_value=0, max_value=len(TARGETS) - 1))

_estrategia_pre_gitkeeps = st.dictionaries(
    keys=st.sampled_from(INDICES_GITKEEP),
    values=st.binary(min_size=0, max_size=64),
    max_size=len(INDICES_GITKEEP),
)

_estrategia_n_execucoes_extras = st.integers(min_value=1, max_value=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _popular_estado_inicial(
    raiz: Path,
    pre_dirs: set[int],
    pre_gitkeeps: Dict[int, bytes],
    arquivos_externos: List[Tuple[str, bytes]],
) -> Dict[Path, str]:
    """Materializa o estado inicial da árvore antes de chamar ``executar``.

    Retorna um dicionário ``{caminho_absoluto: sha256_hex}`` com os arquivos
    externos cujo conteúdo deve permanecer inalterado após o init.
    """
    # Diretórios-alvo pré-existentes.
    for idx in pre_dirs:
        rel, _ = TARGETS[idx]
        (raiz / rel).mkdir(parents=True, exist_ok=True)

    # .gitkeep pré-existentes (com conteúdo arbitrário, possivelmente não-vazio).
    for idx, conteudo in pre_gitkeeps.items():
        rel, _ = TARGETS[idx]
        d = raiz / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").write_bytes(conteudo)

    # Arquivos externos com conteúdos aleatórios.
    estado_externos: Dict[Path, str] = {}
    for rel, conteudo in arquivos_externos:
        caminho = raiz / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
        estado_externos[caminho] = _sha256(conteudo)

    return estado_externos


def _validar_invariantes(
    raiz: Path,
    pre_gitkeeps: Dict[int, bytes],
    estado_externos: Dict[Path, str],
) -> None:
    """Aplica as 4 invariantes da Property 9 sobre ``raiz``."""
    # (1) Todos os 8 targets existem como diretórios.
    for rel, _ in TARGETS:
        d = raiz / rel
        assert d.is_dir(), f"diretório-alvo ausente: {rel}"

    # (2) .gitkeep nos 5 placeholders, com preservação de conteúdo pré-existente.
    for idx, (rel, gk) in enumerate(TARGETS):
        if not gk:
            continue
        arquivo = raiz / rel / ".gitkeep"
        assert arquivo.is_file(), f".gitkeep ausente em {rel}"
        conteudo_atual = arquivo.read_bytes()
        if idx in pre_gitkeeps:
            esperado = pre_gitkeeps[idx]
            assert conteudo_atual == esperado, (
                f".gitkeep pré-existente em {rel} foi alterado: "
                f"esperado {esperado!r}, atual {conteudo_atual!r}"
            )
        else:
            assert conteudo_atual == b"", (
                f".gitkeep criado pelo init em {rel} deveria ter 0 bytes; "
                f"tem {len(conteudo_atual)}"
            )

    # (3) Arquivos externos não foram alterados.
    for caminho, hash_esperado in estado_externos.items():
        assert caminho.is_file(), f"arquivo externo desapareceu: {caminho}"
        assert _sha256(caminho.read_bytes()) == hash_esperado, (
            f"arquivo externo {caminho} foi modificado pelo init"
        )


# ---------------------------------------------------------------------------
# Property 9
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    # Hypothesis avisa sobre uso de fixtures function-scoped com @given;
    # tmp_path_factory é session-scoped e cria um subdiretório único por
    # exemplo via mktemp(), então é seguro suprimir o aviso.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    pre_dirs=_estrategia_pre_dirs,
    pre_gitkeeps=_estrategia_pre_gitkeeps,
    arquivos_externos=_estrategia_arquivos_externos,
    n_execucoes_extras=_estrategia_n_execucoes_extras,
)
def test_caos_init_e_idempotente(
    pre_dirs: set[int],
    pre_gitkeeps: Dict[int, bytes],
    arquivos_externos: List[Tuple[str, bytes]],
    n_execucoes_extras: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 1.8, 1.9, 1.10** (Property 9).

    Para todo estado inicial parcial gerado, executar o ``caos init``
    ``1 + N`` vezes (com ``N ∈ [1, 5]``):

    * Reporta sucesso em todas as chamadas.
    * Produz a árvore-alvo completa (8 diretórios + 5 ``.gitkeep``).
    * Não altera ``.gitkeep`` pré-existentes.
    * Não altera nenhum arquivo fora dos paths-alvo.
    """
    raiz = tmp_path_factory.mktemp("caos_init")

    estado_externos = _popular_estado_inicial(
        raiz, pre_dirs, pre_gitkeeps, arquivos_externos
    )

    # 1ª execução (a "primeira chamada" exigida pela task).
    primeiro = init_workspace.executar(raiz)
    assert primeiro.sucesso, (
        f"primeira execução falhou: {primeiro.falha}"
    )

    # N execuções adicionais — todas devem reportar sucesso e manter
    # a árvore consistente.
    for i in range(n_execucoes_extras):
        r = init_workspace.executar(raiz)
        assert r.sucesso, (
            f"execução repetida #{i + 2} falhou: {r.falha}"
        )

    _validar_invariantes(raiz, pre_gitkeeps, estado_externos)
