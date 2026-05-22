"""Testes unitários do :mod:`caos.failure_handler`.

Cobre R5.6 e R14.1–R14.5 do ``requirements.md`` exercitando:

- registro de falhas de Skill: exit_code != 0, timeout, truncagem de
  ``stderr`` a 4096 caracteres (R14.1, R14.2);
- retries de modelo com backoff ≥2s (R14.3): sucesso na primeira
  tentativa, sucesso após 2 falhas, falha após 3 tentativas (timeout,
  resposta-vazia, transporte) e contagem de chamadas a ``time.sleep``;
- contagem de agentes indisponíveis e a regra estritamente "mais que 2"
  para disparar o abort (R14.4);
- gravação efetiva via Council_Recorder com tmp_path + repo Git
  inicializado, conferindo ``status='abortado-por-indisponibilidade'``
  no arquivo final (R14.5).

Os testes usam o mesmo padrão da Task 10 para inicializar um repo Git
em ``tmp_path`` e ``pytest.skip`` quando ``git`` não está no PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
import yaml

from caos.council_recorder import CouncilRecorder
from caos.failure_handler import (
    BACKOFF_MINIMO_S,
    LIMIAR_AGENTES_INDISPONIVEIS_PADRAO,
    LIMITE_STDERR_CHARS,
    FailureHandler,
    RegistroFalhaSkill,
    ResultadoChamadaModelo,
    StatusAgenteIndisponivel,
    chamar_modelo_com_retries,
    registrar_falha_skill,
)
from caos.models import (
    Debate,
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_disponivel() -> bool:
    return shutil.which("git") is not None


requires_git = pytest.mark.skipif(
    not _git_disponivel(), reason="git não disponível no PATH"
)


def _inicializar_repo(repo: Path) -> None:
    """Cria um repo Git mínimo + um commit inicial vazio."""
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
    seed = repo / "README.md"
    seed.write_text("# repo de teste\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "README.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )


def _debate_minimo() -> Debate:
    return Debate(
        identificador="2026-05-14-09",
        titulo="abort-por-indisponibilidade",
        data_inicio=datetime(2026, 5, 14, 14, 0, 0, tzinfo=timezone.utc),
        data_fim=datetime(2026, 5, 14, 14, 18, 0, tzinfo=timezone.utc),
        agentes_participantes=["Athena", "Cerberus", "Manolo"],
        modelos={
            "Athena": "claude-opus-4.7",
            "Cerberus": "claude-sonnet-4.5",
            "Manolo": "claude-haiku-4.5",
        },
        contexto_hash_sha256="b" * 64,
        notas_injetadas=["Modulo_Risco/Trailing_Tres_Fases.md"],
        seeds={"Athena": 42},
        orcamento_de_turnos=12,
        turnos_consumidos=4,
        fase_final="ABORTADO_POR_INDISPONIBILIDADE",
        status="abortado-por-indisponibilidade",
        turnos=[],
    )


def _decisao_parcial() -> DecisaoDoConselho:
    return DecisaoDoConselho(
        identificador="2026-05-14-09",
        debate_relacionado="2026-05-14-09-abort-por-indisponibilidade.md",
        agentes_participantes=["Athena", "Cerberus", "Manolo"],
        propostas=[
            Proposta(
                id="P1",
                autor="Manolo",
                resumo="Trailing 3 fases",
                conteudo="Detalhes",
                confianca=70,
            ),
        ],
        vetos=[],
        decisao_final=DecisaoFinal(
            proposta_aceita=None,
            rationale="Decisão parcial antes do abort.",
        ),
        links_zettel=["[[Trailing_Tres_Fases]]"],
        aprovado_walk_forward=False,
        reproduzivel="parcial",
        regressao_detectada=False,
        status="em-andamento",
    )


def _ler_frontmatter(caminho: Path) -> dict[str, Any]:
    texto = caminho.read_text(encoding="utf-8")
    assert texto.startswith("---\n"), "frontmatter ausente"
    fim = texto.index("\n---\n", 4)
    return yaml.safe_load(texto[4:fim])


# ---------------------------------------------------------------------------
# registrar_falha_skill — R14.1, R14.2
# ---------------------------------------------------------------------------


class TestRegistrarFalhaSkill:
    """Cobre R14.1 e R14.2: registro estruturado de falhas de Skill."""

    def test_registrar_falha_skill_exit_code(self) -> None:
        reg = registrar_falha_skill(
            "Skill_Terminal",
            exit_code=2,
            stderr="erro de execução",
            duracao_ms=120,
            motivo="exit-code-nao-zero",
        )
        assert isinstance(reg, RegistroFalhaSkill)
        assert reg.nome_skill == "Skill_Terminal"
        assert reg.exit_code == 2
        assert reg.motivo == "exit-code-nao-zero"
        assert reg.stderr_truncado == "erro de execução"
        assert reg.duracao_ms == 120

    def test_registrar_falha_skill_timeout(self) -> None:
        reg = registrar_falha_skill(
            "Skill_MSBuild",
            exit_code=-1,
            stderr="",
            duracao_ms=600_000,
            motivo="timeout",
        )
        assert reg.motivo == "timeout"
        assert reg.exit_code == -1
        assert reg.stderr_truncado == ""
        assert reg.duracao_ms == 600_000

    def test_registrar_falha_skill_trunca_stderr_a_4096(self) -> None:
        """``stderr`` maior que 4096 caracteres é truncado preservando início."""
        bruto = "x" * 5000
        reg = registrar_falha_skill(
            "Skill_Git",
            exit_code=128,
            stderr=bruto,
            duracao_ms=50,
            motivo="exit-code-nao-zero",
        )
        assert len(reg.stderr_truncado) == LIMITE_STDERR_CHARS
        assert reg.stderr_truncado == "x" * LIMITE_STDERR_CHARS

    def test_registrar_falha_skill_stderr_no_limite_nao_trunca(self) -> None:
        """``stderr`` exatamente no limite mantém todos os caracteres."""
        bruto = "y" * LIMITE_STDERR_CHARS
        reg = registrar_falha_skill(
            "Skill_Git",
            exit_code=1,
            stderr=bruto,
            duracao_ms=10,
            motivo="exit-code-nao-zero",
        )
        assert len(reg.stderr_truncado) == LIMITE_STDERR_CHARS

    def test_registrar_falha_skill_motivo_invalido_lanca(self) -> None:
        with pytest.raises(ValueError):
            registrar_falha_skill(
                "Skill_Terminal",
                exit_code=1,
                stderr="x",
                duracao_ms=10,
                motivo="abacaxi",  # type: ignore[arg-type]
            )

    def test_registrar_falha_skill_nome_vazio_lanca(self) -> None:
        with pytest.raises(ValueError):
            registrar_falha_skill(
                "",
                exit_code=1,
                stderr="",
                duracao_ms=0,
                motivo="exit-code-nao-zero",
            )

    def test_registrar_falha_skill_imutavel(self) -> None:
        """A dataclass é frozen — tentar mutar levanta erro."""
        reg = registrar_falha_skill(
            "Skill_Terminal",
            exit_code=1,
            stderr="x",
            duracao_ms=10,
            motivo="exit-code-nao-zero",
        )
        with pytest.raises((AttributeError, TypeError)):
            reg.exit_code = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# chamar_modelo_com_retries — R14.3
# ---------------------------------------------------------------------------


class TestChamarModeloComRetries:
    """Cobre R14.3: 3 tentativas com backoff mínimo de 2s."""

    def test_chamar_modelo_sucesso_primeira_tentativa(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chamadas_sleep: list[float] = []
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep",
            lambda s: chamadas_sleep.append(s),
        )
        chamadas_modelo: list[int] = []

        def callable_modelo() -> str:
            chamadas_modelo.append(1)
            return "resposta válida"

        res = chamar_modelo_com_retries(callable_modelo)
        assert isinstance(res, ResultadoChamadaModelo)
        assert res.sucesso is True
        assert res.resposta == "resposta válida"
        assert res.falha is None
        assert res.tentativa == 1
        assert len(chamadas_modelo) == 1
        # Não dorme entre tentativas porque a primeira já passou.
        assert chamadas_sleep == []

    def test_chamar_modelo_sucesso_apos_2_falhas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chamadas_sleep: list[float] = []
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep",
            lambda s: chamadas_sleep.append(s),
        )
        respostas = iter(["", None, "ok"])

        def callable_modelo() -> Optional[str]:
            return next(respostas)

        res = chamar_modelo_com_retries(callable_modelo)
        assert res.sucesso is True
        assert res.resposta == "ok"
        assert res.tentativa == 3
        assert res.falha is None
        # Dois sleeps: entre 1→2 e entre 2→3.
        assert len(chamadas_sleep) == 2

    def test_chamar_modelo_falha_apos_3_tentativas_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chamadas_sleep: list[float] = []
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep",
            lambda s: chamadas_sleep.append(s),
        )

        def callable_modelo() -> str:
            raise TimeoutError("modelo travou")

        res = chamar_modelo_com_retries(callable_modelo)
        assert res.sucesso is False
        assert res.resposta is None
        assert res.falha == "timeout"
        assert res.tentativa == 3
        # Sleeps após tentativa 1 e 2; nenhum após a 3.
        assert len(chamadas_sleep) == 2

    def test_chamar_modelo_falha_resposta_vazia_pula_para_proxima_tentativa(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep", lambda s: None
        )
        respostas = iter(["", "  ", None])

        def callable_modelo() -> Optional[str]:
            return next(respostas)

        res = chamar_modelo_com_retries(callable_modelo)
        assert res.sucesso is False
        assert res.falha == "resposta-vazia"
        assert res.tentativa == 3

    def test_chamar_modelo_excecao_transporte(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep", lambda s: None
        )

        def callable_modelo() -> str:
            raise ConnectionError("DNS falhou")

        res = chamar_modelo_com_retries(callable_modelo)
        assert res.sucesso is False
        assert res.falha == "transporte"
        assert res.tentativa == 3

    def test_chamar_modelo_backoff_minimo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica que entre tentativas o backoff aplicado é ≥ 2s (R14.3)."""
        chamadas_sleep: list[float] = []
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep",
            lambda s: chamadas_sleep.append(s),
        )

        def callable_modelo() -> str:
            raise RuntimeError("boom")

        chamar_modelo_com_retries(callable_modelo)
        assert len(chamadas_sleep) == 2
        for valor in chamadas_sleep:
            assert valor >= BACKOFF_MINIMO_S
            assert valor >= 2.0

    def test_chamar_modelo_eleva_backoff_abaixo_do_minimo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``backoff_min_s`` abaixo de 2s é elevado ao mínimo de 2s."""
        chamadas_sleep: list[float] = []
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep",
            lambda s: chamadas_sleep.append(s),
        )

        def callable_modelo() -> str:
            raise RuntimeError("boom")

        chamar_modelo_com_retries(callable_modelo, backoff_min_s=0.1)
        assert all(v >= 2.0 for v in chamadas_sleep)

    def test_chamar_modelo_max_tentativas_invalido_lanca(self) -> None:
        with pytest.raises(ValueError):
            chamar_modelo_com_retries(lambda: "x", max_tentativas=0)

    def test_chamar_modelo_timeout_zero_lanca(self) -> None:
        with pytest.raises(ValueError):
            chamar_modelo_com_retries(
                lambda: "x", timeout_s_por_tentativa=0
            )

    def test_chamar_modelo_max_tentativas_customizado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chamadas: list[int] = []
        monkeypatch.setattr(
            "caos.failure_handler.time.sleep", lambda s: None
        )

        def callable_modelo() -> str:
            chamadas.append(1)
            raise TimeoutError("timeout")

        res = chamar_modelo_com_retries(callable_modelo, max_tentativas=5)
        assert res.tentativa == 5
        assert len(chamadas) == 5


# ---------------------------------------------------------------------------
# FailureHandler — R14.4
# ---------------------------------------------------------------------------


class TestFailureHandlerAgentesIndisponiveis:
    """Cobre R14.4: contagem e regra estritamente 'mais que 2'."""

    def test_marcar_agente_indisponivel(self) -> None:
        h = FailureHandler()
        h.marcar_agente_indisponivel(
            "Cerberus", "timeout no modelo", turno=3
        )
        lista = h.agentes_indisponiveis()
        assert len(lista) == 1
        assert lista[0] == StatusAgenteIndisponivel(
            agente="Cerberus", motivo="timeout no modelo", turno=3
        )

    def test_marcar_agente_invalido_lanca(self) -> None:
        h = FailureHandler()
        with pytest.raises(ValueError):
            h.marcar_agente_indisponivel("", "x", 1)
        with pytest.raises(ValueError):
            h.marcar_agente_indisponivel("Cerberus", "", 1)
        with pytest.raises(ValueError):
            h.marcar_agente_indisponivel("Cerberus", "x", 0)

    def test_agentes_indisponiveis_retorna_copia(self) -> None:
        """A lista interna não pode ser mutada via referência externa."""
        h = FailureHandler()
        h.marcar_agente_indisponivel("Cerberus", "x", 1)
        lista = h.agentes_indisponiveis()
        lista.clear()
        assert len(h.agentes_indisponiveis()) == 1

    def test_deve_abortar_quando_passa_limiar(self) -> None:
        """3 agentes indisponíveis com limiar=2 → True (R14.4)."""
        h = FailureHandler(limiar_agentes_indisponiveis=2)
        h.marcar_agente_indisponivel("Cerberus", "x", 1)
        h.marcar_agente_indisponivel("Hermes", "y", 2)
        assert h.deve_abortar() is False  # 2 == 2, não passa
        h.marcar_agente_indisponivel("Manolo", "z", 3)
        assert h.deve_abortar() is True  # 3 > 2, dispara

    def test_deve_abortar_quando_no_limite_inferior(self) -> None:
        """2 agentes com limiar=2 → False (R14.4 exige estritamente >2)."""
        h = FailureHandler(limiar_agentes_indisponiveis=2)
        h.marcar_agente_indisponivel("Cerberus", "x", 1)
        h.marcar_agente_indisponivel("Hermes", "y", 2)
        assert h.deve_abortar() is False

    def test_deve_abortar_zero_agentes(self) -> None:
        h = FailureHandler()
        assert h.deve_abortar() is False

    def test_construtor_default_limiar(self) -> None:
        h = FailureHandler()
        assert h.limiar == LIMIAR_AGENTES_INDISPONIVEIS_PADRAO
        assert h.council_recorder is None

    def test_construtor_limiar_negativo_lanca(self) -> None:
        with pytest.raises(ValueError):
            FailureHandler(limiar_agentes_indisponiveis=-1)


# ---------------------------------------------------------------------------
# FailureHandler.abortar_debate — R14.4 + R14.5
# ---------------------------------------------------------------------------


class TestAbortarDebate:
    """Cobre R14.4 e R14.5 com Council_Recorder real."""

    @requires_git
    def test_abortar_debate_chama_recorder_e_grava(
        self, tmp_path: Path
    ) -> None:
        """Caminho feliz: arquivos no disco com status atualizado."""
        _inicializar_repo(tmp_path)
        recorder = CouncilRecorder(raiz_workspace=tmp_path)
        h = FailureHandler(
            council_recorder=recorder, limiar_agentes_indisponiveis=2
        )
        h.marcar_agente_indisponivel("Cerberus", "timeout", 1)
        h.marcar_agente_indisponivel("Hermes", "timeout", 2)
        h.marcar_agente_indisponivel("Odin", "transporte", 3)
        assert h.deve_abortar() is True

        debate = _debate_minimo()
        decisao = _decisao_parcial()

        resultado = h.abortar_debate(debate, decisao, turno_abortagem=4)
        assert resultado.sucesso, f"falha inesperada: {resultado.falha}"
        assert resultado.commit_realizado is True

        # Arquivos em disco.
        assert resultado.caminho_debate.is_file()
        assert resultado.caminho_decisao.is_file()

        # Frontmatter da decisão tem status atualizado.
        fm_decisao = _ler_frontmatter(resultado.caminho_decisao)
        assert fm_decisao["status"] == "abortado-por-indisponibilidade"

        # Rationale carrega lista de agentes e número do turno.
        rationale = fm_decisao["decisao_final"]["rationale"]
        assert "Aborto por indisponibilidade" in rationale
        assert "Cerberus" in rationale
        assert "Hermes" in rationale
        assert "Odin" in rationale
        assert "turno_abortagem=4" in rationale

        # Decisão original preservada (o objeto não foi mutado).
        assert decisao.status == "em-andamento"
        assert "Aborto por indisponibilidade" not in (
            decisao.decisao_final.rationale
        )

    @requires_git
    def test_abortar_debate_inclui_agentes_em_ordem_alfabetica(
        self, tmp_path: Path
    ) -> None:
        _inicializar_repo(tmp_path)
        recorder = CouncilRecorder(raiz_workspace=tmp_path)
        h = FailureHandler(council_recorder=recorder)
        # Marca em ordem fora de alfabeto.
        h.marcar_agente_indisponivel("Manolo", "x", 1)
        h.marcar_agente_indisponivel("Athena", "y", 2)
        h.marcar_agente_indisponivel("Cerberus", "z", 3)

        resultado = h.abortar_debate(
            _debate_minimo(), _decisao_parcial(), turno_abortagem=5
        )
        assert resultado.sucesso

        rationale = _ler_frontmatter(resultado.caminho_decisao)[
            "decisao_final"
        ]["rationale"]
        # A lista deve aparecer em ordem alfabética determinística.
        idx_athena = rationale.index("Athena")
        idx_cerberus = rationale.index("Cerberus")
        idx_manolo = rationale.index("Manolo")
        assert idx_athena < idx_cerberus < idx_manolo

    def test_abortar_debate_sem_recorder_lanca(self) -> None:
        h = FailureHandler(council_recorder=None)
        h.marcar_agente_indisponivel("Cerberus", "x", 1)
        with pytest.raises(RuntimeError):
            h.abortar_debate(
                _debate_minimo(), _decisao_parcial(), turno_abortagem=2
            )

    def test_abortar_debate_turno_invalido_lanca(self) -> None:
        h = FailureHandler(council_recorder=None)
        with pytest.raises(ValueError):
            h.abortar_debate(
                _debate_minimo(), _decisao_parcial(), turno_abortagem=0
            )
