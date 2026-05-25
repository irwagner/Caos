"""Plugin ``EstrategiaOFI`` — Trade Flow Imbalance momentum.

Baseado em Cont-Larrard 2014 ("Order Book Dynamics in Liquid Markets")
e literatura subsequente sobre microestrutura. A tese e:

> Quando a pressao agressiva de buy ou sell em um intervalo curto
> excede um threshold, o preço tende a continuar na mesma direcao
> nos minutos seguintes (efeito momentum de curto prazo).

Implementacao no CAOS:

- Usa ``ofi_minuto.csv`` agregado por ``scripts/agregar_ofi_tick.py``,
  que classifica cada Last como buy/sell aggressive via Lee-Ready.
- Por minuto, computa ``tfi = buy_volume - sell_volume`` e
  ``tfi_norm = tfi / (buy_volume + sell_volume)`` ∈ [-1, 1].
- Mantem janela rolante de N minutos do TFI normalizado.
- Quando ``soma_tfi_janela`` excede ``+threshold`` -> entrada LONG.
- Quando excede ``-threshold`` -> entrada SHORT.
- Saida: TFI reverte, ou apos K minutos, ou stop/alvo.

Sem parametros otimizaveis livres alem dos defaults derivados do
paper/empiricos:
- ``janela_minutos = 5`` (curtas alavancam momentum, longas captam
  reversao).
- ``threshold_tfi_acumulado = 2.0`` (~2 desvios da media historica).
- ``minutos_max_holding = 15`` (forca exit pra evitar reversao).
- ``stop_pontos = 5.0`` (stop fixo conservador).
- ``alvo_pontos = 10.0`` (R:R 2:1).

Variantes categoricas (nao otimizacao):
- ``modo = "momentum"`` (default): segue o sinal.
- ``modo = "mean_reversion"``: inverte (testar fade do TFI extremo).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Deque, Iterable, List, Literal, Optional, Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


ModoOFI = Literal["momentum", "mean_reversion"]


@dataclass(frozen=True)
class ParametrosOFI:
    """Parametros da EstrategiaOFI.

    Defaults sao heuristicos derivados de Cont-Larrard 2014 +
    caracterizacao empirica do MNQ. Range testado e documentado
    em comentario para evitar otimizacao livre.
    """

    janela_minutos: int = 5
    threshold_tfi_acumulado: float = 2.0  # ~2 sd
    minutos_max_holding: int = 15
    stop_pontos: float = 5.0
    alvo_pontos: float = 10.0
    modo: ModoOFI = "momentum"
    sessao_inicio_utc: time = time(13, 30)  # NY open 9:30 ET
    sessao_fim_utc: time = time(20, 0)  # NY 4:00 PM
    apenas_long: bool = False
    apenas_short: bool = False

    def __post_init__(self) -> None:
        if not (1 <= self.janela_minutos <= 60):
            raise ValueError(f"janela_minutos em [1,60]; recebido {self.janela_minutos}")
        if self.threshold_tfi_acumulado <= 0:
            raise ValueError(f"threshold_tfi_acumulado > 0; recebido {self.threshold_tfi_acumulado}")
        if not (1 <= self.minutos_max_holding <= 480):
            raise ValueError(f"minutos_max_holding em [1,480]; recebido {self.minutos_max_holding}")
        if self.stop_pontos <= 0:
            raise ValueError("stop_pontos > 0")
        if self.alvo_pontos <= 0:
            raise ValueError("alvo_pontos > 0")
        if self.modo not in ("momentum", "mean_reversion"):
            raise ValueError(f"modo invalido: {self.modo}")
        if self.sessao_inicio_utc >= self.sessao_fim_utc:
            raise ValueError("sessao_inicio_utc anterior a sessao_fim_utc")
        if self.apenas_long and self.apenas_short:
            raise ValueError("apenas_long e apenas_short nao podem ser ambos True")


@dataclass
class _PosicaoOFI:
    lado: str
    entrada_timestamp: datetime
    entrada_preco: float
    high_max: float
    low_min: float
    stop: float
    alvo: float
    minuto_entrada: int  # contador interno para max_holding

    def atualizar(self, high: float, low: float) -> None:
        if high > self.high_max:
            self.high_max = high
        if low < self.low_min:
            self.low_min = low


def _carregar_ofi_csvs(caminhos: Iterable[Path]) -> pd.DataFrame:
    """Concatena ofi_minuto.csv de varios contratos em DataFrame
    indexado por minuto_utc.
    """
    dfs: List[pd.DataFrame] = []
    for caminho in caminhos:
        p = Path(caminho)
        if not p.is_file():
            continue
        df = pd.read_csv(p, parse_dates=["minuto_utc"])
        df["minuto_utc"] = pd.to_datetime(df["minuto_utc"], utc=True)
        dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=["minuto_utc", "tfi_norm"])
    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.dropna(subset=["tfi_norm"])
    # Pode haver duplicatas entre contratos no roll. Mantem media.
    df_all = (
        df_all.groupby("minuto_utc", as_index=False)["tfi_norm"]
        .mean()
        .sort_values("minuto_utc")
        .reset_index(drop=True)
    )
    return df_all


class EstrategiaOFI:
    """Plugin que opera momentum/mean-reversion baseado em Trade Flow
    Imbalance.

    Args:
        parametros: :class:`ParametrosOFI` opcional (default = paper).
        caminhos_ofi_csv: lista de paths para ``ofi_minuto.csv``. Se
            None, auto-discovery em ``dados/MNQ/MNQ_*/tick/``.
    """

    NOME: str = "EstrategiaOFI"

    def __init__(
        self,
        parametros: Optional[ParametrosOFI] = None,
        *,
        caminhos_ofi_csv: Optional[Iterable[Path]] = None,
    ) -> None:
        self._parametros = parametros or ParametrosOFI()
        # Carrega CSVs de OFI uma vez.
        paths = list(caminhos_ofi_csv or [])
        if not paths:
            raiz = Path(r"e:\CAOS\dados\MNQ")
            paths = list(raiz.glob("MNQ_*/tick/ofi_minuto.csv"))
        self._ofi_df = _carregar_ofi_csvs(paths)
        if not self._ofi_df.empty:
            self._minuto_para_tfi = self._ofi_df.set_index("minuto_utc")["tfi_norm"].to_dict()
        else:
            self._minuto_para_tfi = {}

        # Estado.
        self._janela_tfi: Deque[float] = deque(maxlen=self._parametros.janela_minutos)
        self._posicao: Optional[_PosicaoOFI] = None
        self._trades: List[Trade] = []
        self._minuto_count: int = 0
        self._ultimo_close: Optional[float] = None
        self._ultimo_ts: Optional[datetime] = None

    def treinar(self, historico: pd.DataFrame) -> None:
        """Reseta estado por janela WF."""
        self._janela_tfi.clear()
        self._posicao = None
        self._trades = []
        self._minuto_count = 0
        self._ultimo_close = None
        self._ultimo_ts = None

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        ts = self._timestamp_de_barra(barra)
        close = float(barra["close"])
        high = float(barra["high"])
        low = float(barra["low"])

        # Atualiza excursoes.
        if self._posicao is not None:
            self._posicao.atualizar(high, low)

        # Atualiza janela TFI a partir do CSV agregado.
        chave = ts.replace(second=0, microsecond=0)
        chave_pd = pd.Timestamp(chave)
        tfi_norm = self._minuto_para_tfi.get(chave_pd)
        if tfi_norm is not None:
            self._janela_tfi.append(float(tfi_norm))

        # Saida da posicao se aberta: stop/alvo/max_holding/sessao_fim.
        if self._posicao is not None:
            # Stop hit.
            if self._posicao.lado == "long" and low <= self._posicao.stop:
                self._fechar(ts=ts, preco=self._posicao.stop)
                return
            if self._posicao.lado == "short" and high >= self._posicao.stop:
                self._fechar(ts=ts, preco=self._posicao.stop)
                return
            # Alvo hit.
            if self._posicao.lado == "long" and high >= self._posicao.alvo:
                self._fechar(ts=ts, preco=self._posicao.alvo)
                return
            if self._posicao.lado == "short" and low <= self._posicao.alvo:
                self._fechar(ts=ts, preco=self._posicao.alvo)
                return
            # Max holding (em minutos).
            if (self._minuto_count - self._posicao.minuto_entrada) >= self._parametros.minutos_max_holding:
                self._fechar(ts=ts, preco=close)
                return
            # Forca exit fim de sessao.
            if ts.time() >= self._parametros.sessao_fim_utc:
                self._fechar(ts=ts, preco=close)
                return

        self._minuto_count += 1
        self._ultimo_close = close
        self._ultimo_ts = ts

        # Sem posicao aberta: avalia entrada.
        if self._posicao is None:
            # Sessao deve estar dentro do range autorizado.
            if not (self._parametros.sessao_inicio_utc <= ts.time() < self._parametros.sessao_fim_utc):
                return
            # Janela cheia?
            if len(self._janela_tfi) < self._parametros.janela_minutos:
                return
            soma = sum(self._janela_tfi)
            threshold = self._parametros.threshold_tfi_acumulado
            sinal = 0
            if soma >= threshold:
                sinal = 1  # buy aggressive acumulado
            elif soma <= -threshold:
                sinal = -1  # sell aggressive acumulado

            if sinal == 0:
                return

            # Determina direcao final pelo modo.
            if self._parametros.modo == "momentum":
                lado = "long" if sinal == 1 else "short"
            else:  # mean_reversion
                lado = "short" if sinal == 1 else "long"

            # Filtros direcionais.
            if lado == "long" and self._parametros.apenas_short:
                return
            if lado == "short" and self._parametros.apenas_long:
                return

            self._abrir(lado, ts, close, high, low)

    def finalizar(self) -> Sequence[Trade]:
        """Forca exit residual."""
        if self._posicao is not None and self._ultimo_ts is not None and self._ultimo_close is not None:
            self._fechar(ts=self._ultimo_ts, preco=self._ultimo_close)
        return list(self._trades)

    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp_de_barra(barra: pd.Series) -> datetime:
        ts = pd.Timestamp(barra["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def _abrir(self, lado: str, ts: datetime, preco: float, high: float, low: float) -> None:
        if lado == "long":
            stop = preco - self._parametros.stop_pontos
            alvo = preco + self._parametros.alvo_pontos
        else:
            stop = preco + self._parametros.stop_pontos
            alvo = preco - self._parametros.alvo_pontos
        self._posicao = _PosicaoOFI(
            lado=lado,
            entrada_timestamp=ts,
            entrada_preco=preco,
            high_max=high,
            low_min=low,
            stop=stop,
            alvo=alvo,
            minuto_entrada=self._minuto_count,
        )

    def _fechar(self, *, ts: datetime, preco: float) -> None:
        if self._posicao is None:
            return
        if ts <= self._posicao.entrada_timestamp:
            ts = self._posicao.entrada_timestamp + pd.Timedelta(seconds=1)
        if self._posicao.lado == "long":
            mfe = max(0.0, self._posicao.high_max - self._posicao.entrada_preco)
            mae = min(0.0, self._posicao.low_min - self._posicao.entrada_preco)
        else:
            mfe = max(0.0, self._posicao.entrada_preco - self._posicao.low_min)
            mae = min(0.0, self._posicao.entrada_preco - self._posicao.high_max)
        self._trades.append(
            Trade(
                entrada_timestamp=self._posicao.entrada_timestamp,
                saida_timestamp=ts,
                entrada_preco=self._posicao.entrada_preco,
                saida_preco=preco,
                lado=self._posicao.lado,  # type: ignore[arg-type]
                contratos=1,
                mfe_pontos=mfe,
                mae_pontos=mae,
            )
        )
        self._posicao = None

    @property
    def parametros(self) -> ParametrosOFI:
        return self._parametros

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)


__all__ = ["EstrategiaOFI", "ModoOFI", "ParametrosOFI"]
