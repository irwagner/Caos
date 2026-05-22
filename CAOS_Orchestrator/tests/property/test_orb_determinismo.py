"""Property-based test do determinismo da ORB ponta-a-ponta
(Property 20 do Spec 4 — Task 7).

Implementa **Property 20 — Determinismo da ORB**:

    For every pair of ``WalkForwardEngine.executar`` calls with same
    ``(seed, ConfiguracaoWalkForward, manifesto_hash, ParametrosORB)``,
    the resulting ``ResultadoWalkForward`` SHALL be byte-identical
    (mesmas janelas, mesmos trades, mesmos PnLs).

**Validates: Requirements 6.1, 6.2**

Reusa a infraestrutura de fixture sintético do Spec 2
(``test_walk_forward_determinismo``), trocando apenas a estratégia
para :class:`EstrategiaORB`. Como a ORB é puramente determinística
(R6.2 — sem random), a Property é uma reafirmação concreta da Property
14 com uma estratégia real plugada.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.data_manifest import DataManifestManager
from caos.walk_forward import (
    ConfiguracaoWalkForward,
    WalkForwardEngine,
)
from caos.walk_forward.estrategias.orb import EstrategiaORB
from caos.walk_forward.estrategias.orb_logica import ParametrosORB

UTC = timezone.utc

CSV_HEADER = "timestamp,open,high,low,close,volume\n"


# ---------------------------------------------------------------------------
# Helpers — gera fixture similar ao test_orb_walk_forward_integrado
# ---------------------------------------------------------------------------


def _gerar_dia_minimo(dia: datetime, personalidade: str) -> List[tuple]:
    """Versão compacta de ``_gerar_dia`` (12 barras de 30 min cada)."""
    inicio = datetime(dia.year, dia.month, dia.day, 13, 30, tzinfo=UTC)
    barras: List[tuple] = []
    for i in range(13):  # 13:30 → 19:30 a cada 30 min.
        ts = inicio + timedelta(minutes=i * 30)
        if i == 0:
            o, h, l, c = 21000.0, 21010.0, 20990.0, 21005.0
        else:
            if personalidade == "long":
                o = 21010 + i * 5
                h = o + 2
                l = o - 1
                c = o + 1
            elif personalidade == "short":
                o = 20990 - i * 5
                h = o + 1
                l = o - 2
                c = o - 1
            else:
                o = 21000 + ((i % 3) - 1) * 2
                h = o + 1
                l = o - 1
                c = o
        barras.append((ts, o, h, l, c, 1000.0))
    return barras


def _construir_fixture(raiz_pai: Path, n_dias_uteis: int) -> Path:
    raiz = raiz_pai / "dados" / "MNQ"
    raiz.mkdir(parents=True, exist_ok=True)
    inicio = datetime(2026, 1, 5)
    dias_uteis: List[tuple] = []
    atual = inicio
    while len(dias_uteis) < n_dias_uteis:
        if atual.weekday() < 5:
            personalidade = ["long", "short", "lateral"][len(dias_uteis) % 3]
            dias_uteis.append((atual, personalidade))
        atual = atual + timedelta(days=1)

    todas_linhas: List[str] = []
    for dia, personalidade in dias_uteis:
        for ts, o, h, l, c, v in _gerar_dia_minimo(dia, personalidade):
            ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            todas_linhas.append(f"{ts_iso},{o},{h},{l},{c},{v}")

    arquivo = raiz / "MNQ-orb-property.csv"
    arquivo.write_text(CSV_HEADER + "\n".join(todas_linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz).build()
    return raiz


# ---------------------------------------------------------------------------
# Estratégia composta para Hypothesis
# ---------------------------------------------------------------------------


@st.composite
def _config_e_parametros(draw):
    """Gera ``(ConfiguracaoWalkForward, ParametrosORB, n_dias)``."""
    treino = draw(st.integers(min_value=60, max_value=70))
    teste = draw(st.integers(min_value=10, max_value=12))
    passo = draw(st.integers(min_value=teste, max_value=teste + 5))
    seed = draw(st.integers(min_value=0, max_value=100_000))
    n_dias = draw(st.integers(min_value=treino + teste, max_value=treino + 3 * teste))
    cfg = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=treino,
        tamanho_teste_dias_uteis=teste,
        passo_dias_uteis=passo,
        granularidade="1m",
        seed=seed,
    )
    parametros = ParametrosORB(
        minutos_or=draw(st.integers(min_value=15, max_value=45)),
        risco_multiplicador=draw(
            st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False)
        ),
        alvo_multiplicador=draw(
            st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False)
        ),
    )
    return cfg, parametros, n_dias


# ---------------------------------------------------------------------------
# Property 20
# ---------------------------------------------------------------------------


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(cenario=_config_e_parametros())
def test_property_orb_determinismo(
    cenario: tuple,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 6.1, 6.2** (Property 20).

    Para qualquer ``(ConfiguracaoWalkForward, ParametrosORB,
    historico_sintetico)``, duas execuções de
    :meth:`WalkForwardEngine.executar` produzem o mesmo
    ``manifesto_hash``, mesmo número de janelas, e mesmas métricas
    por janela (numero_trades, pnl_total, status).
    """
    cfg, parametros, n_dias = cenario
    raiz_pai = tmp_path_factory.mktemp("orb_determinismo")
    raiz = _construir_fixture(raiz_pai, n_dias_uteis=n_dias)
    engine = WalkForwardEngine(raiz_dados=raiz)

    r1 = engine.executar(
        estrategia=EstrategiaORB(parametros=parametros),
        configuracao=cfg,
        fonte_dados=raiz,
        identificador="2026-04-15-01",
    )
    r2 = engine.executar(
        estrategia=EstrategiaORB(parametros=parametros),
        configuracao=cfg,
        fonte_dados=raiz,
        identificador="2026-04-15-01",
    )

    assert r1.manifesto_hash == r2.manifesto_hash
    assert len(r1.janelas) == len(r2.janelas)
    for i, (j1, j2) in enumerate(zip(r1.janelas, r2.janelas)):
        assert j1.status == j2.status, f"status divergiu na janela {i}"
        assert j1.numero_trades == j2.numero_trades, (
            f"numero_trades divergiu na janela {i}: {j1.numero_trades} vs {j2.numero_trades}"
        )
        assert j1.pnl_total == j2.pnl_total, (
            f"pnl_total divergiu na janela {i}: {j1.pnl_total} vs {j2.pnl_total}"
        )
    assert r1.status == r2.status
