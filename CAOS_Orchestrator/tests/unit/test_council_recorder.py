"""Testes unitários do :mod:`caos.council_recorder`.

Cobre R8.1–R8.7 do ``requirements.md`` exercitando:

- gravação básica de Debate + Decisao_Do_Conselho com schemas YAML;
- aplicação de tag ``caos-frozen-AAAA-MM-DD-NN`` quando
  ``aprovado_walk_forward`` é verdadeiro (R8.6);
- ausência de tag quando ``aprovado_walk_forward`` é falso;
- proteção contra colisão de tag pré-existente (R8.7);
- coerência de identificadores entre debate e decisão (R8.1);
- validação de campos obrigatórios da decisão (R8.3);
- preservação dos arquivos no disco em caso de falha de commit (R8.5);
- idempotência da serialização YAML (mesmos modelos → mesmos bytes).

Os testes inicializam um repo Git em ``tmp_path`` (mesmo padrão da
Task 5) e usam ``pytest.skip`` quando ``git`` não está no PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from caos.council_recorder import (
    DIR_DEBATES,
    DIR_DECISIONS,
    PREFIXO_TAG_CONGELAMENTO,
    CouncilRecorder,
    ResultadoGravacao,
    _slug_do_titulo,
)
from caos.models import (
    Debate,
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
    Veto,
)
from caos.skills.git import SkillGit


# ---------------------------------------------------------------------------
# Helpers comuns
# ---------------------------------------------------------------------------


def _git_disponivel() -> bool:
    return shutil.which("git") is not None


requires_git = pytest.mark.skipif(
    not _git_disponivel(), reason="git não disponível no PATH"
)


def _inicializar_repo(repo: Path) -> None:
    """Cria um repo Git mínimo + um commit inicial vazio.

    O commit inicial é necessário para que ``git tag`` em ``HEAD``
    encontre algo onde ancorar (caso contrário, ``git tag`` falha).
    """
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "caos@test.local"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "CAOS Test"],
        check=True,
        capture_output=True,
    )
    # Commit inicial para que HEAD aponte para algo (necessário para tags).
    seed = repo / "README.md"
    seed.write_text("# repo de teste\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "README.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )


def _debate_minimo(
    *,
    identificador: str = "2026-05-14-01",
    titulo: str = "implementacao-circuit-breaker-fase-2",
) -> Debate:
    """Constrói um Debate válido mínimo para os testes."""
    return Debate(
        identificador=identificador,
        titulo=titulo,
        data_inicio=datetime(2026, 5, 14, 14, 0, 0, tzinfo=timezone.utc),
        data_fim=datetime(2026, 5, 14, 14, 18, 0, tzinfo=timezone.utc),
        agentes_participantes=["Athena", "Cerberus", "Manolo"],
        modelos={
            "Athena": "claude-opus-4.7",
            "Cerberus": "claude-sonnet-4.5",
            "Manolo": "claude-haiku-4.5",
        },
        contexto_hash_sha256="a" * 64,
        notas_injetadas=["Modulo_Risco/Trailing_Tres_Fases.md"],
        seeds={"Athena": 42, "Cerberus": 42, "Manolo": 42},
        orcamento_de_turnos=12,
        turnos_consumidos=4,
        fase_final="CONCLUIDO",
        status="concluido",
        turnos=[],
    )


def _decisao_minima(
    *,
    identificador: str = "2026-05-14-01",
    titulo_debate: str = "implementacao-circuit-breaker-fase-2",
    aprovado_walk_forward: bool = False,
    propostas: list[Proposta] | None = None,
    vetos: list[Veto] | None = None,
    links_zettel: list[str] | None = None,
) -> DecisaoDoConselho:
    """Constrói uma DecisaoDoConselho válida mínima para os testes."""
    if propostas is None:
        propostas = [
            Proposta(
                id="P1",
                autor="Manolo",
                resumo="Trailing 3 fases ancorado em VWAP",
                conteudo="Detalhes...",
                confianca=78,
            ),
        ]
    if vetos is None:
        vetos = []
    if links_zettel is None:
        links_zettel = ["[[Trailing_Tres_Fases]]"]
    return DecisaoDoConselho(
        identificador=identificador,
        debate_relacionado=f"{identificador}-{titulo_debate}.md",
        agentes_participantes=["Athena", "Cerberus", "Manolo"],
        propostas=propostas,
        vetos=vetos,
        decisao_final=DecisaoFinal(
            proposta_aceita="P1",
            rationale="Manolo apresentou ancoragem mais robusta em VWAP.",
        ),
        links_zettel=links_zettel,
        aprovado_walk_forward=aprovado_walk_forward,
        reproduzivel="parcial",
        regressao_detectada=False,
        status="concluido",
    )


def _ler_frontmatter(caminho: Path) -> dict:
    """Extrai e parseia o frontmatter YAML de um Markdown."""
    texto = caminho.read_text(encoding="utf-8")
    assert texto.startswith("---\n"), "frontmatter ausente"
    fim = texto.index("\n---\n", 4)
    yaml_str = texto[4:fim]
    return yaml.safe_load(yaml_str)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Atalho para invocações ``git -C <repo> ...`` em testes."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------


def test_slug_passa_quando_ja_e_kebab_case() -> None:
    assert _slug_do_titulo("ja-em-kebab-case") == "ja-em-kebab-case"


def test_slug_normaliza_espacos_e_caixa() -> None:
    assert _slug_do_titulo("Título Composto Com Espaços") == "t-tulo-composto-com-espa-os"


def test_slug_trunca_em_60() -> None:
    titulo = "a" * 200
    s = _slug_do_titulo(titulo)
    assert len(s) <= 60
    assert s == "a" * 60


# ---------------------------------------------------------------------------
# Construtor
# ---------------------------------------------------------------------------


@requires_git
def test_construtor_cria_subdiretorios(tmp_path: Path) -> None:
    """O construtor cria CAOS_Council/{debates,decisions} se ausentes."""
    _inicializar_repo(tmp_path)
    assert not (tmp_path / DIR_DEBATES).exists()
    assert not (tmp_path / DIR_DECISIONS).exists()
    CouncilRecorder(raiz_workspace=tmp_path)
    assert (tmp_path / DIR_DEBATES).is_dir()
    assert (tmp_path / DIR_DECISIONS).is_dir()


def test_construtor_recusa_raiz_inexistente(tmp_path: Path) -> None:
    inexistente = tmp_path / "sem-raiz"
    with pytest.raises(ValueError):
        CouncilRecorder(raiz_workspace=inexistente)


# ---------------------------------------------------------------------------
# Gravação básica
# ---------------------------------------------------------------------------


@requires_git
def test_grava_debate_e_decisao_minimos(tmp_path: Path) -> None:
    """Caminho feliz: arquivos no disco, frontmatter correto, commit feito."""
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    res = rec.gravar(_debate_minimo(), _decisao_minima())
    assert isinstance(res, ResultadoGravacao)
    assert res.sucesso, f"falha inesperada: {res.falha}"
    assert res.commit_realizado is True
    assert res.commit_sha is not None
    assert len(res.commit_sha) >= 7
    assert res.tag_aplicada is None  # walk_forward=False

    # Arquivos em disco.
    assert res.caminho_debate.is_file()
    assert res.caminho_decisao.is_file()
    nome_esperado = "2026-05-14-01-implementacao-circuit-breaker-fase-2.md"
    assert res.caminho_debate.name == nome_esperado
    assert res.caminho_decisao.name == nome_esperado

    # Frontmatter do debate.
    fm_debate = _ler_frontmatter(res.caminho_debate)
    assert fm_debate["identificador"] == "2026-05-14-01"
    assert fm_debate["titulo"] == "implementacao-circuit-breaker-fase-2"
    assert fm_debate["status"] == "concluido"
    assert fm_debate["orcamento_de_turnos"] == 12
    assert fm_debate["agentes_participantes"] == [
        "Athena",
        "Cerberus",
        "Manolo",
    ]

    # Frontmatter da decisão.
    fm_decisao = _ler_frontmatter(res.caminho_decisao)
    assert fm_decisao["identificador"] == "2026-05-14-01"
    assert fm_decisao["aprovado_walk_forward"] is False
    assert fm_decisao["decisao_final"]["proposta_aceita"] == "P1"
    assert fm_decisao["links_zettel"] == ["[[Trailing_Tres_Fases]]"]
    assert fm_decisao["vetos"] == []  # lista vazia é permitida (R8.2)

    # Commit dedicado existe e contém os 2 arquivos.
    log = _git(tmp_path, "log", "-1", "--name-only", "--pretty=%H%n%s")
    assert log.returncode == 0
    saida = log.stdout
    assert "2026-05-14-01" in saida
    assert "implementacao-circuit-breaker-fase-2" in saida
    rel_debate = (
        f"{DIR_DEBATES}/2026-05-14-01-"
        "implementacao-circuit-breaker-fase-2.md"
    )
    rel_decisao = (
        f"{DIR_DECISIONS}/2026-05-14-01-"
        "implementacao-circuit-breaker-fase-2.md"
    )
    assert rel_debate in saida
    assert rel_decisao in saida


# ---------------------------------------------------------------------------
# Tag de congelamento (R8.6, R8.7)
# ---------------------------------------------------------------------------


@requires_git
def test_grava_aplica_tag_quando_walk_forward(tmp_path: Path) -> None:
    """``aprovado_walk_forward=True`` aplica ``caos-frozen-...``."""
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    res = rec.gravar(
        _debate_minimo(),
        _decisao_minima(aprovado_walk_forward=True),
    )
    assert res.sucesso
    assert res.tag_aplicada == f"{PREFIXO_TAG_CONGELAMENTO}2026-05-14-01"
    # Confirmação direta via git tag -l.
    confer = _git(tmp_path, "tag", "-l", res.tag_aplicada)
    assert confer.returncode == 0
    assert confer.stdout.strip() == res.tag_aplicada


@requires_git
def test_grava_nao_aplica_tag_quando_nao_walk_forward(tmp_path: Path) -> None:
    """``aprovado_walk_forward=False`` não aplica nenhuma tag."""
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    res = rec.gravar(
        _debate_minimo(),
        _decisao_minima(aprovado_walk_forward=False),
    )
    assert res.sucesso
    assert res.tag_aplicada is None
    todas = _git(tmp_path, "tag", "-l")
    assert PREFIXO_TAG_CONGELAMENTO not in todas.stdout


@requires_git
def test_colisao_de_tag_nao_sobrescreve(tmp_path: Path) -> None:
    """Se a tag já existe, a gravação retorna ``git-tag-colisao``.

    Os arquivos permanecem em disco (R8.5) e a tag original (apontando
    para um commit anterior) é preservada intacta.
    """
    _inicializar_repo(tmp_path)
    nome_tag = f"{PREFIXO_TAG_CONGELAMENTO}2026-05-14-01"
    # Aplica a tag pré-existente sobre o commit inicial.
    sha_inicial = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    _git(tmp_path, "tag", nome_tag)

    rec = CouncilRecorder(raiz_workspace=tmp_path)
    res = rec.gravar(
        _debate_minimo(),
        _decisao_minima(aprovado_walk_forward=True),
    )
    assert not res.sucesso
    assert res.falha is not None
    assert res.falha.categoria == "git-tag-colisao"
    # Arquivos preservados.
    assert res.caminho_debate.is_file()
    assert res.caminho_decisao.is_file()
    # Commit do par debate+decisão foi feito (gravação aconteceu antes
    # da etapa de tag).
    assert res.commit_realizado is True
    # Tag original ainda aponta para o commit inicial, não para o novo.
    sha_tag = _git(tmp_path, "rev-list", "-n", "1", nome_tag).stdout.strip()
    assert sha_tag == sha_inicial


# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------


@requires_git
def test_identificadores_divergentes_lanca(tmp_path: Path) -> None:
    """``debate.identificador != decisao.identificador`` aborta a gravação."""
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    debate = _debate_minimo(identificador="2026-05-14-01")
    decisao = _decisao_minima(identificador="2026-05-14-02")
    res = rec.gravar(debate, decisao)
    assert not res.sucesso
    assert res.falha is not None
    assert res.falha.categoria == "identificador-invalido"
    # Nada gravado em disco.
    assert not list((tmp_path / DIR_DEBATES).iterdir())
    assert not list((tmp_path / DIR_DECISIONS).iterdir())


@requires_git
def test_decisao_sem_propostas_falha(tmp_path: Path) -> None:
    """Validação Pydantic já bloqueia, mas garantimos a mensagem.

    O modelo ``DecisaoDoConselho`` exige ``propostas`` não-vazia
    (Field min_length=1). O propósito do teste é confirmar que a
    construção do objeto sem propostas levanta exceção — o que mantém
    o invariante R8.3 ainda na fronteira de entrada.
    """
    _inicializar_repo(tmp_path)
    with pytest.raises(Exception):  # pydantic ValidationError
        _decisao_minima(propostas=[])


@requires_git
def test_decisao_sem_links_zettel_falha(tmp_path: Path) -> None:
    """``links_zettel`` vazia também é rejeitada na construção."""
    _inicializar_repo(tmp_path)
    with pytest.raises(Exception):  # pydantic ValidationError
        _decisao_minima(links_zettel=[])


@requires_git
def test_lista_de_vetos_pode_ser_vazia(tmp_path: Path) -> None:
    """Campo ``vetos`` aceita lista vazia (R8.2 — única exceção)."""
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    res = rec.gravar(_debate_minimo(), _decisao_minima(vetos=[]))
    assert res.sucesso, f"falha: {res.falha}"


# ---------------------------------------------------------------------------
# Falha de commit preserva arquivos (R8.5)
# ---------------------------------------------------------------------------


from caos.skills._base import RegistroAuditoriaSkill
from caos.skills.git import ResultadoGit


class _SkillGitForcandoFalha(SkillGit):
    """Variante de ``SkillGit`` que força exit_code != 0 em ``commit``.

    Os demais subcomandos (``add``, ``log``, ``tag``) caem no fluxo real.
    Útil para testar a preservação de arquivos quando o commit falha
    sem precisar corromper o repositório.
    """

    def executar(self, subcomando, *args, timeout_s=None):  # type: ignore[override]
        if subcomando == "commit":
            # Sintetizamos um ResultadoGit determinístico com exit_code=1.
            auditoria = RegistroAuditoriaSkill(
                nome=self.NOME,
                invocador=getattr(self, "_invocador", None),
                timestamp="2026-05-14T14:00:00Z",
                parametros_hash_sha256="0" * 64,
                exit_code=1,
                duracao_ms=0,
                status="skill-falha",
                motivo="commit forçado a falhar pelo teste",
                truncado_stdout=False,
                truncado_stderr=False,
            )
            return ResultadoGit(
                comando="git commit (simulado-falha)",
                subcomando="commit",
                args=tuple(args),
                exit_code=1,
                stdout="",
                stderr="commit forçado a falhar pelo teste",
                truncado_stdout=False,
                truncado_stderr=False,
                duracao_ms=0,
                status="skill-falha",
                auditoria=auditoria,
            )
        return super().executar(subcomando, *args, timeout_s=timeout_s)


@requires_git
def test_falha_de_commit_preserva_arquivos(tmp_path: Path) -> None:
    """Quando ``git commit`` falha, arquivos permanecem em disco (R8.5)."""
    _inicializar_repo(tmp_path)
    skill_quebrada = _SkillGitForcandoFalha(repo_dir=tmp_path)
    rec = CouncilRecorder(
        raiz_workspace=tmp_path, skill_git=skill_quebrada
    )
    res = rec.gravar(_debate_minimo(), _decisao_minima())
    assert not res.sucesso
    assert res.falha is not None
    assert res.falha.categoria == "git-commit-falhou"
    assert res.commit_realizado is False
    # Arquivos ainda no disco.
    assert res.caminho_debate.is_file()
    assert res.caminho_decisao.is_file()


# ---------------------------------------------------------------------------
# Idempotência da serialização
# ---------------------------------------------------------------------------


@requires_git
def test_serializacao_yaml_idempotente(tmp_path: Path) -> None:
    """Gravar 2x os mesmos modelos produz arquivos idênticos byte-a-byte.

    Para evitar a interferência de timestamps de commit (que mudam entre
    execuções), comparamos apenas o conteúdo dos arquivos Markdown.
    A 2ª gravação não passa pelo Git porque não há nada novo para
    commitar — espera-se ``git-commit-falhou`` (commit vazio rejeitado),
    o que é aceitável: o que estamos verificando é a estabilidade do
    output em disco.
    """
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    debate = _debate_minimo()
    decisao = _decisao_minima()

    res1 = rec.gravar(debate, decisao)
    assert res1.sucesso
    bytes_debate_1 = res1.caminho_debate.read_bytes()
    bytes_decisao_1 = res1.caminho_decisao.read_bytes()

    # Reescreve os arquivos sobre si mesmos.
    rec_serializa = rec._serializar_debate(debate)
    rec_serializa_dec = rec._serializar_decisao(decisao)
    res1.caminho_debate.write_text(
        rec_serializa, encoding="utf-8", newline="\n"
    )
    res1.caminho_decisao.write_text(
        rec_serializa_dec, encoding="utf-8", newline="\n"
    )

    bytes_debate_2 = res1.caminho_debate.read_bytes()
    bytes_decisao_2 = res1.caminho_decisao.read_bytes()
    assert bytes_debate_1 == bytes_debate_2
    assert bytes_decisao_1 == bytes_decisao_2


# ---------------------------------------------------------------------------
# Helper de limpeza para testes
# ---------------------------------------------------------------------------


@requires_git
def test_delete_debates_e_decisoes_limpa_apenas_subdirs(tmp_path: Path) -> None:
    _inicializar_repo(tmp_path)
    rec = CouncilRecorder(raiz_workspace=tmp_path)
    res = rec.gravar(_debate_minimo(), _decisao_minima())
    assert res.sucesso
    # Cria também um arquivo extra fora dos subdirs para garantir que
    # não é tocado.
    extra = tmp_path / "outro.txt"
    extra.write_text("preservar", encoding="utf-8")

    rec.delete_debates_e_decisoes()
    assert not list((tmp_path / DIR_DEBATES).iterdir())
    assert not list((tmp_path / DIR_DECISIONS).iterdir())
    assert extra.is_file()
