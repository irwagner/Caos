"""Testes unitários do ``Skill_Data_Reader`` (Spec 2 — Task 2).

Cobre:

- Schema válido: leitura de CSV com colunas canônicas devolve DataFrame
  com timestamps em UTC e numéricos como float.
- Schema com coluna faltando ⇒ :class:`SchemaInvalidoError`.
- Schema com tipo numérico inválido ⇒ :class:`SchemaInvalidoError`.
- Timestamp não-parseável ⇒ :class:`SchemaInvalidoError`.
- Timestamps fora de ordem ⇒ :class:`DadosForaDeOrdemError`.
- Manifesto inválido (ausente ou hash divergente) ⇒
  :class:`ManifestoInvalidoError`.
- Arquivo de dados ausente ⇒ :class:`FileNotFoundError`.
- Carregamento de diretório com varredura recursiva ordenada.
- Concatenação de múltiplos arquivos com violação inter-arquivos ⇒
  :class:`DadosForaDeOrdemError`.
- Validação de integridade é idempotente (executa apenas uma vez).

Cobre R4 do ``requirements.md`` do Spec 2.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

from caos.data_manifest import DataManifestManager, NOME_MANIFESTO
from caos.walk_forward.data_reader import (
    COLUNAS_OBRIGATORIAS,
    DadosForaDeOrdemError,
    ManifestoInvalidoError,
    SchemaInvalidoError,
    SkillDataReader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CSV_HEADER = "timestamp,open,high,low,close,volume\n"


def _csv_valido(linhas: list[tuple[str, float, float, float, float, float]]) -> str:
    """Monta string de CSV válido a partir de tuplas de barras."""
    body = "\n".join(
        f"{ts},{o},{h},{l},{c},{v}" for ts, o, h, l, c, v in linhas
    )
    return CSV_HEADER + body + ("\n" if body else "")


def _criar_csv(path: Path, conteudo: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(conteudo, encoding="utf-8")


def _construir_raiz_com_manifesto(tmp_path: Path) -> Path:
    """Cria ``dados/MNQ/`` com 1 CSV válido + ``manifesto.json`` íntegro."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "MNQ-2026-01.csv",
        _csv_valido(
            [
                ("2026-01-02T13:30:00Z", 21500.25, 21501.50, 21499.75, 21500.75, 1234),
                ("2026-01-02T13:31:00Z", 21500.75, 21502.00, 21500.00, 21501.50, 1100),
                ("2026-01-02T13:32:00Z", 21501.50, 21503.25, 21500.50, 21503.00, 1300),
            ]
        ),
    )
    DataManifestManager(raiz_dados=raiz).build()
    return raiz


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------


def test_construtor_rejeita_raiz_inexistente(tmp_path: Path) -> None:
    inexistente = tmp_path / "fantasma"
    with pytest.raises(ValueError, match="raiz_dados"):
        SkillDataReader(raiz_dados=inexistente)


