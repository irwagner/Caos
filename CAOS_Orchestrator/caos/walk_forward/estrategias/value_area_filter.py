"""Plugin overlay ``EstrategiaValueAreaFilter`` — filtra entradas por regime via Value Area.

Tese (Market Profile clássico, 80% rule):

- **Dia TREND**: abertura **fora** da Value Area do dia anterior →
  alta probabilidade de movimento direcional. Estratégias de breakout
  (ORB, momentum) tem edge.
- **Dia RANGE**: abertura **dentro** da Value Area do dia anterior →
  alta probabilidade de retorno à Value Area / consolidação.
  Estratégias de breakout sofrem; reversão funciona melhor.

Implementação:

- Para cada dia D, calcula Value Area do dia D-1 (POC ± desvio padrão
  do volume até cobrir 70%).
- Quando o primeiro tick do dia D chega, classifica regime conforme
  abertura dentro/fora da VA do dia D-1.
- Em modo ``"trend"`` (default), bloqueia entradas em dias RANGE.
- Em modo ``"range"``, bloqueia entradas em dias TREND.

Fundamentos:

- CME Group: Value Area cobre ~68-70% do volume diário (1 desvio padrão).
- Tradição de Market Profile: ~80% dos dias com abertura fora da VA são
  TREND days (folclore profissional, sem paper acadêmico explícito).
- arXiv 2605.11423 propõe classifier semelhante (Volatility-Volume-Gap)
  para MNQ — pode ser evolução v2 desta abordagem.

Sem parâmetros otimizáveis livres: ``cobertura_va`` é fixa em 0.70
(constante de Market Profile) e ``modo`` é categórico (``"trend"``
ou ``"range"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, List, Literal, Optional, Sequence

import pandas as pd

from caos.walk_forward.metricas import Trade
from caos.walk_forward.runner import BarrasTesteIterator


ModoValueAreaFilter = Literal["trend", "range"]


#: Cobertura padrão da Value Area (CME Group: 1 desvio padrão = 68%
#: do volume; arredondado para 70% como convenção tradicional).
COBERTURA_VA_PADRAO: float = 0.70

#: Tamanho do bin de preço para construir o histograma de volume diário.
#: 0.25 pts = 1 tick MNQ. Granularidade fina o suficiente para captar
#: distribuição sem ruído excessivo.
TAMANHO_BIN_PRECO: float = 0.25


@dataclass(frozen=True)
class ValueAreaDia:
    """Resultado do cálculo de Value Area para um dia."""

    dia: date
    poc: float           # Point of Control: preço de maior volume
    va_low: float        # Limite inferior da Value Area
    va_high: float       # Limite superior da Value Area
    volume_total: float
    cobertura_real: float  # Fração efetiva atingida (próxima de 0.70)


@dataclass(frozen=True)
class ParametrosValueAreaFilter:
    """Parâmetros do filtro de Value Area."""

    modo: ModoValueAreaFilter = "trend"
    cobertura_va: float = COBERTURA_VA_PADRAO
    permitir_se_falta_dado: bool = True

    def __post_init__(self) -> None:
        if self.modo not in ("trend", "range"):
            raise ValueError(f"modo invalido: {self.modo!r}; use 'trend' ou 'range'")
        if not (0.50 <= self.cobertura_va <= 0.90):
            raise ValueError(
                f"cobertura_va deve estar em [0.50, 0.90]; recebido {self.cobertura_va}"
            )


def calcular_value_area(
    barras_dia: pd.DataFrame,
    cobertura: float = COBERTURA_VA_PADRAO,
    tamanho_bin: float = TAMANHO_BIN_PRECO,
) -> Optional[ValueAreaDia]:
    """Calcula Value Area de um dia usando histograma de volume.

    Algoritmo clássico de Market Profile (TPO/Volume Profile):
    1. Constrói histograma de volume por bin de preço.
    2. Identifica POC (bin com maior volume).
    3. Expande simetricamente do POC adicionando bins adjacentes
       (o de maior volume entre os candidatos acima/abaixo) até cobrir
       a fração ``cobertura`` do volume total.

    Retorna ``None`` se ``barras_dia`` está vazio ou volume total é zero.
    """
    if barras_dia.empty:
        return None
    volume_total = float(barras_dia["volume"].sum())
    if volume_total <= 0:
        return None

    dia = pd.Timestamp(barras_dia["timestamp"].iloc[0]).date()

    preco_min = float(barras_dia["low"].min())
    preco_max = float(barras_dia["high"].max())

    # Construção do histograma: para cada barra, atribui o volume aos
    # bins entre [low, high]. Aproximação clássica: distribui igualmente
    # (volume / num_bins_da_barra).
    n_bins = max(1, int((preco_max - preco_min) / tamanho_bin) + 1)
    histograma: dict[int, float] = {i: 0.0 for i in range(n_bins)}

    for _, barra in barras_dia.iterrows():
        bin_low = int((barra["low"] - preco_min) / tamanho_bin)
        bin_high = int((barra["high"] - preco_min) / tamanho_bin)
        bin_low = max(0, min(bin_low, n_bins - 1))
        bin_high = max(0, min(bin_high, n_bins - 1))
        n_bins_barra = bin_high - bin_low + 1
        vol_por_bin = float(barra["volume"]) / n_bins_barra
        for i in range(bin_low, bin_high + 1):
            histograma[i] += vol_por_bin

    # POC = bin com maior volume.
    poc_bin = max(histograma, key=lambda b: histograma[b])
    poc_preco = preco_min + (poc_bin + 0.5) * tamanho_bin

    # Expansão da Value Area: começa em POC, vai adicionando o lado
    # de maior volume até atingir cobertura.
    bins_va = {poc_bin}
    volume_va = histograma[poc_bin]
    cima = poc_bin + 1
    baixo = poc_bin - 1

    while volume_va / volume_total < cobertura and (cima < n_bins or baixo >= 0):
        vol_cima = histograma.get(cima, 0.0) if cima < n_bins else -1.0
        vol_baixo = histograma.get(baixo, 0.0) if baixo >= 0 else -1.0
        if vol_cima < 0 and vol_baixo < 0:
            break
        # Olha 2 bins de cada lado e escolhe o lado de maior volume.
        # Padrão clássico de Market Profile.
        if vol_cima >= vol_baixo:
            bins_va.add(cima)
            volume_va += histograma[cima]
            cima += 1
        else:
            bins_va.add(baixo)
            volume_va += histograma[baixo]
            baixo -= 1

    bin_va_low = min(bins_va)
    bin_va_high = max(bins_va)
    va_low = preco_min + bin_va_low * tamanho_bin
    va_high = preco_min + (bin_va_high + 1) * tamanho_bin

    return ValueAreaDia(
        dia=dia,
        poc=poc_preco,
        va_low=va_low,
        va_high=va_high,
        volume_total=volume_total,
        cobertura_real=volume_va / volume_total,
    )


class EstrategiaValueAreaFilter:
    """Wraps uma estrategia interna e bloqueia entradas conforme regime via VA.

    Em modo ``"trend"`` (default), libera entradas apenas em dias TREND
    (abertura **fora** da Value Area do dia anterior).

    Em modo ``"range"``, libera entradas apenas em dias RANGE (abertura
    **dentro** da Value Area do dia anterior).
    """

    NOME: str = "EstrategiaValueAreaFilter"

    def __init__(
        self,
        estrategia_interna: Any,
        *,
        parametros: Optional[ParametrosValueAreaFilter] = None,
    ) -> None:
        if not (
            callable(getattr(estrategia_interna, "on_barra", None))
            and callable(getattr(estrategia_interna, "finalizar", None))
        ):
            raise TypeError(
                "estrategia_interna deve implementar on_barra e finalizar"
            )
        self._interna = estrategia_interna
        self._parametros = parametros or ParametrosValueAreaFilter()

        # Mapas:
        #   _va_por_dia[d] = ValueAreaDia do dia d (calculada ao fechar d)
        #   _regime_por_dia[d] = "TREND" | "RANGE" | None (não classificável)
        self._va_por_dia: dict[date, ValueAreaDia] = {}
        self._regime_por_dia: dict[date, str] = {}

        # Memória do dia corrente para acumular barras antes de fechar.
        self._dia_corrente: Optional[date] = None
        self._barras_dia_corrente: list[pd.Series] = []
        # Histórico_treinar foi processado completo, marca para evitar
        # reprocessar quando on_barra começar.
        self._historico_processado: bool = False

        # Estatística (testes / auditoria).
        self._barras_recebidas: int = 0
        self._barras_bloqueadas: int = 0

    # ------------------------------------------------------------------
    # Protocol Estrategia (delegação)
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        treinar = getattr(self._interna, "treinar", None)
        if callable(treinar):
            treinar(historico)
        # Pré-computa Value Area de cada dia útil do treino.
        self._va_por_dia = {}
        self._regime_por_dia = {}
        if "timestamp" in historico.columns and not historico.empty:
            df = historico.copy()
            df["dia"] = df["timestamp"].dt.date
            for dia, grupo in df.groupby("dia"):
                va = calcular_value_area(grupo, cobertura=self._parametros.cobertura_va)
                if va is not None:
                    self._va_por_dia[dia] = va
        # Reset estatística por janela.
        self._barras_recebidas = 0
        self._barras_bloqueadas = 0
        self._dia_corrente = None
        self._barras_dia_corrente = []
        self._historico_processado = True

    def on_barra(
        self,
        barra: pd.Series,
        contexto: BarrasTesteIterator,
    ) -> None:
        self._barras_recebidas += 1
        ts = pd.Timestamp(barra["timestamp"])
        dia_atual = ts.date()

        # Acumula barra no dia corrente (para calcular VA ao fechar).
        if self._dia_corrente is None:
            self._dia_corrente = dia_atual
        elif dia_atual != self._dia_corrente:
            # Fecha o dia anterior: calcula VA e armazena.
            if self._barras_dia_corrente:
                df_dia = pd.DataFrame(self._barras_dia_corrente)
                va = calcular_value_area(
                    df_dia, cobertura=self._parametros.cobertura_va
                )
                if va is not None:
                    self._va_por_dia[self._dia_corrente] = va
            # Inicia novo dia.
            self._dia_corrente = dia_atual
            self._barras_dia_corrente = []

        self._barras_dia_corrente.append(barra)

        # Classifica regime do dia atual usando VA do dia anterior.
        if dia_atual not in self._regime_por_dia:
            regime = self._classificar_regime(dia_atual, ts, barra)
            if regime is not None:
                self._regime_por_dia[dia_atual] = regime

        # Aplica filtro: bloqueia entrada se regime do dia não casa com o modo.
        regime_dia = self._regime_por_dia.get(dia_atual)
        if not self._regime_permite_entrada(regime_dia):
            self._barras_bloqueadas += 1
            return

        self._interna.on_barra(barra, contexto)

    def finalizar(self) -> Sequence[Trade]:
        return self._interna.finalizar()

    # ------------------------------------------------------------------
    # Lógica de classificação
    # ------------------------------------------------------------------

    def _classificar_regime(
        self,
        dia_atual: date,
        ts: pd.Timestamp,
        barra: pd.Series,
    ) -> Optional[str]:
        """Classifica o dia atual como TREND ou RANGE com base na VA do dia anterior.

        Retorna ``None`` se o dia anterior não tem VA disponível (primeiro
        dia do treino, gap, etc).
        """
        # Procura o dia útil anterior mais recente com VA disponível.
        dias_anteriores = sorted(
            (d for d in self._va_por_dia.keys() if d < dia_atual), reverse=True
        )
        if not dias_anteriores:
            return None
        va_anterior = self._va_por_dia[dias_anteriores[0]]

        # Abertura do dia: usa o open da primeira barra recebida.
        preco_abertura = float(barra["open"])

        if preco_abertura > va_anterior.va_high or preco_abertura < va_anterior.va_low:
            return "TREND"
        return "RANGE"

    def _regime_permite_entrada(self, regime: Optional[str]) -> bool:
        if regime is None:
            # Sem classificação possível (primeiro dia do dataset, etc).
            return self._parametros.permitir_se_falta_dado
        if self._parametros.modo == "trend":
            return regime == "TREND"
        # modo == "range"
        return regime == "RANGE"

    # ------------------------------------------------------------------
    # Acessores (testes / auditoria)
    # ------------------------------------------------------------------

    @property
    def parametros(self) -> ParametrosValueAreaFilter:
        return self._parametros

    @property
    def estrategia_interna(self) -> Any:
        return self._interna

    @property
    def estatisticas(self) -> dict[str, int]:
        return {
            "barras_recebidas": self._barras_recebidas,
            "barras_bloqueadas": self._barras_bloqueadas,
            "dias_classificados": len(self._regime_por_dia),
            "dias_trend": sum(1 for r in self._regime_por_dia.values() if r == "TREND"),
            "dias_range": sum(1 for r in self._regime_por_dia.values() if r == "RANGE"),
        }

    @property
    def regime_por_dia(self) -> dict[date, str]:
        return dict(self._regime_por_dia)

    @property
    def va_por_dia(self) -> dict[date, ValueAreaDia]:
        return dict(self._va_por_dia)

    @property
    def trades(self) -> Sequence[Trade]:
        return getattr(self._interna, "trades", ())


__all__ = [
    "EstrategiaValueAreaFilter",
    "ParametrosValueAreaFilter",
    "ModoValueAreaFilter",
    "ValueAreaDia",
    "calcular_value_area",
    "COBERTURA_VA_PADRAO",
    "TAMANHO_BIN_PRECO",
]
