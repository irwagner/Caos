"""Property-based test do ``WalkForwardEngine`` (Property 14 do design).

Implementa **Property 14 — Walk-Forward Determinismo** do ``design.md``
do Spec 2:

    For every pair of executions with same
    ``(seed, ConfiguracaoWalkForward, manifesto_hash, estrategia_versao)``,
    the resulting ``ResultadoWalkForward`` SHALL be byte-identical
    (after JSON canonical serialization).

**Validates: Requirements 7.1, 7.2**

Estratégia
----------
Geramos dados sintéticos do MNQ in-memory: ``n_dias_uteis`` business
days a partir de 2024-01-02, com 1 barra/dia à meia-noite UTC. O
``manifesto.json`` é construído via :class:`DataManifestManager` para
que :class:`SkillDataReader` (invocado pelo
:class:`WalkForwardEngine`) consiga validar integridade. A estratégia
plugada é uma versão simplificada do ``EstrategiaSempreVencedora``
usada nos testes unitários da Task 6: cada barra de Teste produz 1
trade vencedor de +1 ponto (modelo
:class:`caos.walk_forward.metricas.Trade`).

Para cada amostra Hypothesis, executamos
:meth:`WalkForwardEngine.executar` duas vezes com a **mesma** seed
e validamos:

1. ``manifesto_hash`` é byte-idêntico entre execuções (R4.3 + R7.1).
2. ``len(janelas)`` é igual.
3. Para cada janela ``i``, ``numero_trades_i`` é igual entre execuções.
4. Para cada janela ``i``, ``pnl_total_i`` é igual entre execuções.
5. ``status`` agregado é igual entre execuções (corolário canônico de
   determinismo — se quaisquer das métricas acima mudasse, o aborto
   por taxa de falhas também poderia divergir).

Para ``max_examples`` mantemos ``20`` no profile ``default`` e ``50``
quando o profile ``gate`` está ativo: o teste cria filesystem
temporário e roda o pipeline 2x por amostra, então é dispendioso.

Sub-propriedade complementar (R7.2)
-----------------------------------
``versoes_dependencias`` carrega ``pandas`` e ``numpy``. Como o
ambiente de teste é o mesmo entre as duas execuções, esses valores
também devem coincidir.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.data_manifest import DataManifestManager
from caos.walk_forward import (
    ConfiguracaoWalkForward,
    WalkForwardEngine,
)
from caos.walk_forward.metricas import Trade as TradeRico
from caos.walk_forward.runner import BarrasTesteIterator

UTC = timezone.utc

CSV_HEADER = "timestamp,open,high,low,close,volume\n"


# ---------------------------------------------------------------------------
# Estratégia plugável (réplica enxuta do test_walk_forward_engine.py)
# ---------------------------------------------------------------------------


class _EstrategiaSempreVencedora:
    """Estratégia determinística: 1 trade vencedor (+1 ponto) por barra de Teste.

    Usa o modelo rico :class:`caos.walk_forward.metricas.Trade` para que
    o ``BacktestRunner`` delegue cálculo completo ao
    ``MetricasCalculator``. Reseta o buffer interno a cada chamada de
    ``treinar`` (a engine reusa a mesma instância entre janelas).
    """

    NOME = "EstrategiaSempreVencedora"

    def __init__(self) -> None:
        self._trades: list[TradeRico] = []

    def treinar(self, historico: pd.DataFrame) -> None:
        self._trades = []

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        ts = barra["timestamp"]
        entrada = ts
        saida = ts + pd.Timedelta(minutes=1)
        self._trades.append(
            TradeRico(
                entrada_timestamp=entrada.to_pydatetime(),
                saida_timestamp=saida.to_pydatetime(),
                entrada_preco=21000.0,
                saida_preco=21001.0,
                lado="long",
                contratos=1,
                mfe_pontos=1.0,
                mae_pontos=0.0,
            )
        )

    def finalizar(self) -> Sequence[TradeRico]:
        return list(self._trades)


# ---------------------------------------------------------------------------
# Helpers de fixture sintético
# ---------------------------------------------------------------------------


def _construir_dados_sinteticos(
    raiz_pai: Path,
    *,
    n_dias_uteis: int,
) -> Path:
    """Cria ``raiz_pai/dados/MNQ/MNQ-sintetico.csv`` + ``manifesto.json``.

    Cada dia útil tem 1 barra à meia-noite UTC. Preço cresce 1 ponto
    por dia. Retorna o path da raiz (``dados/MNQ/``).
    """
    raiz = raiz_pai / "dados" / "MNQ"
    raiz.mkdir(parents=True, exist_ok=True)
    timestamps = pd.bdate_range("2024-01-02", periods=n_dias_uteis, tz="UTC")
    linhas: list[str] = []
    for i, ts in enumerate(timestamps):
        po = 21000.0 + i
        ph = po + 1.0
        pl = po - 1.0
        pc = po + 0.5
        vol = 1000.0
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        linhas.append(f"{ts_iso},{po},{ph},{pl},{pc},{vol}")
    arquivo = raiz / "MNQ-sintetico.csv"
    arquivo.write_text(CSV_HEADER + "\n".join(linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz).build()
    return raiz


# ---------------------------------------------------------------------------
# Estratégia composta para Hypothesis
# ---------------------------------------------------------------------------


@st.composite
def _config_e_n_dias(draw: st.DrawFn) -> tuple[ConfiguracaoWalkForward, int]:
    """Gera ``(ConfiguracaoWalkForward, n_dias_uteis)`` que produz ≥ 1 janela.

    - ``treino`` em ``[60, 70]`` (faixa pequena para teste rápido; o teto
      do model é 504, mas histórico pequeno acelera I/O).
    - ``teste``  em ``[10, 12]``.
    - ``passo``  em ``[teste, teste + 5]`` (R3.1 — passo >= teste).
    - ``seed``   em ``[0, 100_000]``.
    - ``n_dias`` em ``[treino + teste, treino + 4 * teste]`` para
      garantir ≥ 1 janela e ≤ ~5 janelas (controla custo).
    """
    treino = draw(st.integers(min_value=60, max_value=70))
    teste = draw(st.integers(min_value=10, max_value=12))
    passo = draw(st.integers(min_value=teste, max_value=teste + 5))
    seed = draw(st.integers(min_value=0, max_value=100_000))
    n_dias = draw(
        st.integers(min_value=treino + teste, max_value=treino + 4 * teste)
    )
    cfg = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=treino,
        tamanho_teste_dias_uteis=teste,
        passo_dias_uteis=passo,
        granularidade="1m",
        seed=seed,
    )
    return cfg, n_dias


# ---------------------------------------------------------------------------
# Property 14
# ---------------------------------------------------------------------------


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(cfg_e_n=_config_e_n_dias())
def test_property_walk_forward_determinismo(
    cfg_e_n: tuple[ConfiguracaoWalkForward, int],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 7.1, 7.2** (Property 14).

    Para qualquer ``(seed, ConfiguracaoWalkForward, manifesto_hash,
    estrategia_versao)``, duas execuções consecutivas do
    :class:`WalkForwardEngine` produzem ``manifesto_hash`` idêntico,
    mesmas ``numero_trades`` por janela, e mesmo ``pnl_total`` por
    janela. ``versoes_dependencias`` (R7.2) também coincide entre as
    execuções.
    """
    cfg, n_dias = cfg_e_n
    raiz_pai = tmp_path_factory.mktemp("walk_forward_determinismo")
    raiz = _construir_dados_sinteticos(raiz_pai, n_dias_uteis=n_dias)
    engine = WalkForwardEngine(raiz_dados=raiz)
    identificador = "2026-01-15-01"

    r1 = engine.executar(
        estrategia=_EstrategiaSempreVencedora(),
        configuracao=cfg,
        fonte_dados=raiz,
        identificador=identificador,
    )
    r2 = engine.executar(
        estrategia=_EstrategiaSempreVencedora(),
        configuracao=cfg,
        fonte_dados=raiz,
        identificador=identificador,
    )

    # (1) manifesto_hash idêntico (R4.3 + R7.1).
    assert r1.manifesto_hash == r2.manifesto_hash, (
        f"manifesto_hash divergiu entre execuções: "
        f"{r1.manifesto_hash} != {r2.manifesto_hash}"
    )

    # (2) Mesmo número de janelas.
    assert len(r1.janelas) == len(r2.janelas), (
        f"len(janelas) divergiu: {len(r1.janelas)} vs {len(r2.janelas)}"
    )

    # (3) e (4) — métricas-âncora coincidem janela a janela.
    for i, (j1, j2) in enumerate(zip(r1.janelas, r2.janelas)):
        assert j1.numero_trades == j2.numero_trades, (
            f"numero_trades divergiu na janela {i}: "
            f"{j1.numero_trades} vs {j2.numero_trades}"
        )
        assert j1.pnl_total == j2.pnl_total, (
            f"pnl_total divergiu na janela {i}: "
            f"{j1.pnl_total} vs {j2.pnl_total}"
        )

    # (5) Status agregado coincide.
    assert r1.status == r2.status, (
        f"status agregado divergiu: {r1.status!r} vs {r2.status!r}"
    )

    # Sub-propriedade R7.2 — versões de pandas e numpy registradas e
    # iguais entre execuções no mesmo ambiente.
    assert "pandas" in r1.versoes_dependencias
    assert "numpy" in r1.versoes_dependencias
    assert r1.versoes_dependencias == r2.versoes_dependencias
