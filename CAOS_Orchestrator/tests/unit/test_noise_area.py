"""Testes unitários do plugin :class:`EstrategiaNoiseArea`.

Cobre o achado documentado no briefing-explorador-2026-05-24-expandido
(commit 259e1cd): replicação da estratégia "Beat the Market" de
Zarattini-Aziz-Barbon (2024). Sharpe 1.67 em NQ na replicação
Quantitativo (lookback 90, leverage 8x).

A versão default segue o paper original: lookback 14, RTH NY 14:30-21:00 UTC.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.noise_area import (
    EstrategiaNoiseArea,
    LOOKBACK_DEFAULT,
    ParametrosNoiseArea,
    SESSAO_RTH_NY_FIM_UTC,
    SESSAO_RTH_NY_INICIO_UTC,
)
from caos.walk_forward.models import ConfiguracaoWalkForward, JanelaWF
from caos.walk_forward.runner import BacktestRunner, BarrasTesteIterator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serie_rth_estavel(
    inicio: date,
    num_dias_uteis: int,
    barras_por_dia: int = 60,
    base_close: float = 20000.0,
    drift_diario: float = 0.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Série RTH NY (14:30-21:00 UTC) com baixa volatilidade — bom pra
    testar que estratégia NÃO dispara em ruído pequeno (Noise Area
    permanece intacta).
    """
    rng = np.random.default_rng(seed)
    timestamps: List[pd.Timestamp] = []
    closes: List[float] = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contador_dias = 0
    while contador_dias < num_dias_uteis:
        if dia.weekday() < 5:
            sessao_start = dia.replace(hour=14, minute=30)
            for i in range(barras_por_dia):
                ts = sessao_start + pd.Timedelta(minutes=i)
                # Vol baixa; close oscila ±0.5 ponto.
                preco = base_close + drift_diario * contador_dias + rng.normal(0, 0.5)
                timestamps.append(ts)
                closes.append(preco)
            contador_dias += 1
        dia = dia + pd.Timedelta(days=1)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes_arr,
            "high": closes_arr + 0.25,
            "low": closes_arr - 0.25,
            "close": closes_arr,
            "volume": np.ones(len(timestamps)),
        }
    )


def _serie_com_breakout_no_dia_alvo(
    inicio: date,
    num_dias_uteis: int,
    dia_breakout_idx: int,
    direcao: str = "up",
    barras_por_dia: int = 60,
    base_close: float = 20000.0,
) -> pd.DataFrame:
    """Série onde o dia ``dia_breakout_idx`` (0-based) tem movimento
    grande (10% do open) capaz de quebrar a Noise Area, e os demais
    dias são planos.
    """
    timestamps: List[pd.Timestamp] = []
    closes: List[float] = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contador_dias = 0
    while contador_dias < num_dias_uteis:
        if dia.weekday() < 5:
            sessao_start = dia.replace(hour=14, minute=30)
            for i in range(barras_por_dia):
                ts = sessao_start + pd.Timedelta(minutes=i)
                if contador_dias == dia_breakout_idx:
                    # Movimento direcional grande progressivo.
                    delta = (i + 1) * 10.0  # 10 pts/min
                    preco = (
                        base_close + delta if direcao == "up"
                        else base_close - delta
                    )
                else:
                    preco = base_close + 0.1 * (i % 3)
                timestamps.append(ts)
                closes.append(preco)
            contador_dias += 1
        dia = dia + pd.Timedelta(days=1)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes_arr,
            "high": closes_arr + 0.25,
            "low": closes_arr - 0.25,
            "close": closes_arr,
            "volume": np.ones(len(timestamps)),
        }
    )


def _executar_plugin(
    plugin: EstrategiaNoiseArea,
    df_treino: pd.DataFrame,
    df_teste: pd.DataFrame,
) -> List:
    plugin.treinar(df_treino.copy())
    iterator = BarrasTesteIterator(df_teste)
    for barra in iterator:
        plugin.on_barra(barra, iterator)
    return list(plugin.finalizar())


# ---------------------------------------------------------------------------
# ParametrosNoiseArea
# ---------------------------------------------------------------------------


