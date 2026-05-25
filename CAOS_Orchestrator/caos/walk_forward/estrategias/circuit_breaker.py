"""Plugin overlay ``EstrategiaCircuitBreaker`` — desliga estrategia
quando PnL acumulado bate limite.

Wraps qualquer Estrategia plugavel e injeta logica de circuit breaker:
- Computa PnL acumulado a partir dos trades fechados pela estrategia
  interna ate o ponto atual.
- Quando PnL diario/semanal/total atinge threshold negativo, bloqueia
  novas chamadas a ``on_barra`` da estrategia interna ate fim do
  periodo (dia/semana) ou ate o fim da janela WF.
- Trades ja abertos pela estrategia interna NAO sao fechados pela
  forca - apenas novas entradas sao bloqueadas. Isso preserva a
  semantica do plugin original (ex: Pre-FOMC que tem entrada/saida
  agendadas no fechamento do dia).

Decisao do Conselho 2026-05-25-01: este overlay e a ferramenta para
endereçar o veto de Cerberus (exposicao_excede_topstep_drawdown).
Aplicado a Crabel NR7+SF, deve trazer a janela 1 (que perdeu -1711
pts isoladamente) para dentro do envelope Topstep (-2500 trailing DD).

Decisoes de implementacao:

- O calculo de PnL precisa observar trades CONFORME EMITIDOS pela
  estrategia interna. A interface `Estrategia.finalizar()` retorna
  TODOS os trades juntos no fim - o que e tarde demais. Solucao:
  nao bloqueamos durante a janela; em vez disso, **filtramos os
  trades em finalizar()** removendo aqueles que vieram apos o
  trigger do circuit breaker.
- Periodo "dia" e definido como data UTC do timestamp de entrada do
  trade (consistente com o resto do projeto).
- PnL em pontos (consistente com Trade.pnl_pontos()).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Literal, Optional, Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


PeriodoCircuitBreaker = Literal["diario", "semanal", "janela"]


@dataclass(frozen=True)
class ParametrosCircuitBreaker:
    """Limites do circuit breaker.

    Todos em pontos (×USD 2 = USD efetivo no MNQ).

    ``limite_diario_pts``: PnL acumulado no dia que dispara breaker.
    Usar valores NEGATIVOS (ex: -250 = USD -500 com 1 contrato).
    Se ``None``, sem limite diario.

    ``limite_semanal_pts``: PnL acumulado na semana (seg-sex UTC).
    ``None`` desativa.

    ``limite_janela_pts``: PnL acumulado total na janela WF.
    Default ``-1000`` pts (USD -2000) — abaixo do trailing DD Topstep.

    Validacao: se TODOS forem None, levanta ValueError (sem ponto
    em ter circuit breaker desligado).
    """

    limite_diario_pts: Optional[float] = -250.0
    limite_semanal_pts: Optional[float] = -750.0
    limite_janela_pts: Optional[float] = -1000.0

    def __post_init__(self) -> None:
        if all(
            v is None for v in (
                self.limite_diario_pts,
                self.limite_semanal_pts,
                self.limite_janela_pts,
            )
        ):
            raise ValueError(
                "circuit breaker precisa pelo menos UM limite (diario, "
                "semanal ou janela) configurado"
            )
        for nome, val in (
            ("limite_diario_pts", self.limite_diario_pts),
            ("limite_semanal_pts", self.limite_semanal_pts),
            ("limite_janela_pts", self.limite_janela_pts),
        ):
            if val is not None and val >= 0:
                raise ValueError(
                    f"{nome} deve ser NEGATIVO (limite de PERDA); "
                    f"recebido {val}"
                )


def _semana_iso(d: date) -> tuple[int, int]:
    """Retorna (ano_iso, semana_iso) — chave estavel para agrupamento
    semanal cross-mes."""
    iso = d.isocalendar()
    return (iso[0], iso[1])


class EstrategiaCircuitBreaker:
    """Wrapper que filtra trades violando limites de PnL acumulado.

    Estrategia: deixa a estrategia interna rodar livremente durante
    a janela WF, depois em finalizar() filtra trades que ocorreram
    apos qualquer trigger do circuit breaker.

    Logica de filtragem cronologica:
    1. Ordena trades por entrada_timestamp.
    2. Itera, mantendo PnL acumulado diario/semanal/total.
    3. Se algum limite e atingido apos um trade T, desativa todos
       os trades subsequentes ATE o reset do periodo correspondente.
    4. Reset diario: novo dia. Reset semanal: nova semana ISO.
       Limite janela = sem reset (descontinua a janela inteira).
    """

    NOME: str = "EstrategiaCircuitBreaker"

    def __init__(
        self,
        estrategia_interna: Any,
        *,
        parametros: Optional[ParametrosCircuitBreaker] = None,
    ) -> None:
        if not (
            callable(getattr(estrategia_interna, "on_barra", None))
            and callable(getattr(estrategia_interna, "finalizar", None))
        ):
            raise TypeError(
                "estrategia_interna deve implementar on_barra e finalizar"
            )
        self._interna = estrategia_interna
        self._parametros = parametros or ParametrosCircuitBreaker()
        self._trades_descartados_diario: int = 0
        self._trades_descartados_semanal: int = 0
        self._trades_descartados_janela: int = 0

    def treinar(self, historico: pd.DataFrame) -> None:
        treinar = getattr(self._interna, "treinar", None)
        if callable(treinar):
            treinar(historico)
        self._trades_descartados_diario = 0
        self._trades_descartados_semanal = 0
        self._trades_descartados_janela = 0

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        # Sem filtragem em runtime — a estrategia interna nao sabe
        # do circuit breaker e roda livremente. Filtragem retroativa
        # acontece em finalizar(). Trade-off aceito porque permite
        # composicao com plugins streaming sem conhecer interno.
        self._interna.on_barra(barra, contexto)

    def finalizar(self) -> Sequence[Trade]:
        trades_brutos = list(self._interna.finalizar() or [])
        if not trades_brutos:
            return []
        trades_ord = sorted(trades_brutos, key=lambda t: t.entrada_timestamp)

        pnl_diario: dict[date, float] = {}
        pnl_semanal: dict[tuple[int, int], float] = {}
        pnl_janela: float = 0.0

        # Flags de bloqueio por periodo.
        dia_bloqueado: dict[date, bool] = {}
        semana_bloqueada: dict[tuple[int, int], bool] = {}
        janela_bloqueada: bool = False

        trades_aceitos: List[Trade] = []
        for t in trades_ord:
            dia = t.entrada_timestamp.date()
            sem = _semana_iso(dia)

            # Verifica bloqueios ANTES de adicionar PnL deste trade.
            if janela_bloqueada:
                self._trades_descartados_janela += 1
                continue
            if dia_bloqueado.get(dia, False):
                self._trades_descartados_diario += 1
                continue
            if semana_bloqueada.get(sem, False):
                self._trades_descartados_semanal += 1
                continue

            # Aceita o trade.
            pnl_t = t.pnl_pontos()
            trades_aceitos.append(t)
            pnl_diario[dia] = pnl_diario.get(dia, 0.0) + pnl_t
            pnl_semanal[sem] = pnl_semanal.get(sem, 0.0) + pnl_t
            pnl_janela += pnl_t

            # Verifica triggers APOS adicionar (ou seja, dispara para
            # trades subsequentes).
            limite_d = self._parametros.limite_diario_pts
            if limite_d is not None and pnl_diario[dia] <= limite_d:
                dia_bloqueado[dia] = True
            limite_s = self._parametros.limite_semanal_pts
            if limite_s is not None and pnl_semanal[sem] <= limite_s:
                semana_bloqueada[sem] = True
            limite_j = self._parametros.limite_janela_pts
            if limite_j is not None and pnl_janela <= limite_j:
                janela_bloqueada = True

        return trades_aceitos

    @property
    def parametros(self) -> ParametrosCircuitBreaker:
        return self._parametros

    @property
    def estrategia_interna(self) -> Any:
        return self._interna

    @property
    def trades_descartados(self) -> dict[str, int]:
        return {
            "diario": self._trades_descartados_diario,
            "semanal": self._trades_descartados_semanal,
            "janela": self._trades_descartados_janela,
        }


__all__ = [
    "EstrategiaCircuitBreaker",
    "ParametrosCircuitBreaker",
    "PeriodoCircuitBreaker",
]
