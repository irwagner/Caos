"""Testes unitários do ``WalkForwardEngine`` (Spec 2 — Task 6).

Cobre **R7** (reprodutibilidade) e **R10** (tratamento de falhas) do
``requirements.md`` do Spec 2.

Cenários cobertos:

1. Caminho feliz com fixture sintético de 3 janelas: pipeline orquestra
   integridade → geração → execução → agregação e devolve
   :class:`ResultadoWalkForward` com ``status="concluido"``,
   ``len(janelas) == 3``, ``manifesto_hash`` SHA-256, e
   ``versoes_dependencias`` populado com pandas e numpy.
2. Manifesto inválido (modificado após build): engine devolve
   :class:`ResultadoWalkForward` com ``status="manifesto-invalido"`` e
   ``janelas=[]`` (R4.2).
3. Taxa de falhas > 30% (estratégia que sempre quebra): engine devolve
   ``status="abortado-por-falhas"`` (R10.2).
4. Taxa de falhas <= 30% (estratégia parcialmente quebrada): engine
   devolve ``status="concluido"`` apesar das falhas individuais
   (R10.1).
5. Reprodutibilidade: duas execuções com mesma config + mesma
   estratégia produzem ``manifesto_hash`` idêntico e mesmas métricas
   por janela (R7.1).
6. Re-export: :class:`WalkForwardEngine` é re-exportado do pacote.

Convenções: pt-BR (R3.2 do Spec 1), Pydantic v2, Windows + cmd.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd
import pytest

from caos.data_manifest import DataManifestManager
from caos.walk_forward import (
    ConfiguracaoWalkForward,
    ResultadoWalkForward,
    WalkForwardEngine,
)
from caos.walk_forward.metricas import Trade as TradeRico
from caos.walk_forward.runner import BarrasTesteIterator

UTC = timezone.utc

CSV_HEADER = "timestamp,open,high,low,close,volume\n"


# ===========================================================================
# Fixtures e helpers
# ===========================================================================


def _config(
    treino: int = 60,
    teste: int = 10,
    seed: int = 42,
) -> ConfiguracaoWalkForward:
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=treino,
        tamanho_teste_dias_uteis=teste,
        granularidade="1m",
        seed=seed,
    )


def _construir_dados_sinteticos(
    raiz_pai: Path,
    *,
    n_dias_uteis: int,
    inicio: str = "2026-01-02",
    nome_arquivo: str = "MNQ-sintetico.csv",
) -> Path:
    """Gera ``dados/MNQ/`` com 1 CSV cobrindo ``n_dias_uteis`` business days.

    Cada dia tem 1 barra à meia-noite UTC. Preço sintético cresce 1
    ponto por dia. Manifesto é construído via :class:`DataManifestManager`.
    Retorna o path da raiz (``dados/MNQ/``).
    """
    raiz = raiz_pai / "dados" / "MNQ"
    raiz.mkdir(parents=True, exist_ok=True)
    timestamps = pd.bdate_range(inicio, periods=n_dias_uteis, tz="UTC")
    linhas: list[str] = []
    for i, ts in enumerate(timestamps):
        preco_open = 21000.0 + i
        preco_high = preco_open + 1.0
        preco_low = preco_open - 1.0
        preco_close = preco_open + 0.5
        volume = 1000.0
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        linhas.append(
            f"{ts_iso},{preco_open},{preco_high},{preco_low},{preco_close},{volume}"
        )
    arquivo = raiz / nome_arquivo
    arquivo.write_text(CSV_HEADER + "\n".join(linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz).build()
    return raiz


# ===========================================================================
# Estratégias de teste
# ===========================================================================


class EstrategiaSempreVencedora:
    """Estratégia determinística que emite 1 trade vencedor por barra de Teste.

    Cada trade é :class:`TradeRico` (modelo canônico) com PnL = +1 ponto,
    para que o engine possa calcular métricas completas via
    ``MetricasCalculator``.
    """

    NOME = "EstrategiaSempreVencedora"

    def __init__(self) -> None:
        self._trades: list[TradeRico] = []

    def treinar(self, historico: pd.DataFrame) -> None:
        # Reseta o buffer entre janelas — necessário pois a Engine reusa
        # a mesma instância em cada janela.
        self._trades = []

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        ts = barra["timestamp"]
        # Cada barra produz 1 trade: long, +1 ponto.
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


class EstrategiaSempreQuebra:
    """Estratégia que lança exceção em toda janela (R10.1)."""

    NOME = "EstrategiaSempreQuebra"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        raise RuntimeError("falha sintética para testes")

    def finalizar(self) -> Sequence[TradeRico]:
        return []


class EstrategiaIntermitenteFalha:
    """Falha em algumas janelas (controlada por contador de chamadas).

    Quebra apenas na primeira invocação de ``on_barra`` em cada janela
    cujo índice esteja em ``janelas_para_falhar``. Para fins de teste,
    o índice da janela não é diretamente acessível à estratégia — então
    usamos um contador externo de janelas processadas (incrementado em
    ``treinar``).
    """

    NOME = "EstrategiaIntermitenteFalha"

    def __init__(self, janelas_para_falhar: set[int]) -> None:
        self._janelas_para_falhar = set(janelas_para_falhar)
        self._janela_atual = -1
        self._trades: list[TradeRico] = []
        self._ja_falhou_nesta_janela = False

    def treinar(self, historico: pd.DataFrame) -> None:
        self._janela_atual += 1
        self._trades = []
        self._ja_falhou_nesta_janela = False

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        if (
            self._janela_atual in self._janelas_para_falhar
            and not self._ja_falhou_nesta_janela
        ):
            self._ja_falhou_nesta_janela = True
            raise RuntimeError(
                f"falha sintética na janela {self._janela_atual}"
            )
        ts = barra["timestamp"]
        self._trades.append(
            TradeRico(
                entrada_timestamp=ts.to_pydatetime(),
                saida_timestamp=(ts + pd.Timedelta(minutes=1)).to_pydatetime(),
                entrada_preco=21000.0,
                saida_preco=21000.5,
                lado="long",
                contratos=1,
                mfe_pontos=0.5,
                mae_pontos=0.0,
            )
        )

    def finalizar(self) -> Sequence[TradeRico]:
        return list(self._trades)


# ===========================================================================
# 1. Caminho feliz — 3 janelas
# ===========================================================================


class TestPipelineFelizComTresJanelas:
    """Pipeline ponta-a-ponta produz Resultado_Walk_Forward concluído."""

    def test_executar_devolve_resultado_concluido_com_3_janelas(
        self, tmp_path: Path
    ) -> None:
        # 60 (treino) + 10 (teste) + 2 * 10 (passos extras) = 90 dias úteis
        # ⇒ 3 janelas cabem (k=0, k=1, k=2).
        raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=90)
        engine = WalkForwardEngine(raiz_dados=raiz)

        resultado = engine.executar(
            estrategia=EstrategiaSempreVencedora(),
            configuracao=_config(),
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )

        assert isinstance(resultado, ResultadoWalkForward)
        assert resultado.status == "concluido"
        assert resultado.identificador == "2026-01-15-01"
        assert resultado.estrategia == "EstrategiaSempreVencedora"
        assert len(resultado.janelas) == 3
        # Cada janela com 10 barras de teste ⇒ 10 trades vencedores.
        for r in resultado.janelas:
            assert r.status == "ok"
            assert r.numero_trades == 10
            assert r.pnl_total == pytest.approx(10.0)

        # manifesto_hash é SHA-256 hex.
        assert len(resultado.manifesto_hash) == 64
        assert all(c in "0123456789abcdef" for c in resultado.manifesto_hash)

        # versoes_dependencias inclui pandas e numpy.
        assert "pandas" in resultado.versoes_dependencias
        assert "numpy" in resultado.versoes_dependencias

    def test_agregados_mediana_e_media_populados(self, tmp_path: Path) -> None:
        raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=90)
        engine = WalkForwardEngine(raiz_dados=raiz)

        resultado = engine.executar(
            estrategia=EstrategiaSempreVencedora(),
            configuracao=_config(),
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )

        # Pelo menos numero_trades e pnl_total foram agregados.
        assert "numero_trades" in resultado.agregado_mediana
        assert "pnl_total" in resultado.agregado_mediana
        assert resultado.agregado_mediana["numero_trades"] == pytest.approx(10.0)
        assert resultado.agregado_mediana["pnl_total"] == pytest.approx(10.0)
        # Média também populada.
        assert "pnl_total" in resultado.agregado_media
        assert resultado.agregado_media["pnl_total"] == pytest.approx(10.0)


# ===========================================================================
# 2. Manifesto inválido
# ===========================================================================


class TestManifestoInvalido:
    """Engine aborta cedo quando o manifesto está divergente (R4.2)."""

    def test_manifesto_modificado_devolve_status_manifesto_invalido(
        self, tmp_path: Path
    ) -> None:
        raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=90)
        # Modifica o CSV para invalidar o hash registrado.
        csv = raiz / "MNQ-sintetico.csv"
        csv.write_text(
            CSV_HEADER + "2026-01-02T00:00:00Z,1,2,0,1,1\n",
            encoding="utf-8",
        )

        engine = WalkForwardEngine(raiz_dados=raiz)
        resultado = engine.executar(
            estrategia=EstrategiaSempreVencedora(),
            configuracao=_config(),
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )

        assert resultado.status == "manifesto-invalido"
        assert resultado.janelas == []
        assert resultado.agregado_mediana == {}
        assert resultado.agregado_media == {}
        # Hash placeholder válido (64 zeros).
        assert resultado.manifesto_hash == "0" * 64


# ===========================================================================
# 3. Taxa de falhas > 30%
# ===========================================================================


class TestAbortadoPorFalhas:
    """Engine aborta quando >30% das janelas falham (R10.2)."""

    def test_estrategia_sempre_quebra_devolve_abortado_por_falhas(
        self, tmp_path: Path
    ) -> None:
        raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=90)
        engine = WalkForwardEngine(raiz_dados=raiz)

        resultado = engine.executar(
            estrategia=EstrategiaSempreQuebra(),
            configuracao=_config(),
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )

        assert resultado.status == "abortado-por-falhas"
        assert len(resultado.janelas) == 3
        # Todas falharam.
        assert all(r.status == "falha" for r in resultado.janelas)
        # Agregados vazios (faz sentido — nada para agregar).
        assert resultado.agregado_mediana == {}
        assert resultado.agregado_media == {}


# ===========================================================================
# 4. Taxa de falhas <= 30%
# ===========================================================================


class TestConcluidoComFalhasParciais:
    """Falhas individuais não invalidam o WF inteiro (R10.1)."""

    def test_uma_de_quatro_janelas_falha_e_resultado_e_concluido(
        self, tmp_path: Path
    ) -> None:
        # 4 janelas: 60 + 10 + 3*10 = 100 dias úteis.
        raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=100)
        engine = WalkForwardEngine(raiz_dados=raiz)

        # 1 falha em 4 janelas = 25% — abaixo do limiar de 30%.
        estrategia = EstrategiaIntermitenteFalha(janelas_para_falhar={1})

        resultado = engine.executar(
            estrategia=estrategia,
            configuracao=_config(),
            fonte_dados=raiz,
            identificador="2026-02-01-01",
        )

        assert resultado.status == "concluido"
        assert len(resultado.janelas) == 4
        falhas = [r for r in resultado.janelas if r.status == "falha"]
        assert len(falhas) == 1
        # As demais janelas concluíram com trades.
        sucessos = [r for r in resultado.janelas if r.status == "ok"]
        assert len(sucessos) == 3
        # Agregados não-vazios (3 janelas ok contribuem com métricas).
        assert "numero_trades" in resultado.agregado_mediana
        assert resultado.agregado_mediana["numero_trades"] == pytest.approx(10.0)


# ===========================================================================
# 5. Reprodutibilidade
# ===========================================================================


class TestReprodutibilidade:
    """Mesma config + mesma estratégia + mesmo manifesto ⇒ mesmo resultado."""

    def test_duas_execucoes_geram_mesmas_metricas_e_mesmo_hash(
        self, tmp_path: Path
    ) -> None:
        raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=90)
        engine = WalkForwardEngine(raiz_dados=raiz)
        cfg = _config(seed=123)

        r1 = engine.executar(
            estrategia=EstrategiaSempreVencedora(),
            configuracao=cfg,
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )
        r2 = engine.executar(
            estrategia=EstrategiaSempreVencedora(),
            configuracao=cfg,
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )

        # Hashes idênticos (R7.1).
        assert r1.manifesto_hash == r2.manifesto_hash
        # Mesmos status e mesmas métricas por janela.
        for j1, j2 in zip(r1.janelas, r2.janelas):
            assert j1.status == j2.status
            assert j1.numero_trades == j2.numero_trades
            assert j1.pnl_total == j2.pnl_total


# ===========================================================================
# 6. Re-export e construção
# ===========================================================================


def test_walk_forward_engine_reexportado_do_pacote() -> None:
    from caos.walk_forward import WalkForwardEngine as Reexport

    assert Reexport is WalkForwardEngine


def test_construtor_rejeita_raiz_inexistente(tmp_path: Path) -> None:
    inexistente = tmp_path / "fantasma"
    with pytest.raises(ValueError, match="raiz_dados"):
        WalkForwardEngine(raiz_dados=inexistente)


def test_dados_insuficientes_levantam_value_error(tmp_path: Path) -> None:
    """Histórico < treino + teste ⇒ engine levanta ValueError (R3.2)."""
    raiz = _construir_dados_sinteticos(tmp_path, n_dias_uteis=50)
    engine = WalkForwardEngine(raiz_dados=raiz)
    with pytest.raises(ValueError, match="histórico insuficiente"):
        engine.executar(
            estrategia=EstrategiaSempreVencedora(),
            configuracao=_config(),
            fonte_dados=raiz,
            identificador="2026-01-15-01",
        )
