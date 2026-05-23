"""I/O do fluxo de Debate (Spec 5 — Task 2).

Implementa os helpers consumidos pelo CLI ``caos debate iniciar`` e
``caos debate fechar``. O módulo é totalmente offline: gera Debate_Starter
em ``CAOS_Council/debates/AAAA-MM-DD-NN-{slug}.md`` e, no fechamento,
delega gravação + commit Git para :class:`caos.council_recorder.CouncilRecorder`
(Spec 1 — R8).

Convenções:

- Idioma pt-BR em todas as mensagens visíveis ao usuário.
- Identificadores ``AAAA-MM-DD-NN`` em UTC.
- Slug kebab-case 1–60 caracteres ASCII (mesmo regex do
  :class:`caos.models.Debate`).
- Frontmatter YAML escrito com ``yaml.safe_dump(..., sort_keys=True,
  allow_unicode=True)`` para que o arquivo seja byte-estável entre
  invocações.
- Gatilho do Debate (G1..G5 ou ``usuario``) é registrado em
  ``notas_injetadas`` no formato ``gatilho:<nome>`` e
  ``aberto_por:<auto|usuario>`` para preservar compatibilidade com o
  schema :class:`caos.models.Debate` (que tem ``extra="forbid"``).

Cobre R3 e R4 do ``requirements.md`` do Spec 5.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Literal, Optional

import yaml
from pydantic import ValidationError

from caos.council_recorder import CouncilRecorder, ResultadoGravacao
from caos.models import (
    AgenteNome,
    Debate,
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
    Turno,
    Veto,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Subdiretório (relativo à raiz do workspace) onde os Debates são gravados.
DIR_DEBATES_RELATIVO: Path = Path("CAOS_Council/debates")

#: Mesma convenção do CouncilRecorder.
DIR_DECISIONS_RELATIVO: Path = Path("CAOS_Council/decisions")

#: Lista canônica dos 5 gatilhos de R2.1 + ``usuario`` para Debate manual.
GatilhoDebate = Literal["G1", "G2", "G3", "G4", "G5", "usuario"]

GATILHOS_VALIDOS: tuple[str, ...] = ("G1", "G2", "G3", "G4", "G5", "usuario")

#: Default do orçamento de turnos quando steering não fornecer outro
#: valor (R7.1 do Spec 1).
ORCAMENTO_TURNOS_DEFAULT: int = 12

#: Modelo default do Athena (carrega no starter para satisfazer
#: ``Debate.modelos`` exigido pelo schema). Demais modelos são
#: adicionados conforme cada agente participar.
MODELO_ATHENA_DEFAULT: str = "claude-opus-4.7"

#: Slug regex (mesmo do :class:`caos.models.Debate.titulo`).
_RE_SLUG_VALIDO = re.compile(r"^[a-z0-9-]{1,60}$")

#: Identificador AAAA-MM-DD-NN.
_RE_IDENTIFICADOR = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}$")

#: Cabeçalho de Turno — ``## Turno N — Agente (FASE)``.
_RE_TURNO_HEADER = re.compile(
    r"^##\s+Turno\s+(\d+)\s+(?:—|--)\s+([A-Za-z_]+)\s+\(([A-Z_]+)\)\s*$"
)

#: Bloco ```meta`` de Turno em frontmatter intercalado.
_RE_BLOCO_META = re.compile(
    r"^```meta\s*\n(?P<corpo>.*?)\n```\s*$",
    re.DOTALL | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Modelos públicos do módulo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlagsDebateIniciar:
    """Argumentos validados para :func:`iniciar_debate`."""

    slug: str
    titulo: Optional[str] = None
    gatilho: str = "usuario"
    altera_exposicao: bool = False
    csharp: bool = False
    raiz_workspace: Path = field(default_factory=Path.cwd)


@dataclass(frozen=True)
class FlagsDebateFechar:
    """Argumentos validados para :func:`fechar_debate`."""

    identificador: str
    dry_run: bool = False
    raiz_workspace: Path = field(default_factory=Path.cwd)


@dataclass(frozen=True)
class ResultadoIniciar:
    """Saída de :func:`iniciar_debate`."""

    caminho_debate: Path
    identificador: str
    slug: str


@dataclass(frozen=True)
class ResultadoFechar:
    """Saída de :func:`fechar_debate`."""

    caminho_debate: Path
    decisao: DecisaoDoConselho
    resultado_gravacao: Optional[ResultadoGravacao]  # ``None`` em dry-run
    dry_run: bool


# ---------------------------------------------------------------------------
# Erros tipificados
# ---------------------------------------------------------------------------


class DebateIoError(RuntimeError):
    """Erro tipificado dos helpers de Debate.

    Caller transforma em mensagem pt-BR no CLI; estrutura interna
    permanece simples para facilitar testes.
    """

    def __init__(self, categoria: str, mensagem: str) -> None:
        self.categoria = categoria
        self.mensagem = mensagem
        super().__init__(f"{categoria}: {mensagem}")


# ---------------------------------------------------------------------------
# 1. Iniciar Debate (gera starter)
# ---------------------------------------------------------------------------


def iniciar_debate(flags: FlagsDebateIniciar) -> ResultadoIniciar:
    """Cria ``CAOS_Council/debates/{AAAA-MM-DD}-{NN}-{slug}.md``.

    O frontmatter YAML resultante satisfaz o schema
    :class:`caos.models.Debate` no estado ``INICIADO``: contém ao menos
    Athena em ``agentes_participantes``, ``modelos = {Athena: ...}``,
    ``contexto_hash_sha256`` derivado do tema, ``orcamento_de_turnos``
    default 12, ``turnos_consumidos = 0``, ``fase_final = INICIADO``,
    ``status = em-andamento``.

    O gatilho e o flag ``aberto_por`` são gravados em
    ``notas_injetadas`` no formato ``gatilho:G3``/``aberto_por:auto``
    para evitar campos extras (que ``extra="forbid"`` do schema
    rejeitaria).

    Raises
    ------
    DebateIoError
        Quando ``slug`` é inválido (regex), ``gatilho`` não é canônico,
        ``raiz_workspace`` não é diretório, ou há falha de I/O.
    """
    _validar_slug(flags.slug)
    _validar_gatilho(flags.gatilho)
    raiz = _validar_raiz(flags.raiz_workspace)

    diretorio_debates = raiz / DIR_DEBATES_RELATIVO
    diretorio_debates.mkdir(parents=True, exist_ok=True)

    agora_utc = datetime.now(timezone.utc)
    identificador, sequencial = _proximo_identificador(
        diretorio_debates, agora_utc, flags.slug
    )
    titulo = (flags.titulo or flags.slug).strip().lower()
    if not _RE_SLUG_VALIDO.match(titulo):
        # ``Debate.titulo`` é o slug, não texto humano. Reduzimos para
        # slug se o usuário passou algo que não bata.
        titulo = flags.slug

    contexto_hash = _hash_contexto_inicial(flags, identificador, agora_utc)

    aberto_por = "auto" if flags.gatilho != "usuario" else "usuario"
    notas = [
        f"gatilho:{flags.gatilho}",
        f"aberto_por:{aberto_por}",
        f"altera_exposicao:{str(flags.altera_exposicao).lower()}",
        f"requer_csharp:{str(flags.csharp).lower()}",
    ]

    debate = Debate(
        identificador=identificador,
        titulo=titulo,
        data_inicio=agora_utc,
        data_fim=None,
        agentes_participantes=["Athena"],
        modelos={"Athena": MODELO_ATHENA_DEFAULT},
        contexto_hash_sha256=contexto_hash,
        notas_injetadas=notas,
        seeds={"Athena": 42},
        orcamento_de_turnos=ORCAMENTO_TURNOS_DEFAULT,
        turnos_consumidos=0,
        fase_final="INICIADO",
        status="em-andamento",
        turnos=[],
    )

    caminho = diretorio_debates / f"{identificador}-{flags.slug}.md"
    conteudo = _serializar_starter(debate, flags)
    _escrita_atomica(caminho, conteudo)
    return ResultadoIniciar(
        caminho_debate=caminho,
        identificador=identificador,
        slug=flags.slug,
    )


# ---------------------------------------------------------------------------
# 2. Fechar Debate (lê arquivo, monta Decisão, invoca CouncilRecorder)
# ---------------------------------------------------------------------------


def fechar_debate(flags: FlagsDebateFechar) -> ResultadoFechar:
    """Lê o Debate por identificador, valida, monta Decisão e (opcional) commita.

    Em ``dry_run=True``, devolve a Decisão derivada do arquivo sem
    invocar :class:`CouncilRecorder` — útil para preview sem gravar
    nem commitar.

    Em modo real, delega gravação atômica + commit Git para o recorder
    (Spec 1 — R8). O recorder também aplica
    ``caos-frozen-AAAA-MM-DD-NN`` quando ``aprovado_walk_forward=true``
    (R8.6).

    Raises
    ------
    DebateIoError
        Quando o identificador não casa o regex, o arquivo não existe,
        o frontmatter não passa pelo schema do Spec 1, ou a Decisão
        derivada exigiria ≥1 proposta mas o Debate fechou em SEM_QUORUM
        sem motivo coerente.
    """
    if not _RE_IDENTIFICADOR.match(flags.identificador):
        raise DebateIoError(
            "identificador-invalido",
            f"identificador {flags.identificador!r} não respeita AAAA-MM-DD-NN",
        )

    raiz = _validar_raiz(flags.raiz_workspace)
    caminho = _localizar_arquivo_debate(raiz, flags.identificador)
    debate = _carregar_debate(caminho)
    decisao = _montar_decisao_do_debate(debate)

    if flags.dry_run:
        return ResultadoFechar(
            caminho_debate=caminho,
            decisao=decisao,
            resultado_gravacao=None,
            dry_run=True,
        )

    recorder = CouncilRecorder(raiz_workspace=raiz)
    resultado = recorder.gravar(debate, decisao)
    return ResultadoFechar(
        caminho_debate=caminho,
        decisao=decisao,
        resultado_gravacao=resultado,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Validação de inputs do iniciar
# ---------------------------------------------------------------------------


def _validar_slug(slug: str) -> None:
    if not isinstance(slug, str) or not _RE_SLUG_VALIDO.match(slug):
        raise DebateIoError(
            "slug-invalido",
            f"slug {slug!r} deve casar regex ^[a-z0-9-]{{1,60}}$",
        )


def _validar_gatilho(gatilho: str) -> None:
    if gatilho not in GATILHOS_VALIDOS:
        raise DebateIoError(
            "gatilho-invalido",
            f"gatilho {gatilho!r} deve ser um de {list(GATILHOS_VALIDOS)}",
        )


def _validar_raiz(raiz: Path) -> Path:
    raiz_resolvida = Path(raiz).expanduser().resolve()
    if not raiz_resolvida.is_dir():
        raise DebateIoError(
            "raiz-invalida",
            f"raiz_workspace {raiz!r} não é um diretório existente",
        )
    return raiz_resolvida


# ---------------------------------------------------------------------------
# Numeração e hash do contexto
# ---------------------------------------------------------------------------


def _proximo_identificador(
    diretorio_debates: Path,
    agora_utc: datetime,
    slug: str,
) -> tuple[str, int]:
    """Devolve ``(identificador, sequencial)`` para o starter.

    Sequencial começa em 01 e incrementa para cada arquivo já existente
    no mesmo dia (independente do slug). Limite máximo: 99 (R8.1 do
    Spec 1).
    """
    dia_iso = agora_utc.strftime("%Y-%m-%d")
    sequencias_usadas: set[int] = set()
    if diretorio_debates.is_dir():
        for arquivo in diretorio_debates.iterdir():
            if not arquivo.is_file() or arquivo.suffix != ".md":
                continue
            nome = arquivo.stem  # AAAA-MM-DD-NN-slug
            if not nome.startswith(dia_iso + "-"):
                continue
            partes = nome[len(dia_iso) + 1 :].split("-", 1)
            if not partes or not partes[0].isdigit():
                continue
            sequencias_usadas.add(int(partes[0]))
    proximo = 1
    while proximo in sequencias_usadas and proximo <= 99:
        proximo += 1
    if proximo > 99:
        raise DebateIoError(
            "sequencial-esgotado",
            f"limite de 99 Debates por dia atingido em {dia_iso}",
        )
    identificador = f"{dia_iso}-{proximo:02d}"
    return identificador, proximo


def _hash_contexto_inicial(
    flags: FlagsDebateIniciar,
    identificador: str,
    agora_utc: datetime,
) -> str:
    """SHA-256 hex determinístico do tema+contexto do starter (R10.8 do Spec 1)."""
    digest = hashlib.sha256()
    digest.update(identificador.encode("utf-8"))
    digest.update(b"\n")
    digest.update(flags.slug.encode("utf-8"))
    digest.update(b"\n")
    digest.update((flags.titulo or flags.slug).encode("utf-8"))
    digest.update(b"\n")
    digest.update(flags.gatilho.encode("utf-8"))
    digest.update(b"\n")
    digest.update(str(flags.altera_exposicao).lower().encode("utf-8"))
    digest.update(b"\n")
    digest.update(str(flags.csharp).lower().encode("utf-8"))
    digest.update(b"\n")
    digest.update(agora_utc.replace(microsecond=0).isoformat().encode("utf-8"))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Serialização do starter
# ---------------------------------------------------------------------------


def _serializar_starter(debate: Debate, flags: FlagsDebateIniciar) -> str:
    """Serializa o ``Debate`` em Markdown com frontmatter YAML do Spec 1."""
    frontmatter = {
        "identificador": debate.identificador,
        "titulo": debate.titulo,
        "data_inicio": _datetime_para_iso(debate.data_inicio),
        "data_fim": _datetime_para_iso(debate.data_fim),
        "agentes_participantes": list(debate.agentes_participantes),
        "modelos": dict(debate.modelos),
        "contexto_hash_sha256": debate.contexto_hash_sha256,
        "notas_injetadas": list(debate.notas_injetadas),
        "seeds": dict(debate.seeds),
        "orcamento_de_turnos": debate.orcamento_de_turnos,
        "turnos_consumidos": debate.turnos_consumidos,
        "fase_final": debate.fase_final,
        "status": debate.status,
    }
    yaml_str = yaml.safe_dump(
        frontmatter,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
    )
    titulo_humano = (flags.titulo or flags.slug.replace("-", " "))
    corpo = (
        f"# Debate {debate.identificador} — {titulo_humano}\n"
        "\n"
        f"> Slug: `{debate.titulo}`. Aberto por: "
        f"`{'auto' if flags.gatilho != 'usuario' else 'usuario'}` "
        f"(gatilho: `{flags.gatilho}`).\n"
        "\n"
        "Os turnos abaixo serão preenchidos pelo Conselho conforme o protocolo "
        "em `.kiro/steering/protocolo-debate-no-chat.md`. Após preenchimento, "
        "execute `caos debate fechar` no cmd para gerar a Decisão e o commit "
        "Git auditável.\n"
        "\n"
        "## Turno 1 — Athena (INICIADO)\n"
        "\n"
        "```meta\n"
        f"agente: Athena\n"
        f"modelo: {MODELO_ATHENA_DEFAULT}\n"
        f"timestamp: {_datetime_para_iso(debate.data_inicio)}\n"
        "nao_deterministico: true\n"
        "status: ok\n"
        "```\n"
        "\n"
        "_Athena ainda preenche este turno._\n"
    )
    return f"---\n{yaml_str}---\n\n{corpo}"


def _datetime_para_iso(valor: Optional[datetime]) -> Optional[str]:
    if valor is None:
        return None
    sem_us = valor.replace(microsecond=0)
    iso = sem_us.isoformat()
    if sem_us.utcoffset() is not None and sem_us.utcoffset().total_seconds() == 0:
        iso = iso.replace("+00:00", "Z")
    return iso


def _escrita_atomica(caminho: Path, conteudo: str) -> None:
    """Escreve via ``.tmp`` + ``Path.replace`` (mesmo padrão do CouncilRecorder)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8", newline="\n")
    tmp.replace(caminho)


