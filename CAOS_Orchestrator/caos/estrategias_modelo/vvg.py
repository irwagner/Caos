"""Porta de referência (ground truth) da estratégia VVG Late-Session Reversal.

Spec — VVG Late-Session Reversal (MNQ), Tarefa 5.

Este módulo é o **espelho Python da lógica que será portada para C#**
(Tarefas 6 e 7: ``EstrategiaVvgLateSessionLogica.cs`` +
``EstrategiaVvgClassifierLogica.cs`` + ``StrategyVvgLateSessionReversal.cs``).
Existe exclusivamente para validar a paridade Python↔C# via Property 11
(``test_vvg_paridade_py_cs.py``, Tarefa 9). É o análogo do
``caos.estrategias_modelo.orb`` do Spec 4.

Disciplina de reimplementação independente (CRÍTICO)
----------------------------------------------------
Diferente de ``orb.py`` — que nesta fase apenas DELEGA para a função
canônica — esta porta **REIMPLEMENTA toda a lógica de forma
independente**: classificador VVG (volume morning, baseline rolling,
gap, warmup, filtro de dia válido), função de decisão (drift, entrada
oposta, encerramento forçado, 1 trade/dia) e o motor de execução
(stop/target intrabar, force-close, MFE/MAE). NÃO importa nem chama
``vvg_classifier`` / ``vvg_logica`` / ``vvg_late_session_reversal``.

A razão é metodológica: se a porta apenas chamasse os módulos de
produção, a Property 11 (que compara ``EstrategiaVvgLateSessionReversal``
com esta porta) seria **tautológica** — testaria código contra ele
mesmo. A reimplementação paralela é o que dá valor ao teste: ela é o
"ground truth" escrito de forma a antecipar EXATAMENTE como o C# será
escrito (loops e condicionais explícitos, estado mutável estilo
``struct ref``, nenhuma dependência de pandas/numpy).

Quando o código C# for escrito (Tarefas 6/7), ele deve ser uma tradução
literal **deste** módulo. E quando a porta de produção (Tarefa 4) e esta
porta concordarem trade-a-trade sob N=200 sequências Hypothesis, temos
evidência de que as três implementações (produção Python, porta de
referência Python, C#) são equivalentes.

Pureza e fuso horário
---------------------
- Sem pandas, sem numpy: barras chegam como :class:`BarraVvgModelo`
  (dataclass simples) ou tuplas ``(timestamp, open, high, low, close,
  volume)``.
- A conversão UTC→Nova York usa :mod:`zoneinfo`
  (``America/New_York``) — o C# fará o equivalente com
  ``TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time")``.
  Em ambos os lados o DST (horário de verão) é resolvido pela
  biblioteca, sem offset hardcoded.

Valores congelados (Tarefa 1 — ``Calibracao_VVG_2026-05-29.md``)
----------------------------------------------------------------
Declarados localmente em :class:`ParametrosVvgModelo` (não importados):
``multiplicador_volume=1.5``, ``threshold_gap_pct=0.0015``,
``n_dias_baseline=10``, ``stop_pontos=472.25``, ``target_pontos=944.25``.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import List, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Fuso de Nova York — único ponto de conversão UTC→NY (DST automático).
# ---------------------------------------------------------------------------

#: Fuso do RTH do MNQ. ``zoneinfo`` resolve EST/EDT conforme a data.
_FUSO_NOVA_YORK = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Constantes de janela (espelham vvg_classifier.py / vvg_logica.py)
# ---------------------------------------------------------------------------

#: Janela morning ``[09:30, 10:00)`` NY: mede volume_morning e captura o
#: open de referência do gap.
_HORA_MORNING_INICIO: time = time(9, 30)
_HORA_MORNING_FIM: time = time(10, 0)

#: Sessão RTH ``[09:30, 16:00)`` NY. Usada para capturar o close de fim
#: de RTH (que vira ``close(D-1)`` do gap) e o open de referência do drift.
_HORA_RTH_INICIO: time = time(9, 30)
_HORA_RTH_FIM: time = time(16, 0)

#: Horário em que se mede o drift e se entra (14:30 NY).
_HORA_ENTRADA: time = time(14, 30)

#: Horário do encerramento forçado pré-EOD Topstep (15:50 NY).
_HORA_ENCERRAMENTO: time = time(15, 50)

#: Mínimo de barras de minuto para um dia ser "válido" (herdado do Spec 4).
#: 300 barras ~= os 300 minutos de 09:30 a 14:30 NY; qualquer dia que
#: alcança o horário de entrada já é válido.
_MIN_BARRAS_DIA_VALIDO: int = 300


# ---------------------------------------------------------------------------
# Parâmetros congelados (declarados localmente — porta independente)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParametrosVvgModelo:
    """Parâmetros congelados da porta de referência (R10 — anti-overfit).

    Valores **idênticos** aos da produção
    (``ParametrosVvg.PadraoConfigurado()``), mas declarados aqui de forma
    independente para que a porta seja um ground truth paralelo (não
    importa nada de ``vvg_logica``). A porta C# (Tarefa 6) terá um
    ``struct ParametrosVvg`` equivalente.
    """

    # --- Classificador VVG ---
    multiplicador_volume: float = 1.5
    threshold_gap_pct: float = 0.0015
    n_dias_baseline: int = 10

    # --- Stop / target congelados (ATR(14) 24h mediano × 1.0 e × 2.0) ---
    stop_pontos: float = 472.25
    target_pontos: float = 944.25

    # --- Janelas (NY) ---
    janela_morning_inicio_est: time = _HORA_MORNING_INICIO
    janela_morning_fim_est: time = _HORA_MORNING_FIM
    hora_entrada_est: time = _HORA_ENTRADA
    hora_encerramento_est: time = _HORA_ENCERRAMENTO
    sessao_inicio_est: time = _HORA_RTH_INICIO
    sessao_fim_est: time = _HORA_RTH_FIM

    # --- Filtro de dia válido ---
    min_barras_dia_valido: int = _MIN_BARRAS_DIA_VALIDO


# ---------------------------------------------------------------------------
# Barra OHLCV minimalista (sem pandas)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BarraVvgModelo:
    """Barra OHLCV simples consumida pela porta (substitui ``pd.Series``).

    Campos:

    - ``timestamp`` — ``datetime``. Naive é assumido como UTC (mesma
      convenção de ``_barra_de_series`` / ``_para_ny`` da produção).
      Offset diferente de UTC levanta ``ValueError`` na decisão.
    - ``open`` / ``high`` / ``low`` / ``close`` / ``volume`` — floats
      finitos. NaN/inf levantam ``ValueError`` na decisão.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


