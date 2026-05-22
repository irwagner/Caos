"""Council_Recorder — gravação auditada de Debates e Decisões do Conselho.

Este módulo implementa a Task 10 do Spec ``caos-conselho-infra`` cobrindo
R8.1–R8.7 do ``requirements.md``:

- Grava o arquivo de Debate em
  ``CAOS_Council/debates/AAAA-MM-DD-NN-titulo.md`` e o arquivo de
  ``Decisao_Do_Conselho`` em ``CAOS_Council/decisions/...`` usando os
  schemas YAML da seção 3 do ``design.md``.
- Valida campos obrigatórios; aborta a gravação com erro tipificado se
  faltarem (com a única exceção da lista de vetos, que pode ser vazia
  por R8.2).
- Após a gravação bem-sucedida, cria um commit dedicado contendo
  exclusivamente o par debate + decisão via :class:`SkillGit`. A
  mensagem segue o padrão ``[CAOS] AAAA-MM-DD-NN slug-titulo`` (R8.4).
- Quando ``aprovado_walk_forward == True``, aplica a tag
  ``caos-frozen-AAAA-MM-DD-NN`` (R8.6). Tag pré-existente é tratada
  como colisão e a tag não é sobrescrita (R8.7).
- Em qualquer falha de Git, os arquivos permanecem no disco para
  preservar a evidência humana (R8.5).

Convenções:

- Escrita de arquivo é atômica via ``arquivo.tmp`` + ``Path.replace``.
- Todas as mensagens visíveis ao usuário estão em pt-BR.
- Datas em UTC são serializadas como ISO 8601 com sufixo ``Z``; datas
  com offset arbitrário preservam o offset.
- A ordem das chaves no frontmatter YAML é alfabética
  (``yaml.safe_dump(..., sort_keys=True)``) — o que torna a
  serialização idempotente entre execuções e estável diante de
  reordenações eventuais nos modelos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import yaml

from caos.models import Debate, DecisaoDoConselho, Turno
from caos.skills.git import ResultadoGit, SkillGit

# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Subdiretório (relativo à raiz do workspace) onde os Debates são gravados.
DIR_DEBATES: str = "CAOS_Council/debates"

#: Subdiretório (relativo à raiz do workspace) onde as Decisões são gravadas.
DIR_DECISIONS: str = "CAOS_Council/decisions"

#: Prefixo de Tag_De_Congelamento (R8.6).
PREFIXO_TAG_CONGELAMENTO: str = "caos-frozen-"

# ---------------------------------------------------------------------------
# Regex de validação
# ---------------------------------------------------------------------------

#: Identificador AAAA-MM-DD-NN (R8.1).
_RE_IDENTIFICADOR = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}$")

#: Slug do título: kebab-case, 1–60 caracteres ASCII (R4.1, R8.1).
_RE_SLUG_VALIDO = re.compile(r"^[a-z0-9-]{1,60}$")


# ---------------------------------------------------------------------------
# Modelos de resultado
# ---------------------------------------------------------------------------


CategoriaFalhaGravacao = Literal[
    "campo-obrigatorio-vazio",
    "identificador-invalido",
    "titulo-invalido",
    "io-erro",
    "git-commit-falhou",
    "git-tag-colisao",
]


@dataclass(frozen=True)
class FalhaGravacao:
    """Descrição estruturada de uma falha de gravação.

    ``categoria`` é o discriminador estável que o orquestrador usa para
    decidir como reagir. ``mensagem`` é texto livre em pt-BR adequado
    para exibição ao usuário. ``detalhes`` carrega contexto adicional
    (exit_code, stderr truncado, nome de tag, etc.) e é opcional.
    """

    categoria: CategoriaFalhaGravacao
    mensagem: str
    detalhes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoGravacao:
    """Resultado de :meth:`CouncilRecorder.gravar`.

    Quando ``falha`` é ``None``, ``commit_realizado`` é ``True`` e
    ``commit_sha`` carrega o SHA-1 hex (40 chars) do commit dedicado.
    Quando ``aprovado_walk_forward`` é verdadeiro, ``tag_aplicada``
    contém o nome da tag (``caos-frozen-AAAA-MM-DD-NN``).

    Em todas as falhas, os caminhos ``caminho_debate`` e
    ``caminho_decisao`` apontam para os arquivos no disco (preservados
    por R8.5) — o chamador pode inspecioná-los para diagnóstico.
    """

    caminho_debate: Path
    caminho_decisao: Path
    commit_realizado: bool
    commit_sha: Optional[str]
    tag_aplicada: Optional[str]
    falha: Optional[FalhaGravacao] = None

    @property
    def sucesso(self) -> bool:
        """``True`` se a gravação concluiu sem falhas."""
        return self.falha is None


# ---------------------------------------------------------------------------
# Funções utilitárias
# ---------------------------------------------------------------------------


def _slug_do_titulo(titulo: str) -> str:
    """Converte um título arbitrário em um slug kebab-case válido.

    - Se ``titulo`` já está em ``[a-z0-9-]{1,60}``, é retornado como está.
    - Caso contrário, é normalizado: ``lower()``, qualquer sequência de
      caracteres fora de ``[a-z0-9]`` vira ``-``, hifens consecutivos
      são colapsados em um, hifens nas pontas são removidos e o
      resultado é truncado a 60 caracteres.

    Slugs vazios (após normalização) caem fora do regex e são
    detectados como ``titulo-invalido`` por :meth:`CouncilRecorder.gravar`.
    """
    if _RE_SLUG_VALIDO.match(titulo):
        return titulo
    s = titulo.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s[:60]


def _datetime_para_iso(valor: Optional[datetime]) -> Optional[str]:
    """Serializa ``datetime`` em ISO 8601 estável.

    Mantém ``Z`` para UTC e o offset explícito para outros fusos. Para
    consistência (e idempotência da gravação), microssegundos são
    descartados — o protocolo do Debate registra horários ao segundo.
    """
    if valor is None:
        return None
    sem_us = valor.replace(microsecond=0)
    iso = sem_us.isoformat()
    # Normaliza UTC para o sufixo 'Z' (mais compacto e legível).
    if sem_us.utcoffset() == timedelta(0):
        iso = iso.replace("+00:00", "Z")
    return iso


def _escrita_atomica(caminho: Path, conteudo: str) -> None:
    """Escreve ``conteudo`` em ``caminho`` de forma atômica.

    A estratégia é a mesma usada em :mod:`caos.data_manifest` e
    :mod:`caos.skills.token_budget`:

    1. Cria o diretório-pai se necessário.
    2. Escreve em ``caminho.tmp`` com newline ``\\n`` explícito (para
       respeitar a normalização CRLF→LF do R9.3 mesmo em Windows).
    3. Faz ``Path.replace`` para promover o arquivo final, operação
       atômica em sistemas POSIX e em NTFS para o mesmo volume.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    # newline="\n" instrui o Python a NÃO traduzir LF→CRLF em Windows.
    tmp.write_text(conteudo, encoding="utf-8", newline="\n")
    tmp.replace(caminho)


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class CouncilRecorder:
    """Persistência auditada de Debate + Decisao_Do_Conselho.

    Parameters
    ----------
    raiz_workspace:
        Diretório-raiz do workspace CAOS (onde reside ``CAOS_Council/``).
        O construtor garante que os subdiretórios ``debates/`` e
        ``decisions/`` existam.
    skill_git:
        Instância de :class:`SkillGit` a ser usada para os commits e
        tags. Se ``None``, é instanciada com ``repo_dir=raiz_workspace``.
        Aceitar um ``skill_git`` injetado é o ponto de extensão usado
        pelos testes para forçar falhas determinísticas de Git.
    """

    def __init__(
        self,
        *,
        raiz_workspace: Path,
        skill_git: Optional[SkillGit] = None,
    ) -> None:
        raiz = Path(raiz_workspace).expanduser().resolve()
        if not raiz.is_dir():
            raise ValueError(
                "raiz_workspace deve apontar para um diretório existente; "
                f"recebido {raiz_workspace!r}"
            )
        # Garantir CAOS_Council/{debates,decisions} sem destruir conteúdo.
        (raiz / DIR_DEBATES).mkdir(parents=True, exist_ok=True)
        (raiz / DIR_DECISIONS).mkdir(parents=True, exist_ok=True)
        self._raiz = raiz
        self._skill_git: SkillGit = (
            skill_git
            if skill_git is not None
            else SkillGit(repo_dir=raiz, invocador="Council_Recorder")
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    @property
    def raiz_workspace(self) -> Path:
        """Raiz absoluta resolvida do workspace."""
        return self._raiz

    @property
    def skill_git(self) -> SkillGit:
        """Instância de ``SkillGit`` usada pelas operações de auditoria."""
        return self._skill_git

    def gravar(
        self, debate: Debate, decisao: DecisaoDoConselho
    ) -> ResultadoGravacao:
        """Persiste o par ``(debate, decisao)`` e cria o commit dedicado.

        O fluxo, em ordem:

        1. Validação cruzada: ``debate.identificador == decisao.identificador``
           (R8.1) e formato ``AAAA-MM-DD-NN``.
        2. Validação de campos obrigatórios da decisão (R8.2/R8.3); a
           lista de vetos pode ser vazia.
        3. Derivação do slug a partir de ``debate.titulo``.
        4. Construção dos caminhos
           ``CAOS_Council/(debates|decisions)/{identificador}-{slug}.md``.
        5. Serialização determinística + escrita atômica.
        6. ``git add`` dos dois arquivos + ``git commit -m "[CAOS] ..."``
           (R8.4) → captura do SHA via ``git log -1 --pretty=%H``.
        7. Quando ``aprovado_walk_forward``, verifica a colisão de tag
           via ``git tag -l <nome>`` e, se livre, aplica
           ``git tag <nome>`` (R8.6/R8.7).
        """
        # ----- 1. Identificadores -----
        falha_id = self._validar_identificadores(debate, decisao)
        if falha_id is not None:
            # Antes de qualquer escrita: nada no disco para reportar.
            caminho_debate, caminho_decisao = self._caminhos_para(
                debate.identificador or "indefinido", "indefinido"
            )
            return ResultadoGravacao(
                caminho_debate=caminho_debate,
                caminho_decisao=caminho_decisao,
                commit_realizado=False,
                commit_sha=None,
                tag_aplicada=None,
                falha=falha_id,
            )

        # ----- 2. Campos obrigatórios -----
        falha_obrig = self._validar_obrigatorios(decisao)
        if falha_obrig is not None:
            caminho_debate, caminho_decisao = self._caminhos_para(
                debate.identificador,
                _slug_do_titulo(debate.titulo or "indefinido"),
            )
            return ResultadoGravacao(
                caminho_debate=caminho_debate,
                caminho_decisao=caminho_decisao,
                commit_realizado=False,
                commit_sha=None,
                tag_aplicada=None,
                falha=falha_obrig,
            )

        # ----- 3. Slug -----
        slug = _slug_do_titulo(debate.titulo)
        if not _RE_SLUG_VALIDO.match(slug):
            caminho_debate, caminho_decisao = self._caminhos_para(
                debate.identificador, slug or "indefinido"
            )
            return ResultadoGravacao(
                caminho_debate=caminho_debate,
                caminho_decisao=caminho_decisao,
                commit_realizado=False,
                commit_sha=None,
                tag_aplicada=None,
                falha=FalhaGravacao(
                    categoria="titulo-invalido",
                    mensagem=(
                        f"título {debate.titulo!r} não pôde ser convertido "
                        "em um slug válido (regex ^[a-z0-9-]{1,60}$)"
                    ),
                    detalhes={"titulo": debate.titulo, "slug_obtido": slug},
                ),
            )

        # ----- 4. Caminhos -----
        caminho_debate, caminho_decisao = self._caminhos_para(
            debate.identificador, slug
        )

        # ----- 5. Serialização + escrita atômica -----
        try:
            conteudo_debate = self._serializar_debate(debate)
            conteudo_decisao = self._serializar_decisao(decisao)
            _escrita_atomica(caminho_debate, conteudo_debate)
            _escrita_atomica(caminho_decisao, conteudo_decisao)
        except OSError as exc:
            return ResultadoGravacao(
                caminho_debate=caminho_debate,
                caminho_decisao=caminho_decisao,
                commit_realizado=False,
                commit_sha=None,
                tag_aplicada=None,
                falha=FalhaGravacao(
                    categoria="io-erro",
                    mensagem=f"falha de I/O ao gravar arquivos: {exc}",
                    detalhes={"erro": str(exc)},
                ),
            )

        # ----- 6. Git commit -----
        rel_debate = caminho_debate.relative_to(self._raiz).as_posix()
        rel_decisao = caminho_decisao.relative_to(self._raiz).as_posix()

        # git add — usamos '--' para isolar caminhos de eventuais flags.
        for rel in (rel_debate, rel_decisao):
            res_add = self._skill_git.executar("add", "--", rel)
            if res_add.exit_code != 0:
                return ResultadoGravacao(
                    caminho_debate=caminho_debate,
                    caminho_decisao=caminho_decisao,
                    commit_realizado=False,
                    commit_sha=None,
                    tag_aplicada=None,
                    falha=FalhaGravacao(
                        categoria="git-commit-falhou",
                        mensagem=(
                            f"git add {rel!r} falhou: "
                            f"exit_code={res_add.exit_code}"
                        ),
                        detalhes={
                            "etapa": "git-add",
                            "caminho": rel,
                            "exit_code": res_add.exit_code,
                            "stderr": res_add.stderr[:1024],
                        },
                    ),
                )

        msg_commit = f"[CAOS] {debate.identificador} {slug}"
        res_commit = self._skill_git.executar("commit", "-m", msg_commit)
        if res_commit.exit_code != 0:
            return ResultadoGravacao(
                caminho_debate=caminho_debate,
                caminho_decisao=caminho_decisao,
                commit_realizado=False,
                commit_sha=None,
                tag_aplicada=None,
                falha=FalhaGravacao(
                    categoria="git-commit-falhou",
                    mensagem=(
                        "git commit dedicado falhou: "
                        f"exit_code={res_commit.exit_code}"
                    ),
                    detalhes={
                        "etapa": "git-commit",
                        "identificador": debate.identificador,
                        "exit_code": res_commit.exit_code,
                        "stderr": res_commit.stderr[:1024],
                    },
                ),
            )

        commit_sha = self._obter_sha_commit_corrente()

        # ----- 7. Tag (apenas se aprovado_walk_forward) -----
        tag_aplicada: Optional[str] = None
        if decisao.aprovado_walk_forward:
            nome_tag = f"{PREFIXO_TAG_CONGELAMENTO}{debate.identificador}"
            falha_tag = self._aplicar_tag_se_livre(nome_tag)
            if falha_tag is not None:
                return ResultadoGravacao(
                    caminho_debate=caminho_debate,
                    caminho_decisao=caminho_decisao,
                    commit_realizado=True,
                    commit_sha=commit_sha,
                    tag_aplicada=None,
                    falha=falha_tag,
                )
            tag_aplicada = nome_tag

        return ResultadoGravacao(
            caminho_debate=caminho_debate,
            caminho_decisao=caminho_decisao,
            commit_realizado=True,
            commit_sha=commit_sha,
            tag_aplicada=tag_aplicada,
            falha=None,
        )

    def delete_debates_e_decisoes(self) -> None:
        """Remove todos os arquivos sob ``CAOS_Council/(debates|decisions)``.

        Helper estritamente para testes que precisam reciclar o estado do
        recorder dentro de um mesmo processo. Não toca em ``.git`` nem em
        nenhum outro caminho fora desses dois subdiretórios.
        """
        for subdir in (DIR_DEBATES, DIR_DECISIONS):
            base = self._raiz / subdir
            if not base.is_dir():
                continue
            for arquivo in base.iterdir():
                if arquivo.is_file():
                    arquivo.unlink()

    # ------------------------------------------------------------------
    # Validações internas
    # ------------------------------------------------------------------

    @staticmethod
    def _validar_identificadores(
        debate: Debate, decisao: DecisaoDoConselho
    ) -> Optional[FalhaGravacao]:
        """Verifica a coerência dos identificadores entre debate e decisão.

        Retorna ``None`` em sucesso, ou uma :class:`FalhaGravacao` da
        categoria ``identificador-invalido`` com detalhes do problema.
        """
        if debate.identificador != decisao.identificador:
            return FalhaGravacao(
                categoria="identificador-invalido",
                mensagem=(
                    "identificador do debate "
                    f"({debate.identificador!r}) difere do identificador da "
                    f"decisão ({decisao.identificador!r})"
                ),
                detalhes={
                    "debate": debate.identificador,
                    "decisao": decisao.identificador,
                },
            )
        for rotulo, valor in (
            ("debate", debate.identificador),
            ("decisao", decisao.identificador),
        ):
            if not isinstance(valor, str) or not _RE_IDENTIFICADOR.match(valor):
                return FalhaGravacao(
                    categoria="identificador-invalido",
                    mensagem=(
                        f"identificador do {rotulo} ({valor!r}) não respeita "
                        "o formato AAAA-MM-DD-NN"
                    ),
                    detalhes={"identificador": valor, "origem": rotulo},
                )
        return None

    @staticmethod
    def _validar_obrigatorios(
        decisao: DecisaoDoConselho,
    ) -> Optional[FalhaGravacao]:
        """Garante que campos obrigatórios estão preenchidos (R8.2/R8.3).

        A lista ``vetos`` é deliberadamente excluída — pode ser vazia.
        Reaplicar essas verificações aqui (mesmo que os modelos Pydantic
        já as façam) blinda o recorder contra objetos construídos via
        ``model_construct`` ou mutados após a validação inicial.
        """
        erros: list[str] = []
        if not decisao.propostas:
            erros.append("propostas")
        if not decisao.links_zettel:
            erros.append("links_zettel")
        if not decisao.agentes_participantes:
            erros.append("agentes_participantes")
        rationale = (decisao.decisao_final.rationale or "").strip()
        if not rationale:
            erros.append("decisao_final.rationale")
        if erros:
            return FalhaGravacao(
                categoria="campo-obrigatorio-vazio",
                mensagem=(
                    "campos obrigatórios da Decisao_Do_Conselho ausentes ou "
                    f"vazios: {', '.join(erros)}"
                ),
                detalhes={"campos": erros},
            )
        return None

    # ------------------------------------------------------------------
    # Caminhos
    # ------------------------------------------------------------------

    def _caminhos_para(
        self, identificador: str, slug: str
    ) -> tuple[Path, Path]:
        """Devolve os caminhos absolutos do arquivo de debate e da decisão."""
        nome_arquivo = f"{identificador}-{slug}.md"
        caminho_debate = self._raiz / DIR_DEBATES / nome_arquivo
        caminho_decisao = self._raiz / DIR_DECISIONS / nome_arquivo
        return caminho_debate, caminho_decisao

    # ------------------------------------------------------------------
    # Serialização (públicos via testes; prefixo "_" indica uso interno)
    # ------------------------------------------------------------------

    def _serializar_debate(self, debate: Debate) -> str:
        """Serializa o ``Debate`` em Markdown com frontmatter YAML.

        Frontmatter inclui todos os campos do cabeçalho descritos em
        ``design.md`` 3.3. O corpo enumera os turnos em ordem
        sequencial: cada turno fica em um ``## Turno N — Agente
        (FASE)`` seguido por um bloco ```meta``` com os campos
        operacionais e, opcionalmente, pelo ``conteudo_markdown``.
        """
        frontmatter: dict[str, Any] = {
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
        corpo = self._renderizar_turnos(debate.turnos)
        # Linha em branco final preserva idempotência sob append-on-write.
        return f"---\n{yaml_str}---\n\n{corpo}"

    @staticmethod
    def _renderizar_turnos(turnos: Iterable[Turno]) -> str:
        """Renderiza a lista de turnos do Debate como Markdown."""
        partes: list[str] = []
        for turno in turnos:
            partes.append(
                f"## Turno {turno.numero} — {turno.agente} ({turno.fase})\n"
            )
            meta: dict[str, Any] = {
                "agente": turno.agente,
                "modelo": turno.modelo,
                "timestamp": _datetime_para_iso(turno.timestamp),
                "nao_deterministico": turno.nao_deterministico,
                "status": turno.status,
            }
            if turno.contexto_hash_sha256 is not None:
                meta["contexto_hash_sha256"] = turno.contexto_hash_sha256
            if turno.notas_injetadas:
                meta["notas_injetadas"] = list(turno.notas_injetadas)
            if turno.cache_hit is not None:
                meta["cache_hit"] = turno.cache_hit
            yaml_meta = yaml.safe_dump(
                meta,
                sort_keys=True,
                allow_unicode=True,
                default_flow_style=False,
            )
            partes.append("```meta\n" + yaml_meta + "```\n")
            if turno.conteudo_markdown:
                partes.append(turno.conteudo_markdown.rstrip() + "\n")
            partes.append("")  # linha em branco entre turnos
        # Mesmo sem turnos (Debate em fase inicial) deixamos uma string
        # vazia — o frontmatter sozinho ainda é Markdown válido.
        return "\n".join(partes).rstrip() + "\n" if partes else ""

    def _serializar_decisao(self, decisao: DecisaoDoConselho) -> str:
        """Serializa a ``DecisaoDoConselho`` em Markdown com frontmatter YAML.

        ``model_dump(mode='json')`` dos sub-modelos é usado para garantir
        que ``datetime``, ``Enum`` e demais tipos se tornem strings/ints
        válidos para YAML. ``exclude_none=True`` em ``vetos`` mantém o
        bloco enxuto (omite ``categoria_tecnica`` em vetos de risco, por
        exemplo).
        """
        frontmatter: dict[str, Any] = {
            "identificador": decisao.identificador,
            "debate_relacionado": decisao.debate_relacionado,
            "agentes_participantes": list(decisao.agentes_participantes),
            "propostas": [
                p.model_dump(mode="json") for p in decisao.propostas
            ],
            "vetos": [
                v.model_dump(mode="json", exclude_none=True)
                for v in decisao.vetos
            ],
            "decisao_final": {
                "proposta_aceita": decisao.decisao_final.proposta_aceita,
                "rationale": decisao.decisao_final.rationale,
            },
            "links_zettel": list(decisao.links_zettel),
            "aprovado_walk_forward": decisao.aprovado_walk_forward,
            "reproduzivel": decisao.reproduzivel,
            "regressao_detectada": decisao.regressao_detectada,
            "status": decisao.status,
        }
        yaml_str = yaml.safe_dump(
            frontmatter,
            sort_keys=True,
            allow_unicode=True,
            default_flow_style=False,
        )
        corpo = (
            "# Síntese final\n\n"
            + decisao.decisao_final.rationale.rstrip()
            + "\n"
        )
        return f"---\n{yaml_str}---\n\n{corpo}"

    # ------------------------------------------------------------------
    # Operações de Git
    # ------------------------------------------------------------------

    def _obter_sha_commit_corrente(self) -> Optional[str]:
        """Retorna o SHA-1 hex do commit em ``HEAD`` ou ``None`` em falha.

        Usa ``git log -1 --pretty=%H`` (todos os tokens estão na whitelist
        do Skill_Git). Falhas aqui não invalidam a gravação — o commit já
        foi feito; o SHA é uma informação adicional para rastreio.
        """
        res = self._skill_git.executar("log", "-1", "--pretty=%H")
        if res.exit_code != 0:
            return None
        sha = res.stdout.strip()
        # Sanidade: SHA-1 hex tem 40 chars; SHA-256 hex tem 64.
        if not (7 <= len(sha) <= 64) or not all(
            c in "0123456789abcdef" for c in sha.lower()
        ):
            return None
        return sha

    def _aplicar_tag_se_livre(self, nome_tag: str) -> Optional[FalhaGravacao]:
        """Aplica ``nome_tag`` em ``HEAD`` se ainda não existir.

        Retorna ``None`` em sucesso. Em colisão, retorna falha
        ``git-tag-colisao``; em erro de execução do comando ``git tag``,
        também retorna ``git-tag-colisao`` com detalhes da causa
        (mantemos a categoria única para que o orquestrador trate
        ambos os casos como "tag não foi aplicada"; ``detalhes`` carrega
        o discriminador real).
        """
        # Verificação prévia: 'git tag -l <nome>' lista tags casando o nome.
        res_check = self._skill_git.executar("tag", "-l", nome_tag)
        if res_check.exit_code != 0:
            return FalhaGravacao(
                categoria="git-tag-colisao",
                mensagem=(
                    f"falha ao consultar existência da tag {nome_tag!r}: "
                    f"exit_code={res_check.exit_code}"
                ),
                detalhes={
                    "etapa": "git-tag-check",
                    "tag": nome_tag,
                    "exit_code": res_check.exit_code,
                    "stderr": res_check.stderr[:1024],
                },
            )
        if res_check.stdout.strip():
            return FalhaGravacao(
                categoria="git-tag-colisao",
                mensagem=(
                    f"tag {nome_tag!r} já existe; gravação preservada mas "
                    "tag não aplicada (R8.7)"
                ),
                detalhes={"etapa": "git-tag-check", "tag": nome_tag},
            )

        # Aplicação propriamente dita (lightweight tag em HEAD).
        res_tag = self._skill_git.executar("tag", nome_tag)
        if res_tag.exit_code != 0:
            return FalhaGravacao(
                categoria="git-tag-colisao",
                mensagem=(
                    f"git tag {nome_tag!r} falhou: "
                    f"exit_code={res_tag.exit_code}"
                ),
                detalhes={
                    "etapa": "git-tag-apply",
                    "tag": nome_tag,
                    "exit_code": res_tag.exit_code,
                    "stderr": res_tag.stderr[:1024],
                },
            )
        return None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

__all__ = [
    "DIR_DEBATES",
    "DIR_DECISIONS",
    "PREFIXO_TAG_CONGELAMENTO",
    "CategoriaFalhaGravacao",
    "FalhaGravacao",
    "ResultadoGravacao",
    "CouncilRecorder",
]
