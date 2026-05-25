"""Plugin overlay ``EstrategiaSpreadFilter`` — filtra minutos por spread.

Wraps qualquer Estrategia plugável e bloqueia ``on_barra`` em minutos
de spread alto. Implementa o Spread Filter overlay da segunda rodada
do briefing do Explorador (commit faea51c) usando o spread agregado
real medido pelo agregar_spread_tick.py (commit 635b912 e seguintes).

Tese declarada (sem parametros otimizaveis livres):

- Cada minuto do tick agregado tem um ``spread_avg``.
- A friccao realizada e proporcional ao spread (sweep 2026-05-24-10..14
  confirmou: PnL decai linear com sf, ~80 pts por step de 0.025).
- Logo, **operar SO em minutos com spread <= mediana do dia** elimina
  ~50% das observacoes e mantem o lado mais favoravel.

Variantes categoricas (nao otimizacao):

- ``modo="mediana_diaria"`` (default): bloqueia minutos com
  ``spread_avg > mediana(spreads_do_dia_atual)``. Reage por dia.
- ``modo="quantil_global"``: bloqueia minutos com
  ``spread_avg > p75(spreads_do_dataset)``. Calibra uma vez no Treino.
- ``modo="hora_otima"``: simplificacao - so opera entre 14h e 19h UTC
  (RTH NY de menor spread observado). Nao precisa do CSV.

O CSV ``spread_minuto.csv`` precisa ja ter sido gerado para os
contratos relevantes. Se faltar dados de algum minuto, a politica
default e PERMITIR (regra "in dubio, deixa passar").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, List, Literal, Optional, Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


ModoSpreadFilter = Literal["mediana_diaria", "quantil_global", "hora_otima"]


def _carregar_spread_csvs(
    caminhos: Iterable[Path],
) -> pd.DataFrame:
    """Concatena spread_minuto.csv de varios contratos em um DataFrame
    indexado por timestamp UTC.

    Filtra entradas sem spread_avg ou com spread_avg > 5 pts (outliers
    de fim de contrato).
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
        return pd.DataFrame(
            columns=["minuto_utc", "spread_avg"]
        )
    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.dropna(subset=["spread_avg"])
    df_all = df_all[df_all["spread_avg"].between(0, 5)].copy()
    # Pode haver duplicatas entre contratos (transicao). Mantem media.
    df_all = (
        df_all.groupby("minuto_utc", as_index=False)["spread_avg"]
        .mean()
        .sort_values("minuto_utc")
        .reset_index(drop=True)
    )
    return df_all


@dataclass(frozen=True)
class ParametrosSpreadFilter:
    """Parametros do filtro de spread.

    ``modo``: estrategia de filtro. Default ``mediana_diaria``.
    ``quantil_corte``: usado no modo ``quantil_global``. Default 0.5
    (mediana global). Range valido [0.10, 0.95].
    ``hora_inicio_utc`` / ``hora_fim_utc``: usados no modo
    ``hora_otima``. Defaults RTH NY (14:30 -> 19:00 UTC, horas de
    menor spread medido em 14 meses).
    ``permitir_se_falta_dado``: o que fazer quando o spread_minuto.csv
    nao tem entrada para o minuto sendo testado. ``True`` (default)
    = permite o trade. ``False`` = bloqueia.
    """

    modo: ModoSpreadFilter = "mediana_diaria"
    quantil_corte: float = 0.5
    hora_inicio_utc: time = time(14, 30)
    hora_fim_utc: time = time(19, 0)
    permitir_se_falta_dado: bool = True

    def __post_init__(self) -> None:
        if self.modo not in ("mediana_diaria", "quantil_global", "hora_otima"):
            raise ValueError(f"modo invalido: {self.modo!r}")
        if not (0.10 <= self.quantil_corte <= 0.95):
            raise ValueError(
                f"quantil_corte deve estar em [0.10, 0.95]; recebido {self.quantil_corte}"
            )
        if self.hora_inicio_utc >= self.hora_fim_utc:
            raise ValueError(
                "hora_inicio_utc deve ser anterior a hora_fim_utc"
            )