# ---------------------------------------------------------------------------
# Localização e parsing do arquivo de Debate
# ---------------------------------------------------------------------------


def _localizar_arquivo_debate(raiz: Path, identificador: str) -> Path:
    diretorio = raiz / DIR_DEBATES_RELATIVO
    if not diretorio.is_dir():
        raise DebateIoError(
            "diretorio-debates-ausente",
            f"diretório {diretorio} não existe; rode 'caos init' primeiro",
        )
    candidatos = sorted(
        p for p in diretorio.glob(f"{identificador}-*.md") if p.is_file()
    )
    if not candidatos:
        raise DebateIoError(
            "debate-nao-encontrado",
            f"nenhum arquivo {identificador}-*.md em {diretorio}",
        )
    if len(candidatos) > 1:
        nomes = ", ".join(c.name for c in candidatos)
        raise DebateIoError(
            "debate-ambiguo",
            f"múltiplos arquivos para identificador {identificador}: {nomes}",
        )
    return candidatos[0]


def _carregar_debate(caminho: Path) -> Debate:
    """Lê arquivo do Debate, valida o frontmatter via Pydantic e parsea turnos.

    A função aceita o starter (apenas com Turno 1 placeholder da Athena)
    e Debates já preenchidos pelo Kiro_Brain. Quando um turno tiver
    bloco ``conteudo_markdown``, ele é atribuído ao campo
    ``conteudo_markdown`` do :class:`Turno`.
    """
    import frontmatter  # type: ignore[import]

    try:
        post = frontmatter.load(str(caminho))
    except Exception as exc:
        raise DebateIoError(
            "frontmatter-malformado",
            f"falha ao ler {caminho}: {type(exc).__name__}: {exc}",
        ) from exc

    metadata = dict(post.metadata or {})
    corpo = post.content or ""
    turnos = _parsear_turnos(corpo)

    # Se nenhum turno foi parseado (starter sem preenchimento) ou o
    # frontmatter já lista turnos_consumidos > 0, usamos a contagem do
    # frontmatter para o schema. ``turnos`` no schema é literal — só
    # incluímos os parseáveis.
    payload = dict(metadata)
    payload["turnos"] = [t.model_dump(mode="json") for t in turnos]
    try:
        debate = Debate.model_validate(payload)
    except ValidationError as exc:
        raise DebateIoError(
            "frontmatter-invalido",
            f"frontmatter de {caminho} não passa pelo schema Debate: {exc}",
        ) from exc
    return debate


