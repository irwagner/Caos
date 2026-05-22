"""Testes unitários do :mod:`caos.walk_forward.relatorio` (Spec 2 — Task 7).

Cobre **R8** do ``requirements.md``:

- R8.1: arquivo Markdown com frontmatter compatível com
  :class:`caos.models.NotaZettel` (área ``Decisoes_do_Conselho``).
- R8.2: tabela das métricas por janela e dos agregados, em pt-BR.

Cenários cobertos:

1. ``escrever`` cria o diretório ``<raiz_saida>/<identificador>/`` com
   os dois arquivos canônicos (``resultado.json`` e ``relatorio.md``).
2. JSON serializado faz roundtrip — re-parse do arquivo produz o mesmo
   :class:`ResultadoWalkForward` (R7.1, determinismo byte-a-byte).
3. Markdown contém métricas-chave (status, identificador, manifesto,
   números de trades por janela, agregados).
4. Frontmatter parseado por :mod:`python-frontmatter` valida como
   :class:`caos.models.NotaZettel` (área ``Decisoes_do_Conselho``).
5. Integração opcional com :class:`CouncilRecorder` quando
   ``commit_council=True`` — debate/decisão são sintetizados e
   gravados.
6. Re-export de :class:`RelatorioWriter` e :func:`escrever_relatorio`
   pelo pacote ``caos.walk_forward``.

Convenções: pt-BR (R3.2 do Spec 1), Pydantic v2, Windows + cmd.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
import pytest

from caos.council_recorder import CouncilRecorder
from caos.models import NotaZettel
from caos.walk_forward import (
    ConfiguracaoWalkForward,
    JanelaWF,
    RelatorioWriter,
    ResultadoJanela,
    ResultadoWalkForward,
    escrever_relatorio,
)
from caos.walk_forward.relatorio import (
    AGENTE_AUTOR_PADRAO,
    AREA_NOTA_ZETTEL,
    NOME_ARQUIVO_JSON,
    NOME_ARQUIVO_MD,
)

UTC = timezone.utc

HASH_FAKE_A = "a" * 64
HASH_FAKE_B = "b" * 64
HASH_FAKE_C = "c" * 64


# ===========================================================================
# Helpers e fixtures
# ===========================================================================


def _git_disponivel() -> bool:
    return shutil.which("git") is not None


requires_git = pytest.mark.skipif(
    not _git_disponivel(), reason="git não disponível no PATH"
)


def _config_padrao() -> ConfiguracaoWalkForward:
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        seed=42,
    )


def _janela(
    indice: int,
    *,
    treino_inicio: datetime,
    treino_fim: datetime,
    teste_inicio: datetime,
    teste_fim: datetime,
    hash_dados: str = HASH_FAKE_A,
) -> JanelaWF:
    return JanelaWF(
        indice=indice,
        treino_inicio=treino_inicio,
        treino_fim=treino_fim,
        teste_inicio=teste_inicio,
        teste_fim=teste_fim,
        hash_dados=hash_dados,
    )


def _resultado_janela_ok(indice: int) -> ResultadoJanela:
    """Constrói um ResultadoJanela válido com status='ok' e métricas plausíveis."""
    base_treino_inicio = datetime(2026, 1, 1, tzinfo=UTC)
    base_treino_fim = datetime(2026, 3, 1, tzinfo=UTC)
    base_teste_inicio = datetime(2026, 3, 2, tzinfo=UTC)
    base_teste_fim = datetime(2026, 3, 12, tzinfo=UTC)
    # Janelas avançam 10 dias por índice, mantendo treino_fim <= teste_inicio
    # e ordem cronológica entre janelas.
    from datetime import timedelta as _td

    delta = _td(days=10 * indice)
    return ResultadoJanela(
        janela=_janela(
            indice=indice,
            treino_inicio=base_treino_inicio + delta,
            treino_fim=base_treino_fim + delta,
            teste_inicio=base_teste_inicio + delta,
            teste_fim=base_teste_fim + delta,
            hash_dados=HASH_FAKE_A,
        ),
        estrategia="EstrategiaTeste",
        configuracao=_config_padrao(),
        sharpe_anualizado=1.25 + indice * 0.01,
        calmar=0.85 + indice * 0.01,
        drawdown_maximo_percentual=0.15,
        drawdown_maximo_dias=5,
        win_rate=0.55,
        payoff_medio=1.4,
        mfe_medio=2.0,
        mae_medio=-1.0,
        numero_trades=10 + indice,
        pnl_total=100.0 + indice * 5.0,
        look_ahead_violation=False,
        status="ok",
        motivo_falha=None,
        duracao_ms=125 + indice,
    )


def _resultado_walk_forward_concluido(
    *,
    identificador: str = "2026-03-15-01",
    estrategia: str = "EstrategiaTeste",
    n_janelas: int = 3,
) -> ResultadoWalkForward:
    janelas = [_resultado_janela_ok(i) for i in range(n_janelas)]
    return ResultadoWalkForward(
        identificador=identificador,
        estrategia=estrategia,
        configuracao=_config_padrao(),
        manifesto_hash=HASH_FAKE_B,
        janelas=janelas,
        agregado_mediana={
            "sharpe_anualizado": 1.26,
            "numero_trades": 11.0,
            "pnl_total": 105.0,
        },
        agregado_media={
            "sharpe_anualizado": 1.26,
            "numero_trades": 11.0,
            "pnl_total": 105.0,
        },
        versoes_dependencias={"pandas": "2.2.0", "numpy": "1.26.0"},
        status="concluido",
    )


def _resultado_walk_forward_manifesto_invalido(
    identificador: str = "2026-03-15-02",
) -> ResultadoWalkForward:
    """ResultadoWalkForward com status='manifesto-invalido' (R4.2)."""
    return ResultadoWalkForward(
        identificador=identificador,
        estrategia="EstrategiaTeste",
        configuracao=_config_padrao(),
        manifesto_hash="0" * 64,
        janelas=[],
        agregado_mediana={},
        agregado_media={},
        versoes_dependencias={},
        status="manifesto-invalido",
    )


def _inicializar_repo_git(repo: Path) -> None:
    """Cria um repo Git mínimo + commit inicial.

    Mesmo padrão de ``test_council_recorder.py``: o commit inicial é
    necessário para que ``git tag`` em HEAD funcione. Suprime stdout/
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


