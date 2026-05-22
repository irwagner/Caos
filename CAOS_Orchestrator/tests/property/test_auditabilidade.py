"""
Property-based tests para o :mod:`caos.council_recorder`.

Implementa a **Property 2 — Auditability** do ``design.md``:

    Every Decisao_Do_Conselho with `status: concluido` SHALL have a
    corresponding Git commit containing the debate file and the decision
    file with matching identifier `AAAA-MM-DD-NN`.

**Validates: Requirements 8.1, 8.2, 8.4**

Estratégia (alinhada à Task 10 do ``tasks.md``):

- A cada exemplo, criamos um repo Git temporário em ``tmp_path_factory``,
  inicializamos o seed commit (necessário para tags/log) e instanciamos
  o :class:`CouncilRecorder` apontando para a raiz.
- Geramos um ``Debate`` + uma ``DecisaoDoConselho`` consistentes (mesmo
  identificador, mesmo título, mesmos agentes), variando: número de
  propostas (1–5), número de vetos (0–3), valor de
  ``aprovado_walk_forward`` (booleano) e valor de ``reproduzivel``
  (``true``/``parcial``/``false``).
- Gravamos o par e validamos:

  1. ``ResultadoGravacao.sucesso == True``;
  2. existe um commit cuja mensagem contém o identificador
     ``AAAA-MM-DD-NN``;
  3. esse commit toca exclusivamente o arquivo de debate e o de decisão
     com o identificador correspondente;
  4. quando ``aprovado_walk_forward == True``, a tag
     ``caos-frozen-AAAA-MM-DD-NN`` aponta para o commit recém-criado.

Vetos são modelados apenas como ``veto_de_risco`` (autor: Cerberus) com
``decisao == "aprovar-com-ressalvas"`` para evitar a interação com a
Property 4 (Risk Veto Soundness — turno 15) — o objetivo desta
propriedade é estritamente a auditabilidade Git, não a soundness do
veto.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.council_recorder import (
    DIR_DEBATES,
    DIR_DECISIONS,
    PREFIXO_TAG_CONGELAMENTO,
    CouncilRecorder,
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
# Pré-requisitos
# ---------------------------------------------------------------------------


def _git_disponivel() -> bool:
    return shutil.which("git") is not None


requires_git = pytest.mark.skipif(
    not _git_disponivel(), reason="git não disponível no PATH"
)


def _inicializar_repo(repo: Path) -> None:
    """Cria um repo Git mínimo + commit inicial para ancorar as tags."""
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


# ---------------------------------------------------------------------------
# Construtores de payload sintético
# ---------------------------------------------------------------------------


_TITULO = "auditabilidade-property-test"
_IDENTIFICADOR = "2026-05-14-01"


def _construir_propostas(n: int) -> list[Proposta]:
    """Gera ``n`` propostas distintas (id ``P1``..``Pn``)."""
    autores = ["Manolo", "Mister_M", "Odin", "Rodrigo", "Explorador"]
    return [
        Proposta(
            id=f"P{i + 1}",
            autor=autores[i % len(autores)],
            resumo=f"proposta sintética número {i + 1}",
            conteudo=f"detalhes da proposta {i + 1}",
            confianca=50 + i,
        )
        for i in range(n)
    ]


def _construir_vetos(n: int, propostas: list[Proposta]) -> list[Veto]:
    """Gera ``n`` vetos de risco (Cerberus, ``aprovar-com-ressalvas``).

    Limitamo-nos a vetos de risco aprovativos (sem ``bloquear``) para que
    a propriedade não dependa do orquestrador (Task 15) — aqui o foco é
    apenas a auditabilidade Git.
    """
    if n == 0:
        return []
    vetos: list[Veto] = []
    for i in range(n):
        alvo = propostas[i % len(propostas)].id
        vetos.append(
            Veto(
                tipo="veto_de_risco",
                autor="Cerberus",
                decisao="aprovar-com-ressalvas",
                proposta_alvo=alvo,
                justificativa=(
                    f"sintético: ressalva {i + 1} sobre proposta {alvo}"
                ),
            )
        )
    return vetos


def _construir_debate_e_decisao(
    *,
    n_propostas: int,
    n_vetos: int,
    aprovado_wf: bool,
    reproduzivel: str,
) -> tuple[Debate, DecisaoDoConselho]:
    propostas = _construir_propostas(n_propostas)
    vetos = _construir_vetos(n_vetos, propostas)
    debate = Debate(
        identificador=_IDENTIFICADOR,
        titulo=_TITULO,
        data_inicio=datetime(2026, 5, 14, 14, 0, 0, tzinfo=timezone.utc),
        data_fim=datetime(2026, 5, 14, 14, 30, 0, tzinfo=timezone.utc),
        agentes_participantes=["Athena", "Cerberus", "Manolo"],
        modelos={
            "Athena": "claude-opus-4.7",
            "Cerberus": "claude-sonnet-4.5",
            "Manolo": "claude-haiku-4.5",
        },
        contexto_hash_sha256="b" * 64,
        notas_injetadas=["Modulo_Risco/X.md"],
        seeds={"Athena": 1, "Cerberus": 1, "Manolo": 1},
        orcamento_de_turnos=12,
        turnos_consumidos=n_propostas + 1,
        fase_final="CONCLUIDO",
        status="concluido",
        turnos=[],
    )
    decisao = DecisaoDoConselho(
        identificador=_IDENTIFICADOR,
        debate_relacionado=f"{_IDENTIFICADOR}-{_TITULO}.md",
        agentes_participantes=["Athena", "Cerberus", "Manolo"],
        propostas=propostas,
        vetos=vetos,
        decisao_final=DecisaoFinal(
            proposta_aceita=propostas[0].id,
            rationale=(
                "Síntese gerada para teste de propriedade de "
                "auditabilidade — proposta primária aceita."
            ),
        ),
        links_zettel=["[[Modulo_Risco/X]]"],
        aprovado_walk_forward=aprovado_wf,
        reproduzivel=reproduzivel,  # type: ignore[arg-type]
        regressao_detectada=False,
        status="concluido",
    )
    return debate, decisao


# ---------------------------------------------------------------------------
# Property 2 — Auditability
# ---------------------------------------------------------------------------


@requires_git
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_propostas=st.integers(min_value=1, max_value=5),
    n_vetos=st.integers(min_value=0, max_value=3),
    aprovado_wf=st.booleans(),
    reproduzivel=st.sampled_from(["true", "parcial", "false"]),
)
def test_property_auditabilidade(
    n_propostas: int,
    n_vetos: int,
    aprovado_wf: bool,
    reproduzivel: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 8.1, 8.2, 8.4** (Property 2).

    Para todo Debate concluído sintético (variando propostas, vetos,
    walk-forward e reprodutibilidade), a gravação:

    1. tem sucesso (R8.2/R8.3 satisfeitos);
    2. produz commit dedicado cuja mensagem contém o identificador
       ``AAAA-MM-DD-NN`` (R8.4);
    3. o commit altera exatamente os 2 arquivos esperados sob
       ``CAOS_Council/(debates|decisions)/`` (R8.4);
    4. quando ``aprovado_walk_forward``, a tag
       ``caos-frozen-AAAA-MM-DD-NN`` é criada e aponta para o commit
       recém-criado (R8.6).
    """
    raiz = tmp_path_factory.mktemp("council_audit")
    _inicializar_repo(raiz)
    rec = CouncilRecorder(
        raiz_workspace=raiz, skill_git=SkillGit(repo_dir=raiz)
    )

    debate, decisao = _construir_debate_e_decisao(
        n_propostas=n_propostas,
        n_vetos=n_vetos,
        aprovado_wf=aprovado_wf,
        reproduzivel=reproduzivel,
    )

    res = rec.gravar(debate, decisao)
    # (1) gravação bem-sucedida
    assert res.sucesso, f"gravação falhou: {res.falha}"
    assert res.commit_realizado is True
    assert res.commit_sha is not None and len(res.commit_sha) >= 7

    # (2) Mensagem do commit contém o identificador.
    log_msg = subprocess.run(
        ["git", "-C", str(raiz), "log", "-1", "--pretty=%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert _IDENTIFICADOR in log_msg.stdout

    # (3) O commit toca exatamente os 2 caminhos esperados.
    nome_arquivo = f"{_IDENTIFICADOR}-{_TITULO}.md"
    rel_debate = f"{DIR_DEBATES}/{nome_arquivo}"
    rel_decisao = f"{DIR_DECISIONS}/{nome_arquivo}"
    log_files = subprocess.run(
        ["git", "-C", str(raiz), "show", "--name-only", "--pretty=", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    arquivos_no_commit = {
        linha.strip() for linha in log_files.stdout.splitlines() if linha.strip()
    }
    assert arquivos_no_commit == {rel_debate, rel_decisao}

    # (4) Tag aplicada se aprovado_walk_forward; se não, sem tag.
    listar_tags = subprocess.run(
        ["git", "-C", str(raiz), "tag", "-l"],
        capture_output=True,
        text=True,
        check=True,
    )
    tags = set(linha for linha in listar_tags.stdout.splitlines() if linha)
    nome_tag = f"{PREFIXO_TAG_CONGELAMENTO}{_IDENTIFICADOR}"
    if aprovado_wf:
        assert nome_tag in tags, (
            f"tag {nome_tag} ausente; tags presentes: {tags}"
        )
        assert res.tag_aplicada == nome_tag
        # Tag aponta para o commit recém-criado.
        sha_tag = subprocess.run(
            ["git", "-C", str(raiz), "rev-list", "-n", "1", nome_tag],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        sha_head = subprocess.run(
            ["git", "-C", str(raiz), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert sha_tag == sha_head
    else:
        assert nome_tag not in tags
        assert res.tag_aplicada is None
