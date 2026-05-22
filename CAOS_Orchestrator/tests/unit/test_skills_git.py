"""Testes unitários do :mod:`caos.skills.git`.

Cobre o R11.2 do ``requirements.md`` exercitando:

- whitelist estrita das 7 operações Git permitidas;
- rejeição de subcomandos fora da whitelist via :class:`SkillGitNaoAutorizada`;
- aceitação dos 7 subcomandos permitidos (sem lançar exceção em validação);
- ``git log`` em repo vazio (status skill-falha sem exceção);
- ``git branch`` listando branch após commit dummy;
- timeout máximo (120s);
- :func:`is_subcomando_permitido` com casos parametrizados;
- presença de ``subcomando``/``args`` no resultado e estabilidade do hash;
- ``repo_dir`` inexistente.

Os testes assumem que ``git`` está disponível no PATH do Windows. Se não
estiver, os testes que dependem da execução real são pulados.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from caos.skills.git import (
    OPERACOES_PERMITIDAS,
    ResultadoGit,
    SkillGit,
    SkillGitNaoAutorizada,
    is_subcomando_permitido,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_disponivel() -> bool:
    """Heurística: existe ``git`` no PATH?"""
    return shutil.which("git") is not None


requires_git = pytest.mark.skipif(
    not _git_disponivel(), reason="git não disponível no PATH"
)


def _inicializar_repo(repo: Path) -> None:
    """Cria um repo Git mínimo em ``repo`` para os testes que dependem disso.

    Configura ``user.name`` e ``user.email`` localmente para evitar falhas no
    ``commit`` em máquinas sem global config.
    """
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "caos@test.local"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "CAOS Test"],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


def test_subcomando_nao_permitido_lanca() -> None:
    """``push`` está fora da whitelist e dispara SkillGitNaoAutorizada."""
    skill = SkillGit()
    with pytest.raises(SkillGitNaoAutorizada) as excinfo:
        skill.executar("push")
    err = excinfo.value
    assert err.subcomando == "push"
    assert set(err.permitidos) == set(OPERACOES_PERMITIDAS)
    assert len(err.permitidos) == 7
    # mensagem em pt-BR cita whitelist
    assert "whitelist" in str(err).lower() or "permitidos" in str(err).lower()


@pytest.mark.parametrize(
    "subcomando", ["fetch", "pull", "merge", "rebase", "reset", "clone", "stash"]
)
def test_outros_subcomandos_proibidos_lancam(subcomando: str) -> None:
    """Vários subcomandos comuns mas vetados disparam o mesmo erro."""
    skill = SkillGit()
    with pytest.raises(SkillGitNaoAutorizada):
        skill.executar(subcomando)


def test_subcomandos_permitidos_passam_validacao(tmp_path: Path) -> None:
    """Cada um dos 7 nomes da whitelist passa pela validação sem exceção.

    Não verificamos o exit code da execução real — alguns (``commit`` sem
    nada staged) retornam erro do Git, mas isso é problema do Git, não da
    Skill. O ponto é confirmar que a validação não bloqueia.

    Evitamos passar ``--help`` porque o Git invoca um pager interativo que
    bloqueia o ``subprocess.run`` indefinidamente. Em vez disso, executamos
    cada subcomando dentro de uma pasta vazia (não-repo), onde todos falham
    rapidamente com exit_code != 0 sem abrir UI.
    """
    if not _git_disponivel():
        pytest.skip("git não disponível no PATH")
    skill = SkillGit(repo_dir=tmp_path)
    for sub in OPERACOES_PERMITIDAS:
        try:
            skill.executar(sub, timeout_s=10.0)
        except SkillGitNaoAutorizada as err:  # pragma: no cover - falha de teste
            pytest.fail(f"subcomando permitido {sub!r} foi rejeitado: {err}")


# ---------------------------------------------------------------------------
# Função utilitária
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcomando, esperado",
    [
        ("branch", True),
        ("checkout", True),
        ("add", True),
        ("commit", True),
        ("tag", True),
        ("revert", True),
        ("log", True),
        ("push", False),
        ("pull", False),
        ("fetch", False),
        ("BRANCH", False),  # case-sensitive (git é case-sensitive em subcmds)
        ("", False),
    ],
)
def test_is_subcomando_permitido(subcomando: str, esperado: bool) -> None:
    assert is_subcomando_permitido(subcomando) is esperado


# ---------------------------------------------------------------------------
# Execução real (precisa de git no PATH)
# ---------------------------------------------------------------------------


@requires_git
def test_log_em_repo_vazio(tmp_path: Path) -> None:
    """``git log`` em repo recém-init falha sem commits — Skill não lança."""
    _inicializar_repo(tmp_path)
    skill = SkillGit(repo_dir=tmp_path)
    resultado = skill.executar("log")
    assert isinstance(resultado, ResultadoGit)
    # Repo sem commits → exit_code != 0; Skill apenas registra status.
    assert resultado.exit_code != 0
    assert resultado.status == "skill-falha"
    assert resultado.subcomando == "log"
    assert resultado.args == ()


@requires_git
def test_branch_lista(tmp_path: Path) -> None:
    """Após um commit dummy, ``git branch`` lista o branch corrente."""
    _inicializar_repo(tmp_path)
    arquivo = tmp_path / "a.txt"
    arquivo.write_text("conteudo\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "a.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )

    skill = SkillGit(repo_dir=tmp_path)
    resultado = skill.executar("branch")
    assert resultado.exit_code == 0
    assert resultado.status == "skill-ok"
    # Aceita main ou master dependendo da config global do git.
    saida = resultado.stdout.lower()
    assert "main" in saida or "master" in saida


@requires_git
def test_auditoria_tem_subcomando_e_args(tmp_path: Path) -> None:
    """``ResultadoGit`` carrega ``subcomando``/``args`` e hash estável."""
    _inicializar_repo(tmp_path)
    skill = SkillGit(repo_dir=tmp_path, invocador="Athena")
    r1 = skill.executar("log", "--oneline")
    r2 = skill.executar("log", "--oneline")
    assert r1.subcomando == "log"
    assert r1.args == ("--oneline",)
    assert r1.auditoria.parametros_hash_sha256 == r2.auditoria.parametros_hash_sha256
    assert len(r1.auditoria.parametros_hash_sha256) == 64
    assert r1.auditoria.invocador == "Athena"


# ---------------------------------------------------------------------------
# Validações pré-execução
# ---------------------------------------------------------------------------


def test_timeout_excede_maximo_lanca() -> None:
    """``timeout_s=200`` viola o limite de 120s do R11.2."""
    skill = SkillGit()
    with pytest.raises(ValueError) as excinfo:
        skill.executar("log", timeout_s=200)
    assert "120" in str(excinfo.value)


def test_repo_dir_inexistente_lanca(tmp_path: Path) -> None:
    inexistente = tmp_path / "sem_repo"
    with pytest.raises(ValueError):
        SkillGit(repo_dir=inexistente)


def test_subcomando_vazio_lanca() -> None:
    skill = SkillGit()
    with pytest.raises(ValueError):
        skill.executar("")


def test_arg_nao_string_lanca() -> None:
    skill = SkillGit()
    with pytest.raises(TypeError):
        skill.executar("log", 123)  # type: ignore[arg-type]
