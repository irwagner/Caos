"""Testes unitários da CLI ``caos`` (Task 17).

Cobre os 7 subcomandos integrados no Spec 1:

- ``caos init``
- ``caos manifesto build|verify`` (já testado em test_skills_data.py;
  aqui só validamos a presença no ``--help``)
- ``caos hydra sync``
- ``caos debate iniciar|fechar`` (Spec 5)
- ``caos perfil validar [nome]``
- ``caos cache stats``
- ``caos budget status``

A maioria dos testes invoca a CLI como subprocesso, no estilo do Task 6,
para validar o entry point ``python -m caos.main``. Os testes que precisam
de ``monkeypatch`` (ex.: ``hydra sync`` sem clone real) chamam
:func:`caos.main.cli` em-processo.

Plataforma alvo: Windows + cmd. Idioma: pt-BR.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import pytest

from caos import main as caos_main


# ---------------------------------------------------------------------------
# Localização dos perfis reais (copiados nas fixtures)
# ---------------------------------------------------------------------------

# Subimos 4 níveis: __file__ -> tests/unit -> tests -> CAOS_Orchestrator -> raiz workspace
ROOT_WORKSPACE = Path(__file__).resolve().parents[3]
DIR_AGENTES_REAL = ROOT_WORKSPACE / ".kiro" / "agents"

NOMES_AGENTES = (
    "Athena",
    "Cerberus",
    "Devils_Advocate",
    "Explorador",
    "Hermes",
    "Manolo",
    "Mister_M",
    "Odin",
    "Rodrigo",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str,
    cwd: Optional[Path] = None,
    timeout: float = 60.0,
    extra_env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    """Executa ``python -m caos.main <args>`` e devolve o resultado."""
    cmd: list[str] = [sys.executable, "-m", "caos.main", *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        # Forçamos ``utf-8`` com ``errors='replace'`` porque a CLI imprime
        # texto pt-BR (e tracebacks Python contêm caracteres curvos) que
        # quebram o codec cp1252 default do Windows quando há falha.
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd) if cwd is not None else None,
        timeout=timeout,
    )


def _copiar_perfis_reais(destino_kiro_agents: Path) -> None:
    """Copia os 9 perfis reais para ``destino_kiro_agents``."""
    if not DIR_AGENTES_REAL.is_dir():
        pytest.skip(
            f"diretório de agentes reais não encontrado: {DIR_AGENTES_REAL}; "
            "rode a Task 3 antes para criar os 9 arquivos."
        )
    destino_kiro_agents.mkdir(parents=True, exist_ok=True)
    for nome in NOMES_AGENTES:
        origem = DIR_AGENTES_REAL / f"{nome}.md"
        if not origem.is_file():
            pytest.skip(f"arquivo real ausente: {origem}")
        shutil.copy(origem, destino_kiro_agents / f"{nome}.md")


# ---------------------------------------------------------------------------
# 1. Estrutura geral (--help, subcomando inválido)
# ---------------------------------------------------------------------------


class TestCliEstrutura:
    def test_cli_help(self) -> None:
        """``caos --help`` deve listar todos os 7 subcomandos e retornar 0."""
        res = _run_cli("--help", timeout=15)
        assert res.returncode == 0, (
            f"--help falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        # Apenas o stdout precisa conter os subcomandos (não stderr).
        for esperado in (
            "init",
            "manifesto",
            "hydra",
            "debate",
            "perfil",
            "cache",
            "budget",
        ):
            assert esperado in res.stdout, (
                f"--help não cita o subcomando {esperado!r}: {res.stdout!r}"
            )

    def test_cli_subcomando_invalido(self) -> None:
        """Subcomando desconhecido deve sair com código != 0."""
        res = _run_cli("subcomando-que-nao-existe", timeout=15)
        assert res.returncode != 0
        # argparse imprime erro em stderr.
        assert "invalid choice" in res.stderr or "subcomando" in res.stderr

    def test_cli_sem_argumentos_falha(self) -> None:
        """Sem subcomando a CLI deve falhar (argparse marca ``required=True``)."""
        res = _run_cli(timeout=15)
        assert res.returncode != 0


# ---------------------------------------------------------------------------
# 2. caos init (teste isolado)
# ---------------------------------------------------------------------------


class TestCliInit:
    def test_cli_init_em_tmp_cria_estrutura(self, tmp_path: Path) -> None:
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli("init", "--root", str(raiz), timeout=30)
        assert res.returncode == 0, (
            f"init falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert (raiz / ".kiro" / "agents").is_dir()
        assert (raiz / "dados" / "MNQ").is_dir()
        # ``.gitkeep`` foi criado no placeholder ``05_BACKTEST``.
        assert (raiz / "05_BACKTEST" / ".gitkeep").is_file()

    def test_cli_init_idempotente(self, tmp_path: Path) -> None:
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        for _ in range(2):
            res = _run_cli("init", "--root", str(raiz), timeout=30)
            assert res.returncode == 0


# ---------------------------------------------------------------------------
# 3. caos hydra sync (mocked via monkeypatch in-process)
# ---------------------------------------------------------------------------


class _SubprocessGitFake:
    """Fake de ``subprocess.run`` que simula ``git clone/fetch/reset/rev-parse``.

    O objetivo é evitar acesso à internet em testes. Cada chamada inspeciona
    ``cmd[1]`` (o subcomando do git) e devolve um
    :class:`subprocess.CompletedProcess` adequado.
    """

    SHA_FAKE: str = "0123456789abcdef0123456789abcdef01234567"

    def __init__(self) -> None:
        self.chamadas: list[list[str]] = []

    def __call__(
        self,
        cmd: Sequence[str],
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]:
        self.chamadas.append(list(cmd))
        # O caller de hydra_sync passa ``capture_output=True`` → stdout/stderr
        # devem ser bytes no ``CompletedProcess`` resultante.
        if len(cmd) < 2:
            return subprocess.CompletedProcess(
                args=list(cmd), returncode=1, stdout=b"", stderr=b"comando vazio"
            )
        # ``cmd[0] == 'git'``; ``cmd[1]`` pode ser ``-C`` (caso fetch/reset/rev-parse)
        # ou diretamente o subcomando (caso clone).
        idx_subcomando = 1
        if cmd[1] == "-C":
            # Salta ``-C <path>`` para chegar ao subcomando.
            idx_subcomando = 3
        subcomando = cmd[idx_subcomando] if idx_subcomando < len(cmd) else ""

        if subcomando == "clone":
            # Em ``git clone --branch main --depth 1 <url> <path>``, o caminho
            # é o último argumento.
            destino = Path(cmd[-1])
            destino.mkdir(parents=True, exist_ok=True)
            (destino / ".git").mkdir(exist_ok=True)
            (destino / "README.md").write_text(
                "fake hydra clone", encoding="utf-8"
            )
            return subprocess.CompletedProcess(
                args=list(cmd), returncode=0, stdout=b"", stderr=b""
            )
        if subcomando in ("fetch", "reset"):
            return subprocess.CompletedProcess(
                args=list(cmd), returncode=0, stdout=b"", stderr=b""
            )
        if subcomando == "rev-parse":
            return subprocess.CompletedProcess(
                args=list(cmd),
                returncode=0,
                stdout=(self.SHA_FAKE + "\n").encode("utf-8"),
                stderr=b"",
            )
        # Subcomando inesperado: falha silenciosa (returncode 1).
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=1,
            stdout=b"",
            stderr=f"subcomando git nao mockado: {subcomando}".encode("utf-8"),
        )


class TestCliHydraSync:
    def test_cli_hydra_sync_mocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mocka ``subprocess.run`` em ``caos.hydra_sync`` e valida saída humana."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        # ``HydraReferenceSync`` exige que a raiz exista.
        from caos import hydra_sync

        fake = _SubprocessGitFake()
        monkeypatch.setattr(hydra_sync.subprocess, "run", fake)

        # Chama em-processo para que o monkeypatch valha.
        codigo = caos_main.cli(["hydra", "sync", "--root", str(raiz)])
        assert codigo == 0
        # Ao menos clone + rev-parse foram invocados.
        assert any(
            "clone" in chamada for chamada in fake.chamadas
        ), f"esperava 'git clone' nas chamadas, recebeu {fake.chamadas}"
        assert any(
            "rev-parse" in chamada for chamada in fake.chamadas
        ), f"esperava 'git rev-parse' nas chamadas, recebeu {fake.chamadas}"
        # Cópia local foi criada.
        clone = raiz / "04_CODIGO" / "ninjascript" / "reference_hydra"
        assert clone.is_dir()
        # Nota_Zettel foi gravada com hash mockado.
        nota = (
            raiz
            / "CAOS_Zettelkasten"
            / "API_NinjaTrader_8_Reference"
            / "Hydra_Reference_Index.md"
        )
        assert nota.is_file()
        conteudo_nota = nota.read_text(encoding="utf-8")
        assert _SubprocessGitFake.SHA_FAKE in conteudo_nota

    def test_cli_hydra_sync_raiz_inexistente(self, tmp_path: Path) -> None:
        """Raiz inexistente deve falhar com mensagem clara, exit != 0."""
        raiz_inexistente = tmp_path / "nao-existe"
        res = _run_cli(
            "hydra",
            "sync",
            "--root",
            str(raiz_inexistente),
            timeout=15,
        )
        assert res.returncode != 0


# ---------------------------------------------------------------------------
# 4. caos debate {iniciar,fechar} (Spec 5)
# ---------------------------------------------------------------------------


class TestCliDebate:
    """Testa o fluxo `caos debate iniciar` (Spec 5 — Task 2).

    O subgrupo `caos debate fechar` é testado em
    `tests/unit/test_caos_debate_iniciar_fechar.py` (Spec 5 — Task 4),
    que cobre o caminho-feliz com Git real. Aqui só validamos a CLI no
    nível de argparse + smoke do iniciar.
    """

    def test_cli_debate_iniciar_cria_starter(self, tmp_path: Path) -> None:
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli(
            "debate",
            "iniciar",
            "estudo-orb-baseline",
            "--gatilho",
            "G3",
            "--altera-exposicao",
            "--root",
            str(raiz),
            timeout=15,
        )
        assert res.returncode == 0, (
            f"debate iniciar falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "Debate iniciado." in res.stdout
        assert "estudo-orb-baseline" in res.stdout
        # Arquivo deve ter sido criado em CAOS_Council/debates/.
        debates = list((raiz / "CAOS_Council" / "debates").glob("*.md"))
        assert len(debates) == 1
        assert debates[0].name.endswith("-estudo-orb-baseline.md")

    def test_cli_debate_iniciar_slug_invalido_falha(self, tmp_path: Path) -> None:
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli(
            "debate",
            "iniciar",
            "Slug Invalido com espacos",
            "--root",
            str(raiz),
            timeout=15,
        )
        assert res.returncode == 1
        assert "slug-invalido" in res.stderr or "slug" in res.stderr.lower()

    def test_cli_debate_iniciar_sem_slug_falha(self) -> None:
        """Sem o argumento `slug` argparse deve falhar."""
        res = _run_cli("debate", "iniciar", timeout=15)
        assert res.returncode != 0

    def test_cli_debate_help_lista_iniciar_fechar(self) -> None:
        res = _run_cli("debate", "--help", timeout=15)
        assert res.returncode == 0
        assert "iniciar" in res.stdout
        assert "fechar" in res.stdout


# ---------------------------------------------------------------------------
# 5. caos perfil validar
# ---------------------------------------------------------------------------


class TestCliPerfilValidar:
    def _preparar_workspace_com_perfis(self, tmp_path: Path) -> Path:
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        _copiar_perfis_reais(raiz / ".kiro" / "agents")
        return raiz

    def test_cli_perfil_validar_todos(self, tmp_path: Path) -> None:
        """Sem argumento valida os 9 perfis e retorna 0."""
        raiz = self._preparar_workspace_com_perfis(tmp_path)
        res = _run_cli("perfil", "validar", "--root", str(raiz), timeout=30)
        assert res.returncode == 0, (
            f"perfil validar falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        # Stdout deve listar os 9 agentes com modelo.
        for nome in NOMES_AGENTES:
            assert nome in res.stdout, (
                f"saída não cita o agente {nome}: {res.stdout!r}"
            )
        assert "modelo=" in res.stdout

    def test_cli_perfil_validar_nome_especifico(self, tmp_path: Path) -> None:
        """Com nome valida apenas aquele perfil."""
        raiz = self._preparar_workspace_com_perfis(tmp_path)
        res = _run_cli(
            "perfil", "validar", "Athena", "--root", str(raiz), timeout=15
        )
        assert res.returncode == 0, (
            f"perfil validar Athena falhou: "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "Athena" in res.stdout
        assert "claude-opus-4.7" in res.stdout

    def test_cli_perfil_validar_invalido(self, tmp_path: Path) -> None:
        """Perfil com modelo divergente: exit 1."""
        raiz = self._preparar_workspace_com_perfis(tmp_path)
        # Adultera o perfil de Athena para ter modelo errado.
        athena = raiz / ".kiro" / "agents" / "Athena.md"
        original = athena.read_text(encoding="utf-8")
        adulterado = original.replace(
            "modelo: claude-opus-4.7",
            "modelo: claude-haiku-4.5",
        )
        assert adulterado != original, (
            "fixture esperada incluindo 'modelo: claude-opus-4.7' não "
            f"encontrada em {athena}"
        )
        athena.write_text(adulterado, encoding="utf-8")
        res = _run_cli(
            "perfil",
            "validar",
            "--root",
            str(raiz),
            timeout=30,
        )
        assert res.returncode == 1
        # Categoria de falha deve aparecer no stderr.
        assert (
            "modelo-divergente" in res.stderr
            or "validacao-pydantic" in res.stderr
        )

    def test_cli_perfil_validar_sem_diretorio(self, tmp_path: Path) -> None:
        """Sem ``.kiro/agents`` a CLI deve falhar com mensagem orientativa."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli(
            "perfil", "validar", "--root", str(raiz), timeout=15
        )
        assert res.returncode == 1
        assert "ausente" in res.stderr.lower() or "init" in res.stderr.lower()

    def test_cli_perfil_validar_nome_inexistente(self, tmp_path: Path) -> None:
        """Nome de agente sem arquivo correspondente: exit 1."""
        raiz = self._preparar_workspace_com_perfis(tmp_path)
        res = _run_cli(
            "perfil",
            "validar",
            "Inexistente",
            "--root",
            str(raiz),
            timeout=15,
        )
        assert res.returncode == 1


