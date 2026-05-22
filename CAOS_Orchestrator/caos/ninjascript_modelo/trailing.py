"""Espelho Python de ``TrailingTresFases.cs`` (Spec 3 — Task 8).

Reimplementa a máquina de 3 fases de :class:`Trailing_3_Fases` para
validação automatizada via Property 17 (monotonia do stop). Sem
dependência do runtime do NinjaTrader.

Cobre R4.1, R4.2, R4.3, R4.5 do ``requirements.md`` do Spec 3:

- R4.1: ao atingir ``entrada + 0.5R``, move stop para entrada (breakeven).
- R4.2: ao atingir ``entrada + 1R``, move stop para ``entrada + 0.3R``.
- R4.3: ao atingir ``entrada + 2R``, ativa trailing dinâmico de
  ``0.5 * R`` distância do preço.
- R4.5: stop nunca move contra a direção do trade (Property 17).
"""

from __future__ import annotations

import enum
import math
from typing import Optional


class DirecaoTrade(str, enum.Enum):
    """Direção da posição rastreada pelo trailing."""

    LONG = "LONG"
    SHORT = "SHORT"


class FaseTrailing(str, enum.Enum):
    """Estado da máquina de trailing (espelha ``FaseTrailing`` C#)."""

    SEM_POSICAO = "SemPosicao"
    ENTRADA = "Entrada"
    FASE1_BREAKEVEN = "Fase1Breakeven"
    FASE2_LOCK = "Fase2Lock"
    FASE3_DINAMICO = "Fase3Dinamico"


# Constantes do design 3 (não configuráveis por enquanto).
FASE2_STOP_OFFSET_R: float = 0.3   # entrada + 0.3R em LONG (R4.2)
FASE3_DISTANCIA_R: float = 0.5     # 0.5R atrás do preço (R4.3)


