"""Plugin ``EstrategiaORB`` para o Walk-Forward (Spec 4 — Task 2).

Adaptador fino que conecta a função de decisão pura
:func:`caos.walk_forward.estrategias.orb_logica.decidir_acao` ao
protocolo :class:`caos.walk_forward.runner.Estrategia` consumido pelo
:class:`caos.walk_forward.engine.WalkForwardEngine`.

Responsabilidades (R2 despacho, R3 stop/alvo, R4 cooldown, R6.2 sem random):

- Manter um :class:`~orb_logica.EstadoORB` por janela; resetar em
  :meth:`treinar` (que o Engine chama no início de cada janela).
- Em :meth:`on_barra`, traduzir a :class:`pandas.Series` da barra em
  :class:`~orb_logica.Barra`, chamar ``decidir_acao``, abrir/fechar
  trade local conforme a decisão.
- Em :meth:`finalizar`, devolver a lista de :class:`metricas.Trade`
  emitidos.

Convenções: identificadores Python idiomáticos (snake_case);
docstrings/mensagens em pt-BR. Apenas dependência runtime: pandas
(já em ``pyproject.toml`` desde o Spec 2).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

import pandas as pd

from caos.walk_forward.estrategias.orb_logica import (
    AcaoORB,
    Barra,
    DecisaoORB,
    EstadoORB,
    ParametrosORB,
    decidir_acao,
    registrar_abertura_de_posicao,
    registrar_fechamento_de_posicao,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


class _TradeAberto:
    """Wrapper interno do trade em andamento (estado simples)."""

    __slots__ = (
        "lado",
        "entrada_timestamp",
        "entrada_preco",
        "stop",
        "alvo",
        "mfe_pontos",
        "mae_pontos",
    )

    def __init__(
        self,
        lado: str,
        entrada_timestamp: datetime,
        entrada_preco: float,
        stop: float,
        alvo: float,
    ) -> None:
        self.lado = lado
        self.entrada_timestamp = entrada_timestamp
        self.entrada_preco = entrada_preco
        self.stop = stop
        self.alvo = alvo
        # Excursões em pontos (sinais conforme convenção do MetricasCalculator):
        # mfe >= 0, mae <= 0.
        self.mfe_pontos = 0.0
        self.mae_pontos = 0.0


class EstrategiaORB:
    """Estratégia Opening Range Breakout (Spec 4) plugada no Walk-Forward.

    Parameters
    ----------
    parametros:
        :class:`ParametrosORB` opcional. Default usa os valores
        canônicos (R5.1: minutos_or=30, risco_mult=1.0, alvo_mult=2.0,
        cooldown=15, sessão 13:30–20:00 UTC, corte 19:00).
    """

    NOME: str = "EstrategiaORB"

    def __init__(self, parametros: Optional[ParametrosORB] = None) -> None:
        self._parametros: ParametrosORB = parametros or ParametrosORB()
        self._estado: EstadoORB = EstadoORB()
        self._trades: List[Trade] = []
        self._trade_aberto: Optional[_TradeAberto] = None

    # ------------------------------------------------------------------
    # Protocol Estrategia (Spec 2)
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        """Reseta estado interno entre janelas — R6 (determinismo)."""
        self._estado = EstadoORB()
        self._trades = []
        self._trade_aberto = None

    def on_barra(self, barra_pd: pd.Series, contexto: BarrasTesteIterator) -> None:
        """Despacha a barra para :func:`decidir_acao` e age na decisão."""
        barra = self._barra_de_series(barra_pd)

        # Antes da decisão, atualiza MFE/MAE da posição corrente para que
        # a saída forçada de fim-de-sessão já reflita as excursões da
        # barra atual.
        if self._trade_aberto is not None:
            self._atualizar_excursoes(barra)

        decisao = decidir_acao(barra, self._estado, self._parametros)

        if decisao.acao == "LONG":
            self._abrir_trade(barra, decisao, lado="long")
            registrar_abertura_de_posicao(self._estado, decisao)
        elif decisao.acao == "SHORT":
            self._abrir_trade(barra, decisao, lado="short")
            registrar_abertura_de_posicao(self._estado, decisao)
        elif decisao.acao == "FECHAR":
            self._fechar_trade(barra)
            registrar_fechamento_de_posicao(self._estado, barra.timestamp, self._parametros)

    def finalizar(self) -> Sequence[Trade]:
        """Fecha trade pendente (se houver) e devolve a lista final."""
        if self._trade_aberto is not None:
            # Fecha pelo último preço observado — usamos o stop ou alvo
            # como aproximação; aqui usamos o entrada_preco para evitar
            # PnL fictício quando o BacktestRunner não emitiu mais barras.
            # Em produção, o fim-de-sessão (R4.3) já deve ter fechado.
            ts_aprox = self._trade_aberto.entrada_timestamp + timedelta(seconds=1)
            self._fechar_trade(
                Barra(
                    timestamp=ts_aprox,
                    open=self._trade_aberto.entrada_preco,
                    high=self._trade_aberto.entrada_preco,
                    low=self._trade_aberto.entrada_preco,
                    close=self._trade_aberto.entrada_preco,
                    volume=0.0,
                )
            )
        return list(self._trades)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _barra_de_series(barra_pd: pd.Series) -> Barra:
        ts = pd.Timestamp(barra_pd["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return Barra(
            timestamp=ts,
            open=float(barra_pd["open"]),
            high=float(barra_pd["high"]),
            low=float(barra_pd["low"]),
            close=float(barra_pd["close"]),
            volume=float(barra_pd["volume"]),
        )

    def _abrir_trade(self, barra: Barra, decisao: DecisaoORB, *, lado: str) -> None:
        if decisao.stop is None or decisao.alvo is None:
            return  # defensivo; decisão LONG/SHORT sempre traz stop/alvo
        self._trade_aberto = _TradeAberto(
            lado=lado,
            entrada_timestamp=barra.timestamp,
            entrada_preco=barra.close,
            stop=decisao.stop,
            alvo=decisao.alvo,
        )

    def _atualizar_excursoes(self, barra: Barra) -> None:
        """Atualiza MFE/MAE com a excursão da barra corrente."""
        ta = self._trade_aberto
        if ta is None:
            return
        if ta.lado == "long":
            mfe_potencial = barra.high - ta.entrada_preco
            mae_potencial = barra.low - ta.entrada_preco
        else:
            mfe_potencial = ta.entrada_preco - barra.low
            mae_potencial = ta.entrada_preco - barra.high
        if mfe_potencial > ta.mfe_pontos:
            ta.mfe_pontos = mfe_potencial
        if mae_potencial < ta.mae_pontos:
            ta.mae_pontos = mae_potencial

    def _fechar_trade(self, barra: Barra) -> None:
        """Fecha o trade aberto e empilha em ``self._trades``."""
        ta = self._trade_aberto
        if ta is None:
            return
        # Saída pelo close da barra de fechamento (FECHAR foi disparado
        # por fim-de-sessão; em produção real seria o ExitLong/ExitShort).
        saida_preco = barra.close
        # Última atualização das excursões com o preço de saída.
        self._atualizar_excursoes(barra)
        # Garante saída estritamente posterior à entrada (Trade exige
        # saida_timestamp > entrada_timestamp).
        saida_ts = barra.timestamp
        if saida_ts <= ta.entrada_timestamp:
            saida_ts = ta.entrada_timestamp + timedelta(seconds=1)

        trade = Trade(
            entrada_timestamp=ta.entrada_timestamp,
            saida_timestamp=saida_ts,
            entrada_preco=ta.entrada_preco,
            saida_preco=saida_preco,
            lado=ta.lado,  # type: ignore[arg-type]  # Literal["long","short"]
            contratos=1,
            mfe_pontos=ta.mfe_pontos,
            mae_pontos=ta.mae_pontos,
        )
        self._trades.append(trade)
        self._trade_aberto = None

    # ------------------------------------------------------------------
    # Acessores úteis em testes
    # ------------------------------------------------------------------

    @property
    def parametros(self) -> ParametrosORB:
        return self._parametros

    @property
    def estado(self) -> EstadoORB:
        return self._estado

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)


__all__ = ["EstrategiaORB"]
