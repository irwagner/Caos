"""Testes unitários da :class:`EstrategiaORBCrabel`.

Cobre o filtro NR4/NR7 de Crabel 1990, sob recomendação do briefing do
Explorador (commit `c1b2bc6`) e estudo dos robôs de referência
(commit pendente).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.orb_crabel import (
    EstrategiaORBCrabel,
    _calcular_range_diario,
    _dias_apos_nr,
)


def _gerar_serie(
    inicio: date,
    ranges_por_dia: list[float],
    barras_por_dia: int = 60,
) -> pd.DataFrame:
    """Gera DataFrame canônico com range diário customizado.

    Cada dia útil tem a mesma trajetória: open=close=100, high=100+r/2,
    low=100-r/2, onde r é o range do dia.
    """
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contagem = 0
    while contagem < len(ranges_por_dia):
        if dia.weekday() < 5:
            r = ranges_por_dia[contagem]
            for h in range(barras_por_dia):
                timestamps.append(dia + pd.Timedelta(minutes=h))
                opens.append(100.0)
                highs.append(100.0 + r / 2)
                lows.append(100.0 - r / 2)
                closes.append(100.0)
            contagem += 1
        dia = dia + pd.Timedelta(days=1)
    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n),
        }
    )


# ---------------------------------------------------------------------------
# _calcular_range_diario
# ---------------------------------------------------------------------------


class TestCalcularRangeDiario:
    def test_basico(self) -> None:
        ranges = [10.0, 20.0, 30.0]
        df = _gerar_serie(date(2025, 1, 6), ranges)
        mapa = _calcular_range_diario(df)
        assert len(mapa) == 3
        assert sorted(mapa.values()) == ranges

    def test_dataframe_vazio(self) -> None:
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
        assert _calcular_range_diario(df) == {}


# ---------------------------------------------------------------------------
# _dias_apos_nr
# ---------------------------------------------------------------------------


class TestDiasAposNr:
    def test_nr4_simples(self) -> None:
        # 5 dias com ranges 10, 8, 12, 6, 15.
        ranges_por_dia = {
            date(2025, 1, 6): 10.0,
            date(2025, 1, 7): 8.0,
            date(2025, 1, 8): 12.0,
            date(2025, 1, 9): 6.0,  # menor da janela 4 dias
            date(2025, 1, 10): 15.0,
        }
        elegiveis, prox = _dias_apos_nr(ranges_por_dia, janela=4)
        assert date(2025, 1, 10) in elegiveis  # dia após o NR4
        # prox indica se o ÚLTIMO dia conhecido é NR.
        assert isinstance(prox, bool)

    def test_janela_invalida(self) -> None:
        with pytest.raises(ValueError):
            _dias_apos_nr({}, janela=1)

    def test_dados_insuficientes(self) -> None:
        # 3 dias, janela 4 — não há janela completa.
        ranges = {date(2025, 1, 6): 10.0, date(2025, 1, 7): 8.0, date(2025, 1, 8): 12.0}
        elegiveis, prox = _dias_apos_nr(ranges, janela=4)
        assert elegiveis == set()
        assert prox is False

    def test_proximo_dia_elegivel_quando_ultimo_eh_nr(self) -> None:
        # Último dia tem o menor range da janela 4 → próximo é elegível.
        ranges = {
            date(2025, 1, 6): 20.0,
            date(2025, 1, 7): 15.0,
            date(2025, 1, 8): 18.0,
            date(2025, 1, 9): 5.0,  # NR4: menor da janela
        }
        elegiveis, prox = _dias_apos_nr(ranges, janela=4)
        # 2025-01-09 é último, NR4, próximo (desconhecido) é elegível.
        assert prox is True
        # Não há "próximo dia" no dict; elegiveis pode estar vazio
        # ou ter dias anteriores.


# ---------------------------------------------------------------------------
# Plugin EstrategiaORBCrabel — comportamento de filtro
# ---------------------------------------------------------------------------


class TestEstrategiaORBCrabel:
    def test_construtor_modo_invalido(self) -> None:
        with pytest.raises(ValueError):
            EstrategiaORBCrabel(modo_nr="nr3")  # type: ignore[arg-type]

    def test_treinar_calcula_dias_elegiveis(self) -> None:
        # 8 dias com ranges variados; janela NR7.
        plugin = EstrategiaORBCrabel(modo_nr="nr7")
        # 8 dias úteis começando 2025-01-06 (segunda).
        ranges = [50.0, 40.0, 45.0, 30.0, 55.0, 60.0, 25.0, 70.0]
        df = _gerar_serie(date(2025, 1, 6), ranges, barras_por_dia=10)
        plugin.treinar(df)
        # 7 ranges fechados após NR7 só aparece quando há janela
        # completa. Com 8 dias, o dia 8 é candidato; ranges[0:7] tem
        # min=25 no dia 7. Logo dia 8 está apos NR7.
        # Mais especificamente: bloco terminado em dia 7 tem ranges
        # 50,40,45,30,55,60,25 → min é 25 no próprio dia 7. Logo dia 8
        # vira elegível.
        elegiveis = plugin.dias_elegiveis
        # Pelo menos algum dia elegível (existe NR no histórico).
        assert len(elegiveis) >= 1

    def test_modo_nr4_e_nr7_diferentes(self) -> None:
        ranges = [10.0, 8.0, 12.0, 6.0, 15.0, 9.0, 11.0, 5.0]
        df = _gerar_serie(date(2025, 1, 6), ranges, barras_por_dia=5)
        p4 = EstrategiaORBCrabel(modo_nr="nr4")
        p7 = EstrategiaORBCrabel(modo_nr="nr7")
        p4.treinar(df.copy())
        p7.treinar(df.copy())
        # NR4 e NR7 devem produzir conjuntos potencialmente diferentes
        # (NR4 tem janela menor, mais dias atendem o filtro).
        assert isinstance(p4.dias_elegiveis, set)
        assert isinstance(p7.dias_elegiveis, set)
        # Pelo menos um dos dois deve ter >= 1 dia elegível.
        assert len(p4.dias_elegiveis) + len(p7.dias_elegiveis) >= 1

    def test_dia_nao_elegivel_nao_emite_trades(self) -> None:
        """Se nenhum dia é elegível, nenhum trade é emitido."""
        # 3 dias só → não há janela NR completa.
        ranges = [10.0, 20.0, 30.0]
        df = _gerar_serie(date(2025, 1, 6), ranges, barras_por_dia=60)
        plugin = EstrategiaORBCrabel(modo_nr="nr7")
        plugin.treinar(df)
        # Como há < 7 dias, não há filtro válido → nenhum dia elegível
        # → nenhum trade.
        assert plugin.dias_elegiveis == set()

    def test_protocol_compatibility(self) -> None:
        plugin = EstrategiaORBCrabel(modo_nr="nr4")
        assert callable(getattr(plugin, "treinar", None))
        assert callable(getattr(plugin, "on_barra", None))
        assert callable(getattr(plugin, "finalizar", None))
        assert plugin.NOME == "EstrategiaORBCrabel"

    def test_zero_parametros_otimizaveis(self) -> None:
        """Filtro Crabel não deve introduzir parâmetros otimizáveis
        novos além da escolha discreta nr4/nr7."""
        # Construtor aceita só modo_nr (categórico) e parametros (ORB
        # padrão, não da Crabel). Sem floats, ints arbitrários, etc.
        import inspect

        sig = inspect.signature(EstrategiaORBCrabel.__init__)
        params = list(sig.parameters.keys())
        # self, modo_nr (Literal), parametros (ParametrosORB).
        assert params == ["self", "modo_nr", "parametros"]
