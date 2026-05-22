"""Modelos de dados (Pydantic v2) do orquestrador CAOS.

Este módulo declara os schemas formais consumidos pelos demais componentes do
orquestrador (Profile_Loader, Steering_Engine, Context_Loader, Council_Recorder,
Determinism_Auditor, LLM_Cache_Adapter, Token_Budget_Guard e
Data_Manifest_Manager). Cada classe reflete fielmente as restrições descritas em
``design.md`` (seções 3.1 a 3.6) e em ``requirements.md`` (R2, R8, R10, R12,
R15, R16, R17).

Convenções:

- Pydantic v2 é usado com ``ConfigDict(extra="forbid", str_strip_whitespace=True)``
  em todos os modelos, para rejeitar campos extras silenciosos e remover espaços
  acidentais em strings.
- Datas e horários seguem ISO 8601. Campos que exigem UTC (``data_criacao`` de
  ``NotaZettel``, ``data_criacao`` de ``EntradaCache``, ``mtime`` e períodos de
  ``EntradaManifesto``) são validados via ``_parse_datetime_utc``. Os demais
  campos de timestamp aceitam qualquer fuso, desde que ``tzinfo`` esteja
  presente, e usam ``_parse_datetime_with_tz``.
- Identidades (``nome``, ``agente``, ``autor``) são restritas via ``Literal`` ao
  conjunto exato dos 9 agentes do Conselho.
- Modelos de LLM (``modelo``) são restritos via ``Literal`` ao conjunto exato
  dos 7 modelos catalogados em R2.3 e a relação ``(agente, modelo)`` é validada
  por ``model_validator(mode="after")`` em ``AgentProfile``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
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

#: Conjunto exato dos 9 agentes-persona do Conselho CAOS.
AGENTES: tuple[str, ...] = (
    "Athena",
    "Odin",
    "Mister_M",
    "Manolo",
    "Rodrigo",
    "Cerberus",
    "Hermes",
    "Explorador",
    "Devils_Advocate",
)

#: Tipo Literal restrito aos 9 agentes do Conselho (espelha ``AGENTES``).
AgenteNome = Literal[
    "Athena",
    "Odin",
    "Mister_M",
    "Manolo",
    "Rodrigo",
    "Cerberus",
    "Hermes",
    "Explorador",
    "Devils_Advocate",
]

#: Conjunto exato dos modelos de LLM permitidos pelo Spec 1 (R2.3).
ModeloLLM = Literal[
    "claude-opus-4.7",
    "claude-sonnet-4.5",
    "claude-haiku-4.5",
    "minimax-m2",
    "qwen3",
    "qwen3-coder",
    "deepseek-v3.1",
]

#: Mapeamento agente → modelos permitidos conforme R2.3.
MODELOS_PERMITIDOS: dict[str, frozenset[str]] = {
    "Athena": frozenset({"claude-opus-4.7"}),
    "Odin": frozenset({"claude-sonnet-4.5"}),
    "Mister_M": frozenset({"minimax-m2", "qwen3"}),
    "Manolo": frozenset({"claude-haiku-4.5"}),
    "Rodrigo": frozenset({"deepseek-v3.1"}),
    "Cerberus": frozenset({"claude-sonnet-4.5"}),
    "Hermes": frozenset({"qwen3-coder", "deepseek-v3.1"}),
    "Explorador": frozenset({"claude-sonnet-4.5"}),
    "Devils_Advocate": frozenset({"minimax-m2"}),
}

#: Tipo Literal das 9 Skills declaradas no Requirement 11.
SkillNome = Literal[
    "Skill_Terminal",
    "Skill_Git",
    "Skill_MSBuild",
    "Skill_Web_Search",
    "Skill_CSV_Reader",
    "Skill_Data_Inspector",
    "Skill_Data_Integrity",
    "Skill_LLM_Cache",
    "Skill_Token_Budget",
]

#: Áreas raiz exigidas pelo Zettelkasten (R10.1 e design 3.2).
AreaZettel = Literal[
    "Modulo_Institucional",
    "Modulo_Risco",
    "API_NinjaTrader_8_Reference",
    "Papers",
    "Decisoes_do_Conselho",
]

#: Fases ativas do Debate (mantém a ordem da state machine — design seção 4).
FaseDebate = Literal[
    "INICIADO",
    "PROPOSTAS",
    "CRITICA",
    "AVALIACAO_RISCO",
    "AVALIACAO_TECNICA",
    "SINTESE",
]

#: Estados terminais possíveis de um Debate (design seção 4 — diagrama).
FaseTerminal = Literal[
    "CONCLUIDO",
    "TIMEOUT",
    "SEM_QUORUM",
    "ABORTADO_POR_INDISPONIBILIDADE",
    "PENDENTE_USUARIO",
    "CERBERUS_TIMEOUT",
]

#: União das fases ativas e terminais — usada em ``Debate.fase_final``.
FaseFinal = Literal[
    "INICIADO",
    "PROPOSTAS",
    "CRITICA",
    "AVALIACAO_RISCO",
    "AVALIACAO_TECNICA",
    "SINTESE",
    "CONCLUIDO",
    "TIMEOUT",
    "SEM_QUORUM",
    "ABORTADO_POR_INDISPONIBILIDADE",
    "PENDENTE_USUARIO",
    "CERBERUS_TIMEOUT",
]

#: Status público do Debate / DecisaoDoConselho (kebab-case).
StatusDebate = Literal[
    "em-andamento",
    "concluido",
    "timeout",
    "sem-quorum",
    "abortado-por-indisponibilidade",
    "pendente-de-usuario",
    "cerberus-timeout",
]

#: Status do Turno individual (R14 — tratamento de falhas).
StatusTurno = Literal[
    "ok",
    "ausente",
    "agente-indisponivel",
    "orcamento-de-tokens-esgotado",
    "erro",
]

#: Status atribuído a uma Nota_Zettel de paper pelo Bias_Filter (R12).
StatusPaper = Literal[
    "aprovada",
    "rejeitada",
    "amostra-insuficiente",
    "bias-nao-tratado",
    "out-of-sample-insuficiente",
    "dados-incompletos",
]

#: Categorias possíveis de Veto_Tecnico (R6.6).
CategoriaVetoTecnico = Literal[
    "compilacao_falhou",
    "api_nao_autorizada",
    "steering_indisponivel",
]

# Padrões reutilizados em validações de regex.
_REGEX_HASH_SHA256 = r"^[0-9a-f]{64}$"
_REGEX_PROPOSTA_ID = r"^P\d+$"
_REGEX_DEBATE_ID = r"^\d{4}-\d{2}-\d{2}-\d{2}$"
_REGEX_SLUG_TITULO = r"^[a-z0-9-]{1,60}$"
_REGEX_WIKI_LINK = r"^\[\[[^\[\]]+\]\]$"


# ---------------------------------------------------------------------------
# Helpers de parsing de datetime
# ---------------------------------------------------------------------------


def _parse_datetime_with_tz(valor: Any) -> datetime:
    """Converte ``valor`` em ``datetime`` exigindo ``tzinfo`` presente.

    Aceita:
    - ``datetime`` já com ``tzinfo`` (retornado como está);
    - string ISO 8601 com sufixo ``Z`` (UTC) ou offset explícito ``+HH:MM``.

    Levanta ``ValueError`` quando a string é inválida ou o ``tzinfo`` está
    ausente após o parsing.
    """
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            raise ValueError("datetime exige tzinfo (UTC ou offset explícito)")
        return valor
    if isinstance(valor, str):
        bruto = valor.strip()
        if not bruto:
            raise ValueError("string de data vazia")
        # ``datetime.fromisoformat`` em 3.11+ aceita 'Z' diretamente apenas em
        # algumas versões; por segurança normalizamos manualmente.
        normalizado = bruto[:-1] + "+00:00" if bruto.endswith("Z") else bruto
        try:
            parsed = datetime.fromisoformat(normalizado)
        except ValueError as exc:
            raise ValueError(
                f"data não está em formato ISO 8601 válido: {valor!r}"
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                f"data sem fuso horário: {valor!r} (use sufixo 'Z' ou offset)"
            )
        return parsed
    raise TypeError(
        "data deve ser datetime ou string ISO 8601, "
        f"recebido {type(valor).__name__}"
    )


def _parse_datetime_utc(valor: Any) -> datetime:
    """Converte ``valor`` em ``datetime`` exigindo UTC (offset zero).

    Mais estrito que :func:`_parse_datetime_with_tz`: rejeita qualquer offset
    diferente de zero. Usado para campos cuja semântica exige UTC explícito
    (``NotaZettel.data_criacao`` — R10.3, manifesto e cache).
    """
    parsed = _parse_datetime_with_tz(valor)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(
            f"data deve estar em UTC (offset 0); recebido {parsed.isoformat()}"
        )
    return parsed


# ---------------------------------------------------------------------------
# 3.1 — Perfil de agente
# ---------------------------------------------------------------------------


class ConfiancaSchema(BaseModel):
    """Sub-schema do bloco ``confianca`` declarado no formato de saída do agente.

    Reflete o trecho YAML do design 3.1:

    .. code-block:: yaml

       confianca:
         tipo: inteiro
         minimo: 0
         maximo: 100
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tipo: Literal["inteiro"] = "inteiro"
    minimo: int = 0
    maximo: int = 100

    @model_validator(mode="after")
    def _check_intervalo(self) -> "ConfiancaSchema":
        if self.minimo != 0 or self.maximo != 100:
            raise ValueError(
                "intervalo de confiança deve ser exatamente [0, 100]; "
                f"recebido [{self.minimo}, {self.maximo}]"
            )
        return self


