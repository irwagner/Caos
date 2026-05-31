"""Property-based test da paridade Python ↔ C# da estratégia VVG
Late-Session Reversal (Property 11 do design — Tarefa 9).

Implementa **Property 11 — Paridade Python ↔ C# trade-a-trade (R6)**:

    Para N=200 sequências de barras OHLCV de minuto geradas por
    Hypothesis (timestamps UTC cobrindo múltiplos dias úteis, incluindo
    a janela 09:30-16:00 de Nova York sob EST e EDT), o plugin de
    PRODUÇÃO ``EstrategiaVvgLateSessionReversal`` (caminho A, pandas) e
    a porta de REFERÊNCIA ``VvgModeloCSharpPort`` (caminho B, que
    espelha literalmente a lógica que vai pro C#) emitem **exatamente os
    mesmos trades**: mesma direção, mesmo timestamp de entrada (resolução
    minuto), mesmo preço de entrada/saída, mesmo motivo de saída, mesmo
    número de trades e PnL/trade dentro de 5% (tolerância de R6).

**Validates: Requirements 6.2**

Por que o teste tem valor (não é tautológico)
---------------------------------------------
O caminho A (produção) e o caminho B (referência) são DUAS
implementações independentes da mesma especificação: A usa
``VvgClassifier`` + ``decidir_acao`` (pandas, estado imutável copiado);
B reimplementa classificador + decisão + motor de execução do zero
(Python puro, estado mutável estilo ``struct ref`` do C#). A porta B é
o "ground truth" do código C# (Tarefas 6/7). Se as duas convergem
trade-a-trade sob 200 sequências aleatórias, temos forte evidência de
que produção Python, referência Python e C# são equivalentes — que é o
objetivo do spec.

Cobertura de dias VVG-positivos (anti-teste-trivial)
----------------------------------------------------
Um gerador ingênuo de barras quase nunca produz um dia VVG-positivo
(exige, simultaneamente: warmup completo de 10 dias úteis no baseline,
``volume_morning >= 1.5 × baseline`` E ``gap >= 0.15%``). Sem dias
VVG-positivos, ambos os lados emitem 0 trades e a paridade passa
trivialmente.

Para evitar isso, o gerador é **dirigido**:

1. Sempre aquece com ``N_WARMUP_DIAS = 11`` dias úteis válidos (>= os
   10 do baseline) com volume "normal", estabelecendo um baseline
   estável de ``volume_morning``.
2. Em cada dia de Teste, com ~80% de probabilidade, FORÇA a condição
   VVG-positiva: injeta um gap de abertura grande (50-150 pts ≈
   0.24%-0.71%) e um pico de volume na janela morning (3×-5× o normal),
   garantindo ``volume_morning >= 1.5 × baseline`` E
   ``gap >= threshold``. Nos demais ~20%, mantém volume/gap normais
   (dia VVG-negativo → 0 trades dos dois lados — também testa paridade
   do caminho "sem trade").

A cobertura efetiva é registrada via ``hypothesis.event`` (visível com
``--hypothesis-show-statistics``) e ancorada por um teste determinístico
(:func:`test_paridade_dia_vvg_positivo_conhecido`) que GARANTE pelo
menos um cenário com trade emitido e valida a paridade nele.

Padrão herdado do Spec 4 (``test_orb_python_csharp_paridade.py``):
geração via ``@st.composite`` + comparação tolerante de decisões, com
``@settings(deadline=None)`` porque o caminho A itera DataFrames de
milhares de barras (I/O pandas lento no Windows).

Convenções: identificadores em inglês quando idiomático; docstrings e
comentários em pt-BR; termos técnicos em inglês.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from caos.estrategias_modelo.vvg import BarraVvgModelo, VvgModeloCSharpPort
from caos.walk_forward.estrategias.vvg_late_session_reversal import (
    EstrategiaVvgLateSessionReversal,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator

# ---------------------------------------------------------------------------
# Constantes do gerador
# ---------------------------------------------------------------------------

UTC = timezone.utc
_TZ_NY = ZoneInfo("America/New_York")

#: Preço-base do MNQ em torno do qual as barras oscilam (~21000).
BASE_PRICE: float = 21000.0

#: Volume por barra "normal" (warmup e dias não-forçados).
BASE_VOL: float = 100.0

#: Dias úteis de aquecimento (>= os 10 do baseline + 1 para fixar close(D-1)).
N_WARMUP_DIAS: int = 11

#: Máximo de dias de Teste por sequência (mantém o nº de trades pequeno: 0-2).
N_TEST_DIAS_MAX: int = 2

#: Barras por dia de warmup: 09:30→14:39 NY = 310 min. >= MIN_BARRAS_DIA_VALIDO
#: (300) para o dia entrar no baseline; warmup não precisa alcançar 15:50.
N_BARS_WARMUP: int = 310

#: Barras por dia de Teste: 09:30→15:59 NY = 390 min. Cobre a entrada
#: (14:30, índice 300) E o force-close (15:50, índice 380) — assim NENHUMA
#: posição fica aberta no ``finalizar`` (evita a divergência de motivo
#: "encerramento-forcado" vs "fim-de-dados" entre os dois lados).
N_BARS_TEST: int = 390

#: Índice de minuto da entrada (14:30 NY) e do force-close (15:50 NY).
_IDX_ENTRADA: int = 300
_IDX_ENCERRAMENTO: int = 380

#: Datas de início que cobrem tanto EST (inverno) quanto EDT (verão) e
#: atravessam as transições de horário de verão (mar/nov de 2025).
_DATAS_INICIO: Tuple[date, ...] = (
    date(2025, 1, 6),    # inverno (EST, UTC-5)
    date(2025, 3, 3),    # cruza início do DST (09/03/2025)
    date(2025, 7, 7),    # verão (EDT, UTC-4)
    date(2025, 10, 6),   # cruza fim do DST (02/11/2025)
    date(2025, 11, 17),  # inverno (EST, UTC-5)
)

#: Tolerância relativa de PnL por trade (R6).
TOL_PNL: float = 0.05

#: Tolerância absoluta de preço (em pontos) — os dois lados leem a MESMA
#: barra, então a diferença esperada é 0; a folga cobre apenas ruído de
#: ponto-flutuante na coerção UTC/pandas.
EPS_PRECO: float = 1e-6

#: Uma barra é a tupla posicional ``(timestamp_utc, open, high, low, close, volume)``.
Barra6 = Tuple[datetime, float, float, float, float, float]


# ---------------------------------------------------------------------------
# Helpers de construção de barras (puros — sem draws Hypothesis)
# ---------------------------------------------------------------------------


def _ts_utc(dia: date, minuto: int) -> datetime:
    """Timestamp UTC do ``minuto``-ésimo minuto a partir de 09:30 NY de ``dia``.

    Constrói o wall-clock de Nova York (naive) e o localiza em
    ``America/New_York`` antes de converter para UTC. Como todas as
    barras ficam em 09:30-15:59, nunca caímos na transição de DST (02:00
    NY) — não há horário ambíguo/inexistente.
    """
    naive_ny = datetime.combine(dia, time(9, 30)) + timedelta(minutes=minuto)
    aware_ny = naive_ny.replace(tzinfo=_TZ_NY)
    return aware_ny.astimezone(UTC)


def _proximos_dias_uteis(dia0: date, n: int) -> List[date]:
    """Devolve ``n`` dias úteis consecutivos a partir de ``dia0`` (inclusive)."""
    dias: List[date] = []
    d = dia0
    while len(dias) < n:
        if d.weekday() < 5:  # 0-4 = seg-sex
            dias.append(d)
        d = d + timedelta(days=1)
    return dias


def _construir_dia(
    dia: date,
    open_price: float,
    vol_mult: float,
    drift: float,
    n_bars: int,
) -> List[Barra6]:
    """Gera as barras de 1 minuto de um dia (preços OHLCV coerentes).

    - ``open_price`` — preço da primeira barra (09:30 NY); o gap em
      relação ao dia anterior é embutido aqui pelo chamador.
    - ``vol_mult`` — multiplicador de volume aplicado SÓ na janela morning
      ``[09:30, 10:00)`` (índices 0-29). Controla ``volume_morning``.
    - ``drift`` — deslocamento de preço (pts) de 09:30 até 14:30 (índice
      300); define o sinal do drift (entrada é OPOSTA ao drift).
    - O range intrabar é pequeno (amp=1 + ruído<=0.5) ⇒ stop (472.25) e
      target (944.25) NUNCA são tocados ⇒ trades fecham sempre no
      force-close das 15:50 (motivo "encerramento-forcado" nos dois lados).

    Invariantes de barra válida: ``high >= max(open, close)`` e
    ``low <= min(open, close)`` e ``volume >= 0``.
    """
    bars: List[Barra6] = []
    amp = 1.0
    prev_c: float | None = None
    for i in range(n_bars):
        ts = _ts_utc(dia, i)
        # Caminho do close: rampa linear até o índice de entrada, depois constante.
        if i <= _IDX_ENTRADA:
            base_c = open_price + drift * (i / float(_IDX_ENTRADA))
        else:
            base_c = open_price + drift
        ruido = 0.5 * math.sin(i * 0.7)  # |ruído| <= 0.5 — não inverte o drift
        c = base_c + ruido
        o = open_price if prev_c is None else prev_c
        h = max(o, c) + amp
        l = min(o, c) - amp
        v = (BASE_VOL * vol_mult) if i < 30 else BASE_VOL
        bars.append((ts, o, h, l, c, v))
        prev_c = c
    return bars


def _df_de_barras(bars: Sequence[Barra6]) -> pd.DataFrame:
    """Monta o DataFrame canônico (schema do Walk-Forward) a partir das tuplas."""
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(b[0]) for b in bars],
            "open": [b[1] for b in bars],
            "high": [b[2] for b in bars],
            "low": [b[3] for b in bars],
            "close": [b[4] for b in bars],
            "volume": [b[5] for b in bars],
        }
    )


def _modelos_de_barras(bars: Sequence[Barra6]) -> List[BarraVvgModelo]:
    """Converte as tuplas em ``BarraVvgModelo`` (entrada da porta de referência)."""
    return [
        BarraVvgModelo(
            timestamp=b[0], open=b[1], high=b[2], low=b[3], close=b[4], volume=b[5]
        )
        for b in bars
    ]


# ---------------------------------------------------------------------------
# Gerador Hypothesis: aquecimento + dias de Teste (alguns VVG-positivos forçados)
# ---------------------------------------------------------------------------


@st.composite
def _cenario_vvg(draw) -> Tuple[List[Barra6], List[Barra6]]:
    """Gera ``(warmup_bars, test_bars)`` a partir da MESMA fonte de dados.

    Aquece com :data:`N_WARMUP_DIAS` dias úteis "normais" (baseline
    estável) e adiciona 1-2 dias de Teste; cada dia de Teste tem ~80% de
    chance de ser FORÇADO a VVG-positivo (gap grande + pico de volume).
    """
    dia0 = draw(st.sampled_from(_DATAS_INICIO))
    n_test = draw(st.integers(min_value=1, max_value=N_TEST_DIAS_MAX))
    dias = _proximos_dias_uteis(dia0, N_WARMUP_DIAS + n_test)

    warmup_bars: List[Barra6] = []
    test_bars: List[Barra6] = []
    prev_close = BASE_PRICE

    for idx, dia in enumerate(dias):
        is_test = idx >= N_WARMUP_DIAS
        if not is_test:
            # Dia de warmup: sem gap, sem drift, volume normal.
            bars = _construir_dia(
                dia, prev_close, vol_mult=1.0, drift=0.0, n_bars=N_BARS_WARMUP
            )
        else:
            forcar = draw(st.integers(min_value=0, max_value=4)) != 0  # ~80% True
            if forcar:
                # Gap >= 0.15% (50/21000 ≈ 0.24%) e pico de volume 3×-5×.
                gap_mag = draw(
                    st.floats(min_value=50.0, max_value=150.0, allow_nan=False)
                )
                gap = gap_mag if draw(st.booleans()) else -gap_mag
                vol_mult = draw(
                    st.floats(min_value=3.0, max_value=5.0, allow_nan=False)
                )
                drift_mag = draw(
                    st.floats(min_value=20.0, max_value=80.0, allow_nan=False)
                )
                drift = drift_mag if draw(st.booleans()) else -drift_mag
            else:
                # Dia VVG-negativo: gap pequeno (< threshold) e volume normal.
                gap = draw(st.floats(min_value=-8.0, max_value=8.0, allow_nan=False))
                vol_mult = 1.0
                drift = draw(
                    st.floats(min_value=-15.0, max_value=15.0, allow_nan=False)
                )
            open_price = prev_close + gap
            bars = _construir_dia(
                dia, open_price, vol_mult=vol_mult, drift=drift, n_bars=N_BARS_TEST
            )

        prev_close = bars[-1][4]
        (test_bars if is_test else warmup_bars).extend(bars)

    return warmup_bars, test_bars


# ---------------------------------------------------------------------------
# Execução dos dois caminhos
# ---------------------------------------------------------------------------


def _rodar_producao(
    warmup_bars: Sequence[Barra6], test_bars: Sequence[Barra6]
) -> Tuple[List[Trade], List[dict]]:
    """Caminho A — plugin de produção (pandas).

    Aquece via ``treinar`` (DataFrame) e dirige ``on_barra`` por barra do
    Periodo_Teste através de um ``BarrasTesteIterator`` (igual ao
    ``BacktestRunner`` do Spec 2). Devolve os trades e os metadados
    paralelos (que carregam ``motivo_saida``).
    """
    est = EstrategiaVvgLateSessionReversal()
    est.treinar(_df_de_barras(warmup_bars))
    iterator = BarrasTesteIterator(_df_de_barras(test_bars))
    for barra in iterator:
        est.on_barra(barra, iterator)
    trades = list(est.finalizar())
    return trades, list(est.metadados_trades)


def _rodar_referencia(
    warmup_bars: Sequence[Barra6], test_bars: Sequence[Barra6]
):
    """Caminho B — porta de referência (espelho do C#, Python puro)."""
    port = VvgModeloCSharpPort()
    return port.processar(_modelos_de_barras(warmup_bars), _modelos_de_barras(test_bars))


# ---------------------------------------------------------------------------
# Comparação de paridade (R6, tolerância 5%)
# ---------------------------------------------------------------------------


def _mesmo_minuto(a: datetime, b: datetime) -> bool:
    """Compara dois timestamps em resolução de minuto (ambos coeridos a UTC)."""
    aa = a.astimezone(UTC).replace(second=0, microsecond=0)
    bb = b.astimezone(UTC).replace(second=0, microsecond=0)
    return aa == bb


def _pnl_dentro_tolerancia(pnl_a: float, pnl_b: float) -> bool:
    """``True`` se os PnLs batem dentro de 5% (ou são ~iguais perto de zero)."""
    if abs(pnl_a - pnl_b) <= 1e-6:
        return True
    denom = max(abs(pnl_a), abs(pnl_b), 1.0)
    return abs(pnl_a - pnl_b) / denom <= TOL_PNL


def _assert_paridade(
    trades_a: Sequence[Trade],
    metadados_a: Sequence[dict],
    trades_b,
) -> None:
    """Exige paridade trade-a-trade entre os dois caminhos (R6)."""
    # Número de trades idêntico nas duas portas.
    assert len(trades_a) == len(trades_b), (
        f"nº de trades diverge: produção={len(trades_a)} vs "
        f"referência={len(trades_b)}"
    )

    for i, (ta, tb) in enumerate(zip(trades_a, trades_b)):
        # Direção idêntica (long/short).
        assert ta.lado == tb.lado, f"trade {i}: lado {ta.lado} != {tb.lado}"

        # Timestamp de entrada idêntico (resolução minuto).
        assert _mesmo_minuto(ta.entrada_timestamp, tb.entrada_timestamp), (
            f"trade {i}: entrada {ta.entrada_timestamp} != {tb.entrada_timestamp}"
        )
        # Timestamp de saída idêntico (resolução minuto).
        assert _mesmo_minuto(ta.saida_timestamp, tb.saida_timestamp), (
            f"trade {i}: saída {ta.saida_timestamp} != {tb.saida_timestamp}"
        )

        # Preço de entrada idêntico.
        assert abs(ta.entrada_preco - tb.entrada_preco) <= EPS_PRECO, (
            f"trade {i}: entrada_preco {ta.entrada_preco} != {tb.entrada_preco}"
        )
        # Preço de saída idêntico (tolerância pequena).
        assert abs(ta.saida_preco - tb.saida_preco) <= EPS_PRECO, (
            f"trade {i}: saida_preco {ta.saida_preco} != {tb.saida_preco}"
        )

        # Motivo de saída idêntico (produção guarda em metadados paralelos).
        motivo_a = metadados_a[i]["motivo_saida"]
        assert motivo_a == tb.motivo_saida, (
            f"trade {i}: motivo {motivo_a} != {tb.motivo_saida}"
        )

        # PnL por trade dentro de 5%.
        pnl_a = ta.pnl_pontos()
        pnl_b = tb.pnl_pontos()
        assert _pnl_dentro_tolerancia(pnl_a, pnl_b), (
            f"trade {i}: PnL fora de 5% — produção={pnl_a}, referência={pnl_b}"
        )


# ---------------------------------------------------------------------------
# Property 11 — paridade Python(produção) ↔ porta(referência/C#)
# ---------------------------------------------------------------------------


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)
@given(cenario=_cenario_vvg())
def test_property_vvg_paridade_py_cs(cenario: Tuple[List[Barra6], List[Barra6]]) -> None:
    """**Validates: Requirements 6.2** (Property 11).

    Para qualquer sequência de barras OHLCV gerada (com dias VVG-positivos
    forçados), o plugin de produção e a porta de referência emitem o
    mesmo conjunto de trades, dentro da tolerância de 5% do R6.
    """
    warmup_bars, test_bars = cenario

    trades_prod, metadados_prod = _rodar_producao(warmup_bars, test_bars)
    trades_ref = _rodar_referencia(warmup_bars, test_bars)

    # Cobertura: registra quantos trades surgiram (visível com
    # --hypothesis-show-statistics). Garante que o teste não é trivial.
    event(
        "dia_vvg_positivo_com_trade"
        if len(trades_prod) > 0
        else "sem_trade_(vvg_negativo)"
    )
    event(f"n_trades={len(trades_prod)}")

    _assert_paridade(trades_prod, metadados_prod, trades_ref)


