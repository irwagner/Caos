"""Teste de integração ORB ↔ Walk-Forward (Spec 4 — Task 5).

Cobre R8.2: roda :class:`~caos.walk_forward.engine.WalkForwardEngine`
ponta-a-ponta usando :class:`~caos.walk_forward.estrategias.orb.EstrategiaORB`
sobre fixture sintético com 3 sessões. Espera ``status="concluido"`` e
ao menos 1 trade (sessões com rompimento).

O fixture sintético gera barras 1-minuto durante a Janela_Sessao_RTH
(13:30–20:00 UTC) por N dias úteis. Cada dia tem uma "personalidade":

- Dia A (rompimento LONG): preço sobe linearmente após o OR.
- Dia B (rompimento SHORT): preço cai linearmente após o OR.
- Dia C (lateralização): preço oscila dentro do OR sem romper.

Os dias se alternam para que o histórico cubra os 3 cenários e o
Walk-Forward rode janelas com mistura realista.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import List

import pandas as pd
import pytest

from caos.data_manifest import DataManifestManager
from caos.walk_forward import (
    ConfiguracaoWalkForward,
    ResultadoWalkForward,
    WalkForwardEngine,
)
from caos.walk_forward.estrategias.orb import EstrategiaORB
from caos.walk_forward.estrategias.orb_logica import ParametrosORB

UTC = timezone.utc

CSV_HEADER = "timestamp,open,high,low,close,volume\n"


# ---------------------------------------------------------------------------
# Fixture sintético
# ---------------------------------------------------------------------------


def _gerar_dia(
    dia: datetime,
    personalidade: str,
) -> List[tuple[datetime, float, float, float, float, float]]:
    """Gera barras 1-min de 13:30 a 20:00 UTC para um dia.

    Personalidades:
    - "long": preço cresce após o OR (rompe high_or em LONG).
    - "short": preço cai após o OR (rompe low_or em SHORT).
    - "lateral": preço oscila dentro do OR (sem rompimento).
    """
    # 13:30 → 20:00 = 6h30 = 390 minutos.
    inicio = datetime(dia.year, dia.month, dia.day, 13, 30, tzinfo=UTC)
    barras: List[tuple] = []
    base = 21000.0
    for i in range(390):
        ts = inicio + timedelta(minutes=i)
        if i < 30:
            # Periodo OR: preço oscila entre 21000 e 21010.
            o = base + (i % 5)
            h = o + 5
            l = o - 5
            c = o + 1
        else:
            if personalidade == "long":
                # Após OR, preço sobe 1 ponto/min até 100 acima do high.
                o = 21010 + (i - 30) * 0.5
                h = o + 1
                l = o - 1
                c = o + 0.5
            elif personalidade == "short":
                o = 20990 - (i - 30) * 0.5
                h = o + 1
                l = o - 1
                c = o - 0.5
            else:  # lateral
                # Oscila entre 21002 e 21008 (dentro do OR formado em [20995, 21015]).
                o = 21005 + ((i - 30) % 6 - 3)
                h = o + 1
                l = o - 1
                c = o
        barras.append((ts, o, h, l, c, 1000.0))
    return barras


def _construir_workspace_com_3_sessoes(raiz_pai: Path) -> Path:
    """Cria ``dados/MNQ/`` com 3 sessões consecutivas (long/short/lateral)."""
    raiz = raiz_pai / "dados" / "MNQ"
    raiz.mkdir(parents=True, exist_ok=True)

    # 3 dias úteis a partir de 2026-01-05 (segunda).
    dias = [
        (datetime(2026, 1, 5), "long"),
        (datetime(2026, 1, 6), "short"),
        (datetime(2026, 1, 7), "lateral"),
    ]

    todas_linhas: List[str] = []
    for dia, personalidade in dias:
        for ts, o, h, l, c, v in _gerar_dia(dia, personalidade):
            ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            todas_linhas.append(f"{ts_iso},{o},{h},{l},{c},{v}")

    arquivo = raiz / "MNQ-orb-fixture.csv"
    arquivo.write_text(CSV_HEADER + "\n".join(todas_linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz).build()
    return raiz


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def _config_wf_minimo() -> ConfiguracaoWalkForward:
    """Configuração mínima do Walk-Forward para fixture de 3 dias.

    Como o fixture só tem 3 dias úteis, escolhemos treino=1 e teste=1
    para o JanelaGenerator produzir pelo menos 1 janela válida. Isso é
    artificial mas suficiente para o smoke test de integração.
    """
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,  # mínimo do model
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        seed=42,
    )


def test_orb_executa_no_walk_forward_com_dados_suficientes(tmp_path: Path) -> None:
    """Smoke test ponta-a-ponta: Walk-Forward + ORB com histórico ≥ 70 dias."""
    # Para o Walk-Forward exigir >= 60+10 dias úteis, geramos um histórico
    # mais longo: 80 dias úteis com personalidades alternadas.
    raiz_dados = tmp_path / "dados" / "MNQ"
    raiz_dados.mkdir(parents=True, exist_ok=True)

    inicio = datetime(2026, 1, 5)
    dias_uteis: List[tuple[datetime, str]] = []
    atual = inicio
    while len(dias_uteis) < 80:
        if atual.weekday() < 5:
            personalidade = ["long", "short", "lateral"][len(dias_uteis) % 3]
            dias_uteis.append((atual, personalidade))
        atual = atual + timedelta(days=1)

    todas_linhas: List[str] = []
    for dia, personalidade in dias_uteis:
        for ts, o, h, l, c, v in _gerar_dia(dia, personalidade):
            ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            todas_linhas.append(f"{ts_iso},{o},{h},{l},{c},{v}")

    arquivo = raiz_dados / "MNQ-orb.csv"
    arquivo.write_text(CSV_HEADER + "\n".join(todas_linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz_dados).build()

    engine = WalkForwardEngine(raiz_dados=raiz_dados)
    estrategia = EstrategiaORB(parametros=ParametrosORB(minutos_or=30))
    resultado = engine.executar(
        estrategia=estrategia,
        configuracao=_config_wf_minimo(),
        fonte_dados=raiz_dados,
        identificador="2026-04-15-01",
    )

    assert isinstance(resultado, ResultadoWalkForward)
    assert resultado.status == "concluido", (
        f"esperava status='concluido'; recebido {resultado.status} "
        f"({len(resultado.janelas)} janelas)"
    )
    assert resultado.estrategia == "EstrategiaORB"
    # Ao menos 1 janela deve ter trades (dias "long" e "short" no Teste rompem o OR).
    assert any(j.numero_trades >= 1 for j in resultado.janelas), (
        "esperava pelo menos 1 janela com trades; "
        f"todas estão com 0 trades: {[j.numero_trades for j in resultado.janelas]}"
    )


def test_orb_estrategia_e_deterministica(tmp_path: Path) -> None:
    """R6.1 — duas execuções idênticas produzem trades idênticos."""
    raiz_dados = tmp_path / "dados" / "MNQ"
    raiz_dados.mkdir(parents=True, exist_ok=True)

    inicio = datetime(2026, 1, 5)
    dias_uteis: List[tuple[datetime, str]] = []
    atual = inicio
    while len(dias_uteis) < 80:
        if atual.weekday() < 5:
            personalidade = ["long", "short", "lateral"][len(dias_uteis) % 3]
            dias_uteis.append((atual, personalidade))
        atual = atual + timedelta(days=1)

    todas_linhas: List[str] = []
    for dia, personalidade in dias_uteis:
        for ts, o, h, l, c, v in _gerar_dia(dia, personalidade):
            ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            todas_linhas.append(f"{ts_iso},{o},{h},{l},{c},{v}")
    arquivo = raiz_dados / "MNQ-det.csv"
    arquivo.write_text(CSV_HEADER + "\n".join(todas_linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz_dados).build()

    engine = WalkForwardEngine(raiz_dados=raiz_dados)
    cfg = _config_wf_minimo()

    r1 = engine.executar(
        estrategia=EstrategiaORB(),
        configuracao=cfg,
        fonte_dados=raiz_dados,
        identificador="2026-04-15-02",
    )
    r2 = engine.executar(
        estrategia=EstrategiaORB(),
        configuracao=cfg,
        fonte_dados=raiz_dados,
        identificador="2026-04-15-02",
    )

    assert r1.status == r2.status
    assert r1.manifesto_hash == r2.manifesto_hash
    assert len(r1.janelas) == len(r2.janelas)
    for j1, j2 in zip(r1.janelas, r2.janelas):
        assert j1.numero_trades == j2.numero_trades
        assert j1.pnl_total == j2.pnl_total
        assert j1.status == j2.status


def test_orb_finaliza_devolve_lista_de_trades(tmp_path: Path) -> None:
    """Sanity check direto da `EstrategiaORB.finalizar` sem o Engine."""
    estrategia = EstrategiaORB()
    estrategia.treinar(pd.DataFrame())
    trades = estrategia.finalizar()
    assert trades == []


def test_orb_construtor_sem_parametros_usa_defaults() -> None:
    estrategia = EstrategiaORB()
    p = estrategia.parametros
    assert p.minutos_or == 30
    assert p.risco_multiplicador == 1.0
    assert p.alvo_multiplicador == 2.0