class FormatoDeSaida(BaseModel):
    """Schema do campo ``formato_de_saida`` do perfil de agente (R2.4).

    As 4 seções obrigatórias devem aparecer exatamente nesta ordem:
    ``[Proposta, Justificativa, Riscos, Confianca]``.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    secoes_obrigatorias: list[
        Literal["Proposta", "Justificativa", "Riscos", "Confianca"]
    ]
    confianca: ConfiancaSchema = Field(default_factory=ConfiancaSchema)

    @field_validator("secoes_obrigatorias")
    @classmethod
    def _check_ordem_secoes(cls, valor: list[str]) -> list[str]:
        ordem_esperada = ["Proposta", "Justificativa", "Riscos", "Confianca"]
        if valor != ordem_esperada:
            raise ValueError(
                "secoes_obrigatorias deve ser exatamente "
                f"{ordem_esperada} nessa ordem; recebido {valor}"
            )
        return valor


class AgentProfile(BaseModel):
    """Perfil de um dos 9 agentes-persona do Conselho (design 3.1, R2.1–R2.6).

    Validações aplicadas:
    - ``nome`` restrito ao enum dos 9 agentes (sem espaços).
    - ``modelo`` restrito ao enum de 7 modelos autorizados.
    - O par ``(nome, modelo)`` deve respeitar o mapeamento R2.3.
    - ``tags_especialidade`` deve ter pelo menos 1 elemento e cada tag
      entre 1 e 50 caracteres.
    - ``skills_permitidas`` aceita lista vazia; quando preenchida, cada nome
      deve estar no catálogo do Requirement 11.
    - ``escopo_de_decisao`` deve ter pelo menos 1 elemento.
    - ``system_prompt`` deve ter entre 1 e 8000 caracteres (R2.2).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nome: AgenteNome
    modelo: ModeloLLM
    tags_especialidade: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=50)]],
        Field(min_length=1),
    ]
    skills_permitidas: list[SkillNome]
    escopo_de_decisao: Annotated[list[str], Field(min_length=1)]
    formato_de_saida: FormatoDeSaida
    system_prompt: Annotated[str, Field(min_length=1, max_length=8000)]

    @field_validator("nome")
    @classmethod
    def _nome_sem_espacos(cls, valor: str) -> str:
        if any(c.isspace() for c in valor):
            raise ValueError(
                f"nome do agente não pode conter espaços; recebido {valor!r}"
            )
        return valor

    @model_validator(mode="after")
    def _check_modelo_consistente(self) -> "AgentProfile":
        permitidos = MODELOS_PERMITIDOS[self.nome]
        if self.modelo not in permitidos:
            raise ValueError(
                f"agente {self.nome!r} requer modelo em {sorted(permitidos)}; "
                f"recebido {self.modelo!r}"
            )
        return self