class TrailingModelo:
    """Reimplementação fiel de ``Trailing_3_Fases`` (Spec 3)."""

    def __init__(
        self,
        fase1_mult: float = 0.5,
        fase2_mult: float = 1.0,
        fase3_mult: float = 2.0,
    ) -> None:
        for nome, valor in (("fase1_mult", fase1_mult), ("fase2_mult", fase2_mult), ("fase3_mult", fase3_mult)):
            if not isinstance(valor, (int, float)) or math.isnan(valor) or math.isinf(valor):
                raise ValueError(f"{nome} deve ser float finito; recebido {valor!r}")
            if valor < 0.0 or valor > 2.0:
                raise ValueError(f"{nome} deve estar em [0, 2]; recebido {valor!r}")
        if not (fase1_mult <= fase2_mult <= fase3_mult):
            raise ValueError(
                "multiplicadores devem ser crescentes: fase1 <= fase2 <= fase3; "
                f"recebidos {fase1_mult}, {fase2_mult}, {fase3_mult}"
            )

        self._fase1_mult = float(fase1_mult)
        self._fase2_mult = float(fase2_mult)
        self._fase3_mult = float(fase3_mult)

        self._direcao: Optional[DirecaoTrade] = None
        self._entrada_preco: float = 0.0
        self._stop_inicial: float = 0.0
        self._risco_r: float = 0.0
        self._stop_atual: float = 0.0
        self._fase: FaseTrailing = FaseTrailing.SEM_POSICAO

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def fase(self) -> FaseTrailing:
        return self._fase

    @property
    def stop_atual(self) -> float:
        return self._stop_atual

    @property
    def risco_r(self) -> float:
        return self._risco_r

    @property
    def direcao(self) -> Optional[DirecaoTrade]:
        return self._direcao

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def abrir_long(self, entrada: float, stop_inicial: float) -> None:
        """Abre uma posição LONG. ``stop_inicial < entrada``."""
        self._validar_floats(entrada, stop_inicial)
        if not stop_inicial < entrada:
            raise ValueError(
                f"stop_inicial deve ser estritamente menor que entrada para LONG; "
                f"recebidos entrada={entrada}, stop_inicial={stop_inicial}"
            )
        self._direcao = DirecaoTrade.LONG
        self._entrada_preco = float(entrada)
        self._stop_inicial = float(stop_inicial)
        self._risco_r = float(entrada - stop_inicial)
        self._stop_atual = float(stop_inicial)
        self._fase = FaseTrailing.ENTRADA

    def abrir_short(self, entrada: float, stop_inicial: float) -> None:
        """Abre uma posição SHORT. ``stop_inicial > entrada``."""
        self._validar_floats(entrada, stop_inicial)
        if not stop_inicial > entrada:
            raise ValueError(
                f"stop_inicial deve ser estritamente maior que entrada para SHORT; "
                f"recebidos entrada={entrada}, stop_inicial={stop_inicial}"
            )
        self._direcao = DirecaoTrade.SHORT
        self._entrada_preco = float(entrada)
        self._stop_inicial = float(stop_inicial)
        self._risco_r = float(stop_inicial - entrada)
        self._stop_atual = float(stop_inicial)
        self._fase = FaseTrailing.ENTRADA

    def atualizar(self, preco_atual: float) -> float:
        """Atualiza a máquina e devolve o stop a aplicar (R4.1–R4.3, R4.5).

        Quando não há posição, devolve ``float('nan')``. Quando o preço
        é inválido (NaN/inf), preserva o stop atual.
        """
        if self._fase == FaseTrailing.SEM_POSICAO:
            return float("nan")
        if not isinstance(preco_atual, (int, float)):
            return self._stop_atual
        preco = float(preco_atual)
        if math.isnan(preco) or math.isinf(preco):
            return self._stop_atual

        # Lucro corrente em unidades de R, sempre não-negativo quando o
        # trade está a favor.
        if self._direcao == DirecaoTrade.LONG:
            lucro_r = (preco - self._entrada_preco) / self._risco_r
        else:
            lucro_r = (self._entrada_preco - preco) / self._risco_r

        # Transições de fase (irreversíveis: fase só avança).
        if self._fase == FaseTrailing.ENTRADA and lucro_r >= self._fase1_mult:
            self._fase = FaseTrailing.FASE1_BREAKEVEN
        if self._fase == FaseTrailing.FASE1_BREAKEVEN and lucro_r >= self._fase2_mult:
            self._fase = FaseTrailing.FASE2_LOCK
        if self._fase == FaseTrailing.FASE2_LOCK and lucro_r >= self._fase3_mult:
            self._fase = FaseTrailing.FASE3_DINAMICO

        # Stop alvo proposto pela fase corrente.
        if self._fase == FaseTrailing.ENTRADA:
            stop_proposto = self._stop_inicial
        elif self._fase == FaseTrailing.FASE1_BREAKEVEN:
            stop_proposto = self._entrada_preco
        elif self._fase == FaseTrailing.FASE2_LOCK:
            if self._direcao == DirecaoTrade.LONG:
                stop_proposto = self._entrada_preco + FASE2_STOP_OFFSET_R * self._risco_r
            else:
                stop_proposto = self._entrada_preco - FASE2_STOP_OFFSET_R * self._risco_r
        elif self._fase == FaseTrailing.FASE3_DINAMICO:
            if self._direcao == DirecaoTrade.LONG:
                stop_proposto = preco - FASE3_DISTANCIA_R * self._risco_r
            else:
                stop_proposto = preco + FASE3_DISTANCIA_R * self._risco_r
        else:
            stop_proposto = self._stop_atual

        # R4.5 — monotonia: stop nunca move contra o trade.
        if self._direcao == DirecaoTrade.LONG:
            self._stop_atual = max(self._stop_atual, stop_proposto)
        else:
            self._stop_atual = min(self._stop_atual, stop_proposto)
        return self._stop_atual

    def fechar(self) -> None:
        """Fecha a posição corrente e reseta para ``SEM_POSICAO``."""
        self._direcao = None
        self._entrada_preco = 0.0
        self._stop_inicial = 0.0
        self._risco_r = 0.0
        self._stop_atual = 0.0
        self._fase = FaseTrailing.SEM_POSICAO

    # ------------------------------------------------------------------
    @staticmethod
    def _validar_floats(*valores: float) -> None:
        for v in valores:
            if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
                raise ValueError(f"valor float inválido: {v!r}")


__all__ = [
    "DirecaoTrade",
    "FaseTrailing",
    "FASE2_STOP_OFFSET_R",
    "FASE3_DISTANCIA_R",
    "TrailingModelo",
]
