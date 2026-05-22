"""Property-based test do Context_Loader (Property 3 do design).

Implementa **Property 3 — Context Isolation** do ``design.md``:

    The Context_Loader SHALL never inject more than 25 Notas_Zettel into any
    agent prompt, and the SHA-256 hash of injected notes SHALL be present in
    100% of turn headers.

**Validates: Requirements 10.5, 10.8, 10.9**

A estratégia gera Zettelkastens sintéticos com 1–200 notas e topologias de
wiki-link arbitrárias mas determinísticas (via ``random.Random(seed)``). Para
cada amostra Hypothesis, validamos:

1. ``len(res.notas_validas) <= 25`` (R10.9 — invariante duro de truncagem).
2. ``contexto_hash_sha256`` está presente, é uma string de exatamente 64
   caracteres hexadecimais minúsculos (R10.8 — hash sempre presente).
3. Todas as notas válidas têm frontmatter válido (qualquer instância de
   :class:`NotaZettel`).
4. O hash é deterministicamente reprodutível: invocar ``carregar_contexto``
   duas vezes sobre o mesmo Zettelkasten produz exatamente o mesmo hash
   (R9.1 — fundamento da reprodutibilidade).

Mantemos ``n_notas`` limitado a 200 e ``max_examples=50`` para que a suíte
permaneça executável em CI Windows sem pesar no orçamento de tempo.
"""

from __future__ import annotations

import random
import string
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.context_loader import (
    LIMITE_NOTAS_INJETADAS,
    carregar_contexto,
)
from caos.models import NotaZettel

# ---------------------------------------------------------------------------
# Geração de Zettelkasten sintético
# ---------------------------------------------------------------------------

_AGENTES_AUTORES = [
    "Athena",
    "Odin",
    "Mister_M",
    "Manolo",
    "Rodrigo",
    "Cerberus",
    "Hermes",
    "Explorador",
    "Devils_Advocate",
]

_AREAS = [
    "Modulo_Institucional",
    "Modulo_Risco",
    "API_NinjaTrader_8_Reference",
    "Papers",
    "Decisoes_do_Conselho",
]


def _frontmatter_sintetico(
    nome: str,
    area: str,
    autor: str,
    data_iso: str,
    tag: str,
) -> str:
    return (
        "---\n"
        f"titulo: {nome}\n"
        f"area: {area}\n"
        "tags:\n"
        f"  - {tag}\n"
        f"data_criacao: {data_iso}\n"
        f"agente_autor: {autor}\n"
        "---\n"
    )


def _gerar_zettelkasten(
    raiz: Path,
    *,
    n_notas: int,
    densidade_links: float,
    seed: int,
) -> list[str]:
    """Materializa um Zettelkasten sintético determinístico.

    Para cada nota ``Ni`` (``i`` de 0 a ``n_notas - 1``):

    - Subpasta = uma das 5 áreas raiz (R10.1) escolhida pelo PRNG.
    - Frontmatter mínimo válido (R10.3) com ``data_criacao`` em UTC variando
      por dia do mês.
    - Corpo Markdown com ``round(densidade_links * (n_notas - 1))`` wiki-links
      escolhidos aleatoriamente entre as outras notas, sem auto-links.

    Retorna a lista ordenada de nomes (``["N000", "N001", ...]``).
    """
    rng = random.Random(seed)
    nomes = [f"N{i:03d}" for i in range(n_notas)]

    n_links_por_nota = max(0, round(densidade_links * (n_notas - 1)))

    # Pré-gera por nota: área, autor, dia, tag, e a lista de links de saída.
    for i, nome in enumerate(nomes):
        area = _AREAS[rng.randrange(len(_AREAS))]
        autor = _AGENTES_AUTORES[rng.randrange(len(_AGENTES_AUTORES))]
        # Dia do mês determinístico em [1, 28] para evitar problemas de mês.
        dia = (i % 28) + 1
        data_iso = f"2026-05-{dia:02d}T10:00:00Z"
        tag = "tag-" + "".join(rng.choices(string.ascii_lowercase, k=4))

        # Sorteia até `n_links_por_nota` links distintos sem auto-link.
        candidatos = [n for n in nomes if n != nome]
        if n_links_por_nota >= len(candidatos):
            alvos = list(candidatos)
        else:
            alvos = rng.sample(candidatos, n_links_por_nota)

        corpo_links = " ".join(f"[[{alvo}]]" for alvo in alvos)
        corpo = f"# {nome}\n\nLinks: {corpo_links}\n"

        pasta = raiz / area
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"{nome}.md"
        arquivo.write_text(
            _frontmatter_sintetico(nome, area, autor, data_iso, tag) + corpo,
            encoding="utf-8",
        )

    return nomes


# ---------------------------------------------------------------------------
# Property 3
# ---------------------------------------------------------------------------


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_notas=st.integers(min_value=1, max_value=200),
    densidade_links=st.floats(
        min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False
    ),
    referencias_iniciais=st.integers(min_value=1, max_value=5),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_property_isolamento_contexto(
    n_notas: int,
    densidade_links: float,
    referencias_iniciais: int,
    seed: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 10.5, 10.8, 10.9** (Property 3).

    Para todo Zettelkasten sintético gerado com 1–200 notas e topologia
    arbitrária, garante:

    * ``len(notas_validas) <= 25`` (R10.9).
    * ``contexto_hash_sha256`` é sempre uma string de 64 hex chars (R10.8).
    * Todas as notas válidas têm instância correta de :class:`NotaZettel`.
    * O hash é determinístico: 2 invocações idênticas produzem o mesmo valor.
    """
    raiz = tmp_path_factory.mktemp("zettelkasten_property")
    nomes = _gerar_zettelkasten(
        raiz,
        n_notas=n_notas,
        densidade_links=densidade_links,
        seed=seed,
    )

    rng = random.Random(seed ^ 0xA5A5A5)
    n_refs = min(referencias_iniciais, len(nomes))
    refs = rng.sample(nomes, n_refs)
    input_tarefa = " ".join(f"[[{r}]]" for r in refs)

    res = carregar_contexto(input_tarefa, raiz_zettelkasten=raiz)

    # (1) Invariante duro de truncagem (R10.9).
    assert len(res.notas_validas) <= LIMITE_NOTAS_INJETADAS, (
        f"truncagem violada: {len(res.notas_validas)} notas válidas com "
        f"limite {LIMITE_NOTAS_INJETADAS} (n_notas={n_notas}, "
        f"densidade={densidade_links}, seed={seed})"
    )

    # (2) Hash sempre presente, 64 hex chars (R10.8).
    assert isinstance(res.contexto_hash_sha256, str)
    assert len(res.contexto_hash_sha256) == 64
    assert all(c in "0123456789abcdef" for c in res.contexto_hash_sha256)

    # (3) Todas as notas válidas são instâncias de NotaZettel.
    for nc in res.notas_validas:
        assert isinstance(nc.nota, NotaZettel)

    # (4) Hash determinístico: rodar 2x produz o mesmo resultado (R9.1).
    res2 = carregar_contexto(input_tarefa, raiz_zettelkasten=raiz)
    assert res.contexto_hash_sha256 == res2.contexto_hash_sha256