def _parsear_turnos(corpo: str) -> List[Turno]:
    """Extrai turnos do corpo Markdown.

    Percorre linhas procurando cabeçalhos ``## Turno N — Agente (FASE)``;
    para cada cabeçalho captura o bloco ``meta`` YAML imediatamente
    abaixo e o texto livre até o próximo cabeçalho ou final do arquivo.
    """
    linhas = corpo.splitlines()
    turnos: List[Turno] = []
    i = 0
    while i < len(linhas):
        m = _RE_TURNO_HEADER.match(linhas[i])
        if not m:
            i += 1
            continue
        numero = int(m.group(1))
        agente = m.group(2)
        fase = m.group(3)

        # Procura bloco ```meta``` nas próximas linhas (até 5).
        meta_dict: dict[str, Any] = {}
        j = i + 1
        # Pula linhas em branco até encontrar abertura do bloco.
        while j < len(linhas) and not linhas[j].lstrip().startswith("```meta"):
            if linhas[j].strip().startswith("## Turno"):
                break  # próximo turno antes do meta — turno mal formado
            j += 1
        if j < len(linhas) and linhas[j].lstrip().startswith("```meta"):
            # Lê até fechamento.
            k = j + 1
            buffer: list[str] = []
            while k < len(linhas) and linhas[k].strip() != "```":
                buffer.append(linhas[k])
                k += 1
            try:
                meta_dict = yaml.safe_load("\n".join(buffer)) or {}
            except yaml.YAMLError:
                meta_dict = {}
            # Captura corpo até o próximo "## Turno" ou EOF.
            l = k + 1
            corpo_inicio = l
            while l < len(linhas) and not linhas[l].startswith("## Turno"):
                l += 1
            conteudo = "\n".join(linhas[corpo_inicio:l]).strip() or None
            i = l
        else:
            # Sem bloco meta válido — turno é placeholder.
            conteudo = None
            i = j

        # Monta Turno via Pydantic, extraindo defaults seguros.
        timestamp = meta_dict.get("timestamp")
        if isinstance(timestamp, datetime):
            ts = timestamp
        else:
            try:
                ts = datetime.fromisoformat(
                    str(timestamp).replace("Z", "+00:00")
                ) if timestamp else datetime.now(timezone.utc)
            except (TypeError, ValueError):
                ts = datetime.now(timezone.utc)
        try:
            turno = Turno(
                numero=numero,
                agente=agente,  # type: ignore[arg-type]
                modelo=meta_dict.get("modelo") or MODELO_ATHENA_DEFAULT,
                timestamp=ts,
                fase=fase,  # type: ignore[arg-type]
                nao_deterministico=bool(meta_dict.get("nao_deterministico", True)),
                status=meta_dict.get("status", "ok"),
                conteudo_markdown=conteudo,
            )
        except ValidationError as exc:
            raise DebateIoError(
                "turno-invalido",
                f"turno {numero} ({agente}/{fase}) não passa pelo schema Turno: {exc}",
            ) from exc
        turnos.append(turno)
    return turnos


