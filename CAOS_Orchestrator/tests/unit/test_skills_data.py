"""Testes unitários das Skills de dados (Task 6).

Cobre:

- :class:`caos.skills.data_inspector.SkillDataInspector` —
  inspeção de arquivos individuais e varredura recursiva (R11.6, R15.1).
- :class:`caos.skills.data_integrity.SkillDataIntegrity` —
  validação contra ``manifesto.json`` (R11.7, R15.4–R15.6).
- :class:`caos.data_manifest.DataManifestManager` —
  build/verify do manifesto + CLI ponta-a-ponta (R15.1–R15.6).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from caos.data_manifest import DataManifestManager, NOME_MANIFESTO
from caos.skills.data_inspector import (
    SkillDataInspector,
    SkillDataInspectorError,
    _inspecionar_streaming,
)
from caos.skills.data_integrity import (
    SkillDataIntegrity,
    SkillDataIntegrityError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CSV_HEADER = "timestamp,price\n"
CSV_LINHAS_DADOS = (
    "2026-01-02T13:30:00,18000.25\n"
    "2026-01-02T13:31:00,18001.00\n"
    "2026-01-02T13:32:00,18002.50\n"
)


def _criar_csv(path: Path, header: str = CSV_HEADER, dados: str = CSV_LINHAS_DADOS) -> bytes:
    """Cria um CSV simples e retorna seus bytes para hashing/teste."""
    conteudo = (header + dados).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(conteudo)
    return conteudo


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# Skill_Data_Inspector — arquivos individuais
# ---------------------------------------------------------------------------


def test_inspecionar_arquivo_csv_pequeno(tmp_path: Path) -> None:
    """CSV com header + 3 linhas: 4 linhas, hash correto, períodos UTC."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    csv_path = raiz / "file.csv"
    bytes_csv = _criar_csv(csv_path)

    skill = SkillDataInspector(raiz_dados=raiz)
    entrada = skill.inspecionar_arquivo(csv_path)

    assert entrada.nome_arquivo == "file.csv"
    assert entrada.tamanho_bytes == len(bytes_csv)
    assert entrada.num_linhas == 4
    assert entrada.hash_sha256 == _sha256(bytes_csv)
    assert entrada.instrumento == "MNQ"
    # Períodos parseados a partir de strings ISO sem fuso → UTC.
    assert entrada.periodo_inicial == datetime(
        2026, 1, 2, 13, 30, 0, tzinfo=timezone.utc
    )
    assert entrada.periodo_final == datetime(
        2026, 1, 2, 13, 32, 0, tzinfo=timezone.utc
    )


def test_inspecionar_arquivo_nao_csv(tmp_path: Path) -> None:
    """Arquivo .txt: períodos None, hash correto."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    txt_path = raiz / "anotacao.txt"
    conteudo = b"linha um\nlinha dois\nlinha tres\n"
    txt_path.write_bytes(conteudo)

    skill = SkillDataInspector(raiz_dados=raiz)
    entrada = skill.inspecionar_arquivo(txt_path)

    assert entrada.nome_arquivo == "anotacao.txt"
    assert entrada.num_linhas == 3
    assert entrada.hash_sha256 == _sha256(conteudo)
    assert entrada.periodo_inicial is None
    assert entrada.periodo_final is None


def test_inspecionar_arquivo_inexistente_lanca(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    skill = SkillDataInspector(raiz_dados=raiz)
    with pytest.raises(SkillDataInspectorError):
        skill.inspecionar_arquivo(raiz / "nao_existe.csv")


def test_inspecionar_arquivo_sem_newline_final(tmp_path: Path) -> None:
    """Arquivo cuja última linha não termina em '\\n' ainda conta como linha."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    csv = raiz / "sem_newline.csv"
    # Header + 2 linhas, sem '\n' final.
    conteudo = (
        b"timestamp,price\n"
        b"2026-01-02T13:30:00,18000.0\n"
        b"2026-01-02T13:31:00,18001.0"
    )
    csv.write_bytes(conteudo)

    skill = SkillDataInspector(raiz_dados=raiz)
    entrada = skill.inspecionar_arquivo(csv)

    assert entrada.num_linhas == 3
    assert entrada.periodo_inicial == datetime(
        2026, 1, 2, 13, 30, 0, tzinfo=timezone.utc
    )
    assert entrada.periodo_final == datetime(
        2026, 1, 2, 13, 31, 0, tzinfo=timezone.utc
    )


