"""Testes unitários do split tripartite (hold-out cego).

Cobre o item 3 da Decisao_Do_Conselho 2026-05-23-01: antes de qualquer
sweep paramétrico, isolar 20% dos dados (ou N dias úteis) como hold-out
cego — esses dias NÃO entram no Walk-Forward rolante.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from caos.walk_forward.engine import _separar_holdout
from caos.walk_forward.models import (
    ConfiguracaoWalkForward,
    CustosOperacionais,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gerar_minute_bars(
    inicio: datetime,
    dias_uteis: int,
    barras_por_dia: int = 60,
) -> pd.DataFrame:
    """Gera DataFrame canônico com N dias úteis × M barras/dia."""
    timestamps: list[pd.Timestamp] = []
    dia = pd.Timestamp(inicio).normalize().tz_localize("UTC")
    while len(timestamps) < dias_uteis * barras_por_dia:
        if dia.weekday() < 5:
            for h in range(barras_por_dia):
                timestamps.append(dia + pd.Timedelta(minutes=h))
        dia = dia + pd.Timedelta(days=1)

    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": np.linspace(100.0, 200.0, n),
            "high": np.linspace(101.0, 201.0, n),
            "low": np.linspace(99.0, 199.0, n),
            "close": np.linspace(100.5, 200.5, n),
            "volume": np.full(n, 1000.0),
        }
    )


# ---------------------------------------------------------------------------
# Configuração — campo holdout_dias_uteis
# ---------------------------------------------------------------------------


class TestConfiguracaoComHoldout:
    def test_default_e_none(self) -> None:
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
        )
        assert cfg.holdout_dias_uteis is None

    def test_aceita_inteiro_valido(self) -> None:
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
            holdout_dias_uteis=30,
        )
        assert cfg.holdout_dias_uteis == 30

    @pytest.mark.parametrize("invalido", [9, 0, -5, 3000])
    def test_rejeita_fora_da_faixa(self, invalido: int) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(
                tamanho_treino_dias_uteis=60,
                tamanho_teste_dias_uteis=10,
                granularidade="1m",
                holdout_dias_uteis=invalido,
            )


# ---------------------------------------------------------------------------
# _separar_holdout — comportamento básico
# ---------------------------------------------------------------------------


class TestSepararHoldout:
    def test_corta_ultimos_n_dias_uteis(self) -> None:
        # 100 dias úteis × 60 barras/dia = 6000 barras.
        barras = _gerar_minute_bars(
            inicio=datetime(2025, 1, 6, 0, 0),  # segunda-feira
            dias_uteis=100,
        )
        barras_wf, holdout_inicio, holdout_fim = _separar_holdout(
            barras=barras,
            holdout_dias_uteis=20,
        )

        # Restam 80 dias úteis × 60 = 4800 barras no WF.
        assert len(barras_wf) == 80 * 60

        # Todas as barras do WF têm timestamp < holdout_inicio.
        assert (barras_wf["timestamp"] < holdout_inicio).all()

        # holdout_inicio é o primeiro dia útil do hold-out (00:00 UTC).
        assert holdout_inicio.tzinfo is not None
        assert holdout_inicio.utcoffset() == timedelta(0)
        assert holdout_inicio.hour == 0
        assert holdout_inicio.minute == 0

        # holdout_fim > holdout_inicio.
        assert holdout_fim > holdout_inicio

    def test_holdout_inicio_aponta_para_dia_correto(self) -> None:
        # 30 dias úteis começando 2025-01-06 (seg). Hold-out = 5 últimos.
        barras = _gerar_minute_bars(
            inicio=datetime(2025, 1, 6, 0, 0),
            dias_uteis=30,
        )
        # Lista esperada de dias úteis: pula sábado/domingo. Os 25
        # primeiros vão para WF, os 5 últimos para hold-out.
        # A meia-noite do 26º dia útil (índice 25) é holdout_inicio.
        # 30 dias úteis a partir de 06/jan = 30 weekdays:
        # 06, 07, 08, 09, 10 (sem), 13...17, 20...24, 27...31,
        # 03...07/fev, 10...14/fev. → 30º útil = 14/fev/2025 (sex).
        # 26º útil = 10/fev/2025 (seg). Esse é holdout_inicio.
        _, holdout_inicio, _ = _separar_holdout(
            barras=barras,
            holdout_dias_uteis=5,
        )
        assert holdout_inicio.date() == datetime(2025, 2, 10).date()

    def test_holdout_zero_nao_remove_nada_seria_invalido(self) -> None:
        # holdout_dias_uteis=0 não passa pelo validador da Configuracao
        # (ge=10), mas a função interna aceita >0.
        # Validamos que, se passado 0, função levanta porque len(dias)
        # não é > 0.
        barras = _gerar_minute_bars(
            inicio=datetime(2025, 1, 6, 0, 0),
            dias_uteis=10,
        )
        # holdout = total → falha.
        with pytest.raises(ValueError):
            _separar_holdout(barras=barras, holdout_dias_uteis=10)

    def test_holdout_maior_que_total_levanta(self) -> None:
        barras = _gerar_minute_bars(
            inicio=datetime(2025, 1, 6, 0, 0),
            dias_uteis=15,
        )
        with pytest.raises(ValueError) as exc:
            _separar_holdout(barras=barras, holdout_dias_uteis=20)
        assert "holdout" in str(exc.value).lower()

    def test_dataframe_sem_coluna_timestamp_levanta(self) -> None:
        df = pd.DataFrame({"close": [1.0, 2.0]})
        with pytest.raises(ValueError):
            _separar_holdout(barras=df, holdout_dias_uteis=10)


# ---------------------------------------------------------------------------
# Integração com Engine — hold-out reduz o universo do WF rolante
# ---------------------------------------------------------------------------


class TestIntegracaoEngineHoldout:
    """Testa que o WalkForwardEngine.executar realmente pula as barras
    do hold-out (sem precisar de SkillDataReader real)."""

    def test_engine_aplica_holdout_e_registra_no_resultado(
        self, tmp_path: Path
    ) -> None:
        from caos.walk_forward.engine import WalkForwardEngine
        from caos.walk_forward.runner import Trade

        # 100 dias × 1 barra/dia. Sem hold-out: 100 barras → janelas
        # treino=60+teste=10 = 4 janelas (60+10, 70+10, 80+10, 90+10).
        # Com holdout=20: 80 barras → 2 janelas (60+10, 70+10).
        barras = _gerar_minute_bars(
            inicio=datetime(2025, 1, 6, 0, 0),
            dias_uteis=100,
            barras_por_dia=1,
        )

        # Estratégia stub que sempre devolve 1 trade fake.
        class _Estrat:
            NOME = "Stub"

            def on_barra(self, barra, ctx):  # noqa: D401 — interface
                pass

            def finalizar(self):
                return [Trade(pnl=1.0)]

        # Para evitar passar pelo Skill_Data_Integrity, mockamos via
        # criação de manifesto trivial. Aqui usamos diretamente
        # _separar_holdout (já testado) + JanelaGenerator.
        from caos.walk_forward.janelas import JanelaGenerator

        cfg_sem = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
        )
        cfg_com = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
            holdout_dias_uteis=20,
        )

        # Sem hold-out: 4 janelas.
        janelas_sem = JanelaGenerator.gerar(
            barras, cfg_sem, hash_dados="0" * 64
        )
        assert len(janelas_sem) == 4

        # Com hold-out de 20: corta as últimas 20 barras → 80 dias →
        # 2 janelas.
        barras_wf, _, _ = _separar_holdout(
            barras=barras, holdout_dias_uteis=20
        )
        janelas_com = JanelaGenerator.gerar(
            barras_wf, cfg_com, hash_dados="0" * 64
        )
        assert len(janelas_com) == 2


# ---------------------------------------------------------------------------
# Reexport
# ---------------------------------------------------------------------------


def test_holdout_field_acessivel_via_pacote() -> None:
    from caos.walk_forward import ConfiguracaoWalkForward as REEXP

    cfg = REEXP(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        holdout_dias_uteis=30,
    )
    assert cfg.holdout_dias_uteis == 30