# ---------------------------------------------------------------------------
# Montagem da Decisão
# ---------------------------------------------------------------------------


def _montar_decisao_do_debate(debate: Debate) -> DecisaoDoConselho:
    """Constrói :class:`DecisaoDoConselho` a partir dos turnos do Debate.

    Para o caminho atual do Spec 5, exigimos que o Kiro_Brain tenha
    preenchido manualmente em algum turno SINTESE da Athena um bloco
    YAML ``decisao`` com os campos: ``proposta_aceita``, ``rationale``,
    ``links_zettel``, ``aprovado_walk_forward``, ``reproduzivel``,
    ``regressao_detectada``, ``status``. Também extraímos propostas e
    vetos de blocos YAML análogos (``proposta`` em turnos PROPOSTAS;
    ``veto`` em turnos AVALIACAO_RISCO/AVALIACAO_TECNICA).

    Em uma primeira iteração, fail-soft: se o Kiro_Brain não preencheu
    todos os blocos, a função usa heurísticas conservadoras (proposta
    aceita = ``None``, ``aprovado_walk_forward=False``, status =
    ``pendente-usuario``) e levanta erro só quando o schema obrigatório
    (≥ 1 proposta, ≥ 1 link Zettel, rationale não vazio) não puder ser
    satisfeito.
    """
    propostas = _extrair_propostas(debate)
    vetos = _extrair_vetos(debate)
    decisao_final, links, aprovado, reproduzivel, regressao, status = (
        _extrair_sintese(debate)
    )

    if not propostas:
        # Sem propostas, a Decisão violaria o schema (≥ 1). Devolvemos
        # erro tipificado para que o caller sinalize ao usuário que o
        # Debate fechou em SEM_QUORUM ou que a Athena precisa preencher
        # o bloco ``proposta`` em turnos PROPOSTAS antes de fechar.
        raise DebateIoError(
            "sem-propostas",
            "Debate não tem propostas extraíveis. Preencha bloco ```proposta "
            "no(s) turno(s) PROPOSTAS antes de fechar, ou aceite que o Debate "
            "fechou em SEM_QUORUM (não pode gerar Decisão).",
        )

    if not links:
        # Pelo menos 1 link Zettel é obrigatório (R8.2 do Spec 1).
        raise DebateIoError(
            "sem-links-zettel",
            "DecisaoDoConselho exige >= 1 link Zettel. Preencha "
            "``links_zettel`` no bloco ```sintese do turno SINTESE da Athena.",
        )

    # Compila lista única e ordenada de agentes participantes.
    agentes = sorted(set(debate.agentes_participantes) | {t.agente for t in debate.turnos})

    try:
        decisao = DecisaoDoConselho(
            identificador=debate.identificador,
            debate_relacionado=f"{debate.identificador}-{debate.titulo}.md",
            agentes_participantes=list(agentes),
            propostas=propostas,
            vetos=vetos,
            decisao_final=decisao_final,
            links_zettel=links,
            aprovado_walk_forward=aprovado,
            reproduzivel=reproduzivel,
            regressao_detectada=regressao,
            status=status,
        )
    except ValidationError as exc:
        raise DebateIoError(
            "decisao-invalida",
            f"Decisão derivada não passa pelo schema DecisaoDoConselho: {exc}",
        ) from exc
    return decisao


