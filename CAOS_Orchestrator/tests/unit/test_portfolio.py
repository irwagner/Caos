"""Testes do EstrategiaPortfolio meta-estrategia."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.portfolio import EstrategiaPortfolio
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


class _MockEstrategia:
    """Mock que emite trades determinisicos baseados em uma lista."""

    def __init__(self, nome: str, trades_para_emitir: List[Trade]) -> None:
        self.NOME = nome
        self.trades_para_emitir = trades_para_emitir
        self.barras_recebidas = 0
        self.foi_treinado = False

    def treinar(self, historico: pd.DataFrame) -> None:
        self.foi_treinado = True

    def on_barra(self, barra, contexto) -> None:
        self.barras_recebidas += 1

    def finalizar(self):
        return self.trades_para_emitir


def _trade(entrada_str: str, saida_str: str, lado: str = "long",
           preco_entrada: float = 100.0, preco_saida: float = 101.0) -> Trade:
    return Trade(
        entrada_timestamp=entrada_str,
        saida_timestamp=saida_str,
        entrada_preco=preco_entrada,
        saida_preco=preco_saida,
        lado=lado,
        contratos=1,
        mfe_pontos=1.5,
        mae_pontos=-0.5,
    )


def _gerar_serie_minute(num_barras: int) -> pd.DataFrame:
    timestamps = pd.date_range(
        start="2025-03-17T14:30:00Z", periods=num_barras, freq="1min", tz="UTC"
    )
    arr = np.linspace(20000.0, 20010.0, num_barras)
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": arr, "high": arr + 0.25, "low": arr - 0.25, "close": arr,
        "volume": np.ones(num_barras),
    })


class TestProtocoloEConstrucao:
    def test_nome_padrao(self) -> None:
        m = _MockEstrategia("a", [])
        p = EstrategiaPortfolio([m])
        assert p.NOME == "EstrategiaPortfolio"

    def test_nome_customizado(self) -> None:
        m = _MockEstrategia("a", [])
        p = EstrategiaPortfolio([m], nome="Portfolio_PreFOMC_NR7")
        assert p.NOME == "Portfolio_PreFOMC_NR7"

    def test_componentes_vazios_levanta(self) -> None:
        with pytest.raises(ValueError, match="precisa"):
            EstrategiaPortfolio([])

    def test_componente_invalido_levanta(self) -> None:
        class Bad:
            pass
        with pytest.raises(TypeError, match="on_barra"):
            EstrategiaPortfolio([Bad()])


class TestTreinar:
    def test_repassa_para_todos_componentes(self) -> None:
        m1 = _MockEstrategia("a", [])
        m2 = _MockEstrategia("b", [])
        p = EstrategiaPortfolio([m1, m2])
        df = _gerar_serie_minute(10)
        p.treinar(df)
        assert m1.foi_treinado is True
        assert m2.foi_treinado is True


class TestOnBarra:
    def test_repassa_barra_para_todos(self) -> None:
        m1 = _MockEstrategia("a", [])
        m2 = _MockEstrategia("b", [])
        p = EstrategiaPortfolio([m1, m2])
        df = _gerar_serie_minute(10)
        p.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            p.on_barra(barra, iterator)
        assert m1.barras_recebidas == 10
        assert m2.barras_recebidas == 10


class TestFinalizar:
    def test_concatena_trades(self) -> None:
        t1 = _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z")
        t2 = _trade("2025-03-17T14:40:00Z", "2025-03-17T14:45:00Z")
        m1 = _MockEstrategia("a", [t1])
        m2 = _MockEstrategia("b", [t2])
        p = EstrategiaPortfolio([m1, m2])
        df = _gerar_serie_minute(10)
        p.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            p.on_barra(barra, iterator)
        trades = list(p.finalizar())
        assert len(trades) == 2

    def test_ordena_por_entrada(self) -> None:
        # Componentes emitem trades em ordem inversa cronologicamente.
        t_tarde = _trade("2025-03-17T14:40:00Z", "2025-03-17T14:45:00Z")
        t_cedo = _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z")
        m1 = _MockEstrategia("componente_tarde", [t_tarde])
        m2 = _MockEstrategia("componente_cedo", [t_cedo])
        p = EstrategiaPortfolio([m1, m2])
        df = _gerar_serie_minute(20)
        p.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            p.on_barra(barra, iterator)
        trades = list(p.finalizar())
        # Apos ordenacao, t_cedo vem primeiro mesmo que m1 emita primeiro.
        assert trades[0].entrada_timestamp < trades[1].entrada_timestamp

    def test_estatistica_num_trades_por_componente(self) -> None:
        t1 = _trade("2025-03-17T14:30:00Z", "2025-03-17T14:35:00Z")
        t2 = _trade("2025-03-17T14:40:00Z", "2025-03-17T14:45:00Z")
        m1 = _MockEstrategia("a", [t1, t2])
        m2 = _MockEstrategia("b", [])
        p = EstrategiaPortfolio([m1, m2])
        df = _gerar_serie_minute(10)
        p.treinar(df)
        iterator = BarrasTesteIterator(df)
        for barra in iterator:
            p.on_barra(barra, iterator)
        list(p.finalizar())
        stats = p.num_trades_por_componente
        assert stats["a"] == 2
        assert stats["b"] == 0


class TestIntegracaoBacktestRunner:
    def test_funciona_com_runner(self) -> None:
        from caos.walk_forward.models import (
            ConfiguracaoWalkForward, JanelaWF
        )
        from caos.walk_forward.runner import BacktestRunner

        t1 = _trade("2025-03-17T14:35:00Z", "2025-03-17T14:36:00Z")
        m1 = _MockEstrategia("a", [t1])
        m2 = _MockEstrategia("b", [])
        p = EstrategiaPortfolio([m1, m2])

        df = _gerar_serie_minute(60)
        janela = JanelaWF(
            indice=0,
            treino_inicio=datetime(2025, 1, 1, tzinfo=timezone.utc),
            treino_fim=datetime(2025, 3, 17, 14, 30, tzinfo=timezone.utc),
            teste_inicio=datetime(2025, 3, 17, 14, 30, tzinfo=timezone.utc),
            teste_fim=datetime(2025, 3, 17, 16, 0, tzinfo=timezone.utc),
            hash_dados="0" * 64,
        )
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
        )
        resultado = BacktestRunner.executar(
            janela=janela, dados=df, estrategia=p, configuracao=cfg
        )
        assert resultado.status in ("ok", "sem-trades")
        assert resultado.numero_trades == 1