# ===========================================================================
# 1. Estrutura de arquivos
# ===========================================================================


class TestEscritaCriaArquivos:
    """`escrever` cria o diretório com JSON + Markdown canônicos."""

    def test_escrever_cria_diretorio_com_dois_arquivos(
        self, tmp_path: Path
    ) -> None:
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()

        diretorio = writer.escrever(
            resultado=resultado,
            raiz_saida=tmp_path,
            commit_council=False,
        )

        assert diretorio == tmp_path / resultado.identificador
        assert diretorio.is_dir()
        assert (diretorio / NOME_ARQUIVO_JSON).is_file()
        assert (diretorio / NOME_ARQUIVO_MD).is_file()

    def test_escrever_devolve_path_absoluto_quando_raiz_absoluta(
        self, tmp_path: Path
    ) -> None:
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )
        assert diretorio.is_absolute()

    def test_escrever_idempotente_sobre_o_mesmo_destino(
        self, tmp_path: Path
    ) -> None:
        """Duas escritas consecutivas devem produzir bytes idênticos (R7.1)."""
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        d1 = writer.escrever(resultado=resultado, raiz_saida=tmp_path)
        bytes_json_1 = (d1 / NOME_ARQUIVO_JSON).read_bytes()
        bytes_md_1 = (d1 / NOME_ARQUIVO_MD).read_bytes()

        d2 = writer.escrever(resultado=resultado, raiz_saida=tmp_path)
        bytes_json_2 = (d2 / NOME_ARQUIVO_JSON).read_bytes()
        bytes_md_2 = (d2 / NOME_ARQUIVO_MD).read_bytes()

        assert bytes_json_1 == bytes_json_2
        assert bytes_md_1 == bytes_md_2

    def test_escrever_remove_arquivo_temporario(self, tmp_path: Path) -> None:
        """Garante que o ``.tmp`` não vaza no diretório final (limpeza)."""
        resultado = _resultado_walk_forward_concluido()
        RelatorioWriter().escrever(
            resultado=resultado, raiz_saida=tmp_path
        )
        diretorio = tmp_path / resultado.identificador
        nomes = {p.name for p in diretorio.iterdir()}
        assert nomes == {NOME_ARQUIVO_JSON, NOME_ARQUIVO_MD}


