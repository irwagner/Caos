"""Testes unitários para ``caos.profile_loader`` e ``caos.skill_validator``.

Cobre R2.1–R2.6 e R11.7 do ``requirements.md``:

- 9 perfis válidos carregados sem falhas.
- Perfil com modelo divergente do permitido pelo agente.
- Perfil com campo obrigatório faltando.
- Perfil com Skill não declarada no Requirement 11.
- Pasta com arquivo extra (não corresponde a nenhum dos 9).
- Pasta com arquivo esperado faltando.
- Frontmatter ausente no arquivo.
- System prompt vazio (corpo Markdown vazio).

Os 9 perfis reais em ``e:/CAOS/.kiro/agents/`` são copiados para
``tmp_path`` em cada cenário, garantindo que cada teste é determinístico e
isolado do filesystem do desenvolvedor.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

import pytest

from caos.models import AGENTES, AgentProfile
from caos.profile_loader import (
    ARQUIVOS_ESPERADOS,
    FalhaCarregamento,
    ResultadoCarregamentoPerfil,
    ResultadoCarregamentoTodos,
    carregar_perfil,
    carregar_todos,
)
from caos.skill_validator import (
    SKILLS_DO_CATALOGO,
    ResultadoValidacaoSkill,
    registrar_auditoria_bloqueio,
    validar_invocacao,
)


# ---------------------------------------------------------------------------
# Localização dos perfis reais entregues pela Task 3
# ---------------------------------------------------------------------------

# Os perfis reais ficam em ``<workspace_root>/.kiro/agents/``. Subimos a partir
# deste arquivo de testes:
#   tests/unit/test_profile_loader.py -> tests/unit/ -> tests/ -> CAOS_Orchestrator/ -> CAOS/
# ou seja, 4 níveis acima de ``__file__``.
ROOT_WORKSPACE = Path(__file__).resolve().parents[3]
DIR_AGENTES_REAL = ROOT_WORKSPACE / ".kiro" / "agents"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dir_agentes(tmp_path: Path) -> Path:
    """Copia os 9 perfis reais para ``tmp_path/.kiro/agents`` e devolve o caminho.

    Cada teste recebe uma cópia limpa, podendo modificar/remover/adicionar
    arquivos sem afetar os outros testes nem o workspace real.
    """
    if not DIR_AGENTES_REAL.is_dir():
        pytest.skip(
            f"diretório de agentes reais não encontrado: {DIR_AGENTES_REAL}; "
            "rode a Task 3 antes para criar os 9 arquivos."
        )

    destino = tmp_path / ".kiro" / "agents"
    destino.mkdir(parents=True, exist_ok=True)
    for nome in ARQUIVOS_ESPERADOS:
        origem = DIR_AGENTES_REAL / nome
        if not origem.is_file():
            pytest.skip(f"arquivo real ausente: {origem}")
        shutil.copy(origem, destino / nome)
    return destino


def _categorias(falhas: Iterable[FalhaCarregamento]) -> list[str]:
    return [f.categoria for f in falhas]


# ---------------------------------------------------------------------------
# Caso A: 9 perfis válidos
# ---------------------------------------------------------------------------


class TestCarregarTodosPerfilValidos:
    def test_carrega_os_9_perfis_sem_falhas(self, dir_agentes: Path) -> None:
        resultado = carregar_todos(dir_agentes)
        assert isinstance(resultado, ResultadoCarregamentoTodos)
        assert resultado.falhas == [], (
            "esperava-se nenhuma falha, mas houve: "
            f"{[(f.categoria, f.mensagem) for f in resultado.falhas]}"
        )
        assert resultado.sucesso is True
        assert set(resultado.perfis.keys()) == set(AGENTES)
        for nome, perfil in resultado.perfis.items():
            assert isinstance(perfil, AgentProfile)
            assert perfil.nome == nome

    def test_cada_perfil_tem_system_prompt_nao_vazio(
        self, dir_agentes: Path
    ) -> None:
        resultado = carregar_todos(dir_agentes)
        for perfil in resultado.perfis.values():
            assert len(perfil.system_prompt) > 0
            assert len(perfil.system_prompt) <= 8000

    def test_carregar_perfil_individual_retorna_objeto_correto(
        self, dir_agentes: Path
    ) -> None:
        for nome in AGENTES:
            resultado = carregar_perfil(dir_agentes / f"{nome}.md")
            assert isinstance(resultado, ResultadoCarregamentoPerfil)
            assert resultado.sucesso, (
                f"falha ao carregar {nome}.md: "
                f"{resultado.falha.mensagem if resultado.falha else 'sem detalhes'}"
            )
            assert resultado.perfil is not None
            assert resultado.perfil.nome == nome


# ---------------------------------------------------------------------------
# Caso B: modelo divergente do permitido para o agente
# ---------------------------------------------------------------------------


class TestModeloDivergente:
    def test_athena_com_haiku_falha_modelo_divergente(
        self, dir_agentes: Path
    ) -> None:
        # Athena exige claude-opus-4.7; injetamos claude-haiku-4.5.
        arquivo = dir_agentes / "Athena.md"
        conteudo = arquivo.read_text(encoding="utf-8")
        adulterado = conteudo.replace(
            "modelo: claude-opus-4.7",
            "modelo: claude-haiku-4.5",
        )
        assert adulterado != conteudo, (
            "o substituto deveria efetivamente alterar o conteúdo"
        )
        arquivo.write_text(adulterado, encoding="utf-8")

        resultado = carregar_perfil(arquivo)
        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria in (
            "modelo-divergente",
            "validacao-pydantic",
        )

    def test_falha_aparece_no_carregar_todos(self, dir_agentes: Path) -> None:
        arquivo = dir_agentes / "Cerberus.md"
        conteudo = arquivo.read_text(encoding="utf-8")
        # Cerberus exige claude-sonnet-4.5; injetamos claude-haiku-4.5.
        arquivo.write_text(
            conteudo.replace(
                "modelo: claude-sonnet-4.5",
                "modelo: claude-haiku-4.5",
            ),
            encoding="utf-8",
        )

        resultado = carregar_todos(dir_agentes)
        assert resultado.sucesso is False
        assert any(
            f.categoria in ("modelo-divergente", "validacao-pydantic")
            for f in resultado.falhas
        )


# ---------------------------------------------------------------------------
# Caso C: campo obrigatório faltando
# ---------------------------------------------------------------------------


class TestCampoObrigatorioFaltando:
    def test_cerberus_sem_tags_especialidade(self, dir_agentes: Path) -> None:
        arquivo = dir_agentes / "Cerberus.md"
        # Reescrevemos o arquivo removendo completamente o bloco
        # ``tags_especialidade``.
        arquivo.write_text(
            (
                "---\n"
                "nome: Cerberus\n"
                "modelo: claude-sonnet-4.5\n"
                "skills_permitidas:\n"
                "  - Skill_CSV_Reader\n"
                "  - Skill_LLM_Cache\n"
                "  - Skill_Token_Budget\n"
                "escopo_de_decisao:\n"
                "  - veto_de_risco\n"
                "formato_de_saida:\n"
                "  secoes_obrigatorias:\n"
                "    - Proposta\n"
                "    - Justificativa\n"
                "    - Riscos\n"
                "    - Confianca\n"
                "  confianca:\n"
                "    tipo: inteiro\n"
                "    minimo: 0\n"
                "    maximo: 100\n"
                "---\n\n"
                "# Identidade\n\nVocê é Cerberus.\n"
            ),
            encoding="utf-8",
        )

        resultado = carregar_perfil(arquivo)
        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria in (
            "campo-obrigatorio-faltando",
            "validacao-pydantic",
        )
        if resultado.falha.categoria == "campo-obrigatorio-faltando":
            assert "tags_especialidade" in resultado.falha.detalhes.get(
                "campos_faltando", []
            )


# ---------------------------------------------------------------------------
# Caso D: Skill não autorizada (não existente no catálogo)
# ---------------------------------------------------------------------------


class TestSkillNaoAutorizada:
    def test_hermes_com_skill_inexistente(self, dir_agentes: Path) -> None:
        arquivo = dir_agentes / "Hermes.md"
        arquivo.write_text(
            (
                "---\n"
                "nome: Hermes\n"
                "modelo: qwen3-coder\n"
                "tags_especialidade:\n"
                "  - csharp\n"
                "  - ninjascript\n"
                "skills_permitidas:\n"
                "  - Skill_Inexistente\n"
                "escopo_de_decisao:\n"
                "  - veto_tecnico\n"
                "formato_de_saida:\n"
                "  secoes_obrigatorias:\n"
                "    - Proposta\n"
                "    - Justificativa\n"
                "    - Riscos\n"
                "    - Confianca\n"
                "  confianca:\n"
                "    tipo: inteiro\n"
                "    minimo: 0\n"
                "    maximo: 100\n"
                "---\n\n"
                "# Identidade\n\nVocê é Hermes.\n"
            ),
            encoding="utf-8",
        )

        resultado = carregar_perfil(arquivo)
        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria in (
            "skill-nao-autorizada",
            "validacao-pydantic",
        )


# ---------------------------------------------------------------------------
# Caso E: arquivo extra na pasta
# ---------------------------------------------------------------------------


class TestArquivoExtra:
    def test_loki_md_e_sinalizado_como_extra(self, dir_agentes: Path) -> None:
        (dir_agentes / "Loki.md").write_text(
            "---\nnome: Loki\n---\n\n# Loki\n",
            encoding="utf-8",
        )

        resultado = carregar_todos(dir_agentes)
        assert resultado.sucesso is False
        assert "arquivo-extra" in _categorias(resultado.falhas)
        # Os 9 perfis reais ainda devem ter sido carregados com sucesso.
        assert set(resultado.perfis.keys()) == set(AGENTES)


# ---------------------------------------------------------------------------
# Caso F: arquivo faltando no Conselho
# ---------------------------------------------------------------------------


class TestArquivoFaltando:
    def test_athena_md_ausente(self, dir_agentes: Path) -> None:
        (dir_agentes / "Athena.md").unlink()

        resultado = carregar_todos(dir_agentes)
        assert resultado.sucesso is False
        assert "arquivo-faltando-no-conselho" in _categorias(resultado.falhas)
        assert "Athena" not in resultado.perfis


# ---------------------------------------------------------------------------
# Caso G: frontmatter ausente
# ---------------------------------------------------------------------------


class TestFrontmatterAusente:
    def test_arquivo_so_com_prosa(self, dir_agentes: Path) -> None:
        arquivo = dir_agentes / "Athena.md"
        arquivo.write_text(
            "Athena sem frontmatter, só prosa pura.\n",
            encoding="utf-8",
        )

        resultado = carregar_perfil(arquivo)
        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "frontmatter-ausente"


# ---------------------------------------------------------------------------
# Caso H: system prompt vazio
# ---------------------------------------------------------------------------


class TestSystemPromptVazio:
    def test_corpo_markdown_vazio_falha(self, dir_agentes: Path) -> None:
        arquivo = dir_agentes / "Athena.md"
        arquivo.write_text(
            (
                "---\n"
                "nome: Athena\n"
                "modelo: claude-opus-4.7\n"
                "tags_especialidade:\n"
                "  - orquestracao\n"
                "skills_permitidas: []\n"
                "escopo_de_decisao:\n"
                "  - sintese_final\n"
                "formato_de_saida:\n"
                "  secoes_obrigatorias:\n"
                "    - Proposta\n"
                "    - Justificativa\n"
                "    - Riscos\n"
                "    - Confianca\n"
                "  confianca:\n"
                "    tipo: inteiro\n"
                "    minimo: 0\n"
                "    maximo: 100\n"
                "---\n"
                "\n"
                "   \n"
            ),
            encoding="utf-8",
        )

        resultado = carregar_perfil(arquivo)
        assert resultado.sucesso is False
        assert resultado.falha is not None
        # System prompt vazio viola o min_length=1 do Pydantic.
        assert resultado.falha.categoria in (
            "validacao-pydantic",
            "campo-obrigatorio-faltando",
        )


# ---------------------------------------------------------------------------
# Caso adicional: arquivo inexistente
# ---------------------------------------------------------------------------


class TestArquivoInexistente:
    def test_caminho_nao_existe(self, tmp_path: Path) -> None:
        resultado = carregar_perfil(tmp_path / "nao-existe.md")
        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "arquivo-ausente"

    def test_diretorio_nao_existe(self, tmp_path: Path) -> None:
        resultado = carregar_todos(tmp_path / "nao-existe")
        assert resultado.sucesso is False
        assert any(
            f.categoria == "arquivo-ausente" for f in resultado.falhas
        )


# ---------------------------------------------------------------------------
# Skill_Validator
# ---------------------------------------------------------------------------


def _carregar_perfil_real(dir_agentes: Path, nome: str) -> AgentProfile:
    resultado = carregar_perfil(dir_agentes / f"{nome}.md")
    assert resultado.sucesso, (
        f"falha ao carregar {nome}.md: "
        f"{resultado.falha.mensagem if resultado.falha else ''}"
    )
    assert resultado.perfil is not None
    return resultado.perfil


class TestSkillValidator:
    def test_skill_autorizada_passa(self, dir_agentes: Path) -> None:
        hermes = _carregar_perfil_real(dir_agentes, "Hermes")
        # Hermes declara Skill_MSBuild.
        assert "Skill_MSBuild" in hermes.skills_permitidas
        resultado = validar_invocacao(hermes, "Skill_MSBuild")
        assert isinstance(resultado, ResultadoValidacaoSkill)
        assert resultado.autorizada is True
        assert resultado.categoria is None
        assert resultado.motivo is None
        assert resultado.agente == "Hermes"

    def test_skill_no_catalogo_mas_nao_no_perfil(
        self, dir_agentes: Path
    ) -> None:
        cerberus = _carregar_perfil_real(dir_agentes, "Cerberus")
        # Skill_MSBuild existe no catálogo (R11) mas Cerberus NÃO declara.
        assert "Skill_MSBuild" in SKILLS_DO_CATALOGO
        assert "Skill_MSBuild" not in cerberus.skills_permitidas
        resultado = validar_invocacao(cerberus, "Skill_MSBuild")
        assert resultado.autorizada is False
        assert resultado.categoria == "skill-nao-autorizada"
        assert resultado.motivo is not None
        assert "Cerberus" in resultado.motivo
        assert "Skill_MSBuild" in resultado.motivo

    def test_skill_desconhecida(self, dir_agentes: Path) -> None:
        cerberus = _carregar_perfil_real(dir_agentes, "Cerberus")
        assert "Skill_Imaginaria" not in SKILLS_DO_CATALOGO
        resultado = validar_invocacao(cerberus, "Skill_Imaginaria")
        assert resultado.autorizada is False
        assert resultado.categoria == "skill-desconhecida"
        assert resultado.motivo is not None
        assert "Skill_Imaginaria" in resultado.motivo

    def test_registrar_auditoria_bloqueio_estrutura(
        self, dir_agentes: Path
    ) -> None:
        cerberus = _carregar_perfil_real(dir_agentes, "Cerberus")
        registro = registrar_auditoria_bloqueio(
            cerberus,
            "Skill_MSBuild",
            "skill-nao-autorizada",
            parametros_hash="a" * 64,
        )
        assert registro["nome"] == "Skill_MSBuild"
        assert registro["invocador"] == "Cerberus"
        assert registro["modelo"] == "claude-sonnet-4.5"
        assert registro["status"] == "skill-nao-autorizada"
        assert registro["parametros_hash_sha256"] == "a" * 64
        assert registro["exit_code"] is None
        assert registro["duracao_ms"] == 0
        # timestamp deve ser ISO 8601 com tzinfo (sufixo +00:00 ou Z).
        assert "T" in registro["timestamp"]

    def test_registrar_auditoria_bloqueio_skill_desconhecida(
        self, dir_agentes: Path
    ) -> None:
        athena = _carregar_perfil_real(dir_agentes, "Athena")
        registro = registrar_auditoria_bloqueio(
            athena, "Skill_Inventada", "skill-desconhecida"
        )
        assert registro["status"] == "skill-desconhecida"
        assert registro["invocador"] == "Athena"

    @pytest.mark.parametrize(
        "agente, skills_esperadas",
        [
            ("Athena", {"Skill_Terminal", "Skill_Git", "Skill_MSBuild"}),
            ("Cerberus", {"Skill_CSV_Reader"}),
            ("Hermes", {"Skill_MSBuild", "Skill_Terminal"}),
            ("Explorador", {"Skill_Web_Search"}),
        ],
    )
    def test_skills_esperadas_dos_agentes_chave(
        self,
        dir_agentes: Path,
        agente: str,
        skills_esperadas: set[str],
    ) -> None:
        perfil = _carregar_perfil_real(dir_agentes, agente)
        for skill in skills_esperadas:
            resultado = validar_invocacao(perfil, skill)
            assert resultado.autorizada is True, (
                f"esperava-se que {agente} pudesse invocar {skill}, "
                f"mas o resultado foi: {resultado}"
            )
