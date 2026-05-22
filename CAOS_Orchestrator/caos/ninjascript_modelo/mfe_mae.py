"""Espelho Python de ``MfeMaeTracker.cs`` (Spec 3 — Task 9).

Reimplementa o tracker MFE/MAE para validação automatizada via
Property 18. Sem dependência do runtime do NinjaTrader.

Cobre R5.1, R5.4 do ``requirements.md`` do Spec 3:

- R5.1: acompanha ``mfe_atual`` e ``mae_atual`` em ticks por trade
  aberto.
- R5.4: garante ``mfe_ticks >= 0`` e ``mae_ticks <= 0`` em qualquer
  snapshot devolvido por :meth:`MfeMaeModelo.fechar` (Property 18).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


class DirecaoTradeMfeMae(str, enum.Enum):
    """Direção do trade rastreado."""

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class TradeMfeMae:
    """Snapshot imutável devolvido por :meth:`MfeMaeModelo.fechar`."""

    id_trade: int
    direcao: DirecaoTradeMfeMae
    entrada_timestamp: datetime
    saida_timestamp: datetime
    entrada_preco: float
    saida_preco: float
    mfe_ticks: int
    mae_ticks: int
    pnl_usd: float


class MfeMaeModelo:
    """Reimplementação fiel de ``MfeMaeTracker`` (Spec 3 — apenas lógica pura).

    Não escreve em disco — a porta C# faz isso via :class:`StreamWriter`.
    O Python aqui foca na correção semântica das Properties.
    """

    def __init__(self, tick_size: float = 0.25) -> None:
        if not isinstance(tick_size, (int, float)) or tick_size <= 0.0:
            raise ValueError(f"tick_size deve ser > 0; recebido {tick_size!r}")
        if math.isnan(tick_size) or math.isinf(tick_size):
            raise ValueError(f"tick_size inválido: {tick_size!r}")
        self._tick_size = float(tick_size)

        self._id_trade_atual: int = 0
        self._direcao_atual: Optional[DirecaoTradeMfeMae] = None
        self._entrada_preco: float = 0.0
        self._entrada_timestamp: Optional[datetime] = None
        self._mfe_ticks: int = 0
        self._mae_ticks: int = 0

    # ------------------------------------------------------------------
    @property
    def tem_trade_aberto(self) -> bool:
        return self._id_trade_atual != 0

    @property
    def mfe_ticks_corrente(self) -> int:
        return self._mfe_ticks

    @property
    def mae_ticks_corrente(self) -> int:
        return self._mae_ticks

    @property
    def tick_size(self) -> float:
        return self._tick_size

    # ------------------------------------------------------------------
    def abrir(
        self,
        id_trade: int,
        direcao: DirecaoTradeMfeMae,
        entrada_preco: float,
        entrada_timestamp: datetime,
    ) -> None:
        """Abre o rastreamento de um novo trade (R5.1)."""
        if not isinstance(id_trade, int) or id_trade <= 0:
            raise ValueError(f"id_trade deve ser inteiro > 0; recebido {id_trade!r}")
        if self.tem_trade_aberto:
            raise RuntimeError(
                f"MfeMaeModelo já tem trade aberto (id={self._id_trade_atual}); "
                "feche o trade corrente antes de abrir outro."
            )
        if not isinstance(direcao, DirecaoTradeMfeMae):
            raise ValueError(f"direcao inválida: {direcao!r}")
        if not isinstance(entrada_preco, (int, float)):
            raise ValueError(f"entrada_preco inválido: {entrada_preco!r}")
        if math.isnan(entrada_preco) or math.isinf(entrada_preco):
            raise ValueError(f"entrada_preco não pode ser NaN/inf: {entrada_preco!r}")
        if not isinstance(entrada_timestamp, datetime):
            raise ValueError(f"entrada_timestamp deve ser datetime; recebido {entrada_timestamp!r}")
        ts_utc = self._para_utc(entrada_timestamp)

        self._id_trade_atual = id_trade
        self._direcao_atual = direcao
        self._entrada_preco = float(entrada_preco)
        self._entrada_timestamp = ts_utc
        self._mfe_ticks = 0
        self._mae_ticks = 0

    def atualizar(self, preco_atual: float) -> None:
        """Atualiza MFE/MAE com ``preco_atual`` (R5.1, R5.4)."""
        if not self.tem_trade_aberto:
            return
        if not isinstance(preco_atual, (int, float)):
            return
        preco = float(preco_atual)
        if math.isnan(preco) or math.isinf(preco):
            return

        # Excursão em ticks, sinalizada pela direção do trade.
        if self._direcao_atual == DirecaoTradeMfeMae.LONG:
            delta = preco - self._entrada_preco
        else:
            delta = self._entrada_preco - preco
        delta_ticks = int(round(delta / self._tick_size))

        # R5.4: mfe sempre >= 0; mae sempre <= 0.
        if delta_ticks > self._mfe_ticks:
            self._mfe_ticks = delta_ticks
        if delta_ticks < self._mae_ticks:
            self._mae_ticks = delta_ticks

    def fechar(
        self,
        saida_preco: float,
        saida_timestamp: datetime,
        pnl_usd: float,
    ) -> TradeMfeMae:
        """Fecha o trade corrente e devolve o snapshot final (R5.2, R5.4).

        O preço de saída é considerado uma última atualização: a excursão
        realizada pelo próprio fill conta no MFE/MAE.
        """
        if not self.tem_trade_aberto:
            raise RuntimeError("MfeMaeModelo não tem trade aberto para fechar")
        if not isinstance(saida_preco, (int, float)):
            raise ValueError(f"saida_preco inválido: {saida_preco!r}")
        if math.isnan(saida_preco) or math.isinf(saida_preco):
            raise ValueError(f"saida_preco não pode ser NaN/inf: {saida_preco!r}")
        if not isinstance(saida_timestamp, datetime):
            raise ValueError(f"saida_timestamp deve ser datetime; recebido {saida_timestamp!r}")
        if math.isnan(pnl_usd) or math.isinf(pnl_usd):
            raise ValueError(f"pnl_usd não pode ser NaN/inf: {pnl_usd!r}")

        self.atualizar(saida_preco)
        ts_saida = self._para_utc(saida_timestamp)

        snap = TradeMfeMae(
            id_trade=self._id_trade_atual,
            direcao=self._direcao_atual,  # type: ignore[arg-type]
            entrada_timestamp=self._entrada_timestamp,  # type: ignore[arg-type]
            saida_timestamp=ts_saida,
            entrada_preco=self._entrada_preco,
            saida_preco=float(saida_preco),
            mfe_ticks=self._mfe_ticks,
            mae_ticks=self._mae_ticks,
            pnl_usd=float(pnl_usd),
        )

        # Reset de estado.
        self._id_trade_atual = 0
        self._direcao_atual = None
        self._entrada_preco = 0.0
        self._entrada_timestamp = None
        self._mfe_ticks = 0
        self._mae_ticks = 0

        return snap

    # ------------------------------------------------------------------
    @staticmethod
    def _para_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            # Convenção: timestamps naive são interpretados como UTC para
            # alinhar com a convenção do Spec 1 (R3.1 do walk-forward).
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)


__all__ = ["DirecaoTradeMfeMae", "MfeMaeModelo", "TradeMfeMae"]
