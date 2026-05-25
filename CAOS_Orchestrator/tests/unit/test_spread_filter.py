"""Testes do EstrategiaSpreadFilter overlay."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.spread_filter import (
    EstrategiaSpreadFilter,
    ParametrosSpreadFilter,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


# ---------------------------------------------------------------------------
# Estrategia de mock que conta barras vistas
# ---------------------------------------------------------------------------


class _EstrategiaMock:
    """Mock que registra cada barra recebida em on_barra."""

    NOME = "MockInterna"

    def __init__(self) -> None:
        self.barras_vistas: List[pd.Timestamp] = []
        self.foi_treinado = False

    def treinar(self, historico: pd.DataFrame) -> None:
        self.foi_treinado = True

    def on_barra(self, barra, contexto) -> None:
        self.barras_vistas.append(pd.Timestamp(barra["timestamp"]))

    def finalizar(self):
        return []


def _gerar_serie_minute(
    inicio: date, num_dias: int, barras_por_dia: int = 60
) -> pd.DataFrame:
    timestamps: List[pd.Timestamp] = []
    closes: List[float] = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contador = 0
    while contador < num_dias * barras_por_dia:
        if dia.weekday() < 5:
            base = dia.replace(hour=14, minute=30)
            for i in range(barras_por_dia):
                ts = base + pd.Timedelta(minutes=i)
                timestamps.append(ts)
                closes.append(20000.0 + 0.1 * i)
                contador += 1
        dia += pd.Timedelta(days=1)
    n = len(timestamps)
    arr = np.array(closes)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": arr,
            "high": arr + 0.25,
            "low": arr - 0.25,
            "close": arr,
            "volume": np.ones(n),
        }
    )


def _criar_csv_spread(tmp_path: Path, df_spread: pd.DataFrame) -> Path:
    """Cria spread_minuto.csv minimo no formato canonico."""
    csv_path = tmp_path / "spread_minuto.csv"
    cols_canonicas = [
        "minuto_utc", "num_ticks_last", "volume_total", "last_first",
        "last_last", "last_high", "last_low", "bid_min", "bid_max",
        "bid_avg", "ask_min", "ask_max", "ask_avg", "spread_avg",
        "spread_median", "spread_min", "spread_max", "spread_n_amostras",
    ]
    df = pd.DataFrame({c: [None] * len(df_spread) for c in cols_canonicas})
    df["minuto_utc"] = df_spread["minuto_utc"].astype(str)
    df["spread_avg"] = df_spread["spread_avg"].values
    df.to_csv(csv_path, index=False)
    return csv_path


# ---------------------------------------------------------------------------
# Parametros
# ---------------------------------------------------------------------------


class TestParametros:
    def test_defaults(self) -> None:
        p = ParametrosSpreadFilter()
        assert p.modo == "mediana_diaria"
        assert p.quantil_corte == 0.5
        assert p.hora_inicio_utc == time(14, 30)
        assert p.hora_fim_utc == time(19, 0)
        assert p.permitir_se_falta_dado is True

    def test_modo_invalido(self) -> None:
        with pytest.raises(ValueError, match="modo"):
            ParametrosSpreadFilter(modo="xpto")  # type: ignore[arg-type]

    def test_quantil_fora_range(self) -> None:
        with pytest.raises(ValueError, match="quantil"):
            ParametrosSpreadFilter(quantil_corte=0.05)
        with pytest.raises(ValueError, match="quantil"):
            ParametrosSpreadFilter(quantil_corte=0.99)

    def test_hora_invertida(self) -> None:
        with pytest.raises(ValueError, match="hora_inicio"):
            ParametrosSpreadFilter(
                hora_inicio_utc=time(20, 0),
                hora_fim_utc=time(15, 0),
            )


# ---------------------------------------------------------------------------
# Modo hora_otima (sem dependencia de CSV)
# ---------------------------------------------------------------------------


class TestModoHoraOtima:
    def test_bloqueia_minutos_fora_da_janela(self) -> None:
        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(
                modo="hora_otima",
                hora_inicio_utc=time(14, 30),
                hora_fim_utc=time(19, 0),
            ),
        )
        df = _gerar_serie_minute(date(2025, 3, 17), num_dias=2, barras_por_dia=120)
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        wrapper.finalizar()

        for ts in mock.barras_vistas:
            hora = ts.time()
            assert time(14, 30) <= hora < time(19, 0), (
                f"Mock recebeu barra fora da janela: {ts}"
            )

    def test_estatisticas_contam_corretamente(self) -> None:
        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(modo="hora_otima"),
        )
        df = _gerar_serie_minute(date(2025, 3, 17), num_dias=1, barras_por_dia=120)
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)

        stats = wrapper.estatisticas
        assert stats["barras_recebidas"] == 120
        assert stats["barras_bloqueadas"] + len(mock.barras_vistas) == 120


# ---------------------------------------------------------------------------
# Modo mediana_diaria com CSV
# ---------------------------------------------------------------------------


class TestModoMedianaDiaria:
    def test_bloqueia_minutos_acima_da_mediana(self, tmp_path: Path) -> None:
        # 4 minutos do mesmo dia: spreads 0.3, 0.4, 0.6, 0.8.
        # Mediana = 0.5. So 2 primeiros passam.
        spreads = pd.DataFrame({
            "minuto_utc": [
                "2025-03-17T14:30:00Z", "2025-03-17T14:31:00Z",
                "2025-03-17T14:32:00Z", "2025-03-17T14:33:00Z",
            ],
            "spread_avg": [0.3, 0.4, 0.6, 0.8],
        })
        csv = _criar_csv_spread(tmp_path, spreads)

        # Cria 4 barras correspondentes.
        timestamps = pd.to_datetime([
            "2025-03-17T14:30:00Z", "2025-03-17T14:31:00Z",
            "2025-03-17T14:32:00Z", "2025-03-17T14:33:00Z",
        ], utc=True)
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [20000.0] * 4,
            "high": [20001.0] * 4,
            "low": [19999.0] * 4,
            "close": [20000.0] * 4,
            "volume": [1.0] * 4,
        })

        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(modo="mediana_diaria"),
            caminhos_spread_csv=[csv],
        )
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)

        # So as barras com spread <= 0.5 passam (0.3 e 0.4).
        assert len(mock.barras_vistas) == 2
        horas_vistas = [ts.time() for ts in mock.barras_vistas]
        assert time(14, 30) in horas_vistas
        assert time(14, 31) in horas_vistas

    def test_falta_dado_permite_default(self, tmp_path: Path) -> None:
        # CSV com apenas 1 minuto. Os outros nao tem dado.
        spreads = pd.DataFrame({
            "minuto_utc": ["2025-03-17T14:30:00Z"],
            "spread_avg": [0.3],
        })
        csv = _criar_csv_spread(tmp_path, spreads)

        # Barras em minutos sem dado.
        timestamps = pd.to_datetime([
            "2025-03-17T15:00:00Z", "2025-03-17T15:01:00Z",
        ], utc=True)
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [20000.0] * 2,
            "high": [20001.0] * 2,
            "low": [19999.0] * 2,
            "close": [20000.0] * 2,
            "volume": [1.0] * 2,
        })

        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(
                modo="mediana_diaria", permitir_se_falta_dado=True,
            ),
            caminhos_spread_csv=[csv],
        )
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        # Permite ambas (default).
        assert len(mock.barras_vistas) == 2

    def test_falta_dado_bloqueia_se_configurado(self, tmp_path: Path) -> None:
        spreads = pd.DataFrame({
            "minuto_utc": ["2025-03-17T14:30:00Z"],
            "spread_avg": [0.3],
        })
        csv = _criar_csv_spread(tmp_path, spreads)

        timestamps = pd.to_datetime([
            "2025-03-17T15:00:00Z", "2025-03-17T15:01:00Z",
        ], utc=True)
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [20000.0] * 2,
            "high": [20001.0] * 2,
            "low": [19999.0] * 2,
            "close": [20000.0] * 2,
            "volume": [1.0] * 2,
        })

        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(
                modo="mediana_diaria", permitir_se_falta_dado=False,
            ),
            caminhos_spread_csv=[csv],
        )
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        assert len(mock.barras_vistas) == 0


# ---------------------------------------------------------------------------
# Modo quantil_global
# ---------------------------------------------------------------------------


class TestModoQuantilGlobal:
    def test_bloqueia_minutos_acima_do_quantil(self, tmp_path: Path) -> None:
        # 10 minutos com spreads 0.1..1.0. p50 = 0.55.
        spreads = pd.DataFrame({
            "minuto_utc": [f"2025-03-17T14:{30+i:02d}:00Z" for i in range(10)],
            "spread_avg": [0.1 + 0.1 * i for i in range(10)],
        })
        csv = _criar_csv_spread(tmp_path, spreads)

        timestamps = pd.to_datetime(
            [f"2025-03-17T14:{30+i:02d}:00Z" for i in range(10)], utc=True
        )
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [20000.0] * 10,
            "high": [20001.0] * 10,
            "low": [19999.0] * 10,
            "close": [20000.0] * 10,
            "volume": [1.0] * 10,
        })

        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(
                modo="quantil_global", quantil_corte=0.5,
            ),
            caminhos_spread_csv=[csv],
        )
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        # Deve passar ~5 (os de menor spread).
        assert 4 <= len(mock.barras_vistas) <= 6


# ---------------------------------------------------------------------------
# Integracao com Estrategia real
# ---------------------------------------------------------------------------


class TestIntegracao:
    def test_protocolo(self) -> None:
        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock,
            parametros=ParametrosSpreadFilter(modo="hora_otima"),
        )
        assert callable(getattr(wrapper, "on_barra", None))
        assert callable(getattr(wrapper, "finalizar", None))
        assert callable(getattr(wrapper, "treinar", None))
        assert wrapper.NOME == "EstrategiaSpreadFilter"

    def test_treinar_repassa_para_interna(self) -> None:
        mock = _EstrategiaMock()
        wrapper = EstrategiaSpreadFilter(
            mock, parametros=ParametrosSpreadFilter(modo="hora_otima")
        )
        df = _gerar_serie_minute(date(2025, 3, 17), num_dias=1)
        wrapper.treinar(df)
        assert mock.foi_treinado is True

    def test_construtor_rejeita_estrategia_invalida(self) -> None:
        class BadStrategy:
            pass

        with pytest.raises(TypeError, match="on_barra"):
            EstrategiaSpreadFilter(BadStrategy())