# ===========================================================================
# 2. JSON canônico — roundtrip
# ===========================================================================


class TestJsonRoundtrip:
    """O JSON gerado é um ``ResultadoWalkForward`` válido (roundtrip)."""

    def test_json_roundtrip_concluido(self, tmp_path: Path) -> None:
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        bruto = (diretorio / NOME_ARQUIVO_JSON).read_text(encoding="utf-8")
        payload = json.loads(bruto)
        recriado = ResultadoWalkForward.model_validate(payload)

        # ``model_dump_json`` (mode JSON) tem que coincidir; qualquer
        # divergência indica perda de dados na serialização.
        assert (
            recriado.model_dump(mode="json")
            == resultado.model_dump(mode="json")
        )

    def test_json_roundtrip_manifesto_invalido(self, tmp_path: Path) -> None:
        resultado = _resultado_walk_forward_manifesto_invalido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        payload = json.loads(
            (diretorio / NOME_ARQUIVO_JSON).read_text(encoding="utf-8")
        )
        recriado = ResultadoWalkForward.model_validate(payload)

        assert recriado.status == "manifesto-invalido"
        assert recriado.janelas == []

    def test_json_e_canonico_e_chaves_ordenadas(self, tmp_path: Path) -> None:
        """JSON deve usar ``sort_keys=True`` e ``indent=2`` (determinismo)."""
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        bruto = (diretorio / NOME_ARQUIVO_JSON).read_text(encoding="utf-8")
        # indent=2: a primeira chave de objeto começa após "{\n  \""
        assert bruto.startswith("{\n  \""), bruto[:50]
        # sort_keys=True: chaves de topo aparecem em ordem alfabética.
        # Esperado o primeiro nível do dump ter "agregado_media" antes
        # de "agregado_mediana" (mesma ordem alfabética).
        idx_media = bruto.index('"agregado_media"')
        idx_mediana = bruto.index('"agregado_mediana"')
        assert idx_media < idx_mediana


# ===========================================================================
# 3. Markdown contém métricas-chave
# ===========================================================================


