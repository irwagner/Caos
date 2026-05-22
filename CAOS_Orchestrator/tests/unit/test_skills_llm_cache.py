"""Testes unitários do :class:`caos.skills.llm_cache.SkillLLMCache`.

Cobre R11.8 e R16.1–R16.7.

Estratégia: usa diretórios temporários em ``tmp_path`` para isolar leituras
e gravações. Os testes não exercitam o caller (Athena) — esta Skill é um
cache puro e a integração com turno fica em outra task.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from caos.models import EntradaCache
from caos.skills.llm_cache import SkillLLMCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Hash hex SHA-256 fixo, útil para os campos hash_prompt/hash_contexto.
HASH_A = hashlib.sha256(b"prompt-A").hexdigest()
HASH_B = hashlib.sha256(b"prompt-B").hexdigest()
HASH_CTX = hashlib.sha256(b"contexto-1").hexdigest()


def _entrada_valida(
    skill: SkillLLMCache,
    *,
    agente: str = "Athena",
    modelo: str = "claude-opus-4.7",
    seed: str = "42",
    resposta: str = "resposta cacheada",
    hash_prompt: str = HASH_A,
    hash_contexto: str = HASH_CTX,
    tokens: int = 100,
) -> EntradaCache:
    """Constrói uma :class:`EntradaCache` válida com chave coerente."""
    chave = skill.computar_chave(
        agente=agente,
        modelo=modelo,
        hash_prompt=hash_prompt,
        hash_contexto=hash_contexto,
        seed=seed,
    )
    return EntradaCache(
        chave=chave,
        agente=agente,
        modelo=modelo,
        seed=seed,
        data_criacao=datetime(2026, 5, 14, 14, 0, 0, tzinfo=timezone.utc),
        tokens_consumidos_estimados=tokens,
        resposta=resposta,
    )


# ---------------------------------------------------------------------------
# computar_chave (R16.2)
# ---------------------------------------------------------------------------


class TestComputarChave:
    def test_chave_deterministica(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        c1 = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="42",
        )
        c2 = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="42",
        )
        assert c1 == c2
        assert len(c1) == 64
        assert all(c in "0123456789abcdef" for c in c1)

    def test_chave_difere_quando_seed_muda(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        c1 = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="42",
        )
        c2 = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="43",
        )
        assert c1 != c2

    def test_chave_difere_quando_prompt_muda(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        c1 = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="42",
        )
        c2 = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_B,
            hash_contexto=HASH_CTX,
            seed="42",
        )
        assert c1 != c2

    def test_chave_aceita_seed_vazia(self, tmp_path: Path) -> None:
        """R16.2: seed vazia representa modelo sem suporte a seed."""
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        c = skill.computar_chave(
            agente="Mister_M",
            modelo="qwen3",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="",
        )
        assert len(c) == 64

    def test_chave_rejeita_hash_prompt_invalido(
        self, tmp_path: Path
    ) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        with pytest.raises(ValueError, match="hash_prompt"):
            skill.computar_chave(
                agente="Athena",
                modelo="claude-opus-4.7",
                hash_prompt="curto",
                hash_contexto=HASH_CTX,
                seed="42",
            )

    def test_chave_rejeita_hash_contexto_invalido(
        self, tmp_path: Path
    ) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        with pytest.raises(ValueError, match="hash_contexto"):
            skill.computar_chave(
                agente="Athena",
                modelo="claude-opus-4.7",
                hash_prompt=HASH_A,
                hash_contexto="X" * 64,  # X não é hex
                seed="42",
            )

    def test_chave_rejeita_seed_nao_string(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        with pytest.raises(ValueError, match="seed"):
            skill.computar_chave(
                agente="Athena",
                modelo="claude-opus-4.7",
                hash_prompt=HASH_A,
                hash_contexto=HASH_CTX,
                seed=42,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# consultar / cache_hit (R16.3, R16.7)
# ---------------------------------------------------------------------------


class TestConsulta:
    def test_consulta_miss_retorna_none(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        chave = skill.computar_chave(
            agente="Athena",
            modelo="claude-opus-4.7",
            hash_prompt=HASH_A,
            hash_contexto=HASH_CTX,
            seed="42",
        )
        assert skill.consultar(chave) is None
        assert skill.cache_hit(chave) is False
        assert skill.warnings() == []

    def test_grava_e_consulta_roundtrip(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        entrada = _entrada_valida(skill, resposta="hello, world")
        skill.gravar(entrada)

        recuperada = skill.consultar(entrada.chave)
        assert recuperada is not None
        assert recuperada.chave == entrada.chave
        assert recuperada.resposta == "hello, world"
        assert recuperada.agente == entrada.agente
        assert recuperada.modelo == entrada.modelo
        assert recuperada.seed == entrada.seed
        assert recuperada.tokens_consumidos_estimados == entrada.tokens_consumidos_estimados
        assert skill.cache_hit(entrada.chave) is True

    def test_consulta_chave_malformada_retorna_none(
        self, tmp_path: Path
    ) -> None:
        """Chave fora do formato hex SHA-256 nunca pode ter hit válido."""
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        assert skill.consultar("nao-eh-hex") is None
        assert skill.consultar("") is None
        assert skill.consultar("z" * 64) is None

    def test_consulta_json_corrompido_retorna_none_com_warning(
        self, tmp_path: Path
    ) -> None:
        """R16.7: JSON inválido → cache miss com warning interno."""
        cache_dir = tmp_path / ".cache"
        skill = SkillLLMCache(diretorio_cache=cache_dir)
        chave = "a" * 64
        (cache_dir / f"{chave}.json").write_text(
            "{ json invalido", encoding="utf-8"
        )

        assert skill.consultar(chave) is None
        warnings = skill.warnings()
        assert len(warnings) == 1
        assert "corrompido" in warnings[0].lower()
        assert chave in warnings[0]

    def test_consulta_arquivo_nao_json_retorna_none(
        self, tmp_path: Path
    ) -> None:
        """Conteúdo arbitrário não-JSON também é tratado como miss."""
        cache_dir = tmp_path / ".cache"
        skill = SkillLLMCache(diretorio_cache=cache_dir)
        chave = "b" * 64
        (cache_dir / f"{chave}.json").write_bytes(
            b"\x00\x01\x02 dados binarios"
        )

        assert skill.consultar(chave) is None
        assert any("corrompido" in w.lower() for w in skill.warnings())

    def test_consulta_schema_incompleto_retorna_none_com_warning(
        self, tmp_path: Path
    ) -> None:
        """JSON válido mas com schema fora do EntradaCache → miss com warning."""
        cache_dir = tmp_path / ".cache"
        skill = SkillLLMCache(diretorio_cache=cache_dir)
        chave = "c" * 64
        # JSON válido mas faltando vários campos obrigatórios.
        (cache_dir / f"{chave}.json").write_text(
            json.dumps({"chave": chave, "agente": "Athena"}),
            encoding="utf-8",
        )

        assert skill.consultar(chave) is None
        assert any("schema" in w.lower() for w in skill.warnings())


# ---------------------------------------------------------------------------
# gravar (R16.4, R16.6)
# ---------------------------------------------------------------------------


class TestGravacao:
    def test_grava_atomico_nao_deixa_tmp(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".cache"
        skill = SkillLLMCache(diretorio_cache=cache_dir)
        entrada = _entrada_valida(skill)
        skill.gravar(entrada)

        # Apenas o arquivo final deve existir no diretório.
        arquivos = list(cache_dir.iterdir())
        assert len(arquivos) == 1
        assert arquivos[0].name == f"{entrada.chave}.json"
        assert not any(p.suffix == ".tmp" for p in cache_dir.rglob("*"))

    def test_grava_json_canonico_e_carregavel(self, tmp_path: Path) -> None:
        """JSON gravado deve ser parseável e conter todos os campos R16.6."""
        cache_dir = tmp_path / ".cache"
        skill = SkillLLMCache(diretorio_cache=cache_dir)
        entrada = _entrada_valida(skill, resposta="abc")
        skill.gravar(entrada)

        bruto = (cache_dir / f"{entrada.chave}.json").read_text(
            encoding="utf-8"
        )
        payload = json.loads(bruto)
        # Campos exigidos por R16.6:
        for campo in (
            "chave",
            "agente",
            "modelo",
            "seed",
            "data_criacao",
            "tokens_consumidos_estimados",
            "resposta",
        ):
            assert campo in payload, f"campo obrigatório ausente: {campo}"

    def test_grava_sobrescreve_entrada_existente(
        self, tmp_path: Path
    ) -> None:
        cache_dir = tmp_path / ".cache"
        skill = SkillLLMCache(diretorio_cache=cache_dir)
        entrada1 = _entrada_valida(skill, resposta="primeira", tokens=10)
        skill.gravar(entrada1)

        # Mesma chave (mesmos componentes), nova resposta.
        entrada2 = _entrada_valida(skill, resposta="segunda", tokens=20)
        assert entrada1.chave == entrada2.chave
        skill.gravar(entrada2)

        recuperada = skill.consultar(entrada2.chave)
        assert recuperada is not None
        assert recuperada.resposta == "segunda"
        assert recuperada.tokens_consumidos_estimados == 20

    def test_grava_recusa_objeto_nao_entrada_cache(
        self, tmp_path: Path
    ) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        with pytest.raises(TypeError, match="EntradaCache"):
            skill.gravar({"chave": "x" * 64})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construtor
# ---------------------------------------------------------------------------


class TestConstrutor:
    def test_cria_diretorio_se_ausente(self, tmp_path: Path) -> None:
        diretorio = tmp_path / "subpasta" / ".cache"
        assert not diretorio.exists()
        skill = SkillLLMCache(diretorio_cache=diretorio)
        assert diretorio.is_dir()
        assert skill.diretorio_cache == diretorio

    def test_invocador_default_none(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
        assert skill.invocador is None

    def test_invocador_e_propagado(self, tmp_path: Path) -> None:
        skill = SkillLLMCache(
            diretorio_cache=tmp_path / ".cache",
            invocador="Athena",
        )
        assert skill.invocador == "Athena"


# ---------------------------------------------------------------------------
# Performance — leitura sob 1 segundo (R16.7)
# ---------------------------------------------------------------------------


def test_consulta_sob_um_segundo_em_caso_normal(tmp_path: Path) -> None:
    """Sanity check: leitura de entrada normal deve estar bem abaixo de 1s."""
    skill = SkillLLMCache(diretorio_cache=tmp_path / ".cache")
    entrada = _entrada_valida(skill)
    skill.gravar(entrada)

    inicio = time.monotonic()
    recuperada = skill.consultar(entrada.chave)
    duracao = time.monotonic() - inicio

    assert recuperada is not None
    # Limite folgado para tolerar pressão de CI; o objetivo é apenas
    # garantir que a leitura não estoura o orçamento de R16.7.
    assert duracao < 1.0
