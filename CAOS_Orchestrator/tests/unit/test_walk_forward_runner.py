"""Testes unitários do ``BacktestRunner`` (Spec 2 — Task 4).

Cobre **R5** do ``requirements.md`` do Spec 2 (isolamento Treino/Teste,
sem look-ahead).

Cenários cobertos:

- Estratégia válida com trades ⇒ ``ResultadoJanela.status == "ok"``.
- Estratégia válida sem trades ⇒ ``status == "sem-trades"``.
- Estratégia que tenta look-ahead via indexação positiva ⇒
  :class:`LookAheadException` capturada e propagada como
  ``status="falha"`` + ``look_ahead_violation=True`` (R5.3).
- Estratégia que tenta look-ahead via slice futuro ⇒ idem.
- Estratégia que lança exceção arbitrária ⇒ ``status="falha"``,
  ``motivo_falha`` preenchido (R10.1).
- Periodo_Teste vazio (``numero_trades == 0``) ⇒ ``status="sem-trades"``.
- :class:`BarrasTesteIterator` permite acesso a barras passadas e à
  barra atual; índices negativos referem-se à janela visível.
- Estratégia opcional sem ``treinar`` ainda funciona (Protocol mínimo).
- Reprodutibilidade básica: ``seed`` aplicada antes da iteração.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import pytest

from caos.walk_forward import (
    BacktestRunner,
    BarrasTesteIterator,
    ConfiguracaoWalkForward,
    JanelaWF,
    LookAheadException,
    ResultadoJanela,
    Trade,
)

UTC = timezone.utc
HASH_FAKE = "f" * 64


# ===========================================================================
# Fixtures e helpers
# ===========================================================================


def _config(seed: int = 42) -> ConfiguracaoWalkForward:
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        seed=seed,
    )


def _bdays(quantidade: int, inicio: str = "2024-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(inicio, periods=quantidade, tz="UTC")


def _df_canonico(timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1000.0] * n,
        }
    )


def _janela_padrao() -> tuple[JanelaWF, pd.DataFrame]:
    """Constrói (JanelaWF, DataFrame) válidos cobrindo Treino + Teste."""
    idx = _bdays(70)
    df = _df_canonico(idx)
    janela = JanelaWF(
        indice=0,
        treino_inicio=idx[0].to_pydatetime(),
        treino_fim=idx[60].to_pydatetime(),
        teste_inicio=idx[60].to_pydatetime(),
        teste_fim=(idx[-1] + pd.Timedelta(days=1)).to_pydatetime(),
        hash_dados=HASH_FAKE,
    )
    return janela, df


# ===========================================================================
# Estratégias de teste (stubs)
# ===========================================================================


class EstrategiaQueGeraTrade:
    """Estratégia que olha apenas a barra atual e emite 1 trade no fim."""

    NOME = "EstrategiaQueGeraTrade"

    def __init__(self) -> None:
        self.barras_vistas: list[pd.Timestamp] = []
        self.treinou: bool = False

    def treinar(self, historico: pd.DataFrame) -> None:
        self.treinou = True

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        self.barras_vistas.append(barra["timestamp"])
        # Sanidade: pode acessar a barra atual e barras passadas.
        if contexto.idx_atual >= 1:
            _ = contexto[contexto.idx_atual - 1]
        _ = contexto[contexto.idx_atual]

    def finalizar(self) -> list[Trade]:
        return [Trade(pnl=12.5, mfe=15.0, mae=-3.0)]


class EstrategiaSemTrades:
    """Estratégia válida que nunca emite trades."""

    NOME = "EstrategiaSemTrades"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        return None

    def finalizar(self) -> list[Trade]:
        return []


class EstrategiaQuePeekaFuturo:
    """Estratégia que tenta acessar uma barra futura via indexação positiva."""

    NOME = "EstrategiaQuePeekaFuturo"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        # Tenta acessar a barra do dia seguinte (look-ahead).
        _ = contexto[contexto.idx_atual + 1]

    def finalizar(self) -> list[Trade]:
        return []


class EstrategiaQuePeekaSlice:
    """Estratégia que tenta acessar slice contendo barras futuras."""

    NOME = "EstrategiaQuePeekaSlice"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        # Slice [0:idx_atual+5) viola o cursor.
        _ = contexto[0 : contexto.idx_atual + 5]

    def finalizar(self) -> list[Trade]:
        return []


class EstrategiaQueQuebra:
    """Estratégia que lança ValueError no meio do Teste (R10.1)."""

    NOME = "EstrategiaQueQuebra"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        if contexto.idx_atual == 2:
            raise ValueError("erro proposital de teste")

    def finalizar(self) -> list[Trade]:
        return []


class EstrategiaSemTreinar:
    """Estratégia que omite ``treinar`` — Protocol mínimo (R5)."""

    NOME = "EstrategiaSemTreinar"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        return None

    def finalizar(self) -> list[Trade]:
        return [Trade(pnl=1.0)]


# ===========================================================================
# BacktestRunner: caminhos felizes
# ===========================================================================


class TestExecucaoFeliz:
    """Estratégia válida sem violações."""

    def test_estrategia_com_trades_retorna_status_ok(self) -> None:
        janela, df = _janela_padrao()
        estrategia = EstrategiaQueGeraTrade()

        resultado = BacktestRunner.executar(janela, df, estrategia, _config())

        assert isinstance(resultado, ResultadoJanela)
        assert resultado.status == "ok"
        assert resultado.numero_trades == 1
        assert resultado.pnl_total == pytest.approx(12.5)
        assert resultado.look_ahead_violation is False
        assert resultado.motivo_falha is None
        assert resultado.estrategia == "EstrategiaQueGeraTrade"
        # Estratégia recebeu fase de Treino.
        assert estrategia.treinou is True
        # E viu exatamente as 10 barras do Teste em ordem cronológica.
        assert len(estrategia.barras_vistas) == 10
        assert estrategia.barras_vistas == sorted(estrategia.barras_vistas)

    def test_estrategia_sem_trades_retorna_sem_trades(self) -> None:
        janela, df = _janela_padrao()

        resultado = BacktestRunner.executar(
            janela, df, EstrategiaSemTrades(), _config()
        )

        assert resultado.status == "sem-trades"
        assert resultado.numero_trades == 0
        assert resultado.pnl_total == 0.0
        assert resultado.look_ahead_violation is False
        # R6.2 — métricas dependentes ficam None em sem-trades.
        assert resultado.sharpe_anualizado is None
        assert resultado.win_rate is None

    def test_estrategia_sem_metodo_treinar_funciona(self) -> None:
        janela, df = _janela_padrao()

        resultado = BacktestRunner.executar(
            janela, df, EstrategiaSemTreinar(), _config()
        )

        assert resultado.status == "ok"
        assert resultado.numero_trades == 1


# ===========================================================================
# BacktestRunner: detecção de look-ahead (R5.3)
# ===========================================================================


class TestLookAheadDetection:
    """Acesso a barras futuras é detectado e empacotado em status='falha'."""

    def test_indexacao_positiva_para_futuro_marca_falha(self) -> None:
        janela, df = _janela_padrao()

        resultado = BacktestRunner.executar(
            janela, df, EstrategiaQuePeekaFuturo(), _config()
        )

        assert resultado.status == "falha"
        assert resultado.look_ahead_violation is True
        assert resultado.motivo_falha is not None
        assert "look-ahead" in resultado.motivo_falha.lower()
        # PnL e número de trades zerados quando há falha.
        assert resultado.numero_trades == 0
        assert resultado.pnl_total == 0.0

    def test_slice_para_futuro_marca_falha(self) -> None:
        janela, df = _janela_padrao()

        resultado = BacktestRunner.executar(
            janela, df, EstrategiaQuePeekaSlice(), _config()
        )

        assert resultado.status == "falha"
        assert resultado.look_ahead_violation is True
        assert resultado.motivo_falha is not None
        assert "look-ahead" in resultado.motivo_falha.lower()


# ===========================================================================
# BacktestRunner: falhas não-look-ahead (R10.1)
# ===========================================================================


class TestFalhaArbitrariaPropagaComStatusFalha:
    def test_excecao_arbitraria_vira_status_falha(self) -> None:
        janela, df = _janela_padrao()

        resultado = BacktestRunner.executar(
            janela, df, EstrategiaQueQuebra(), _config()
        )

        assert resultado.status == "falha"
        assert resultado.look_ahead_violation is False
        assert resultado.motivo_falha is not None
        assert "ValueError" in resultado.motivo_falha
        assert "erro proposital" in resultado.motivo_falha


# ===========================================================================
# BacktestRunner: Periodo_Teste vazio
# ===========================================================================


class TestTesteVazio:
    """Quando o Teste não tem barras, status é 'sem-trades' (R6.2)."""

    def test_teste_vazio_retorna_sem_trades(self) -> None:
        # Constrói janela cujo Teste está fora do DataFrame.
        idx = _bdays(60)
        df = _df_canonico(idx)
        janela = JanelaWF(
            indice=0,
            treino_inicio=idx[0].to_pydatetime(),
            treino_fim=idx[59].to_pydatetime(),
            # Teste cai *após* o fim do DataFrame.
            teste_inicio=(idx[-1] + pd.Timedelta(days=1)).to_pydatetime(),
            teste_fim=(idx[-1] + pd.Timedelta(days=15)).to_pydatetime(),
            hash_dados=HASH_FAKE,
        )

        resultado = BacktestRunner.executar(
            janela, df, EstrategiaQueGeraTrade(), _config()
        )

        assert resultado.status == "sem-trades"
        assert resultado.numero_trades == 0
        assert resultado.pnl_total == 0.0


# ===========================================================================
# BarrasTesteIterator: comportamento isolado
# ===========================================================================


class TestBarrasTesteIterator:
    """Testes diretos do iterator anti-look-ahead."""

    def _iterator_com_n_barras(self, n: int) -> BarrasTesteIterator:
        return BarrasTesteIterator(_df_canonico(_bdays(n)))

    def test_iteracao_avanca_cursor_um_a_um(self) -> None:
        it = self._iterator_com_n_barras(5)
        assert it.idx_atual == -1
        avancos = []
        for barra in it:
            avancos.append(it.idx_atual)
        assert avancos == [0, 1, 2, 3, 4]

    def test_acesso_a_barra_atual_permitido(self) -> None:
        it = self._iterator_com_n_barras(3)
        next(iter(it))  # avança para idx 0
        # iter() acima reseta — refazer manualmente:
        it = self._iterator_com_n_barras(3)
        iter_obj = iter(it)
        next(iter_obj)
        assert it.idx_atual == 0
        # Acesso à barra atual é OK.
        _ = it[0]
        # Acesso à barra atual via barra_atual também.
        _ = it.barra_atual

    def test_acesso_a_barra_passada_permitido(self) -> None:
        it = self._iterator_com_n_barras(5)
        iter_obj = iter(it)
        next(iter_obj)
        next(iter_obj)
        next(iter_obj)
        assert it.idx_atual == 2
        # Acesso a 0, 1, 2 é OK.
        for i in (0, 1, 2):
            _ = it[i]

    def test_acesso_a_barra_futura_levanta_lookahead(self) -> None:
        it = self._iterator_com_n_barras(5)
        iter_obj = iter(it)
        next(iter_obj)  # idx_atual = 0
        with pytest.raises(LookAheadException) as exc_info:
            _ = it[1]
        assert exc_info.value.idx_atual == 0
        assert exc_info.value.idx_acessado == 1

    def test_indice_negativo_relativo_a_janela_visivel(self) -> None:
        it = self._iterator_com_n_barras(5)
        iter_obj = iter(it)
        next(iter_obj)
        next(iter_obj)
        next(iter_obj)
        assert it.idx_atual == 2
        # ``it[-1]`` é a barra atual (idx 2), ``it[-2]`` é a anterior.
        assert it[-1].equals(it[2])
        assert it[-3].equals(it[0])
        with pytest.raises(IndexError):
            _ = it[-4]

    def test_slice_ate_atual_permitido(self) -> None:
        it = self._iterator_com_n_barras(5)
        iter_obj = iter(it)
        for _ in range(3):
            next(iter_obj)
        # idx_atual = 2 ⇒ slice [0:3) tem 3 barras visíveis.
        recorte = it[0:3]
        assert len(recorte) == 3

    def test_slice_para_o_futuro_levanta_lookahead(self) -> None:
        it = self._iterator_com_n_barras(5)
        iter_obj = iter(it)
        next(iter_obj)  # idx_atual = 0
        with pytest.raises(LookAheadException):
            _ = it[0:5]

    def test_len_reflete_apenas_janela_visivel(self) -> None:
        it = self._iterator_com_n_barras(5)
        assert len(it) == 0
        iter_obj = iter(it)
        next(iter_obj)
        assert len(it) == 1
        next(iter_obj)
        assert len(it) == 2

    def test_barra_atual_antes_de_iterar_levanta_indexerror(self) -> None:
        it = self._iterator_com_n_barras(5)
        with pytest.raises(IndexError):
            _ = it.barra_atual

    def test_lookahead_exception_carrega_indices(self) -> None:
        exc = LookAheadException(idx_atual=3, idx_acessado=7)
        assert exc.idx_atual == 3
        assert exc.idx_acessado == 7
        assert "idx=7" in str(exc)
        assert "idx_atual=3" in str(exc)


# ===========================================================================
# Reprodutibilidade
# ===========================================================================


class TestReprodutibilidade:
    """Mesma seed + mesmos dados ⇒ mesmo resultado em campos relevantes."""

    def test_duas_execucoes_identicas_geram_mesmo_pnl_e_status(self) -> None:
        janela, df = _janela_padrao()
        cfg = _config(seed=123)

        r1 = BacktestRunner.executar(
            janela, df, EstrategiaQueGeraTrade(), cfg
        )
        r2 = BacktestRunner.executar(
            janela, df, EstrategiaQueGeraTrade(), cfg
        )

        assert r1.status == r2.status
        assert r1.numero_trades == r2.numero_trades
        assert r1.pnl_total == r2.pnl_total
        assert r1.look_ahead_violation == r2.look_ahead_violation