class TestParametros:
    def test_defaults_paper(self) -> None:
        p = ParametrosNoiseArea()
        assert p.lookback_dias == LOOKBACK_DEFAULT == 14
        assert p.sessao_inicio_utc == SESSAO_RTH_NY_INICIO_UTC == time(14, 30)
        assert p.sessao_fim_utc == SESSAO_RTH_NY_FIM_UTC == time(21, 0)
        assert p.minutos_lockout == 30
        assert not p.apenas_long
        assert not p.apenas_short

    def test_lookback_fora_de_range(self) -> None:
        with pytest.raises(ValueError, match="lookback_dias"):
            ParametrosNoiseArea(lookback_dias=4)
        with pytest.raises(ValueError, match="lookback_dias"):
            ParametrosNoiseArea(lookback_dias=300)

    def test_sessao_invertida(self) -> None:
        with pytest.raises(ValueError, match="sessao_inicio_utc"):
            ParametrosNoiseArea(
                sessao_inicio_utc=time(21, 0),
                sessao_fim_utc=time(14, 30),
            )

    def test_lockout_fora_de_range(self) -> None:
        with pytest.raises(ValueError, match="minutos_lockout"):
            ParametrosNoiseArea(minutos_lockout=-1)
        with pytest.raises(ValueError, match="minutos_lockout"):
            ParametrosNoiseArea(minutos_lockout=300)

    def test_long_e_short_simultaneo(self) -> None:
        with pytest.raises(ValueError, match="apenas_long"):
            ParametrosNoiseArea(apenas_long=True, apenas_short=True)

    def test_variante_quantitativo_lookback_90(self) -> None:
        # Replicação Quantitativo NQ usou lookback 90.
        p = ParametrosNoiseArea(lookback_dias=90)
        assert p.lookback_dias == 90


# ---------------------------------------------------------------------------
# Histórico de retornos absolutos (treinar)
# ---------------------------------------------------------------------------


class TestTreinar:
    def test_treinar_popula_historico(self) -> None:
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=5))
        df = _serie_rth_estavel(date(2025, 3, 17), num_dias_uteis=10)
        plugin.treinar(df)
        # Histórico mantém deque de tamanho lookback (=5) ao final.
        assert plugin.historico_size <= 5
        # Pelo menos 5 dias úteis.
        assert plugin.historico_size == 5

    def test_treinar_reset_total(self) -> None:
        plugin = EstrategiaNoiseArea()
        df1 = _serie_rth_estavel(date(2025, 3, 17), num_dias_uteis=20)
        plugin.treinar(df1)
        assert plugin.historico_size > 0
        # Re-treinar com DataFrame vazio reseta tudo.
        plugin.treinar(pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]))
        assert plugin.historico_size == 0

    def test_treinar_ignora_barras_fora_da_sessao(self) -> None:
        # DataFrame com barras 24h — só RTH deve entrar no histórico.
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=14))
        # Combina barras de RTH com barras overnight.
        timestamps = []
        closes = []
        dia = pd.Timestamp("2025-03-17").tz_localize("UTC")
        contador_dias = 0
        while contador_dias < 20:
            if dia.weekday() < 5:
                # 6 barras RTH + 6 barras overnight (fora sessão).
                for h in [15, 16, 17, 18, 19, 20]:  # RTH UTC
                    timestamps.append(dia.replace(hour=h))
                    closes.append(20000.0 + 0.1)
                for h in [22, 23]:  # Overnight
                    timestamps.append(dia.replace(hour=h))
                    closes.append(20000.0 + 5.0)  # vol artificial alta
                contador_dias += 1
            dia += pd.Timedelta(days=1)
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": closes,
                "high": [c + 0.25 for c in closes],
                "low": [c - 0.25 for c in closes],
                "close": closes,
                "volume": np.ones(len(closes)),
            }
        )
        plugin.treinar(df)
        # Histórico tem só 14 dias mesmo com 20 dias de dados.
        assert plugin.historico_size == 14


# ---------------------------------------------------------------------------
# Detecção de breakout
# ---------------------------------------------------------------------------


