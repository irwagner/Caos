"""Espelho Python de ``Cerberus.cs`` (Spec 3 — Task 7).

Reimplementa a lógica pura de :class:`Cerberus_CSharp` para validação
automatizada via Property 16. Sem dependência do runtime do NinjaTrader.

Cobre R3.1, R3.2, R3.5 do ``requirements.md`` do Spec 3:

- R3.1: ``autorizar_entrada(contratos, risco_usd)`` retorna ``False``
  quando o tamanho violar limites configurados.
- R3.2: ``Circuit_Breaker_Diario`` (default USD 500) — quando o PnL
  diário cumulativo atinge ``-circuit_breaker_usd`` (ou pior), o
  circuit breaker é ativado e bloqueia novas entradas.
- R3.5: rollover automático em UTC zera ``pnl_diario_realizado`` e
  desativa o circuit breaker.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Callable, Optional


class CerberusModelo:
    """Reimplementação fiel de ``Cerberus_CSharp`` (Spec 3).

    Parameters
    ----------
    max_contratos:
        Tamanho máximo de posição em contratos. Inteiro ``>= 1``.
    circuit_breaker_usd:
        Limite diário de drawdown em USD. Float ``> 0``. Atingido,
        bloqueia novas entradas até o próximo dia UTC (R3.2).
    agora_utc:
        Função opcional que devolve o instante UTC atual. Default usa
        :func:`datetime.now(timezone.utc)`. Testes injetam um clock fake
        para validar rollover sem depender de horário real.

    Raises
    ------
    ValueError
        Quando ``max_contratos < 1`` ou ``circuit_breaker_usd <= 0``.
    """

    def __init__(
        self,
        max_contratos: int,
        circuit_breaker_usd: float,
        agora_utc: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if not isinstance(max_contratos, int) or max_contratos < 1:
            raise ValueError(
                f"max_contratos deve ser inteiro >= 1; recebido {max_contratos!r}"
            )
        if circuit_breaker_usd <= 0.0 or math.isnan(circuit_breaker_usd) or math.isinf(circuit_breaker_usd):
            raise ValueError(
                f"circuit_breaker_usd deve ser > 0; recebido {circuit_breaker_usd!r}"
            )
        self._max_contratos = max_contratos
        self._circuit_breaker_usd = float(circuit_breaker_usd)
        self._agora_utc = agora_utc or (lambda: datetime.now(timezone.utc))
        self._dia_corrente: date = self._agora_utc().date()
        self._pnl_diario_realizado: float = 0.0
        self._circuit_breaker_ativado: bool = False

    # ------------------------------------------------------------------
    # Propriedades públicas (espelham getters do C#)
    # ------------------------------------------------------------------

    @property
    def max_contratos(self) -> int:
        """Tamanho máximo de posição configurado (R3.1)."""
        return self._max_contratos

    @property
    def circuit_breaker_usd(self) -> float:
        """Limite diário de drawdown em USD (R3.2)."""
        return self._circuit_breaker_usd

    @property
    def pnl_diario_realizado(self) -> float:
        """PnL realizado acumulado no dia UTC corrente."""
        self._verificar_rollover_dia()
        return self._pnl_diario_realizado

    @property
    def circuit_breaker_ativo(self) -> bool:
        """``True`` se o circuit breaker foi ativado no dia UTC corrente."""
        self._verificar_rollover_dia()
        return self._circuit_breaker_ativado

    # ------------------------------------------------------------------
    # API pública (R3.1, R3.2)
    # ------------------------------------------------------------------

    def autorizar_entrada(self, contratos: int, risco_usd: float) -> bool:
        """Decide se uma intenção de entrada pode prosseguir (R3.1, R3.2).

        Bloqueia quando:

        - circuit breaker ativo;
        - ``contratos < 1`` ou ``contratos > max_contratos``;
        - ``risco_usd <= 0`` ou ``NaN``/``inf`` (risco não declarado).
        """
        self._verificar_rollover_dia()
        if self._circuit_breaker_ativado:
            return False
        if not isinstance(contratos, int):
            return False
        if contratos < 1 or contratos > self._max_contratos:
            return False
        if not isinstance(risco_usd, (int, float)):
            return False
        risco = float(risco_usd)
        if math.isnan(risco) or math.isinf(risco):
            return False
        if risco <= 0.0:
            return False
        return True

    def registrar_pnl_realizado(self, pnl: float) -> None:
        """Registra o PnL realizado de um trade fechado (R3.2, R3.5).

        Quando o acumulado do dia atinge ``-circuit_breaker_usd`` (ou
        pior), o circuit breaker é ativado.
        """
        self._verificar_rollover_dia()
        if math.isnan(pnl) or math.isinf(pnl):
            raise ValueError(f"pnl não pode ser NaN/inf; recebido {pnl!r}")
        self._pnl_diario_realizado += float(pnl)
        if self._pnl_diario_realizado <= -self._circuit_breaker_usd:
            self._circuit_breaker_ativado = True

    def resetar(self) -> None:
        """Reset manual (testes / nova sessão)."""
        self._pnl_diario_realizado = 0.0
        self._circuit_breaker_ativado = False
        self._dia_corrente = self._agora_utc().date()

    # ------------------------------------------------------------------
    # R3.5 — Rollover diário em UTC
    # ------------------------------------------------------------------

    def _verificar_rollover_dia(self) -> None:
        hoje = self._agora_utc().date()
        if hoje != self._dia_corrente:
            self._dia_corrente = hoje
            self._pnl_diario_realizado = 0.0
            self._circuit_breaker_ativado = False


__all__ = ["CerberusModelo"]