# ---------------------------------------------------------------------------
# Extração de Propostas / Vetos / Síntese a partir dos turnos
# ---------------------------------------------------------------------------


_RE_BLOCO_NOMEADO = re.compile(
    r"^```(?P<nome>proposta|veto|sintese)\s*\n(?P<corpo>.*?)\n```\s*$",
    re.DOTALL | re.MULTILINE,
)


def _extrair_blocos_yaml_do_turno(turno: Turno, nome: str) -> List[dict[str, Any]]:
    """Extrai blocos ```<nome>... ```yaml... ``` do ``conteudo_markdown``.

    O Kiro_Brain emite blocos nomeados (ex: ``proposta``, ``veto``,
    ``sintese``) dentro do conteúdo Markdown de cada turno; este helper
    devolve a lista de dicts YAML parseados.
    """
    if not turno.conteudo_markdown:
        return []
    resultados: List[dict[str, Any]] = []
    pattern = re.compile(
        rf"^```{nome}\s*\n(?P<corpo>.*?)\n```\s*$",
        re.DOTALL | re.MULTILINE,
    )
    for match in pattern.finditer(turno.conteudo_markdown):
        try:
            payload = yaml.safe_load(match.group("corpo")) or {}
        except yaml.YAMLError:
            continue
        if isinstance(payload, dict):
            resultados.append(payload)
    return resultados


