"""Testes unitários do fluxo `caos debate iniciar|fechar` (Spec 5 — Task 4).

Cobre R3 e R4 do ``requirements.md`` do Spec 5:

- ``iniciar_debate`` cria starter em ``CAOS_Council/debates/AAAA-MM-DD-NN-{slug}.md``
  com frontmatter válido (schema :class:`caos.models.Debate`).
- Sequencial NN incrementa quando já existe arquivo no mesmo dia.
- Slug inválido / gatilho inválido / raiz inválida levantam
  :class:`DebateIoError` com categoria estável.
- ``fechar_debate`` em ``--dry-run`` devolve a Decisão derivada sem
  gravar nem commitar.
- ``fechar_debate`` em modo real grava arquivos em
  ``CAOS_Council/{debates,decisions}/`` e cria commit Git via
  :class:`CouncilRecorder` (Spec 1 — R8). Quando
  ``aprovado_walk_forward=true``, a tag
  ``caos-frozen-AAAA-MM-DD-NN`` é aplicada.
- ``fechar_debate`` num arquivo sem propostas / sem links_zettel
  retorna erro estruturado (não tenta gravar).

Os testes usam um repo Git temporário em ``tmp_path`` (mesmo padrão de
``tests/unit/test_council_recorder.py``) — não tocam o repo real do
projeto.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from caos.debate_io import (
    DIR_DEBATES_RELATIVO,
    DIR_DECISIONS_RELATIVO,
    DebateIoError,
    FlagsDebateFechar,
    FlagsDebateIniciar,
    fechar_debate,
    iniciar_debate,
)
from caos.models import Debate

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_disponivel() -> bool:
    return shutil.which("git") is not None


requires_git = pytest.mark.skipif(
    not _git_disponivel(), reason="git não disponível no PATH"
)


def _inicializar_repo_git(repo: Path) -> None:
    """Cria um repo Git mínimo com commit inicial.

    Mesmo padrão de ``tests/unit/test_council_recorder.py``: o commit
    inicial existe para que ``git tag`` em HEAD funcione. Suprime stdout/
    stderr para manter saída do pytest limpa.
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


def _ler_frontmatter(caminho: Path) -> dict:
    bruto = caminho.read_text(encoding="utf-8")
    assert bruto.startswith("---\n"), f"frontmatter ausente em {caminho}"
    fim = bruto.index("\n---\n", 4)
    return yaml.safe_load(bruto[4:fim]) or {}