#: Aceita uma :class:`BarraVvgModelo` ou uma tupla posicional
#: ``(timestamp, open, high, low, close, volume)``.
BarraComoEntrada = Union[
    BarraVvgModelo,
    Tuple[datetime, float, float, float, float, float],
]


def _coerir_barra(barra: BarraComoEntrada) -> BarraVvgModelo:
    """Normaliza a entrada para :class:`BarraVvgModelo`.

    Aceita a própria dataclass ou uma tupla posicional de 6 elementos.
    """
    if isinstance(barra, BarraVvgModelo):
        return barra
    if isinstance(barra, tuple) and len(barra) == 6:
        ts, o, h, l, c, v = barra
        return BarraVvgModelo(
            timestamp=ts,
            open=float(o),
            high=float(h),
            low=float(l),
            close=float(c),
            volume=float(v),
        )
    raise TypeError(
        "barra deve ser BarraVvgModelo ou tupla "
        "(timestamp, open, high, low, close, volume); "
        f"recebido {type(barra).__name__}"
    )


# ---------------------------------------------------------------------------
# Ações canônicas e trade emitido
# ---------------------------------------------------------------------------


class AcaoVvgModelo(str, Enum):
    """Ações canônicas (espelha ``vvg_logica.AcaoVvg``)."""

    LONG = "LONG"
    SHORT = "SHORT"
    FECHAR = "FECHAR"
    NADA = "NADA"


