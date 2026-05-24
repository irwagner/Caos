"""Plugin ``EstrategiaOvernightDrift`` — overnight effect (Cooper 2008).

Hipotese declarada (sem parametros otimizaveis):

- ENTRADA: long no fechamento da sessao RTH (16:00 NY = 21:00 UTC).
- SAIDA: long sai na abertura da sessao RTH no proximo dia util
  (09:30 NY = 14:30 UTC).
- Holding: ~17.5 horas overnight.

Background (Cooper, Cliff & Gulen 2008, "A by Night"):

- Estudo de SPY/QQQ 1993-2006 mostrou que ~100% do retorno medio das
  acoes americanas vem do periodo overnight (close-to-open). Periodo
  RTH (open-to-close) e ligeiramente negativo em media.
- Replicado por Bondt-Lakonishok 2009 e Berkman-Liu 2017 em ETFs.
- O efeito persiste apos friccao em ETFs com spread baixo.

Por que pode funcionar em MNQ:

- MNQ futures negocia 23 horas/dia, mas o overnight effect e
  sobre o periodo de "fechamento dos mercados ativos" — definido
  aqui como 16:00 NY a 09:30 NY do dia seguinte (cerca de 17.5h).
- Se MNQ herda parte do drift overnight do equity index NDX, a
  estrategia simples de "comprar no close, vender no open" deve
  capturar parte desse drift.

Edge bruto esperado: ~50 pts/trade × ~250 trades/ano = ~12k pts/ano
(USD 24k bruto). Com friccao Topstep ~2.5 pts/trade × 250 = 625 pts
de friccao = 5% do edge bruto. Estrategia DEVE sobreviver friccao
pela regra ouro do sweep (edge bruto >> 5 pts/trade).

Decisoes de implementacao:

- Plugin streaming: detecta transicao para 21:00 UTC para abrir,
  detecta transicao para 14:30 UTC do dia seguinte para fechar.
- Em granularidade 1m, abertura e fechamento sao precisos.
- Em granularidade day, cada barra cobre 24h - usa close do dia
  como entrada e open do dia seguinte como saida.
- Sem holding em fins de semana: sexta-feira nao abre (saida seria
  na segunda, holding 65h, viola modelo Cooper).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import List, Optional, Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


#: Horario de fechamento da sessao RTH NY (UTC).
HORARIO_FECHAMENTO_RTH_UTC: time = time(21, 0)

#: Horario de abertura da sessao RTH NY (UTC).
HORARIO_ABERTURA_RTH_UTC: time = time(14, 30)


@dataclass
class _PosicaoOvernight:
    entrada_timestamp: datetime
    entrada_preco: float
    high_max: float
    low_min: float

    def atualizar(self, high: float, low: float) -> None:
        if high > self.high_max:
            self.high_max = high
        if low < self.low_min:
            self.low_min = low


class EstrategiaOvernightDrift:
    """Estrategia long-flat baseada no overnight effect (Cooper 2008).

    Sem parametros otimizaveis. Operacao:

    1. Long no fechamento da sessao RTH (21:00 UTC).
    2. Saida na abertura da sessao RTH no dia util seguinte (14:30 UTC).
    3. Pula sextas (saida seria segunda, holding 65h - viola modelo).
    """

    NOME: str = "EstrategiaOvernightDrift"

    def __init__(self, *, pular_sextas: bool = True) -> None:
        # pular_sextas=True (default) evita holding 65h sobre o weekend.
        # Pode ser desligado via --estrategia-args para teste.
        self._pular_sextas = pular_sextas
        self._trades: List[Trade] = []
        self._posicao: Optional[_PosicaoOvernight] = None
        self._ultimo_ts: Optional[datetime] = None
        self._ultimo_close: float = 0.0
        self._ultimo_high: float = 0.0
        self._ultimo_low: float = 0.0
        # Flag: na proxima barra com hora >= 14:30 UTC e dia diferente
        # da entrada, fecha a posicao.
        self._aguardando_abertura: bool = False

    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        """Reseta estado entre janelas WF."""
        self._trades = []
        self._posicao = None
        self._ultimo_ts = None
        self._ultimo_close = 0.0
        self._ultimo_high = 0.0
        self._ultimo_low = 0.0
        self._aguardando_abertura = False

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        ts = self._timestamp_de_barra(barra)
        close = float(barra["close"])
        high = float(barra["high"])
        low = float(barra["low"])
        open_b = float(barra["open"])
        hora = ts.time()

        # Atualiza excursao da posicao.
        if self._posicao is not None:
            self._posicao.atualizar(high, low)

        # Decisao de SAIDA: estamos aguardando abertura RTH e a barra
        # atual cruza o horario.
        if (
            self._posicao is not None
            and self._aguardando_abertura
            and hora >= HORARIO_ABERTURA_RTH_UTC
            and ts.date() != self._posicao.entrada_timestamp.date()
        ):
            # Fecha pelo open desta barra (proxy para "abertura RTH").
            self._fechar_posicao(ts=ts, preco=open_b)
            self._aguardando_abertura = False

        # Decisao de ENTRADA: estamos no horario de fechamento RTH e
        # nao temos posicao aberta.
        # A entrada acontece na PRIMEIRA barra cujo horario >= 21:00
        # UTC do dia (em granularidade 1m, sera 21:00 exato; em day,
        # sera a unica barra do dia).
        if (
            self._posicao is None
            and hora >= HORARIO_FECHAMENTO_RTH_UTC
            and self._eh_entrada_valida(ts)
        ):
            self._abrir_posicao(ts, close, high, low)
            self._aguardando_abertura = True

        self._ultimo_ts = ts
        self._ultimo_close = close
        self._ultimo_high = high
        self._ultimo_low = low

    def finalizar(self) -> Sequence[Trade]:
        """Fecha posicao residual com ultimo close visto."""
        if self._posicao is not None and self._ultimo_ts is not None:
            self._fechar_posicao(ts=self._ultimo_ts, preco=self._ultimo_close)
        return list(self._trades)

    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp_de_barra(barra: pd.Series) -> datetime:
        ts = pd.Timestamp(barra["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def _eh_entrada_valida(self, ts: datetime) -> bool:
        """True se este timestamp pode iniciar entrada overnight.

        Pula sexta-feira (weekday=4) por default — saida seria na
        proxima segunda, holding 65h, viola modelo Cooper.
        """
        if not self._pular_sextas:
            return True
        return ts.weekday() != 4  # sexta=4 segundo datetime

    def _abrir_posicao(
        self, ts: datetime, preco: float, high: float, low: float
    ) -> None:
        self._posicao = _PosicaoOvernight(
            entrada_timestamp=ts,
            entrada_preco=preco,
            high_max=high,
            low_min=low,
        )

    def _fechar_posicao(self, *, ts: datetime, preco: float) -> None:
        if self._posicao is None:
            return
        if ts <= self._posicao.entrada_timestamp:
            ts = self._posicao.entrada_timestamp + pd.Timedelta(seconds=1)
        mfe = max(0.0, self._posicao.high_max - self._posicao.entrada_preco)
        mae = min(0.0, self._posicao.low_min - self._posicao.entrada_preco)
        self._trades.append(
            Trade(
                entrada_timestamp=self._posicao.entrada_timestamp,
                saida_timestamp=ts,
                entrada_preco=self._posicao.entrada_preco,
                saida_preco=preco,
                lado="long",
                contratos=1,
                mfe_pontos=mfe,
                mae_pontos=mae,
            )
        )
        self._posicao = None

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)


__all__ = [
    "EstrategiaOvernightDrift",
    "HORARIO_ABERTURA_RTH_UTC",
    "HORARIO_FECHAMENTO_RTH_UTC",
]