# ---------------------------------------------------------------------------
# 3.2 — Nota_Zettel
# ---------------------------------------------------------------------------


class NotaZettel(BaseModel):
    """Frontmatter de Nota_Zettel (design 3.2, R10.3).

    Os campos opcionais ``corpo_markdown`` e ``wiki_links`` carregam,
    respectivamente, o corpo Markdown da nota (sem o frontmatter) e a lista
    de nomes-alvo de wiki-links extraídos do corpo.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    titulo: Annotated[str, Field(min_length=1, max_length=200)]
    area: AreaZettel
    tags: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=50)]],
        Field(min_length=1, max_length=20),
    ]
    data_criacao: datetime
    agente_autor: AgenteNome
    corpo_markdown: Optional[str] = None
    wiki_links: list[str] = Field(default_factory=list)

    @field_validator("data_criacao", mode="before")
    @classmethod
    def _parse_data_criacao(cls, valor: Any) -> datetime:
        # R10.3 exige UTC (sufixo 'Z' ou offset zero explícito).
        return _parse_datetime_utc(valor)


# ---------------------------------------------------------------------------
# 3.4 — Proposta, Veto, DecisaoFinal
# ---------------------------------------------------------------------------


class Proposta(BaseModel):
    """Proposta submetida por um agente durante a fase ``PROPOSTAS``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: Annotated[str, Field(pattern=_REGEX_PROPOSTA_ID)]
    autor: AgenteNome
    resumo: Annotated[str, Field(min_length=1, max_length=500)]
    conteudo: Annotated[str, Field(min_length=1)]
    confianca: Annotated[int, Field(ge=0, le=100)]


