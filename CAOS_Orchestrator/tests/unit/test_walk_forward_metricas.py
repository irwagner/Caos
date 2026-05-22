"""Testes unitários do ``MetricasCalculator`` (Spec 2 — Task 5).

Cobre **R6** do ``requirements.md`` do Spec 2.

Cenários cobertos:

- 0 trades ⇒ ``status="sem-trades"`` e métricas dependentes ``None`` (R6.2).
- 1 trade vencedor ⇒ ``status="ok"``, ``win_rate=1.0``, ``payoff=None``
  (sem perdedores), Sharpe ``None`` (< 2 dias).
- 1 trade perdedor ⇒ ``win_rate=0.0``, ``payoff=0.0`` (0 ganhos / 1 perda)
  ou ``payoff_medio == 0.0``, drawdown ≈ 1.0.
- Série só de wins ⇒ drawdown == 0, Calmar ``None``.
- Série só de losses ⇒ drawdown ≈ 1.0, Calmar finito e negativo.
- Série mista com Sharpe finito ⇒ Sharpe não-nulo e calculável.
- ``payoff_medio`` com 0 perdas devolve ``None``.
- Drawdown calculado corretamente em série conhecida (peak/trough/dias).
- Modelo :class:`Trade` exige UTC, ``saida_timestamp > entrada_timestamp``
  e ``contratos >= 1``.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from caos.walk_forward import (
    ConfiguracaoWalkForward,
    JanelaWF,
    MetricasCalculator,
    ResultadoJanela,
)
from caos.walk_forward.metricas import DIAS_UTEIS_POR_ANO, Trade

UTC = timezone.utc
HASH_FAKE = "f" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(treino: int = 60, teste: int = 10) -> ConfiguracaoWalkForward:
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=treino,
        tamanho_teste_dias_uteis=teste,
        granularidade="1m",
    )


def _janela() -> JanelaWF:
    treino_inicio = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)
    treino_fim = datetime(2024, 3, 27, 0, 0, tzinfo=UTC)
    teste_inicio = treino_fim
    teste_fim = datetime(2024, 4, 10, 0, 0, tzinfo=UTC)
    return JanelaWF(
        indice=0,
        treino_inicio=treino_inicio,
        treino_fim=treino_fim,
        teste_inicio=teste_inicio,
        teste_fim=teste_fim,
        hash_dados=HASH_FAKE,
    )


def _trade(
    *,
    dia: int,
    pnl: float,
    contratos: int = 1,
    lado: str = "long",
    mfe: float = 0.0,
    mae: float = 0.0,
    base_data: datetime = datetime(2024, 3, 27, 13, 30, tzinfo=UTC),
) -> Trade:
    """Cria um Trade que produz exatamente ``pnl`` pontos × contratos.

    O ``saida_timestamp`` é ``base_data + timedelta(days=dia)`` e a
    duração do trade é fixa em 1h. Para ``lado='long'``, ``saida_preco -
    entrada_preco = pnl/contratos``. Para ``lado='short'``, é o oposto.
    """
    entrada_ts = base_data + timedelta(days=dia)
    saida_ts = entrada_ts + timedelta(hours=1)
    delta = pnl / contratos
    if lado == "short":
        delta = -delta
    entrada_preco = 21000.0
    saida_preco = entrada_preco + delta
    return Trade(
        entrada_timestamp=entrada_ts,
        saida_timestamp=saida_ts,
        entrada_preco=entrada_preco,
        saida_preco=saida_preco,
        lado=lado,  # type: ignore[arg-type]
        contratos=contratos,
        mfe_pontos=mfe,
        mae_pontos=mae,
    )


# ===========================================================================
# Modelo Trade — validações básicas
# ===========================================================================


def test_trade_pnl_long():
    t = _trade(dia=0, pnl=10.0, lado="long")
    assert t.pnl_pontos() == pytest.approx(10.0)


def test_trade_pnl_short():
    t = _trade(dia=0, pnl=10.0, lado="short")
    assert t.pnl_pontos() == pytest.approx(10.0)


def test_trade_pnl_long_com_contratos():
    t = _trade(dia=0, pnl=20.0, contratos=2, lado="long")
    # delta = 20 / 2 = 10 ponto, * 2 contratos = 20 pontos × contratos.
    assert t.pnl_pontos() == pytest.approx(20.0)


def test_trade_rejeita_naive_datetime():
    with pytest.raises(ValidationError):
        Trade(
            entrada_timestamp=datetime(2024, 1, 1, 13, 30),
            saida_timestamp=datetime(2024, 1, 1, 14, 30, tzinfo=UTC),
            entrada_preco=100.0,
            saida_preco=110.0,
            lado="long",
            contratos=1,
            mfe_pontos=12.0,
            mae_pontos=-2.0,
        )


def test_trade_rejeita_saida_antes_de_entrada():
    with pytest.raises(ValidationError):
        Trade(
            entrada_timestamp=datetime(2024, 1, 1, 14, 30, tzinfo=UTC),
            saida_timestamp=datetime(2024, 1, 1, 13, 30, tzinfo=UTC),
            entrada_preco=100.0,
            saida_preco=110.0,
            lado="long",
            contratos=1,
            mfe_pontos=12.0,
            mae_pontos=-2.0,
        )


def test_trade_rejeita_contratos_zero():
    with pytest.raises(ValidationError):
        Trade(
            entrada_timestamp=datetime(2024, 1, 1, 13, 30, tzinfo=UTC),
            saida_timestamp=datetime(2024, 1, 1, 14, 30, tzinfo=UTC),
            entrada_preco=100.0,
            saida_preco=110.0,
            lado="long",
            contratos=0,
            mfe_pontos=12.0,
            mae_pontos=-2.0,
        )


def test_trade_rejeita_lado_invalido():
    with pytest.raises(ValidationError):
        Trade(
            entrada_timestamp=datetime(2024, 1, 1, 13, 30, tzinfo=UTC),
            saida_timestamp=datetime(2024, 1, 1, 14, 30, tzinfo=UTC),
            entrada_preco=100.0,
            saida_preco=110.0,
            lado="hold",  # type: ignore[arg-type]
            contratos=1,
            mfe_pontos=12.0,
            mae_pontos=-2.0,
        )


# ===========================================================================
# 0 trades — sem-trades
# ===========================================================================


def test_zero_trades_devolve_status_sem_trades():
    res = MetricasCalculator.calcular(
        trades=[],
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=42,
    )
    assert isinstance(res, ResultadoJanela)
    assert res.status == "sem-trades"
    assert res.numero_trades == 0
    assert res.pnl_total == 0.0
    # R6.2 — métricas dependentes None.
    assert res.sharpe_anualizado is None
    assert res.calmar is None
    assert res.drawdown_maximo_percentual is None
    assert res.drawdown_maximo_dias is None
    assert res.win_rate is None
    assert res.payoff_medio is None
    assert res.mfe_medio is None
    assert res.mae_medio is None
    assert res.duracao_ms == 42
    assert res.look_ahead_violation is False


def test_zero_trades_propaga_look_ahead_violation():
    res = MetricasCalculator.calcular(
        trades=[],
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
        look_ahead_violation=True,
    )
    assert res.status == "sem-trades"
    assert res.look_ahead_violation is True


# ===========================================================================
# 1 trade
# ===========================================================================


def test_um_trade_vencedor():
    trades = [_trade(dia=0, pnl=15.0, mfe=20.0, mae=-3.0)]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=10,
    )
    assert res.status == "ok"
    assert res.numero_trades == 1
    assert res.pnl_total == pytest.approx(15.0)
    assert res.win_rate == pytest.approx(1.0)
    # 0 perdas ⇒ payoff None.
    assert res.payoff_medio is None
    assert res.mfe_medio == pytest.approx(20.0)
    assert res.mae_medio == pytest.approx(-3.0)
    # 1 dia ⇒ Sharpe None (precisa de >= 2 dias).
    assert res.sharpe_anualizado is None
    # Sem drawdown (curva monotônica de subida) ⇒ dd_pct == 0.
    assert res.drawdown_maximo_percentual == pytest.approx(0.0)
    assert res.drawdown_maximo_dias == 0
    # Calmar None quando dd == 0.
    assert res.calmar is None


def test_um_trade_perdedor():
    trades = [_trade(dia=0, pnl=-8.0, mfe=2.0, mae=-12.0)]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=10,
    )
    assert res.status == "ok"
    assert res.numero_trades == 1
    assert res.pnl_total == pytest.approx(-8.0)
    assert res.win_rate == pytest.approx(0.0)
    # 0 ganhos, 1 perda ⇒ payoff = 0 / 8 = 0.0 (definido).
    assert res.payoff_medio == pytest.approx(0.0)
    # Drawdown total = 8.0; capital_base = max(peak=0, dd=8, 1) = 8.
    # dd_pct = 8/8 = 1.0.
    assert res.drawdown_maximo_percentual == pytest.approx(1.0)
    assert res.drawdown_maximo_dias == 0  # peak coincide com saída do trade.


# ===========================================================================
# Sequências homogêneas
# ===========================================================================


def test_sequencia_so_wins_drawdown_zero_calmar_none():
    trades = [
        _trade(dia=0, pnl=10.0, mfe=12.0, mae=0.0),
        _trade(dia=1, pnl=20.0, mfe=22.0, mae=-1.0),
        _trade(dia=2, pnl=15.0, mfe=18.0, mae=-2.0),
        _trade(dia=3, pnl=5.0, mfe=8.0, mae=0.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=10,
    )
    assert res.status == "ok"
    assert res.numero_trades == 4
    assert res.pnl_total == pytest.approx(50.0)
    assert res.win_rate == pytest.approx(1.0)
    # 0 perdas ⇒ payoff None.
    assert res.payoff_medio is None
    # Sem drawdown ⇒ Calmar None.
    assert res.drawdown_maximo_percentual == pytest.approx(0.0)
    assert res.drawdown_maximo_dias == 0
    assert res.calmar is None
    # Sharpe finito (4 dias diferentes, std > 0).
    assert res.sharpe_anualizado is not None
    assert math.isfinite(res.sharpe_anualizado)
    assert res.sharpe_anualizado > 0


def test_sequencia_so_losses_drawdown_um_calmar_negativo():
    trades = [
        _trade(dia=0, pnl=-5.0, mfe=1.0, mae=-7.0),
        _trade(dia=1, pnl=-10.0, mfe=2.0, mae=-15.0),
        _trade(dia=2, pnl=-3.0, mfe=0.5, mae=-5.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=10,
    )
    assert res.status == "ok"
    assert res.numero_trades == 3
    assert res.pnl_total == pytest.approx(-18.0)
    assert res.win_rate == pytest.approx(0.0)
    # 0 ganhos ⇒ payoff = 0.0 (definido).
    assert res.payoff_medio == pytest.approx(0.0)
    # Drawdown ≈ 18.0; capital_base = 18.0; dd_pct = 1.0.
    assert res.drawdown_maximo_percentual == pytest.approx(1.0)
    # Pico no estado pré-primeiro trade; mapeado para saída do trade 0
    # (dia=0). Trough no trade 2 (dia=2). Diferença = 2 dias.
    assert res.drawdown_maximo_dias == 2
    # Calmar finito e negativo.
    assert res.calmar is not None
    assert math.isfinite(res.calmar)
    assert res.calmar < 0
    # Sharpe finito (3 dias diferentes, std > 0).
    assert res.sharpe_anualizado is not None
    assert math.isfinite(res.sharpe_anualizado)
    assert res.sharpe_anualizado < 0


# ===========================================================================
# Série mista
# ===========================================================================


def test_serie_mista_sharpe_finito_e_payoff_calculado():
    trades = [
        _trade(dia=0, pnl=10.0, mfe=12.0, mae=-2.0),
        _trade(dia=1, pnl=-5.0, mfe=2.0, mae=-7.0),
        _trade(dia=2, pnl=20.0, mfe=22.0, mae=-3.0),
        _trade(dia=3, pnl=-10.0, mfe=1.0, mae=-12.0),
        _trade(dia=4, pnl=15.0, mfe=18.0, mae=-1.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=10,
    )
    assert res.status == "ok"
    assert res.numero_trades == 5
    assert res.pnl_total == pytest.approx(30.0)
    # 3 wins / 5 = 0.6.
    assert res.win_rate == pytest.approx(0.6)
    # mean(ganhos) = (10+20+15)/3 = 15; mean(|perdas|) = (5+10)/2 = 7.5.
    assert res.payoff_medio == pytest.approx(15.0 / 7.5)
    # Sharpe finito.
    assert res.sharpe_anualizado is not None
    assert math.isfinite(res.sharpe_anualizado)
    # Drawdown > 0 ⇒ Calmar finito.
    assert res.drawdown_maximo_percentual is not None
    assert res.drawdown_maximo_percentual > 0.0
    assert res.calmar is not None
    assert math.isfinite(res.calmar)


# ===========================================================================
# Drawdown — série conhecida
# ===========================================================================


def test_drawdown_serie_conhecida():
    """Curva de equity: 0 → 100 → 80 → 130 → 60 → 90.

    PnLs por trade: +100, -20, +50, -70, +30.
    Peaks: 100 e depois 130 (no trade 3).
    Maior drawdown absoluto = 130 - 60 = 70 (peak no trade 3, trough no trade 4).
    Capital_base = max(peak_global=130, dd=70, 1.0) = 130.
    Dd_pct = 70/130 ≈ 0.5384615.
    Dias = 1 (entre dia=2 e dia=3).
    """
    trades = [
        _trade(dia=0, pnl=100.0),
        _trade(dia=1, pnl=-20.0),
        _trade(dia=2, pnl=50.0),
        _trade(dia=3, pnl=-70.0),
        _trade(dia=4, pnl=30.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    assert res.status == "ok"
    assert res.drawdown_maximo_percentual == pytest.approx(70.0 / 130.0)
    # Pico no trade idx=2 (dia=2) com equity=130; trough no trade idx=3 (dia=3).
    assert res.drawdown_maximo_dias == 1
    # Calmar > 0: pnl_total = 90, capital_base = 130, retorno_total ≈ 0.692,
    # retorno_anualizado = retorno_total * 252/10 ≈ 17.45,
    # Calmar = 17.45 / 0.5385 ≈ 32.4.
    assert res.calmar is not None
    assert res.calmar > 0


def test_drawdown_dias_em_serie_de_picos_intermediarios():
    """Curva: 0 → 50 → 30 → 40 → 10 → 60.

    Peaks: 50 (trade 0), 60 (trade 4). Trough do maior dd: trade 3 (eq=10).
    Maior dd absoluto = peak[trade 0] - eq[trade 3] = 50 - 10 = 40.
    Peak idx = 1 (trade 0, dia=0). Trough idx = 4 (trade 3, dia=3).
    Dias = 3.
    """
    trades = [
        _trade(dia=0, pnl=50.0),
        _trade(dia=1, pnl=-20.0),
        _trade(dia=2, pnl=10.0),
        _trade(dia=3, pnl=-30.0),
        _trade(dia=4, pnl=50.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    assert res.drawdown_maximo_dias == 3
    # capital_base = max(peak_global=60, dd=40, 1) = 60. dd_pct = 40/60 ≈ 0.667.
    assert res.drawdown_maximo_percentual == pytest.approx(40.0 / 60.0)


# ===========================================================================
# Sharpe — casos especiais
# ===========================================================================


def test_sharpe_um_dia_apenas_devolve_none():
    """Múltiplos trades no mesmo dia ⇒ 1 entrada em returns_diarios."""
    base = datetime(2024, 3, 27, 13, 30, tzinfo=UTC)
    trades = [
        Trade(
            entrada_timestamp=base + timedelta(hours=i),
            saida_timestamp=base + timedelta(hours=i, minutes=30),
            entrada_preco=21000.0,
            saida_preco=21000.0 + (5.0 * (1 if i % 2 == 0 else -1)),
            lado="long",
            contratos=1,
            mfe_pontos=5.0,
            mae_pontos=-1.0,
        )
        for i in range(4)
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    # Todos os trades fecham no mesmo `date()`. < 2 dias ⇒ Sharpe None.
    assert res.sharpe_anualizado is None


def test_sharpe_todos_pnls_iguais_devolve_none():
    """std == 0 ⇒ Sharpe None."""
    trades = [
        _trade(dia=0, pnl=10.0),
        _trade(dia=1, pnl=10.0),
        _trade(dia=2, pnl=10.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    # std == 0 ⇒ Sharpe None.
    assert res.sharpe_anualizado is None


def test_sharpe_formula_anualizada_simples():
    """Sharpe = (mean / std) * sqrt(252) com PnLs conhecidos."""
    pnls = [10.0, -5.0, 8.0]
    trades = [_trade(dia=i, pnl=p) for i, p in enumerate(pnls)]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    media = sum(pnls) / len(pnls)
    var = sum((x - media) ** 2 for x in pnls) / (len(pnls) - 1)
    std = math.sqrt(var)
    esperado = (media / std) * math.sqrt(DIAS_UTEIS_POR_ANO)
    assert res.sharpe_anualizado is not None
    assert res.sharpe_anualizado == pytest.approx(esperado, rel=1e-9)


# ===========================================================================
# Payoff médio — convenção 0 perdas
# ===========================================================================


def test_payoff_medio_zero_perdas_devolve_none():
    trades = [
        _trade(dia=0, pnl=10.0),
        _trade(dia=1, pnl=20.0),
        _trade(dia=2, pnl=5.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    assert res.payoff_medio is None


def test_payoff_medio_com_breakeven_ignora_zero():
    """PnL == 0 não conta nem como win nem como loss."""
    trades = [
        _trade(dia=0, pnl=10.0),
        _trade(dia=1, pnl=0.0),
        _trade(dia=2, pnl=-5.0),
    ]
    res = MetricasCalculator.calcular(
        trades=trades,
        janela=_janela(),
        estrategia="exemplo",
        configuracao=_config(),
        duracao_ms=1,
    )
    # 1 win, 1 loss, 1 breakeven (ignorado).
    assert res.win_rate == pytest.approx(0.5)
    # mean(ganhos) = 10; mean(|perdas|) = 5; payoff = 2.0.
    assert res.payoff_medio == pytest.approx(2.0)


# ===========================================================================
# Re-export
# ===========================================================================


def test_metricas_calculator_e_dia_uteis_reexportados():
    from caos.walk_forward import DIAS_UTEIS_POR_ANO as DIA_REEXPORT
    from caos.walk_forward import MetricasCalculator as MCREEXPORT

    assert DIA_REEXPORT == 252
    assert MCREEXPORT is MetricasCalculator
