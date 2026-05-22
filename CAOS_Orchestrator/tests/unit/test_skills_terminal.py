"""Testes unitários do :mod:`caos.skills.terminal`.

Cobre o R11.1 do ``requirements.md`` exercitando:

- execução bem-sucedida (``echo``);
- exit code não-zero (``exit 7``);
- timeout via ``ping`` no Windows;
- validação de timeout máximo (300s);
- comando vazio;
- truncagem de stdout > 10 MB;
- estabilidade do hash de parâmetros entre invocações idênticas;
- ``cwd`` inexistente;
- propagação do ``invocador`` para o registro de auditoria.

Os testes assumem Windows + ``cmd`` (regra de steering
``plataforma-windows-cmd``). Não há cobertura de Linux.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from caos.skills._base import _LIMITE_BYTES_POR_CANAL
from caos.skills.terminal import ResultadoTerminal, SkillTerminal


# ---------------------------------------------------------------------------
# Casos felizes
# ---------------------------------------------------------------------------


def test_executa_comando_simples_sucesso() -> None:
    """``echo ok`` retorna exit_code 0, stdout contendo 'ok' e status skill-ok."""
    skill = SkillTerminal()
    resultado = skill.executar("echo ok")

    assert isinstance(resultado, ResultadoTerminal)
    assert resultado.exit_code == 0
    assert "ok" in resultado.stdout.lower()
    assert resultado.status == "skill-ok"
    assert resultado.truncado_stdout is False
    assert resultado.truncado_stderr is False
    assert resultado.duracao_ms >= 0
    assert resultado.auditoria.nome == "Skill_Terminal"
    assert resultado.auditoria.exit_code == 0
    assert resultado.auditoria.status == "skill-ok"
    assert resultado.auditoria.motivo is None


def test_status_skill_ok_e_falha_distintos() -> None:
    """Skill-ok e skill-falha são produzidos em cenários diferentes."""
    skill = SkillTerminal()
    ok = skill.executar("echo ok")
    falha = skill.executar("exit 3")
    assert ok.status == "skill-ok"
    assert falha.status == "skill-falha"
    assert ok.status != falha.status


# ---------------------------------------------------------------------------
# Caminhos de erro de execução
# ---------------------------------------------------------------------------


def test_exit_code_diferente_de_zero() -> None:
    """``exit 7`` propaga exit_code=7 e status skill-falha."""
    skill = SkillTerminal()
    resultado = skill.executar("exit 7")
    assert resultado.exit_code == 7
    assert resultado.status == "skill-falha"
    assert resultado.auditoria.motivo == "exit_code=7"


def test_timeout() -> None:
    """``ping -n 30`` excede 1s e produz status skill-timeout com exit_code -1.

    No Windows ``ping -n 30 127.0.0.1`` envia 30 pacotes a ~1s cada (~29s
    totais), o que garante que 1s de timeout é insuficiente.
    """
    skill = SkillTerminal()
    resultado = skill.executar("ping -n 30 127.0.0.1", timeout_s=1.0)
    assert resultado.status == "skill-timeout"
    assert resultado.exit_code == -1
    assert resultado.auditoria.status == "skill-timeout"
    assert "timeout" in (resultado.auditoria.motivo or "").lower()


# ---------------------------------------------------------------------------
# Validações pré-execução (ValueError)
# ---------------------------------------------------------------------------


def test_timeout_excede_maximo_lanca() -> None:
    """``timeout_s=400`` excede 300s e levanta ValueError em pt-BR."""
    skill = SkillTerminal()
    with pytest.raises(ValueError) as excinfo:
        skill.executar("dir", timeout_s=400)
    assert "300" in str(excinfo.value)
    assert "timeout" in str(excinfo.value).lower()


def test_comando_vazio_lanca() -> None:
    """``executar('')`` levanta ValueError sem tocar em subprocess."""
    skill = SkillTerminal()
    with pytest.raises(ValueError):
        skill.executar("")
    with pytest.raises(ValueError):
        skill.executar("   ")  # apenas whitespace também é vazio


def test_cwd_inexistente_lanca(tmp_path: Path) -> None:
    """``cwd`` que não existe levanta ValueError antes da execução."""
    skill = SkillTerminal()
    inexistente = tmp_path / "nao_existe"
    with pytest.raises(ValueError):
        skill.executar("dir", cwd=inexistente)


def test_cwd_default_inexistente_no_construtor_lanca(tmp_path: Path) -> None:
    """O construtor já valida ``cwd`` default — falha rápida é melhor."""
    inexistente = tmp_path / "nao_existe_construtor"
    with pytest.raises(ValueError):
        SkillTerminal(cwd=inexistente)


# ---------------------------------------------------------------------------
# Truncagem de saída
# ---------------------------------------------------------------------------


def test_truncagem_stdout(tmp_path: Path) -> None:
    """Saída maior que 10 MB é truncada e ``truncado_stdout`` fica True.

    Geramos a saída por meio de um script Python isolado em ``tmp_path`` para
    contornar limitações do ``cmd`` em construir strings imensas inline. Para
    invocar Python evitamos ``sys.executable`` (caminho absoluto com espaços
    sofre da regra de stripping de aspas do ``cmd /c``) e usamos o alias
    ``python`` do PATH com ``cwd=tmp_path``, o que mantém o comando livre de
    quoting frágil.
    """
    if shutil.which("python") is None:
        pytest.skip("python não disponível no PATH")
    script = tmp_path / "gerar.py"
    # 11 MB de 'x' — bem acima do limite de 10 MB para garantir truncagem.
    script.write_text(
        "import sys\n"
        "sys.stdout.write('x' * (11 * 1024 * 1024))\n",
        encoding="utf-8",
    )

    skill = SkillTerminal(cwd=tmp_path)
    resultado = skill.executar("python gerar.py", timeout_s=120.0)

    assert resultado.exit_code == 0, (
        f"script de geração falhou com stderr={resultado.stderr!r}"
    )
    assert resultado.truncado_stdout is True
    assert len(resultado.stdout.encode("utf-8")) <= _LIMITE_BYTES_POR_CANAL
    assert resultado.auditoria.truncado_stdout is True


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------


def test_auditoria_tem_hash_estavel() -> None:
    """Mesmo comando + mesmos parâmetros → mesmo hash SHA-256 entre invocações."""
    skill = SkillTerminal()
    r1 = skill.executar("echo estavel")
    r2 = skill.executar("echo estavel")
    assert r1.auditoria.parametros_hash_sha256 == r2.auditoria.parametros_hash_sha256
    # Sanity: hash sha256 hex tem 64 chars
    assert len(r1.auditoria.parametros_hash_sha256) == 64


def test_auditoria_hash_difere_quando_comando_muda() -> None:
    """Comandos diferentes produzem hashes diferentes."""
    skill = SkillTerminal()
    r1 = skill.executar("echo a")
    r2 = skill.executar("echo b")
    assert r1.auditoria.parametros_hash_sha256 != r2.auditoria.parametros_hash_sha256


def test_invocador_aparece_na_auditoria() -> None:
    """``invocador`` informado no construtor é propagado para o registro."""
    skill = SkillTerminal(invocador="Athena")
    resultado = skill.executar("echo identidade")
    assert resultado.auditoria.invocador == "Athena"


def test_invocador_default_none() -> None:
    """Sem invocador explícito, o campo permanece ``None``."""
    skill = SkillTerminal()
    resultado = skill.executar("echo anonimo")
    assert resultado.auditoria.invocador is None
