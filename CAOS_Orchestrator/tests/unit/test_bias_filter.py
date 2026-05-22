"""Testes unitários do Bias_Filter do Explorador (R12.1–R12.8).

Cobre os 7 fluxos de status declarados em :func:`caos.bias_filter.avaliar_paper`,
suas precedências, o guard :func:`validar_link_de_entrada` (R12.8) e o helper
:func:`armazenar_em_papers` (R12.5). Também valida a integração com
:class:`NotaPaper` via :func:`construir_nota_paper`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter
import pytest

from caos.bias_filter import (
    LIMITE_SHARPE,
    MINIMO_OUT_OF_SAMPLE_DIAS_UTEIS,
    MINIMO_SAMPLE_SIZE_DIAS_UTEIS,
    ResultadoValidacaoLink,
    armazenar_em_papers,
    avaliar_paper,
    construir_nota_paper,
    validar_link_de_entrada,
)
from caos.models import NotaPaper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entradas_aprovadas() -> dict[str, Any]:
    """Conjunto canônico de entradas que produz ``status == 'aprovada'``."""
    return {
        "sharpe_replicado": 1.5,
        "sample_size": 500,
        "out_of_sample_periodo": 120,
        "instrumento_testado": "MNQ",
        "survivorship_bias_tratado": True,
    }


def _kwargs_construir(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "titulo": "Volatility Clustering in Micro Futures",
        "tags": ["volatility", "garch"],
        "data_criacao": "2026-05-14T15:00:00Z",
        "agente_autor": "Explorador",
        "sharpe_replicado": 0.74,
        "sample_size": 504,
        "out_of_sample_periodo": 126,
        "instrumento_testado": "MNQ",
        "survivorship_bias_tratado": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# avaliar_paper — casos de status individuais
# ---------------------------------------------------------------------------


class TestAvaliarPaperCasoBase:
    def test_paper_completo_e_aprovado(self) -> None:
        """R12.1: passar em todos os critérios produz ``aprovada``."""
        assert avaliar_paper(**_entradas_aprovadas()) == "aprovada"

    def test_dados_incompletos_via_None_em_cada_campo(self) -> None:
        """R12.6: qualquer um dos 5 campos como ``None`` → ``dados-incompletos``."""
        for chave in (
            "sharpe_replicado",
            "sample_size",
            "out_of_sample_periodo",
            "instrumento_testado",
            "survivorship_bias_tratado",
        ):
            entradas = _entradas_aprovadas()
            entradas[chave] = None
            assert avaliar_paper(**entradas) == "dados-incompletos", chave

    def test_dados_incompletos_via_tipo_errado_no_sharpe(self) -> None:
        """R12.6: ``sharpe_replicado`` string → ``dados-incompletos``."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = "abc"  # type: ignore[arg-type]
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_dados_incompletos_via_bool_no_sharpe(self) -> None:
        """``bool`` em campo numérico não pode ser aceito como int (R12.6)."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = True  # type: ignore[arg-type]
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_dados_incompletos_via_instrumento_vazio(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["instrumento_testado"] = "   "
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_dados_incompletos_via_sample_negativo(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["sample_size"] = -1
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_dados_incompletos_via_oos_float(self) -> None:
        """R12.6: ``out_of_sample_periodo`` como float é tipo divergente."""
        entradas = _entradas_aprovadas()
        entradas["out_of_sample_periodo"] = 60.0  # type: ignore[arg-type]
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_rejeitada_quando_sharpe_baixo(self) -> None:
        """R12.2: ``sharpe_replicado < 0.5`` → ``rejeitada``."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = 0.3
        assert avaliar_paper(**entradas) == "rejeitada"

    def test_rejeitada_quando_sharpe_no_limite_inferior(self) -> None:
        """Sharpe estritamente menor que 0.5 dispara ``rejeitada``."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = LIMITE_SHARPE - 0.0001
        assert avaliar_paper(**entradas) == "rejeitada"

    def test_aprovada_no_limite_de_sharpe(self) -> None:
        """``sharpe == 0.5`` ainda passa (R12.2 usa estritamente menor)."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = LIMITE_SHARPE
        assert avaliar_paper(**entradas) == "aprovada"

    def test_amostra_insuficiente(self) -> None:
        """R12.3: ``sample_size < 250`` → ``amostra-insuficiente``."""
        entradas = _entradas_aprovadas()
        entradas["sample_size"] = 100
        assert avaliar_paper(**entradas) == "amostra-insuficiente"

    def test_aprovada_no_limite_de_sample(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["sample_size"] = MINIMO_SAMPLE_SIZE_DIAS_UTEIS
        assert avaliar_paper(**entradas) == "aprovada"

    def test_out_of_sample_insuficiente(self) -> None:
        """R12.7: ``out_of_sample_periodo < 60`` → ``out-of-sample-insuficiente``."""
        entradas = _entradas_aprovadas()
        entradas["out_of_sample_periodo"] = 30
        assert avaliar_paper(**entradas) == "out-of-sample-insuficiente"

    def test_aprovada_no_limite_de_oos(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["out_of_sample_periodo"] = MINIMO_OUT_OF_SAMPLE_DIAS_UTEIS
        assert avaliar_paper(**entradas) == "aprovada"

    def test_bias_nao_tratado(self) -> None:
        """R12.4: ``survivorship_bias_tratado == False`` → ``bias-nao-tratado``."""
        entradas = _entradas_aprovadas()
        entradas["survivorship_bias_tratado"] = False
        assert avaliar_paper(**entradas) == "bias-nao-tratado"


# ---------------------------------------------------------------------------
# avaliar_paper — precedência R12.1
# ---------------------------------------------------------------------------


class TestPrecedencia:
    def test_precedencia_dados_incompletos_sobre_rejeitada(self) -> None:
        """``None`` em sharpe vence ``sharpe < 0.5``."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = None
        # E também rejeição evidente em outro campo:
        entradas["survivorship_bias_tratado"] = False
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_precedencia_dados_incompletos_sobre_amostra(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["sample_size"] = None  # type: ignore[arg-type]
        entradas["sharpe_replicado"] = 0.2  # rejeitada também aplicaria
        assert avaliar_paper(**entradas) == "dados-incompletos"

    def test_precedencia_rejeitada_sobre_amostra(self) -> None:
        """``rejeitada`` vence ``amostra-insuficiente``."""
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = 0.3
        entradas["sample_size"] = 100
        assert avaliar_paper(**entradas) == "rejeitada"

    def test_precedencia_rejeitada_sobre_oos(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = 0.3
        entradas["out_of_sample_periodo"] = 30
        assert avaliar_paper(**entradas) == "rejeitada"

    def test_precedencia_rejeitada_sobre_bias(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["sharpe_replicado"] = 0.3
        entradas["survivorship_bias_tratado"] = False
        assert avaliar_paper(**entradas) == "rejeitada"

    def test_precedencia_amostra_sobre_oos(self) -> None:
        """``amostra-insuficiente`` vence ``out-of-sample-insuficiente``."""
        entradas = _entradas_aprovadas()
        entradas["sample_size"] = 100
        entradas["out_of_sample_periodo"] = 30
        assert avaliar_paper(**entradas) == "amostra-insuficiente"

    def test_precedencia_amostra_sobre_bias(self) -> None:
        entradas = _entradas_aprovadas()
        entradas["sample_size"] = 100
        entradas["survivorship_bias_tratado"] = False
        assert avaliar_paper(**entradas) == "amostra-insuficiente"

    def test_precedencia_oos_sobre_bias(self) -> None:
        """``out-of-sample-insuficiente`` vence ``bias-nao-tratado``."""
        entradas = _entradas_aprovadas()
        entradas["out_of_sample_periodo"] = 30
        entradas["survivorship_bias_tratado"] = False
        assert avaliar_paper(**entradas) == "out-of-sample-insuficiente"


# ---------------------------------------------------------------------------
# validar_link_de_entrada — R12.8 / Property 8
# ---------------------------------------------------------------------------


class TestValidarLinkDeEntrada:
    @pytest.mark.parametrize(
        "status",
        [
            "rejeitada",
            "amostra-insuficiente",
            "bias-nao-tratado",
            "out-of-sample-insuficiente",
            "dados-incompletos",
        ],
    )
    def test_bloqueia_status_diferente_de_aprovada(self, status: str) -> None:
        """R12.8: para cada status não-aprovado, o guard deve bloquear."""
        nota = construir_nota_paper(
            **_kwargs_construir(
                # Forçamos status especificado bypassando avaliar_paper:
                # construímos com entradas aprovadas e depois substituímos.
                sharpe_replicado=1.5,
                sample_size=500,
                out_of_sample_periodo=120,
                survivorship_bias_tratado=True,
            )
        )
        # Reconstrói a nota com o status alvo (NotaPaper aceita o enum).
        nota_alvo = NotaPaper(
            **{
                **nota.model_dump(),
                "status": status,
                "data_criacao": nota.data_criacao,
            }
        )
        resultado = validar_link_de_entrada(nota_alvo)
        assert isinstance(resultado, ResultadoValidacaoLink)
        assert resultado.autorizado is False
        assert resultado.motivo is not None
        assert status in resultado.motivo
        assert resultado.status_alvo == status

    def test_permite_aprovada(self) -> None:
        """R12.8: status ``aprovada`` libera link de entrada."""
        nota = construir_nota_paper(**_kwargs_construir())
        assert nota.status == "aprovada"
        resultado = validar_link_de_entrada(nota)
        assert resultado.autorizado is True
        assert resultado.motivo is None
        assert resultado.status_alvo == "aprovada"

    def test_permitir_se_aprovada_falso_bloqueia_aprovada(self) -> None:
        """Interruptor defensivo: bloqueia até quando aprovada."""
        nota = construir_nota_paper(**_kwargs_construir())
        resultado = validar_link_de_entrada(nota, permitir_se_aprovada=False)
        assert resultado.autorizado is False


# ---------------------------------------------------------------------------
# armazenar_em_papers — R12.5
# ---------------------------------------------------------------------------


class TestArmazenarEmPapers:
    def test_grava_aprovada(self, tmp_path: Path) -> None:
        nota = construir_nota_paper(
            **_kwargs_construir(
                titulo="Aprovada Volatility",
                corpo_markdown="# Conteúdo da nota\n\nTexto livre.",
            )
        )
        assert nota.status == "aprovada"

        caminho = armazenar_em_papers(nota, tmp_path)

        assert caminho.exists()
        assert caminho.parent == tmp_path / "Papers"
        assert caminho.suffix == ".md"

        post = frontmatter.loads(caminho.read_text(encoding="utf-8"))
        assert post.metadata["status"] == "aprovada"
        assert post.metadata["instrumento_testado"] == "MNQ"
        assert "Texto livre" in post.content

    def test_grava_dados_incompletos(self, tmp_path: Path) -> None:
        """R12.5: status diferente de ``aprovada`` ainda grava."""
        nota = construir_nota_paper(
            **_kwargs_construir(
                titulo="Paper sem amostra",
                sharpe_replicado=None,
            )
        )
        assert nota.status == "dados-incompletos"

        caminho = armazenar_em_papers(nota, tmp_path)
        assert caminho.exists()

        post = frontmatter.loads(caminho.read_text(encoding="utf-8"))
        assert post.metadata["status"] == "dados-incompletos"

    def test_grava_rejeitada(self, tmp_path: Path) -> None:
        nota = construir_nota_paper(
            **_kwargs_construir(
                titulo="Paper rejeitado",
                sharpe_replicado=0.2,
            )
        )
        assert nota.status == "rejeitada"
        caminho = armazenar_em_papers(nota, tmp_path)
        assert caminho.exists()

    def test_levanta_em_raiz_invalida(self, tmp_path: Path) -> None:
        nota = construir_nota_paper(**_kwargs_construir())
        nao_existe = tmp_path / "nao-existe"
        with pytest.raises(ValueError):
            armazenar_em_papers(nota, nao_existe)

    def test_slug_remove_acentos_e_caracteres_especiais(
        self, tmp_path: Path
    ) -> None:
        nota = construir_nota_paper(
            **_kwargs_construir(
                titulo="Análise de Volatilidade — MNQ (2026)!",
            )
        )
        caminho = armazenar_em_papers(nota, tmp_path)
        nome = caminho.name
        # Espera apenas [a-z0-9-] no slug (mais .md).
        assert nome.endswith(".md")
        slug = nome[:-3]
        assert all(
            c.islower() or c.isdigit() or c == "-" for c in slug
        ), nome


# ---------------------------------------------------------------------------
# construir_nota_paper — integração com avaliar_paper
# ---------------------------------------------------------------------------


class TestConstruirNotaPaper:
    def test_aprovada_e_consistente(self) -> None:
        nota = construir_nota_paper(**_kwargs_construir())
        assert isinstance(nota, NotaPaper)
        assert nota.area == "Papers"
        assert nota.status == "aprovada"
        assert nota.instrumento_testado == "MNQ"

    def test_propaga_dados_incompletos_para_status(self) -> None:
        nota = construir_nota_paper(
            **_kwargs_construir(
                survivorship_bias_tratado=None,
            )
        )
        assert nota.status == "dados-incompletos"
        # Mesmo com None na entrada, o NotaPaper deve ser instanciável
        # com bool normalizado.
        assert nota.survivorship_bias_tratado is False

    def test_propaga_rejeitada_para_status(self) -> None:
        nota = construir_nota_paper(
            **_kwargs_construir(sharpe_replicado=0.1)
        )
        assert nota.status == "rejeitada"
        assert nota.sharpe_replicado == pytest.approx(0.1)