def _extrair_propostas(debate: Debate) -> List[Proposta]:
    propostas: List[Proposta] = []
    contador = 1
    for turno in debate.turnos:
        if turno.fase != "PROPOSTAS":
            continue
        for bloco in _extrair_blocos_yaml_do_turno(turno, "proposta"):
            payload = dict(bloco)
            payload.setdefault("autor", turno.agente)
            payload.setdefault("id", f"P{contador}")
            try:
                proposta = Proposta(**payload)
            except ValidationError as exc:
                raise DebateIoError(
                    "proposta-invalida",
                    f"bloco ```proposta no turno {turno.numero} é inválido: {exc}",
                ) from exc
            propostas.append(proposta)
            contador += 1
    return propostas


def _extrair_vetos(debate: Debate) -> List[Veto]:
    vetos: List[Veto] = []
    for turno in debate.turnos:
        if turno.fase not in ("AVALIACAO_RISCO", "AVALIACAO_TECNICA"):
            continue
        for bloco in _extrair_blocos_yaml_do_turno(turno, "veto"):
            payload = dict(bloco)
            payload.setdefault("autor", turno.agente)
            try:
                veto = Veto(**payload)
            except ValidationError as exc:
                raise DebateIoError(
                    "veto-invalido",
                    f"bloco ```veto no turno {turno.numero} é inválido: {exc}",
                ) from exc
            vetos.append(veto)
    return vetos


