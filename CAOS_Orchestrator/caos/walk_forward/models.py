"""Modelos Pydantic v2 do Walk-Forward (Spec 2).

Este módulo declara os schemas formais consumidos pelos demais componentes
do pipeline de Walk-Forward (``JanelaGenerator``, ``BacktestRunner``,
``MetricasCalculator``, ``WalkForwardEngine``, ``RelatorioWriter``).

Os 4 modelos públicos abaixo refletem fielmente as restrições descritas em
``design.md`` (seção 3 — Data Models) e em ``requirements.md`` (R2 e R6):

- :class:`ConfiguracaoWalkForward` — parâmetros do pipeline (R2).
- :class:`JanelaWF` — par cronológico (Treino, Teste).
- :class:`ResultadoJanela` — métricas de uma janela (R6).
- :class:`ResultadoWalkForward` — agregado de todas as janelas.

Convenções (mesmas de ``caos.models``):

- Pydantic v2 com ``ConfigDict(extra="forbid", str_strip_whitespace=True)``
  em todos os modelos, para rejeitar campos extras silenciosos e remover
  espaços acidentais em strings.
- Datas exigem ``tzinfo`` (qualquer offset). Os campos de ``JanelaWF``
  exigem UTC explícito (offset 0) por se tratar de timestamps de barras
  do MNQ que vivem em ``dados/MNQ/`` em ISO 8601 com sufixo ``Z``.
- Identidades de status seguem kebab-case (``"abortado-por-falhas"``).
- ``hash_dados`` e ``manifesto_hash`` são SHA-256 hex (64 chars
  ``[0-9a-f]``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Constantes e tipos enumerados
# ---------------------------------------------------------------------------

#: Granularidades de barra suportadas pelo Walk-Forward.
Granularidade = Literal["1m", "tick"]

#: Status individual de uma janela executada (``ResultadoJanela.status``).
#:
#: - ``"ok"``: janela concluída com pelo menos 1 trade no Teste.
#: - ``"falha"``: exceção na Estrategia ou erro de execução (R10.1).
#: - ``"sem-trades"``: janela concluída mas com ``numero_trades == 0``
#:   (R6.2 — métricas dependentes ficam ``None``).
StatusJanela = Literal["ok", "falha", "sem-trades"]

#: Status agregado do Walk-Forward (``ResultadoWalkForward.status``).
#:
#: - ``"concluido"``: < 30% das janelas falharam (R10.2).
#: - ``"abortado-por-falhas"``: ≥ 30% das janelas falharam.
#: - ``"manifesto-invalido"``: Skill_Data_Integrity rejeitou os dados (R4.2).
StatusWalkForward = Literal[
    "concluido",
    "abortado-por-falhas",
    "manifesto-invalido",
]

#: Limites dos campos de :class:`ConfiguracaoWalkForward` (R2.1).
TAMANHO_TREINO_MIN = 60
TAMANHO_TREINO_MAX = 504
TAMANHO_TESTE_MIN = 10
TAMANHO_TESTE_MAX = 120
PASSO_MIN = 1

# Padrões reutilizados em validações de regex.
_REGEX_HASH_SHA256 = r"^[0-9a-f]{64}$"
_REGEX_IDENTIFICADOR_WF = r"^\d{4}-\d{2}-\d{2}-\d{2}$"


# ---------------------------------------------------------------------------
# Helpers de parsing de datetime
# ---------------------------------------------------------------------------


def _parse_datetime_utc(valor: Any) -> datetime:
    """Converte ``valor`` em ``datetime`` exigindo UTC (offset 0).

    Aceita:
    - ``datetime`` já com ``tzinfo`` UTC (offset zero) — retornado como está.
    - string ISO 8601 com sufixo ``"Z"`` ou ``"+00:00"``.

    Levanta ``ValueError`` para ``tzinfo`` ausente, offset não-zero, ou
    string malformada. Mesma regra do helper homônimo de ``caos.models``.
    """
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            raise ValueError(
                "datetime exige tzinfo (UTC ou offset 0); "
                "recebido naive datetime"
            )
        if valor.utcoffset() != timedelta(0):
            raise ValueError(
                "datetime deve estar em UTC (offset 0); "
                f"recebido {valor.isoformat()}"
            )
        return valor
    if isinstance(valor, str):
        bruto = valor.strip()
        if not bruto:
            raise ValueError("string de data vazia")
        normalizado = bruto[:-1] + "+00:00" if bruto.endswith("Z") else bruto
        try:
            parsed = datetime.fromisoformat(normalizado)
        except ValueError as exc:
            raise ValueError(
                f"data não está em formato ISO 8601 válido: {valor!r}"
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                f"data sem fuso horário: {valor!r} (use sufixo 'Z' ou '+00:00')"
            )
        if parsed.utcoffset() != timedelta(0):
            raise ValueError(
                f"data deve estar em UTC (offset 0); recebido {parsed.isoformat()}"
            )
        return parsed
    raise TypeError(
        "data deve ser datetime ou string ISO 8601, "
        f"recebido {type(valor).__name__}"
    )


# ---------------------------------------------------------------------------
# 3.1 — ConfiguracaoWalkForward (R2)
# ---------------------------------------------------------------------------


class ConfiguracaoWalkForward(BaseModel):
    """Configuração do pipeline de Walk-Forward (design 3, R2).

    Campos:
    - ``tamanho_treino_dias_uteis``: dias úteis do Periodo_Treino, no
      intervalo [60, 504] (R2.1).
    - ``tamanho_teste_dias_uteis``: dias úteis do Periodo_Teste, no
      intervalo [10, 120] (R2.1).
    - ``passo_dias_uteis``: avanço cronológico entre janelas; default é
      igual a ``tamanho_teste_dias_uteis`` (R2.1, R3.2).
    - ``instrumento``: símbolo do contrato; default ``"MNQ"`` conforme
      regra de steering ``instrumento-mnq.md``.
    - ``granularidade``: ``"1m"`` ou ``"tick"`` — granularidade das barras.
    - ``seed``: inteiro usado por ``random.seed`` / ``numpy.random.seed``
      antes de cada janela (R7.1).

    Validador cruzado (R2.2): ``tamanho_teste_dias_uteis`` não pode
    exceder ``tamanho_treino_dias_uteis`` — o Treino é sempre maior ou
    igual ao Teste.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tamanho_treino_dias_uteis: Annotated[
        int, Field(ge=TAMANHO_TREINO_MIN, le=TAMANHO_TREINO_MAX)
    ]
    tamanho_teste_dias_uteis: Annotated[
        int, Field(ge=TAMANHO_TESTE_MIN, le=TAMANHO_TESTE_MAX)
    ]
    passo_dias_uteis: Optional[Annotated[int, Field(ge=PASSO_MIN)]] = None
    instrumento: Annotated[str, Field(min_length=1, max_length=20)] = "MNQ"
    granularidade: Granularidade
    seed: int = 42

    @model_validator(mode="after")
    def _check_treino_maior_que_teste(self) -> "ConfiguracaoWalkForward":
        # R2.2: Treino sempre ≥ Teste.
        if self.tamanho_teste_dias_uteis > self.tamanho_treino_dias_uteis:
            raise ValueError(
                "tamanho_teste_dias_uteis "
                f"({self.tamanho_teste_dias_uteis}) não pode ser maior "
                "que tamanho_treino_dias_uteis "
                f"({self.tamanho_treino_dias_uteis}) — Treino sempre ≥ Teste"
            )
        # ``passo_dias_uteis`` defaulta para ``tamanho_teste_dias_uteis``
        # (R2.1) — preenchido aqui para manter o objeto consistente após
        # a validação. Pydantic v2 permite reatribuição em
        # ``model_validator(mode="after")``.
        if self.passo_dias_uteis is None:
            self.passo_dias_uteis = self.tamanho_teste_dias_uteis
        return self


