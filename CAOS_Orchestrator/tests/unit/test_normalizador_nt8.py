"""Testes unitários do :mod:`caos.walk_forward.normalizador_nt8`.

Cobre a tradução do schema NT8 (sem cabeçalho, separador ``;``,
timestamp local em ``YYYYMMDD HHMMSS`` ou ``YYYYMMDD``) para o schema
canônico do CAOS (cabeçalho ``timestamp,open,high,low,close,volume``,
separador vírgula, timestamp ISO 8601 UTC, ordenação cronológica
estritamente crescente).

Plataforma: Windows + Python 3.11+ (``zoneinfo`` da stdlib).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from caos.walk_forward.normalizador_nt8 import (
    FUSO_DEFAULT_NT8,
    NormalizadorNt8Error,
    detectar_destino_canonico,
    normalizar_arquivo,
    varrer_e_normalizar,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escrever_minute(path: Path, linhas: list[str]) -> None:
    """Cria um ``.txt`` no formato NT8 minute (sem cabeçalho)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _escrever_day(path: Path, linhas: list[str]) -> None:
    """Cria um ``.txt`` no formato NT8 day (sem cabeçalho)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _ler_csv(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# detectar_destino_canonico
# ---------------------------------------------------------------------------


class TestDetectarDestinoCanonico:
    def test_minute_last(self, tmp_path: Path) -> None:
        txt = tmp_path / "MNQ 03-26.Last.txt"
        txt.write_text("", encoding="utf-8")
        destino = detectar_destino_canonico(txt)
        assert destino == tmp_path / "last.csv"

    @pytest.mark.parametrize(
        ("nome", "serie_esperada"),
        [
            ("MNQ 03-26.Ask.txt", "ask"),
            ("MNQ 06-25.Bid.txt", "bid"),
            ("MNQ 12-25.Last.txt", "last"),
            # Variante com underscore (caso o usuário renomeie):
            ("MNQ_09-25.Last.txt", "last"),
        ],
    )
    def test_extrai_serie(self, tmp_path: Path, nome: str, serie_esperada: str) -> None:
        txt = tmp_path / nome
        txt.write_text("", encoding="utf-8")
        destino = detectar_destino_canonico(txt)
        assert destino.name == f"{serie_esperada}.csv"

    @pytest.mark.parametrize(
        "nome_invalido",
        [
            "MNQ.Last.txt",
            "MNQ 03-26.Trade.txt",
            "ES 03-26.Last.txt",
            "mnq 03-26.last.txt",  # case-sensitive
            "outro.txt",
        ],
    )
    def test_rejeita_nomes_fora_do_padrao(
        self, tmp_path: Path, nome_invalido: str
    ) -> None:
        txt = tmp_path / nome_invalido
        txt.write_text("", encoding="utf-8")
        with pytest.raises(NormalizadorNt8Error) as exc:
            detectar_destino_canonico(txt)
        assert exc.value.categoria == "nome-arquivo-fora-do-padrao"


# ---------------------------------------------------------------------------
# normalizar_arquivo — schema da saída
# ---------------------------------------------------------------------------


class TestSchemaSaidaMinute:
    def test_cabecalho_canonico_e_iso_utc(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        # 03:01:00 BRT (UTC-3) = 06:01:00 UTC.
        _escrever_minute(
            txt,
            [
                "20251215 030100;25519;25527;25518.75;25526;207",
                "20251215 030200;25525.25;25527.5;25523.25;25527.25;143",
            ],
        )
        csv = tmp_path / "last.csv"
        resultado = normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
            fuso="America/Sao_Paulo",
        )
        assert resultado.linhas_lidas == 2
        assert resultado.linhas_escritas == 2
        assert resultado.pulado is False

        linhas = _ler_csv(csv)
        assert linhas[0] == "timestamp,open,high,low,close,volume"
        assert (
            linhas[1]
            == "2025-12-15T06:01:00Z,25519,25527,25518.75,25526,207"
        )
        assert (
            linhas[2]
            == "2025-12-15T06:02:00Z,25525.25,25527.5,25523.25,25527.25,143"
        )

    def test_preserva_decimais_do_origem(self, tmp_path: Path) -> None:
        """Não normalizamos a representação numérica — o CSV de saída
        carrega exatamente os mesmos dígitos do .txt original."""
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            [
                "20251215 030100;25519.0000;25527;25518.75000;25526;207"
            ],
        )
        csv = tmp_path / "out.csv"
        normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
        )
        linhas = _ler_csv(csv)
        assert (
            linhas[1]
            == "2025-12-15T06:01:00Z,25519.0000,25527,25518.75000,25526,207"
        )


class TestSchemaSaidaDay:
    def test_dia_inteiro_em_meia_noite_local(self, tmp_path: Path) -> None:
        # Meia-noite BRT (UTC-3) = 03:00:00 UTC do mesmo dia.
        txt = tmp_path / "src.txt"
        _escrever_day(
            txt,
            [
                "20251215;25474.75;25670;25286.5;25342.75;882905",
                "20251216;25356;25444;25073.75;25380.25;1705154",
            ],
        )
        csv = tmp_path / "last.csv"
        resultado = normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="day",
        )
        assert resultado.linhas_escritas == 2

        linhas = _ler_csv(csv)
        assert linhas[0] == "timestamp,open,high,low,close,volume"
        assert (
            linhas[1]
            == "2025-12-15T03:00:00Z,25474.75,25670,25286.5,25342.75,882905"
        )
        assert (
            linhas[2]
            == "2025-12-16T03:00:00Z,25356,25444,25073.75,25380.25,1705154"
        )


# ---------------------------------------------------------------------------
# Conversão de fuso
# ---------------------------------------------------------------------------


class TestConversaoFuso:
    def test_brasilia_e_utc_minus_3(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 120000;100;101;99;100.5;1"],
        )
        csv = tmp_path / "out.csv"
        normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
            fuso="America/Sao_Paulo",
        )
        # 12:00 BRT = 15:00 UTC.
        assert "2025-12-15T15:00:00Z" in _ler_csv(csv)[1]

    def test_utc_explicito_nao_aplica_offset(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 120000;100;101;99;100.5;1"],
        )
        csv = tmp_path / "out.csv"
        normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
            fuso="UTC",
        )
        # 12:00 UTC = 12:00 UTC (zero offset).
        assert "2025-12-15T12:00:00Z" in _ler_csv(csv)[1]

    def test_fuso_invalido_levanta(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 120000;100;101;99;100.5;1"],
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
                fuso="Atlantis/Capital",
            )
        assert exc.value.categoria == "fuso-invalido"

    def test_default_e_brasilia(self, tmp_path: Path) -> None:
        assert FUSO_DEFAULT_NT8 == "America/Sao_Paulo"


# ---------------------------------------------------------------------------
# Validações de schema
# ---------------------------------------------------------------------------


class TestSchemaValidacao:
    def test_arquivo_inexistente_levanta(self, tmp_path: Path) -> None:
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=tmp_path / "fantasma.txt",
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "arquivo-ausente"

    def test_linha_com_numero_errado_de_campos(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 120000;100;101;99;100.5"],  # 5 campos, faltam volume
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "linha-malformada"

    def test_timestamp_malformado(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["2025/12/15 12:00:00;100;101;99;100.5;1"],
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "timestamp-malformado"

    def test_timestamp_minute_em_arquivo_day_levanta(self, tmp_path: Path) -> None:
        # Timestamp YYYYMMDD HHMMSS com granularidade='day' → falha de
        # parsing porque o formato esperado para day é apenas YYYYMMDD.
        txt = tmp_path / "src.txt"
        _escrever_day(
            txt,
            ["20251215 120000;100;101;99;100.5;1"],
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="day",
            )
        assert exc.value.categoria == "timestamp-malformado"

    def test_valor_nao_numerico(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 120000;100;XYZ;99;100.5;1"],
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "numero-invalido"

    def test_linhas_vazias_sao_ignoradas(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        txt.write_text(
            "\n"
            "20251215 030100;100;101;99;100.5;1\n"
            "\n"
            "   \n"
            "20251215 030200;101;102;100;101.5;2\n",
            encoding="utf-8",
        )
        csv = tmp_path / "out.csv"
        resultado = normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
        )
        assert resultado.linhas_escritas == 2

    def test_arquivo_vazio_levanta(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        txt.write_text("\n   \n\n", encoding="utf-8")
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "arquivo-vazio"


# ---------------------------------------------------------------------------
# Ordenação cronológica
# ---------------------------------------------------------------------------


class TestOrdenacaoCronologica:
    def test_timestamps_iguais_levantam(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            [
                "20251215 030100;100;101;99;100.5;1",
                "20251215 030100;100;101;99;100.5;1",  # duplicado
            ],
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "fora-de-ordem"

    def test_timestamp_decrescente_levanta(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            [
                "20251215 030200;100;101;99;100.5;1",
                "20251215 030100;100;101;99;100.5;1",  # anterior
            ],
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=tmp_path / "out.csv",
                granularidade="minute",
            )
        assert exc.value.categoria == "fora-de-ordem"

    def test_csv_destino_nao_e_criado_se_falha_no_meio(
        self, tmp_path: Path
    ) -> None:
        """Em caso de erro, nenhum .csv parcial é deixado para trás."""
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            [
                "20251215 030100;100;101;99;100.5;1",
                "20251215 030100;100;101;99;100.5;1",  # quebra ordem
            ],
        )
        csv = tmp_path / "out.csv"
        with pytest.raises(NormalizadorNt8Error):
            normalizar_arquivo(
                arquivo_txt=txt,
                arquivo_csv=csv,
                granularidade="minute",
            )
        assert not csv.exists()
        assert not (tmp_path / "out.csv.tmp").exists()


# ---------------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------------


class TestIdempotencia:
    def test_pula_quando_csv_mais_novo_que_txt(self, tmp_path: Path) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 030100;100;101;99;100.5;1"],
        )
        csv = tmp_path / "out.csv"
        # Primeira execução grava o CSV.
        normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
        )
        # Garante que csv.mtime > txt.mtime aplicando offset positivo.
        epoch_txt = txt.stat().st_mtime
        import os

        os.utime(csv, (epoch_txt + 10, epoch_txt + 10))

        # Segunda execução deve pular.
        resultado = normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
        )
        assert resultado.pulado is True
        assert resultado.linhas_lidas == 0
        assert resultado.linhas_escritas == 0

    def test_forcar_reprocessa_mesmo_se_csv_mais_novo(
        self, tmp_path: Path
    ) -> None:
        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            ["20251215 030100;100;101;99;100.5;1"],
        )
        csv = tmp_path / "out.csv"
        normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
        )
        epoch_txt = txt.stat().st_mtime
        import os

        os.utime(csv, (epoch_txt + 10, epoch_txt + 10))

        resultado = normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
            forcar=True,
        )
        assert resultado.pulado is False
        assert resultado.linhas_escritas == 1


# ---------------------------------------------------------------------------
# varrer_e_normalizar
# ---------------------------------------------------------------------------


class TestVarrerENormalizar:
    def test_varre_estrutura_canonica_e_gera_csvs(
        self, tmp_path: Path
    ) -> None:
        # Estrutura: dados/MNQ/MNQ_03-26/{minute,day}/MNQ 03-26.Last.txt
        for granularidade, linhas in [
            (
                "minute",
                ["20251215 030100;100;101;99;100.5;1"],
            ),
            (
                "day",
                ["20251215;100;101;99;100.5;100"],
            ),
        ]:
            d = tmp_path / "dados" / "MNQ" / "MNQ_03-26" / granularidade
            d.mkdir(parents=True)
            (d / "MNQ 03-26.Last.txt").write_text(
                "\n".join(linhas) + "\n", encoding="utf-8"
            )

        resultados = varrer_e_normalizar(raiz_workspace=tmp_path)
        assert len(resultados) == 2
        assert all(r.linhas_escritas == 1 for r in resultados)

        # Verificações dos CSVs gerados.
        csv_min = (
            tmp_path
            / "dados"
            / "MNQ"
            / "MNQ_03-26"
            / "minute"
            / "last.csv"
        )
        csv_day = (
            tmp_path
            / "dados"
            / "MNQ"
            / "MNQ_03-26"
            / "day"
            / "last.csv"
        )
        assert csv_min.is_file()
        assert csv_day.is_file()
        assert "2025-12-15T06:01:00Z" in csv_min.read_text(encoding="utf-8")
        assert "2025-12-15T03:00:00Z" in csv_day.read_text(encoding="utf-8")

    def test_arquivos_sem_padrao_nt8_sao_ignorados(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "dados" / "MNQ" / "MNQ_03-26" / "minute"
        d.mkdir(parents=True)
        (d / "notas.txt").write_text("isto não é um export NT8", encoding="utf-8")
        resultados = varrer_e_normalizar(raiz_workspace=tmp_path)
        assert resultados == []

    def test_nome_em_diretorio_de_outro_contrato_levanta(
        self, tmp_path: Path
    ) -> None:
        # MNQ 06-25.Last.txt dentro de MNQ_03-26/ é incoerente.
        d = tmp_path / "dados" / "MNQ" / "MNQ_03-26" / "minute"
        d.mkdir(parents=True)
        (d / "MNQ 06-25.Last.txt").write_text(
            "20251215 030100;100;101;99;100.5;1\n", encoding="utf-8"
        )
        with pytest.raises(NormalizadorNt8Error) as exc:
            varrer_e_normalizar(raiz_workspace=tmp_path)
        assert exc.value.categoria == "contrato-divergente"

    def test_diretorio_dados_inexistente_devolve_lista_vazia(
        self, tmp_path: Path
    ) -> None:
        resultados = varrer_e_normalizar(raiz_workspace=tmp_path)
        assert resultados == []


# ---------------------------------------------------------------------------
# Integração com o data_reader (round-trip)
# ---------------------------------------------------------------------------


class TestRoundTripComDataReader:
    """O CSV gerado pelo normalizador DEVE ser aceito pelo schema
    rígido do :class:`SkillDataReader` (Spec 2)."""

    def test_csv_passa_pelo_skill_data_reader(self, tmp_path: Path) -> None:
        from caos.walk_forward.data_reader import SkillDataReader

        # Estrutura mínima esperada pelo SkillDataReader.
        raiz_dados = tmp_path / "dados"
        raiz_dados.mkdir()
        # SkillDataReader exige raiz_dados ser diretório; manifesto pode
        # ser stubado via flag interna — usamos `ler_csv` (que NÃO
        # invoca a integridade) para focar no schema do CSV.
        reader = SkillDataReader(raiz_dados=raiz_dados)

        txt = tmp_path / "src.txt"
        _escrever_minute(
            txt,
            [
                "20251215 030100;25519;25527;25518.75;25526;207",
                "20251215 030200;25525.25;25527.5;25523.25;25527.25;143",
                "20251215 030300;25527.25;25530.75;25524.5;25529.75;185",
            ],
        )
        csv = tmp_path / "last.csv"
        normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade="minute",
        )

        df = reader.ler_csv(csv)
        assert list(df.columns) == [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        assert len(df) == 3
        # Timestamp foi convertido para UTC e mantém ordem.
        assert df["timestamp"].iloc[0] == datetime(
            2025, 12, 15, 6, 1, 0, tzinfo=timezone.utc
        )
        assert df["timestamp"].is_monotonic_increasing
        assert df["close"].iloc[-1] == pytest.approx(25529.75)


# ---------------------------------------------------------------------------
# Reexport via pacote
# ---------------------------------------------------------------------------


def test_simbolos_reexportados_pelo_pacote() -> None:
    from caos.walk_forward import (
        FUSO_DEFAULT_NT8 as FUSO_REEXP,
        NormalizadorNt8Error as ERROR_REEXP,
        normalizar_arquivo as NORM_REEXP,
        varrer_e_normalizar as VARRER_REEXP,
    )

    assert FUSO_REEXP == FUSO_DEFAULT_NT8
    assert ERROR_REEXP is NormalizadorNt8Error
    assert NORM_REEXP is normalizar_arquivo
    assert VARRER_REEXP is varrer_e_normalizar