# ---------------------------------------------------------------------------
# 6. caos cache stats
# ---------------------------------------------------------------------------


class TestCliCacheStats:
    def test_cli_cache_stats_vazio(self, tmp_path: Path) -> None:
        """Sem entradas, retorna 0 e mostra 0 entradas."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli("cache", "stats", "--root", str(raiz), timeout=15)
        assert res.returncode == 0, (
            f"cache stats falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "0 entradas" in res.stdout

    def test_cli_cache_stats_com_entradas(self, tmp_path: Path) -> None:
        """Pre-popula 2 arquivos JSON e valida contagem + tamanho."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        diretorio = raiz / "CAOS_Orchestrator" / ".cache"
        diretorio.mkdir(parents=True)
        bytes_total = 0
        for nome in ("a" * 64, "b" * 64):  # 64 hex-like chars (basta nome único)
            payload = {"chave": nome, "fake": True}
            bruto = json.dumps(payload, indent=2).encode("utf-8")
            # ``write_bytes`` evita a tradução CRLF do Windows; o CLI
            # reporta o tamanho real em disco via ``stat().st_size``.
            (diretorio / f"{nome}.json").write_bytes(bruto)
            bytes_total += len(bruto)
        res = _run_cli("cache", "stats", "--root", str(raiz), timeout=15)
        assert res.returncode == 0
        assert "2 entradas" in res.stdout
        assert f"tamanho total: {bytes_total} bytes" in res.stdout