def _preencher_debate_completo(
    caminho: Path,
    *,
    altera_exposicao: bool = False,
    requer_csharp: bool = False,
    aprovado_walk_forward: bool = True,
) -> None:
    """Sobrescreve um starter com Debate completo (≥2 propostas + síntese).

    Apenda turnos de PROPOSTAS (Manolo, Mister_M), CRITICA (Devils_Advocate),
    AVALIACAO_RISCO opcional (Cerberus), AVALIACAO_TECNICA opcional (Hermes),
    e SINTESE (Athena com bloco ```sintese contendo proposta_aceita,
    rationale, links_zettel, aprovado_walk_forward, reproduzivel,
    regressao_detectada, status).

    Atualiza o frontmatter para refletir ``fase_final=CONCLUIDO``,
    ``status=concluido``, ``turnos_consumidos`` correto e
    ``agentes_participantes`` expandido.
    """
    bruto = caminho.read_text(encoding="utf-8")
    fim = bruto.index("\n---\n", 4)
    frontmatter = yaml.safe_load(bruto[4:fim])

    agentes = ["Athena", "Manolo", "Mister_M", "Devils_Advocate"]
    if altera_exposicao:
        agentes.append("Cerberus")
    if requer_csharp:
        agentes.append("Hermes")
    frontmatter["agentes_participantes"] = sorted(set(agentes))
    frontmatter["modelos"]["Manolo"] = "claude-haiku-4.5"
    frontmatter["modelos"]["Mister_M"] = "minimax-m2"
    frontmatter["modelos"]["Devils_Advocate"] = "minimax-m2"
    if altera_exposicao:
        frontmatter["modelos"]["Cerberus"] = "claude-sonnet-4.5"
    if requer_csharp:
        frontmatter["modelos"]["Hermes"] = "qwen3-coder"
    frontmatter["fase_final"] = "CONCLUIDO"
    frontmatter["status"] = "concluido"
    frontmatter["data_fim"] = "2026-05-22T19:30:00Z"

    # Turnos.
    turnos_md = []
    n = 1

    def _turno(agente: str, fase: str, modelo: str, conteudo: str) -> str:
        nonlocal n
        cabecalho = (
            f"## Turno {n} — {agente} ({fase})\n\n"
            "```meta\n"
            f"agente: {agente}\n"
            f"modelo: {modelo}\n"
            "timestamp: 2026-05-22T19:00:00Z\n"
            "nao_deterministico: true\n"
            "status: ok\n"
            "```\n\n"
            f"{conteudo}\n"
        )
        n += 1
        return cabecalho

    turnos_md.append(_turno("Athena", "INICIADO", "claude-opus-4.7", "Tema definido."))
    turnos_md.append(
        _turno(
            "Manolo",
            "PROPOSTAS",
            "claude-haiku-4.5",
            (
                "```proposta\n"
                "id: P1\n"
                "autor: Manolo\n"
                "resumo: Filtro de regime via volatilidade.\n"
                "conteudo: Aplicar filtro ATR(14) > 1.0 antes de abrir trade.\n"
                "confianca: 70\n"
                "```\n"
            ),
        )
    )
    turnos_md.append(
        _turno(
            "Mister_M",
            "PROPOSTAS",
            "minimax-m2",
            (
                "```proposta\n"
                "id: P2\n"
                "autor: Mister_M\n"
                "resumo: Mean reversion VWAP no minuto 35.\n"
                "conteudo: Entrar contra rompimento se desvio do VWAP > 1.5σ.\n"
                "confianca: 65\n"
                "```\n"
            ),
        )
    )
    turnos_md.append(
        _turno(
            "Devils_Advocate",
            "CRITICA",
            "minimax-m2",
            "Risco de overfit ao período de treino, especialmente para P1.",
        )
    )
    if altera_exposicao:
        turnos_md.append(
            _turno(
                "Cerberus",
                "AVALIACAO_RISCO",
                "claude-sonnet-4.5",
                "Aprovado sem veto; exposição preservada.",
            )
        )
    if requer_csharp:
        turnos_md.append(
            _turno(
                "Hermes",
                "AVALIACAO_TECNICA",
                "qwen3-coder",
                "APIs aderentes à whitelist; sem veto técnico.",
            )
        )

    sintese_yaml = {
        "proposta_aceita": "P1",
        "rationale": "Proposta P1 (Manolo) aprovada por consenso.",
        "links_zettel": ["[[Decisao_Aprimoramento_ORB]]"],
        "aprovado_walk_forward": aprovado_walk_forward,
        "reproduzivel": "parcial",
        "regressao_detectada": False,
        "status": "concluido",
    }
    sintese_md = (
        "```sintese\n" + yaml.safe_dump(sintese_yaml, sort_keys=True) + "```\n"
    )
    turnos_md.append(_turno("Athena", "SINTESE", "claude-opus-4.7", sintese_md))

    frontmatter["turnos_consumidos"] = n - 1

    yaml_str = yaml.safe_dump(
        frontmatter, sort_keys=True, allow_unicode=True, default_flow_style=False
    )
    titulo_humano = frontmatter["titulo"].replace("-", " ")
    corpo = (
        f"# Debate {frontmatter['identificador']} — {titulo_humano}\n\n"
        + "\n".join(turnos_md)
    )
    caminho.write_text(f"---\n{yaml_str}---\n\n{corpo}", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# 1. iniciar_debate — caminho-feliz e validações
# ---------------------------------------------------------------------------


class TestIniciarDebate:
    def test_iniciar_cria_arquivo_com_frontmatter_valido(
        self, tmp_path: Path
    ) -> None:
        flags = FlagsDebateIniciar(
            slug="estudo-orb-baseline",
            titulo="Estudo da ORB baseline",
            gatilho="G3",
            altera_exposicao=True,
            csharp=False,
            raiz_workspace=tmp_path,
        )
        resultado = iniciar_debate(flags)

        assert resultado.caminho_debate.is_file()
        assert resultado.caminho_debate.parent == tmp_path / DIR_DEBATES_RELATIVO
        assert resultado.identificador.endswith("-01")
        assert resultado.slug == "estudo-orb-baseline"

        meta = _ler_frontmatter(resultado.caminho_debate)
        assert meta["identificador"] == resultado.identificador
        assert meta["titulo"] == "estudo-orb-baseline"
        assert meta["fase_final"] == "INICIADO"
        assert meta["status"] == "em-andamento"
        assert meta["agentes_participantes"] == ["Athena"]
        assert meta["modelos"]["Athena"] == "claude-opus-4.7"
        # Notas injetadas carregam gatilho e flags do tema.
        assert "gatilho:G3" in meta["notas_injetadas"]
        assert "aberto_por:auto" in meta["notas_injetadas"]
        assert "altera_exposicao:true" in meta["notas_injetadas"]
        assert "requer_csharp:false" in meta["notas_injetadas"]
        # Hash SHA-256 hex 64 chars [0-9a-f].
        assert len(meta["contexto_hash_sha256"]) == 64
        assert all(c in "0123456789abcdef" for c in meta["contexto_hash_sha256"])

    def test_iniciar_dois_debates_no_mesmo_dia_incrementa_nn(
        self, tmp_path: Path
    ) -> None:
        flags1 = FlagsDebateIniciar(
            slug="primeiro", raiz_workspace=tmp_path
        )
        r1 = iniciar_debate(flags1)
        flags2 = FlagsDebateIniciar(
            slug="segundo", raiz_workspace=tmp_path
        )
        r2 = iniciar_debate(flags2)
        assert r1.identificador != r2.identificador
        # NN é o último componente.
        assert int(r1.identificador.split("-")[-1]) == 1
        assert int(r2.identificador.split("-")[-1]) == 2

    @pytest.mark.parametrize(
        "slug_invalido",
        ["Slug Com Espaço", "ABC", "slug-com-_", "ç-acento", "x" * 61, ""],
    )
    def test_iniciar_slug_invalido_levanta(
        self, tmp_path: Path, slug_invalido: str
    ) -> None:
        flags = FlagsDebateIniciar(slug=slug_invalido, raiz_workspace=tmp_path)
        with pytest.raises(DebateIoError) as exc:
            iniciar_debate(flags)
        assert exc.value.categoria == "slug-invalido"

    def test_iniciar_gatilho_invalido_levanta(self, tmp_path: Path) -> None:
        flags = FlagsDebateIniciar(
            slug="ok", gatilho="G99", raiz_workspace=tmp_path
        )
        with pytest.raises(DebateIoError) as exc:
            iniciar_debate(flags)
        assert exc.value.categoria == "gatilho-invalido"

    def test_iniciar_raiz_inexistente_levanta(self, tmp_path: Path) -> None:
        flags = FlagsDebateIniciar(
            slug="ok", raiz_workspace=tmp_path / "nao-existe"
        )
        with pytest.raises(DebateIoError) as exc:
            iniciar_debate(flags)
        assert exc.value.categoria == "raiz-invalida"


# ---------------------------------------------------------------------------
# 2. fechar_debate — dry-run
# ---------------------------------------------------------------------------


class TestFecharDebateDryRun:
    def test_dry_run_devolve_decisao_sem_gravar(self, tmp_path: Path) -> None:
        flags_iniciar = FlagsDebateIniciar(
            slug="dry-run-decision", raiz_workspace=tmp_path
        )
        r_iniciar = iniciar_debate(flags_iniciar)
        _preencher_debate_completo(r_iniciar.caminho_debate)

        flags_fechar = FlagsDebateFechar(
            identificador=r_iniciar.identificador,
            dry_run=True,
            raiz_workspace=tmp_path,
        )
        r_fechar = fechar_debate(flags_fechar)
        assert r_fechar.dry_run is True
        assert r_fechar.resultado_gravacao is None
        # Decisão derivada deve ter as 2 propostas + síntese.
        assert len(r_fechar.decisao.propostas) == 2
        assert r_fechar.decisao.decisao_final.proposta_aceita == "P1"
        assert r_fechar.decisao.aprovado_walk_forward is True
        # Em dry-run, nenhum arquivo de Decisão é criado.
        decisoes_dir = tmp_path / DIR_DECISIONS_RELATIVO
        assert not decisoes_dir.exists() or not list(decisoes_dir.glob("*.md"))

    def test_dry_run_arquivo_sem_propostas_levanta(self, tmp_path: Path) -> None:
        # Starter sem turnos PROPOSTAS preenchidos.
        flags_iniciar = FlagsDebateIniciar(
            slug="sem-propostas", raiz_workspace=tmp_path
        )
        r_iniciar = iniciar_debate(flags_iniciar)
        # NÃO chama _preencher_debate_completo — fica só com o starter
        # (Turno 1 placeholder da Athena).
        flags_fechar = FlagsDebateFechar(
            identificador=r_iniciar.identificador,
            dry_run=True,
            raiz_workspace=tmp_path,
        )
        with pytest.raises(DebateIoError) as exc:
            fechar_debate(flags_fechar)
        assert exc.value.categoria == "sem-propostas"


# ---------------------------------------------------------------------------
# 3. fechar_debate — modo real (commit Git via CouncilRecorder)
# ---------------------------------------------------------------------------


@requires_git
class TestFecharDebateReal:
    def test_fechar_grava_decisao_e_aplica_tag(self, tmp_path: Path) -> None:
        _inicializar_repo_git(tmp_path)

        # Iniciar + preencher.
        r_iniciar = iniciar_debate(
            FlagsDebateIniciar(
                slug="aprimorar-orb",
                raiz_workspace=tmp_path,
                altera_exposicao=True,
            )
        )
        _preencher_debate_completo(
            r_iniciar.caminho_debate,
            altera_exposicao=True,
            aprovado_walk_forward=True,
        )

        r_fechar = fechar_debate(
            FlagsDebateFechar(
                identificador=r_iniciar.identificador,
                dry_run=False,
                raiz_workspace=tmp_path,
            )
        )
        assert r_fechar.dry_run is False
        grav = r_fechar.resultado_gravacao
        assert grav is not None
        assert grav.sucesso, f"falha: {grav.falha}"
        # Decisão gravada.
        decisoes = list((tmp_path / DIR_DECISIONS_RELATIVO).glob("*.md"))
        assert len(decisoes) == 1
        # Tag aplicada porque aprovado_walk_forward=true.
        assert grav.tag_aplicada is not None
        assert grav.tag_aplicada.startswith("caos-frozen-")
        # Commit feito.
        assert grav.commit_realizado is True
        assert grav.commit_sha is not None and len(grav.commit_sha) >= 7

    def test_fechar_sem_aprovacao_nao_aplica_tag(self, tmp_path: Path) -> None:
        _inicializar_repo_git(tmp_path)
        r_iniciar = iniciar_debate(
            FlagsDebateIniciar(slug="sem-aprovacao", raiz_workspace=tmp_path)
        )
        _preencher_debate_completo(
            r_iniciar.caminho_debate,
            aprovado_walk_forward=False,
        )
        r_fechar = fechar_debate(
            FlagsDebateFechar(
                identificador=r_iniciar.identificador,
                raiz_workspace=tmp_path,
            )
        )
        grav = r_fechar.resultado_gravacao
        assert grav is not None and grav.sucesso
        # Sem `aprovado_walk_forward`, recorder NÃO aplica tag (R8.6 do Spec 1).
        assert grav.tag_aplicada is None


# ---------------------------------------------------------------------------
# 4. fechar_debate — erros estruturados
# ---------------------------------------------------------------------------


class TestFecharDebateErros:
    def test_identificador_invalido_levanta(self, tmp_path: Path) -> None:
        with pytest.raises(DebateIoError) as exc:
            fechar_debate(
                FlagsDebateFechar(
                    identificador="2026-5-22-1",  # NN/MM com 1 dígito
                    raiz_workspace=tmp_path,
                )
            )
        assert exc.value.categoria == "identificador-invalido"

    def test_arquivo_inexistente_levanta(self, tmp_path: Path) -> None:
        # Diretório de Debates existe mas vazio.
        (tmp_path / DIR_DEBATES_RELATIVO).mkdir(parents=True)
        with pytest.raises(DebateIoError) as exc:
            fechar_debate(
                FlagsDebateFechar(
                    identificador="2026-05-22-99",
                    raiz_workspace=tmp_path,
                )
            )
        assert exc.value.categoria == "debate-nao-encontrado"
