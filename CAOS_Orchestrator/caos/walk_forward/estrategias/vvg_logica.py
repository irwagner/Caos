"""Lógica pura da estratégia VVG Late-Session Reversal (Spec — Tarefa 2).

Função de decisão canônica da reversão de fim de sessão para o MNQ em
dias VVG-positivos. Cobre R2 (`requirements.md`) e os parâmetros
congelados de R10.

Decisão arquitetural-chave (mesmo padrão de ``orb_logica.py``):
:func:`decidir_acao` é uma **função pura** — sem I/O, sem random, sem
consultar o relógio real. Recebe uma :class:`Barra` OHLCV + :class:`EstadoVvg`
+ :class:`ParametrosVvg` e devolve uma das 4 ações canônicas
(``LONG``, ``SHORT``, ``FECHAR``, ``NADA``) junto de um **novo** estado.

Este módulo é a **fonte da verdade** da regra de decisão da estratégia. A
porta C# (``EstrategiaVvgLateSessionLogica.cs``, Tarefa 6) reproduz a
lógica aqui, e a Property 11 valida a paridade Python↔C#.

Separação de camadas (design "decidir_acao" + nota da Tarefa 2):
a função pura **NÃO calcula VVG**. O flag ``vvg_positivo`` é fornecido
EXTERNAMENTE — setado pelo plugin (via ``VvgClassifier``, Tarefa 3) antes
de chamar :func:`decidir_acao`. Aqui apenas o **consumimos**. O cálculo
de drift direcional, o reset de estado diário e as regras de decisão são
responsabilidade desta função.

Abordagem de fuso horário (escolhida e documentada — Tarefa 2)
--------------------------------------------------------------
A :class:`Barra` chega com ``timestamp`` em **UTC** (convenção do
``manifesto.json`` do CAOS). As horas de sessão em :class:`ParametrosVvg`
são armazenadas em **horário de Nova York** (sufixo ``_est``). A
conversão UTC→NY é feita **dentro** de :func:`decidir_acao` via
``zoneinfo.ZoneInfo("America/New_York")``.

Por que esta abordagem (Opção B do enunciado):

- É **determinística**: a conversão é função pura do ``timestamp`` da
  barra, não do relógio real. Mesma barra ⇒ mesmo horário NY ⇒ mesma
  decisão.
- É **robusta a DST**: a transição EST↔EDT (horário de verão americano)
  é tratada pela ``zoneinfo``, sem offset hardcoded. Janelas que cruzam
  março/novembro funcionam sem código especial.
- É **testável** sem acoplar a função a um adaptador de fuso externo: o
  teste constrói barras com ``timestamp`` UTC e verifica a ação.

A porta C# (Tarefa 6) faz a conversão equivalente com
``TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time")``, que no
Windows também trata DST automaticamente.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Literal, Optional
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Fuso horário de Nova York (RTH do MNQ). Único ponto de conversão UTC→NY.
# ---------------------------------------------------------------------------

#: Fuso de Nova York usado para mapear ``timestamp`` UTC → horário do RTH.
#: ``zoneinfo`` trata DST (EST/EDT) automaticamente.
FUSO_NOVA_YORK = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

#: Direção da posição corrente rastreada em :class:`EstadoVvg`.
DirecaoVvg = Literal["LONG", "SHORT"]


class AcaoVvg(str, Enum):
    """Ações canônicas devolvidas por :func:`decidir_acao`.

    Herda de ``str`` para serialização trivial e comparação com strings
    (mesmo padrão do design e da porta C# ``enum AcaoVvg``).
    """

    LONG = "LONG"
    SHORT = "SHORT"
    FECHAR = "FECHAR"
    NADA = "NADA"


@dataclass(frozen=True)
class Barra:
    """Barra OHLCV minimalista para a função de decisão.

    Campos:

    - ``timestamp`` — UTC tz-aware. Naive ou offset ≠ 0 levanta
      ``ValueError`` em :func:`decidir_acao`.
    - ``open`` / ``high`` / ``low`` / ``close`` / ``volume`` — floats
      finitos. NaN/inf levantam ``ValueError`` em :func:`decidir_acao`.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ParametrosVvg:
    """Parâmetros congelados em código (R10 — regra anti-overfit).

    Os valores default são os **CONGELADOS** pela calibração da Tarefa 1,
    documentada em
    ``CAOS_Zettelkasten/Walk_Forwards/Calibracao_VVG_2026-05-29.md``.
    Não há otimização: alterar qualquer um destes 5 valores
    (``multiplicador_volume``, ``threshold_gap_pct``, ``n_dias_baseline``,
    ``stop_pontos``, ``target_pontos``) exige Decisão formal
    (``aprovado_walk_forward=true``), nunca recalibração silenciosa.

    Horas de sessão em **horário de Nova York** (sufixo ``_est``). A
    conversão UTC→NY é feita por :func:`decidir_acao` (ver docstring do
    módulo, "Abordagem de fuso horário").
    """

    # --- Classificador VVG (consumidos pela Tarefa 3; aqui só validados) ---
    multiplicador_volume: float = 1.5      # calibração 2026-05-29 (sweep 16.7%)
    threshold_gap_pct: float = 0.0015      # calibração 2026-05-29 (sweep 16.7%)
    n_dias_baseline: int = 10              # prescrito (design.md / R1.1)

    # --- Stop / Target congelados (ATR(14) 24h mediano × 1.0 e × 2.0) ---
    stop_pontos: float = 472.25            # 472.18 × 1.0, arred. tick MNQ (0.25)
    target_pontos: float = 944.25          # 472.18 × 2.0, arred. tick MNQ (0.25)

    # --- Janela morning (baseline E volume na MESMA janela de 30 min) ---
    # Decisão da Tarefa 1: baseline e volume_morning usam [09:30, 10:00) NY.
    janela_morning_inicio_est: time = time(9, 30)
    janela_morning_fim_est: time = time(10, 0)

    # --- Horários da estratégia (NY) ---
    hora_entrada_est: time = time(14, 30)       # mede drift e entra
    hora_encerramento_est: time = time(15, 50)  # force-close (EOD Topstep)

    # --- Sessão RTH (NY) ---
    sessao_inicio_est: time = time(9, 30)
    sessao_fim_est: time = time(16, 0)

    def __post_init__(self) -> None:
        # Ranges dos parâmetros congelados (R10).
        if not (self.multiplicador_volume > 1.0):
            raise ValueError(
                "multiplicador_volume deve ser > 1.0; "
                f"recebido {self.multiplicador_volume}"
            )
        if not (self.threshold_gap_pct > 0.0):
            raise ValueError(
                "threshold_gap_pct deve ser > 0; "
                f"recebido {self.threshold_gap_pct}"
            )
        if not (self.n_dias_baseline >= 2):
            raise ValueError(
                "n_dias_baseline deve ser >= 2; "
                f"recebido {self.n_dias_baseline}"
            )
        if not (self.stop_pontos > 0.0):
            raise ValueError(
                f"stop_pontos deve ser > 0; recebido {self.stop_pontos}"
            )
        if not (self.target_pontos > self.stop_pontos):
            raise ValueError(
                "target_pontos deve ser > stop_pontos; recebido "
                f"target={self.target_pontos}, stop={self.stop_pontos}"
            )

        # Coerência cronológica das janelas (NY).
        if not (self.janela_morning_inicio_est < self.janela_morning_fim_est):
            raise ValueError(
                "janela_morning_inicio_est deve ser anterior a "
                f"janela_morning_fim_est; recebido "
                f"[{self.janela_morning_inicio_est}, {self.janela_morning_fim_est})"
            )
        if not (self.sessao_inicio_est < self.sessao_fim_est):
            raise ValueError(
                f"sessao_inicio_est ({self.sessao_inicio_est}) deve ser "
                f"anterior a sessao_fim_est ({self.sessao_fim_est})"
            )
        if not (
            self.sessao_inicio_est
            <= self.hora_entrada_est
            < self.hora_encerramento_est
            <= self.sessao_fim_est
        ):
            raise ValueError(
                "horários devem satisfazer sessao_inicio <= hora_entrada < "
                "hora_encerramento <= sessao_fim; recebido "
                f"inicio={self.sessao_inicio_est}, entrada={self.hora_entrada_est}, "
                f"encerramento={self.hora_encerramento_est}, fim={self.sessao_fim_est}"
            )

    @classmethod
    def PadraoConfigurado(cls) -> "ParametrosVvg":
        """Devolve a instância com os valores CONGELADOS da calibração.

        Espelha ``ParametrosVvg.PadraoConfigurado()`` da porta C#. Os
        valores são passados explicitamente (em vez de ``cls()``) para que
        a origem de cada constante fique auditável neste único ponto.

        Origem: ``Calibracao_VVG_2026-05-29.md`` (Tarefa 1).
        """
        return cls(
            multiplicador_volume=1.5,
            threshold_gap_pct=0.0015,
            n_dias_baseline=10,
            stop_pontos=472.25,
            target_pontos=944.25,
            janela_morning_inicio_est=time(9, 30),
            janela_morning_fim_est=time(10, 0),
            hora_entrada_est=time(14, 30),
            hora_encerramento_est=time(15, 50),
            sessao_inicio_est=time(9, 30),
            sessao_fim_est=time(16, 0),
        )


@dataclass
class EstadoVvg:
    """Estado mutável da estratégia ao longo da sessão.

    :func:`decidir_acao` **não muta** a instância recebida: ela devolve um
    **novo** ``EstadoVvg`` (cópia atualizada). Isso garante idempotência —
    chamar :func:`decidir_acao` duas vezes com o mesmo ``(barra, estado)``
    congelado produz a mesma ação e o mesmo estado de saída.

    A replicação fiel em C# usa campos privados de
    ``StrategyVvgLateSessionReversal`` (struct ``EstadoVvg`` passada por
    ``ref``).
    """

    # --- Estado de classificação (diário) ---
    #: Data NY do dia corrente; muda dispara o reset diário.
    dia_corrente: Optional[date] = None
    #: Open do RTH (~09:30 NY) do dia corrente; base do drift.
    open_dia_atual: Optional[float] = None
    #: Close registrado na ``hora_entrada_est`` (close de referência do drift).
    drift_close_referencia: Optional[float] = None
    #: Flag VVG do dia — setado EXTERNAMENTE pelo classificador (Tarefa 3).
    vvg_positivo: bool = False

    # --- Estado da posição ---
    posicao_aberta: bool = False
    direcao_atual: Optional[DirecaoVvg] = None
    preco_entrada: Optional[float] = None
    sinal_atual: Optional[str] = None
    #: Garante no máximo 1 trade por dia (R2.6): True após fechar no dia.
    trade_fechado_hoje: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validar_barra(barra: Barra) -> None:
    """Valida que a barra é estruturalmente sã (UTC tz-aware, OHLCV finitos)."""
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


def _copiar_estado(estado: EstadoVvg) -> EstadoVvg:
    """Cópia rasa do estado (todos os campos são imutáveis: scalars/date/str).

    Usar uma cópia preserva a idempotência de :func:`decidir_acao`: a
    instância recebida nunca é mutada.
    """
    return dataclasses.replace(estado)


def _sinal_de(direcao: DirecaoVvg) -> str:
    """Mapeia direção → tag de sinal canônica (mesma do espelho C#)."""
    return "vvg-rev-long" if direcao == "LONG" else "vvg-rev-short"


# ---------------------------------------------------------------------------
# decidir_acao — função pura canônica
# ---------------------------------------------------------------------------


def decidir_acao(
    barra: Barra,
    estado: EstadoVvg,
    parametros: ParametrosVvg,
) -> tuple[AcaoVvg, EstadoVvg]:
    """Decide a ação VVG para ``barra`` dado ``estado`` e ``parametros``.

    Função **pura**: sem I/O, sem random, sem relógio real. Não muta o
    ``estado`` recebido — devolve uma tupla ``(acao, novo_estado)`` com uma
    cópia atualizada. Idempotente: mesmas entradas ⇒ mesma saída.

    Fluxo (precedência):

    1. Valida a barra e converte ``timestamp`` UTC → horário de Nova York.
    2. Reset de estado diário quando muda a data NY (``trade_fechado_hoje``,
       ``open_dia_atual``, ``drift_close_referencia``, ``vvg_positivo``).
    3. Captura o ``open_dia_atual`` (open do RTH ~09:30 NY) — primeira barra
       do dia já dentro de ``[sessao_inicio_est, sessao_fim_est)``.
    4. Se há posição aberta:
       a. ``hora >= hora_encerramento_est`` → ``FECHAR`` (R2.5, EOD Topstep).
       b. senão → ``NADA`` (stop/target são do motor de execução).
    5. Sem posição, exatamente em ``hora_entrada_est``, com ``vvg_positivo``
       e sem trade fechado hoje → calcula o drift e entra OPOSTO a ele
       (R2.1/R2.2): ``drift > 0`` ⇒ ``SHORT``; ``drift <= 0`` ⇒ ``LONG``.
    6. Caso contrário → ``NADA``.

    O flag ``vvg_positivo`` é **consumido**, não calculado (ver módulo).

    Stops/targets NÃO são devolvidos aqui: o adaptador os deriva de
    ``parametros.stop_pontos`` / ``parametros.target_pontos`` sobre o
    ``preco_entrada`` no momento do despacho (igual à porta C#).
    """
    _validar_barra(barra)
    novo = _copiar_estado(estado)

    ts_ny = barra.timestamp.astimezone(FUSO_NOVA_YORK)
    dia = ts_ny.date()
    hora = ts_ny.time()

    # Passo 2: reset de estado diário ao mudar a data NY.
    if novo.dia_corrente != dia:
        novo.dia_corrente = dia
        novo.open_dia_atual = None
        novo.drift_close_referencia = None
        novo.trade_fechado_hoje = False
        # vvg_positivo é setado externamente pelo classificador. No início
        # de um novo dia, antes do fechamento da janela morning, ainda não
        # há informação: zeramos para nunca operar sob valor obsoleto de
        # D-1 (coerente com R1.4 — sem sinal sob incerteza). O classificador
        # reescreve o valor correto às 10:00 NY, antes da entrada (14:30 NY).
        novo.vvg_positivo = False
        # Defensivo: posição não deveria cruzar a fronteira do dia (force-close
        # às 15:50 NY). Se cruzar, o motor de execução já a terá encerrado;
        # o estado de posição é mantido como veio para não mascarar bugs.

    # Passo 3: captura do open de referência do RTH (~09:30 NY).
    # Robusto a barras de Globex (pré-mercado): só capturamos quando a barra
    # já está dentro da sessão RTH.
    if (
        novo.open_dia_atual is None
        and parametros.sessao_inicio_est <= hora < parametros.sessao_fim_est
    ):
        novo.open_dia_atual = barra.open

    # Passo 4: posição aberta → só decidimos o force-close de fim de sessão.
    if novo.posicao_aberta:
        if hora >= parametros.hora_encerramento_est:
            novo.posicao_aberta = False
            novo.direcao_atual = None
            novo.preco_entrada = None
            novo.sinal_atual = None
            novo.trade_fechado_hoje = True
            return AcaoVvg.FECHAR, novo
        return AcaoVvg.NADA, novo

    # Passo 5: avaliação de entrada — somente na barra exata de hora_entrada.
    if (
        hora == parametros.hora_entrada_est
        and novo.vvg_positivo
        and not novo.trade_fechado_hoje
        and novo.open_dia_atual is not None
    ):
        # Drift = close(hora_entrada) - open(09:30). Entrada OPOSTA ao drift.
        novo.drift_close_referencia = barra.close
        drift = novo.drift_close_referencia - novo.open_dia_atual
        direcao: DirecaoVvg = "SHORT" if drift > 0 else "LONG"

        novo.posicao_aberta = True
        novo.direcao_atual = direcao
        novo.preco_entrada = barra.close
        novo.sinal_atual = _sinal_de(direcao)
        return (AcaoVvg.SHORT if direcao == "SHORT" else AcaoVvg.LONG), novo

    # Passo 6: nada a fazer.
    return AcaoVvg.NADA, novo


# ---------------------------------------------------------------------------
# Helper para o caller registrar saídas por stop/alvo (fora da função pura)
# ---------------------------------------------------------------------------


def registrar_saida_externa(estado: EstadoVvg) -> EstadoVvg:
    """Registra fechamento por stop/target detectado pelo motor de execução.

    :func:`decidir_acao` só emite ``FECHAR`` no fim de sessão; quando o
    stop ou o target é atingido intrabar, quem observa o fill é o motor de
    execução (plugin Python / NT8). Este helper devolve um novo estado com
    a posição encerrada e ``trade_fechado_hoje=True`` (R2.6 — 1 trade/dia),
    mantendo a coerência sem violar a pureza de :func:`decidir_acao`.
    """
    novo = _copiar_estado(estado)
    novo.posicao_aberta = False
    novo.direcao_atual = None
    novo.preco_entrada = None
    novo.sinal_atual = None
    novo.trade_fechado_hoje = True
    return novo


__all__ = [
    "FUSO_NOVA_YORK",
    "AcaoVvg",
    "Barra",
    "DirecaoVvg",
    "EstadoVvg",
    "ParametrosVvg",
    "decidir_acao",
    "registrar_saida_externa",
]
