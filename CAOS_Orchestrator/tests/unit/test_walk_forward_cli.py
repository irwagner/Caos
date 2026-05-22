"""Testes unitários do subcomando ``caos walk-forward`` (Spec 2 — Task 8).

Cobre **R9** do ``requirements.md`` do Spec 2:

- R9.1: ``caos walk-forward run --estrategia <import_path>
  --identificador <AAAA-MM-DD-NN> [--config <yaml>] [--root <path>]``.
- R9.2: ``caos walk-forward status [--root <path>] [--id <id>]`` lista
  os relatórios gerados em ``05_BACKTEST/walk_forward/relatorios/``.
- R9.3: estratégia desconhecida (import path inválido) sai com exit
  code 1 e mensagem orientativa em pt-BR.

Cenários cobertos:

1. ``caos --help`` cita o subcomando ``walk-forward``.
2. ``caos walk-forward run`` com fixture sintético + manifesto pré-construído
   executa fim-a-fim usando :class:`EstrategiaExemplo`, grava
   ``resultado.json`` + ``relatorio.md`` no diretório esperado e retorna 0.
3. ``caos walk-forward status`` lista o relatório recém-gerado, mostrando
   identificador, status e estratégia.
4. ``caos walk-forward status --id <id>`` filtra um relatório específico.
5. ``caos walk-forward run`` com import path inválido sai com exit code 1.
6. ``caos walk-forward run`` com config YAML carrega a configuração do
   arquivo (treino/teste customizados).

Plataforma alvo: Windows + cmd. Idioma: pt-BR.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from caos.data_manifest import DataManifestManager

CSV_HEADER = "timestamp,open,high,low,close,volume\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str,
    cwd: Optional[Path] = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Executa ``python -m caos.main <args>`` e devolve o resultado."""
    cmd: list[str] = [sys.executable, "-m", "caos.main", *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd) if cwd is not None else None,
        timeout=timeout,
    )


def _construir_workspace_com_dados(
    raiz_pai: Path,
    *,
    n_dias_uteis: int = 90,
    inicio: str = "2026-01-02",
) -> Path:
    """Cria um workspace mínimo com ``dados/MNQ/`` populado e ``manifesto.json``.

    Retorna o path da raiz do workspace.
    """
    raiz = raiz_pai / "workspace"
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "05_BACKTEST" / "walk_forward" / "relatorios").mkdir(
        parents=True, exist_ok=True
    )
    raiz_dados = raiz / "dados" / "MNQ"
    raiz_dados.mkdir(parents=True, exist_ok=True)

    timestamps = pd.bdate_range(inicio, periods=n_dias_uteis, tz="UTC")
    linhas: list[str] = []
    for i, ts in enumerate(timestamps):
        preco_open = 21000.0 + i
        preco_high = preco_open + 1.0
        preco_low = preco_open - 1.0
        preco_close = preco_open + 0.5
        volume = 1000.0
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        linhas.append(
            f"{ts_iso},{preco_open},{preco_high},{preco_low},"
            f"{preco_close},{volume}"
        )
    arquivo = raiz_dados / "MNQ-sintetico.csv"
    arquivo.write_text(CSV_HEADER + "\n".join(linhas) + "\n", encoding="utf-8")
    DataManifestManager(raiz_dados=raiz_dados).build()
    return raiz


# ---------------------------------------------------------------------------
# 1. Estrutura geral — --help cita walk-forward
# ---------------------------------------------------------------------------


