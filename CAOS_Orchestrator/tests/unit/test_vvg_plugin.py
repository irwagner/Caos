"""Testes unitários do plugin VVG Late-Session Reversal (Spec — Tarefa 8).

Cobre a integração das três camadas (``VvgClassifier`` + ``decidir_acao`` +
motor de execução do plugin) através de
:class:`caos.walk_forward.estrategias.vvg_late_session_reversal.EstrategiaVvgLateSessionReversal`:

- ``treinar`` aquece o classificador SEM emitir trades (``finalizar``
  devolve lista vazia após só treinar).
- ``on_barra`` emite um trade num dia VVG-positivo conhecido (histórico de
  treino + dia de teste construído para disparar a entrada às 14:30 NY).
- Property 12 (R4.1): todo :class:`Trade` emitido tem ``contratos == 1``.
- Stop/target intrabar: se uma barra após a entrada toca o stop, o trade
  fecha no stop com ``motivo_saida == "stop"`` (via ``metadados_trades``);
  idem para o target.
- Encerramento forçado: sem stop nem target tocados, o trade fecha às
  15:50 NY com motivo ``"encerramento-forcado"``.
- Ordem de prioridade (conservadora): barra que toca stop E target no mesmo
  minuto → fecha por ``"stop"``.
- 1 trade por dia (R2.6): um dia VVG-positivo cujo trade é stopado cedo NÃO
  reabre nova posição (nem no force-close de 15:50) → exatamente 1 trade.

Schema: usamos o :class:`caos.walk_forward.metricas.Trade` real (8 campos)
e a property ``metadados_trades`` do plugin (alinhada por índice com
``trades``).

Convenção de fuso: barras com ``timestamp`` UTC; o plugin/classificador
converte para Nova York. Usamos datas de julho de 2025 (EDT, UTC-4) para
manter o offset constante. O dia de teste vai de 09:30 a 16:00 NY (390
barras de minuto), o que cobre a janela morning, a entrada às 14:30
(índice 300) e o encerramento forçado às 15:50 (índice 380).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from caos.walk_forward.estrategias.vvg_late_session_reversal import (
    EstrategiaVvgLateSessionReversal,
)
from caos.walk_forward.estrategias.vvg_logica import ParametrosVvg
from caos.walk_forward.metricas import Trade

# ---------------------------------------------------------------------------
# Constantes e helpers de geração de barras
# ---------------------------------------------------------------------------

NY = ZoneInfo("America/New_York")
UTC = timezone.utc

#: Close de referência dos dias de treino (vira close(D-1) do dia de teste).
CLOSE_BASE = 20000.0

#: Parâmetros congelados, exceto n_dias_baseline reduzido para o teste.
N_BASELINE_TESTE = 2

#: Índices de minuto (a partir de 09:30 NY) de marcos do dia de teste.
IDX_ENTRADA = 300       # 09:30 + 300 min = 14:30 NY (entrada)
IDX_POS_ENTRADA = 301   # 14:31 NY (primeira barra após a entrada)
IDX_FORCE_CLOSE = 380   # 09:30 + 380 min = 15:50 NY (encerramento forçado)


def _params() -> ParametrosVvg:
    """Parâmetros do teste: stop/target congelados + baseline curto."""
    return ParametrosVvg(n_dias_baseline=N_BASELINE_TESTE)


def _dias_uteis(inicio: date, n: int) -> list[date]:
    """Devolve ``n`` datas de dias úteis (seg–sex) a partir de ``inicio``."""
    dias: list[date] = []
    d = inicio
    while len(dias) < n:
        if d.weekday() < 5:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def _barras_dia(
    dia: date,
    *,
    open_0930: float,
    close_base: float,
    morning_vol: float,
    n_barras: int,
    overrides: Optional[dict[int, tuple[float, float, float, float]]] = None,
) -> list[dict]:
    """Gera ``n_barras`` barras de minuto a partir das 09:30 NY de ``dia``.

    - Índice 0 (09:30) abre em ``open_0930`` e concentra todo o
      ``morning_vol``; as demais barras morning têm volume 0.
    - Barras default fecham em ``close_base`` com ``high = low = close_base``
      (nenhuma excursão).
    - ``overrides`` mapeia índice → ``(open, high, low, close)`` para
      injetar barras que tocam stop/target após a entrada.
    """
    overrides = overrides or {}
    base_ny = datetime(dia.year, dia.month, dia.day, 9, 30, tzinfo=NY)
    barras: list[dict] = []
    for i in range(n_barras):
        ts_utc = (base_ny + timedelta(minutes=i)).astimezone(UTC)
        if i in overrides:
            o, h, l, c = overrides[i]
            v = 0.0
        elif i == 0:
            o, c = open_0930, close_base
            h, l = max(o, c), min(o, c)
            v = morning_vol
        else:
            o = c = close_base
            h = l = close_base
            v = 0.0
        barras.append(
            {"timestamp": ts_utc, "open": o, "high": h, "low": l, "close": c, "volume": v}
        )
    return barras


def _df_treino() -> pd.DataFrame:
    """DataFrame de treino com 2 dias úteis válidos (310 barras cada).

    Ambos com ``volume_morning = 1000`` e ``close = CLOSE_BASE``; servem para
    preencher o baseline rolling e o ``close(D-1)`` antes do dia de teste.
    """
    dias = _dias_uteis(date(2025, 7, 7), N_BASELINE_TESTE)
    linhas: list[dict] = []
    for d in dias:
        linhas.extend(
            _barras_dia(
                d,
                open_0930=CLOSE_BASE,
                close_base=CLOSE_BASE,
                morning_vol=1000.0,
                n_barras=310,
            )
        )
    return pd.DataFrame(linhas)


def _dia_teste(
    overrides: Optional[dict[int, tuple[float, float, float, float]]] = None,
) -> pd.DataFrame:
    """DataFrame do dia de teste VVG-positivo (09:30→16:00 NY = 390 barras).

    - ``open(09:30) = CLOSE_BASE * 1.01`` ⇒ gap ≈ 1% (>> 0.0015).
    - ``volume_morning = 5000`` (>> 1.5 × baseline=1000) ⇒ VVG-positivo.
    - ``close`` das demais barras = ``CLOSE_BASE`` ⇒ drift = 20000 − 20200 =
      −200 ≤ 0 ⇒ entrada LONG a 20000.
    """
    dia_teste = _dias_uteis(date(2025, 7, 7), N_BASELINE_TESTE + 1)[N_BASELINE_TESTE]
    linhas = _barras_dia(
        dia_teste,
        open_0930=CLOSE_BASE * 1.01,
        close_base=CLOSE_BASE,
        morning_vol=5000.0,
        n_barras=390,
        overrides=overrides,
    )
    return pd.DataFrame(linhas)


def _rodar(
    overrides: Optional[dict[int, tuple[float, float, float, float]]] = None,
) -> EstrategiaVvgLateSessionReversal:
    """Treina o plugin e roda o dia de teste; devolve o plugin já finalizado."""
    plugin = EstrategiaVvgLateSessionReversal(parametros=_params())
    plugin.treinar(_df_treino())
    df = _dia_teste(overrides)
    for _, barra in df.iterrows():
        plugin.on_barra(barra, contexto=None)  # type: ignore[arg-type]
    plugin.finalizar()
    return plugin


# ---------------------------------------------------------------------------
# treinar — aquecimento sem trades
# ---------------------------------------------------------------------------


class TestTreinarSemTrades:
    def test_treinar_nao_emite_trades(self) -> None:
        """Só treinar (sem on_barra) ⇒ finalizar devolve lista vazia."""
        plugin = EstrategiaVvgLateSessionReversal(parametros=_params())
        plugin.treinar(_df_treino())
        trades = plugin.finalizar()
        assert list(trades) == []
        assert plugin.metadados_trades == ()


# ---------------------------------------------------------------------------
# on_barra — emissão de trade em dia VVG-positivo
# ---------------------------------------------------------------------------


class TestEmiteTradeVvgPositivo:
    def test_dia_vvg_positivo_emite_um_trade_long(self) -> None:
        """Dia VVG-positivo com drift ≤ 0 ⇒ 1 trade LONG, fechado no EOD."""
        plugin = _rodar()
        trades = list(plugin.trades)
        assert len(trades) == 1
        trade = trades[0]
        assert isinstance(trade, Trade)
        assert trade.lado == "long"
        assert trade.entrada_preco == CLOSE_BASE  # entrada às 14:30 a 20000

        meta = plugin.metadados_trades
        assert len(meta) == 1
        assert meta[0]["vvg_positivo"] is True
        assert meta[0]["motivo_saida"] == "encerramento-forcado"

    def test_entrada_ocorre_as_1430_ny(self) -> None:
        """O timestamp de entrada do trade corresponde a 14:30 NY."""
        plugin = _rodar()
        trade = list(plugin.trades)[0]
        ts_ny = trade.entrada_timestamp.astimezone(NY)
        assert (ts_ny.hour, ts_ny.minute) == (14, 30)


# ---------------------------------------------------------------------------
# Property 12 — contratos == 1 em todo trade (R4.1)
# ---------------------------------------------------------------------------


class TestProperty12Contratos:
    def test_todo_trade_tem_um_contrato(self) -> None:
        """Validates: Requirements 4.1

        Todo :class:`Trade` emitido pelo plugin usa ``contratos == 1``.
        Exercitamos os quatro caminhos de saída (EOD, stop, target,
        stop+target) e exigimos ``contratos == 1`` em todos.
        """
        cenarios = [
            None,  # encerramento forçado
            {IDX_POS_ENTRADA: (20000.0, 20000.0, 19000.0, 19500.0)},  # stop
            {IDX_POS_ENTRADA: (20000.0, 21000.0, 20000.0, 20900.0)},  # target
            {IDX_POS_ENTRADA: (20000.0, 21000.0, 19000.0, 20000.0)},  # stop+target
        ]
        for overrides in cenarios:
            plugin = _rodar(overrides)
            trades = list(plugin.trades)
            assert len(trades) == 1
            assert all(t.contratos == 1 for t in trades)


# ---------------------------------------------------------------------------
# Stop / target intrabar
# ---------------------------------------------------------------------------


class TestStopTargetIntrabar:
    def test_barra_toca_stop_fecha_no_stop(self) -> None:
        """Barra após a entrada com low ≤ stop ⇒ fecha no stop (motivo 'stop')."""
        # LONG a 20000; stop = 20000 - 472.25 = 19527.75.
        plugin = _rodar({IDX_POS_ENTRADA: (20000.0, 20000.0, 19000.0, 19500.0)})
        trades = list(plugin.trades)
        assert len(trades) == 1
        stop_preco = CLOSE_BASE - _params().stop_pontos
        assert trades[0].saida_preco == stop_preco
        assert plugin.metadados_trades[0]["motivo_saida"] == "stop"

    def test_barra_toca_target_fecha_no_target(self) -> None:
        """Barra após a entrada com high ≥ target ⇒ fecha no target."""
        # LONG a 20000; target = 20000 + 944.25 = 20944.25.
        plugin = _rodar({IDX_POS_ENTRADA: (20000.0, 21000.0, 20000.0, 20900.0)})
        trades = list(plugin.trades)
        assert len(trades) == 1
        alvo_preco = CLOSE_BASE + _params().target_pontos
        assert trades[0].saida_preco == alvo_preco
        assert plugin.metadados_trades[0]["motivo_saida"] == "target"


# ---------------------------------------------------------------------------
# Encerramento forçado às 15:50 NY
# ---------------------------------------------------------------------------


class TestEncerramentoForcado:
    def test_sem_stop_nem_target_fecha_as_1550(self) -> None:
        """Sem toque em stop/target ⇒ fecha às 15:50 NY (encerramento-forcado)."""
        plugin = _rodar()  # sem overrides: preço fica em 20000
        trade = list(plugin.trades)[0]
        assert plugin.metadados_trades[0]["motivo_saida"] == "encerramento-forcado"
        ts_ny = trade.saida_timestamp.astimezone(NY)
        assert (ts_ny.hour, ts_ny.minute) == (15, 50)


# ---------------------------------------------------------------------------
# Ordem de prioridade — stop antes de target (conservador)
# ---------------------------------------------------------------------------


class TestPrioridadeStopAntesTarget:
    def test_stop_e_target_no_mesmo_minuto_fecha_por_stop(self) -> None:
        """Barra que toca stop E target no mesmo minuto ⇒ fecha por 'stop'."""
        plugin = _rodar({IDX_POS_ENTRADA: (20000.0, 21000.0, 19000.0, 20000.0)})
        trades = list(plugin.trades)
        assert len(trades) == 1
        stop_preco = CLOSE_BASE - _params().stop_pontos
        assert trades[0].saida_preco == stop_preco
        assert plugin.metadados_trades[0]["motivo_saida"] == "stop"


# ---------------------------------------------------------------------------
# 1 trade por dia (R2.6)
# ---------------------------------------------------------------------------


class TestUmTradePorDia:
    def test_trade_stopado_nao_reabre_no_mesmo_dia(self) -> None:
        """Trade stopado às 14:31 não reabre — nem no force-close de 15:50.

        Mesmo o dia seguindo até 16:00 (incluindo o instante do
        encerramento forçado, 15:50), apenas 1 trade é emitido: o guard
        ``trade_fechado_hoje`` (R2.6) impede nova posição.
        """
        plugin = _rodar({IDX_POS_ENTRADA: (20000.0, 20000.0, 19000.0, 19500.0)})
        trades = list(plugin.trades)
        assert len(trades) == 1
        assert plugin.metadados_trades[0]["motivo_saida"] == "stop"