# ---------------------------------------------------------------------------
# 7. caos budget status
# ---------------------------------------------------------------------------


class TestCliBudgetStatus:
    def test_cli_budget_status_dia_sem_consumo(self, tmp_path: Path) -> None:
        """Dia sem arquivo correspondente: mensagem 'sem consumo'."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli(
            "budget",
            "status",
            "--root",
            str(raiz),
            "--data",
            "2099-12-31",
            timeout=15,
        )
        assert res.returncode == 0
        assert "sem consumo" in res.stdout.lower()

    def test_cli_budget_status_com_consumo(self, tmp_path: Path) -> None:
        """Pre-cria JSON do dia e valida formatação por agente."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        diretorio = raiz / "CAOS_Orchestrator" / ".budget"
        diretorio.mkdir(parents=True)
        dia = "2026-01-15"
        payload = {
            "dia": dia,
            "agentes": {
                "Athena": {
                    "agente": "Athena",
                    "tokens_input_consumidos": 100_000,
                    "tokens_output_consumidos": 50_000,
                    "tokens_total_consumidos": 150_000,
                    "orcamento_diario_tokens": 1_500_000,
                },
                "Cerberus": {
                    "agente": "Cerberus",
                    "tokens_input_consumidos": 20_000,
                    "tokens_output_consumidos": 10_000,
                    "tokens_total_consumidos": 30_000,
                    "orcamento_diario_tokens": 800_000,
                },
            },
        }
        (diretorio / f"{dia}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        res = _run_cli(
            "budget",
            "status",
            "--root",
            str(raiz),
            "--data",
            dia,
            timeout=15,
        )
        assert res.returncode == 0, (
            f"budget status falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "Athena" in res.stdout
        assert "Cerberus" in res.stdout
        # Saldo restante: 1500000 - 150000 = 1350000.
        assert "1350000" in res.stdout
        # Total do Cerberus.
        assert "30000" in res.stdout

    def test_cli_budget_status_data_invalida(self, tmp_path: Path) -> None:
        """Formato de --data inválido deve sair com código != 0."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        res = _run_cli(
            "budget",
            "status",
            "--root",
            str(raiz),
            "--data",
            "31/12/2099",
            timeout=15,
        )
        assert res.returncode != 0
        assert "data" in res.stderr.lower()

    def test_cli_budget_status_default_hoje_utc(self, tmp_path: Path) -> None:
        """Sem ``--data`` usa hoje UTC: encontra arquivo se existir."""
        raiz = tmp_path / "workspace"
        raiz.mkdir()
        diretorio = raiz / "CAOS_Orchestrator" / ".budget"
        diretorio.mkdir(parents=True)
        hoje = datetime.now(timezone.utc).date().isoformat()
        payload = {
            "dia": hoje,
            "agentes": {
                "Hermes": {
                    "agente": "Hermes",
                    "tokens_input_consumidos": 1,
                    "tokens_output_consumidos": 2,
                    "tokens_total_consumidos": 3,
                    "orcamento_diario_tokens": 1_200_000,
                }
            },
        }
        (diretorio / f"{hoje}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        res = _run_cli("budget", "status", "--root", str(raiz), timeout=15)
        assert res.returncode == 0
        assert "Hermes" in res.stdout
        assert hoje in res.stdout
