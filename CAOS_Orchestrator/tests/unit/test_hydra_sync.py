"""Testes unitários do :mod:`caos.hydra_sync` (Task 13).

Cobre R13.1–R13.5:

- Clone inicial bem-sucedido com mock de ``subprocess.run`` (R13.2).
- Update incremental quando o clone já existe (R13.2).
- Timeout categorizado preservando a cópia local (R13.3).
- Repositório inacessível categorizado (R13.3).
- Binário ``git`` ausente (R13.3).
- Pasta ``reference_hydra/`` existente sem ``.git/`` é tratada como
  ``repositorio-inacessivel`` e o conteúdo é preservado (R13.3).
- ``Hydra_Reference_Index.md`` é criada e atualizada (R13.1).
- Guard de cópia (R13.5): bloqueia sem decisão, bloqueia decisão sem
  rationale apropriado, autoriza decisão com rationale apropriado.

Os testes nunca executam ``git clone`` real: todos os caminhos críticos
são exercitados via ``unittest.mock.patch`` sobre
``caos.hydra_sync.subprocess.run``.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest
import yaml

from caos.hydra_sync import (
    DIR_REFERENCE_HYDRA,
    HYDRA_BRANCH,
    HYDRA_URL,
    NOTA_HYDRA_INDEX,
    FalhaSync,
    HydraReferenceSync,
    ResultadoSync,
    ResultadoValidacaoCopia,
)
from caos.models import (
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
)

# ---------------------------------------------------------------------------
# Constantes auxiliares
# ---------------------------------------------------------------------------

#: SHA-1 hex sintético usado nos testes.
HASH_FAKE_1 = "a" * 40
HASH_FAKE_2 = "b" * 40


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ler_frontmatter(caminho: Path) -> dict[str, Any]:
    """Extrai e parseia o bloco YAML do início de um arquivo Markdown."""
    texto = caminho.read_text(encoding="utf-8")
    assert texto.startswith("---\n"), (
        f"arquivo {caminho} não começa com '---'"
    )
    fim = texto.find("\n---", 4)
    assert fim > 0, f"arquivo {caminho} não fecha o frontmatter com '---'"
    return yaml.safe_load(texto[4:fim])


def _construir_decisao_minima(
    *,
    rationale: str = "Decisão genérica.",
    aprovado_walk_forward: bool = False,
) -> DecisaoDoConselho:
    """Constrói uma ``DecisaoDoConselho`` válida e mínima para os testes."""
    proposta = Proposta(
        id="P1",
        autor="Athena",
        resumo="Resumo curto da proposta",
        conteudo="Conteúdo da proposta",
        confianca=80,
    )
    return DecisaoDoConselho(
        identificador="2026-05-14-01",
        debate_relacionado="2026-05-14-01-debate.md",
        agentes_participantes=["Athena"],
        propostas=[proposta],
        vetos=[],
        decisao_final=DecisaoFinal(
            proposta_aceita="P1",
            rationale=rationale,
        ),
        links_zettel=["[[Hydra_Reference_Index]]"],
        aprovado_walk_forward=aprovado_walk_forward,
        reproduzivel="true",
        regressao_detectada=False,
        status="concluido",
    )


class _CompletedProcessFake:
    """Stub mínimo de :class:`subprocess.CompletedProcess` para os mocks."""

    def __init__(
        self,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _agendar_respostas(respostas: list[Any]):
    """Devolve um ``side_effect`` que consome ``respostas`` em ordem.

    Cada item pode ser:

    - :class:`_CompletedProcessFake` — retornado como resultado normal.
    - :class:`Exception` — lançado.
    - ``callable(cmd, *args, **kwargs)`` — invocado com ``(cmd, ...)`` e seu
      retorno propagado (suporta efeitos colaterais como criar ``.git/``).
    """
    iterador = iter(respostas)

    def _side_effect(cmd, *args, **kwargs):
        proximo = next(iterador)
        if isinstance(proximo, BaseException):
            raise proximo
        if callable(proximo):
            return proximo(cmd, *args, **kwargs)
        return proximo

    return _side_effect


# ---------------------------------------------------------------------------
# Construtor
# ---------------------------------------------------------------------------


class TestConstrutor:
    """Validações triviais do construtor."""

    def test_raiz_inexistente_lanca(self, tmp_path: Path) -> None:
        inexistente = tmp_path / "nao_existe"
        with pytest.raises(ValueError):
            HydraReferenceSync(raiz_workspace=inexistente)

    def test_url_vazia_lanca(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            HydraReferenceSync(raiz_workspace=tmp_path, url="   ")

    def test_branch_vazio_lanca(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            HydraReferenceSync(raiz_workspace=tmp_path, branch="")

    def test_propriedades_default(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        assert sync.url == HYDRA_URL
        assert sync.branch == HYDRA_BRANCH
        assert sync.caminho_clone == (
            tmp_path.resolve() / DIR_REFERENCE_HYDRA
        )
        assert sync.caminho_nota_index == (
            tmp_path.resolve() / NOTA_HYDRA_INDEX
        )


# ---------------------------------------------------------------------------
# Sincronização — clone inicial
# ---------------------------------------------------------------------------


class TestSincronizarCloneInicial:
    """Cobre o caminho feliz: caminho_clone não existe."""

    def test_sincronizar_clone_inicial_mocked(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.caminho_clone

        def _simular_clone(cmd, *_args, **_kwargs):
            # Cria diretório + .git/ placeholder, simulando ``git clone``.
            assert cmd[0] == "git" and cmd[1] == "clone"
            caminho.mkdir(parents=True, exist_ok=True)
            (caminho / ".git").mkdir()
            (caminho / "README.md").write_text(
                "Hydra fake content\n", encoding="utf-8"
            )
            (caminho / "strategies").mkdir()
            return _CompletedProcessFake(returncode=0)

        respostas = [
            _simular_clone,  # git clone
            _CompletedProcessFake(
                returncode=0,
                stdout=(HASH_FAKE_1 + "\n").encode("utf-8"),
            ),  # git rev-parse HEAD
        ]

        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas(respostas),
        ):
            resultado = sync.sincronizar()

        assert isinstance(resultado, ResultadoSync)
        assert resultado.sucesso is True
        assert resultado.cloned_now is True
        assert resultado.hash_commit == HASH_FAKE_1
        assert resultado.caminho_clone == caminho
        assert resultado.falha is None

        # A nota deve ter sido criada com o hash.
        nota = sync.caminho_nota_index
        assert nota.is_file()
        front = _ler_frontmatter(nota)
        assert front["url"] == HYDRA_URL
        assert front["branch"] == HYDRA_BRANCH
        assert front["hash_commit"] == HASH_FAKE_1
        # Auto-discovery: 'strategies' (e não '.git') deve aparecer.
        caminhos_subdir = [
            entrada["caminho"] for entrada in front["subdiretorios"]
        ]
        assert "strategies" in caminhos_subdir
        assert ".git" not in caminhos_subdir

    def test_clone_inicial_invoca_git_com_branch_e_depth(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.caminho_clone
        chamadas: list[list[str]] = []

        def _simular_clone(cmd, *_args, **_kwargs):
            chamadas.append(list(cmd))
            caminho.mkdir(parents=True, exist_ok=True)
            (caminho / ".git").mkdir()
            return _CompletedProcessFake(returncode=0)

        def _simular_rev_parse(cmd, *_args, **_kwargs):
            chamadas.append(list(cmd))
            return _CompletedProcessFake(
                returncode=0,
                stdout=(HASH_FAKE_1 + "\n").encode("utf-8"),
            )

        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas(
                [_simular_clone, _simular_rev_parse]
            ),
        ):
            sync.sincronizar()

        # Confere que o primeiro comando foi um clone com --branch main e --depth 1.
        clone_cmd = chamadas[0]
        assert clone_cmd[:2] == ["git", "clone"]
        assert "--branch" in clone_cmd
        assert clone_cmd[clone_cmd.index("--branch") + 1] == HYDRA_BRANCH
        assert "--depth" in clone_cmd
        assert clone_cmd[clone_cmd.index("--depth") + 1] == "1"
        assert HYDRA_URL in clone_cmd


# ---------------------------------------------------------------------------
# Sincronização — update existente
# ---------------------------------------------------------------------------


class TestSincronizarUpdate:
    """Cobre o caminho onde o clone já existe e basta atualizar."""

    def test_sincronizar_update_existente(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.caminho_clone

        # Pré-cria caminho_clone com .git/ placeholder.
        caminho.mkdir(parents=True)
        (caminho / ".git").mkdir()
        arquivo_existente = caminho / "preserve_me.txt"
        arquivo_existente.write_text("existente", encoding="utf-8")

        respostas = [
            _CompletedProcessFake(returncode=0),  # git fetch
            _CompletedProcessFake(returncode=0),  # git reset --hard
            _CompletedProcessFake(
                returncode=0,
                stdout=(HASH_FAKE_2 + "\n").encode("utf-8"),
            ),  # git rev-parse HEAD
        ]

        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas(respostas),
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is True
        assert resultado.cloned_now is False
        assert resultado.hash_commit == HASH_FAKE_2
        # Conteúdo preexistente não foi tocado pelo nosso mock (mock não
        # remove arquivos; isso é esperado — o teste valida apenas que
        # ``cloned_now`` é False e o sync passou pelo caminho de update).
        assert arquivo_existente.is_file()


# ---------------------------------------------------------------------------
# Sincronização — falhas categorizadas
# ---------------------------------------------------------------------------


class TestSincronizarFalhas:
    """Cobre R13.3: timeout, rede, repo inacessível, git ausente, sem .git/."""

    def test_sincronizar_timeout(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.caminho_clone

        # Pré-cria a pasta como repo válido para forçar caminho de update;
        # o fetch vai disparar timeout.
        caminho.mkdir(parents=True)
        (caminho / ".git").mkdir()
        sentinela = caminho / "preserve_me.txt"
        sentinela.write_text("local-content", encoding="utf-8")

        timeout_exc = subprocess.TimeoutExpired(
            cmd=["git", "fetch"], timeout=120
        )

        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas([timeout_exc]),
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "timeout"
        # A cópia local foi preservada.
        assert sentinela.is_file()
        assert sentinela.read_text(encoding="utf-8") == "local-content"

    def test_sincronizar_repositorio_inacessivel(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)

        respostas = [
            _CompletedProcessFake(
                returncode=128,
                stderr=b"fatal: unable to access 'https://...': 403\n",
            ),
        ]
        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas(respostas),
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "repositorio-inacessivel"

    def test_sincronizar_falha_de_rede(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)

        respostas = [
            _CompletedProcessFake(
                returncode=128,
                stderr=b"fatal: Could not resolve host: github.com\n",
            ),
        ]
        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas(respostas),
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "rede"

    def test_sincronizar_git_ausente(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)

        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=FileNotFoundError(
                "[WinError 2] git não encontrado"
            ),
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "git-ausente"

    def test_sincronizar_pasta_existe_mas_nao_e_repo(
        self, tmp_path: Path
    ) -> None:
        """R13.3: pasta sem ``.git/`` é tratada como inacessível."""
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.caminho_clone
        caminho.mkdir(parents=True)
        sentinela = caminho / "manual_file.txt"
        sentinela.write_text("manual", encoding="utf-8")

        # Não deve invocar git nenhum: mock que falha o teste se chamado.
        def _fail_if_called(*_args, **_kwargs):  # pragma: no cover
            pytest.fail("subprocess.run não deveria ser chamado")

        with patch(
            "caos.hydra_sync.subprocess.run", side_effect=_fail_if_called
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "repositorio-inacessivel"
        # A pasta e o conteúdo seguem intactos.
        assert caminho.is_dir()
        assert sentinela.is_file()
        assert sentinela.read_text(encoding="utf-8") == "manual"

    def test_timeout_acima_do_limite_lanca(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        with pytest.raises(ValueError):
            sync.sincronizar(timeout_s=200)

    def test_timeout_zero_lanca(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        with pytest.raises(ValueError):
            sync.sincronizar(timeout_s=0)


# ---------------------------------------------------------------------------
# Hydra_Reference_Index.md
# ---------------------------------------------------------------------------


class TestGarantirNotaIndex:
    """Cobre R13.1 — schema da Nota_Zettel ``Hydra_Reference_Index``."""

    def test_garantir_nota_index_cria_arquivo(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.garantir_nota_index(hash_commit=HASH_FAKE_1)
        assert caminho == sync.caminho_nota_index
        assert caminho.is_file()

        front = _ler_frontmatter(caminho)
        assert front["url"] == HYDRA_URL
        assert front["branch"] == HYDRA_BRANCH
        assert front["hash_commit"] == HASH_FAKE_1
        assert isinstance(front["subdiretorios"], list)
        assert front["titulo"] == "Hydra_Reference_Index"
        assert front["area"] == "API_NinjaTrader_8_Reference"
        assert "hydra" in front["tags"]
        # data_criacao em UTC (sufixo Z).
        assert isinstance(front["data_criacao"], (str, datetime))

    def test_garantir_nota_index_atualiza_hash(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        sync.garantir_nota_index(hash_commit=HASH_FAKE_1)
        sync.garantir_nota_index(hash_commit=HASH_FAKE_2)

        front = _ler_frontmatter(sync.caminho_nota_index)
        assert front["hash_commit"] == HASH_FAKE_2

    def test_garantir_nota_index_aceita_hash_none(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        sync.garantir_nota_index(hash_commit=None)
        front = _ler_frontmatter(sync.caminho_nota_index)
        assert front["hash_commit"] is None

    def test_garantir_nota_index_rejeita_hash_invalido(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        with pytest.raises(ValueError):
            sync.garantir_nota_index(hash_commit="naohex")

    def test_garantir_nota_index_subdiretorios_explicitos(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        sync.garantir_nota_index(
            hash_commit=HASH_FAKE_1,
            subdiretorios=["strategies", "indicators"],
        )
        front = _ler_frontmatter(sync.caminho_nota_index)
        caminhos = [e["caminho"] for e in front["subdiretorios"]]
        assert caminhos == ["strategies", "indicators"]

    def test_garantir_nota_index_auto_discovery_com_clone_existente(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        clone = sync.caminho_clone
        clone.mkdir(parents=True)
        (clone / ".git").mkdir()
        (clone / "alpha").mkdir()
        (clone / "bravo").mkdir()
        # Arquivo solto não deve aparecer.
        (clone / "README.md").write_text("doc", encoding="utf-8")

        sync.garantir_nota_index(hash_commit=HASH_FAKE_1)
        front = _ler_frontmatter(sync.caminho_nota_index)
        caminhos = [e["caminho"] for e in front["subdiretorios"]]
        assert caminhos == ["alpha", "bravo"]


# ---------------------------------------------------------------------------
# Guard de cópia (R13.5)
# ---------------------------------------------------------------------------


class TestValidarCopiaDeCodigo:
    """Cobre R13.5 — guard antes de copiar de reference_hydra/ ao código ativo."""

    def test_validar_copia_sem_decisao_bloqueia(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        resultado = sync.validar_copia_de_codigo(
            arquivo_origem_relativo="reference_hydra/strategies/Foo.cs",
            decisao=None,
        )
        assert isinstance(resultado, ResultadoValidacaoCopia)
        assert resultado.autorizado is False
        assert resultado.decisao_id is None
        assert "R13.5" in (resultado.motivo or "")

    def test_validar_copia_com_decisao_sem_rationale_apropriado_bloqueia(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        decisao = _construir_decisao_minima(
            rationale="Decisão genérica que não menciona o caminho."
        )
        resultado = sync.validar_copia_de_codigo(
            arquivo_origem_relativo="reference_hydra/strategies/Foo.cs",
            decisao=decisao,
        )
        assert resultado.autorizado is False
        assert resultado.decisao_id == "2026-05-14-01"
        assert "rationale" in (resultado.motivo or "").lower()

    def test_validar_copia_com_decisao_apropriada_autoriza(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        decisao = _construir_decisao_minima(
            rationale=(
                "Aprovamos a cópia adaptada do arquivo "
                "reference_hydra/strategies/Foo.cs para o código ativo, "
                "com revisão de Hermes."
            )
        )
        resultado = sync.validar_copia_de_codigo(
            arquivo_origem_relativo="reference_hydra/strategies/Foo.cs",
            decisao=decisao,
        )
        assert resultado.autorizado is True
        assert resultado.decisao_id == "2026-05-14-01"
        assert resultado.motivo is None

    def test_validar_copia_origem_fora_de_reference_hydra_autoriza(
        self, tmp_path: Path
    ) -> None:
        """Se a origem nem está em ``reference_hydra/``, R13.5 não se aplica."""
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        resultado = sync.validar_copia_de_codigo(
            arquivo_origem_relativo="strategies/Foo.cs",
            decisao=None,
        )
        assert resultado.autorizado is True

    def test_validar_copia_normaliza_separadores_windows(
        self, tmp_path: Path
    ) -> None:
        """Caminho Windows ``reference_hydra\\Foo.cs`` é tratado igual."""
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        resultado = sync.validar_copia_de_codigo(
            arquivo_origem_relativo="reference_hydra\\strategies\\Foo.cs",
            decisao=None,
        )
        assert resultado.autorizado is False

    def test_validar_copia_origem_vazia_lanca(self, tmp_path: Path) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        with pytest.raises(ValueError):
            sync.validar_copia_de_codigo(
                arquivo_origem_relativo="   ",
                decisao=None,
            )


# ---------------------------------------------------------------------------
# Falha pós-clone na gravação da nota
# ---------------------------------------------------------------------------


class TestFalhaPosClone:
    """Cobre o caminho ``io-erro`` na gravação da nota_index após clone."""

    def test_falha_io_durante_garantir_nota_e_categorizada(
        self, tmp_path: Path
    ) -> None:
        sync = HydraReferenceSync(raiz_workspace=tmp_path)
        caminho = sync.caminho_clone

        def _simular_clone(cmd, *_args, **_kwargs):
            caminho.mkdir(parents=True, exist_ok=True)
            (caminho / ".git").mkdir()
            return _CompletedProcessFake(returncode=0)

        respostas = [
            _simular_clone,
            _CompletedProcessFake(
                returncode=0,
                stdout=(HASH_FAKE_1 + "\n").encode("utf-8"),
            ),
        ]

        with patch(
            "caos.hydra_sync.subprocess.run",
            side_effect=_agendar_respostas(respostas),
        ), patch.object(
            HydraReferenceSync,
            "garantir_nota_index",
            side_effect=OSError("disco cheio"),
        ):
            resultado = sync.sincronizar()

        assert resultado.sucesso is False
        assert resultado.falha is not None
        assert resultado.falha.categoria == "io-erro"
        assert "Hydra_Reference_Index.md" in resultado.falha.mensagem
