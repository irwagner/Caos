"""Testes do EstrategiaCircuitBreaker overlay."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.circuit_breaker import (
    EstrategiaCircuitBreaker,
    ParametrosCircuitBreaker,
    _semana_iso,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


class _MockEstrategia:
    """Mock que emite trades determinisicos."""

    NOME = "Mock"

    def __init__(self, trades: List[Trade]) -> None:
        self._trades = trades
        self.foi_treinado = False
        self.barras_recebidas = 0

    def treinar(self, historico: pd.DataFrame) -> None:
        self.foi_treinado = True

    def on_barra(self, barra, contexto) -> None:
        self.barras_recebidas += 1

    def finalizar(self):
        return self._trades


def _trade(
    entrada: str, saida: str, pnl_pts: float = 10.0,
    contratos: int = 1, lado: str = "long",
) -> Trade:
    """Constroi trade com PnL pontos especificado."""
    if lado == "long":
        entrada_p = 100.0
        saida_p = entrada_p + pnl_pts / contratos
    else:
        entrada_p = 100.0
        saida_p = entrada_p - pnl_pts / contratos
    return Trade(
        entrada_timestamp=entrada,
        saida_timestamp=saida,
        entrada_preco=entrada_p,
        saida_preco=saida_p,
        lado=lado,
        contratos=contratos,
        mfe_pontos=max(pnl_pts, 0.5),
        mae_pontos=min(pnl_pts, -0.5),
    )


def _df_minimo(n: int) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2025-03-17T14:30:00Z", periods=n, freq="1min", tz="UTC"
    )
    arr = np.linspace(20000, 20010, n)
    return pd.DataFrame({
        "timestamp": timestamps, "open": arr, "high": arr + 0.25,
        "low": arr - 0.25, "close": arr, "volume": np.ones(n),
    })


# ---------------------------------------------------------------------------
# Parametros
# ---------------------------------------------------------------------------


class TestParametros:
    def test_defaults(self) -> None:
        p = ParametrosCircuitBreaker()
        assert p.limite_diario_pts == -250.0
        assert p.limite_semanal_pts == -750.0
        assert p.limite_janela_pts == -1000.0

    def test_todos_none_levanta(self) -> None:
        with pytest.raises(ValueError, match="pelo menos UM limite"):
            ParametrosCircuitBreaker(
                limite_diario_pts=None,
                limite_semanal_pts=None,
                limite_janela_pts=None,
            )

    def test_limite_positivo_levanta(self) -> None:
        with pytest.raises(ValueError, match="NEGATIVO"):
            ParametrosCircuitBreaker(limite_diario_pts=100.0)


# ---------------------------------------------------------------------------
# _semana_iso
# ---------------------------------------------------------------------------


class TestSemanaISO:
    def test_estavel(self) -> None:
        from datetime import date
        # 2025-03-17 e segunda-feira da semana 12 de 2025.
        assert _semana_iso(date(2025, 3, 17)) == (2025, 12)
        # 2025-03-23 = domingo da mesma semana.
        assert _semana_iso(date(2025, 3, 23)) == (2025, 12)
        # 2025-03-24 = segunda da semana 13.
        assert _semana_iso(date(2025, 3, 24)) == (2025, 13)


# ---------------------------------------------------------------------------
# Sem trigger
# ---------------------------------------------------------------------------


class TestSemTrigger:
    def test_todos_trades_passam(self) -> None:
        # 3 trades positivos, sem trigger.
        trades = [
            _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z", 50),
            _trade("2025-03-17T15:00:00Z", "2025-03-17T15:05:00Z", 30),
            _trade("2025-03-18T14:30:00Z", "2025-03-18T14:35:00Z", 20),
        ]
        mock = _MockEstrategia(trades)
        wrapper = EstrategiaCircuitBreaker(
            mock,
            parametros=ParametrosCircuitBreaker(
                limite_diario_pts=-250.0,
                limite_semanal_pts=-500.0,
                limite_janela_pts=-1000.0,
            ),
        )
        df = _df_minimo(20)
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        out = list(wrapper.finalizar())
        assert len(out) == 3
        stats = wrapper.trades_descartados
        assert stats == {"diario": 0, "semanal": 0, "janela": 0}


# ---------------------------------------------------------------------------
# Trigger diario
# ---------------------------------------------------------------------------


class TestTriggerDiario:
    def test_bloqueia_resto_do_dia(self) -> None:
        # Dia 1: trades de -100 e -200 (acumulado -300, dispara em -250).
        # Dia 2: trade +50.
        trades = [
            _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z", -100),
            _trade("2025-03-17T15:00:00Z", "2025-03-17T15:05:00Z", -200),
            # Apos esse, dia 17 acumulou -300 — abaixo do -250.
            _trade("2025-03-17T16:00:00Z", "2025-03-17T16:05:00Z", +50),
            _trade("2025-03-18T14:30:00Z", "2025-03-18T14:35:00Z", +50),
        ]
        mock = _MockEstrategia(trades)
        wrapper = EstrategiaCircuitBreaker(
            mock,
            parametros=ParametrosCircuitBreaker(
                limite_diario_pts=-250.0,
                limite_semanal_pts=None,
                limite_janela_pts=None,
            ),
        )
        df = _df_minimo(20)
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        out = list(wrapper.finalizar())
        # Trades aceitos: 2 do dia 17 (que atingiram o limite) + dia 18.
        # O 3o trade do dia 17 deve ser DESCARTADO.
        assert len(out) == 3
        assert wrapper.trades_descartados["diario"] == 1

    def test_reset_no_dia_seguinte(self) -> None:
        trades = [
            _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z", -300),
            # Dia 17 disparou em -300 (abaixo do -250).
            _trade("2025-03-17T15:00:00Z", "2025-03-17T15:05:00Z", -100),
            _trade("2025-03-18T14:30:00Z", "2025-03-18T14:35:00Z", +50),
            # Dia 18 e novo, pode operar.
            _trade("2025-03-18T15:00:00Z", "2025-03-18T15:05:00Z", -100),
        ]
        mock = _MockEstrategia(trades)
        wrapper = EstrategiaCircuitBreaker(
            mock,
            parametros=ParametrosCircuitBreaker(
                limite_diario_pts=-250.0,
                limite_semanal_pts=None,
                limite_janela_pts=None,
            ),
        )
        df = _df_minimo(20)
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        out = list(wrapper.finalizar())
        # Aceitos: t0 (dia 17 dispara), t2 (dia 18), t3 (dia 18).
        # Descartado: t1 (dia 17 ja bloqueado).
        assert len(out) == 3
        assert wrapper.trades_descartados["diario"] == 1


# ---------------------------------------------------------------------------
# Trigger janela
# ---------------------------------------------------------------------------


class TestTriggerJanela:
    def test_descarta_resto_da_janela(self) -> None:
        # 4 trades em dias distintos, cada um -300.
        # Total acumula -300, -600, -900, -1200.
        # Limite janela -1000 dispara apos o 4o.
        # Mas o limite diario tambem -250 dispara em cada dia.
        # Para isolar trigger janela, usar so limite_janela:
        trades = [
            _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z", -300),
            _trade("2025-03-18T14:30:00Z", "2025-03-18T14:35:00Z", -300),
            _trade("2025-03-19T14:30:00Z", "2025-03-19T14:35:00Z", -500),
            # Janela acumula -1100 — dispara.
            _trade("2025-03-20T14:30:00Z", "2025-03-20T14:35:00Z", +50),
            _trade("2025-03-21T14:30:00Z", "2025-03-21T14:35:00Z", +50),
        ]
        mock = _MockEstrategia(trades)
        wrapper = EstrategiaCircuitBreaker(
            mock,
            parametros=ParametrosCircuitBreaker(
                limite_diario_pts=None,
                limite_semanal_pts=None,
                limite_janela_pts=-1000.0,
            ),
        )
        df = _df_minimo(20)
        wrapper.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            wrapper.on_barra(barra, iterator)
        out = list(wrapper.finalizar())
        # Aceitos: 3 primeiros (-1100). Descartados: 4o e 5o.
        assert len(out) == 3
        assert wrapper.trades_descartados["janela"] == 2


# ---------------------------------------------------------------------------
# Integracao Protocol
# ---------------------------------------------------------------------------


class TestProtocolo:
    def test_metodos(self) -> None:
        mock = _MockEstrategia([])
        wrapper = EstrategiaCircuitBreaker(mock)
        assert wrapper.NOME == "EstrategiaCircuitBreaker"
        assert callable(wrapper.on_barra)
        assert callable(wrapper.finalizar)
        assert callable(wrapper.treinar)

    def test_treinar_propaga(self) -> None:
        mock = _MockEstrategia([])
        wrapper = EstrategiaCircuitBreaker(mock)
        df = _df_minimo(5)
        wrapper.treinar(df)
        assert mock.foi_treinado is True

    def test_construtor_rejeita_invalido(self) -> None:
        class Bad:
            pass
        with pytest.raises(TypeError, match="on_barra"):
            EstrategiaCircuitBreaker(Bad())
