"""Testes unitários do plugin :class:`EstrategiaPreFomcDrift`.

Cobre o achado documentado no briefing do Explorador (commit c1b2bc6):
implementação fiel da estratégia long-flat de Lucca-Moench (2015) sem
parâmetros otimizáveis.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.pre_fomc import (
    EstrategiaPreFomcDrift,
    JanelaFomc,
    _dia_util_anterior,
    carregar_meetings_fomc,
)
from caos.walk_forward.runner import BarrasTesteIterator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _criar_csv_fomc(tmp_path: Path, datas: list[str]) -> Path:
    csv_path = tmp_path / "fomc.csv"
    linhas = ["data_anuncio,duracao_dias,tem_press_conference,fonte"]
    for d in datas:
        linhas.append(f"{d},2,true,unit-test")
    csv_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return csv_path


def _serie_minute_simples(
    inicio: date,
    num_dias_uteis: int,
    barras_por_dia: int = 4,
    base_close: float = 100.0,
) -> pd.DataFrame:
    """DataFrame canônico: N dias úteis com poucas barras por dia.

    Preço progride deterministicamente +0.1/barra para ficar fácil
    auditar PnL nos testes.
    """
    timestamps = []
    closes = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contador = 0
    while contador < num_dias_uteis * barras_por_dia:
        if dia.weekday() < 5:
            for h in range(barras_por_dia):
                timestamps.append(dia + pd.Timedelta(hours=h))
                closes.append(base_close + 0.1 * contador)
                contador += 1
        dia = dia + pd.Timedelta(days=1)

    n = len(timestamps)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes_arr,
            "high": closes_arr + 0.05,
            "low": closes_arr - 0.05,
            "close": closes_arr,
            "volume": np.ones(n),
        }
    )


# ---------------------------------------------------------------------------
# carregar_meetings_fomc
# ---------------------------------------------------------------------------


class TestCarregarMeetingsFomc:
    def test_lista_basica(self, tmp_path: Path) -> None:
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19", "2025-05-07"])
        janelas = carregar_meetings_fomc(csv_path)
        assert len(janelas) == 2
        assert janelas[0].dia_anuncio == date(2025, 3, 19)
        # 2025-03-19 é quarta-feira, dia útil anterior é terça 2025-03-18.
        assert janelas[0].dia_antes == date(2025, 3, 18)

    def test_dia_anterior_pula_fim_de_semana(self, tmp_path: Path) -> None:
        # 2025-03-17 é segunda. Dia útil anterior deve ser sexta 2025-03-14.
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-17"])
        janelas = carregar_meetings_fomc(csv_path)
        assert janelas[0].dia_antes == date(2025, 3, 14)

    def test_arquivo_inexistente(self) -> None:
        with pytest.raises(FileNotFoundError):
            carregar_meetings_fomc(Path("/path/nao/existe.csv"))

    def test_csv_sem_coluna_obrigatoria(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "ruim.csv"
        csv_path.write_text("foo,bar\n1,2\n", encoding="utf-8")
        with pytest.raises(ValueError):
            carregar_meetings_fomc(csv_path)

    def test_data_invalida_levanta(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "ruim.csv"
        csv_path.write_text(
            "data_anuncio\n2025-13-99\n", encoding="utf-8"
        )
        with pytest.raises(ValueError):
            carregar_meetings_fomc(csv_path)

    def test_ordena_por_data(self, tmp_path: Path) -> None:
        csv_path = _criar_csv_fomc(
            tmp_path, ["2025-12-10", "2025-01-29", "2025-09-17"]
        )
        janelas = carregar_meetings_fomc(csv_path)
        datas = [j.dia_anuncio for j in janelas]
        assert datas == sorted(datas)


# ---------------------------------------------------------------------------
# _dia_util_anterior
# ---------------------------------------------------------------------------


class TestDiaUtilAnterior:
    @pytest.mark.parametrize(
        "data, esperado",
        [
            # Quarta -> terça
            (date(2025, 3, 19), date(2025, 3, 18)),
            # Segunda -> sexta
            (date(2025, 3, 17), date(2025, 3, 14)),
            # Domingo -> sexta
            (date(2025, 3, 16), date(2025, 3, 14)),
            # Sábado -> sexta
            (date(2025, 3, 15), date(2025, 3, 14)),
        ],
    )
    def test_casos_canonicos(self, data: date, esperado: date) -> None:
        assert _dia_util_anterior(data) == esperado


# ---------------------------------------------------------------------------
# Plugin — emissão de trades
# ---------------------------------------------------------------------------


def _executar_plugin(
    plugin: EstrategiaPreFomcDrift,
    df: pd.DataFrame,
) -> list:
    plugin.treinar(df.copy())
    iterator = BarrasTesteIterator(df)
    for barra in iterator:
        plugin.on_barra(barra, iterator)
    return list(plugin.finalizar())


class TestPlugin:
    def test_sem_meetings_no_periodo_nao_emite_trades(
        self, tmp_path: Path
    ) -> None:
        # Meeting em 2099 — fora da série gerada.
        csv_path = _criar_csv_fomc(tmp_path, ["2099-06-01"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17), num_dias_uteis=10
        )
        trades = _executar_plugin(plugin, df)
        assert trades == []

    def test_emite_um_trade_long_close_d_minus_1_para_close_d(
        self, tmp_path: Path
    ) -> None:
        # Meeting em 2025-03-19 (qua). Dia D-1 = 2025-03-18 (ter).
        # Geramos serie começando 2025-03-17 (seg) com 5 dias úteis.
        # Dia 1 (seg 17): closes 100.0..100.3
        # Dia 2 (ter 18): closes 100.4..100.7   <- ÚLTIMO close = entrada
        # Dia 3 (qua 19): closes 100.8..101.1   <- ÚLTIMO close = saída
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17),
            num_dias_uteis=5,
            barras_por_dia=4,
            base_close=100.0,
        )
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 1
        t = trades[0]
        assert t.lado == "long"
        # Entrada = último close do dia 2 (ter): contador=7 -> 100.7.
        assert t.entrada_preco == pytest.approx(100.7)
        # Saída = último close do dia 3 (qua): contador=11 -> 101.1.
        assert t.saida_preco == pytest.approx(101.1)
        assert t.contratos == 1
        # PnL = +0.4 pts (positivo nesta serie crescente).
        assert t.pnl_pontos() == pytest.approx(0.4)

    def test_dois_meetings_emitem_dois_trades(
        self, tmp_path: Path
    ) -> None:
        # Meetings 2025-03-19 (qua) e 2025-03-26 (qua) — dia D-1 não conflita.
        csv_path = _criar_csv_fomc(
            tmp_path, ["2025-03-19", "2025-03-26"]
        )
        plugin = EstrategiaPreFomcDrift(csv_path)
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17),
            num_dias_uteis=10,
            barras_por_dia=4,
        )
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 2

    def test_meeting_fora_da_serie_descartado(
        self, tmp_path: Path
    ) -> None:
        # Meeting em 2025-03-19 mas serie começa só em 2025-03-20.
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        df = _serie_minute_simples(
            inicio=date(2025, 3, 20), num_dias_uteis=5
        )
        trades = _executar_plugin(plugin, df)
        assert trades == []

    def test_dia_anuncio_eh_ultimo_dia_da_serie(
        self, tmp_path: Path
    ) -> None:
        # Janela termina no próprio dia FOMC. A finalizacao deve fechar
        # a posicao com o ultimo close visto.
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        # Serie de seg/ter/qua só (3 dias úteis); meeting cai na qua.
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17),
            num_dias_uteis=3,
            barras_por_dia=4,
        )
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 1

    def test_reset_entre_janelas_via_treinar(
        self, tmp_path: Path
    ) -> None:
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        df1 = _serie_minute_simples(date(2025, 3, 17), num_dias_uteis=5)
        # Janela 1 emite 1 trade.
        t1 = _executar_plugin(plugin, df1)
        assert len(t1) == 1
        # Janela 2 — outro periodo, treinar deve resetar.
        df2 = _serie_minute_simples(date(2025, 4, 7), num_dias_uteis=5)
        plugin.treinar(df2.copy())
        assert plugin.trades == ()  # após reset, sem trades

    def test_granularidade_day(self, tmp_path: Path) -> None:
        # 1 barra/dia ainda funciona. Meeting 2025-03-19, serie de 5 dias
        # uteis comecando 2025-03-17.
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        df = _serie_minute_simples(
            inicio=date(2025, 3, 17),
            num_dias_uteis=5,
            barras_por_dia=1,
        )
        trades = _executar_plugin(plugin, df)
        assert len(trades) == 1
        # Entrada = close do dia 2 (única barra): contador=1 → 100.1.
        # Saída   = close do dia 3 (única barra): contador=2 → 100.2.
        assert trades[0].entrada_preco == pytest.approx(100.1)
        assert trades[0].saida_preco == pytest.approx(100.2)


# ---------------------------------------------------------------------------
# Smoke: aderência ao Protocol Estrategia
# ---------------------------------------------------------------------------


class TestProtocoloEstrategia:
    def test_tem_metodos_obrigatorios(self, tmp_path: Path) -> None:
        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        assert callable(getattr(plugin, "on_barra", None))
        assert callable(getattr(plugin, "finalizar", None))
        assert callable(getattr(plugin, "treinar", None))
        assert plugin.NOME == "EstrategiaPreFomcDrift"

    def test_funciona_com_walk_forward_engine_estrutura_minima(
        self, tmp_path: Path
    ) -> None:
        # Smoke: rodar via BacktestRunner direto.
        from caos.walk_forward.models import (
            ConfiguracaoWalkForward,
            JanelaWF,
        )
        from caos.walk_forward.runner import BacktestRunner

        csv_path = _criar_csv_fomc(tmp_path, ["2025-03-19"])
        plugin = EstrategiaPreFomcDrift(csv_path)
        df = _serie_minute_simples(date(2025, 3, 17), num_dias_uteis=5)

        # JanelaWF cobrindo a serie.
        treino_inicio = datetime(2025, 3, 1, tzinfo=timezone.utc)
        treino_fim = datetime(2025, 3, 17, tzinfo=timezone.utc)
        teste_inicio = datetime(2025, 3, 17, tzinfo=timezone.utc)
        teste_fim = datetime(2025, 4, 1, tzinfo=timezone.utc)
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
        # No nosso caso ha 1 meeting → status "ok".
        assert resultado.numero_trades == 1
