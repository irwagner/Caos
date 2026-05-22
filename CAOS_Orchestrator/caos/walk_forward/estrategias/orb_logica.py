"""Lógica pura da estratégia ORB (Spec 4 — Task 1).

Função de decisão canônica da Opening Range Breakout para o MNQ.
Cobre R1, R2, R3, R4, R5 do ``requirements.md`` do Spec 4.

Decisão arquitetural-chave:
:func:`decidir_acao` é uma **função pura** (sem I/O, sem timer real, sem
random). Recebe uma barra OHLCV + estado interno + parâmetros e devolve
uma das 4 ações canônicas: ``LONG``, ``SHORT``, ``FECHAR``, ``NADA``.
Tanto :class:`~caos.walk_forward.estrategias.orb.EstrategiaORB` (Python,
plugado no Walk-Forward) quanto :class:`StrategyORB` (C#, no NT8) são
adaptadores finos que traduzem barras + estado de runtime para entrada
desta função.

Este módulo é a **fonte da verdade** da regra de decisão. A porta C#
(``EstrategiaORBLogica.cs``) reproduz byte-a-byte a lógica aqui, e a
Property 19 valida a paridade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

#: Ações possíveis devolvidas por :func:`decidir_acao`.
AcaoORB = Literal["LONG", "SHORT", "FECHAR", "NADA"]

#: Posição corrente rastreada por :class:`EstadoORB`.
PosicaoORB = Literal["LONG", "SHORT", "NADA"]


@dataclass(frozen=True)
class Barra:
    """Barra OHLCV minimalista para a função de decisão (R1).

    Campos:

    - ``timestamp`` — UTC tz-aware. Naive levanta ``ValueError`` em
      :func:`decidir_acao`.
    - ``open`` / ``high`` / ``low`` / ``close`` / ``volume`` — float
      finitos. NaN/inf levantam ``ValueError`` em :func:`decidir_acao`.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ParametrosORB:
    """Parâmetros configuráveis da estratégia (R5).

    Defaults vêm do design 3 do Spec 4. Validação em ``__post_init__``
    garante que valores fora dos ranges levantam ``ValueError``.
    """

    minutos_or: int = 30
    risco_multiplicador: float = 1.0
    alvo_multiplicador: float = 2.0
    cooldown_minutos: int = 15
    hora_corte_entradas_utc: time = time(19, 0)
    sessao_inicio_utc: time = time(13, 30)
    sessao_fim_utc: time = time(20, 0)
    range_minimo_pontos: float = 0.5

    def __post_init__(self) -> None:
        # R5 — ranges canônicos.
        if not (5 <= self.minutos_or <= 60):
            raise ValueError(
                f"minutos_or deve estar em [5, 60]; recebido {self.minutos_or}"
            )
        if not (0.5 <= self.risco_multiplicador <= 2.0):
            raise ValueError(
                "risco_multiplicador deve estar em [0.5, 2.0]; "
                f"recebido {self.risco_multiplicador}"
            )
        if not (0.5 <= self.alvo_multiplicador <= 5.0):
            raise ValueError(
                "alvo_multiplicador deve estar em [0.5, 5.0]; "
                f"recebido {self.alvo_multiplicador}"
            )
        if not (0 <= self.cooldown_minutos <= 120):
            raise ValueError(
                "cooldown_minutos deve estar em [0, 120]; "
                f"recebido {self.cooldown_minutos}"
            )
        if self.range_minimo_pontos <= 0:
            raise ValueError(
                "range_minimo_pontos deve ser > 0; "
                f"recebido {self.range_minimo_pontos}"
            )
        # Coerência cronológica das horas de sessão.
        if not (self.sessao_inicio_utc < self.sessao_fim_utc):
            raise ValueError(
                f"sessao_inicio_utc ({self.sessao_inicio_utc}) deve ser "
                f"anterior a sessao_fim_utc ({self.sessao_fim_utc})"
            )
        if not (
            self.sessao_inicio_utc
            <= self.hora_corte_entradas_utc
            <= self.sessao_fim_utc
        ):
            raise ValueError(
                "hora_corte_entradas_utc deve estar dentro da janela de sessão; "
                f"recebido {self.hora_corte_entradas_utc} fora de "
                f"[{self.sessao_inicio_utc}, {self.sessao_fim_utc}]"
            )


@dataclass
class EstadoORB:
    """Estado mutável da ORB ao longo da sessão.

    O caller mantém uma instância por estratégia/janela e a passa para
    cada chamada de :func:`decidir_acao` (que muta o estado in-place).
    """

    sessao_corrente: Optional[date] = None
    high_or: float = float("-inf")
    low_or: float = float("inf")
    or_formado: bool = False
    posicao: PosicaoORB = "NADA"
    cooldown_ate: Optional[datetime] = None
    entrou_nesta_sessao: bool = False