@dataclass
class TradeModelo:
    """Trade emitido pela porta de referência.

    Os nomes de campo espelham os 8 campos do
    :class:`caos.walk_forward.metricas.Trade` canônico para permitir
    comparação campo-a-campo na Property 11 (Tarefa 9). ``motivo_saida``
    é extra (diagnóstico) — não existe no Trade canônico.
    """

    entrada_timestamp: datetime
    saida_timestamp: datetime
    entrada_preco: float
    saida_preco: float
    lado: str            # "long" | "short"
    contratos: int       # sempre 1 (R4.1)
    mfe_pontos: float
    mae_pontos: float
    motivo_saida: str     # "stop" | "target" | "encerramento-forcado" | "fim-de-dados"

    def pnl_pontos(self) -> float:
        """PnL bruto em pontos × contratos (mesma fórmula do Trade canônico)."""
        delta = self.saida_preco - self.entrada_preco
        if self.lado == "short":
            delta = -delta
        return delta * self.contratos


@dataclass
class ResultadoClassificacaoModelo:
    """Resultado da classificação VVG de um dia (espelha ``ResultadoClassificacao``)."""

    vvg_positivo: bool
    volume_morning: float
    volume_baseline: float
    gap_pct: float
    razao_volume: float
    motivo: str


# ---------------------------------------------------------------------------
# Helpers de fuso / validação
# ---------------------------------------------------------------------------