class EstrategiaSpreadFilter:
    """Wraps uma Estrategia interna e filtra ``on_barra`` por spread alto.

    Se a barra atual estiver em minuto bloqueado, NAO chama
    ``estrategia_interna.on_barra``. ``finalizar`` e ``treinar`` sao
    repassados sem mudanca.
    """

    NOME: str = "EstrategiaSpreadFilter"

    def __init__(
        self,
        estrategia_interna: Any,
        *,
        parametros: Optional[ParametrosSpreadFilter] = None,
        caminhos_spread_csv: Optional[Iterable[Path]] = None,
    ) -> None:
        if not (
            callable(getattr(estrategia_interna, "on_barra", None))
            and callable(getattr(estrategia_interna, "finalizar", None))
        ):
            raise TypeError(
                "estrategia_interna deve implementar on_barra e finalizar"
            )
        self._interna = estrategia_interna
        self._parametros = parametros or ParametrosSpreadFilter()
        # Carrega CSVs de spread, se modo precisa.
        if self._parametros.modo in ("mediana_diaria", "quantil_global"):
            paths = list(caminhos_spread_csv or [])
            if not paths:
                # Auto-discovery: procura em dados/MNQ/*/tick/.
                raiz = Path(r"e:\CAOS\dados\MNQ")
                paths = list(raiz.glob("MNQ_*/tick/spread_minuto.csv"))
            self._spread_df = _carregar_spread_csvs(paths)
            # Indexa por minuto_utc para lookup O(1).
            if not self._spread_df.empty:
                self._spread_df = self._spread_df.set_index("minuto_utc")
            # Para modo quantil_global, calcula corte uma vez.
            if self._parametros.modo == "quantil_global" and not self._spread_df.empty:
                self._corte_global = float(
                    self._spread_df["spread_avg"].quantile(
                        self._parametros.quantil_corte
                    )
                )
            else:
                self._corte_global = None
            # Cache da mediana por dia (preenchido on-demand).
            self._mediana_dia_cache: dict[date, float] = {}
        else:
            self._spread_df = pd.DataFrame()
            self._corte_global = None
            self._mediana_dia_cache = {}

        # Estatistica observavel (testes / auditoria).
        self._barras_recebidas: int = 0
        self._barras_bloqueadas: int = 0

    # ------------------------------------------------------------------
    # Protocol Estrategia (delegacao)
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        treinar = getattr(self._interna, "treinar", None)
        if callable(treinar):
            treinar(historico)
        # Reset estatisticas por janela.
        self._barras_recebidas = 0
        self._barras_bloqueadas = 0
        self._mediana_dia_cache = {}

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        self._barras_recebidas += 1
        ts = self._timestamp_de_barra(barra)
        if not self._minuto_permitido(ts):
            self._barras_bloqueadas += 1
            return
        self._interna.on_barra(barra, contexto)

    def finalizar(self) -> Sequence[Trade]:
        return self._interna.finalizar()

    # ------------------------------------------------------------------
    # Logica de filtro
    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp_de_barra(barra: pd.Series) -> datetime:
        ts = pd.Timestamp(barra["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def _minuto_permitido(self, ts: datetime) -> bool:
        modo = self._parametros.modo
        if modo == "hora_otima":
            hora = ts.time()
            return (
                self._parametros.hora_inicio_utc <= hora < self._parametros.hora_fim_utc
            )

        # Modos baseados em CSV.
        if self._spread_df.empty:
            return self._parametros.permitir_se_falta_dado

        # Trunca para minuto inteiro para lookup.
        chave = ts.replace(second=0, microsecond=0)
        chave_pd = pd.Timestamp(chave)
        if chave_pd not in self._spread_df.index:
            return self._parametros.permitir_se_falta_dado

        spread = float(self._spread_df.loc[chave_pd, "spread_avg"])

        if modo == "quantil_global":
            if self._corte_global is None:
                return self._parametros.permitir_se_falta_dado
            return spread <= self._corte_global

        # mediana_diaria.
        dia = ts.date()
        mediana = self._mediana_dia_cache.get(dia)
        if mediana is None:
            mediana = self._calcular_mediana_dia(dia)
            self._mediana_dia_cache[dia] = mediana
        if mediana <= 0:
            return self._parametros.permitir_se_falta_dado
        return spread <= mediana

    def _calcular_mediana_dia(self, dia: date) -> float:
        """Calcula mediana de spread para o dia. Cache simples."""
        # Filtra index pelo dia.
        if self._spread_df.empty:
            return 0.0
        idx = self._spread_df.index
        mask = (idx.date == dia)  # type: ignore[union-attr]
        sub = self._spread_df.loc[mask, "spread_avg"]
        if sub.empty:
            return 0.0
        return float(sub.median())

    # ------------------------------------------------------------------
    # Acessores
    # ------------------------------------------------------------------

    @property
    def parametros(self) -> ParametrosSpreadFilter:
        return self._parametros

    @property
    def estrategia_interna(self) -> Any:
        return self._interna

    @property
    def estatisticas(self) -> dict[str, int]:
        """Devolve dict com barras_recebidas e barras_bloqueadas."""
        return {
            "barras_recebidas": self._barras_recebidas,
            "barras_bloqueadas": self._barras_bloqueadas,
        }

    @property
    def trades(self) -> Sequence[Trade]:
        return getattr(self._interna, "trades", ())


__all__ = [
    "EstrategiaSpreadFilter",
    "ModoSpreadFilter",
    "ParametrosSpreadFilter",
]