@dataclass(frozen=True)
class DecisaoORB:
    """Decisão devolvida por :func:`decidir_acao`.

    - ``acao`` — uma de :data:`AcaoORB`.
    - ``stop``/``alvo`` — preenchidos apenas quando ``acao`` é ``LONG`` ou ``SHORT``.
    - ``motivo`` — string curta em pt-BR para auditoria. Vazia para
      ``NADA`` ou ``FECHAR``-padrão.
    """

    acao: AcaoORB
    stop: Optional[float] = None
    alvo: Optional[float] = None
    motivo: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validar_barra(barra: Barra) -> None:
    """Valida que a barra é estruturalmente sã (UTC, OHLCV finitos)."""
    if barra.timestamp.tzinfo is None:
        raise ValueError("barra.timestamp deve ser tz-aware (UTC)")
    if barra.timestamp.utcoffset() != timedelta(0):
        raise ValueError(
            f"barra.timestamp deve estar em UTC (offset 0); "
            f"recebido {barra.timestamp.isoformat()}"
        )
    for nome in ("open", "high", "low", "close", "volume"):
        v = getattr(barra, nome)
        if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            raise ValueError(f"barra.{nome} deve ser float finito; recebido {v!r}")


def _esta_dentro_da_sessao(
    barra: Barra,
    parametros: ParametrosORB,
) -> bool:
    """Verifica se ``barra.timestamp`` cai dentro da Janela_Sessao_RTH."""
    hora = barra.timestamp.time()
    return parametros.sessao_inicio_utc <= hora < parametros.sessao_fim_utc


def _esta_no_periodo_or(
    barra: Barra,
    parametros: ParametrosORB,
) -> bool:
    """Verifica se a barra está no janela de formação do OR (R1)."""
    hora = barra.timestamp.time()
    if hora < parametros.sessao_inicio_utc:
        return False
    inicio = datetime.combine(
        barra.timestamp.date(),
        parametros.sessao_inicio_utc,
        tzinfo=timezone.utc,
    )
    fim_or = inicio + timedelta(minutes=parametros.minutos_or)
    return barra.timestamp < fim_or


def _resetar_se_nova_sessao(
    estado: EstadoORB,
    barra: Barra,
) -> None:
    """Reset de R1.3 quando muda o ``date()`` UTC entre barras."""
    sessao_da_barra = barra.timestamp.date()
    if estado.sessao_corrente != sessao_da_barra:
        estado.sessao_corrente = sessao_da_barra
        estado.high_or = float("-inf")
        estado.low_or = float("inf")
        estado.or_formado = False
        estado.entrou_nesta_sessao = False
        # Cooldown não cruza fronteira de sessão (defensivo): ao virar o
        # dia, qualquer cooldown pendente deixa de bloquear novas entradas.
        estado.cooldown_ate = None


# ---------------------------------------------------------------------------
# decidir_acao — função pura canônica
# ---------------------------------------------------------------------------


