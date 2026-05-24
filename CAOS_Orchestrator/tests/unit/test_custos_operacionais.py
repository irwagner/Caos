"""Testes unitários do modelo :class:`CustosOperacionais` e da
aplicação de fricção no :class:`BacktestRunner`.

Cobre a Decisao_Do_Conselho 2026-05-23-01: WF sem fricção é otimista;
slippage + comissão devem entrar antes de qualquer próxima Decisão sobre
EstrategiaORB.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from caos.walk_forward.models import (
    USD_POR_PONTO_MNQ,
    ConfiguracaoWalkForward,
    CustosOperacionais,
    JanelaWF,
)
from caos.walk_forward.metricas import Trade as TradeMetricas
from caos.walk_forward.runner import (
    Trade as TradeMinimo,
    _aplicar_custos_operacionais,
)


# ---------------------------------------------------------------------------
# Construtores e validações do modelo
# ---------------------------------------------------------------------------


class TestModeloCustosOperacionais:
    def test_zerados_eh_padrao(self) -> None:
        c = CustosOperacionais()
        assert c.slippage_pontos_por_lado == 0.0
        assert c.comissao_usd_por_contrato_por_lado == 0.0
        assert c.usd_por_ponto == USD_POR_PONTO_MNQ
        assert c.eh_zerado()
        assert CustosOperacionais.zerados().eh_zerado()

    def test_topstep_mnq_default_slippage_1_tick(self) -> None:
        c = CustosOperacionais.topstep_mnq()
        assert c.slippage_pontos_por_lado == 0.25
        assert c.comissao_usd_por_contrato_por_lado == 0.62
        assert c.usd_por_ponto == 2.0
        assert not c.eh_zerado()

    def test_topstep_mnq_slippage_customizado(self) -> None:
        c = CustosOperacionais.topstep_mnq(slippage_pontos_por_lado=0.5)
        assert c.slippage_pontos_por_lado == 0.5

    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("slippage_pontos_por_lado", -0.1),
            ("slippage_pontos_por_lado", 11.0),
            ("comissao_usd_por_contrato_por_lado", -0.5),
            ("comissao_usd_por_contrato_por_lado", 25.0),
            ("usd_por_ponto", 0.0),
            ("usd_por_ponto", -2.0),
            ("usd_por_ponto", 1500.0),
        ],
    )
    def test_rejeita_valores_fora_de_faixa(self, campo: str, valor: float) -> None:
        with pytest.raises(ValidationError):
            CustosOperacionais.model_validate({campo: valor})


# ---------------------------------------------------------------------------
# Cálculo de custo
# ---------------------------------------------------------------------------


class TestCustoTotalPontos:
    def test_zerado_retorna_zero(self) -> None:
        c = CustosOperacionais()
        assert c.custo_total_pontos(contratos=1) == 0.0
        assert c.custo_total_pontos(contratos=10) == 0.0

    def test_apenas_slippage(self) -> None:
        # 0.25 pontos/lado × 2 lados × 1 contrato = 0.5 pontos.
        c = CustosOperacionais(slippage_pontos_por_lado=0.25)
        assert c.custo_total_pontos(contratos=1) == 0.5

    def test_apenas_comissao_em_mnq(self) -> None:
        # USD 0.62 / lado / contrato; usd_por_ponto = 2.0
        # → 0.31 pts/lado/contrato × 2 lados × 1 contrato = 0.62 pts.
        c = CustosOperacionais(comissao_usd_por_contrato_por_lado=0.62)
        assert c.custo_total_pontos(contratos=1) == pytest.approx(0.62)

    def test_topstep_default(self) -> None:
        # slippage 0.25 + comissao 0.62/2.0 = 0.25 + 0.31 = 0.56 pts/lado.
        # Round-trip 1 contrato = 1.12 pts.
        c = CustosOperacionais.topstep_mnq()
        assert c.custo_total_pontos(contratos=1) == pytest.approx(1.12)

    def test_escala_com_contratos(self) -> None:
        c = CustosOperacionais.topstep_mnq()
        assert c.custo_total_pontos(contratos=3) == pytest.approx(3.36)

    def test_contratos_invalidos_levanta(self) -> None:
        c = CustosOperacionais.topstep_mnq()
        with pytest.raises(ValueError):
            c.custo_total_pontos(contratos=0)
        with pytest.raises(ValueError):
            c.custo_total_pontos(contratos=-1)


# ---------------------------------------------------------------------------
# Integração com ConfiguracaoWalkForward
# ---------------------------------------------------------------------------


class TestConfiguracaoComCustos:
    def test_custos_default_e_none(self) -> None:
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
        )
        assert cfg.custos is None

    def test_custos_aceita_modelo(self) -> None:
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
            custos=CustosOperacionais.topstep_mnq(),
        )
        assert cfg.custos is not None
        assert cfg.custos.slippage_pontos_por_lado == 0.25

    def test_custos_aceita_dict(self) -> None:
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
            custos={
                "slippage_pontos_por_lado": 0.5,
                "comissao_usd_por_contrato_por_lado": 1.0,
            },
        )
        assert cfg.custos is not None
        assert cfg.custos.slippage_pontos_por_lado == 0.5
        assert cfg.custos.comissao_usd_por_contrato_por_lado == 1.0


# ---------------------------------------------------------------------------
# _aplicar_custos_operacionais — Trade rico (metricas.Trade)
# ---------------------------------------------------------------------------


def _trade_long(
    entrada: float = 100.0,
    saida: float = 110.0,
    contratos: int = 1,
) -> TradeMetricas:
    return TradeMetricas(
        entrada_timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc),
        saida_timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        entrada_preco=entrada,
        saida_preco=saida,
        lado="long",
        contratos=contratos,
        mfe_pontos=10.0,
        mae_pontos=-2.0,
    )


def _trade_short(
    entrada: float = 110.0,
    saida: float = 100.0,
    contratos: int = 1,
) -> TradeMetricas:
    return TradeMetricas(
        entrada_timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc),
        saida_timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
        entrada_preco=entrada,
        saida_preco=saida,
        lado="short",
        contratos=contratos,
        mfe_pontos=10.0,
        mae_pontos=-2.0,
    )


class TestAplicarCustosTradeMetricas:
    def test_custos_none_e_no_op(self) -> None:
        trades = [_trade_long()]
        ajustados = _aplicar_custos_operacionais(trades, None)
        # Mesma referência (no-op rápido).
        assert ajustados is trades

    def test_custos_zerados_e_no_op(self) -> None:
        trades = [_trade_long()]
        ajustados = _aplicar_custos_operacionais(
            trades, CustosOperacionais.zerados()
        )
        assert ajustados is trades

    def test_long_pnl_reduz_pelo_custo(self) -> None:
        # PnL bruto: (110 - 100) * 1 = 10 pontos.
        # Topstep: custo_total = 1.12 pts. PnL líquido = 8.88.
        t = _trade_long()
        custos = CustosOperacionais.topstep_mnq()
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        assert t_ajustado.pnl_pontos() == pytest.approx(10.0 - 1.12)
        # Slippage simétrico: entrada subiu, saída desceu, cada uma por
        # 0.56 pontos.
        assert t_ajustado.entrada_preco == pytest.approx(100.56)
        assert t_ajustado.saida_preco == pytest.approx(109.44)

    def test_short_pnl_reduz_pelo_custo(self) -> None:
        # PnL bruto: (110 - 100) * 1 = 10 pontos.
        t = _trade_short()
        custos = CustosOperacionais.topstep_mnq()
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        assert t_ajustado.pnl_pontos() == pytest.approx(10.0 - 1.12)
        # Para short: vendo barato (entrada -0.56), recompro caro
        # (saída +0.56).
        assert t_ajustado.entrada_preco == pytest.approx(109.44)
        assert t_ajustado.saida_preco == pytest.approx(100.56)

    def test_multiplos_contratos_escalonam_o_custo(self) -> None:
        # 3 contratos: PnL bruto (110-100)*3 = 30 pts.
        # custo_total_pontos(3) = 3.36.
        # PnL líquido = 26.64.
        t = _trade_long(contratos=3)
        custos = CustosOperacionais.topstep_mnq()
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        assert t_ajustado.pnl_pontos() == pytest.approx(30.0 - 3.36)
        # Por contrato: custo_total/contratos = 1.12 pts; metade por
        # lado = 0.56. Preços por contrato deslocados em 0.56 ainda.
        assert t_ajustado.entrada_preco == pytest.approx(100.56)
        assert t_ajustado.saida_preco == pytest.approx(109.44)

    def test_trade_perdedor_fica_mais_negativo(self) -> None:
        # PnL bruto: (95 - 100) * 1 = -5. Líquido = -5 - 1.12 = -6.12.
        t = _trade_long(entrada=100.0, saida=95.0)
        custos = CustosOperacionais.topstep_mnq()
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        assert t_ajustado.pnl_pontos() == pytest.approx(-5.0 - 1.12)


# ---------------------------------------------------------------------------
# _aplicar_custos_operacionais — Trade mínimo (runner.Trade)
# ---------------------------------------------------------------------------


class TestAplicarCustosTradeMinimo:
    def test_pnl_reduz_pelo_custo_total(self) -> None:
        t = TradeMinimo(pnl=10.0)
        custos = CustosOperacionais.topstep_mnq()
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        # Trade mínimo assume 1 contrato; custo round-trip = 1.12.
        assert t_ajustado.pnl == pytest.approx(10.0 - 1.12)

    def test_so_slippage(self) -> None:
        t = TradeMinimo(pnl=5.0)
        custos = CustosOperacionais(slippage_pontos_por_lado=0.5)
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        # 0.5 * 2 * 1 = 1.0 pt.
        assert t_ajustado.pnl == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Regressão: caminho legado (sem custos) preserva valor original
# ---------------------------------------------------------------------------


class TestRegressaoSemCustos:
    def test_pipeline_sem_custos_eh_identico_ao_legado(self) -> None:
        trades_originais = [_trade_long(entrada=100, saida=110, contratos=2)]
        ajustados = _aplicar_custos_operacionais(trades_originais, None)
        # Lista é a MESMA referência — caminho legado nem aloca cópias.
        assert ajustados is trades_originais
        assert ajustados[0].entrada_preco == 100
        assert ajustados[0].saida_preco == 110
        assert ajustados[0].pnl_pontos() == 20.0


# ---------------------------------------------------------------------------
# Reexports do pacote
# ---------------------------------------------------------------------------


def test_custos_operacionais_reexportado() -> None:
    from caos.walk_forward import CustosOperacionais as REEXP

    assert REEXP is CustosOperacionais



# ---------------------------------------------------------------------------
# Slippage proporcional (Hydra v1 lesson — commit c1b2bc6 anexo)
# ---------------------------------------------------------------------------


class TestSlippageProporcional:
    def test_topstep_proporcional_default_e_7_5_pct(self) -> None:
        c = CustosOperacionais.topstep_mnq_proporcional()
        assert c.slippage_fracao_range == 0.075
        assert c.slippage_pontos_por_lado == 0.25  # piso = 1 tick
        assert c.comissao_usd_por_contrato_por_lado == 0.62

    def test_proporcional_aciona_quando_range_dado(self) -> None:
        # Range 100 pts × 7.5% = 7.5 pts/lado.
        c = CustosOperacionais.topstep_mnq_proporcional()
        # Sem range_referencia, fallback ao fixo + comissão.
        sem_range = c.custo_total_pontos(1)
        # 0.25 + 0.31 = 0.56/lado × 2 lados = 1.12.
        assert sem_range == pytest.approx(1.12)

        com_range = c.custo_total_pontos(1, range_referencia=100.0)
        # max(0.25, 7.5) + 0.31 = 7.81 por lado × 2 = 15.62.
        assert com_range == pytest.approx((7.5 + 0.31) * 2)

    def test_piso_minimo_aplicado_quando_range_pequeno(self) -> None:
        # Range 1 pt × 7.5% = 0.075 < piso 0.25.
        c = CustosOperacionais.topstep_mnq_proporcional()
        custo = c.custo_total_pontos(1, range_referencia=1.0)
        # max(0.25, 0.075) = 0.25 → 0.25 + 0.31 = 0.56 × 2 = 1.12.
        assert custo == pytest.approx(1.12)

    def test_eh_zerado_falso_quando_proporcional_setado(self) -> None:
        c = CustosOperacionais(
            slippage_fracao_range=0.075,
            comissao_usd_por_contrato_por_lado=0.0,
        )
        assert c.eh_zerado() is False

    def test_aplicacao_no_runner_com_proporcional(self) -> None:
        """Trade rico com MFE 10 + |MAE| 2 = range proxy 12 pts deve
        sofrer slippage proporcional baseado em MFE+|MAE|."""
        # PnL bruto: (110-100)*1 = 10 pts.
        # Range proxy = MFE + |MAE| = 10 + 2 = 12.
        # Slip por lado = max(0.25, 0.075 × 12) = 0.9 pts.
        # Comissão por lado = 0.62/2.0 = 0.31 pts.
        # Custo total = 2 × (0.9 + 0.31) × 1 = 2.42 pts.
        # PnL líquido esperado: 10 - 2.42 = 7.58.
        t = _trade_long(entrada=100.0, saida=110.0)
        custos = CustosOperacionais.topstep_mnq_proporcional()
        [t_ajustado] = _aplicar_custos_operacionais([t], custos)
        assert t_ajustado.pnl_pontos() == pytest.approx(10.0 - 2.42, rel=1e-3)

    def test_proporcional_escala_com_volatilidade(self) -> None:
        """Trade com MFE/MAE maior deve sofrer mais slippage que MFE/MAE menor."""
        # Helper _trade_long fixa MFE=10, MAE=-2 → range_proxy=12.
        # Pra criar diferença real, construo trades com excursões
        # diferentes diretamente.
        t_calmo = TradeMetricas(
            entrada_timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc),
            saida_timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
            entrada_preco=100.0, saida_preco=110.0,
            lado="long", contratos=1,
            mfe_pontos=10.0, mae_pontos=-2.0,  # range_proxy 12
        )
        t_volatil = TradeMetricas(
            entrada_timestamp=datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc),
            saida_timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
            entrada_preco=100.0, saida_preco=110.0,
            lado="long", contratos=1,
            mfe_pontos=30.0, mae_pontos=-10.0,  # range_proxy 40
        )
        custos = CustosOperacionais.topstep_mnq_proporcional()

        [tc] = _aplicar_custos_operacionais([t_calmo], custos)
        [tv] = _aplicar_custos_operacionais([t_volatil], custos)

        custo_c = 10.0 - tc.pnl_pontos()
        custo_v = 10.0 - tv.pnl_pontos()
        # Calmo: max(0.25, 0.075×12) + 0.31 = 1.21/lado × 2 = 2.42.
        # Volátil: max(0.25, 0.075×40) + 0.31 = 3.31/lado × 2 = 6.62.
        assert custo_c == pytest.approx(2.42, rel=1e-3)
        assert custo_v == pytest.approx(6.62, rel=1e-3)
        # Volátil deve ter custo significativamente maior.
        assert custo_v > 2 * custo_c