# ---------------------------------------------------------------------------
# 3.2 — JanelaWF
# ---------------------------------------------------------------------------


class JanelaWF(BaseModel):
    """Par cronológico ``(Periodo_Treino, Periodo_Teste)`` de uma execução.

    Campos:
    - ``indice``: posição 0-based da janela no Walk-Forward (R3.1).
    - ``treino_inicio`` / ``treino_fim``: limites do Periodo_Treino (UTC).
    - ``teste_inicio`` / ``teste_fim``: limites do Periodo_Teste (UTC).
    - ``hash_dados``: SHA-256 hex do subset de barras usadas pela janela.

    Validações cruzadas (design 3, R3.1, R5):
    - ``treino_inicio < treino_fim``;
    - ``teste_inicio < teste_fim``;
    - ``treino_fim <= teste_inicio`` — Treino precede Teste sem
      sobreposição (anti-lookahead estrutural).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    indice: Annotated[int, Field(ge=0)]
    treino_inicio: datetime
    treino_fim: datetime
    teste_inicio: datetime
    teste_fim: datetime
    hash_dados: Annotated[str, Field(pattern=_REGEX_HASH_SHA256)]

    @field_validator(
        "treino_inicio",
        "treino_fim",
        "teste_inicio",
        "teste_fim",
        mode="before",
    )
    @classmethod
    def _parse_datas_utc(cls, valor: Any) -> datetime:
        return _parse_datetime_utc(valor)

    @model_validator(mode="after")
    def _check_ordem_cronologica(self) -> "JanelaWF":
        if self.treino_inicio >= self.treino_fim:
            raise ValueError(
                "treino_inicio deve ser estritamente menor que treino_fim; "
                f"recebido treino_inicio={self.treino_inicio.isoformat()}, "
                f"treino_fim={self.treino_fim.isoformat()}"
            )
        if self.teste_inicio >= self.teste_fim:
            raise ValueError(
                "teste_inicio deve ser estritamente menor que teste_fim; "
                f"recebido teste_inicio={self.teste_inicio.isoformat()}, "
                f"teste_fim={self.teste_fim.isoformat()}"
            )
        if self.treino_fim > self.teste_inicio:
            raise ValueError(
                "treino_fim deve preceder teste_inicio (sem sobreposição); "
                f"recebido treino_fim={self.treino_fim.isoformat()}, "
                f"teste_inicio={self.teste_inicio.isoformat()}"
            )
        return self


# ---------------------------------------------------------------------------
# 3.3 — ResultadoJanela (R6)
# ---------------------------------------------------------------------------


class ResultadoJanela(BaseModel):
    """Métricas geradas por uma janela executada (design 3, R6).

    Campos métricos (R6.1):
    - ``sharpe_anualizado`` — pode ser negativo, ``None`` se sem trades.
    - ``calmar`` — razão retorno anualizado / drawdown máx, ``None`` se
      sem trades ou drawdown == 0.
    - ``drawdown_maximo_percentual`` — magnitude do drawdown em [0, 1]
      (não negativo por convenção; 0.25 = drawdown de 25%).
    - ``drawdown_maximo_dias`` — duração do drawdown em dias úteis (≥ 0).
    - ``win_rate`` — proporção de trades vencedores em [0, 1].
    - ``payoff_medio`` — razão média de ganho/perda; ``None`` quando
      indefinido (zero perdas ou zero trades).
    - ``mfe_medio`` / ``mae_medio`` — magnitudes médias de Maximum
      Favorable / Adverse Excursion. Por convenção mantemos ambos
      como float qualquer (negativo permitido).
    - ``numero_trades`` — contagem de trades no Periodo_Teste (≥ 0).
    - ``pnl_total`` — PnL total da janela (float qualquer).

    Campos de auditoria (R5, R10):
    - ``look_ahead_violation`` — flag booleana levantada pelo
      ``BarrasTesteIterator`` quando detecta acesso a barra futura.
    - ``status`` — ``"ok"``, ``"falha"`` ou ``"sem-trades"``.
    - ``motivo_falha`` — stderr/exception truncado a 4096 chars (R10.3).
    - ``duracao_ms`` — tempo de execução da janela em milissegundos.

    Regras cruzadas (R6.2, R10.1):
    - ``status == "sem-trades"`` ⇒ ``numero_trades == 0`` e todas as
      métricas dependentes de trades (sharpe, calmar, drawdown_*,
      win_rate, payoff_medio, mfe_medio, mae_medio) devem ser ``None``.
    - ``status == "falha"`` ⇒ ``motivo_falha`` não pode ser ``None``.
    - ``status == "ok"`` ⇒ ``numero_trades >= 1`` e ``motivo_falha is None``.
    - ``motivo_falha`` (quando presente) limitado a 4096 chars (R10.3).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    janela: JanelaWF
    estrategia: Annotated[str, Field(min_length=1, max_length=200)]
    configuracao: ConfiguracaoWalkForward
    sharpe_anualizado: Optional[float] = None
    calmar: Optional[float] = None
    drawdown_maximo_percentual: Optional[
        Annotated[float, Field(ge=0.0, le=1.0)]
    ] = None
    drawdown_maximo_dias: Optional[Annotated[int, Field(ge=0)]] = None
    win_rate: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None
    payoff_medio: Optional[Annotated[float, Field(ge=0.0)]] = None
    mfe_medio: Optional[float] = None
    mae_medio: Optional[float] = None
    numero_trades: Annotated[int, Field(ge=0)]
    pnl_total: float
    look_ahead_violation: bool = False
    status: StatusJanela
    motivo_falha: Optional[Annotated[str, Field(min_length=1, max_length=4096)]] = None
    duracao_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _check_consistencia_status(self) -> "ResultadoJanela":
        # R10.1 — status "falha" exige motivo_falha.
        if self.status == "falha":
            if self.motivo_falha is None:
                raise ValueError(
                    "ResultadoJanela com status='falha' exige "
                    "motivo_falha não nulo (R10.1)"
                )
            return self

        # R6.2 — status "sem-trades" exige numero_trades == 0 e métricas
        # dependentes de trades como None (não inventar zeros).
        if self.status == "sem-trades":
            if self.numero_trades != 0:
                raise ValueError(
                    "ResultadoJanela com status='sem-trades' exige "
                    f"numero_trades=0; recebido {self.numero_trades}"
                )
            metricas_dependentes = {
                "sharpe_anualizado": self.sharpe_anualizado,
                "calmar": self.calmar,
                "drawdown_maximo_percentual": self.drawdown_maximo_percentual,
                "drawdown_maximo_dias": self.drawdown_maximo_dias,
                "win_rate": self.win_rate,
                "payoff_medio": self.payoff_medio,
                "mfe_medio": self.mfe_medio,
                "mae_medio": self.mae_medio,
            }
            preenchidas = [
                nome for nome, val in metricas_dependentes.items() if val is not None
            ]
            if preenchidas:
                raise ValueError(
                    "ResultadoJanela com status='sem-trades' exige métricas "
                    "dependentes de trades como None (R6.2); preenchidas: "
                    f"{preenchidas}"
                )
            if self.motivo_falha is not None:
                raise ValueError(
                    "ResultadoJanela com status='sem-trades' não deve "
                    "carregar motivo_falha; "
                    f"recebido {self.motivo_falha!r}"
                )
            return self

        # status == "ok"
        if self.numero_trades < 1:
            raise ValueError(
                "ResultadoJanela com status='ok' exige numero_trades >= 1; "
                f"recebido {self.numero_trades} (use status='sem-trades')"
            )
        if self.motivo_falha is not None:
            raise ValueError(
                "ResultadoJanela com status='ok' não deve carregar "
                f"motivo_falha; recebido {self.motivo_falha!r}"
            )
        return self


