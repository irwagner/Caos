"""Testes unitários para ``caos.steering_engine``.

Cobre R3.1–R3.6, R7.3, R7.4, R13.4, R17.2 e R17.6 do ``requirements.md``.

Estratégia geral:

- Os 8 arquivos reais entregues por Task 4 ficam em
  ``<workspace_root>/.kiro/steering/``. A fixture ``dir_steering_real``
  aponta diretamente para esse caminho — testes apenas leem.
- Para cenários que exigem manipular o conteúdo (orçamento configurado,
  valor inválido, frontmatter ausente), criamos diretórios temporários em
  ``tmp_path`` e escrevemos arquivos sintéticos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from caos.steering_engine import (
    ARQUIVO_NINJASCRIPT_API,
    ARQUIVO_ORCAMENTO_TOKENS,
    ARQUIVO_ORCAMENTO_TURNOS,
    ORCAMENTO_TOKENS_DEFAULT,
    ORCAMENTO_TURNOS_DEFAULT,
    FalhaSteering,
    ResultadoCarregamentoSteering,
    SteeringEngine,
    carregar_regras,
)


# ---------------------------------------------------------------------------
# Localização dos arquivos reais entregues pela Task 4
# ---------------------------------------------------------------------------

# tests/unit/test_steering_engine.py -> tests/unit/ -> tests/ ->
# CAOS_Orchestrator/ -> CAOS/  (4 níveis acima de __file__)
ROOT_WORKSPACE = Path(__file__).resolve().parents[3]
DIR_STEERING_REAL = ROOT_WORKSPACE / ".kiro" / "steering"

#: Os 8 arquivos esperados conforme Task 4.
ARQUIVOS_ESPERADOS_REAIS: tuple[str, ...] = (
    "idioma-pt-br",
    "instrumento-mnq",
    "ninjascript-api",
    "ninjascript-state-historical-realtime",
    "orcamento-de-tokens",
    "orcamento-de-turnos",
    "plataforma-windows-cmd",
    "reference-hydra-readonly",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dir_steering_real() -> Path:
    """Caminho para o ``.kiro/steering/`` real do workspace.

    Pula o teste se o diretório ainda não existir (Task 4 não rodada).
    """
    if not DIR_STEERING_REAL.is_dir():
        pytest.skip(
            f"diretório de steering real não existe: {DIR_STEERING_REAL}"
        )
    return DIR_STEERING_REAL


@pytest.fixture()
def dir_steering_vazio(tmp_path: Path) -> Path:
    """Diretório de steering vazio em ``tmp_path``."""
    destino = tmp_path / ".kiro" / "steering"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _escrever_regra_minima(
    diretorio: Path,
    nome_arquivo: str,
    *,
    frontmatter_yaml: str,
    corpo: str = "Conteúdo Markdown da regra.\n",
) -> Path:
    """Escreve um arquivo de steering com frontmatter e corpo arbitrários."""
    caminho = diretorio / nome_arquivo
    caminho.write_text(
        f"---\n{frontmatter_yaml}---\n\n{corpo}",
        encoding="utf-8",
    )
    return caminho


# ---------------------------------------------------------------------------
# Carregamento dos 8 arquivos reais (R3.1–R3.5, R13.4)
# ---------------------------------------------------------------------------


class TestCarregaArquivosReais:
    def test_carrega_8_regras_validas(self, dir_steering_real: Path) -> None:
        resultado = carregar_regras(dir_steering_real)

        assert isinstance(resultado, ResultadoCarregamentoSteering)
        assert resultado.falhas == [], (
            "esperava-se nenhuma falha, mas houve: "
            f"{[(f.categoria, f.mensagem) for f in resultado.falhas]}"
        )
        assert resultado.sucesso is True
        assert set(resultado.regras.keys()) == set(ARQUIVOS_ESPERADOS_REAIS)

    def test_engine_carrega_e_expoe_regras(
        self, dir_steering_real: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_real)
        regras = engine.regras_validas()
        assert set(regras.keys()) == set(ARQUIVOS_ESPERADOS_REAIS)
        assert engine.regras_invalidas() == []
        assert engine.warnings() == []


# ---------------------------------------------------------------------------
# Construção da SteeringEngine
# ---------------------------------------------------------------------------


class TestSteeringEngineConstrutor:
    def test_diretorio_inexistente_lanca(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            SteeringEngine(tmp_path / "nao-existe")

    def test_diretorio_vazio_constroi_sem_falhas(
        self, dir_steering_vazio: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.regras_validas() == {}
        assert engine.regras_invalidas() == []


# ---------------------------------------------------------------------------
# R7.3 / R7.4 — get_orcamento_de_turnos
# ---------------------------------------------------------------------------


class TestGetOrcamentoDeTurnos:
    def test_default_em_diretorio_vazio(
        self, dir_steering_vazio: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.get_orcamento_de_turnos() == ORCAMENTO_TURNOS_DEFAULT
        assert engine.warnings() == []

    def test_valor_configurado_no_frontmatter(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_ORCAMENTO_TURNOS}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Configura orçamento de turnos para teste.\n"
                "orcamento: 20\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.get_orcamento_de_turnos() == 20
        assert engine.warnings() == []

    def test_valor_real_do_workspace_e_12(
        self, dir_steering_real: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_real)
        assert engine.get_orcamento_de_turnos() == 12

    @pytest.mark.parametrize(
        "valor_yaml",
        [
            "1",       # abaixo do mínimo
            "200",     # acima do máximo
            "'abc'",   # não é inteiro
            "3.5",     # float fracionário
        ],
    )
    def test_valores_invalidos_voltam_para_default_com_warning(
        self, dir_steering_vazio: Path, valor_yaml: str
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_ORCAMENTO_TURNOS}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Teste de valor inválido para orcamento.\n"
                f"orcamento: {valor_yaml}\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.get_orcamento_de_turnos() == ORCAMENTO_TURNOS_DEFAULT
        warnings_ = engine.warnings()
        assert len(warnings_) >= 1
        assert any("Orcamento_De_Turnos" in w for w in warnings_)

    def test_valor_no_corpo_markdown_quando_frontmatter_omite(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_ORCAMENTO_TURNOS}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Frontmatter sem campo orcamento.\n"
            ),
            corpo=(
                "# Orçamento\n\n"
                "Configuração via corpo Markdown.\n\n"
                "orcamento: 50\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.get_orcamento_de_turnos() == 50


# ---------------------------------------------------------------------------
# R17.2 / R17.6 — get_orcamento_de_tokens
# ---------------------------------------------------------------------------


class TestGetOrcamentoDeTokens:
    def test_default_em_diretorio_vazio(
        self, dir_steering_vazio: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_vazio)
        assert (
            engine.get_orcamento_de_tokens("Athena")
            == ORCAMENTO_TOKENS_DEFAULT
        )
        assert engine.warnings() == []

    def test_default_para_agente_nao_listado(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_ORCAMENTO_TOKENS}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Apenas Athena listada para teste.\n"
                "orcamentos:\n"
                "  Athena: 1500000\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        # Agente listado retorna o configurado.
        assert engine.get_orcamento_de_tokens("Athena") == 1_500_000
        # Agente não listado retorna o default sem warning.
        assert (
            engine.get_orcamento_de_tokens("Cerberus")
            == ORCAMENTO_TOKENS_DEFAULT
        )
        assert engine.warnings() == []

    def test_valor_real_do_workspace(self, dir_steering_real: Path) -> None:
        engine = SteeringEngine(dir_steering_real)
        # Conforme Task 4: Athena=1.500.000, Cerberus=800.000.
        assert engine.get_orcamento_de_tokens("Athena") == 1_500_000
        assert engine.get_orcamento_de_tokens("Cerberus") == 800_000
        # Se algum agente não estiver listado, recebe default 1.000.000;
        # mas como configuramos os 9, todos devem estar presentes.
        assert (
            engine.get_orcamento_de_tokens("Devils_Advocate") == 500_000
        )

    @pytest.mark.parametrize(
        "valor_yaml",
        [
            "9999",     # abaixo do mínimo de 10.000
            "0",        # zero
            "'xpto'",   # não-inteiro
            "5.5",      # float fracionário
        ],
    )
    def test_valor_invalido_volta_para_default_com_warning(
        self, dir_steering_vazio: Path, valor_yaml: str
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_ORCAMENTO_TOKENS}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Teste de valor inválido por agente.\n"
                "orcamentos:\n"
                f"  Athena: {valor_yaml}\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        assert (
            engine.get_orcamento_de_tokens("Athena")
            == ORCAMENTO_TOKENS_DEFAULT
        )
        warnings_ = engine.warnings()
        assert len(warnings_) >= 1
        assert any("orcamento_diario_tokens" in w for w in warnings_)
        assert any("Athena" in w for w in warnings_)


# ---------------------------------------------------------------------------
# R6.3 — get_ninjascript_apis_autorizadas
# ---------------------------------------------------------------------------


class TestGetNinjascriptApisAutorizadas:
    def test_lista_real_tem_pelo_menos_20_apis(
        self, dir_steering_real: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_real)
        apis = engine.get_ninjascript_apis_autorizadas()
        assert isinstance(apis, list)
        assert len(apis) >= 20, (
            f"esperava ≥20 APIs autorizadas; retornou {len(apis)}: {apis}"
        )
        # Itens mínimos exigidos pela Task 4.
        for esperado in (
            "Strategy",
            "Indicator",
            "OnBarUpdate",
            "OnStateChange",
            "State",
            "State.Historical",
            "State.Realtime",
            "BarsArray",
            "Bars",
            "Close",
            "Open",
            "High",
            "Low",
            "Volume",
            "Time",
            "Position",
            "EnterLong",
            "EnterShort",
            "ExitLong",
            "ExitShort",
            "SetStopLoss",
            "SetProfitTarget",
            "Print",
        ):
            assert esperado in apis, (
                f"API esperada {esperado!r} ausente da whitelist real; "
                f"lista: {apis}"
            )

    def test_lista_vazia_quando_arquivo_ausente(
        self, dir_steering_vazio: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.get_ninjascript_apis_autorizadas() == []

    def test_lista_e_extraida_do_corpo_markdown(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_NINJASCRIPT_API}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Whitelist mínima para teste isolado.\n"
            ),
            corpo=(
                "# APIs\n\n"
                "## APIs Autorizadas\n\n"
                "- Strategy\n"
                "- Indicator\n"
                "- OnBarUpdate\n"
                "\n"
                "Outro parágrafo que não é item de lista.\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        apis = engine.get_ninjascript_apis_autorizadas()
        assert apis == ["Strategy", "Indicator", "OnBarUpdate"]


# ---------------------------------------------------------------------------
# R3.6 — Falhas de validação por categoria
# ---------------------------------------------------------------------------


def _categorias(falhas: list[FalhaSteering]) -> list[str]:
    return [f.categoria for f in falhas]


class TestFalhaDataFormatoInvalido:
    def test_data_em_formato_brasileiro_e_rejeitada(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-com-data-ruim.md",
            frontmatter_yaml=(
                "data: 14/05/2026\n"
                "autor: Athena\n"
                "justificativa: Data em formato pt-BR para teste.\n"
            ),
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        cats = _categorias(resultado.falhas)
        assert (
            "data-formato-invalido" in cats
            or "validacao-pydantic" in cats
        )


class TestFalhaAutorComAcento:
    def test_autor_usuario_com_acento_e_rejeitado(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-autor-acentuado.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: usuário\n"
                "justificativa: Autor com acento para teste de rejeição.\n"
            ),
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        cats = _categorias(resultado.falhas)
        assert (
            "autor-invalido" in cats
            or "validacao-pydantic" in cats
        )

    def test_autor_fora_do_enum_e_rejeitado(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-autor-invalido.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Loki\n"
                "justificativa: Autor fora do conjunto permitido.\n"
            ),
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        cats = _categorias(resultado.falhas)
        assert (
            "autor-invalido" in cats
            or "validacao-pydantic" in cats
        )


class TestFalhaJustificativaVazia:
    def test_justificativa_vazia_e_rejeitada(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-sem-justificativa.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                'justificativa: ""\n'
            ),
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        cats = _categorias(resultado.falhas)
        assert (
            "justificativa-vazia" in cats
            or "validacao-pydantic" in cats
            or "campo-obrigatorio-faltando" in cats
        )

    def test_justificativa_curta_e_rejeitada(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-justificativa-curta.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: curta\n"  # < 10 caracteres
            ),
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        cats = _categorias(resultado.falhas)
        assert (
            "justificativa-vazia" in cats
            or "validacao-pydantic" in cats
        )


class TestFalhaFrontmatterAusente:
    def test_arquivo_so_com_prosa_sem_marcadores(
        self, dir_steering_vazio: Path
    ) -> None:
        caminho = dir_steering_vazio / "regra-sem-frontmatter.md"
        caminho.write_text(
            "Apenas prosa solta, sem bloco YAML delimitado.\n",
            encoding="utf-8",
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        assert "frontmatter-ausente" in _categorias(resultado.falhas)


class TestFalhaCampoFaltando:
    def test_sem_campo_data(self, dir_steering_vazio: Path) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-sem-data.md",
            frontmatter_yaml=(
                "autor: Athena\n"
                "justificativa: Falta campo obrigatório data.\n"
            ),
        )
        resultado = carregar_regras(dir_steering_vazio)
        assert resultado.sucesso is False
        cats = _categorias(resultado.falhas)
        assert (
            "campo-obrigatorio-faltando" in cats
            or "validacao-pydantic" in cats
        )


# ---------------------------------------------------------------------------
# Recarregar
# ---------------------------------------------------------------------------


class TestRecarregar:
    def test_recarregar_pega_novo_arquivo(
        self, dir_steering_vazio: Path
    ) -> None:
        engine = SteeringEngine(dir_steering_vazio)
        assert engine.regras_validas() == {}

        _escrever_regra_minima(
            dir_steering_vazio,
            "regra-nova.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Regra adicionada após construção da engine.\n"
            ),
        )
        engine.recarregar()
        assert "regra-nova" in engine.regras_validas()

    def test_recarregar_zera_warnings(
        self, dir_steering_vazio: Path
    ) -> None:
        _escrever_regra_minima(
            dir_steering_vazio,
            f"{ARQUIVO_ORCAMENTO_TURNOS}.md",
            frontmatter_yaml=(
                "data: 2026-05-14\n"
                "autor: Athena\n"
                "justificativa: Regra com valor inválido para gerar warning.\n"
                "orcamento: 1\n"
            ),
        )
        engine = SteeringEngine(dir_steering_vazio)
        # Disparar warning.
        engine.get_orcamento_de_turnos()
        assert engine.warnings() != []
        engine.recarregar()
        assert engine.warnings() == []
