"""Testes unitários do módulo :mod:`caos.walk_forward.caracterizacao`.

Cobre o item 3 da Decisao_Do_Conselho 2026-05-23-01: análise descritiva
da série antes de propor nova família de estratégias.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.caracterizacao import (
    LIMIAR_GAP_SIGNIFICATIVO_PCT,
    RelatorioCaracterizacao,
    SumarioAutocorrelacao,
    SumarioGaps,
    SumarioRangeDiario,
    SumarioVolatilidadeIntradia,
    calcular_autocorrelacao,
    calcular_gaps,
    calcular_range_diario,
    calcular_volatilidade_intradia,
    caracterizar_serie,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serie_minute(
    inicio: datetime,
    num_dias_uteis: int,
    barras_por_dia: int = 60,
    seed: int = 42,
    base_close: float = 100.0,
) -> pd.DataFrame:
    """Constrói DataFrame canônico com retornos pseudo-aleatórios estáveis."""
    rng = np.random.default_rng(seed)
    timestamps: list[pd.Timestamp] = []
    dia = pd.Timestamp(inicio).normalize().tz_localize("UTC")
    while len([t for t in timestamps]) < num_dias_uteis * barras_por_dia:
        if dia.weekday() < 5:
            for h in range(barras_por_dia):
                timestamps.append(dia + pd.Timedelta(minutes=h))
        dia = dia + pd.Timedelta(days=1)

    n = len(timestamps)
    # Random-walk simétrico — ρ ≈ 0 no lag 1.
    rets = rng.normal(0, 0.001, size=n)
    closes = base_close * np.exp(np.cumsum(rets))
    opens = np.concatenate([[base_close], closes[:-1]])
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.5, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.5, n))
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": rng.integers(100, 10_000, size=n).astype(float),
        }
    )


# ---------------------------------------------------------------------------
# Range diário
# ---------------------------------------------------------------------------


class TestRangeDiario:
    def test_range_basico(self) -> None:
        # 3 dias úteis × 10 barras. Range calculado como max(high)-min(low).
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=3, barras_por_dia=10)
        sumario = calcular_range_diario(df)
        assert sumario.num_dias == 3
        assert sumario.media_pontos > 0
        assert sumario.mediana_pontos > 0
        assert sumario.p05_pontos <= sumario.mediana_pontos <= sumario.p95_pontos

    def test_dataframe_vazio_levanta(self) -> None:
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
        with pytest.raises(ValueError):
            calcular_range_diario(df)

    def test_um_unico_dia(self) -> None:
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=1, barras_por_dia=10)
        sumario = calcular_range_diario(df)
        assert sumario.num_dias == 1
        # Apenas 1 amostra → std=0 (ddof=1 não definido, fallback 0).
        assert sumario.desvio_padrao_pontos == 0.0


# ---------------------------------------------------------------------------
# Autocorrelação
# ---------------------------------------------------------------------------


class TestAutocorrelacao:
    def test_random_walk_tem_autocorrelacao_perto_de_zero(self) -> None:
        # Random walk geométrico → ρ(1) ≈ 0.
        df = _serie_minute(
            datetime(2026, 1, 5, 0, 0), num_dias_uteis=20, barras_por_dia=60, seed=1
        )
        sumario = calcular_autocorrelacao(df)
        # Random walk não garante exatamente zero, mas deve ser pequeno.
        assert abs(sumario.autocorrelacoes[1]) < 0.05
        assert isinstance(sumario, SumarioAutocorrelacao)
        assert sumario.num_observacoes > 1000

    def test_serie_mean_reverting_tem_rho1_negativo(self) -> None:
        # Constrói série AR(1) com phi=-0.5: x_{t+1} = -0.5*x_t + ruido.
        # Em log-retornos isso aparece como autocorrelação negativa
        # forte no lag 1.
        n = 5000
        rng = np.random.default_rng(2)
        ret = np.zeros(n)
        for i in range(1, n):
            ret[i] = -0.5 * ret[i - 1] + rng.normal(0, 0.001)
        closes = 100 * np.exp(np.cumsum(ret))
        ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": np.ones(n),
            }
        )
        sumario = calcular_autocorrelacao(df, lags_minutos=(1,))
        # AR(-0.5) deve produzir rho(1) claramente negativo.
        assert sumario.autocorrelacoes[1] < -0.3

    def test_serie_momentum_tem_rho1_positivo(self) -> None:
        # AR(1) com phi=+0.5 → rho(1) positivo.
        n = 5000
        rng = np.random.default_rng(3)
        ret = np.zeros(n)
        for i in range(1, n):
            ret[i] = 0.5 * ret[i - 1] + rng.normal(0, 0.001)
        closes = 100 * np.exp(np.cumsum(ret))
        ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": np.ones(n),
            }
        )
        sumario = calcular_autocorrelacao(df, lags_minutos=(1,))
        assert sumario.autocorrelacoes[1] > 0.3

    def test_serie_curta_demais_levanta(self) -> None:
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=1, freq="1min", tz="UTC"),
                "open": [100.0],
                "high": [100.0],
                "low": [100.0],
                "close": [100.0],
                "volume": [1.0],
            }
        )
        with pytest.raises(ValueError):
            calcular_autocorrelacao(df)


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------


class TestGaps:
    def test_um_dia_so_devolve_zero_gaps(self) -> None:
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=1)
        sumario = calcular_gaps(df)
        assert sumario.num_gaps_observados == 0
        assert sumario.gaps_pontos == ()

    def test_multiplos_dias(self) -> None:
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=10)
        sumario = calcular_gaps(df)
        # 10 dias úteis -> 9 gaps.
        assert sumario.num_gaps_observados == 9
        assert len(sumario.gaps_pontos) == 9
        assert isinstance(sumario.fracao_gaps_significativos, float)
        assert 0.0 <= sumario.fracao_gaps_significativos <= 1.0

    def test_serie_constante_tem_zero_gaps(self) -> None:
        ts = pd.date_range(
            "2026-01-05", periods=5 * 60, freq="1min", tz="UTC"
        )
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "open": np.full(len(ts), 100.0),
                "high": np.full(len(ts), 100.0),
                "low": np.full(len(ts), 100.0),
                "close": np.full(len(ts), 100.0),
                "volume": np.full(len(ts), 1.0),
            }
        )
        sumario = calcular_gaps(df)
        assert sumario.num_gaps_observados >= 0
        # Gaps todos zero → fracao_gaps_significativos = 0.
        assert sumario.fracao_gaps_significativos == 0.0


# ---------------------------------------------------------------------------
# Volatilidade intradia
# ---------------------------------------------------------------------------


class TestVolatilidadeIntradia:
    def test_devolve_uma_entrada_por_hora_observada(self) -> None:
        # 5 dias × 60 barras (1 por minuto, 1 hora por dia útil).
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=5, barras_por_dia=60)
        sumario = calcular_volatilidade_intradia(df)
        # Todas as 60 barras estão na mesma hora UTC (hora=0). Mas o
        # gerador adiciona dia + N min — vai cair em hora=0 sempre.
        assert isinstance(sumario, SumarioVolatilidadeIntradia)
        assert all(0 <= h <= 23 for h in sumario.volatilidade_por_hora_utc)
        assert all(v >= 0 for v in sumario.volatilidade_por_hora_utc.values())

    def test_pico_e_calmaria_sao_horas_validas(self) -> None:
        # Construímos artificialmente: 30 dias × 24 horas com vol diferente.
        # Para gerar std finito por hora, precisamos de ≥ 2 observações
        # de log-retorno por hora E variação real entre observações.
        timestamps = []
        closes = []
        rng = np.random.default_rng(7)
        for dia in range(30):
            for hora in range(24):
                t = pd.Timestamp("2026-01-05", tz="UTC") + pd.Timedelta(
                    days=dia, hours=hora
                )
                timestamps.append(t)
                # Hora 14 com vol 10x maior que o resto.
                escala = 0.01 if hora == 14 else 0.001
                closes.append(100.0 + rng.normal(0, escala) * 100.0)
        n = len(timestamps)
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": np.ones(n),
            }
        )
        sumario = calcular_volatilidade_intradia(df)
        # hora 14 deve ter std maior — é o pico.
        assert sumario.hora_pico == 14


# ---------------------------------------------------------------------------
# Fachada caracterizar_serie
# ---------------------------------------------------------------------------


class TestCaracterizarSerie:
    def test_devolve_relatorio_completo(self) -> None:
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=10)
        rel = caracterizar_serie(df, instrumento="MNQ")
        assert isinstance(rel, RelatorioCaracterizacao)
        assert rel.instrumento == "MNQ"
        assert rel.barras_analisadas == len(df)
        assert isinstance(rel.range_diario, SumarioRangeDiario)
        assert isinstance(rel.autocorrelacao, SumarioAutocorrelacao)
        assert isinstance(rel.gaps, SumarioGaps)
        assert isinstance(rel.volatilidade_intradia, SumarioVolatilidadeIntradia)

    def test_formatar_markdown_inclui_secoes(self) -> None:
        df = _serie_minute(datetime(2026, 1, 5, 0, 0), num_dias_uteis=10)
        md = caracterizar_serie(df).formatar_markdown()
        assert "# Caracterização" in md
        assert "## Range diário" in md
        assert "## Autocorrelação" in md
        assert "## Gaps" in md
        assert "## Volatilidade intradia" in md

    def test_dataframe_sem_schema_canonico_levanta(self) -> None:
        df = pd.DataFrame({"foo": [1, 2, 3]})
        with pytest.raises(ValueError):
            caracterizar_serie(df)


# ---------------------------------------------------------------------------
# Reexports
# ---------------------------------------------------------------------------


def test_reexports_pelo_pacote() -> None:
    from caos.walk_forward import (
        caracterizar_serie as REEXP,
        SumarioRangeDiario as REEXP_SRD,
    )

    assert REEXP is caracterizar_serie
    assert REEXP_SRD is SumarioRangeDiario
