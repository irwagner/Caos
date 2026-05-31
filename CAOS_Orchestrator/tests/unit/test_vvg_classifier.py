"""Testes unitários do classificador VVG stateful (Spec — Tarefa 8).

Cobre as Properties 2, 3 e 4 do ``design.md`` desta feature, além dos
edge cases de R1 (baseline rolling, anti look-ahead via ``shift(1)``,
filtro de dia válido, fim de semana e os motivos canônicos):

- Property 2 (R1.2): monotonicidade em volume — com ``gap_pct`` fixo
  acima do threshold, aumentar ``volume_morning`` nunca faz
  ``vvg_positivo`` passar de ``True`` para ``False``.
- Property 3 (R1.2): monotonicidade em gap — análogo com volume fixo
  acima do limiar de volume.
- Property 4 (R1.4): warmup incompleto (< ``n_dias_baseline`` dias úteis
  válidos) sempre devolve ``vvg_positivo=False`` com motivo
  ``"warmup-incompleto"``.

Edge cases adicionais:

- O baseline rolling reflete os últimos N dias úteis válidos.
- ``shift(1)``: o baseline NÃO inclui o próprio dia (anti look-ahead).
- Dia inválido (< :data:`MIN_BARRAS_DIA_VALIDO` barras) não entra no
  baseline.
- Sábado/domingo são descartados (``on_barra`` devolve ``None``).
- ``vvg_positivo`` só dispara quando ``volume >= 1.5 * baseline`` E
  ``gap >= 0.0015``.
- Motivos canônicos: ``"OK"``, ``"volume-baixo"``, ``"gap-baixo"``,
  ``"warmup-incompleto"``, ``"dia-invalido"``.

Convenção de fuso (ver docstring de ``vvg_classifier``): as barras chegam
com ``timestamp`` em UTC; o classificador converte para horário de Nova
York. Os timestamps de teste são construídos em NY (via ``zoneinfo``) e
convertidos para UTC. Usamos datas de julho (garantidamente EDT) para
manter o offset constante dentro de um mesmo dia.

Decisão de geração de barras: para que o ``volume_morning`` e o baseline
sejam EXATOS (sem ruído de divisão de ponto-flutuante), todo o volume da
janela morning ``[09:30, 10:00)`` é concentrado na primeira barra
(09:30). As demais barras morning têm volume zero. Isso não altera nada
do ponto de vista do classificador (que apenas SOMA o volume morning),
mas torna os asserts de baseline determinísticos.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.walk_forward.estrategias.vvg_classifier import (
    MIN_BARRAS_DIA_VALIDO,
    ResultadoClassificacao,
    VvgClassifier,
)
from caos.walk_forward.estrategias.vvg_logica import ParametrosVvg

# ---------------------------------------------------------------------------
# Constantes e helpers
# ---------------------------------------------------------------------------

NY = ZoneInfo("America/New_York")
UTC = timezone.utc

#: Close de referência (close(D-1)) usado para fixar o gap dos dias de teste.
CLOSE_REF = 20000.0


def _floats(lo: float, hi: float) -> st.SearchStrategy:
    """Strategy de floats finitos no intervalo fechado ``[lo, hi]``."""
    return st.floats(min_value=lo, max_value=hi, allow_nan=False, allow_infinity=False)


def _dias_uteis(inicio: date, n: int) -> list[date]:
    """Devolve ``n`` datas de dias úteis (seg–sex) a partir de ``inicio``."""
    dias: list[date] = []
    d = inicio
    while len(dias) < n:
        if d.weekday() < 5:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def _barra(ts_utc: datetime, *, o: float, c: float, v: float) -> dict:
    """Constrói uma barra OHLCV mínima como dict (compatível com on_barra).

    O classificador lê apenas ``timestamp``, ``open``, ``close`` e
    ``volume``; ``high``/``low`` são derivados de ``open``/``close`` apenas
    para coerência de schema.
    """
    return {
        "timestamp": ts_utc,
        "open": o,
        "high": max(o, c),
        "low": min(o, c),
        "close": c,
        "volume": v,
    }


def _gerar_dia(
    dia: date,
    *,
    open_0930: float,
    close_dia: float,
    volume_morning: float,
    n_barras: int,
) -> list[dict]:
    """Gera ``n_barras`` barras de minuto a partir das 09:30 NY de ``dia``.

    - A primeira barra (09:30) abre em ``open_0930`` e concentra todo o
      ``volume_morning`` (as demais barras morning têm volume 0).
    - Todas as barras fecham em ``close_dia`` (a última barra de RTH vira
      ``close(D-1)`` na finalização do dia).
    - ``n_barras >=`` :data:`MIN_BARRAS_DIA_VALIDO` torna o dia válido.
    """
    barras: list[dict] = []
    base_ny = datetime(dia.year, dia.month, dia.day, 9, 30, tzinfo=NY)
    for i in range(n_barras):
        ts_utc = (base_ny + timedelta(minutes=i)).astimezone(UTC)
        o = open_0930 if i == 0 else close_dia
        v = volume_morning if i == 0 else 0.0
        barras.append(_barra(ts_utc, o=o, c=close_dia, v=v))
    return barras


def _gerar_dia_sem_morning(dia: date, *, close_dia: float, n_barras: int = 11) -> list[dict]:
    """Gera barras de um dia útil que começa às 10:00 NY (sem janela morning).

    A primeira barra (10:00) já dispara a classificação; como nenhuma barra
    caiu em ``[09:30, 10:00)``, o ``open`` do dia não é capturado e o
    classificador devolve motivo ``"dia-invalido"``.
    """
    barras: list[dict] = []
    base_ny = datetime(dia.year, dia.month, dia.day, 10, 0, tzinfo=NY)
    for i in range(n_barras):
        ts_utc = (base_ny + timedelta(minutes=i)).astimezone(UTC)
        barras.append(_barra(ts_utc, o=close_dia, c=close_dia, v=0.0))
    return barras


def _classificar_caso(
    volume_morning: float,
    gap_pct: float,
    *,
    baseline_morning: float = 1000.0,
    n_baseline: int = 2,
    n_dias_validos: Optional[int] = None,
) -> Optional[ResultadoClassificacao]:
    """Aquece o classificador com dias válidos e classifica um dia de teste.

    Alimenta ``n_dias_validos`` dias úteis válidos (cada um com
    ``volume_morning = baseline_morning`` e ``close = CLOSE_REF``) e depois
    um dia de teste com o ``volume_morning`` e o gap pedidos. Devolve o
    :class:`ResultadoClassificacao` do dia de teste (ou ``None``).

    O gap é fixado pelo ``open(09:30)`` do dia de teste:
    ``open = CLOSE_REF * (1 + gap_pct)`` ⇒ ``gap_pct`` exato (open > close).
    """
    if n_dias_validos is None:
        n_dias_validos = n_baseline
    params = ParametrosVvg(n_dias_baseline=n_baseline)
    clf = VvgClassifier(params)
    dias = _dias_uteis(date(2025, 7, 7), n_dias_validos + 1)
    for d in dias[:n_dias_validos]:
        for b in _gerar_dia(
            d,
            open_0930=CLOSE_REF,
            close_dia=CLOSE_REF,
            volume_morning=baseline_morning,
            n_barras=310,
        ):
            clf.on_barra(b)
    d_teste = dias[n_dias_validos]
    open_teste = CLOSE_REF * (1.0 + gap_pct)
    res: Optional[ResultadoClassificacao] = None
    for b in _gerar_dia(
        d_teste,
        open_0930=open_teste,
        close_dia=CLOSE_REF,
        volume_morning=volume_morning,
        n_barras=31,
    ):
        r = clf.on_barra(b)
        if r is not None:
            res = r
    return res


# ---------------------------------------------------------------------------
# Property 2 — monotonicidade em volume (R1.2)
# ---------------------------------------------------------------------------


class TestProperty2MonotoniaVolume:
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        baseline=_floats(100.0, 5000.0),
        vols=st.tuples(_floats(0.0, 30000.0), _floats(0.0, 30000.0)),
    )
    def test_aumentar_volume_nunca_inverte_para_false(
        self, baseline: float, vols: tuple[float, float]
    ) -> None:
        """Validates: Requirements 1.2

        Com gap fixo acima do threshold, se o dia é VVG-positivo com
        ``v_low``, então também é com qualquer ``v_high >= v_low``.
        """
        v_low, v_high = sorted(vols)
        gap = 0.01  # bem acima de threshold_gap_pct=0.0015
        res_low = _classificar_caso(v_low, gap, baseline_morning=baseline)
        res_high = _classificar_caso(v_high, gap, baseline_morning=baseline)
        assert res_low is not None and res_high is not None
        if res_low.vvg_positivo:
            assert res_high.vvg_positivo


# ---------------------------------------------------------------------------
# Property 3 — monotonicidade em gap (R1.2)
# ---------------------------------------------------------------------------


class TestProperty3MonotoniaGap:
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        baseline=_floats(100.0, 5000.0),
        gaps=st.tuples(_floats(0.0, 0.05), _floats(0.0, 0.05)),
    )
    def test_aumentar_gap_nunca_inverte_para_false(
        self, baseline: float, gaps: tuple[float, float]
    ) -> None:
        """Validates: Requirements 1.2

        Com volume fixo acima do limiar (``3 * baseline``), se o dia é
        VVG-positivo com ``g_low``, também é com qualquer ``g_high >= g_low``.
        """
        g_low, g_high = sorted(gaps)
        volume = baseline * 3.0  # garante volume >= 1.5 * baseline
        res_low = _classificar_caso(volume, g_low, baseline_morning=baseline)
        res_high = _classificar_caso(volume, g_high, baseline_morning=baseline)
        assert res_low is not None and res_high is not None
        if res_low.vvg_positivo:
            assert res_high.vvg_positivo


# ---------------------------------------------------------------------------
# Property 4 — warmup incompleto sempre devolve False (R1.4)
# ---------------------------------------------------------------------------


class TestProperty4WarmupIncompleto:
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        k=st.integers(min_value=0, max_value=2),
        volume=_floats(0.0, 30000.0),
        gap=_floats(0.0, 0.05),
    )
    def test_warmup_incompleto_sempre_false(
        self, k: int, volume: float, gap: float
    ) -> None:
        """Validates: Requirements 1.4

        Com ``n_dias_baseline=3`` e apenas ``k < 3`` dias válidos antes do
        dia de teste, o classificador devolve ``False`` com motivo
        ``"warmup-incompleto"``, independentemente de volume/gap.
        """
        res = _classificar_caso(
            volume,
            gap,
            baseline_morning=1000.0,
            n_baseline=3,
            n_dias_validos=k,
        )
        assert res is not None
        assert res.vvg_positivo is False
        assert res.motivo == "warmup-incompleto"


# ---------------------------------------------------------------------------
# Edge cases — baseline rolling, shift(1), dia inválido, fim de semana
# ---------------------------------------------------------------------------


class TestBaselineRolling:
    def test_baseline_reflete_ultimos_n_dias_uteis(self) -> None:
        """O baseline rolling reflete só os últimos ``n_dias_baseline`` dias."""
        clf = VvgClassifier(ParametrosVvg(n_dias_baseline=2))
        dias = _dias_uteis(date(2025, 7, 7), 5)
        mornings = [100.0, 200.0, 300.0, 400.0]
        for d, mv in zip(dias[:4], mornings):
            for b in _gerar_dia(
                d, open_0930=CLOSE_REF, close_dia=CLOSE_REF, volume_morning=mv, n_barras=310
            ):
                clf.on_barra(b)
        res: Optional[ResultadoClassificacao] = None
        for b in _gerar_dia(
            dias[4],
            open_0930=CLOSE_REF * 1.01,
            close_dia=CLOSE_REF,
            volume_morning=5000.0,
            n_barras=31,
        ):
            r = clf.on_barra(b)
            if r is not None:
                res = r
        assert res is not None
        # deque (maxlen=2) retém os 2 dias mais recentes: 300 e 400 → média 350.
        assert math.isclose(res.volume_baseline, 350.0, rel_tol=1e-9)
        assert clf.dias_no_baseline == 2

    def test_shift1_baseline_nao_inclui_dia_corrente(self) -> None:
        """``shift(1)``: o baseline não inclui o ``volume_morning`` do dia atual."""
        clf = VvgClassifier(ParametrosVvg(n_dias_baseline=2))
        dias = _dias_uteis(date(2025, 7, 7), 3)
        for d in dias[:2]:
            for b in _gerar_dia(
                d, open_0930=CLOSE_REF, close_dia=CLOSE_REF, volume_morning=100.0, n_barras=310
            ):
                clf.on_barra(b)
        res: Optional[ResultadoClassificacao] = None
        for b in _gerar_dia(
            dias[2],
            open_0930=CLOSE_REF * 1.01,
            close_dia=CLOSE_REF,
            volume_morning=99999.0,
            n_barras=31,
        ):
            r = clf.on_barra(b)
            if r is not None:
                res = r
        assert res is not None
        assert math.isclose(res.volume_morning, 99999.0, rel_tol=1e-9)
        # baseline = média dos 2 dias anteriores (100), sem o dia corrente.
        assert math.isclose(res.volume_baseline, 100.0, rel_tol=1e-9)

    def test_dia_invalido_menos_300_barras_nao_entra_baseline(self) -> None:
        """Dia com < MIN_BARRAS_DIA_VALIDO barras não entra no baseline."""
        assert MIN_BARRAS_DIA_VALIDO == 300
        clf = VvgClassifier(ParametrosVvg(n_dias_baseline=2))
        dias = _dias_uteis(date(2025, 7, 7), 4)
        # 2 dias válidos (morning=100 cada).
        for d in dias[:2]:
            for b in _gerar_dia(
                d, open_0930=CLOSE_REF, close_dia=CLOSE_REF, volume_morning=100.0, n_barras=310
            ):
                clf.on_barra(b)
        # Dia inválido: só 50 barras (< 300) e morning gigantesca.
        for b in _gerar_dia(
            dias[2], open_0930=CLOSE_REF, close_dia=CLOSE_REF, volume_morning=99999.0, n_barras=50
        ):
            clf.on_barra(b)
        # Dia de teste.
        res: Optional[ResultadoClassificacao] = None
        for b in _gerar_dia(
            dias[3],
            open_0930=CLOSE_REF * 1.01,
            close_dia=CLOSE_REF,
            volume_morning=5000.0,
            n_barras=31,
        ):
            r = clf.on_barra(b)
            if r is not None:
                res = r
        assert res is not None
        # O dia inválido foi descartado: baseline ainda reflete só os 2 válidos.
        assert math.isclose(res.volume_baseline, 100.0, rel_tol=1e-9)
        assert clf.dias_no_baseline == 2


class TestFimDeSemana:
    def test_sabado_descartado_devolve_none(self) -> None:
        """Sábado: nenhuma barra produz classificação (sempre ``None``)."""
        clf = VvgClassifier(ParametrosVvg(n_dias_baseline=2))
        sabado = date(2025, 7, 12)
        assert sabado.weekday() == 5  # sanity: é sábado
        resultados = [
            clf.on_barra(b)
            for b in _gerar_dia(
                sabado,
                open_0930=CLOSE_REF,
                close_dia=CLOSE_REF,
                volume_morning=5000.0,
                n_barras=310,
            )
        ]
        assert all(r is None for r in resultados)


# ---------------------------------------------------------------------------
# vvg_positivo só com AMBAS as condições + motivos canônicos
# ---------------------------------------------------------------------------


class TestCondicoesEMotivos:
    def test_motivo_ok_volume_e_gap(self) -> None:
        """volume >= 1.5*baseline E gap >= 0.0015 → vvg_positivo, motivo OK."""
        res = _classificar_caso(
            volume_morning=1500.0, gap_pct=0.002, baseline_morning=1000.0
        )
        assert res is not None
        assert res.vvg_positivo is True
        assert res.motivo == "OK"

    def test_motivo_volume_baixo(self) -> None:
        """volume < 1.5*baseline (mesmo com gap OK) → False, 'volume-baixo'."""
        res = _classificar_caso(
            volume_morning=1499.0, gap_pct=0.002, baseline_morning=1000.0
        )
        assert res is not None
        assert res.vvg_positivo is False
        assert res.motivo == "volume-baixo"

    def test_motivo_gap_baixo(self) -> None:
        """volume OK mas gap < 0.0015 → False, 'gap-baixo'."""
        res = _classificar_caso(
            volume_morning=1500.0, gap_pct=0.001, baseline_morning=1000.0
        )
        assert res is not None
        assert res.vvg_positivo is False
        assert res.motivo == "gap-baixo"

    def test_motivo_warmup_incompleto(self) -> None:
        """Histórico < n_dias_baseline → False, 'warmup-incompleto'."""
        res = _classificar_caso(
            volume_morning=1500.0,
            gap_pct=0.002,
            baseline_morning=1000.0,
            n_baseline=2,
            n_dias_validos=1,
        )
        assert res is not None
        assert res.vvg_positivo is False
        assert res.motivo == "warmup-incompleto"

    def test_motivo_dia_invalido_sem_janela_morning(self) -> None:
        """Dia útil sem barras em [09:30, 10:00) → False, 'dia-invalido'."""
        clf = VvgClassifier(ParametrosVvg(n_dias_baseline=2))
        dia = date(2025, 7, 7)  # segunda-feira
        res: Optional[ResultadoClassificacao] = None
        for b in _gerar_dia_sem_morning(dia, close_dia=CLOSE_REF, n_barras=11):
            r = clf.on_barra(b)
            if r is not None:
                res = r
        assert res is not None
        assert res.vvg_positivo is False
        assert res.motivo == "dia-invalido"