class Veto(BaseModel):
    """Veto emitido por Cerberus (risco) ou Hermes (técnico) — R5, R6.

    Regras de consistência aplicadas em ``model_validator``:

    - ``veto_de_risco`` somente Cerberus pode emitir; ``categoria_tecnica``
      deve ser ``None``; ``decisao`` é ``bloquear`` ou ``aprovar-com-ressalvas``.
    - ``veto_tecnico`` somente Hermes pode emitir; ``decisao`` é sempre
      ``bloquear``; ``categoria_tecnica`` é obrigatória.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tipo: Literal["veto_de_risco", "veto_tecnico"]
    autor: AgenteNome
    decisao: Literal["bloquear", "aprovar-com-ressalvas"]
    proposta_alvo: Annotated[str, Field(pattern=_REGEX_PROPOSTA_ID)]
    justificativa: Annotated[str, Field(min_length=1)]
    categoria_tecnica: Optional[CategoriaVetoTecnico] = None

    @model_validator(mode="after")
    def _check_consistencia(self) -> "Veto":
        if self.tipo == "veto_de_risco":
            if self.autor != "Cerberus":
                raise ValueError(
                    "veto_de_risco só pode ser emitido por Cerberus; "
                    f"recebido autor={self.autor!r}"
                )
            if self.categoria_tecnica is not None:
                raise ValueError(
                    "veto_de_risco não deve declarar categoria_tecnica; "
                    f"recebido {self.categoria_tecnica!r}"
                )
        else:  # veto_tecnico
            if self.autor != "Hermes":
                raise ValueError(
                    "veto_tecnico só pode ser emitido por Hermes; "
                    f"recebido autor={self.autor!r}"
                )
            if self.decisao != "bloquear":
                raise ValueError(
                    "veto_tecnico exige decisao='bloquear'; "
                    f"recebido {self.decisao!r}"
                )
            if self.categoria_tecnica is None:
                raise ValueError(
                    "veto_tecnico exige categoria_tecnica não nula"
                )
        return self


class DecisaoFinal(BaseModel):
    """Bloco ``decisao_final`` da Decisao_Do_Conselho (design 3.4).

    ``proposta_aceita`` pode ser ``None`` em decisões sem aceitação (sem-quorum,
    timeout, abortado, pendente-de-usuario).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    proposta_aceita: Optional[
        Annotated[str, Field(pattern=_REGEX_PROPOSTA_ID)]
    ] = None
    rationale: Annotated[str, Field(min_length=1)]


# ---------------------------------------------------------------------------
# 3.3 — Turno e Debate
# ---------------------------------------------------------------------------


