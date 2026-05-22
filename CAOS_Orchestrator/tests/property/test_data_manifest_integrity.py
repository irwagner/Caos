"""Property-based tests do Data Manifest (Task 6 — Property 10).

Implementa **Property 10 — Data Manifest Integrity** do ``design.md``:

    For every Skill invocation reading files under ``dados/MNQ/``, the
    SHA-256 of the file at read time SHALL equal the SHA-256 recorded in
    ``dados/MNQ/manifesto.json``; any divergence SHALL abort the read with
    error ``manifesto-divergente``.

**Validates: Requirements 15.4, 15.5, 15.6**

Estratégia:

1. Hypothesis gera ``N ∈ [1, 10]`` arquivos sintéticos em
   ``tmp_path/dados/MNQ/`` com nomes ``[a-z0-9_]+\\.csv`` e conteúdo CSV
   válido (cabeçalho + 1 a 50 linhas com timestamps incrementais).
2. Construímos o manifesto via :class:`DataManifestManager.build`.
3. Validamos: ``ok=True`` (manifesto coerente com o disco recém-escrito).
4. Modificamos 1 byte de um arquivo escolhido por Hypothesis.
5. Validamos novamente: ``ok=False`` e o arquivo modificado aparece nas
   ``divergencias`` com motivo ``hash-divergente``; e
   :meth:`ResultadoIntegridade.assert_ok` levanta
   :class:`SkillDataIntegrityError` com categoria ``manifesto-divergente``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.data_manifest import DataManifestManager, NOME_MANIFESTO
from caos.skills.data_integrity import (
    SkillDataIntegrity,
    SkillDataIntegrityError,
)


# ---------------------------------------------------------------------------
# Estratégias Hypothesis
# ---------------------------------------------------------------------------

# Nomes de arquivo simples — ASCII puro, sem ambiguidade no Windows.
_nome_arquivo = st.from_regex(r"\A[a-z0-9_]{1,12}\Z", fullmatch=True).map(
    lambda s: s + ".csv"
)


def _gerar_csv(num_linhas: int, semente: int) -> bytes:
    """Gera um CSV determinístico (header + N linhas) a partir de ``semente``.

    Timestamps são incrementais a partir de uma base fixa, e os preços são
    derivados da semente para que dois arquivos com (num_linhas, semente)
    diferentes tenham conteúdos distintos.
    """
    base = datetime(2026, 1, 2, 13, 30, 0)
    linhas = ["timestamp,price"]
    for i in range(num_linhas):
        ts = base + timedelta(minutes=i)
        preco = 18000.0 + (semente % 100) * 0.25 + i * 0.25
        linhas.append(f"{ts.isoformat()},{preco:.2f}")
    return ("\n".join(linhas) + "\n").encode("utf-8")


@st.composite
def _arquivos_sinteticos(draw) -> List[Tuple[str, bytes]]:
    """Gera lista de ``(nome, conteudo)`` única por nome, ``N ∈ [1, 10]``."""
    num_arquivos = draw(st.integers(min_value=1, max_value=10))
    nomes = draw(
        st.lists(
            _nome_arquivo,
            min_size=num_arquivos,
            max_size=num_arquivos,
            unique=True,
        )
    )
    arquivos: List[Tuple[str, bytes]] = []
    for i, nome in enumerate(nomes):
        num_linhas = draw(st.integers(min_value=1, max_value=50))
        # Semente derivada do índice para garantir conteúdos distintos.
        conteudo = _gerar_csv(num_linhas, semente=i + 1)
        arquivos.append((nome, conteudo))
    return arquivos


# ---------------------------------------------------------------------------
# Property 10
# ---------------------------------------------------------------------------


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    arquivos=_arquivos_sinteticos(),
    indice_alvo=st.integers(min_value=0, max_value=9),
    posicao_byte=st.integers(min_value=0, max_value=1023),
)
def test_data_manifest_integrity_detecta_modificacao_de_byte(
    arquivos: List[Tuple[str, bytes]],
    indice_alvo: int,
    posicao_byte: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 15.4, 15.5, 15.6** (Property 10).

    Para todo conjunto de N arquivos sintéticos:

    1. Build do manifesto sobre os arquivos recém-escritos.
    2. ``validar()`` retorna ``ok=True`` (sanity).
    3. Modifica 1 byte do arquivo de índice ``indice_alvo % N`` na posição
       ``posicao_byte % len(conteudo)``.
    4. ``validar()`` retorna ``ok=False`` e o arquivo aparece em
       ``divergencias`` com motivo ``hash-divergente``;
       ``assert_ok()`` levanta ``manifesto-divergente``.
    """
    raiz = tmp_path_factory.mktemp("manifest_pbt")
    dados = raiz / "dados" / "MNQ"
    dados.mkdir(parents=True)

    # 1. Materializa os arquivos no disco.
    for nome, conteudo in arquivos:
        (dados / nome).write_bytes(conteudo)

    gerente = DataManifestManager(raiz_dados=dados)
    gerente.build()

    skill = SkillDataIntegrity(
        raiz_dados=dados,
        caminho_manifesto=dados / NOME_MANIFESTO,
    )

    # 2. Sanity: manifesto recém-construído está coerente.
    resultado_inicial = skill.validar()
    assert resultado_inicial.ok is True, (
        f"manifesto recém-construído não está coerente: "
        f"{resultado_inicial}"
    )

    # 3. Modifica 1 byte do arquivo escolhido.
    indice = indice_alvo % len(arquivos)
    nome_alvo, conteudo_alvo = arquivos[indice]
    pos = posicao_byte % len(conteudo_alvo)
    byte_original = conteudo_alvo[pos]
    # XOR com 0xFF garante byte diferente do original.
    novo_byte = byte_original ^ 0xFF
    bytes_modificados = (
        conteudo_alvo[:pos]
        + bytes([novo_byte])
        + conteudo_alvo[pos + 1 :]
    )
    assert bytes_modificados != conteudo_alvo, (
        "modificação não alterou o conteúdo (XOR resultou no mesmo byte)"
    )
    (dados / nome_alvo).write_bytes(bytes_modificados)

    # 4. Validação após modificação detecta divergência.
    resultado = skill.validar()
    assert resultado.ok is False, (
        f"validação após modificação deveria falhar; resultado={resultado}"
    )
    nomes_divergentes = [d.nome_arquivo for d in resultado.divergencias]
    assert nome_alvo in nomes_divergentes, (
        f"arquivo {nome_alvo!r} modificado não aparece em divergencias: "
        f"{nomes_divergentes}"
    )
    div_alvo = next(
        d for d in resultado.divergencias if d.nome_arquivo == nome_alvo
    )
    assert div_alvo.motivo == "hash-divergente"
    assert div_alvo.hash_atual is not None
    assert div_alvo.hash_atual != div_alvo.hash_esperado

    # 5. assert_ok eleva exceção tipificada com categoria correta.
    with pytest.raises(SkillDataIntegrityError) as exc_info:
        resultado.assert_ok()
    assert exc_info.value.categoria == "manifesto-divergente"
    assert nome_alvo in exc_info.value.arquivos_afetados