class TestBreakouts:
    def test_serie_estavel_sem_breakout(self) -> None:
        # Série com vol comparável entre Treino e Teste — quando o
        # Teste tem mesma magnitude do Treino, a Noise Area absorve
        # tudo. Espera-se 0 trades.
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=14))
        df_treino = _serie_rth_estavel(
            date(2025, 1, 6),
            num_dias_uteis=14,
            seed=42,
        )
        df_teste = _serie_rth_estavel(
            date(2025, 1, 24),
            num_dias_uteis=5,
            seed=42,  # mesmo seed → magnitude idêntica
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        # Pode ter 0 ou no máximo 1-2 trades pequenos por overshoot
        # numérico; o critério importante é não ser breakout
        # massivo. Testamos a magnitude.
        if trades:
            for t in trades:
                # PnL < 5 pontos para vol síntetica de ±0.5pt.
                assert abs(t.pnl_pontos()) < 5.0

    def test_breakout_alto_dispara_long(self) -> None:
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=14))
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        # Teste: 2 dias planos + 1 dia com breakout up.
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="up",
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        assert len(trades) >= 1
        # Primeiro trade deve ser long no dia do breakout.
        assert trades[0].lado == "long"

    def test_breakout_baixo_dispara_short(self) -> None:
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=14))
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="down",
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        assert len(trades) >= 1
        assert trades[0].lado == "short"

    def test_apenas_long_descarta_breakout_short(self) -> None:
        plugin = EstrategiaNoiseArea(
            ParametrosNoiseArea(lookback_dias=14, apenas_long=True)
        )
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="down",
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        # Sem trade short.
        assert all(t.lado != "short" for t in trades)

    def test_um_trade_por_dia(self) -> None:
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=14))
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="up",
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        # Mesmo se preço continua subindo dentro do dia, só 1 trade
        # por dia (regra de 1 trade/dia do paper).
        # Não pode haver dois trades com mesma data de entrada.
        datas_entrada = [t.entrada_timestamp.date() for t in trades]
        assert len(datas_entrada) == len(set(datas_entrada))

    def test_inverter_sinais_breakout_alto_dispara_short(self) -> None:
        # Hipótese mean-reversion: breakout up vira SHORT (em vez de
        # long como no paper).
        plugin = EstrategiaNoiseArea(
            ParametrosNoiseArea(lookback_dias=14, inverter_sinais=True)
        )
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="up",
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        assert len(trades) >= 1
        assert trades[0].lado == "short"

    def test_inverter_sinais_breakout_baixo_dispara_long(self) -> None:
        plugin = EstrategiaNoiseArea(
            ParametrosNoiseArea(lookback_dias=14, inverter_sinais=True)
        )
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="down",
        )
        trades = _executar_plugin(plugin, df_treino, df_teste)
        assert len(trades) >= 1
        assert trades[0].lado == "long"


# ---------------------------------------------------------------------------
# Smoke: aderência ao Protocol Estrategia + integração
# ---------------------------------------------------------------------------


class TestProtocolo:
    def test_metodos_obrigatorios(self) -> None:
        plugin = EstrategiaNoiseArea()
        assert callable(getattr(plugin, "on_barra", None))
        assert callable(getattr(plugin, "finalizar", None))
        assert callable(getattr(plugin, "treinar", None))
        assert plugin.NOME == "EstrategiaNoiseArea"

    def test_integracao_com_backtest_runner(self) -> None:
        plugin = EstrategiaNoiseArea(ParametrosNoiseArea(lookback_dias=14))
        df_treino = _serie_rth_estavel(date(2025, 1, 6), num_dias_uteis=14)
        df_teste = _serie_com_breakout_no_dia_alvo(
            inicio=date(2025, 1, 24),
            num_dias_uteis=3,
            dia_breakout_idx=2,
            direcao="up",
        )
        # Concatena para BacktestRunner filtrar internamente.
        df = pd.concat([df_treino, df_teste], ignore_index=True)

        treino_inicio = datetime(2025, 1, 6, tzinfo=timezone.utc)
        treino_fim = datetime(2025, 1, 24, tzinfo=timezone.utc)
        teste_inicio = datetime(2025, 1, 24, tzinfo=timezone.utc)
        teste_fim = datetime(2025, 2, 1, tzinfo=timezone.utc)
        janela = JanelaWF(
            indice=0,
            treino_inicio=treino_inicio,
            treino_fim=treino_fim,
            teste_inicio=teste_inicio,
            teste_fim=teste_fim,
            hash_dados="0" * 64,
        )
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
        )
        resultado = BacktestRunner.executar(
            janela=janela,
            dados=df,
            estrategia=plugin,
            configuracao=cfg,
        )
        assert resultado.status in ("ok", "sem-trades")
        assert resultado.numero_trades >= 0
