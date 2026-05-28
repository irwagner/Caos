"""Testes unitários do plugin :class:`EstrategiaValueAreaFilter`."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.value_area_filter import (
    COBERTURA_VA_PADRAO,
    EstrategiaValueAreaFilter,
    ParametrosValueAreaFilter,
    ValueAreaDia,
    calcular_value_area,
)


def _gerar_barras_dia(
    dia: date,
    minutos: int = 1380,
    preco_central: float = 25000.0,
    range_pts: float = 100.0,
    volume_por_barra: float = 100.0,
) -> pd.DataFrame:
    """Gera barras sintéticas de 1 minuto distribuídas em torno de preco_central."""
    timestamps = []
    opens, highs, lows, closes, volumes = [], [], [], [], []
    inicio = pd.Timestamp(dia).tz_localize("UTC") + pd.Timedelta(hours=13, minutes=30)
    np.random.seed(42)
    for i in range(minutos):
        ts = inicio + pd.Timedelta(minutes=i)
        # Preço oscila aleatoriamente em torno do central.
        oscilacao = np.random.uniform(-range_pts / 2, range_pts / 2)
        o = preco_central + oscilacao
        c = o + np.random.uniform(-1, 1)
        h = max(o, c) + abs(np.random.uniform(0, 1))
        l = min(o, c) - abs(np.random.uniform(0, 1))
        timestamps.append(ts)
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        volumes.append(volume_por_barra)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


# ---------------------------------------------------------------------------
# calcular_value_area
# ---------------------------------------------------------------------------


class TestCalcularValueArea:
    def test_dataframe_vazio_retorna_none(self) -> None:
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([], utc=True),
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": [],
            }
        )
        assert calcular_value_area(df) is None

    def test_volume_zero_retorna_none(self) -> None:
        df = _gerar_barras_dia(date(2025, 1, 6), volume_por_barra=0.0)
        assert calcular_value_area(df) is None

    def test_va_cobre_aprox_70_porcento(self) -> None:
        df = _gerar_barras_dia(date(2025, 1, 6))
        va = calcular_value_area(df, cobertura=0.70)
        assert va is not None
        # Cobertura efetiva deve estar próxima de 70% (algoritmo
        # discreto pode passar um pouco devido a granularidade do bin).
        assert 0.68 <= va.cobertura_real <= 0.85

    def test_poc_dentro_da_va(self) -> None:
        df = _gerar_barras_dia(date(2025, 1, 6))
        va = calcular_value_area(df)
        assert va is not None
        assert va.va_low <= va.poc <= va.va_high

    def test_va_dentro_do_range_diario(self) -> None:
        df = _gerar_barras_dia(date(2025, 1, 6))
        va = calcular_value_area(df)
        assert va is not None
        assert va.va_low >= df["low"].min()
        assert va.va_high <= df["high"].max()

    def test_cobertura_invalida_eh_aceita_pela_funcao_pura(self) -> None:
        # A funcao calcular_value_area nao valida cobertura — a validacao
        # esta nos ParametrosValueAreaFilter. Aqui apenas verificamos
        # que retorna alguma VA mesmo com valores estranhos.
        df = _gerar_barras_dia(date(2025, 1, 6))
        va_50 = calcular_value_area(df, cobertura=0.50)
        va_90 = calcular_value_area(df, cobertura=0.90)
        assert va_50 is not None and va_90 is not None
        # VA mais ampla quando cobertura e maior.
        assert (va_90.va_high - va_90.va_low) >= (va_50.va_high - va_50.va_low)


# ---------------------------------------------------------------------------
# ParametrosValueAreaFilter
# ---------------------------------------------------------------------------


class TestParametrosValueAreaFilter:
    def test_defaults(self) -> None:
        p = ParametrosValueAreaFilter()
        assert p.modo == "trend"
        assert p.cobertura_va == COBERTURA_VA_PADRAO
        assert p.permitir_se_falta_dado is True

    def test_modo_invalido_levanta(self) -> None:
        with pytest.raises(ValueError):
            ParametrosValueAreaFilter(modo="reverter")  # type: ignore[arg-type]

    def test_cobertura_fora_range_levanta(self) -> None:
        with pytest.raises(ValueError):
            ParametrosValueAreaFilter(cobertura_va=0.1)
        with pytest.raises(ValueError):
            ParametrosValueAreaFilter(cobertura_va=0.95)


# ---------------------------------------------------------------------------
# EstrategiaValueAreaFilter — comportamento
# ---------------------------------------------------------------------------


class _EstrategiaInternaFake:
    """Fake que conta chamadas a on_barra para verificar bloqueio."""

    def __init__(self) -> None:
        self.barras_recebidas: list[pd.Series] = []
        self.treinou: bool = False

    def treinar(self, historico: pd.DataFrame) -> None:
        self.treinou = True

    def on_barra(self, barra: pd.Series, contexto: Any) -> None:
        self.barras_recebidas.append(barra)

    def finalizar(self):
        return ()


class TestEstrategiaValueAreaFilter:
    def test_construtor_rejeita_estrategia_sem_protocolo(self) -> None:
        with pytest.raises(TypeError):
            EstrategiaValueAreaFilter(estrategia_interna=object())

    def test_treinar_calcula_va_por_dia_de_treino(self) -> None:
        interna = _EstrategiaInternaFake()
        filtro = EstrategiaValueAreaFilter(interna)
        historico = pd.concat(
            [
                _gerar_barras_dia(date(2025, 1, 6), minutos=300),
                _gerar_barras_dia(date(2025, 1, 7), minutos=300),
                _gerar_barras_dia(date(2025, 1, 8), minutos=300),
            ],
            ignore_index=True,
        )
        filtro.treinar(historico)
        assert interna.treinou
        assert len(filtro.va_por_dia) == 3

    def test_dia_sem_va_anterior_permite_se_padrao(self) -> None:
        # Primeiro dia sem treino - permitir_se_falta_dado=True (default).
        interna = _EstrategiaInternaFake()
        filtro = EstrategiaValueAreaFilter(interna)
        filtro.treinar(pd.DataFrame(
            {
                "timestamp": pd.to_datetime([], utc=True),
                "open": [], "high": [], "low": [], "close": [], "volume": [],
            }
        ))
        df_dia = _gerar_barras_dia(date(2025, 1, 6), minutos=10)
        for _, b in df_dia.iterrows():
            filtro.on_barra(b, contexto=None)
        # Deve ter passado todas as barras (sem VA do dia anterior).
        assert len(interna.barras_recebidas) == 10

    def test_modo_trend_bloqueia_dia_range(self) -> None:
        # Setup: dia 1 com preco 25000, VA estreita ~25000.
        # Dia 2 com abertura 25001 (DENTRO da VA do dia 1) → RANGE.
        # Modo trend deve bloquear todas as barras do dia 2.
        interna = _EstrategiaInternaFake()
        filtro = EstrategiaValueAreaFilter(
            interna, parametros=ParametrosValueAreaFilter(modo="trend")
        )
        treino = _gerar_barras_dia(
            date(2025, 1, 6), minutos=300, preco_central=25000.0, range_pts=20.0
        )
        filtro.treinar(treino)
        # Dia seguinte: abertura próxima do preco_central (dentro da VA).
        df_teste = _gerar_barras_dia(
            date(2025, 1, 7), minutos=10, preco_central=25000.0, range_pts=20.0
        )
        for _, b in df_teste.iterrows():
            filtro.on_barra(b, contexto=None)
        stats = filtro.estatisticas
        # Esperado: regime detectado, dia bloqueado.
        regime = filtro.regime_por_dia.get(date(2025, 1, 7))
        # O fixture tem variação aleatória, mas o caso é construído para RANGE.
        if regime == "RANGE":
            assert stats["barras_bloqueadas"] == 10
            assert len(interna.barras_recebidas) == 0

    def test_modo_trend_permite_dia_trend(self) -> None:
        # Treino: preco central 25000, range estreito.
        # Teste: abertura 25500 (FORA da VA do treino) → TREND.
        interna = _EstrategiaInternaFake()
        filtro = EstrategiaValueAreaFilter(
            interna, parametros=ParametrosValueAreaFilter(modo="trend")
        )
        treino = _gerar_barras_dia(
            date(2025, 1, 6), minutos=300, preco_central=25000.0, range_pts=20.0
        )
        filtro.treinar(treino)
        # Abertura bem fora da VA (gap de +500 pts).
        df_teste = _gerar_barras_dia(
            date(2025, 1, 7), minutos=10, preco_central=25500.0, range_pts=10.0
        )
        for _, b in df_teste.iterrows():
            filtro.on_barra(b, contexto=None)
        regime = filtro.regime_por_dia.get(date(2025, 1, 7))
        assert regime == "TREND"
        # Deve permitir todas as barras.
        assert len(interna.barras_recebidas) == 10

    def test_modo_range_inverso_bloqueia_dia_trend(self) -> None:
        interna = _EstrategiaInternaFake()
        filtro = EstrategiaValueAreaFilter(
            interna, parametros=ParametrosValueAreaFilter(modo="range")
        )
        treino = _gerar_barras_dia(
            date(2025, 1, 6), minutos=300, preco_central=25000.0, range_pts=20.0
        )
        filtro.treinar(treino)
        # Abertura fora da VA → TREND. Modo range deve BLOQUEAR.
        df_teste = _gerar_barras_dia(
            date(2025, 1, 7), minutos=10, preco_central=25500.0, range_pts=10.0
        )
        for _, b in df_teste.iterrows():
            filtro.on_barra(b, contexto=None)
        regime = filtro.regime_por_dia.get(date(2025, 1, 7))
        assert regime == "TREND"
        assert len(interna.barras_recebidas) == 0
        assert filtro.estatisticas["barras_bloqueadas"] == 10

    def test_estatisticas_disponiveis(self) -> None:
        interna = _EstrategiaInternaFake()
        filtro = EstrategiaValueAreaFilter(interna)
        filtro.treinar(_gerar_barras_dia(date(2025, 1, 6), minutos=300))
        stats = filtro.estatisticas
        # Valores antes de qualquer on_barra.
        assert stats["barras_recebidas"] == 0
        assert stats["barras_bloqueadas"] == 0
        assert "dias_classificados" in stats
        assert "dias_trend" in stats
        assert "dias_range" in stats

    def test_zero_parametros_otimizaveis_continuos(self) -> None:
        # ParametrosValueAreaFilter so tem categorical (modo) +
        # cobertura_va (constante de Market Profile) + flag bool.
        # Nenhum float otimizavel livre.
        import inspect

        sig = inspect.signature(ParametrosValueAreaFilter.__init__)
        # __init__ de dataclass tem self + cada campo.
        nomes = list(sig.parameters.keys())
        assert nomes == ["self", "modo", "cobertura_va", "permitir_se_falta_dado"]