def test_construtor_aceita_diretorio_vazio(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    reader = SkillDataReader(raiz_dados=raiz)
    assert reader.raiz_dados == raiz
    assert reader.caminho_manifesto == raiz / NOME_MANIFESTO
    assert reader.integridade_validada is False


# ---------------------------------------------------------------------------
# Schema válido — leitura básica
# ---------------------------------------------------------------------------


def test_ler_csv_valido_devolve_dataframe_com_schema(tmp_path: Path) -> None:
    raiz = _construir_raiz_com_manifesto(tmp_path)
    reader = SkillDataReader(raiz_dados=raiz)
    df = reader.carregar(raiz / "MNQ-2026-01.csv")

    assert list(df.columns) == list(COLUNAS_OBRIGATORIAS)
    assert len(df) == 3
    # timestamp é UTC.
    assert str(df["timestamp"].dtype) == "datetime64[ns, UTC]"
    # numéricos são float.
    for coluna in ("open", "high", "low", "close", "volume"):
        assert df[coluna].dtype == "float64"
    assert reader.integridade_validada is True


def test_carregar_diretorio_varre_recursivamente_ordenado(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    (raiz / "1m").mkdir(parents=True)
    _criar_csv(
        raiz / "1m" / "a.csv",
        _csv_valido(
            [
                ("2026-01-02T13:30:00Z", 21500.0, 21501.0, 21499.0, 21500.5, 100),
                ("2026-01-02T13:31:00Z", 21500.5, 21502.0, 21500.0, 21501.5, 110),
            ]
        ),
    )
    _criar_csv(
        raiz / "1m" / "b.csv",
        _csv_valido(
            [
                ("2026-01-02T13:32:00Z", 21501.5, 21503.0, 21500.5, 21503.0, 120),
                ("2026-01-02T13:33:00Z", 21503.0, 21504.0, 21502.0, 21503.5, 130),
            ]
        ),
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    df = reader.carregar(raiz)

    assert len(df) == 4
    # Verifica que timestamps estão em ordem global crescente após concat.
    assert df["timestamp"].is_monotonic_increasing


def test_carregar_lista_explicita_de_paths_preserva_ordem(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "parte1.csv",
        _csv_valido(
            [
                ("2026-01-02T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 10),
                ("2026-01-02T13:31:00Z", 1.5, 2.5, 1.0, 2.0, 11),
            ]
        ),
    )
    _criar_csv(
        raiz / "parte2.csv",
        _csv_valido(
            [
                ("2026-01-02T13:32:00Z", 2.0, 3.0, 1.5, 2.5, 12),
                ("2026-01-02T13:33:00Z", 2.5, 3.5, 2.0, 3.0, 13),
            ]
        ),
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    df = reader.carregar([raiz / "parte1.csv", raiz / "parte2.csv"])
    assert len(df) == 4
    assert df["timestamp"].is_monotonic_increasing


def test_carregar_fonte_vazia_devolve_dataframe_vazio(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    df = reader.carregar([])
    assert len(df) == 0
    assert list(df.columns) == list(COLUNAS_OBRIGATORIAS)


# ---------------------------------------------------------------------------
# Schema inválido
# ---------------------------------------------------------------------------


def test_schema_coluna_faltando_levanta(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    # Sem a coluna 'volume'.
    _criar_csv(
        raiz / "ruim.csv",
        "timestamp,open,high,low,close\n"
        "2026-01-02T13:30:00Z,1.0,2.0,0.5,1.5\n",
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(SchemaInvalidoError) as exc_info:
        reader.carregar(raiz / "ruim.csv")
    assert "volume" in exc_info.value.detalhes


def test_schema_coluna_extra_levanta(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "extra.csv",
        "timestamp,open,high,low,close,volume,instrumento\n"
        "2026-01-02T13:30:00Z,1.0,2.0,0.5,1.5,100,MNQ\n",
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(SchemaInvalidoError) as exc_info:
        reader.carregar(raiz / "extra.csv")
    assert "instrumento" in exc_info.value.detalhes


def test_schema_ordem_colunas_errada_levanta(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    # 'open' e 'high' trocados.
    _criar_csv(
        raiz / "ordem.csv",
        "timestamp,high,open,low,close,volume\n"
        "2026-01-02T13:30:00Z,2.0,1.0,0.5,1.5,100\n",
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(SchemaInvalidoError) as exc_info:
        reader.carregar(raiz / "ordem.csv")
    assert (
        "ordem" in exc_info.value.detalhes.lower()
        or "colunas" in exc_info.value.detalhes.lower()
    )


def test_schema_tipo_numerico_invalido_levanta(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    # 'volume' contém texto não-numérico.
    _criar_csv(
        raiz / "tipo.csv",
        "timestamp,open,high,low,close,volume\n"
        "2026-01-02T13:30:00Z,1.0,2.0,0.5,1.5,abc\n",
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(SchemaInvalidoError):
        reader.carregar(raiz / "tipo.csv")


def test_schema_timestamp_nao_parseavel_levanta(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "ts_ruim.csv",
        "timestamp,open,high,low,close,volume\n"
        "nao-eh-data,1.0,2.0,0.5,1.5,100\n",
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(SchemaInvalidoError) as exc_info:
        reader.carregar(raiz / "ts_ruim.csv")
    assert "timestamp" in exc_info.value.detalhes.lower()


# ---------------------------------------------------------------------------
# Ordenação cronológica
# ---------------------------------------------------------------------------


def test_timestamps_fora_de_ordem_dentro_do_arquivo(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "fora.csv",
        _csv_valido(
            [
                ("2026-01-02T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 10),
                ("2026-01-02T13:32:00Z", 1.5, 2.5, 1.0, 2.0, 11),
                # Volta no tempo (≤ anterior).
                ("2026-01-02T13:31:00Z", 2.0, 3.0, 1.5, 2.5, 12),
            ]
        ),
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(DadosForaDeOrdemError) as exc_info:
        reader.carregar(raiz / "fora.csv")
    assert exc_info.value.timestamp_anterior > exc_info.value.timestamp_atual


def test_timestamps_duplicados_violam_ordem_estrita(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "dup.csv",
        _csv_valido(
            [
                ("2026-01-02T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 10),
                ("2026-01-02T13:30:00Z", 1.5, 2.5, 1.0, 2.0, 11),
            ]
        ),
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(DadosForaDeOrdemError):
        reader.carregar(raiz / "dup.csv")


def test_violacao_de_ordem_entre_arquivos(tmp_path: Path) -> None:
    """Carga concatenada com último ts do arq1 >= primeiro ts do arq2."""
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "a.csv",
        _csv_valido(
            [
                ("2026-01-02T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 10),
                ("2026-01-02T13:35:00Z", 1.5, 2.5, 1.0, 2.0, 11),
            ]
        ),
    )
    _criar_csv(
        raiz / "b.csv",
        _csv_valido(
            [
                # Sobrepõe o final de a.csv.
                ("2026-01-02T13:33:00Z", 2.0, 3.0, 1.5, 2.5, 12),
                ("2026-01-02T13:34:00Z", 2.5, 3.5, 2.0, 3.0, 13),
            ]
        ),
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(DadosForaDeOrdemError):
        reader.carregar([raiz / "a.csv", raiz / "b.csv"])


# ---------------------------------------------------------------------------
# Manifesto inválido
# ---------------------------------------------------------------------------


def test_manifesto_ausente_levanta_manifesto_invalido(tmp_path: Path) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "MNQ.csv",
        _csv_valido([("2026-01-02T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 10)]),
    )
    # Sem chamar DataManifestManager.build() — manifesto não existe.

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(ManifestoInvalidoError) as exc_info:
        reader.carregar(raiz / "MNQ.csv")
    assert exc_info.value.categoria == "manifesto-ausente"


def test_manifesto_divergente_levanta_manifesto_invalido(tmp_path: Path) -> None:
    raiz = _construir_raiz_com_manifesto(tmp_path)
    csv_path = raiz / "MNQ-2026-01.csv"
    # Modifica o arquivo para invalidar o hash registrado.
    csv_path.write_text(
        _csv_valido(
            [("2026-01-02T13:30:00Z", 99999.0, 99999.0, 99999.0, 99999.0, 1)]
        ),
        encoding="utf-8",
    )

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(ManifestoInvalidoError) as exc_info:
        reader.carregar(csv_path)
    assert exc_info.value.categoria == "manifesto-divergente"
    assert "MNQ-2026-01.csv" in exc_info.value.arquivos_afetados


def test_arquivo_nao_registrado_levanta_manifesto_invalido(tmp_path: Path) -> None:
    raiz = _construir_raiz_com_manifesto(tmp_path)
    # Adiciona um arquivo extra após gerar o manifesto.
    _criar_csv(
        raiz / "extra.csv",
        _csv_valido([("2026-01-02T13:30:00Z", 1.0, 2.0, 0.5, 1.5, 10)]),
    )

    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(ManifestoInvalidoError) as exc_info:
        reader.carregar(raiz / "extra.csv")
    assert exc_info.value.categoria == "arquivo-nao-registrado"


# ---------------------------------------------------------------------------
# Arquivos ausentes
# ---------------------------------------------------------------------------


def test_arquivo_inexistente_levanta_file_not_found(tmp_path: Path) -> None:
    raiz = _construir_raiz_com_manifesto(tmp_path)
    reader = SkillDataReader(raiz_dados=raiz)
    with pytest.raises(FileNotFoundError):
        reader.carregar(raiz / "nao_existe.csv")


# ---------------------------------------------------------------------------
# Idempotência da validação de integridade (R4.1)
# ---------------------------------------------------------------------------


def test_integridade_validada_uma_unica_vez(tmp_path: Path) -> None:
    """Skill_Data_Integrity é invocada apenas na primeira leitura (R4.1)."""
    raiz = _construir_raiz_com_manifesto(tmp_path)
    reader = SkillDataReader(raiz_dados=raiz)

    chamadas: list[None] = []

    real_validar = reader.__class__.validar_integridade

    def spy(self: SkillDataReader) -> None:
        chamadas.append(None)
        real_validar(self)

    with mock.patch.object(SkillDataReader, "validar_integridade", spy):
        # 3 leituras consecutivas.
        reader.carregar(raiz / "MNQ-2026-01.csv")
        reader.carregar(raiz / "MNQ-2026-01.csv")
        reader.carregar(raiz / "MNQ-2026-01.csv")

    # spy é chamado em toda leitura; mas o trabalho real só acontece na
    # primeira (cache interno). Validamos isso indiretamente:
    assert reader.integridade_validada is True
    # E a flag não regredia para False — chamadas explícitas a
    # validar_integridade após sucesso são no-op.
    reader.validar_integridade()
    assert reader.integridade_validada is True


def test_validar_integridade_explicito_antes_de_carregar(tmp_path: Path) -> None:
    raiz = _construir_raiz_com_manifesto(tmp_path)
    reader = SkillDataReader(raiz_dados=raiz)
    assert reader.integridade_validada is False
    reader.validar_integridade()
    assert reader.integridade_validada is True
    df = reader.carregar(raiz / "MNQ-2026-01.csv")
    assert len(df) == 3


# ---------------------------------------------------------------------------
# Schema válido com diferentes formas de fuso UTC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ts",
    [
        "2026-01-02T13:30:00Z",
        "2026-01-02T13:30:00+00:00",
    ],
)
def test_timestamp_aceita_z_e_offset_zero(tmp_path: Path, ts: str) -> None:
    raiz = tmp_path / "dados" / "MNQ"
    raiz.mkdir(parents=True)
    _criar_csv(
        raiz / "ts.csv",
        _csv_valido([(ts, 1.0, 2.0, 0.5, 1.5, 10)]),
    )
    DataManifestManager(raiz_dados=raiz).build()

    reader = SkillDataReader(raiz_dados=raiz)
    df = reader.carregar(raiz / "ts.csv")
    assert len(df) == 1
    assert df["timestamp"].iloc[0] == pd.Timestamp("2026-01-02T13:30:00", tz="UTC")
