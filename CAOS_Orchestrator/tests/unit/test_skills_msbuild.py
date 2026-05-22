"""Testes unitários do :mod:`caos.skills.msbuild`.

Cobre o R11.3 do ``requirements.md`` exercitando:

- ``.csproj`` ausente devolve resultado ``skill-ok`` com motivo
  ``csproj-ausente`` e ``exit_code = -2`` sem falhar (R11.3 + nota de
  implementação no ``tasks.md``).
- Localização de ``.csproj`` único no diretório.
- Múltiplos ``.csproj`` → primeiro alfabeticamente + warning textual em
  stderr.
- Parse de erros e warnings com formato canônico (com coluna).
- Parse com formato sem coluna (regex tolerante).
- Validação de ``timeout_s`` (limite 600s do R11.3).
- ``TimeoutExpired`` durante execução → ``skill-timeout``.
- ``OSError`` no spawn → ``skill-falha`` com exit_code -1.
- ``diretorio_projeto`` inexistente → ``ValueError`` no construtor.
- Estabilidade do hash de auditoria entre execuções idênticas.

Não chamamos o MSBuild real — todos os testes que precisam de execução
mocam ``subprocess.run`` via ``monkeypatch``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from caos.skills.msbuild import (
    ItemMSBuild,
    ResultadoMSBuild,
    SkillMSBuild,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CompletedProcessFake:
    """Mínimo subset de ``subprocess.CompletedProcess`` usado nos mocks."""

    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _criar_csproj(diretorio: Path, nome: str) -> Path:
    """Cria um arquivo ``nome.csproj`` (vazio) em ``diretorio``."""
    caminho = diretorio / nome
    caminho.write_text("<!-- placeholder -->\n", encoding="utf-8")
    return caminho


# ---------------------------------------------------------------------------
# Caso especial: csproj ausente
# ---------------------------------------------------------------------------


def test_csproj_ausente_retorna_skill_ok_com_motivo(tmp_path: Path) -> None:
    """Sem ``.csproj`` no diretório, a Skill devolve resultado vazio sem falhar."""
    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar()
    assert isinstance(resultado, ResultadoMSBuild)
    assert resultado.csproj is None
    assert resultado.exit_code == -2
    assert resultado.status == "skill-ok"
    assert resultado.motivo == "csproj-ausente"
    assert resultado.erros == []
    assert resultado.warnings == []
    # Auditoria também reflete o estado.
    assert resultado.auditoria is not None
    assert resultado.auditoria.exit_code == -2
    assert resultado.auditoria.status == "skill-ok"
    assert resultado.auditoria.motivo == "csproj-ausente"


# ---------------------------------------------------------------------------
# Localização do csproj
# ---------------------------------------------------------------------------


def test_csproj_unico_e_localizado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com 1 ``.csproj`` no dir, a Skill o localiza e ``status='skill-ok'``."""
    csproj = _criar_csproj(tmp_path, "proj.csproj")

    chamadas: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> _CompletedProcessFake:
        chamadas.append(args)
        return _CompletedProcessFake(
            returncode=0, stdout=b"", stderr=b""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar()

    assert resultado.csproj == csproj
    assert resultado.status == "skill-ok"
    assert resultado.exit_code == 0
    # Args contém o caminho do csproj e a configuration default.
    assert len(chamadas) == 1
    args = chamadas[0]
    assert str(csproj) in args
    assert "/p:Configuration=Release" in args
    assert "/nologo" in args


def test_multiplos_csproj_usa_primeiro_alfabetico(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com 2 ``.csproj``, escolhe o primeiro alfabeticamente e avisa em stderr."""
    csproj_a = _criar_csproj(tmp_path, "a.csproj")
    _criar_csproj(tmp_path, "b.csproj")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _CompletedProcessFake(
            returncode=0, stdout=b"", stderr=b""
        ),
    )

    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar()

    assert resultado.csproj == csproj_a
    assert resultado.status == "skill-ok"
    # Aviso textual está presente no stderr.
    assert "AVISO" in resultado.stderr
    assert "a.csproj" in resultado.stderr
    assert "b.csproj" in resultado.stderr
    assert resultado.motivo == "multiplos-csproj"


# ---------------------------------------------------------------------------
# Parse de erros e warnings
# ---------------------------------------------------------------------------


def test_parse_erro_e_warning_simples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saída canônica do MSBuild produz 1 erro e 1 warning estruturados."""
    _criar_csproj(tmp_path, "proj.csproj")
    saida_msbuild = (
        "C:\\foo\\Bar.cs(10,5): error CS0103: The name 'x' does not exist "
        "[C:\\foo\\proj.csproj]\n"
        "C:\\foo\\Bar.cs(20,5): warning CS0168: variable declared but unused "
        "[C:\\foo\\proj.csproj]\n"
    ).encode("utf-8")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _CompletedProcessFake(
            returncode=1, stdout=saida_msbuild, stderr=b""
        ),
    )

    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar()

    assert resultado.exit_code == 1
    assert resultado.status == "skill-falha"
    assert len(resultado.erros) == 1
    assert len(resultado.warnings) == 1

    erro: ItemMSBuild = resultado.erros[0]
    assert erro.severidade == "error"
    assert erro.codigo == "CS0103"
    assert erro.linha == 10
    assert erro.coluna == 5
    assert erro.arquivo == "C:\\foo\\Bar.cs"
    assert "does not exist" in erro.mensagem
    # O sufixo entre colchetes deve ter sido removido.
    assert "[" not in erro.mensagem

    warning: ItemMSBuild = resultado.warnings[0]
    assert warning.severidade == "warning"
    assert warning.codigo == "CS0168"
    assert warning.linha == 20
    assert warning.coluna == 5
    assert "unused" in warning.mensagem


def test_parse_erro_sem_coluna(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aceita formato ``arquivo(10): error ...`` (regex tolerante a coluna)."""
    _criar_csproj(tmp_path, "proj.csproj")
    saida = b"X\\y.cs(42): error MSB0001: algo deu errado\n"

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _CompletedProcessFake(
            returncode=1, stdout=saida, stderr=b""
        ),
    )
    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar()

    assert len(resultado.erros) == 1
    erro = resultado.erros[0]
    assert erro.codigo == "MSB0001"
    assert erro.linha == 42
    assert erro.coluna is None
    assert erro.severidade == "error"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_timeout_excede_maximo_lanca(tmp_path: Path) -> None:
    """``timeout_s=700`` viola o limite do R11.3."""
    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    with pytest.raises(ValueError) as excinfo:
        skill.executar(timeout_s=700)
    assert "600" in str(excinfo.value)


def test_timeout_durante_execucao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``TimeoutExpired`` durante o build retorna ``skill-timeout``."""
    _criar_csproj(tmp_path, "proj.csproj")

    def raise_timeout(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(
            cmd=args[0] if args else "msbuild",
            timeout=kwargs.get("timeout", 1),
            output=b"",
            stderr=b"",
        )

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar(timeout_s=1.0)
    assert resultado.status == "skill-timeout"
    assert resultado.exit_code == -1
    assert resultado.motivo is not None and "timeout" in resultado.motivo


# ---------------------------------------------------------------------------
# Falha de spawn
# ---------------------------------------------------------------------------


def test_falha_spawn_retorna_skill_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``OSError`` no spawn vira ``skill-falha`` com exit_code -1, sem exceção."""
    _criar_csproj(tmp_path, "proj.csproj")

    def raise_oserror(*args: Any, **kwargs: Any) -> None:
        raise OSError("MSBuild.exe not found")

    monkeypatch.setattr(subprocess, "run", raise_oserror)
    skill = SkillMSBuild(diretorio_projeto=tmp_path)
    resultado = skill.executar()
    assert resultado.status == "skill-falha"
    assert resultado.exit_code == -1
    assert resultado.motivo is not None
    assert "msbuild" in resultado.motivo.lower()


# ---------------------------------------------------------------------------
# Validações pré-execução
# ---------------------------------------------------------------------------


def test_diretorio_projeto_inexistente_lanca(tmp_path: Path) -> None:
    inexistente = tmp_path / "sem_diretorio"
    with pytest.raises(ValueError):
        SkillMSBuild(diretorio_projeto=inexistente)


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------


def test_auditoria_hash_estavel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duas execuções com mesmos parâmetros produzem o mesmo hash de auditoria."""
    _criar_csproj(tmp_path, "proj.csproj")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _CompletedProcessFake(
            returncode=0, stdout=b"", stderr=b""
        ),
    )
    skill = SkillMSBuild(diretorio_projeto=tmp_path, invocador="Hermes")
    r1 = skill.executar()
    r2 = skill.executar()
    assert r1.auditoria is not None and r2.auditoria is not None
    assert (
        r1.auditoria.parametros_hash_sha256
        == r2.auditoria.parametros_hash_sha256
    )
    assert len(r1.auditoria.parametros_hash_sha256) == 64
    assert r1.auditoria.invocador == "Hermes"
