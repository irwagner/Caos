"""Plugin meta-estrategia ``EstrategiaPortfolio`` — combina N estrategias.

Roda N estrategias plugaveis em paralelo durante o mesmo Walk-Forward.
Cada estrategia recebe a mesma barra independentemente (sem
comunicacao entre elas). Os trades emitidos por todas sao
concatenados na ``finalizar`` final.

Decisao do Conselho-no-Chat:

- Sem alocacao de capital dinamica entre componentes (anti-overfit).
  Cada componente opera com 1 contrato, portfolio total = soma de
  exposicoes individuais.
- Sem hedge entre componentes. Se duas componentes querem long ao
  mesmo tempo, total e 2 contratos.
- Sem rebalance / target volatility. O portfolio e literalmente a
  uniao dos trades.

Casos de uso esperados:

- Diversificacao de regime: combinar estrategia que ganha em vol
  comprimida (Crabel NR7+SF) com uma que ganha em eventos macro
  (Pre-FOMC). Hipotese: se janela ruim de uma e janela boa da outra,
  Sharpe combinado fica acima do componente individual.
- Validacao de correlacao real entre achados. Sem rodar o portfolio,
  so vemos correlacao entre RESUMOS por janela; com portfolio rodando,
  vemos correlacao entre TRADES individuais.

Estatisticas observaveis (testes/auditoria):
- ``num_trades_por_componente``: dict[nome_componente, int]
- ``estrategias_internas``: lista de instancias para inspecao
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


class EstrategiaPortfolio:
    """Wraps N estrategias e roda em paralelo. Trades concatenados."""

    NOME: str = "EstrategiaPortfolio"

    def __init__(
        self,
        componentes: Sequence[Any],
        nome: str = "EstrategiaPortfolio",
    ) -> None:
        if not componentes:
            raise ValueError("portfolio precisa de >=1 componente")
        for i, c in enumerate(componentes):
            if not (
                callable(getattr(c, "on_barra", None))
                and callable(getattr(c, "finalizar", None))
            ):
                raise TypeError(
                    f"componente {i} ({type(c).__name__}) nao implementa "
                    "on_barra/finalizar"
                )
        self._componentes: List[Any] = list(componentes)
        self.NOME = nome  # type: ignore[misc]
        self._num_trades_emitidos: List[int] = [0] * len(self._componentes)

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        for c in self._componentes:
            treinar = getattr(c, "treinar", None)
            if callable(treinar):
                # Cada componente recebe COPIA do historico para
                # evitar mutacao acidental compartilhada.
                treinar(historico.copy())
        self._num_trades_emitidos = [0] * len(self._componentes)

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        for c in self._componentes:
            c.on_barra(barra, contexto)

    def finalizar(self) -> Sequence[Trade]:
        """Concatena trades de todos os componentes em ordem
        cronologica por entrada_timestamp.
        """
        trades_total: List[Trade] = []
        for i, c in enumerate(self._componentes):
            trades_c = list(c.finalizar() or [])
            self._num_trades_emitidos[i] = len(trades_c)
            trades_total.extend(trades_c)
        # Ordena por entrada_timestamp para que MetricasCalculator
        # processe em ordem cronologica.
        trades_total.sort(key=lambda t: t.entrada_timestamp)
        return trades_total

    # ------------------------------------------------------------------
    # Acessores
    # ------------------------------------------------------------------

    @property
    def estrategias_internas(self) -> Sequence[Any]:
        return tuple(self._componentes)

    @property
    def num_trades_por_componente(self) -> dict:
        return {
            getattr(c, "NOME", type(c).__name__): n
            for c, n in zip(self._componentes, self._num_trades_emitidos)
        }


__all__ = ["EstrategiaPortfolio"]
