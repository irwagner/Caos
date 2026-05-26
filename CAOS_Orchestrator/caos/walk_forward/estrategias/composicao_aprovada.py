"""Plugin :class:`EstrategiaORBCrabelSFCB` — composicao aprovada na Decisao 2026-05-25-02.

Composicao canonica:

    EstrategiaCircuitBreaker(
        EstrategiaSpreadFilter(
            EstrategiaORBCrabel(modo_nr="nr7"),
            modo="mediana_diaria", warmup=30, running median
        ),
        diario=-250 pts, semanal=-750 pts, janela=-1000 pts
    )

Wrapper de conveniencia para a CLI ``caos walk-forward run`` poder
instanciar a estrategia aprovada com um unico import path. Sem
parametros otimizaveis livres — todos sao descritos pela Decisao.

Uso:

    caos walk-forward run \
      --estrategia caos.walk_forward.estrategias.composicao_aprovada:EstrategiaORBCrabelSFCB \
      --identificador YYYY-MM-DD-NN
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from caos.walk_forward.estrategias.circuit_breaker import (
    EstrategiaCircuitBreaker,
    ParametrosCircuitBreaker,
)
from caos.walk_forward.estrategias.orb_crabel import EstrategiaORBCrabel
from caos.walk_forward.estrategias.spread_filter import (
    EstrategiaSpreadFilter,
    ParametrosSpreadFilter,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


class EstrategiaORBCrabelSFCB:
    """Composicao aprovada da Decisao 2026-05-25-02.

    Plugin que delega ao :class:`EstrategiaCircuitBreaker` ja composto
    com :class:`EstrategiaSpreadFilter` + :class:`EstrategiaORBCrabel`.
    """

    NOME: str = "EstrategiaORBCrabelSFCB"

    def __init__(self) -> None:
        # Camada interna: ORB filtrada por NR7 (Crabel).
        self._orb_crabel = EstrategiaORBCrabel(modo_nr="nr7")
        # Camada media: Spread Filter (mediana_diaria, running median, warmup 30).
        params_sf = ParametrosSpreadFilter(
            modo="mediana_diaria",
            minutos_warmup_dia=30,
        )
        self._sf = EstrategiaSpreadFilter(
            self._orb_crabel,
            parametros=params_sf,
        )
        # Camada externa: Circuit Breaker estendido (diario/semanal/janela em pontos).
        params_cb = ParametrosCircuitBreaker(
            limite_diario_pts=-250.0,
            limite_semanal_pts=-750.0,
            limite_janela_pts=-1000.0,
        )
        self._cb = EstrategiaCircuitBreaker(
            self._sf,
            parametros=params_cb,
        )

    def treinar(self, historico: pd.DataFrame) -> None:
        self._cb.treinar(historico)

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        self._cb.on_barra(barra, contexto)

    def finalizar(self) -> Sequence[Trade]:
        return self._cb.finalizar()

    @property
    def trades(self) -> Sequence[Trade]:
        return getattr(self._cb, "trades", ())


__all__ = ["EstrategiaORBCrabelSFCB"]
