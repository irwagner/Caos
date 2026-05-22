"""Testes unitários do :class:`caos.skills.token_budget.SkillTokenBudget`.

Cobre R11.9 e R17.1, R17.3–R17.6.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import pytest

from caos.skills.token_budget import (
    DIRETORIO_BUDGET_PADRAO,
    ResultadoVerificacaoBudget,
    SkillTokenBudget,
)
from caos.steering_engine import (
    ORCAMENTO_TOKENS_DEFAULT,
    SteeringEngine,
)


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


class _SteeringEngineFake:
    """Implementação mínima compatível com :class:`SteeringEngine` para teste.

    Reproduz apenas o método consumido por :class:`SkillTokenBudget`
    (``get_orcamento_de_tokens``). Evita ter que materializar arquivos
    de regra de Steering em cada teste.
    """

    def __init__(self, orcamentos: dict[str, int]) -> None:
        self._orcamentos = dict(orcamentos)

    def get_orcamento_de_tokens(self, agente: str) -> int:
        return self._orcamentos.get(agente, ORCAMENTO_TOKENS_DEFAULT)


def _escrever_regras_steering(
    diretorio: Path,
    *,
    orcamentos: dict[str, int],
) -> Path:
    """Escreve uma regra ``orcamento-de-tokens.md`` em ``diretorio``.

    Útil para testar a integração real com :class:`SteeringEngine`.
    """
    diretorio.mkdir(parents=True, exist_ok=True)
    yaml = "data: 2026-05-14\nautor: Athena\n"
    yaml += (
        "justificativa: Configuração de orçamentos para teste.\n"
    )
    yaml += "orcamentos:\n"
    for agente, valor in orcamentos.items():
        yaml += f"  {agente}: {valor}\n"
    arquivo = diretorio / "orcamento-de-tokens.md"
    arquivo.write_text(
        f"---\n{yaml}---\n\nCorpo arbitrário.\n",
        encoding="utf-8",
    )
    return arquivo


# ---------------------------------------------------------------------------
# Construtor / propriedades
# ---------------------------------------------------------------------------


class TestConstrutor:
    def test_cria_diretorio_se_ausente(self, tmp_path: Path) -> None:
        destino = tmp_path / "subpasta" / ".budget"
        assert not destino.exists()
        skill = SkillTokenBudget(diretorio_budget=destino)
        assert destino.is_dir()
        assert skill.diretorio_budget == destino

    def test_diretorio_budget_padrao_constante(self) -> None:
        # Garante que a constante existe e tem o layout esperado.
        assert DIRETORIO_BUDGET_PADRAO == Path(
            "CAOS_Orchestrator/.budget"
        )

    def test_invocador_default_none(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        assert skill.invocador is None

    def test_invocador_e_propagado(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            invocador="Athena",
        )
        assert skill.invocador == "Athena"


# ---------------------------------------------------------------------------
# obter_estado
# ---------------------------------------------------------------------------


class TestObterEstado:
    def test_obter_estado_inicial_zero(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        estado = skill.obter_estado("Athena", dia=date(2026, 5, 14))
        assert estado.agente == "Athena"
        assert estado.tokens_input_consumidos == 0
        assert estado.tokens_output_consumidos == 0
        assert estado.tokens_total_consumidos == 0
        assert estado.orcamento_diario_tokens == ORCAMENTO_TOKENS_DEFAULT

    def test_estado_separa_agentes(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        skill.registrar_consumo(
            "Athena",
            tokens_input=100,
            tokens_output=50,
            dia=date(2026, 5, 14),
        )
        estado_athena = skill.obter_estado("Athena", dia=date(2026, 5, 14))
        estado_cerberus = skill.obter_estado(
            "Cerberus", dia=date(2026, 5, 14)
        )
        assert estado_athena.tokens_total_consumidos == 150
        assert estado_cerberus.tokens_total_consumidos == 0


# ---------------------------------------------------------------------------
# registrar_consumo (R17.5)
# ---------------------------------------------------------------------------


class TestRegistrarConsumo:
    def test_registrar_consumo_atualiza_total(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        estado = skill.registrar_consumo(
            "Athena",
            tokens_input=100,
            tokens_output=200,
            dia=date(2026, 5, 14),
        )
        assert estado.tokens_input_consumidos == 100
        assert estado.tokens_output_consumidos == 200
        assert estado.tokens_total_consumidos == 300

    def test_consumos_acumulam_no_mesmo_dia(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        skill.registrar_consumo(
            "Athena",
            tokens_input=100,
            tokens_output=200,
            dia=date(2026, 5, 14),
        )
        estado = skill.registrar_consumo(
            "Athena",
            tokens_input=10,
            tokens_output=20,
            dia=date(2026, 5, 14),
        )
        assert estado.tokens_input_consumidos == 110
        assert estado.tokens_output_consumidos == 220
        assert estado.tokens_total_consumidos == 330

    def test_consumos_separam_por_dia(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        skill.registrar_consumo(
            "Athena",
            tokens_input=100,
            tokens_output=0,
            dia=date(2026, 5, 14),
        )
        skill.registrar_consumo(
            "Athena",
            tokens_input=200,
            tokens_output=0,
            dia=date(2026, 5, 15),
        )
        estado_d1 = skill.obter_estado("Athena", dia=date(2026, 5, 14))
        estado_d2 = skill.obter_estado("Athena", dia=date(2026, 5, 15))
        assert estado_d1.tokens_total_consumidos == 100
        assert estado_d2.tokens_total_consumidos == 200

    def test_recusa_inputs_negativos(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        with pytest.raises(ValueError, match="tokens_input"):
            skill.registrar_consumo(
                "Athena",
                tokens_input=-1,
                tokens_output=0,
            )
        with pytest.raises(ValueError, match="tokens_output"):
            skill.registrar_consumo(
                "Athena",
                tokens_input=0,
                tokens_output=-5,
            )

    def test_consumo_total_dia_lista_apenas_agentes_que_consumiram(
        self, tmp_path: Path
    ) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        dia = date(2026, 5, 14)
        skill.registrar_consumo("Athena", tokens_input=1, tokens_output=2, dia=dia)
        skill.registrar_consumo(
            "Cerberus", tokens_input=10, tokens_output=20, dia=dia
        )
        mapa = skill.consumo_total_dia(dia)
        assert mapa == {"Athena": 3, "Cerberus": 30}


# ---------------------------------------------------------------------------
# verificar (R17.3)
# ---------------------------------------------------------------------------


class TestVerificar:
    def test_verificar_nao_bloqueia_quando_cabe(
        self, tmp_path: Path
    ) -> None:
        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            steering_engine=_SteeringEngineFake({"Athena": 1_000_000}),
        )
        resultado = skill.verificar(
            "Athena",
            tokens_estimados=500,
            dia=date(2026, 5, 14),
        )
        assert isinstance(resultado, ResultadoVerificacaoBudget)
        assert resultado.bloqueado is False
        assert resultado.tokens_consumidos == 0
        assert resultado.tokens_estimados == 500
        assert resultado.orcamento_diario == 1_000_000
        assert resultado.saldo_restante == 1_000_000

    def test_verificar_bloqueia_quando_estouraria(
        self, tmp_path: Path
    ) -> None:
        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            steering_engine=_SteeringEngineFake({"Athena": 100_000}),
        )
        skill.registrar_consumo(
            "Athena",
            tokens_input=80_000,
            tokens_output=10_000,
            dia=date(2026, 5, 14),
        )
        # 90.000 já consumidos + 20.000 estimados = 110.000 > 100.000
        resultado = skill.verificar(
            "Athena",
            tokens_estimados=20_000,
            dia=date(2026, 5, 14),
        )
        assert resultado.bloqueado is True
        assert resultado.tokens_consumidos == 90_000

    def test_verificar_no_limite_exato_nao_bloqueia(
        self, tmp_path: Path
    ) -> None:
        """``> orcamento`` é estouro; ``== orcamento`` é OK (R17.3)."""
        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            steering_engine=_SteeringEngineFake({"Athena": 100_000}),
        )
        resultado = skill.verificar(
            "Athena",
            tokens_estimados=100_000,
            dia=date(2026, 5, 14),
        )
        assert resultado.bloqueado is False
        assert resultado.saldo_restante == 100_000

    def test_verificar_recusa_estimativa_negativa(
        self, tmp_path: Path
    ) -> None:
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        with pytest.raises(ValueError, match="tokens_estimados"):
            skill.verificar("Athena", tokens_estimados=-1)


# ---------------------------------------------------------------------------
# Integração com SteeringEngine (R17.2, R17.6)
# ---------------------------------------------------------------------------


class TestIntegracaoSteering:
    def test_steering_engine_define_orcamento(self, tmp_path: Path) -> None:
        # Diretório de steering com regra real.
        dir_steering = tmp_path / ".kiro" / "steering"
        _escrever_regras_steering(
            dir_steering,
            orcamentos={"Athena": 1_500_000, "Cerberus": 800_000},
        )
        engine = SteeringEngine(dir_steering)

        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            steering_engine=engine,
        )
        estado = skill.obter_estado("Athena", dia=date(2026, 5, 14))
        assert estado.orcamento_diario_tokens == 1_500_000

        estado_cerberus = skill.obter_estado(
            "Cerberus", dia=date(2026, 5, 14)
        )
        assert estado_cerberus.orcamento_diario_tokens == 800_000

    def test_sem_steering_usa_default(self, tmp_path: Path) -> None:
        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            steering_engine=None,
        )
        estado = skill.obter_estado("Athena", dia=date(2026, 5, 14))
        assert estado.orcamento_diario_tokens == ORCAMENTO_TOKENS_DEFAULT

    def test_agente_nao_listado_recebe_default(
        self, tmp_path: Path
    ) -> None:
        dir_steering = tmp_path / ".kiro" / "steering"
        _escrever_regras_steering(
            dir_steering,
            orcamentos={"Athena": 1_500_000},
        )
        engine = SteeringEngine(dir_steering)
        skill = SkillTokenBudget(
            diretorio_budget=tmp_path / ".budget",
            steering_engine=engine,
        )
        # Agente não listado → SteeringEngine retorna default 1.000.000.
        estado = skill.obter_estado("Hermes", dia=date(2026, 5, 14))
        assert estado.orcamento_diario_tokens == ORCAMENTO_TOKENS_DEFAULT


# ---------------------------------------------------------------------------
# Persistência (R17.1, R17.5)
# ---------------------------------------------------------------------------


class TestPersistencia:
    def test_persistencia_json_canonico(self, tmp_path: Path) -> None:
        diretorio = tmp_path / ".budget"
        skill = SkillTokenBudget(diretorio_budget=diretorio)
        skill.registrar_consumo(
            "Athena",
            tokens_input=100,
            tokens_output=200,
            dia=date(2026, 5, 14),
        )

        arquivo = diretorio / "2026-05-14.json"
        assert arquivo.is_file()
        payload = json.loads(arquivo.read_text(encoding="utf-8"))
        assert payload["dia"] == "2026-05-14"
        assert "agentes" in payload
        athena = payload["agentes"]["Athena"]
        for campo in (
            "agente",
            "tokens_input_consumidos",
            "tokens_output_consumidos",
            "tokens_total_consumidos",
            "orcamento_diario_tokens",
        ):
            assert campo in athena, f"campo R17.1 ausente: {campo}"
        assert athena["agente"] == "Athena"
        assert athena["tokens_input_consumidos"] == 100
        assert athena["tokens_output_consumidos"] == 200
        assert athena["tokens_total_consumidos"] == 300

    def test_atomico_nao_deixa_tmp(self, tmp_path: Path) -> None:
        diretorio = tmp_path / ".budget"
        skill = SkillTokenBudget(diretorio_budget=diretorio)
        skill.registrar_consumo(
            "Athena",
            tokens_input=1,
            tokens_output=1,
            dia=date(2026, 5, 14),
        )
        # Apenas o arquivo final deve existir.
        arquivos = list(diretorio.iterdir())
        assert len(arquivos) == 1
        assert arquivos[0].name == "2026-05-14.json"
        assert not any(p.suffix == ".tmp" for p in diretorio.rglob("*"))

    def test_payload_corrompido_nao_quebra_proxima_gravacao(
        self, tmp_path: Path
    ) -> None:
        """JSON existente corrompido deve ser sobrescrito sem erro."""
        diretorio = tmp_path / ".budget"
        diretorio.mkdir()
        (diretorio / "2026-05-14.json").write_text(
            "lixo {{ não-json", encoding="utf-8"
        )
        skill = SkillTokenBudget(diretorio_budget=diretorio)
        # Não deve levantar.
        estado = skill.registrar_consumo(
            "Athena",
            tokens_input=10,
            tokens_output=20,
            dia=date(2026, 5, 14),
        )
        assert estado.tokens_total_consumidos == 30


# ---------------------------------------------------------------------------
# Concorrência (R17.5)
# ---------------------------------------------------------------------------


class TestConcorrencia:
    def test_concurrent_register_atualiza_consistente(
        self, tmp_path: Path
    ) -> None:
        """10 threads registrando 100 tokens cada → total final = 1000.

        Valida que o lock interno protege a sequência leitura+escrita.
        """
        skill = SkillTokenBudget(diretorio_budget=tmp_path / ".budget")
        dia = date(2026, 5, 14)

        erros: list[Exception] = []

        def alvo() -> None:
            try:
                skill.registrar_consumo(
                    "Athena",
                    tokens_input=100,
                    tokens_output=0,
                    dia=dia,
                )
            except Exception as exc:  # pragma: no cover
                erros.append(exc)

        threads = [threading.Thread(target=alvo) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not erros, f"erros em threads: {erros}"
        estado = skill.obter_estado("Athena", dia=dia)
        assert estado.tokens_total_consumidos == 1000
        assert estado.tokens_input_consumidos == 1000
        assert estado.tokens_output_consumidos == 0