def test_inspecionar_arquivo_csv_so_header(tmp_path: Path) -> None:
    """CSV apenas com header: períodos None, num_linhas=1."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    csv = raiz / "vazio.csv"
    csv.write_bytes(b"timestamp,price\n")
    skill = SkillDataInspector(raiz_dados=raiz)
    entrada = skill.inspecionar_arquivo(csv)
    assert entrada.num_linhas == 1
    assert entrada.periodo_inicial is None
    assert entrada.periodo_final is None


# ---------------------------------------------------------------------------
# Skill_Data_Inspector — varredura recursiva
# ---------------------------------------------------------------------------


def test_varredura_recursiva_ordena_alfabeticamente(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    (raiz / "1m").mkdir(parents=True)
    (raiz / "tick").mkdir(parents=True)
    _criar_csv(raiz / "1m" / "a.csv")
    _criar_csv(raiz / "1m" / "b.csv")
    _criar_csv(raiz / "tick" / "z.csv")

    skill = SkillDataInspector(raiz_dados=raiz)
    resultado = skill.varrer_diretorio()

    nomes = [e.nome_arquivo for e in resultado.entradas]
    assert nomes == ["1m/a.csv", "1m/b.csv", "tick/z.csv"]
    assert resultado.sucesso is True
    assert resultado.falhas == []


def test_varredura_ignora_manifesto_json(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")
    (raiz / "manifesto.json").write_text("{}", encoding="utf-8")

    skill = SkillDataInspector(raiz_dados=raiz)
    resultado = skill.varrer_diretorio()

    nomes = [e.nome_arquivo for e in resultado.entradas]
    assert "manifesto.json" not in nomes
    assert nomes == ["a.csv"]


def test_varredura_falha_arquivo_ilegivel_continua(tmp_path: Path) -> None:
    """Quando um arquivo falha, varredura prossegue e a falha é registrada."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "ok.csv")
    ruim = raiz / "ruim.csv"
    ruim.write_bytes(b"timestamp,price\n2026-01-02T13:30:00,1\n")

    skill = SkillDataInspector(raiz_dados=raiz)

    # Mock injetado: força _inspecionar_streaming a falhar para 'ruim.csv'
    # mas processar normalmente os outros arquivos.
    original = _inspecionar_streaming

    def fake_streaming(caminho: Path, nome: str, instrumento: str):
        if caminho.name == "ruim.csv":
            raise SkillDataInspectorError(caminho, "erro de leitura: simulado")
        return original(caminho, nome, instrumento)

    with mock.patch(
        "caos.skills.data_inspector._inspecionar_streaming",
        side_effect=fake_streaming,
    ):
        resultado = skill.varrer_diretorio()

    nomes_ok = [e.nome_arquivo for e in resultado.entradas]
    assert nomes_ok == ["ok.csv"]
    assert len(resultado.falhas) == 1
    falha = resultado.falhas[0]
    assert falha.caminho_relativo == "ruim.csv"
    assert falha.categoria == "erro-de-leitura"


# ---------------------------------------------------------------------------
# Skill_Data_Integrity
# ---------------------------------------------------------------------------


