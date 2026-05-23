"""Testes unitários do módulo ``caos.walk_forward.fontes_dados``.

Cobre os helpers que resolvem ``dados/MNQ/<contrato>/<granularidade>/<serie>.csv``
em ``Path`` absoluto, validam identificadores e listam contratos
disponíveis no workspace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from caos.walk_forward.fontes_dados import (
    DIR_RAIZ_MNQ_RELATIVO,
    FonteCsv,
    FonteDadosError,
    GRANULARIDADES_VALIDAS,
    SERIES_VALIDAS,
    listar_contratos_disponiveis,
    listar_csvs_existentes,
    resolver_fonte,
    validar_contrato,
    validar_granularidade,
    validar_serie,
)


def _criar_estrutura_completa(raiz: Path, contratos: tuple[str, ...]) -> None:
    """Cria diretórios canônicos e arquivos vazios para todos os contratos."""
    for contrato in contratos:
        for granularidade in ("minute", "day"):
            d = raiz / "dados" / "MNQ" / contrato / granularidade
            d.mkdir(parents=True, exist_ok=True)
            for serie in ("ask", "bid", "last"):
                (d / f"{serie}.csv").write_text("placeholder", encoding="utf-8")


# ---------------------------------------------------------------------------
# validar_*
# ---------------------------------------------------------------------------


class TestValidarContrato:
    @pytest.mark.parametrize(
        "valido",
        [
            "MNQ_03-26",
            "MNQ_06-25",
            "MNQ_06-26",
            "MNQ_09-25",
            "MNQ_12-25",
            "MNQ_03-99",
        ],
    )
    def test_aceita_contratos_canonicos(self, valido: str) -> None:
        validar_contrato(valido)  # não levanta

    @pytest.mark.parametrize(
        "invalido",
        [
            "MNQ_01-26",      # mês 01 não é trimestral
            "MNQ_04-26",      # mês 04 idem
            "MNQ_03-260",     # ano com 3 dígitos
            "ES_03-26",       # outro instrumento
            "mnq_03-26",      # minúsculo
            "MNQ-03-26",      # separador errado
            "MNQ_03_26",      # separador errado
            "MNQ 03-26",      # espaço (formato NT8 — rejeitado em disco)
            "",
            "MNQ",
        ],
    )
    def test_rejeita_contratos_fora_do_padrao(self, invalido: str) -> None:
        with pytest.raises(FonteDadosError) as exc:
            validar_contrato(invalido)
        assert exc.value.categoria == "contrato-invalido"


class TestValidarGranularidade:
    @pytest.mark.parametrize("g", ["minute", "day", "tick"])
    def test_aceita_granularidades_canonicas(self, g: str) -> None:
        validar_granularidade(g)

    @pytest.mark.parametrize("g", ["1m", "5m", "minuto", "Minute", "", "MIN"])
    def test_rejeita_granularidades_fora_do_dominio(self, g: str) -> None:
        with pytest.raises(FonteDadosError) as exc:
            validar_granularidade(g)
        assert exc.value.categoria == "granularidade-invalida"


class TestValidarSerie:
    @pytest.mark.parametrize("s", ["ask", "bid", "last"])
    def test_aceita_series_canonicas(self, s: str) -> None:
        validar_serie(s)

    @pytest.mark.parametrize("s", ["Ask", "BID", "trade", "vwap", "", "open"])
    def test_rejeita_series_fora_do_dominio(self, s: str) -> None:
        with pytest.raises(FonteDadosError) as exc:
            validar_serie(s)
        assert exc.value.categoria == "serie-invalida"


# ---------------------------------------------------------------------------
# resolver_fonte
# ---------------------------------------------------------------------------


class TestResolverFonte:
    def test_resolve_caminho_canonico(self, tmp_path: Path) -> None:
        _criar_estrutura_completa(tmp_path, ("MNQ_03-26",))
        fonte = resolver_fonte(
            raiz_workspace=tmp_path,
            contrato="MNQ_03-26",
            granularidade="minute",
            serie="last",
        )
        assert isinstance(fonte, FonteCsv)
        assert fonte.contrato == "MNQ_03-26"
        assert fonte.granularidade == "minute"
        assert fonte.serie == "last"
        assert fonte.caminho == (
            tmp_path / "dados" / "MNQ" / "MNQ_03-26" / "minute" / "last.csv"
        ).resolve()
        assert fonte.existe()

    def test_default_serie_e_last(self, tmp_path: Path) -> None:
        _criar_estrutura_completa(tmp_path, ("MNQ_06-25",))
        fonte = resolver_fonte(
            raiz_workspace=tmp_path,
            contrato="MNQ_06-25",
            granularidade="day",
        )
        assert fonte.serie == "last"

    def test_arquivo_inexistente_nao_levanta_apenas_marca_existe_falso(
        self, tmp_path: Path
    ) -> None:
        # Cria os diretórios mas não os arquivos.
        (tmp_path / "dados" / "MNQ" / "MNQ_03-26" / "minute").mkdir(parents=True)
        fonte = resolver_fonte(
            raiz_workspace=tmp_path,
            contrato="MNQ_03-26",
            granularidade="minute",
            serie="last",
        )
        assert fonte.existe() is False

    def test_raiz_inexistente_levanta(self, tmp_path: Path) -> None:
        with pytest.raises(FonteDadosError) as exc:
            resolver_fonte(
                raiz_workspace=tmp_path / "nao-existe",
                contrato="MNQ_03-26",
                granularidade="minute",
                serie="last",
            )
        assert exc.value.categoria == "raiz-invalida"

    def test_propaga_erro_de_contrato_invalido(self, tmp_path: Path) -> None:
        with pytest.raises(FonteDadosError) as exc:
            resolver_fonte(
                raiz_workspace=tmp_path,
                contrato="MNQ_01-26",
                granularidade="minute",
                serie="last",
            )
        assert exc.value.categoria == "contrato-invalido"


# ---------------------------------------------------------------------------
# listar_contratos_disponiveis
# ---------------------------------------------------------------------------


class TestListarContratosDisponiveis:
    def test_lista_em_ordem_alfabetica(self, tmp_path: Path) -> None:
        _criar_estrutura_completa(
            tmp_path,
            (
                "MNQ_03-26",
                "MNQ_06-25",
                "MNQ_06-26",
                "MNQ_09-25",
                "MNQ_12-25",
            ),
        )
        contratos = listar_contratos_disponiveis(tmp_path)
        # Ordem alfabética numérica/lex: 03-26, 06-25, 06-26, 09-25, 12-25.
        assert contratos == [
            "MNQ_03-26",
            "MNQ_06-25",
            "MNQ_06-26",
            "MNQ_09-25",
            "MNQ_12-25",
        ]

    def test_diretorio_inexistente_devolve_lista_vazia(self, tmp_path: Path) -> None:
        contratos = listar_contratos_disponiveis(tmp_path)
        assert contratos == []

    def test_diretorios_fora_do_padrao_sao_ignorados(self, tmp_path: Path) -> None:
        raiz_mnq = tmp_path / "dados" / "MNQ"
        raiz_mnq.mkdir(parents=True)
        (raiz_mnq / "MNQ_03-26").mkdir()
        (raiz_mnq / "ES_03-26").mkdir()
        (raiz_mnq / "lixo").mkdir()
        (raiz_mnq / "manifesto.json").write_text("{}", encoding="utf-8")
        contratos = listar_contratos_disponiveis(tmp_path)
        assert contratos == ["MNQ_03-26"]


# ---------------------------------------------------------------------------
# listar_csvs_existentes
# ---------------------------------------------------------------------------


class TestListarCsvsExistentes:
    def test_devolve_apenas_arquivos_presentes(self, tmp_path: Path) -> None:
        # Cria minute/last.csv e day/ask.csv apenas.
        d_min = tmp_path / "dados" / "MNQ" / "MNQ_03-26" / "minute"
        d_day = tmp_path / "dados" / "MNQ" / "MNQ_03-26" / "day"
        d_min.mkdir(parents=True)
        d_day.mkdir(parents=True)
        (d_min / "last.csv").write_text("x", encoding="utf-8")
        (d_day / "ask.csv").write_text("x", encoding="utf-8")

        presentes = listar_csvs_existentes(tmp_path, "MNQ_03-26")
        # Tipos de granularidade e série fixos (validados pelo regex).
        nomes = {(f.granularidade, f.serie) for f in presentes}
        assert nomes == {("minute", "last"), ("day", "ask")}

    def test_contrato_invalido_levanta(self, tmp_path: Path) -> None:
        with pytest.raises(FonteDadosError) as exc:
            listar_csvs_existentes(tmp_path, "MNQ_01-26")
        assert exc.value.categoria == "contrato-invalido"

    def test_raiz_inexistente_levanta(self, tmp_path: Path) -> None:
        with pytest.raises(FonteDadosError) as exc:
            listar_csvs_existentes(tmp_path / "fantasma", "MNQ_03-26")
        assert exc.value.categoria == "raiz-invalida"


# ---------------------------------------------------------------------------
# Reexports
# ---------------------------------------------------------------------------


def test_constantes_reexportadas_pelo_pacote() -> None:
    from caos.walk_forward import (
        DIR_RAIZ_MNQ_RELATIVO as DIR_REEXPORT,
        GRANULARIDADES_VALIDAS as G_REEXPORT,
        SERIES_VALIDAS as S_REEXPORT,
    )

    assert DIR_REEXPORT == DIR_RAIZ_MNQ_RELATIVO
    assert G_REEXPORT == GRANULARIDADES_VALIDAS
    assert S_REEXPORT == SERIES_VALIDAS