# ---------------------------------------------------------------------------
# 3.4 — ResultadoWalkForward
# ---------------------------------------------------------------------------


class ResultadoWalkForward(BaseModel):
    """Agregado de todos os :class:`ResultadoJanela` de uma execução.

    Campos:
    - ``identificador``: ``AAAA-MM-DD-NN`` (R1.3, R3.3).
    - ``estrategia``: nome da Estrategia avaliada.
    - ``configuracao``: :class:`ConfiguracaoWalkForward` usada.
    - ``manifesto_hash``: SHA-256 hex agregado dos arquivos lidos (R4.3).
    - ``janelas``: lista de :class:`ResultadoJanela`, possivelmente vazia
      quando ``status == "manifesto-invalido"``.
    - ``agregado_mediana`` / ``agregado_media``: dicionários nome→valor
      das métricas agregadas (R6.3).
    - ``versoes_dependencias``: ex. ``{"pandas": "2.x", "numpy": "1.x"}``
      (R7.2).
    - ``status``: ``"concluido"``, ``"abortado-por-falhas"``,
      ``"manifesto-invalido"``.

    Validação cruzada (R3.1, R10.2):
    - Janelas devem ter ``indice`` único e estritamente crescente
      (0, 1, 2, ...).
    - Janelas devem ser cronologicamente não-sobrepostas: para todo par
      ``(j_i, j_{i+1})``, ``j_i.teste_fim <= j_{i+1}.teste_inicio``.
    - ``status == "manifesto-invalido"`` exige ``janelas == []``.
    - ``status == "abortado-por-falhas"`` exige ``janelas != []`` e a
      taxa de falhas ``> 30%`` (R10.2).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identificador: Annotated[str, Field(pattern=_REGEX_IDENTIFICADOR_WF)]
    estrategia: Annotated[str, Field(min_length=1, max_length=200)]
    configuracao: ConfiguracaoWalkForward
    manifesto_hash: Annotated[str, Field(pattern=_REGEX_HASH_SHA256)]
    janelas: list[ResultadoJanela] = Field(default_factory=list)
    agregado_mediana: dict[str, float] = Field(default_factory=dict)
    agregado_media: dict[str, float] = Field(default_factory=dict)
    versoes_dependencias: dict[str, str] = Field(default_factory=dict)
    status: StatusWalkForward

    @model_validator(mode="after")
    def _check_janelas_e_status(self) -> "ResultadoWalkForward":
        # 1. Status terminal "manifesto-invalido" exige lista vazia de janelas.
        if self.status == "manifesto-invalido":
            if self.janelas:
                raise ValueError(
                    "ResultadoWalkForward com status='manifesto-invalido' "
                    "não deve carregar janelas; recebido "
                    f"{len(self.janelas)} janelas"
                )
            return self

        # 2. Demais status exigem pelo menos 1 janela.
        if not self.janelas:
            raise ValueError(
                f"ResultadoWalkForward com status={self.status!r} exige "
                "pelo menos 1 janela em ``janelas``"
            )

        # 3. Índices únicos e estritamente crescentes (0, 1, 2, ...).
        for esperado, resultado in enumerate(self.janelas):
            if resultado.janela.indice != esperado:
                raise ValueError(
                    "janelas devem ter ``indice`` 0-based estritamente "
                    f"crescente; posição {esperado} tem "
                    f"indice={resultado.janela.indice}"
                )

        # 4. Janelas cronologicamente não-sobrepostas (R3.1).
        for i in range(len(self.janelas) - 1):
            j_atual = self.janelas[i].janela
            j_prox = self.janelas[i + 1].janela
            if j_atual.teste_fim > j_prox.teste_inicio:
                raise ValueError(
                    "janelas devem ser não-sobrepostas (R3.1): "
                    f"janela {j_atual.indice}.teste_fim="
                    f"{j_atual.teste_fim.isoformat()} > "
                    f"janela {j_prox.indice}.teste_inicio="
                    f"{j_prox.teste_inicio.isoformat()}"
                )

        # 5. R10.2 — status "abortado-por-falhas" exige taxa de falhas > 30%.
        if self.status == "abortado-por-falhas":
            total = len(self.janelas)
            falhas = sum(1 for r in self.janelas if r.status == "falha")
            taxa = falhas / total
            if taxa <= 0.30:
                raise ValueError(
                    "ResultadoWalkForward com status='abortado-por-falhas' "
                    f"exige taxa de falhas > 30%; recebido {falhas}/{total} "
                    f"= {taxa:.2%}"
                )

        return self


__all__ = [
    # Tipos / constantes
    "Granularidade",
    "StatusJanela",
    "StatusWalkForward",
    "TAMANHO_TREINO_MIN",
    "TAMANHO_TREINO_MAX",
    "TAMANHO_TESTE_MIN",
    "TAMANHO_TESTE_MAX",
    "PASSO_MIN",
    # Modelos
    "ConfiguracaoWalkForward",
    "JanelaWF",
    "ResultadoJanela",
    "ResultadoWalkForward",
]