def test_data_integrity_manifesto_intacto(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")
    _criar_csv(raiz / "b.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    gerente.build()

    skill = SkillDataIntegrity(
        raiz_dados=raiz,
        caminho_manifesto=raiz / NOME_MANIFESTO,
    )
    resultado = skill.validar()
    assert resultado.ok is True
    assert resultado.divergencias == []
    assert resultado.nao_registrados == []
    assert resultado.arquivos_ausentes == []


def test_data_integrity_arquivo_modificado(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")
    _criar_csv(raiz / "b.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    gerente.build()

    # Modifica 1 byte de a.csv
    a = raiz / "a.csv"
    bytes_a = a.read_bytes()
    a.write_bytes(b"X" + bytes_a[1:])

    skill = SkillDataIntegrity(
        raiz_dados=raiz,
        caminho_manifesto=raiz / NOME_MANIFESTO,
    )
    resultado = skill.validar()
    assert resultado.ok is False
    nomes_divergentes = [d.nome_arquivo for d in resultado.divergencias]
    assert "a.csv" in nomes_divergentes
    # E é divergência de hash, não arquivo ausente.
    div_a = next(d for d in resultado.divergencias if d.nome_arquivo == "a.csv")
    assert div_a.motivo == "hash-divergente"


def test_data_integrity_assert_ok_lanca_em_divergencia(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    gerente.build()

    a = raiz / "a.csv"
    a.write_bytes(b"corrompido!\n")

    skill = SkillDataIntegrity(
        raiz_dados=raiz,
        caminho_manifesto=raiz / NOME_MANIFESTO,
    )
    resultado = skill.validar()
    with pytest.raises(SkillDataIntegrityError) as exc_info:
        resultado.assert_ok()
    assert exc_info.value.categoria == "manifesto-divergente"
    assert "a.csv" in exc_info.value.arquivos_afetados


def test_data_integrity_arquivo_ausente_no_disco(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")
    _criar_csv(raiz / "b.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    gerente.build()

    (raiz / "a.csv").unlink()

    skill = SkillDataIntegrity(
        raiz_dados=raiz,
        caminho_manifesto=raiz / NOME_MANIFESTO,
    )
    resultado = skill.validar()
    assert resultado.ok is False
    assert "a.csv" in resultado.arquivos_ausentes
    motivos = {d.motivo for d in resultado.divergencias if d.nome_arquivo == "a.csv"}
    assert "arquivo-ausente" in motivos


def test_data_integrity_arquivo_nao_registrado(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    gerente.build()

    # Adiciona arquivo após o build.
    _criar_csv(raiz / "novo.csv")

    skill = SkillDataIntegrity(
        raiz_dados=raiz,
        caminho_manifesto=raiz / NOME_MANIFESTO,
    )
    resultado = skill.validar()
    assert resultado.ok is False
    assert "novo.csv" in resultado.nao_registrados


def test_data_integrity_manifesto_malformado_lanca_via_assert_ok(
    tmp_path: Path,
) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")
    manifesto = raiz / NOME_MANIFESTO
    manifesto.write_text("{ não é json válido", encoding="utf-8")

    skill = SkillDataIntegrity(
        raiz_dados=raiz,
        caminho_manifesto=manifesto,
    )
    resultado = skill.validar()
    assert resultado.ok is False
    assert resultado.erro_global is not None
    with pytest.raises(SkillDataIntegrityError) as exc_info:
        resultado.assert_ok()
    assert exc_info.value.categoria == "manifesto-malformado"


def test_data_integrity_construtor_recusa_manifesto_inexistente(
    tmp_path: Path,
) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    with pytest.raises(ValueError):
        SkillDataIntegrity(
            raiz_dados=raiz,
            caminho_manifesto=raiz / "nao_existe.json",
        )


# ---------------------------------------------------------------------------
# DataManifestManager
# ---------------------------------------------------------------------------


def test_data_manifest_build_escreve_json_canonico(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "b.csv")
    _criar_csv(raiz / "a.csv")
    _criar_csv(raiz / "c.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    resultado = gerente.build()

    assert resultado.caminho_manifesto == raiz / NOME_MANIFESTO
    assert resultado.escrito is True

    # Arquivo gravado é JSON parseável com chaves esperadas.
    payload = json.loads(
        (raiz / NOME_MANIFESTO).read_text(encoding="utf-8")
    )
    assert "geracao" in payload
    assert payload["geracao"]["instrumento"] == "MNQ"
    assert "data_iso8601_utc" in payload["geracao"]
    assert "entradas" in payload
    assert "falhas" in payload

    # Ordem alfabética por nome_arquivo.
    nomes = [e["nome_arquivo"] for e in payload["entradas"]]
    assert nomes == ["a.csv", "b.csv", "c.csv"]


def test_data_manifest_build_escrita_atomica_nao_deixa_tmp(
    tmp_path: Path,
) -> None:
    """Após build, o arquivo .tmp não deve existir."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")

    gerente = DataManifestManager(raiz_dados=raiz)
    gerente.build()

    # Não deve existir manifesto.json.tmp residual.
    assert not (raiz / "manifesto.json.tmp").exists()
    assert (raiz / NOME_MANIFESTO).is_file()


def test_data_manifest_verify_quando_manifesto_ausente(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(raiz / "a.csv")
    gerente = DataManifestManager(raiz_dados=raiz)
    resultado = gerente.verify()
    assert resultado.ok is False
    assert "ausente" in resultado.sumario_humano.lower()


# ---------------------------------------------------------------------------
# CLI ponta-a-ponta
# ---------------------------------------------------------------------------


def _construir_workspace_minimo(tmp_path: Path) -> Path:
    """Constrói um workspace mínimo com dados/MNQ/ pronto para testes da CLI."""
    raiz = tmp_path / "workspace"
    dados = raiz / "dados" / "MNQ"
    dados.mkdir(parents=True)
    _criar_csv(dados / "a.csv")
    _criar_csv(dados / "b.csv")
    return raiz


def test_cli_manifesto_build_e_verify_e2e(tmp_path: Path) -> None:
    """Testa ``caos manifesto build`` e ``caos manifesto verify`` via subprocess."""
    raiz = _construir_workspace_minimo(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    # build
    res_build = subprocess.run(
        [sys.executable, "-m", "caos.main", "manifesto", "build", "--root", str(raiz)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert res_build.returncode == 0, (
        f"build falhou: stdout={res_build.stdout!r} stderr={res_build.stderr!r}"
    )
    manifesto = raiz / "dados" / "MNQ" / NOME_MANIFESTO
    assert manifesto.is_file()

    # verify (deve passar)
    res_verify_ok = subprocess.run(
        [sys.executable, "-m", "caos.main", "manifesto", "verify", "--root", str(raiz)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert res_verify_ok.returncode == 0, (
        f"verify falhou inesperadamente: stdout={res_verify_ok.stdout!r} "
        f"stderr={res_verify_ok.stderr!r}"
    )

    # corrompe um arquivo e re-verify (deve falhar com exit 1)
    a = raiz / "dados" / "MNQ" / "a.csv"
    a.write_bytes(b"corrompido!\n")
    res_verify_falha = subprocess.run(
        [sys.executable, "-m", "caos.main", "manifesto", "verify", "--root", str(raiz)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert res_verify_falha.returncode == 1
    assert "a.csv" in res_verify_falha.stderr


def test_cli_manifesto_build_dados_ausente(tmp_path: Path) -> None:
    """Sem dados/MNQ/ a CLI deve falhar com mensagem clara."""
    raiz = tmp_path / "workspace"
    raiz.mkdir()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run(
        [sys.executable, "-m", "caos.main", "manifesto", "build", "--root", str(raiz)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert res.returncode == 1
    assert "ausente" in res.stderr.lower()