class TestMarkdownContemMetricas:
    """O Markdown gerado contém métricas-chave em pt-BR (R8.2)."""

    def test_markdown_contem_identificador_e_status(self, tmp_path: Path) -> None:
        resultado = _resultado_walk_forward_concluido(
            identificador="2026-03-15-07"
        )
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        texto = (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        assert "2026-03-15-07" in texto
        assert "concluido" in texto
        assert resultado.estrategia in texto
        # Cabeçalho em pt-BR.
        assert "# Relatório Walk-Forward" in texto

    def test_markdown_contem_tabela_de_janelas(self, tmp_path: Path) -> None:
        resultado = _resultado_walk_forward_concluido(n_janelas=3)
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        texto = (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        assert "## Métricas por Janela" in texto
        # Cabeçalho de tabela markdown contém "Sharpe" e "PnL".
        assert "| Sharpe" in texto or "Sharpe |" in texto
        assert "PnL" in texto
        # Cada janela aparece com seu número de trades.
        for janela in resultado.janelas:
            assert f"| {janela.numero_trades} |" in texto

    def test_markdown_contem_agregados_em_pt_br(self, tmp_path: Path) -> None:
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        texto = (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        assert "## Agregado (mediana)" in texto
        assert "## Agregado (média)" in texto
        # Cada métrica agregada aparece na tabela.
        for metrica in resultado.agregado_mediana:
            assert f"| {metrica} |" in texto

    def test_markdown_para_manifesto_invalido_indica_ausencia_de_janelas(
        self, tmp_path: Path
    ) -> None:
        resultado = _resultado_walk_forward_manifesto_invalido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        texto = (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        assert "manifesto-invalido" in texto
        # Mensagem explicita ausência de janelas.
        assert "Sem janelas registradas" in texto


# ===========================================================================
# 4. Frontmatter compatível com NotaZettel
# ===========================================================================


class TestFrontmatterNotaZettel:
    """Frontmatter parseável por :mod:`python-frontmatter` e compatível com NotaZettel."""

    def test_frontmatter_parseia_com_python_frontmatter(
        self, tmp_path: Path
    ) -> None:
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        texto = (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        post = frontmatter.loads(texto)

        # Campos NotaZettel obrigatórios (R8.1).
        assert post.metadata["area"] == AREA_NOTA_ZETTEL
        assert post.metadata["agente_autor"] == AGENTE_AUTOR_PADRAO
        assert isinstance(post.metadata["tags"], list)
        assert len(post.metadata["tags"]) >= 1
        assert isinstance(post.metadata["titulo"], str)
        assert resultado.identificador in post.metadata["titulo"]
        # data_criacao em ISO 8601 com sufixo 'Z' (UTC).
        assert post.metadata["data_criacao"].endswith("Z")

        # Campos extras úteis para auditoria.
        assert post.metadata["id"] == resultado.identificador
        assert post.metadata["identificador"] == resultado.identificador
        assert post.metadata["manifesto_hash"] == resultado.manifesto_hash
        assert post.metadata["estrategia"] == resultado.estrategia
        assert post.metadata["status"] == resultado.status
        assert post.metadata["num_janelas"] == len(resultado.janelas)

    def test_frontmatter_valida_como_nota_zettel(self, tmp_path: Path) -> None:
        """Frontmatter pode ser usado para construir uma :class:`NotaZettel`."""
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        texto = (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        post = frontmatter.loads(texto)

        # Selecionar apenas os campos que NotaZettel reconhece (extras
        # do WF não passam por ``extra="forbid"``).
        campos_nota = {
            "titulo": post.metadata["titulo"],
            "area": post.metadata["area"],
            "tags": post.metadata["tags"],
            "data_criacao": post.metadata["data_criacao"],
            "agente_autor": post.metadata["agente_autor"],
        }
        nota = NotaZettel.model_validate(campos_nota)
        assert nota.area == "Decisoes_do_Conselho"
        assert nota.agente_autor == "Athena"
        assert nota.data_criacao == datetime(
            2026, 3, 15, 0, 0, 0, tzinfo=UTC
        )

    def test_frontmatter_data_criacao_derivada_do_identificador(
        self, tmp_path: Path
    ) -> None:
        """``data_criacao`` é determinística: AAAA-MM-DD-NN ⇒ AAAA-MM-DD 00:00:00 UTC."""
        resultado = _resultado_walk_forward_concluido(
            identificador="2027-07-04-12"
        )
        writer = RelatorioWriter()
        diretorio = writer.escrever(
            resultado=resultado, raiz_saida=tmp_path
        )

        post = frontmatter.loads(
            (diretorio / NOME_ARQUIVO_MD).read_text(encoding="utf-8")
        )
        assert post.metadata["data_criacao"] == "2027-07-04T00:00:00Z"


# ===========================================================================
# 5. Integração com CouncilRecorder (commit_council=True)
# ===========================================================================


class TestIntegracaoCouncil:
    """`commit_council=True` dispara :meth:`CouncilRecorder.gravar`."""

    @requires_git
    def test_commit_council_grava_debate_e_decisao(
        self, tmp_path: Path
    ) -> None:
        # Estrutura: tmp_path é workspace; raiz_saida é um subdir interno.
        _inicializar_repo_git(tmp_path)
        recorder = CouncilRecorder(raiz_workspace=tmp_path)

        resultado = _resultado_walk_forward_concluido(
            identificador="2026-04-10-01",
            estrategia="EstrategiaCommit",
        )
        raiz_saida = tmp_path / "05_BACKTEST" / "relatorios"
        writer = RelatorioWriter(recorder=recorder)

        diretorio = writer.escrever(
            resultado=resultado,
            raiz_saida=raiz_saida,
            commit_council=True,
        )

        # Arquivos do relatório existem.
        assert (diretorio / NOME_ARQUIVO_JSON).is_file()
        assert (diretorio / NOME_ARQUIVO_MD).is_file()

        # CouncilRecorder gravou debate + decisão em CAOS_Council/.
        debates_dir = tmp_path / "CAOS_Council" / "debates"
        decisions_dir = tmp_path / "CAOS_Council" / "decisions"
        debates = list(debates_dir.glob("2026-04-10-01-*.md"))
        decisions = list(decisions_dir.glob("2026-04-10-01-*.md"))
        assert len(debates) == 1
        assert len(decisions) == 1

    def test_commit_council_sem_recorder_levanta_value_error(
        self, tmp_path: Path
    ) -> None:
        """`commit_council=True` sem recorder no construtor falha cedo."""
        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter()  # sem recorder

        with pytest.raises(ValueError, match="commit_council"):
            writer.escrever(
                resultado=resultado,
                raiz_saida=tmp_path,
                commit_council=True,
            )

        # Não deve ter criado arquivos (falha cedo, antes de qualquer escrita).
        assert not (tmp_path / resultado.identificador).exists()

    def test_commit_council_false_nao_invoca_recorder(
        self, tmp_path: Path
    ) -> None:
        """`commit_council=False` não usa o recorder mesmo se injetado."""
        recorder_chamadas: list[tuple] = []

        class RecorderEspiao:
            """Stub que registra invocações de :meth:`gravar`."""

            def gravar(self, debate, decisao):  # type: ignore[no-untyped-def]
                recorder_chamadas.append((debate, decisao))

        resultado = _resultado_walk_forward_concluido()
        writer = RelatorioWriter(recorder=RecorderEspiao())  # type: ignore[arg-type]

        writer.escrever(
            resultado=resultado,
            raiz_saida=tmp_path,
            commit_council=False,
        )

        assert recorder_chamadas == []


# ===========================================================================
# 6. Re-export e helper funcional
# ===========================================================================


def test_relatorio_writer_reexportado_do_pacote() -> None:
    from caos.walk_forward import RelatorioWriter as Reexport

    assert Reexport is RelatorioWriter


def test_escrever_relatorio_funcional_equivale_ao_writer(
    tmp_path: Path,
) -> None:
    resultado = _resultado_walk_forward_concluido()
    raiz_a = tmp_path / "writer"
    raiz_b = tmp_path / "func"
    raiz_a.mkdir()
    raiz_b.mkdir()

    d_a = RelatorioWriter().escrever(
        resultado=resultado, raiz_saida=raiz_a
    )
    d_b = escrever_relatorio(resultado, raiz_b)

    bytes_json_a = (d_a / NOME_ARQUIVO_JSON).read_bytes()
    bytes_json_b = (d_b / NOME_ARQUIVO_JSON).read_bytes()
    bytes_md_a = (d_a / NOME_ARQUIVO_MD).read_bytes()
    bytes_md_b = (d_b / NOME_ARQUIVO_MD).read_bytes()

    assert bytes_json_a == bytes_json_b
    assert bytes_md_a == bytes_md_b
