"""Estratégias-stub para testes e exemplos do CLI ``caos walk-forward``.

Este módulo expõe :class:`EstrategiaExemplo`, um plugin determinístico
mínimo compatível com o protocolo
:class:`caos.walk_forward.runner.Estrategia`. Não reflete nenhuma
estratégia de trading real — sua única razão de existir é permitir que o
subcomando ``caos walk-forward run`` tenha um caminho-feliz testável
ponta-a-ponta sem depender de Specs 4+.

Comportamento (determinístico):

- ``treinar(historico)``: zera o buffer de trades.
- ``on_barra(barra, contexto)``: a cada N-ésima barra de Teste (com
  ``N == ESPACAMENTO_TRADES``, default 3), abre e fecha imediatamente um
  trade ``long`` de 1 contrato com PnL = ``+0.5`` ponto. Como
  ``saida_timestamp`` é exigido estritamente posterior a
  ``entrada_timestamp`` pelo modelo, somamos 1 minuto à entrada.
- ``finalizar()``: devolve a lista acumulada de :class:`Trade`.

Para uma estratégia que dispara em **toda** barra do Teste, use
``EstrategiaExemplo(espacamento=1)``. Estratégias que não emitem trades
geram ``status="sem-trades"`` no :class:`ResultadoJanela` (R6.2).

Convenções: pt-BR (R3.2 do Spec 1), Pydantic v2, Windows + cmd.
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator

#: Espaçamento default entre trades sucessivos (1 trade a cada N barras).
ESPACAMENTO_TRADES: int = 3


class EstrategiaExemplo:
    """Estratégia-stub determinística para testes do ``caos walk-forward``.

    Parameters
    ----------
    espacamento:
        Número de barras de Teste entre dois trades emitidos. Inteiro
        ``>= 1``. Default: :data:`ESPACAMENTO_TRADES`.
    pnl_por_trade:
        PnL do trade sintético em pontos × contratos. Default: ``0.5``.
    """

    NOME: str = "EstrategiaExemplo"

    def __init__(
        self,
        *,
        espacamento: int = ESPACAMENTO_TRADES,
        pnl_por_trade: float = 0.5,
    ) -> None:
        if espacamento < 1:
            raise ValueError(
                "espacamento deve ser inteiro >= 1; "
                f"recebido {espacamento}"
            )
        self._espacamento = int(espacamento)
        self._pnl_por_trade = float(pnl_por_trade)
        self._trades: list[Trade] = []
        self._contador_barras: int = 0

    # ------------------------------------------------------------------
    # Protocolo Estrategia
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        # A Engine reusa a mesma instância em cada janela; resetar o
        # estado em ``treinar`` é a forma idiomática de isolar janelas.
        self._trades = []
        self._contador_barras = 0

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        self._contador_barras += 1
        if self._contador_barras % self._espacamento != 0:
            return

        ts_entrada = pd.Timestamp(barra["timestamp"]).to_pydatetime()
        ts_saida = (
            pd.Timestamp(barra["timestamp"]) + pd.Timedelta(minutes=1)
        ).to_pydatetime()
        preco_entrada = float(barra["close"])
        preco_saida = preco_entrada + self._pnl_por_trade
        self._trades.append(
            Trade(
                entrada_timestamp=ts_entrada,
                saida_timestamp=ts_saida,
                entrada_preco=preco_entrada,
                saida_preco=preco_saida,
                lado="long",
                contratos=1,
                mfe_pontos=abs(self._pnl_por_trade),
                mae_pontos=0.0,
            )
        )

    def finalizar(self) -> Sequence[Trade]:
        return list(self._trades)


__all__ = [
    "ESPACAMENTO_TRADES",
    "EstrategiaExemplo",
]