class TestCliWalkForwardHelp:
    def test_help_raiz_cita_walk_forward(self) -> None:
        """``caos --help`` deve listar o subcomando ``walk-forward``."""
        res = _run_cli("--help", timeout=15)
        assert res.returncode == 0, (
            f"--help falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "walk-forward" in res.stdout

    def test_help_walk_forward_lista_run_e_status(self) -> None:
        """``caos walk-forward --help`` deve listar ``run`` e ``status``."""
        res = _run_cli("walk-forward", "--help", timeout=15)
        assert res.returncode == 0, (
            f"walk-forward --help falhou: stdout={res.stdout!r} "
            f"stderr={res.stderr!r}"
        )
        assert "run" in res.stdout
        assert "status" in res.stdout

    def test_help_walk_forward_run_cita_flags(self) -> None:
        """``caos walk-forward run --help`` deve citar as flags esperadas."""
        res = _run_cli("walk-forward", "run", "--help", timeout=15)
        assert res.returncode == 0
        assert "--estrategia" in res.stdout
        assert "--identificador" in res.stdout
        assert "--config" in res.stdout
        assert "--commit" in res.stdout


# ---------------------------------------------------------------------------
# 2. caos walk-forward run — caminho feliz com EstrategiaExemplo
# ---------------------------------------------------------------------------


class TestCliWalkForwardRun:
    def test_run_caminho_feliz_executa_e_grava_relatorio(
        self, tmp_path: Path
    ) -> None:
        """``run`` executa o engine e grava ``resultado.json`` + ``relatorio.md``."""
        raiz = _construir_workspace_com_dados(tmp_path)
        identificador = "2026-04-01-01"

        res = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos:EstrategiaExemplo",
            "--identificador",
            identificador,
            "--root",
            str(raiz),
            timeout=120,
        )

        assert res.returncode == 0, (
            f"run falhou: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        # Saída humana cita o identificador e o status concluído.
        assert identificador in res.stdout
        assert "concluido" in res.stdout
        assert "EstrategiaExemplo" in res.stdout

        # Relatório foi escrito no layout canônico.
        diretorio = (
            raiz
            / "05_BACKTEST"
            / "walk_forward"
            / "relatorios"
            / identificador
        )
        assert diretorio.is_dir(), (
            f"diretório do relatório não criado: {diretorio}"
        )
        arquivo_json = diretorio / "resultado.json"
        arquivo_md = diretorio / "relatorio.md"
        assert arquivo_json.is_file()
        assert arquivo_md.is_file()

        # Conteúdo do JSON: status concluido e identificador correto.
        payload = json.loads(arquivo_json.read_text(encoding="utf-8"))
        assert payload["identificador"] == identificador
        assert payload["status"] == "concluido"
        assert payload["estrategia"] == "EstrategiaExemplo"
        assert len(payload["janelas"]) >= 1

    def test_run_estrategia_inexistente_falha_com_exit_1(
        self, tmp_path: Path
    ) -> None:
        """Estratégia desconhecida ⇒ exit 1 com mensagem em pt-BR (R9.3)."""
        raiz = _construir_workspace_com_dados(tmp_path)
        res = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "modulo.que.nao.existe:Fantasma",
            "--identificador",
            "2026-04-01-02",
            "--root",
            str(raiz),
            timeout=60,
        )
        assert res.returncode == 1, (
            f"esperava exit 1, recebeu {res.returncode}; "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "ERRO" in res.stderr or "erro" in res.stderr.lower()
        # Mensagem deve indicar que o módulo não foi encontrado.
        assert "modulo.que.nao.existe" in res.stderr

    def test_run_estrategia_sem_dois_pontos_falha(
        self, tmp_path: Path
    ) -> None:
        """Formato sem ``:`` é rejeitado com mensagem clara."""
        raiz = _construir_workspace_com_dados(tmp_path)
        res = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos.EstrategiaExemplo",
            "--identificador",
            "2026-04-01-03",
            "--root",
            str(raiz),
            timeout=30,
        )
        assert res.returncode == 1
        assert "pacote.modulo:Classe" in res.stderr

    def test_run_dados_inexistentes_falha_com_mensagem(
        self, tmp_path: Path
    ) -> None:
        """Sem ``dados/MNQ/`` o subcomando falha com sugestão de ``caos init``."""
        raiz = tmp_path / "ws-vazio"
        raiz.mkdir()
        res = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos:EstrategiaExemplo",
            "--identificador",
            "2026-04-01-04",
            "--root",
            str(raiz),
            timeout=30,
        )
        assert res.returncode == 1
        # Sem dados, a mensagem deve indicar o problema.
        assert "dados" in res.stderr.lower() or "init" in res.stderr.lower()

    def test_run_com_config_yaml_carrega_parametros(
        self, tmp_path: Path
    ) -> None:
        """Config YAML customiza treino/teste e a execução é bem-sucedida."""
        raiz = _construir_workspace_com_dados(tmp_path, n_dias_uteis=120)
        identificador = "2026-04-01-05"
        config_path = tmp_path / "wf-config.yaml"
        config_path.write_text(
            "tamanho_treino_dias_uteis: 80\n"
            "tamanho_teste_dias_uteis: 20\n"
            "granularidade: 1m\n"
            "seed: 7\n",
            encoding="utf-8",
        )

        res = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos:EstrategiaExemplo",
            "--identificador",
            identificador,
            "--config",
            str(config_path),
            "--root",
            str(raiz),
            timeout=120,
        )

        assert res.returncode == 0, (
            f"run --config falhou: stdout={res.stdout!r} "
            f"stderr={res.stderr!r}"
        )
        arquivo_json = (
            raiz
            / "05_BACKTEST"
            / "walk_forward"
            / "relatorios"
            / identificador
            / "resultado.json"
        )
        payload = json.loads(arquivo_json.read_text(encoding="utf-8"))
        assert payload["configuracao"]["tamanho_treino_dias_uteis"] == 80
        assert payload["configuracao"]["tamanho_teste_dias_uteis"] == 20
        assert payload["configuracao"]["seed"] == 7

    def test_run_identificador_invalido_falha(
        self, tmp_path: Path
    ) -> None:
        """Identificador fora do padrão AAAA-MM-DD-NN é rejeitado pelo model."""
        raiz = _construir_workspace_com_dados(tmp_path)
        res = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos:EstrategiaExemplo",
            "--identificador",
            "id-invalido",
            "--root",
            str(raiz),
            timeout=60,
        )
        assert res.returncode != 0