# ---------------------------------------------------------------------------
# Âncora determinística de cobertura — GARANTE >= 1 trade e valida a paridade
# ---------------------------------------------------------------------------


def _cenario_fixo_vvg_positivo() -> Tuple[List[Barra6], List[Barra6]]:
    """Cenário fixo conhecido: 11 dias de warmup + 1 dia VVG-positivo forçado.

    Gap de +80 pts (~0.38%) e volume morning 4× ⇒ ``vvg_positivo`` certo;
    drift de +40 pts ⇒ entrada SHORT (oposta ao drift).
    """
    dias = _proximos_dias_uteis(date(2025, 7, 7), N_WARMUP_DIAS + 1)
    warmup_bars: List[Barra6] = []
    test_bars: List[Barra6] = []
    prev_close = BASE_PRICE
    for idx, dia in enumerate(dias):
        if idx < N_WARMUP_DIAS:
            bars = _construir_dia(
                dia, prev_close, vol_mult=1.0, drift=0.0, n_bars=N_BARS_WARMUP
            )
            warmup_bars.extend(bars)
        else:
            bars = _construir_dia(
                dia, prev_close + 80.0, vol_mult=4.0, drift=40.0, n_bars=N_BARS_TEST
            )
            test_bars.extend(bars)
        prev_close = bars[-1][4]
    return warmup_bars, test_bars