class Turno(BaseModel):
    """Turno individual do Debate (design 3.3, R4.7, R9.2).

    ``timestamp`` exige ``tzinfo`` (qualquer offset, não só UTC). Se o agente
    rodar com modelo sem suporte a seed, ``nao_deterministico`` deve vir
    ``True`` (R9.2).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    numero: Annotated[int, Field(ge=1)]
    agente: AgenteNome
    modelo: Annotated[str, Field(min_length=1)]
    timestamp: datetime
    fase: FaseDebate
    nao_deterministico: bool = False
    notas_injetadas: list[str] = Field(default_factory=list)
    contexto_hash_sha256: Optional[
        Annotated[str, Field(pattern=_REGEX_HASH_SHA256)]
    ] = None
    cache_hit: Optional[bool] = None
    status: StatusTurno = "ok"
    conteudo_markdown: Optional[str] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, valor: Any) -> datetime:
        return _parse_datetime_with_tz(valor)


class Debate(BaseModel):
    """Cabeçalho + turnos do arquivo de Debate (design 3.3, R7, R8, R9).

    ``identificador`` segue ``AAAA-MM-DD-NN`` (R8.1). ``titulo`` é um slug
    kebab-case com no máximo 60 caracteres (R4.1, R8.1). ``orcamento_de_turnos``
    deve estar em [4, 100] (R7.2).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identificador: Annotated[str, Field(pattern=_REGEX_DEBATE_ID)]
    titulo: Annotated[str, Field(pattern=_REGEX_SLUG_TITULO)]
    data_inicio: datetime
    data_fim: Optional[datetime] = None
    agentes_participantes: Annotated[list[AgenteNome], Field(min_length=1)]
    modelos: dict[str, str]
    contexto_hash_sha256: Annotated[str, Field(pattern=_REGEX_HASH_SHA256)]
    notas_injetadas: list[str]
    seeds: dict[str, int]
    orcamento_de_turnos: Annotated[int, Field(ge=4, le=100)]
    turnos_consumidos: Annotated[int, Field(ge=0)]
    fase_final: FaseFinal
    status: StatusDebate
    turnos: list[Turno] = Field(default_factory=list)

    @field_validator("data_inicio", "data_fim", mode="before")
    @classmethod
    def _parse_datas(cls, valor: Any) -> Any:
        if valor is None:
            return None
        return _parse_datetime_with_tz(valor)


# ---------------------------------------------------------------------------
# 3.4 — Decisao_Do_Conselho
# ---------------------------------------------------------------------------


