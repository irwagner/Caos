"""Classificador VVG stateful (Spec — VVG Late-Session Reversal, Tarefa 3).

Implementa :class:`VvgClassifier`, o classificador de regime
**Volatility-Volume-Gap** de Mesfin (arXiv 2605.11423) adaptado ao MNQ.
Cobre R1.1, R1.2, R1.4 e R1.5 do ``requirements.md`` desta feature.

Decisão arquitetural-chave
--------------------------
O classificador é **stateful porém determinístico**: todo o seu estado é
função apenas das barras já vistas (sem random, sem I/O, sem relógio
real). Ele mantém um baseline rolling do ``volume_morning`` dos últimos
``n_dias_baseline`` dias úteis válidos e o ``close`` da sessão RTH do dia
anterior, e determina ``vvg_positivo`` quando a janela morning de um dia
fecha (primeira barra com hora >= 10:00 EST).

Janela morning — decisão CONGELADA da Tarefa 1
----------------------------------------------
A Tarefa 1 (ver ``Calibracao_VVG_2026-05-29.md``) confirmou que a janela
do ``volume_morning`` **e** a janela do baseline de volume são **ambas**
de 30 minutos ``[09:30, 10:00)`` EST. Misturar 30 min (morning) com
60 min (baseline) colapsa a elegibilidade para 1.9% (sweep de
sensibilidade). Portanto este módulo usa a **mesma janela de 30 min**
para os dois — o baseline de um dia é simplesmente a média do
``volume_morning`` dos N dias úteis válidos anteriores.

Conversão de fuso (DST automático)
----------------------------------
O dataset canônico do ``Skill_Data_Reader`` traz ``timestamp`` em UTC
(``datetime64[ns, UTC]``). O RTH do MNQ é definido em horário de Nova
York (09:30–16:00). Como o offset EST/EDT muda com o horário de verão
americano, **não** se faz hardcode de offset: cada barra é convertida
para ``America/New_York`` via :mod:`zoneinfo`, que resolve o DST
automaticamente. A porta C# (``EstrategiaVvgClassifierLogica.cs``,
Tarefa 7) usa ``TimeZoneInfo`` para o mesmo efeito.

Portabilidade Python↔C# (Tarefa 9)
----------------------------------
A lógica é escrita com loops e condicionais explícitas (sem truques
pythônicos) para ser portada literalmente para C#. A paridade
trade-a-trade é exigida na Tarefa 9 (Property 11) — R1.6.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import date, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

# ---------------------------------------------------------------------------
# Coordenação com a Tarefa 2 (vvg_logica.py) — import defensivo
# ---------------------------------------------------------------------------
#
# O ideal é importar ``ParametrosVvg`` do módulo canônico ``vvg_logica``
# (Tarefa 2). Como a Tarefa 2 roda em paralelo, pode haver uma corrida em
# que o arquivo ainda não exista no momento deste import. Para não
# quebrar o ``import`` deste módulo (verificado na Tarefa 3), fazemos um
# import tardio/defensivo: se ``vvg_logica`` não estiver disponível,
# usamos um fallback mínimo local com os mesmos três campos consumidos
# pelo classificador (``multiplicador_volume``, ``threshold_gap_pct`` e
# ``n_dias_baseline``). Os valores default do fallback são os
# **CONGELADOS** na Tarefa 1.
try:  # pragma: no cover - caminho exercido conforme a ordem das tarefas
    from caos.walk_forward.estrategias.vvg_logica import (  # type: ignore
        ParametrosVvg as _ParametrosVvgCanonico,
    )
except Exception:  # ImportError em corrida com a Tarefa 2.
    _ParametrosVvgCanonico = None


# ---------------------------------------------------------------------------
# Constantes congeladas (Tarefa 1 — Calibracao_VVG_2026-05-29.md)
# ---------------------------------------------------------------------------

#: Multiplicador de volume congelado (anti-overfit). ``vvg_positivo``
#: exige ``volume_morning >= multiplicador_volume * volume_baseline``.
MULTIPLICADOR_VOLUME_PADRAO: float = 1.5

#: Threshold de gap congelado (fração, não %). ``vvg_positivo`` exige
#: ``gap_pct >= threshold_gap_pct``. 0.0015 = 0.15%.
THRESHOLD_GAP_PCT_PADRAO: float = 0.0015

#: Janela do baseline rolling de volume, em dias úteis válidos.
N_DIAS_BASELINE_PADRAO: int = 10

#: Número mínimo de barras de minuto que um dia precisa ter para ser
#: contado como dia útil válido (constante herdada do Spec 4 —
#: Decisao 2026-05-26-01). Pregão regular MNQ ~= 1380 barras; abertura
#: noturna de fim de semana no Globex tem ~120-300 barras. O limiar 300
#: descarta sessões truncadas. Observação: 300 barras ~= os 300 minutos
#: de 09:30 a 14:30 EST — ou seja, qualquer dia que efetivamente alcança
#: o horário de entrada da estratégia (14:30 EST) já satisfaz o limiar.
MIN_BARRAS_DIA_VALIDO: int = 300

#: Fuso de Nova York (DST resolvido pela biblioteca, sem offset fixo).
_TZ_NY = ZoneInfo("America/New_York")

#: Janela morning ``[09:30, 10:00)`` EST (wall-clock de Nova York).
HORA_MORNING_INICIO: time = time(9, 30)
HORA_MORNING_FIM: time = time(10, 0)

#: Sessão RTH ``[09:30, 16:00)`` EST. Usada para capturar o ``close``
#: de fim de RTH do dia anterior (``close(D-1)`` do gap).
HORA_RTH_INICIO: time = time(9, 30)
HORA_RTH_FIM: time = time(16, 0)


# ---------------------------------------------------------------------------
# Fallback mínimo de ParametrosVvg (apenas se vvg_logica ainda não existe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ParametrosVvgMinimo:
    """Fallback local de ``ParametrosVvg`` (coordenação com a Tarefa 2).

    Carrega apenas os três campos que o classificador consome. Os defaults
    são os valores **CONGELADOS** na Tarefa 1. Quando ``vvg_logica`` está
    disponível, o nome público :data:`ParametrosVvg` aponta para a versão
    canônica e este fallback não é usado.
    """

    multiplicador_volume: float = MULTIPLICADOR_VOLUME_PADRAO
    threshold_gap_pct: float = THRESHOLD_GAP_PCT_PADRAO
    n_dias_baseline: int = N_DIAS_BASELINE_PADRAO


#: Nome público de ``ParametrosVvg``: canônico (Tarefa 2) quando
#: disponível, fallback mínimo caso contrário.
if _ParametrosVvgCanonico is not None:  # pragma: no cover - depende da ordem
    ParametrosVvg = _ParametrosVvgCanonico
else:
    ParametrosVvg = _ParametrosVvgMinimo


# ---------------------------------------------------------------------------
# Resultado da classificação
# ---------------------------------------------------------------------------


@dataclass
class ResultadoClassificacao:
    """Resultado da classificação VVG de um dia útil.

    Campos:

    - ``vvg_positivo`` — ``True`` se e somente se AMBAS as condições de
      R1.2 são verdadeiras (volume e gap). ``False`` em warmup ou quando
      qualquer condição falha.
    - ``volume_morning`` — soma do volume das barras em ``[09:30, 10:00)``
      EST do dia.
    - ``volume_baseline`` — média do ``volume_morning`` dos
      ``n_dias_baseline`` dias úteis válidos anteriores (``shift(1)``:
      NÃO inclui o dia corrente). Em warmup, é a média parcial disponível
      (apenas informativa — não decide nada).
    - ``gap_pct`` — ``abs(open(09:30) - close(D-1)) / close(D-1)`` (fração).
    - ``razao_volume`` — ``volume_morning / volume_baseline`` (0.0 se o
      baseline não é positivo).
    - ``motivo`` — auditoria em pt-BR. Um de: ``"OK"``,
      ``"warmup-incompleto"``, ``"volume-baixo"``, ``"gap-baixo"``,
      ``"dia-invalido"``.
    """

    vvg_positivo: bool
    volume_morning: float
    volume_baseline: float
    gap_pct: float
    razao_volume: float
    motivo: str


# ---------------------------------------------------------------------------
# VvgClassifier — classificador stateful
# ---------------------------------------------------------------------------


class VvgClassifier:
    """Classificador VVG stateful por dia útil (R1).

    Consome barras OHLCV de minuto via :meth:`on_barra` (em ordem
    cronológica) e devolve um :class:`ResultadoClassificacao` exatamente
    na barra em que a janela morning ``[09:30, 10:00)`` EST de um dia
    válido fecha. Em todas as outras barras (e em dias inválidos) devolve
    ``None``.

    Estado mantido (todo determinístico):

    - ``_historico`` — ``deque`` (maxlen = ``n_dias_baseline``) com tuplas
      ``(date, volume_morning)`` dos últimos N dias úteis válidos. O
      baseline é a média da componente de volume. O dia corrente só entra
      aqui na sua finalização (transição de dia) — ``shift(1)`` semântico,
      anti look-ahead.
    - ``_close_d_menos_1`` — ``close`` de fim de RTH do último dia útil
      válido anterior. Usado no gap.
    - Acumuladores do dia corrente: ``volume_morning``, ``open`` da
      primeira barra morning, ``close`` corrente de RTH e contagem de
      barras.

    Regra de warmup (R1.4): enquanto o histórico tiver menos de
    ``n_dias_baseline`` dias OU ainda não houver ``close`` do dia anterior,
    a classificação devolve ``vvg_positivo = False`` com motivo
    ``"warmup-incompleto"`` (nunca emite sinal sob incerteza estatística).

    Filtro de dia válido (Spec 4 herdado): sábado/domingo são descartados
    (devolve ``None``); dias com menos de :data:`MIN_BARRAS_DIA_VALIDO`
    barras não entram no baseline nem viram ``close(D-1)``. O filtro de
    300 barras só pode ser avaliado no fechamento do dia (não no horário
    da classificação, às 10:00), pois conhecê-lo antes exigiria
    look-ahead. Na prática isso é inócuo: 300 barras equivalem aos 300
    minutos de 09:30 a 14:30 EST, então qualquer dia que de fato alcança o
    horário de entrada da estratégia (14:30 EST) já é válido.
    """

    NOME: str = "VvgClassifier"

    def __init__(self, parametros: Optional["ParametrosVvg"] = None) -> None:
        self._params = parametros if parametros is not None else ParametrosVvg()

        n_baseline = int(self._params.n_dias_baseline)
        if n_baseline < 1:
            raise ValueError(
                f"n_dias_baseline deve ser >= 1; recebido {n_baseline}"
            )

        # Histórico rolling: deque de (date, volume_morning). maxlen impõe
        # o descarte automático do dia mais antigo quando cheio.
        self._historico: "collections.deque[tuple[date, float]]" = (
            collections.deque(maxlen=n_baseline)
        )

        # close de fim de RTH do último dia útil válido (close(D-1)).
        self._close_d_menos_1: Optional[float] = None

        # Estado do dia corrente.
        self._dia_corrente: Optional[date] = None
        self._volume_morning_atual: float = 0.0
        self._open_dia_atual: Optional[float] = None
        self._close_rth_corrente: Optional[float] = None
        self._barras_dia_corrente: int = 0
        self._morning_classificada: bool = False

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def on_barra(self, barra: pd.Series) -> Optional[ResultadoClassificacao]:
        """Processa uma barra e devolve o resultado quando a morning fecha.

        Devolve um :class:`ResultadoClassificacao` apenas na primeira
        barra de um dia válido cuja hora (NY) é >= 10:00 EST. Em qualquer
        outra barra — e em dias de fim de semana — devolve ``None``.
        """
        ts_ny = self._para_ny(barra["timestamp"])
        dia = ts_ny.date()
        hora = ts_ny.time()
        open_barra = float(barra["open"])
        close_barra = float(barra["close"])
        volume_barra = float(barra["volume"])

        # 1. Detecção de transição de dia (NY).
        if self._dia_corrente is None:
            self._iniciar_dia(dia)
        elif dia != self._dia_corrente:
            # Finaliza o dia anterior (atualiza baseline e close(D-1))
            # ANTES de começar o novo dia — garante shift(1).
            self._finalizar_dia()
            self._iniciar_dia(dia)

        # 2. Acumulação do dia corrente.
        self._barras_dia_corrente += 1

        # 2a. close corrente de RTH (vira close(D-1) na finalização).
        if HORA_RTH_INICIO <= hora < HORA_RTH_FIM:
            self._close_rth_corrente = close_barra

        # 2b. janela morning [09:30, 10:00): acumula volume e captura open.
        if HORA_MORNING_INICIO <= hora < HORA_MORNING_FIM:
            if self._open_dia_atual is None:
                self._open_dia_atual = open_barra
            self._volume_morning_atual += volume_barra

        # 3. Detecção do fim da janela morning: primeira barra >= 10:00.
        if (not self._morning_classificada) and (hora >= HORA_MORNING_FIM):
            self._morning_classificada = True
            return self._classificar(dia)

        return None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _para_ny(ts) -> pd.Timestamp:
        """Converte um timestamp UTC para horário de Nova York (DST auto).

        Aceita ``pd.Timestamp`` (tz-aware, como vem do data_reader) ou um
        ``datetime``. Timestamps naive são assumidos como UTC. Usa
        :mod:`zoneinfo` (``America/New_York``) — sem offset hardcoded.
        """
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        # ``astimezone`` resolve EST/EDT conforme a data (horário de verão).
        return ts.astimezone(_TZ_NY)

    def _iniciar_dia(self, dia: date) -> None:
        """Reseta os acumuladores para um novo dia (NY)."""
        self._dia_corrente = dia
        self._volume_morning_atual = 0.0
        self._open_dia_atual = None
        self._close_rth_corrente = None
        self._barras_dia_corrente = 0
        self._morning_classificada = False

    def _finalizar_dia(self) -> None:
        """Fecha o dia corrente: atualiza baseline e close(D-1) se válido.

        Aplica o filtro de dia válido (sábado/domingo e
        :data:`MIN_BARRAS_DIA_VALIDO`). Só um dia útil válido:

        - vira ``close(D-1)`` para o próximo dia (gap), e
        - entra no baseline rolling de ``volume_morning`` (somente se teve
          uma janela morning real, isto é, ``open`` capturado).

        ``shift(1)`` é garantido porque este método roda na transição de
        dia, ANTES de o novo dia ser classificado — o baseline de um dia
        nunca inclui o próprio dia.
        """
        if self._dia_corrente is None:
            return

        dia_util = self._dia_corrente.weekday() < 5
        tem_barras = self._barras_dia_corrente >= MIN_BARRAS_DIA_VALIDO
        if not (dia_util and tem_barras):
            return

        # close de fim de RTH vira close(D-1) do próximo dia válido.
        if self._close_rth_corrente is not None:
            self._close_d_menos_1 = self._close_rth_corrente

        # Entra no baseline somente se houve janela morning real (open
        # capturado em [09:30, 10:00)). Evita poluir o baseline com 0.0
        # de dias sem morning.
        if self._open_dia_atual is not None:
            self._historico.append(
                (self._dia_corrente, self._volume_morning_atual)
            )

    def _classificar(self, dia: date) -> Optional[ResultadoClassificacao]:
        """Classifica o dia corrente no fechamento da janela morning.

        Devolve ``None`` para sábado/domingo (R: dias inválidos não geram
        classificação). Para dias úteis, devolve um
        :class:`ResultadoClassificacao` aplicando warmup (R1.4) e a regra
        R1.2.
        """
        # Sábado/domingo: dia inválido -> sem classificação.
        if dia.weekday() >= 5:
            return None

        # Dia útil sem janela morning real (gap de dados sobre 09:30-10:00):
        # estruturalmente inválido para o VVG.
        if self._open_dia_atual is None:
            return ResultadoClassificacao(
                vvg_positivo=False,
                volume_morning=0.0,
                volume_baseline=self._media_baseline(),
                gap_pct=0.0,
                razao_volume=0.0,
                motivo="dia-invalido",
            )

        volume_morning = self._volume_morning_atual
        volume_baseline = self._media_baseline()

        # Warmup (R1.4): histórico incompleto OU sem close do dia anterior.
        warmup_incompleto = (
            len(self._historico) < int(self._params.n_dias_baseline)
            or self._close_d_menos_1 is None
        )
        if warmup_incompleto:
            gap_warmup = 0.0
            if self._close_d_menos_1 is not None and self._close_d_menos_1 != 0.0:
                gap_warmup = abs(self._open_dia_atual - self._close_d_menos_1) / abs(
                    self._close_d_menos_1
                )
            return ResultadoClassificacao(
                vvg_positivo=False,
                volume_morning=volume_morning,
                volume_baseline=volume_baseline,
                gap_pct=gap_warmup,
                razao_volume=0.0,
                motivo="warmup-incompleto",
            )

        # Gap (R1.1). close(D-1) garantidamente não-None aqui.
        close_anterior = self._close_d_menos_1
        if close_anterior == 0.0:
            # Defensivo: close zerado tornaria o gap indefinido.
            gap_pct = 0.0
        else:
            gap_pct = abs(self._open_dia_atual - close_anterior) / abs(close_anterior)

        razao_volume = 0.0
        if volume_baseline > 0.0:
            razao_volume = volume_morning / volume_baseline

        # R1.2: vvg_positivo = (volume) AND (gap).
        cond_volume = (
            volume_morning >= self._params.multiplicador_volume * volume_baseline
        )
        cond_gap = gap_pct >= self._params.threshold_gap_pct

        if cond_volume and cond_gap:
            vvg_positivo = True
            motivo = "OK"
        elif not cond_volume:
            vvg_positivo = False
            motivo = "volume-baixo"
        else:
            # volume OK, mas gap insuficiente.
            vvg_positivo = False
            motivo = "gap-baixo"

        return ResultadoClassificacao(
            vvg_positivo=vvg_positivo,
            volume_morning=volume_morning,
            volume_baseline=volume_baseline,
            gap_pct=gap_pct,
            razao_volume=razao_volume,
            motivo=motivo,
        )

    def _media_baseline(self) -> float:
        """Média do ``volume_morning`` no histórico rolling (0.0 se vazio).

        Loop explícito (sem ``statistics.mean``) para portabilidade
        literal ao C#.
        """
        if len(self._historico) == 0:
            return 0.0
        soma = 0.0
        for _dia, volume in self._historico:
            soma += volume
        return soma / len(self._historico)

    # ------------------------------------------------------------------
    # Acessores (testes / debug)
    # ------------------------------------------------------------------

    @property
    def dias_no_baseline(self) -> int:
        """Quantidade de dias úteis válidos atualmente no baseline."""
        return len(self._historico)

    @property
    def close_dia_anterior(self) -> Optional[float]:
        """``close`` de fim de RTH do último dia útil válido (close(D-1))."""
        return self._close_d_menos_1


__all__ = [
    "MIN_BARRAS_DIA_VALIDO",
    "MULTIPLICADOR_VOLUME_PADRAO",
    "THRESHOLD_GAP_PCT_PADRAO",
    "N_DIAS_BASELINE_PADRAO",
    "ParametrosVvg",
    "ResultadoClassificacao",
    "VvgClassifier",
]
