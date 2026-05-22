"""Testes unitários do Context_Loader (Task 9).

Cobre os critérios R10.1 a R10.9 do ``requirements.md`` de forma exemplar
(complemento ao teste de propriedade em ``tests/property/test_isolamento_contexto.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from caos.context_loader import (
    LIMITE_NOTAS_INJETADAS,
    MAX_SALTOS,
    ContextLoader,
    ContextoCarregado,
    carregar_contexto,
    computar_hash_contexto,
    extrair_wiki_links,
)

# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

UTC_2026_BASE = "2026-05-14T10:00:00Z"


def _frontmatter_valido(
    titulo: str,
    *,
    area: str = "Modulo_Risco",
    data: str = UTC_2026_BASE,
    autor: str = "Athena",
    tags: list[str] | None = None,
) -> str:
    tags = tags or ["risco"]
    tags_yaml = "\n".join(f"  - {t}" for t in tags)
    return (
        "---\n"
        f"titulo: {titulo}\n"
        f"area: {area}\n"
        "tags:\n"
        f"{tags_yaml}\n"
        f"data_criacao: {data}\n"
        f"agente_autor: {autor}\n"
        "---\n"
    )


def _criar_nota(
    raiz: Path,
    *,
    subpasta: str,
    nome: str,
    corpo: str = "",
    titulo: str | None = None,
    data: str = UTC_2026_BASE,
    autor: str = "Athena",
    area: str | None = None,
) -> Path:
    """Cria uma Nota_Zettel válida em ``raiz/subpasta/nome.md``.

    ``area`` é inferida do nome da subpasta quando não fornecida.
    """
    pasta = raiz / subpasta
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{nome}.md"
    area = area if area is not None else subpasta
    fm = _frontmatter_valido(
        titulo or nome,
        area=area,
        data=data,
        autor=autor,
    )
    arquivo.write_text(fm + corpo, encoding="utf-8")
    return arquivo


# ---------------------------------------------------------------------------
# extrair_wiki_links
# ---------------------------------------------------------------------------


def test_extrair_wiki_links_simples():
    assert extrair_wiki_links("veja [[A]] e [[B|texto]]") == ["A", "B"]


def test_extrair_wiki_links_remove_extensao_md():
    assert extrair_wiki_links("[[Trailing.md]] e [[VWAP]]") == ["Trailing", "VWAP"]


def test_extrair_wiki_links_dedup_preserva_ordem():
    texto = "[[Z]] [[A]] [[Z]] [[B]] [[A|alias]]"
    assert extrair_wiki_links(texto) == ["Z", "A", "B"]


def test_extrair_wiki_links_input_vazio():
    assert extrair_wiki_links("") == []
    assert extrair_wiki_links(None) == []


def test_extrair_wiki_links_ignora_link_vazio():
    # `[[]]` ou `[[ ]]` não devem aparecer no resultado.
    assert extrair_wiki_links("texto [[]] [[ ]] [[A]]") == ["A"]


# ---------------------------------------------------------------------------
# _extrair_referencias (via carregar_contexto)
# ---------------------------------------------------------------------------


def test_extrair_referencias_inclui_arquivo_md(tmp_path: Path):
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="proposta")
    res = carregar_contexto(
        "olha o arquivo proposta.md aqui",
        raiz_zettelkasten=tmp_path,
    )
    assert "proposta" in res.referencias_explicitas
    assert len(res.notas_validas) == 1


# ---------------------------------------------------------------------------
# carregar_contexto — casos básicos
# ---------------------------------------------------------------------------


def test_carrega_nota_unica_referenciada(tmp_path: Path):
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A")
    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)

    assert res.referencias_explicitas == ("A",)
    assert len(res.notas_validas) == 1
    assert res.notas_validas[0].nome_relativo_posix == "Modulo_Risco/A.md"
    assert res.notas_invalidas == []
    assert res.notas_ausentes == []
    assert res.notas_truncadas == []
    assert len(res.contexto_hash_sha256) == 64
    assert all(c in "0123456789abcdef" for c in res.contexto_hash_sha256)


def test_bfs_expande_dois_saltos(tmp_path: Path):
    # A → B → C → D; com input [[A]] esperamos {A, B, C}, sem D (3º salto).
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A", corpo="ver [[B]]")
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="B", corpo="ver [[C]]")
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="C", corpo="ver [[D]]")
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="D")

    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    nomes = {n.nome_relativo_posix.split("/")[-1].removesuffix(".md") for n in res.notas_validas}
    assert nomes == {"A", "B", "C"}
    assert "D" not in nomes


def test_bfs_nao_revisita(tmp_path: Path):
    # A ↔ B com ciclo; A referencia B duas vezes.
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A", corpo="[[B]] [[B]] [[A]]")
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="B", corpo="[[A]]")
    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    assert len(res.notas_validas) == 2


# ---------------------------------------------------------------------------
# Truncagem (R10.9)
# ---------------------------------------------------------------------------


def test_truncagem_25_notas(tmp_path: Path):
    # Cria 30 notas em cadeia, mas como BFS limita a 2 saltos só visita 3.
    # Para forçar > 25, criamos um hub "H" que linka para 30 outras notas.
    corpo_hub = " ".join(f"[[N{i:03d}]]" for i in range(30))
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="H", corpo=corpo_hub)
    for i in range(30):
        _criar_nota(tmp_path, subpasta="Modulo_Risco", nome=f"N{i:03d}")

    res = carregar_contexto("[[H]]", raiz_zettelkasten=tmp_path)
    assert len(res.notas_validas) <= LIMITE_NOTAS_INJETADAS
    # 31 candidatos válidos (H + 30 N's), 25 ficam, 6 truncados.
    assert len(res.notas_truncadas) == 31 - LIMITE_NOTAS_INJETADAS
    for t in res.notas_truncadas:
        assert t.motivo == "limite-25-excedido"


def test_truncagem_aplica_criterios_de_desempate(tmp_path: Path):
    # 26 notas com 0 backlinks (nenhuma é alvo de wiki-link de outra),
    # variando data_criacao. A nota com data mais antiga deve ser removida.
    # Hub com 26 links garante que todas viram candidatas válidas.
    corpo_hub = " ".join(f"[[N{i:02d}]]" for i in range(26))
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="H", corpo=corpo_hub)
    # Datas crescentes; N00 é a mais antiga.
    for i in range(26):
        # 2026-05-(14+i)T10:00:00Z; cobre dias 14 a 39 → ajustamos para mês 5/6.
        dia = 14 + i
        if dia <= 31:
            data = f"2026-05-{dia:02d}T10:00:00Z"
        else:
            data = f"2026-06-{dia - 31:02d}T10:00:00Z"
        _criar_nota(
            tmp_path,
            subpasta="Modulo_Risco",
            nome=f"N{i:02d}",
            data=data,
        )

    res = carregar_contexto("[[H]]", raiz_zettelkasten=tmp_path)
    # 27 candidatos (H + N00..N25); H é alvo de 0 backlinks também.
    # Limite 25 → 2 truncados. A nota com data mais antiga é N00; H também
    # tem data igual a UTC_2026_BASE = 2026-05-14, mas como é referenciada
    # pelo input ela aparece. Para garantir determinismo, validamos que N00
    # foi removida (a mais antiga não-explícita).
    nomes_validos = {
        n.nome_relativo_posix.split("/")[-1].removesuffix(".md")
        for n in res.notas_validas
    }
    nomes_truncados = {t.nome_nota for t in res.notas_truncadas}
    assert "N00" in nomes_truncados
    assert "N00" not in nomes_validos


def test_limite_notas_customizado(tmp_path: Path):
    corpo_hub = " ".join(f"[[N{i:02d}]]" for i in range(10))
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="H", corpo=corpo_hub)
    for i in range(10):
        _criar_nota(tmp_path, subpasta="Modulo_Risco", nome=f"N{i:02d}")

    res = carregar_contexto("[[H]]", raiz_zettelkasten=tmp_path, limite_notas=5)
    assert len(res.notas_validas) == 5
    assert len(res.notas_truncadas) == 11 - 5


# ---------------------------------------------------------------------------
# Hash determinístico
# ---------------------------------------------------------------------------


def test_hash_estavel_entre_invocacoes(tmp_path: Path):
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A", corpo="conteudo A")
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="B", corpo="conteudo B")
    res1 = carregar_contexto("[[A]] [[B]]", raiz_zettelkasten=tmp_path)
    res2 = carregar_contexto("[[A]] [[B]]", raiz_zettelkasten=tmp_path)
    assert res1.contexto_hash_sha256 == res2.contexto_hash_sha256


def test_hash_difere_quando_nota_muda(tmp_path: Path):
    arq_a = _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A", corpo="versao 1")
    res1 = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    # Mantém o frontmatter, altera somente o corpo Markdown.
    arq_a.write_text(
        _frontmatter_valido("A", area="Modulo_Risco") + "versao 2",
        encoding="utf-8",
    )
    res2 = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    assert res1.contexto_hash_sha256 != res2.contexto_hash_sha256


def test_hash_independe_da_ordem_de_referencia(tmp_path: Path):
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A", corpo="alpha")
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="B", corpo="beta")
    res1 = carregar_contexto("[[A]] [[B]]", raiz_zettelkasten=tmp_path)
    res2 = carregar_contexto("[[B]] [[A]]", raiz_zettelkasten=tmp_path)
    assert res1.contexto_hash_sha256 == res2.contexto_hash_sha256


def test_hash_vazio_quando_sem_notas_validas(tmp_path: Path):
    # Hash do vazio (SHA-256("")) é constante e tem 64 chars hex.
    res = carregar_contexto(
        "tarefa sem referencias", raiz_zettelkasten=tmp_path
    )
    assert len(res.contexto_hash_sha256) == 64


def test_computar_hash_contexto_lista_vazia():
    h = computar_hash_contexto([])
    assert (
        h
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


# ---------------------------------------------------------------------------
# Notas inválidas e ausentes
# ---------------------------------------------------------------------------


def test_nota_invalida_frontmatter_ausente(tmp_path: Path):
    pasta = tmp_path / "Modulo_Risco"
    pasta.mkdir(parents=True)
    (pasta / "A.md").write_text("apenas prosa, sem frontmatter\n", encoding="utf-8")

    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    assert res.notas_validas == []
    assert len(res.notas_invalidas) == 1
    assert res.notas_invalidas[0].categoria == "frontmatter-ausente"


def test_nota_invalida_campo_faltando(tmp_path: Path):
    # Frontmatter sem `area`.
    pasta = tmp_path / "Modulo_Risco"
    pasta.mkdir(parents=True)
    fm = (
        "---\n"
        "titulo: A\n"
        "tags:\n  - x\n"
        "data_criacao: 2026-05-14T10:00:00Z\n"
        "agente_autor: Athena\n"
        "---\n"
    )
    (pasta / "A.md").write_text(fm, encoding="utf-8")

    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    assert res.notas_validas == []
    assert len(res.notas_invalidas) == 1
    assert res.notas_invalidas[0].categoria == "campo-obrigatorio-faltando"


def test_nota_invalida_valor_fora_do_dominio(tmp_path: Path):
    # `area` fora do enum permitido.
    pasta = tmp_path / "Custom"
    pasta.mkdir(parents=True)
    fm = (
        "---\n"
        "titulo: A\n"
        "area: Custom\n"
        "tags:\n  - x\n"
        "data_criacao: 2026-05-14T10:00:00Z\n"
        "agente_autor: Athena\n"
        "---\n"
    )
    (pasta / "A.md").write_text(fm, encoding="utf-8")

    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    assert res.notas_validas == []
    assert len(res.notas_invalidas) == 1
    assert res.notas_invalidas[0].categoria == "valor-invalido"


def test_nota_invalida_frontmatter_malformado(tmp_path: Path):
    pasta = tmp_path / "Modulo_Risco"
    pasta.mkdir(parents=True)
    # YAML quebrado (chave sem valor + dois pontos extras).
    fm = "---\ntitulo: A\narea: : :\n---\ncorpo\n"
    (pasta / "A.md").write_text(fm, encoding="utf-8")

    res = carregar_contexto("[[A]]", raiz_zettelkasten=tmp_path)
    assert res.notas_validas == []
    assert len(res.notas_invalidas) == 1
    assert res.notas_invalidas[0].categoria in {
        "frontmatter-malformado",
        "valor-invalido",
        "campo-obrigatorio-faltando",
    }


def test_nota_ausente(tmp_path: Path):
    res = carregar_contexto("[[Nao_Existe]]", raiz_zettelkasten=tmp_path)
    assert res.notas_ausentes == ["Nao_Existe"]
    assert res.notas_validas == []


# ---------------------------------------------------------------------------
# ContextLoader (wrapper OO)
# ---------------------------------------------------------------------------


def test_construtor_valida_diretorio(tmp_path: Path):
    inexistente = tmp_path / "nao_existe"
    with pytest.raises(ValueError):
        ContextLoader(raiz_zettelkasten=inexistente)


def test_carregar_contexto_valida_diretorio(tmp_path: Path):
    inexistente = tmp_path / "nao_existe"
    with pytest.raises(ValueError):
        carregar_contexto("[[A]]", raiz_zettelkasten=inexistente)


def test_carregar_contexto_rejeita_limite_negativo(tmp_path: Path):
    with pytest.raises(ValueError):
        carregar_contexto(
            "[[A]]", raiz_zettelkasten=tmp_path, limite_notas=-1
        )


def test_context_loader_wrapper_oo(tmp_path: Path):
    _criar_nota(tmp_path, subpasta="Modulo_Risco", nome="A")
    loader = ContextLoader(raiz_zettelkasten=tmp_path)
    res = loader.carregar("[[A]]")
    assert isinstance(res, ContextoCarregado)
    assert len(res.notas_validas) == 1


def test_max_saltos_constante():
    # Garante que o invariante R10.5 (2 saltos) está documentado.
    assert MAX_SALTOS == 2