def _para_ny(ts: datetime) -> datetime:
    """Converte um timestamp para horário de Nova York (DST automático).

    Lenient: timestamps naive são assumidos como UTC (mesma convenção do
    classificador de produção ``_para_ny``).
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(_FUSO_NOVA_YORK)


def _coerir_utc(ts: datetime) -> datetime:
    """Coerção timestamp→UTC (espelha ``_barra_de_series`` da produção).

    Naive é assumido UTC; tz-aware é convertido para UTC via
    ``astimezone``. Assim a barra que chega à decisão tem sempre offset 0.
    """
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _validar_barra_decisao(barra: BarraVvgModelo) -> None:
    """Validação estrita da barra na decisão (espelha ``vvg_logica._validar_barra``).

    Levanta ``ValueError`` para timestamp naive, offset diferente de UTC,
    ou campos OHLCV não-finitos. Aplicada sobre a barra JÁ coerida
    (naive já virou UTC), então só offsets explícitos não-UTC falham.
    """
    if barra.timestamp.tzinfo is None:
        raise ValueError("barra.timestamp deve ser tz-aware (UTC)")
    if barra.timestamp.utcoffset() != timedelta(0):
        raise ValueError(
            "barra.timestamp deve estar em UTC (offset 0); "
            f"recebido {barra.timestamp.isoformat()}"
        )
    for nome in ("open", "high", "low", "close", "volume"):
        v = getattr(barra, nome)
        if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            raise ValueError(f"barra.{nome} deve ser float finito; recebido {v!r}")


def _sinal_de(direcao: str) -> str:
    """Mapeia direção → tag de sinal canônica (espelho do C#)."""
    return "vvg-rev-long" if direcao == "LONG" else "vvg-rev-short"


# ---------------------------------------------------------------------------
# Classificador VVG (reimplementação independente — espelho de vvg_classifier)
# ---------------------------------------------------------------------------


class _ClassificadorVvgModelo:
    """Classificador VVG stateful, reimplementado de forma independente.

    Espelha ``caos.walk_forward.estrategias.vvg_classifier.VvgClassifier``
    com loops e condicionais explícitos (estilo C#). Mantém um baseline
    rolling do ``volume_morning`` dos últimos ``n_dias_baseline`` dias
    úteis válidos e o ``close`` de fim de RTH do dia anterior.
    """

    def __init__(self, parametros: ParametrosVvgModelo) -> None:
        self._p = parametros
        n = int(parametros.n_dias_baseline)
        if n < 1:
            raise ValueError(f"n_dias_baseline deve ser >= 1; recebido {n}")
        # Histórico rolling (date, volume_morning); maxlen descarta o mais antigo.
        self._historico: "collections.deque[Tuple[date, float]]" = collections.deque(
            maxlen=n
        )
        self._close_d_menos_1: Optional[float] = None
        self._dia_corrente: Optional[date] = None
        self._volume_morning_atual: float = 0.0
        self._open_dia_atual: Optional[float] = None
        self._close_rth_corrente: Optional[float] = None
        self._barras_dia_corrente: int = 0
        self._morning_classificada: bool = False

    def on_barra(self, barra: BarraVvgModelo) -> Optional[ResultadoClassificacaoModelo]:
        """Processa uma barra; devolve resultado quando a morning fecha."""
        ts_ny = _para_ny(barra.timestamp)
        dia = ts_ny.date()
        hora = ts_ny.time()
        open_barra = float(barra.open)
        close_barra = float(barra.close)
        volume_barra = float(barra.volume)

        # 1. Transição de dia (NY).
        if self._dia_corrente is None:
            self._iniciar_dia(dia)
        elif dia != self._dia_corrente:
            # Finaliza o dia anterior ANTES de iniciar o novo (shift(1)).
            self._finalizar_dia()
            self._iniciar_dia(dia)

        # 2. Acumulação do dia corrente.
        self._barras_dia_corrente += 1

        # 2a. close corrente de RTH (vira close(D-1) na finalização).
        if _HORA_RTH_INICIO <= hora < _HORA_RTH_FIM:
            self._close_rth_corrente = close_barra

        # 2b. janela morning [09:30, 10:00): acumula volume e captura open.
        if _HORA_MORNING_INICIO <= hora < _HORA_MORNING_FIM:
            if self._open_dia_atual is None:
                self._open_dia_atual = open_barra
            self._volume_morning_atual += volume_barra

        # 3. Primeira barra >= 10:00: classifica.
        if (not self._morning_classificada) and (hora >= _HORA_MORNING_FIM):
            self._morning_classificada = True
            return self._classificar(dia)

        return None

    # --- helpers internos ---

    def _iniciar_dia(self, dia: date) -> None:
        self._dia_corrente = dia
        self._volume_morning_atual = 0.0
        self._open_dia_atual = None
        self._close_rth_corrente = None
        self._barras_dia_corrente = 0
        self._morning_classificada = False

    def _finalizar_dia(self) -> None:
        if self._dia_corrente is None:
            return
        dia_util = self._dia_corrente.weekday() < 5
        tem_barras = self._barras_dia_corrente >= self._p.min_barras_dia_valido
        if not (dia_util and tem_barras):
            return
        if self._close_rth_corrente is not None:
            self._close_d_menos_1 = self._close_rth_corrente
        # Só entra no baseline se houve janela morning real (open capturado).
        if self._open_dia_atual is not None:
            self._historico.append((self._dia_corrente, self._volume_morning_atual))

    def _media_baseline(self) -> float:
        """Média do volume_morning no histórico (loop explícito — portável ao C#)."""
        if len(self._historico) == 0:
            return 0.0
        soma = 0.0
        for _dia, volume in self._historico:
            soma += volume
        return soma / len(self._historico)

    def _classificar(self, dia: date) -> Optional[ResultadoClassificacaoModelo]:
        # Sábado/domingo: dia inválido -> sem classificação.
        if dia.weekday() >= 5:
            return None

        # Dia útil sem janela morning real (gap de dados em 09:30-10:00).
        if self._open_dia_atual is None:
            return ResultadoClassificacaoModelo(
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
            len(self._historico) < int(self._p.n_dias_baseline)
            or self._close_d_menos_1 is None
        )
        if warmup_incompleto:
            gap_warmup = 0.0
            if self._close_d_menos_1 is not None and self._close_d_menos_1 != 0.0:
                gap_warmup = abs(
                    self._open_dia_atual - self._close_d_menos_1
                ) / abs(self._close_d_menos_1)
            return ResultadoClassificacaoModelo(
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
            gap_pct = 0.0
        else:
            gap_pct = abs(self._open_dia_atual - close_anterior) / abs(close_anterior)

        razao_volume = 0.0
        if volume_baseline > 0.0:
            razao_volume = volume_morning / volume_baseline

        # R1.2: vvg_positivo = (volume) AND (gap).
        cond_volume = volume_morning >= self._p.multiplicador_volume * volume_baseline
        cond_gap = gap_pct >= self._p.threshold_gap_pct

        if cond_volume and cond_gap:
            vvg_positivo = True
            motivo = "OK"
        elif not cond_volume:
            vvg_positivo = False
            motivo = "volume-baixo"
        else:
            vvg_positivo = False
            motivo = "gap-baixo"

        return ResultadoClassificacaoModelo(
            vvg_positivo=vvg_positivo,
            volume_morning=volume_morning,
            volume_baseline=volume_baseline,
            gap_pct=gap_pct,
            razao_volume=razao_volume,
            motivo=motivo,
        )


# ---------------------------------------------------------------------------
# Estado mutável da decisão (espelha EstadoVvg; aqui mutado in-place estilo C#)
# ---------------------------------------------------------------------------


@dataclass
class _EstadoVvgModelo:
    """Estado mutável da decisão (struct passada por ``ref`` no C#)."""

    # Classificação (diário).
    dia_corrente: Optional[date] = None
    open_dia_atual: Optional[float] = None
    drift_close_referencia: Optional[float] = None
    vvg_positivo: bool = False
    # Posição.
    posicao_aberta: bool = False
    direcao_atual: Optional[str] = None       # "LONG" | "SHORT"
    preco_entrada: Optional[float] = None
    sinal_atual: Optional[str] = None
    trade_fechado_hoje: bool = False


class _TradeAbertoModelo:
    """Trade em andamento (uso interno do motor de execução)."""

    __slots__ = (
        "direcao",
        "entrada_timestamp",
        "entrada_preco",
        "stop_preco",
        "target_preco",
        "mfe_pontos",
        "mae_pontos",
    )

    def __init__(
        self,
        direcao: str,
        entrada_timestamp: datetime,
        entrada_preco: float,
        stop_preco: float,
        target_preco: float,
    ) -> None:
        self.direcao = direcao
        self.entrada_timestamp = entrada_timestamp
        self.entrada_preco = entrada_preco
        self.stop_preco = stop_preco
        self.target_preco = target_preco
        # Excursões (convenção MetricasCalculator): mfe >= 0, mae <= 0.
        self.mfe_pontos = 0.0
        self.mae_pontos = 0.0


# ---------------------------------------------------------------------------
# Porta de referência principal
# ---------------------------------------------------------------------------


class VvgModeloCSharpPort:
    """Porta Python da estratégia VVG que será portada para C#.

    Combina, numa única classe, as três camadas que no C# ficarão em
    ``EstrategiaVvgClassifierLogica``, ``EstrategiaVvgLateSessionLogica``
    e o despacho de ``StrategyVvgLateSessionReversal``:

    1. **Classificador** (:class:`_ClassificadorVvgModelo`) — atualiza o
       baseline rolling de volume e o ``close(D-1)``; produz a flag
       ``vvg_positivo`` ao fechar a janela morning (~10:00 NY).
    2. **Decisão** (:meth:`_decidir_acao`) — drift direcional, entrada
       oposta às 14:30 NY, encerramento forçado às 15:50 NY, no máximo 1
       trade/dia.
    3. **Execução** (:meth:`_abrir_trade` / :meth:`_checar_stop_target` /
       :meth:`_fechar_trade`) — stop/target intrabar (stop prevalece em
       empate de barra), MFE/MAE, e o fallback de :meth:`finalizar`.

    O protocolo público espelha o do plugin de produção
    (``EstrategiaVvgLateSessionReversal``): :meth:`treinar`,
    :meth:`on_barra`, :meth:`finalizar` — além do atalho
    :meth:`processar`. Assim a Property 11 (Tarefa 9) pode dirigir os
    dois lados com as mesmas barras e exigir trades idênticos.
    """

    NOME: str = "VvgModeloCSharpPort"

    def __init__(self, parametros: Optional[ParametrosVvgModelo] = None) -> None:
        self._p: ParametrosVvgModelo = parametros or ParametrosVvgModelo()
        self._classificador = _ClassificadorVvgModelo(self._p)
        self._estado = _EstadoVvgModelo()
        self._trades: List[TradeModelo] = []
        self._trade_aberto: Optional[_TradeAbertoModelo] = None

    # ------------------------------------------------------------------
    # Protocolo público (espelha o plugin de produção)
    # ------------------------------------------------------------------

    def treinar(self, historico: Optional[Sequence[BarraComoEntrada]] = None) -> None:
        """Aquece o classificador com as barras de Treino (sem emitir trade).

        Re-instancia o classificador e zera o estado (idempotência entre
        janelas). Ao final, o baseline rolling e o ``close(D-1)`` refletem
        exatamente a janela de Treino.
        """
        self._classificador = _ClassificadorVvgModelo(self._p)
        self._estado = _EstadoVvgModelo()
        self._trades = []
        self._trade_aberto = None

        if not historico:
            return
        for barra in historico:
            self._classificador.on_barra(_coerir_barra(barra))

    def on_barra(self, barra: BarraComoEntrada) -> None:
        """Integra classificador + stop/target intrabar + decisão + despacho.

        Ordem das etapas (precedência cronológica dentro da barra), idêntica
        ao ``EstrategiaVvgLateSessionReversal.on_barra`` de produção:

        a. Classificador → atualiza ``vvg_positivo`` ao fechar a morning.
        b. Stop/target intrabar de posição aberta numa barra ANTERIOR
           (atualiza excursões e, se tocou, fecha o trade).
        c. Decisão pura (muta o estado in-place, estilo C#).
        d. Despacho da ação canônica.
        """
        b = _coerir_barra(barra)

        # (a) Classificador → vvg_positivo.
        resultado = self._classificador.on_barra(b)
        if resultado is not None:
            self._estado.vvg_positivo = resultado.vvg_positivo

        # Coerção timestamp→UTC para a decisão (espelha _barra_de_series).
        b_dec = BarraVvgModelo(
            timestamp=_coerir_utc(b.timestamp),
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )

        # (b) Stop/target intrabar de posição aberta numa barra ANTERIOR.
        #     (A barra de entrada não é checada: o fill ocorre no seu close.)
        if self._trade_aberto is not None:
            self._atualizar_excursoes(b_dec)
            if self._checar_stop_target(b_dec):
                # Posição encerrada por stop/alvo; sincroniza o estado.
                self._registrar_saida_externa()

        # (c) Decisão canônica (muta self._estado in-place, estilo C#).
        acao = self._decidir_acao(b_dec)

        # (d) Despacho.
        if acao == AcaoVvgModelo.LONG:
            self._abrir_trade(b_dec, "LONG")
        elif acao == AcaoVvgModelo.SHORT:
            self._abrir_trade(b_dec, "SHORT")
        elif acao == AcaoVvgModelo.FECHAR:
            self._fechar_trade(b_dec, b_dec.close, motivo="encerramento-forcado")

    def finalizar(self) -> List[TradeModelo]:
        """Fecha trade pendente (defensivo) e devolve a lista de trades.

        Em operação normal a posição é sempre encerrada intraday; se
        sobrar (dados terminaram no meio do trade), fecha pelo
        ``preco_entrada`` (PnL ~0) sem inventar excursão fictícia.
        """
        if self._trade_aberto is not None:
            ta = self._trade_aberto
            ts_aprox = ta.entrada_timestamp + timedelta(seconds=1)
            barra_fake = BarraVvgModelo(
                timestamp=ts_aprox,
                open=ta.entrada_preco,
                high=ta.entrada_preco,
                low=ta.entrada_preco,
                close=ta.entrada_preco,
                volume=0.0,
            )
            self._fechar_trade(barra_fake, ta.entrada_preco, motivo="fim-de-dados")
        return list(self._trades)

    def processar(
        self,
        barras_treino: Optional[Sequence[BarraComoEntrada]],
        barras_teste: Sequence[BarraComoEntrada],
    ) -> List[TradeModelo]:
        """Atalho: aquece (Treino), processa (Teste) e devolve os trades.

        Equivale a ``treinar(barras_treino)`` + ``on_barra`` para cada
        barra de Teste + ``finalizar()``. Conveniência para a Property 11.
        """
        self.treinar(barras_treino)
        for barra in barras_teste:
            self.on_barra(barra)
        return self.finalizar()

    # ------------------------------------------------------------------
    # Decisão (espelha vvg_logica.decidir_acao; imperativo estilo C#)
    # ------------------------------------------------------------------

    def _decidir_acao(self, barra: BarraVvgModelo) -> AcaoVvgModelo:
        """Decide a ação VVG mutando ``self._estado`` in-place.

        Espelha ``vvg_logica.decidir_acao``, mas — como o C# fará — muta o
        estado diretamente em vez de devolver uma cópia. A flag
        ``vvg_positivo`` é CONSUMIDA (setada externamente pelo
        classificador), nunca calculada aqui.
        """
        _validar_barra_decisao(barra)
        estado = self._estado

        ts_ny = _para_ny(barra.timestamp)
        dia = ts_ny.date()
        hora = ts_ny.time()

        # Reset de estado diário ao mudar a data NY.
        if estado.dia_corrente != dia:
            estado.dia_corrente = dia
            estado.open_dia_atual = None
            estado.drift_close_referencia = None
            estado.trade_fechado_hoje = False
            # Zera a flag: nunca operar sob valor obsoleto de D-1. O
            # classificador reescreve o valor correto às 10:00 NY.
            estado.vvg_positivo = False

        # Captura do open de referência do RTH (~09:30 NY).
        if (
            estado.open_dia_atual is None
            and self._p.sessao_inicio_est <= hora < self._p.sessao_fim_est
        ):
            estado.open_dia_atual = barra.open

        # Posição aberta: só decidimos o force-close de fim de sessão.
        if estado.posicao_aberta:
            if hora >= self._p.hora_encerramento_est:
                estado.posicao_aberta = False
                estado.direcao_atual = None
                estado.preco_entrada = None
                estado.sinal_atual = None
                estado.trade_fechado_hoje = True
                return AcaoVvgModelo.FECHAR
            return AcaoVvgModelo.NADA

        # Avaliação de entrada — somente na barra exata de hora_entrada.
        if (
            hora == self._p.hora_entrada_est
            and estado.vvg_positivo
            and not estado.trade_fechado_hoje
            and estado.open_dia_atual is not None
        ):
            # Drift = close(hora_entrada) - open(09:30). Entrada OPOSTA ao drift.
            estado.drift_close_referencia = barra.close
            drift = estado.drift_close_referencia - estado.open_dia_atual
            direcao = "SHORT" if drift > 0 else "LONG"

            estado.posicao_aberta = True
            estado.direcao_atual = direcao
            estado.preco_entrada = barra.close
            estado.sinal_atual = _sinal_de(direcao)
            return AcaoVvgModelo.SHORT if direcao == "SHORT" else AcaoVvgModelo.LONG

        return AcaoVvgModelo.NADA

    def _registrar_saida_externa(self) -> None:
        """Sincroniza o estado após saída por stop/target (espelha helper homônimo)."""
        estado = self._estado
        estado.posicao_aberta = False
        estado.direcao_atual = None
        estado.preco_entrada = None
        estado.sinal_atual = None
        estado.trade_fechado_hoje = True

    # ------------------------------------------------------------------
    # Execução (espelha vvg_late_session_reversal)
    # ------------------------------------------------------------------

    def _abrir_trade(self, barra: BarraVvgModelo, direcao: str) -> None:
        """Abre a posição no ``close`` da barra de entrada (14:30 NY).

        Deriva stop/target de ``stop_pontos`` / ``target_pontos`` sobre o
        preço de entrada (mesma convenção da porta C# e do plugin).

        Importante: NÃO atualizamos MFE/MAE com a barra de entrada. O fill
        ocorre no ``close`` e o motor de produção
        (``EstrategiaVvgLateSessionReversal``) só conta excursões a partir
        da barra SEGUINTE (etapa (b) do seu ``on_barra``) e na barra de
        fechamento. Capturar a excursão da própria barra de entrada aqui
        divergiria do MFE/MAE de produção.
        """
        preco = barra.close
        if direcao == "LONG":
            stop_preco = preco - self._p.stop_pontos
            target_preco = preco + self._p.target_pontos
        else:  # SHORT
            stop_preco = preco + self._p.stop_pontos
            target_preco = preco - self._p.target_pontos

        self._trade_aberto = _TradeAbertoModelo(
            direcao=direcao,
            entrada_timestamp=barra.timestamp,
            entrada_preco=preco,
            stop_preco=stop_preco,
            target_preco=target_preco,
        )

    def _atualizar_excursoes(self, barra: BarraVvgModelo) -> None:
        """Atualiza MFE/MAE da posição corrente com a excursão da barra."""
        ta = self._trade_aberto
        if ta is None:
            return
        if ta.direcao == "LONG":
            mfe_potencial = barra.high - ta.entrada_preco
            mae_potencial = barra.low - ta.entrada_preco
        else:  # SHORT
            mfe_potencial = ta.entrada_preco - barra.low
            mae_potencial = ta.entrada_preco - barra.high
        if mfe_potencial > ta.mfe_pontos:
            ta.mfe_pontos = mfe_potencial
        if mae_potencial < ta.mae_pontos:
            ta.mae_pontos = mae_potencial

    def _checar_stop_target(self, barra: BarraVvgModelo) -> bool:
        """Fecha por stop/target se a barra cruzou um deles. Devolve se fechou.

        Convenção conservadora: se ambos forem tocados na MESMA barra, o
        **stop** prevalece (pior caminho intrabar).
        """
        ta = self._trade_aberto
        if ta is None:
            return False

        if ta.direcao == "LONG":
            stop_atingido = barra.low <= ta.stop_preco
            target_atingido = barra.high >= ta.target_preco
        else:  # SHORT
            stop_atingido = barra.high >= ta.stop_preco
            target_atingido = barra.low <= ta.target_preco

        if stop_atingido:
            self._fechar_trade(barra, ta.stop_preco, motivo="stop")
            return True
        if target_atingido:
            self._fechar_trade(barra, ta.target_preco, motivo="target")
            return True
        return False

    def _fechar_trade(
        self, barra: BarraVvgModelo, saida_preco: float, *, motivo: str
    ) -> None:
        """Fecha o trade aberto e empilha um :class:`TradeModelo` bruto."""
        ta = self._trade_aberto
        if ta is None:
            return

        # Última atualização das excursões com a barra de fechamento
        # (mesma ordem do ``_fechar_posicao`` de produção).
        self._atualizar_excursoes(barra)

        lado = "long" if ta.direcao == "LONG" else "short"

        # Trade exige saida_timestamp estritamente > entrada_timestamp.
        saida_ts = barra.timestamp
        if saida_ts <= ta.entrada_timestamp:
            saida_ts = ta.entrada_timestamp + timedelta(seconds=1)

        self._trades.append(
            TradeModelo(
                entrada_timestamp=ta.entrada_timestamp,
                saida_timestamp=saida_ts,
                entrada_preco=ta.entrada_preco,
                saida_preco=saida_preco,
                lado=lado,
                contratos=1,  # R4.1: fixo permanente.
                mfe_pontos=ta.mfe_pontos,
                mae_pontos=ta.mae_pontos,
                motivo_saida=motivo,
            )
        )
        self._trade_aberto = None

    # ------------------------------------------------------------------
    # Acessores (testes / debug)
    # ------------------------------------------------------------------

    @property
    def parametros(self) -> ParametrosVvgModelo:
        return self._p

    @property
    def trades(self) -> Sequence[TradeModelo]:
        return tuple(self._trades)


__all__ = [
    "AcaoVvgModelo",
    "BarraVvgModelo",
    "ParametrosVvgModelo",
    "ResultadoClassificacaoModelo",
    "TradeModelo",
    "VvgModeloCSharpPort",
]