class DecisaoDoConselho(BaseModel):
    """Decisao_Do_Conselho (design 3.4, R8.2).

    Validações:
    - ``identificador`` segue ``AAAA-MM-DD-NN``.
    - ``propostas`` exige no mínimo 1 elemento.
    - ``links_zettel`` exige no mínimo 1 wiki-link no formato ``[[Nome]]``.
    - ``vetos`` pode estar vazio (R8.2 — única lista que aceita zero).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identificador: Annotated[str, Field(pattern=_REGEX_DEBATE_ID)]
    debate_relacionado: Annotated[str, Field(min_length=1)]
    agentes_participantes: Annotated[list[AgenteNome], Field(min_length=1)]
    propostas: Annotated[list[Proposta], Field(min_length=1)]
    vetos: list[Veto] = Field(default_factory=list)
    decisao_final: DecisaoFinal
    links_zettel: Annotated[
        list[Annotated[str, Field(pattern=_REGEX_WIKI_LINK)]],
        Field(min_length=1),
    ]
    aprovado_walk_forward: bool = False
    reproduzivel: Literal["true", "parcial", "false"]
    regressao_detectada: bool = False
    status: StatusDebate


# ---------------------------------------------------------------------------
# 3.5 — Regra de Steering
# ---------------------------------------------------------------------------


class RegraSteering(BaseModel):
    """Cabeçalho de regra de Steering em ``.kiro/steering/*.md`` (design 3.5, R3.5).

    O campo ``autor`` é restrito a ``Athena`` ou ``usuario``: optamos por
    armazenar sem acento para evitar problemas de encoding em arquivos
    versionados em Windows + Git.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    data: date
    autor: Literal["Athena", "usuario"]
    justificativa: Annotated[str, Field(min_length=10)]
    corpo_markdown: Optional[str] = None
    nome_arquivo: Optional[str] = None


# ---------------------------------------------------------------------------
# 3.6 — Nota_Zettel de paper
# ---------------------------------------------------------------------------


class NotaPaper(NotaZettel):
    """Nota_Zettel de paper (design 3.6, R12).

    Estende :class:`NotaZettel` adicionando os metadados de avaliação aplicados
    pelo Bias_Filter. Exige ``area == "Papers"``.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sharpe_replicado: float
    sample_size: Annotated[int, Field(ge=0)]
    out_of_sample_periodo: Annotated[int, Field(ge=0)]
    instrumento_testado: Annotated[str, Field(min_length=1)]
    survivorship_bias_tratado: bool
    status: StatusPaper

    @field_validator("area")
    @classmethod
    def _area_deve_ser_papers(cls, valor: str) -> str:
        if valor != "Papers":
            raise ValueError(
                "NotaPaper exige area='Papers'; "
                f"recebido {valor!r}"
            )
        return valor


# ---------------------------------------------------------------------------
# R16 — Cache de respostas LLM
# ---------------------------------------------------------------------------


class EntradaCache(BaseModel):
    """Entrada do Skill_LLM_Cache (R16).

    A ``chave`` é o SHA-256 hex computado sobre
    ``(agente, modelo, hash_prompt, hash_contexto, seed)``.
    ``seed`` aceita string vazia para representar modelos sem suporte a seed.
    """

    model_config = ConfigDict(extra="forbid")

    chave: Annotated[str, Field(pattern=_REGEX_HASH_SHA256)]
    agente: AgenteNome
    modelo: ModeloLLM
    seed: str
    data_criacao: datetime
    tokens_consumidos_estimados: Annotated[int, Field(ge=0)]
    resposta: str

    @field_validator("data_criacao", mode="before")
    @classmethod
    def _parse_data(cls, valor: Any) -> datetime:
        return _parse_datetime_utc(valor)


# ---------------------------------------------------------------------------
# R17 — Estado de orçamento de tokens
# ---------------------------------------------------------------------------


class EstadoOrcamento(BaseModel):
    """Estado diário do orçamento de tokens por agente (R17).

    Validação cruzada: ``tokens_total_consumidos`` deve ser exatamente igual a
    ``tokens_input_consumidos + tokens_output_consumidos``. A regra
    ``orcamento_diario_tokens >= 10000`` (R17.2) é responsabilidade do
    Skill_Token_Budget; aqui mantemos apenas ``>= 0`` para permitir leitura de
    estados inválidos sem mascarar o erro semântico.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    agente: AgenteNome
    tokens_input_consumidos: Annotated[int, Field(ge=0)]
    tokens_output_consumidos: Annotated[int, Field(ge=0)]
    tokens_total_consumidos: Annotated[int, Field(ge=0)]
    orcamento_diario_tokens: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _check_total(self) -> "EstadoOrcamento":
        soma = self.tokens_input_consumidos + self.tokens_output_consumidos
        if self.tokens_total_consumidos != soma:
            raise ValueError(
                "tokens_total_consumidos deve ser igual a "
                "tokens_input_consumidos + tokens_output_consumidos; "
                f"recebido total={self.tokens_total_consumidos}, "
                f"input+output={soma}"
            )
        return self


# ---------------------------------------------------------------------------
# R15 — Entrada do manifesto de dados MNQ
# ---------------------------------------------------------------------------


class EntradaManifesto(BaseModel):
    """Entrada de ``dados/MNQ/manifesto.json`` (R15).

    ``nome_arquivo`` deve ser caminho relativo POSIX (sem ``\\`` e sem prefixo
    ``/``), localizado dentro de ``dados/MNQ/``.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nome_arquivo: Annotated[str, Field(min_length=1)]
    tamanho_bytes: Annotated[int, Field(ge=0)]
    mtime: datetime
    num_linhas: Annotated[int, Field(ge=0)]
    hash_sha256: Annotated[str, Field(pattern=_REGEX_HASH_SHA256)]
    periodo_inicial: Optional[datetime] = None
    periodo_final: Optional[datetime] = None
    instrumento: str = "MNQ"

    @field_validator("nome_arquivo")
    @classmethod
    def _check_caminho_posix(cls, valor: str) -> str:
        if "\\" in valor:
            raise ValueError(
                "nome_arquivo deve usar separadores POSIX ('/'); "
                f"recebido {valor!r}"
            )
        if valor.startswith("/"):
            raise ValueError(
                "nome_arquivo deve ser caminho relativo (sem '/' inicial); "
                f"recebido {valor!r}"
            )
        return valor

    @field_validator("mtime", "periodo_inicial", "periodo_final", mode="before")
    @classmethod
    def _parse_datas(cls, valor: Any) -> Any:
        if valor is None:
            return None
        return _parse_datetime_utc(valor)


__all__ = [
    # Constantes / tipos
    "AGENTES",
    "AgenteNome",
    "ModeloLLM",
    "MODELOS_PERMITIDOS",
    "SkillNome",
    "AreaZettel",
    "FaseDebate",
    "FaseTerminal",
    "FaseFinal",
    "StatusDebate",
    "StatusTurno",
    "StatusPaper",
    "CategoriaVetoTecnico",
    # Sub-modelos
    "ConfiancaSchema",
    "FormatoDeSaida",
    "DecisaoFinal",
    # Modelos públicos da Task 2
    "AgentProfile",
    "NotaZettel",
    "Debate",
    "Turno",
    "Proposta",
    "Veto",
    "DecisaoDoConselho",
    "RegraSteering",
    "NotaPaper",
    "EntradaCache",
    "EstadoOrcamento",
    "EntradaManifesto",
]