# ---------------------------------------------------------------------------
# 3. caos walk-forward status
# ---------------------------------------------------------------------------


class TestCliWalkForwardStatus:
    def test_status_sem_relatorios_imprime_mensagem(
        self, tmp_path: Path
    ) -> None:
        """``status`` em workspace vazio reporta ausência de relatórios."""
        raiz = tmp_path / "ws"
        raiz.mkdir()
        res = _run_cli(
            "walk-forward",
            "status",
            "--root",
            str(raiz),
            timeout=15,
        )
        assert res.returncode == 0
        assert "nenhum" in res.stdout.lower()

    def test_status_lista_relatorio_recem_gerado(
        self, tmp_path: Path
    ) -> None:
        """Após ``run``, ``status`` lista o relatório com identificador + status."""
        raiz = _construir_workspace_com_dados(tmp_path)
        identificador = "2026-04-02-01"

        res_run = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos:EstrategiaExemplo",
            "--identificador",
            identificador,
            "--root",
            str(raiz),
            timeout=120,
        )
        assert res_run.returncode == 0, (
            f"run falhou: stdout={res_run.stdout!r} stderr={res_run.stderr!r}"
        )

        res_status = _run_cli(
            "walk-forward",
            "status",
            "--root",
            str(raiz),
            timeout=15,
        )
        assert res_status.returncode == 0
        assert identificador in res_status.stdout
        assert "concluido" in res_status.stdout
        assert "EstrategiaExemplo" in res_status.stdout

    def test_status_filtro_por_id_encontrado(self, tmp_path: Path) -> None:
        """``--id`` filtra um relatório específico já gerado."""
        raiz = _construir_workspace_com_dados(tmp_path)
        identificador = "2026-04-02-02"

        res_run = _run_cli(
            "walk-forward",
            "run",
            "--estrategia",
            "caos.walk_forward.estrategias.exemplos:EstrategiaExemplo",
            "--identificador",
            identificador,
            "--root",
            str(raiz),
            timeout=120,
        )
        assert res_run.returncode == 0

        res_status = _run_cli(
            "walk-forward",
            "status",
            "--root",
            str(raiz),
            "--id",
            identificador,
            timeout=15,
        )
        assert res_status.returncode == 0
        assert identificador in res_status.stdout

    def test_status_filtro_por_id_nao_encontrado_falha(
        self, tmp_path: Path
    ) -> None:
        """``--id`` inexistente retorna exit 1 com mensagem em stderr."""
        raiz = tmp_path / "ws"
        raiz.mkdir()
        res = _run_cli(
            "walk-forward",
            "status",
            "--root",
            str(raiz),
            "--id",
            "9999-12-31-99",
            timeout=15,
        )
        assert res.returncode == 1
        assert "9999-12-31-99" in res.stderr