def decidir_acao(
    barra: Barra,
    estado: EstadoORB,
    parametros: ParametrosORB,
) -> DecisaoORB:
    """Decide a ação ORB para ``barra`` dado ``estado`` e ``parametros``.

    Implementa R1 (formação do OR), R2 (sinais de entrada), R3 (stop e
    alvo), R4 (cooldown e fim de sessão) com a precedência abaixo:

    1. Reset de sessão se mudou o ``date()``.
    2. Se a barra está fora da Janela_Sessao_RTH → ``NADA``.
    3. Se há posição aberta e a barra está em ``sessao_fim - 1min``
       (último minuto da sessão) → ``FECHAR``.
    4. Se a barra está no Periodo_OR → atualiza ``high_or``/``low_or`` e
       devolve ``NADA``. Marca ``or_formado=True`` quando ultrapassa o
       fim do Periodo_OR (próxima barra fora dele).
    5. Se há posição aberta → ``NADA`` (saída discricionária via
       trailing/take fica fora da ORB; só intervimos no fim de sessão).
6. Se cooldown ativo → ``NADA``.
    7. Se ``entrou_nesta_sessao`` → ``NADA`` (R2.3).
    8. Se hora de corte ultrapassada → ``NADA``.
    9. Range degenerado (R3.3) → ``NADA``.
    10. Rompimento LONG (R2.1) → ``LONG`` com stop/alvo (R3.1).
    11. Rompimento SHORT (R2.2) → ``SHORT`` com stop/alvo (R3.2).

    A função NÃO altera ``posicao`` nem ``cooldown_ate``: cabe ao
    caller, que despacha a ordem de fato, registrar essas mudanças via
    :func:`registrar_abertura_de_posicao` /
    :func:`registrar_fechamento_de_posicao` (helpers abaixo). Isso
    mantém :func:`decidir_acao` puramente decisória — coerente com a
    porta C# que segue o mesmo split.
    """
    _validar_barra(barra)
    _resetar_se_nova_sessao(estado, barra)

    # Passo 2: barra fora da Janela_Sessao_RTH.
    if not _esta_dentro_da_sessao(barra, parametros):
        return DecisaoORB(acao="NADA", motivo="fora-da-sessao")

    # Passo 3: fim de sessão com posição aberta → fechar.
    sessao_fim_dt = datetime.combine(
        barra.timestamp.date(),
        parametros.sessao_fim_utc,
        tzinfo=timezone.utc,
    )
    if (
        estado.posicao != "NADA"
        and barra.timestamp >= sessao_fim_dt - timedelta(minutes=1)
    ):
        return DecisaoORB(acao="FECHAR", motivo="fim-de-sessao")

    # Passo 4: barra dentro do Periodo_OR → atualiza range.
    if _esta_no_periodo_or(barra, parametros):
        if barra.high > estado.high_or:
            estado.high_or = barra.high
        if barra.low < estado.low_or:
            estado.low_or = barra.low
        return DecisaoORB(acao="NADA", motivo="acumulando-or")

    # Marca o OR como formado na primeira barra após o Periodo_OR.
    if not estado.or_formado:
        # Caso patológico R1.4: nenhuma barra caiu dentro do Periodo_OR
        # (ex.: gap na série). Sessão pulada — high_or e low_or
        # permanecem nos sentinelas e qualquer rompimento futuro falha
        # pela checagem de range_minimo_pontos.
        if estado.high_or == float("-inf") or estado.low_or == float("inf"):
            estado.or_formado = True
            return DecisaoORB(acao="NADA", motivo="or-vazio")
        estado.or_formado = True

    # Passo 5: posição aberta → ORB não decide saídas além do fim de sessão.
    if estado.posicao != "NADA":
        return DecisaoORB(acao="NADA", motivo="posicao-aberta")

    # Passo 6: cooldown ativo.
    if estado.cooldown_ate is not None and barra.timestamp < estado.cooldown_ate:
        return DecisaoORB(acao="NADA", motivo="cooldown")

    # Passo 7: já entrou nesta sessão (R2.3 — única entrada por sessão).
    if estado.entrou_nesta_sessao:
        return DecisaoORB(acao="NADA", motivo="ja-entrou-nesta-sessao")

    # Passo 8: hora de corte ultrapassada.
    if barra.timestamp.time() > parametros.hora_corte_entradas_utc:
        return DecisaoORB(acao="NADA", motivo="apos-hora-de-corte")

    # Passo 9: range degenerado.
    range_pontos = estado.high_or - estado.low_or
    if range_pontos <= parametros.range_minimo_pontos:
        return DecisaoORB(acao="NADA", motivo="range-degenerado")

    # Passos 10/11: rompimento (R2.1 / R2.2).
    rompeu_long = barra.close > estado.high_or
    rompeu_short = barra.close < estado.low_or

    if rompeu_long and rompeu_short:
        # Defensivo (R2.4): impossível com OR válido, mas se ambos os
        # lados parecem rompidos prefere o lado com maior magnitude.
        if (barra.close - estado.high_or) > (estado.low_or - barra.close):
            rompeu_short = False
        else:
            rompeu_long = False

    risco_pontos = range_pontos * parametros.risco_multiplicador
    if rompeu_long:
        stop = estado.low_or
        alvo = barra.close + risco_pontos * parametros.alvo_multiplicador
        return DecisaoORB(acao="LONG", stop=stop, alvo=alvo, motivo="rompimento-long")
    if rompeu_short:
        stop = estado.high_or
        alvo = barra.close - risco_pontos * parametros.alvo_multiplicador
        return DecisaoORB(acao="SHORT", stop=stop, alvo=alvo, motivo="rompimento-short")

    return DecisaoORB(acao="NADA", motivo="sem-rompimento")


# ---------------------------------------------------------------------------
# Helpers para o caller (Python ou C#) registrar transições de posição
# ---------------------------------------------------------------------------


def registrar_abertura_de_posicao(
    estado: EstadoORB,
    decisao: DecisaoORB,
) -> None:
    """Mantém ``estado.posicao`` e ``entrou_nesta_sessao`` coerentes (R2.3)."""
    if decisao.acao == "LONG":
        estado.posicao = "LONG"
        estado.entrou_nesta_sessao = True
    elif decisao.acao == "SHORT":
        estado.posicao = "SHORT"
        estado.entrou_nesta_sessao = True


def registrar_fechamento_de_posicao(
    estado: EstadoORB,
    timestamp_saida: datetime,
    parametros: ParametrosORB,
) -> None:
    """Marca posição como ``NADA`` e ativa cooldown (R4.1)."""
    estado.posicao = "NADA"
    estado.cooldown_ate = timestamp_saida + timedelta(
        minutes=parametros.cooldown_minutos
    )


__all__ = [
    "AcaoORB",
    "Barra",
    "DecisaoORB",
    "EstadoORB",
    "ParametrosORB",
    "PosicaoORB",
    "decidir_acao",
    "registrar_abertura_de_posicao",
    "registrar_fechamento_de_posicao",
]