def test_paridade_dia_vvg_positivo_conhecido() -> None:
    """Âncora de cobertura: um dia VVG-positivo conhecido produz exatamente
    1 trade (SHORT, force-close) IDÊNTICO nos dois caminhos.

    Complementa a Property 11 garantindo que o caminho que EMITE trade é
    de fato exercido (o gerador aleatório poderia, em teoria, nunca
    forçar um dia positivo).

    **Validates: Requirements 6.2**
    """
    warmup_bars, test_bars = _cenario_fixo_vvg_positivo()

    trades_prod, metadados_prod = _rodar_producao(warmup_bars, test_bars)
    trades_ref = _rodar_referencia(warmup_bars, test_bars)

    # O dia forçado DEVE gerar exatamente 1 trade em ambos os caminhos.
    assert len(trades_prod) == 1, f"esperado 1 trade na produção, veio {len(trades_prod)}"
    assert len(trades_ref) == 1, f"esperado 1 trade na referência, veio {len(trades_ref)}"

    # Drift positivo (+40) ⇒ entrada OPOSTA = SHORT (R2.2).
    assert trades_prod[0].lado == "short"
    assert trades_ref[0].lado == "short"

    # Sem stop/target tocado ⇒ saída por force-close das 15:50.
    assert metadados_prod[0]["motivo_saida"] == "encerramento-forcado"
    assert trades_ref[0].motivo_saida == "encerramento-forcado"

    _assert_paridade(trades_prod, metadados_prod, trades_ref)