def _extrair_sintese(
    debate: Debate,
) -> tuple[
    DecisaoFinal,
    List[str],
    bool,
    Literal["true", "parcial", "false"],
    bool,
    str,
]:
    """Devolve ``(decisao_final, links_zettel, aprovado, reproduzivel, regressao, status)``.

    Procura blocos ```sintese em turnos SINTESE da Athena. Quando não
    há síntese, devolve defaults conservadores que ainda satisfazem
    o schema (``aprovado_walk_forward=false``,
    ``reproduzivel="parcial"``, ``status="pendente-usuario"``,
    ``rationale="<sem-sintese>"``).
    """
    rationale = "<sem-sintese>"
    proposta_aceita: Optional[str] = None
    links: List[str] = []
    aprovado = False
    reproduzivel: Literal["true", "parcial", "false"] = "parcial"
    regressao = False
    status: str = "pendente-usuario"

    for turno in debate.turnos:
        if turno.fase != "SINTESE":
            continue
        if turno.agente != "Athena":
            continue
        blocos = _extrair_blocos_yaml_do_turno(turno, "sintese")
        if not blocos:
            continue
        bloco = blocos[-1]  # última síntese da Athena vence
        rationale = str(bloco.get("rationale", rationale)).strip() or rationale
        proposta_aceita = bloco.get("proposta_aceita")
        if proposta_aceita is not None:
            proposta_aceita = str(proposta_aceita).strip() or None
        links = list(bloco.get("links_zettel", []) or [])
        aprovado = bool(bloco.get("aprovado_walk_forward", False))
        reproduzivel = bloco.get("reproduzivel", reproduzivel) or reproduzivel
        regressao = bool(bloco.get("regressao_detectada", False))
        status = bloco.get("status", status) or status

    decisao_final = DecisaoFinal(
        proposta_aceita=proposta_aceita,
        rationale=rationale,
    )
    return decisao_final, links, aprovado, reproduzivel, regressao, status


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


__all__ = [
    "DIR_DEBATES_RELATIVO",
    "DIR_DECISIONS_RELATIVO",
    "GATILHOS_VALIDOS",
    "GatilhoDebate",
    "MODELO_ATHENA_DEFAULT",
    "ORCAMENTO_TURNOS_DEFAULT",
    "DebateIoError",
    "FlagsDebateFechar",
    "FlagsDebateIniciar",
    "ResultadoFechar",
    "ResultadoIniciar",
    "fechar_debate",
    "iniciar_debate",
]
