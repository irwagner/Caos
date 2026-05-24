"""Testes unitários do plugin :class:`EstrategiaTurnOfMonth`.

Cobre o achado documentado no briefing tick-portfolio-microestrutura
(commit faea51c): calendar effect Turn-of-the-Month replicado em ES
futures por Carchano-Tornero (2011, SSRN 1958587). Único calendar
effect que sobreviveu ao rigor estatístico entre 188 testados.

Setup do paper:

- Long no fechamento do **5º último dia útil** do mês.
- Saída no fechamento do **3º dia útil** do mês seguinte.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.turn_of_month import (
    DIAS_ANTES_FIM_MES_DEFAULT,
    DIAS_DEPOIS_INICIO_MES_DEFAULT,
    EstrategiaTurnOfMonth,
    ParametrosTurnOfMonth,
    _calcular_dias_uteis_do_mes,
    _gerar_pares_entrada_saida,
    _proximo_mes,
)
from caos.walk_forward.models import ConfiguracaoWalkForward, JanelaWF
from caos.walk_forward.runner import BacktestRunner, BarrasTesteIterator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serie_minute_simples(
    inicio: date,
    num_dias_uteis: int,
    barras_por_dia: int = 4,
    base_close: float = 100.0,
) -> pd.DataFrame:
    """Série determinística +0.1/barra para auditoria de PnL."""
    timestamps = []
    closes: List[float] = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contador = 0
    while contador < num_dias_uteis * barras_por_dia:
        if dia.weekday() < 5:
            for h in range(barras_por_dia):
                timestamps.append(dia + pd.Timedelta(hours=h))
                closes.append(base_close + 0.1 * contador)
                contador += 1
        dia = dia + pd.Timedelta(days=1)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes_arr,
            "high": closes_arr + 0.05,
            "low": closes_arr - 0.05,
            "close": closes_arr,
            "volume": np.ones(len(timestamps)),
        }
    )


def _executar_plugin(
    plugin: EstrategiaTurnOfMonth,
    df: pd.DataFrame,
) -> List:
    plugin.treinar(df.copy())
    iterator = BarrasTesteIterator(df)
    for barra in iterator:
        plugin.on_barra(barra, iterator)
    return list(plugin.finalizar())


# ---------------------------------------------------------------------------
# ParametrosTurnOfMonth
# ---------------------------------------------------------------------------


class TestParametros:
    def test_defaults_paper(self) -> None:
        p = ParametrosTurnOfMonth()
        assert p.dias_antes_fim_mes == DIAS_ANTES_FIM_MES_DEFAULT == 5
        assert p.dias_depois_inicio_mes == DIAS_DEPOIS_INICIO_MES_DEFAULT == 3

    def test_dias_antes_fim_mes_fora_de_range(self) -> None:
        with pytest.raises(ValueError, match="dias_antes_fim_mes"):
            ParametrosTurnOfMonth(dias_antes_fim_mes=0)
        with pytest.raises(ValueError, match="dias_antes_fim_mes"):
            ParametrosTurnOfMonth(dias_antes_fim_mes=11)

    def test_dias_depois_inicio_mes_fora_de_range(self) -> None:
        with pytest.raises(ValueError, match="dias_depois_inicio_mes"):
            ParametrosTurnOfMonth(dias_depois_inicio_mes=0)
        with pytest.raises(ValueError, match="dias_depois_inicio_mes"):
            ParametrosTurnOfMonth(dias_depois_inicio_mes=11)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


class TestProximoMes:
    @pytest.mark.parametrize(
        "atual, esperado",
        [
            ((2025, 1), (2025, 2)),
            ((2025, 11), (2025, 12)),
            ((2025, 12), (2026, 1)),
            ((2024, 2), (2024, 3)),
        ],
    )
    def test_casos(self, atual: tuple, esperado: tuple) -> None:
        assert _proximo_mes(atual) == esperado


class TestCalcularDiasUteisDoMes:
    def test_agrupa_por_ano_mes(self) -> None:
        dias = [
            date(2025, 3, 31),
            date(2025, 4, 1),
            date(2025, 4, 2),
            date(2025, 4, 30),
        ]
        grupos = _calcular_dias_uteis_do_mes(dias)
        assert (2025, 3) in grupos
        assert (2025, 4) in grupos
        assert grupos[(2025, 3)] == [date(2025, 3, 31)]
        assert grupos[(2025, 4)] == [date(2025, 4, 1), date(2025, 4, 2), date(2025, 4, 30)]

    def test_ordena_dentro_do_mes(self) -> None:
        dias = [date(2025, 3, 5), date(2025, 3, 1), date(2025, 3, 3)]
        grupos = _calcular_dias_uteis_do_mes(dias)
        assert grupos[(2025, 3)] == [date(2025, 3, 1), date(2025, 3, 3), date(2025, 3, 5)]


class TestGerarParesEntradaSaida:
    def test_caso_canonico_5_3(self) -> None:
        # Mar/25: 21 dias úteis. Abr/25: 22 dias úteis. Setup default: 5/3.
        # Entrada = 5º último dia útil de mar/25.
        # Saída   = 3º dia útil de abr/25.
        dias = self._dias_uteis_de_periodo(date(2025, 3, 1), date(2025, 4, 30))
        pares = _gerar_pares_entrada_saida(dias, 5, 3)
        assert len(pares) == 1  # apenas mar→abr (abr não tem mês seguinte completo)
        d_entrada, d_saida = pares[0]
        # Mar/25 dias úteis ordenados: ..., 25, 26, 27, 28, 31. 5º último = 25.
        assert d_entrada == date(2025, 3, 25)
        # Abr/25 dias úteis: 1, 2, 3, .... 3º = 3.
        assert d_saida == date(2025, 4, 3)

    def test_meses_nao_consecutivos_pulados(self) -> None:
        # Tem mar/25 e mai/25 (sem abr/25) — não deve gerar par.
        dias_mar = self._dias_uteis_de_periodo(date(2025, 3, 1), date(2025, 3, 31))
        dias_mai = self._dias_uteis_de_periodo(date(2025, 5, 1), date(2025, 5, 31))
        pares = _gerar_pares_entrada_saida(dias_mar + dias_mai, 5, 3)
        assert pares == []

    def test_mes_com_poucos_dias_pulado(self) -> None:
        # Mês "atual" com só 3 dias úteis e o setup pede 5 — pula.
        dias = [date(2025, 3, 28), date(2025, 3, 29), date(2025, 3, 31)]
        # Adiciona abril completo para garantir que a falha é só no mar.
        dias += self._dias_uteis_de_periodo(date(2025, 4, 1), date(2025, 4, 30))
        pares = _gerar_pares_entrada_saida(dias, 5, 3)
        assert pares == []

    def test_mes_seguinte_curto(self) -> None:
        # Set/25 completo, out/25 com só 2 dias — pula porque setup pede 3.
        dias = self._dias_uteis_de_periodo(date(2025, 9, 1), date(2025, 9, 30))
        dias += [date(2025, 10, 1), date(2025, 10, 2)]
        pares = _gerar_pares_entrada_saida(dias, 5, 3)
        assert pares == []

    def test_multiplos_meses_consecutivos(self) -> None:
        dias = self._dias_uteis_de_periodo(date(2025, 1, 1), date(2025, 6, 30))
        pares = _gerar_pares_entrada_saida(dias, 5, 3)
        # Espera 5 pares: jan→fev, fev→mar, mar→abr, abr→mai, mai→jun.
        assert len(pares) == 5

    def test_dia_de_fim_de_semana_excluido(self) -> None:
        # Garante que sábado/domingo não entram no dias_uteis.
        dias = self._dias_uteis_de_periodo(date(2025, 3, 1), date(2025, 3, 31))
        for d in dias:
            assert d.weekday() < 5

    @staticmethod
    def _dias_uteis_de_periodo(inicio: date, fim: date) -> List[date]:
        """Lista dias úteis (seg-sex) entre inicio e fim inclusive."""
        atual = pd.Timestamp(inicio)
        out: List[date] = []
        while atual.date() <= fim:
            if atual.weekday() < 5:
                out.append(atual.date())
            atual += pd.Timedelta(days=1)
        return out


# ---------------------------------------------------------------------------
# Plugin — emissão de trades
# ---------------------------------------------------------------------------


class TestPluginExecucao:
    def test_serie_curta_dispara_entrada_mas_fechamento_residual(self) -> None:
        # 3 dias úteis num único mês (24, 25, 26 mar/25). Com projeção
        # de calendário à frente, a estratégia AGENDA entrada em 25/3
        # (5º último dia útil de mar). A saida programada seria em 3/4,
        # mas a série termina em 26/3 — finalizar() fecha pelo último
        # close visto. Expectativa: 1 trade residual.
        plugin = EstrategiaTurnOfMonth()
        df = _serie_minute_simples(date(2025, 3, 24), num_dias_uteis=3)
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 1
        assert trades[0].lado == "long"

    def test_emite_trade_long_no_padrao_canonico(self) -> None:
        # Cobre mar/25 → abr/25. Default setup 5/3 → entrada em 25/mar,
        # saida em 03/abr.
        plugin = EstrategiaTurnOfMonth()
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17),
            num_dias_uteis=20,  # ~mar/17 a abr/11
            barras_por_dia=2,
        )
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 1
        t = trades[0]
        assert t.lado == "long"
        # PnL deve ser positivo (série crescente +0.1/barra).
        assert t.pnl_pontos() > 0

    def test_dois_meses_geram_dois_trades(self) -> None:
        # Cobre fev → mar → abr para ter 2 pares.
        plugin = EstrategiaTurnOfMonth()
        # ~50 dias úteis cobrem fev, mar, abr (assumindo ~21 dias/mês).
        df = _serie_minute_simples(
            inicio=date(2025, 2, 3),
            num_dias_uteis=55,
            barras_por_dia=2,
        )
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 2

    def test_periodo_fora_padrao_sem_trades(self) -> None:
        # Janela cobre apenas meio-de-mês de um único mês.
        plugin = EstrategiaTurnOfMonth()
        df = _serie_minute_simples(
            inicio=date(2025, 3, 10),
            num_dias_uteis=6,
        )
        trades = _executar_plugin(plugin, df)
        assert trades == []

    def test_reset_entre_janelas(self) -> None:
        plugin = EstrategiaTurnOfMonth()
        df1 = _serie_minute_simples(date(2025, 3, 17), num_dias_uteis=20, barras_por_dia=2)
        t1 = _executar_plugin(plugin, df1)
        assert len(t1) == 1
        # Reset via treinar.
        df2 = _serie_minute_simples(date(2025, 7, 1), num_dias_uteis=5)
        plugin.treinar(df2.copy())
        assert plugin.trades == ()


# ---------------------------------------------------------------------------
# Smoke: aderência ao Protocol Estrategia + integração com BacktestRunner
# ---------------------------------------------------------------------------


class TestProtocolo:
    def test_metodos_obrigatorios(self) -> None:
        plugin = EstrategiaTurnOfMonth()
        assert callable(getattr(plugin, "on_barra", None))
        assert callable(getattr(plugin, "finalizar", None))
        assert callable(getattr(plugin, "treinar", None))
        assert plugin.NOME == "EstrategiaTurnOfMonth"

    def test_integracao_com_backtest_runner(self) -> None:
        plugin = EstrategiaTurnOfMonth()
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17),
            num_dias_uteis=20,
            barras_por_dia=2,
        )
        treino_inicio = datetime(2025, 1, 1, tzinfo=timezone.utc)
        treino_fim = datetime(2025, 3, 17, tzinfo=timezone.utc)
        teste_inicio = datetime(2025, 3, 17, tzinfo=timezone.utc)
        teste_fim = datetime(2025, 5, 1, tzinfo=timezone.utc)
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
            tamanho_teste_dias_uteis=30,
            granularidade="1m",
        )
        resultado = BacktestRunner.executar(
            janela=janela,
            dados=df,
            estrategia=plugin,
            configuracao=cfg,
        )
        assert resultado.status in ("ok", "sem-trades")
        # Esperamos ao menos 1 trade.
        assert resultado.numero_trades >= 1
