"""Testes unitários do :mod:`caos.skills.web_search`.

Cobre o R11.4 do ``requirements.md`` exercitando:

- validação de :class:`FiltrosBusca`;
- combinação de fontes mockadas (sucesso, falha, parcial);
- deduplicação por ``doi_ou_url``;
- truncagem ao limite de 50 resultados;
- categorização de erros em :attr:`ResultadoWebSearch.erros`;
- parser Atom do :class:`FonteArXiv` sobre XML mínimo;
- placeholder do :class:`FonteSSRN` (sempre vazio, sem exceção);
- estabilidade do hash de auditoria.

Nenhum teste faz chamada real à internet — todos usam fontes mock
implementando :class:`FontePapers`.
"""

from __future__ import annotations

import pytest

from caos.skills.web_search import (
    ANO_MAX_DEFAULT,
    FiltrosBusca,
    FonteArXiv,
    FonteIndisponivel,
    FontePapers,
    FonteSSRN,
    LIMITE_RESULTADOS,
    NomeFonte,
    ResultadoBusca,
    SkillWebSearch,
)


# ---------------------------------------------------------------------------
# Fontes mock
# ---------------------------------------------------------------------------


class FonteMockSucesso:
    """Mock que devolve uma lista pré-fabricada sem fazer rede."""

    def __init__(
        self,
        *,
        nome: NomeFonte = "arxiv",
        resultados: list[ResultadoBusca],
    ) -> None:
        self.nome: NomeFonte = nome
        self._resultados = list(resultados)
        self.chamadas: int = 0

    def buscar(
        self, filtros: FiltrosBusca, *, deadline_s: float
    ) -> list[ResultadoBusca]:
        self.chamadas += 1
        return list(self._resultados)


class FonteMockFalha:
    """Mock que sempre levanta :class:`FonteIndisponivel`."""

    def __init__(self, *, nome: NomeFonte, categoria: str) -> None:
        self.nome: NomeFonte = nome
        self._categoria = categoria

    def buscar(
        self, filtros: FiltrosBusca, *, deadline_s: float
    ) -> list[ResultadoBusca]:
        raise FonteIndisponivel(self._categoria)


def _criar_resultado(
    *,
    titulo: str = "Paper teste",
    doi_ou_url: str = "http://arxiv.org/abs/0001",
    fonte: NomeFonte = "arxiv",
    ano: int = 2020,
) -> ResultadoBusca:
    """Constrói um :class:`ResultadoBusca` mínimo para os testes."""
    return ResultadoBusca(
        titulo=titulo,
        autores=("Autor A",),
        ano=ano,
        doi_ou_url=doi_ou_url,
        abstract="resumo curto",
        fonte=fonte,
    )


# ---------------------------------------------------------------------------
# Validação de filtros
# ---------------------------------------------------------------------------


def test_filtros_validacao_termo_vazio() -> None:
    skill = SkillWebSearch(fontes=[])
    with pytest.raises(ValueError):
        skill.buscar(FiltrosBusca(termo=""))


def test_filtros_validacao_termo_so_espacos() -> None:
    skill = SkillWebSearch(fontes=[])
    with pytest.raises(ValueError):
        skill.buscar(FiltrosBusca(termo="   "))


def test_filtros_validacao_ano_fora_range() -> None:
    skill = SkillWebSearch(fontes=[])
    with pytest.raises(ValueError):
        skill.buscar(FiltrosBusca(termo="garch", ano_inicio=1800))


def test_filtros_validacao_ano_acima_atual() -> None:
    skill = SkillWebSearch(fontes=[])
    with pytest.raises(ValueError):
        skill.buscar(
            FiltrosBusca(termo="garch", ano_fim=ANO_MAX_DEFAULT + 50)
        )


def test_filtros_validacao_ano_inicio_maior_que_fim() -> None:
    skill = SkillWebSearch(fontes=[])
    with pytest.raises(ValueError):
        skill.buscar(
            FiltrosBusca(termo="garch", ano_inicio=2020, ano_fim=2010)
        )


def test_filtros_autor_nao_string_lanca() -> None:
    skill = SkillWebSearch(fontes=[])
    with pytest.raises(ValueError):
        skill.buscar(
            FiltrosBusca(
                termo="garch", autores=("",)  # autor vazio
            )
        )


# ---------------------------------------------------------------------------
# Busca com fonte mock
# ---------------------------------------------------------------------------


def test_busca_com_fonte_mock_retorna_resultados() -> None:
    """Fonte mock retorna 3 itens; ``status='skill-ok'`` e 3 resultados finais."""
    itens = [
        _criar_resultado(titulo="A", doi_ou_url="http://arxiv.org/abs/1"),
        _criar_resultado(titulo="B", doi_ou_url="http://arxiv.org/abs/2"),
        _criar_resultado(titulo="C", doi_ou_url="http://arxiv.org/abs/3"),
    ]
    fonte = FonteMockSucesso(nome="arxiv", resultados=itens)
    skill = SkillWebSearch(fontes=[fonte])

    resultado = skill.buscar(FiltrosBusca(termo="garch", fonte="arxiv"))

    assert resultado.status == "skill-ok"
    assert len(resultado.resultados) == 3
    assert tuple(r.titulo for r in resultado.resultados) == ("A", "B", "C")
    assert resultado.erros == ()
    assert fonte.chamadas == 1


def test_busca_descarta_duplicatas_por_doi() -> None:
    """Duas fontes retornam o mesmo ``doi_ou_url`` → dedup ao 1º encontrado."""
    item_arxiv = _criar_resultado(
        titulo="Paper Único", doi_ou_url="https://arxiv.org/abs/9999"
    )
    item_ssrn_dup = _criar_resultado(
        titulo="Paper Único - cópia",
        doi_ou_url="HTTPS://arxiv.org/abs/9999",  # case-insensitive
        fonte="ssrn",
    )

    fonte_a = FonteMockSucesso(nome="arxiv", resultados=[item_arxiv])
    fonte_b = FonteMockSucesso(nome="ssrn", resultados=[item_ssrn_dup])
    skill = SkillWebSearch(fontes=[fonte_a, fonte_b])

    resultado = skill.buscar(FiltrosBusca(termo="garch"))
    assert len(resultado.resultados) == 1
    # Vence o primeiro (arxiv).
    assert resultado.resultados[0].titulo == "Paper Único"
    assert resultado.resultados[0].fonte == "arxiv"


def test_busca_limita_a_50_resultados() -> None:
    """Fonte mock retornando 100 itens é truncada a 50 (R11.4)."""
    itens = [
        _criar_resultado(
            titulo=f"Paper {i}", doi_ou_url=f"http://arxiv.org/abs/{i:04d}"
        )
        for i in range(100)
    ]
    fonte = FonteMockSucesso(nome="arxiv", resultados=itens)
    skill = SkillWebSearch(fontes=[fonte])

    resultado = skill.buscar(FiltrosBusca(termo="garch", fonte="arxiv"))
    assert len(resultado.resultados) == LIMITE_RESULTADOS == 50
    # A ordem preserva o que veio da fonte.
    assert resultado.resultados[0].titulo == "Paper 0"
    assert resultado.resultados[-1].titulo == "Paper 49"


# ---------------------------------------------------------------------------
# Erros e status
# ---------------------------------------------------------------------------


def test_fonte_indisponivel_e_registrada_em_erros() -> None:
    """Fonte que falha é registrada em ``erros`` com a categoria recebida."""
    falha = FonteMockFalha(nome="arxiv", categoria="arxiv-timeout")
    sucesso = FonteMockSucesso(
        nome="ssrn",
        resultados=[
            _criar_resultado(
                titulo="X",
                doi_ou_url="https://ssrn.com/abstract=1",
                fonte="ssrn",
            )
        ],
    )
    skill = SkillWebSearch(fontes=[falha, sucesso])

    resultado = skill.buscar(FiltrosBusca(termo="garch"))
    assert resultado.status == "skill-ok"  # 1 fonte respondeu
    assert "arxiv-timeout" in resultado.erros
    assert len(resultado.resultados) == 1


def test_todas_fontes_falham_status_skill_falha() -> None:
    """2 fontes que falham → ``status='skill-falha'`` e nenhum resultado."""
    f1 = FonteMockFalha(nome="arxiv", categoria="arxiv-erro")
    f2 = FonteMockFalha(nome="ssrn", categoria="ssrn-erro")
    skill = SkillWebSearch(fontes=[f1, f2])

    resultado = skill.buscar(FiltrosBusca(termo="garch"))
    assert resultado.status == "skill-falha"
    assert resultado.resultados == ()
    assert "arxiv-erro" in resultado.erros
    assert "ssrn-erro" in resultado.erros


# ---------------------------------------------------------------------------
# Parser Atom (FonteArXiv)
# ---------------------------------------------------------------------------


def test_arxiv_parser_xml_basico() -> None:
    """O parser extrai título, autores, ano, URL e abstract de XML mínimo."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678</id>
    <title>Volatility Clustering in Micro Futures</title>
    <summary>
      Estudo emp\xc3\xadrico sobre clusters de volatilidade.
    </summary>
    <published>2021-03-14T12:00:00Z</published>
    <author><name>Alice Silva</name></author>
    <author><name>Bob Souza</name></author>
  </entry>
</feed>
"""
    fonte = FonteArXiv()
    resultados = fonte._parsear_atom(xml)
    assert len(resultados) == 1
    r = resultados[0]
    assert r.titulo == "Volatility Clustering in Micro Futures"
    assert r.autores == ("Alice Silva", "Bob Souza")
    assert r.ano == 2021
    assert r.doi_ou_url == "http://arxiv.org/abs/1234.5678"
    assert "clusters" in r.abstract
    assert r.fonte == "arxiv"


def test_arxiv_parser_ignora_entry_sem_id() -> None:
    """Entradas sem ``id`` são silenciosamente puladas (não são deduplicáveis)."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Sem ID</title>
    <summary>...</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/9999.9999</id>
    <title>Com ID</title>
    <summary>...</summary>
    <published>2010-01-01T00:00:00Z</published>
  </entry>
</feed>
"""
    fonte = FonteArXiv()
    resultados = fonte._parsear_atom(xml)
    assert len(resultados) == 1
    assert resultados[0].titulo == "Com ID"


# ---------------------------------------------------------------------------
# Placeholder do SSRN
# ---------------------------------------------------------------------------


def test_ssrn_placeholder_retorna_vazio_sem_erro() -> None:
    """:class:`FonteSSRN` retorna sempre lista vazia sem exceção."""
    fonte = FonteSSRN()
    assert (
        fonte.buscar(FiltrosBusca(termo="qualquer"), deadline_s=10.0) == []
    )


def test_ssrn_no_skill_marca_nao_disponivel_em_erros() -> None:
    """Quando SSRN é a única fonte, ``erros`` contém ``ssrn-nao-disponivel``."""
    skill = SkillWebSearch(fontes=[FonteSSRN()])
    resultado = skill.buscar(FiltrosBusca(termo="garch", fonte="ssrn"))
    assert resultado.status == "skill-ok"  # SSRN respondeu, mesmo que vazio
    assert "ssrn-nao-disponivel" in resultado.erros
    assert resultado.resultados == ()


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------


def test_auditoria_registra_filtros() -> None:
    """Hash dos filtros é estável entre chamadas com mesma entrada."""
    fonte = FonteMockSucesso(nome="arxiv", resultados=[])
    skill = SkillWebSearch(fontes=[fonte], invocador="Explorador")
    f = FiltrosBusca(
        termo="garch",
        ano_inicio=2010,
        ano_fim=2020,
        autores=("Alice",),
        fonte="arxiv",
    )
    r1 = skill.buscar(f)
    r2 = skill.buscar(f)
    assert (
        r1.auditoria.parametros_hash_sha256
        == r2.auditoria.parametros_hash_sha256
    )
    assert len(r1.auditoria.parametros_hash_sha256) == 64
    assert r1.auditoria.invocador == "Explorador"


# ---------------------------------------------------------------------------
# Filtragem por escolha de fonte
# ---------------------------------------------------------------------------


def test_escolha_fonte_arxiv_so_chama_arxiv() -> None:
    """Com ``fonte='arxiv'`` no filtro, apenas a fonte arxiv é consultada."""
    arxiv = FonteMockSucesso(
        nome="arxiv",
        resultados=[
            _criar_resultado(
                titulo="A", doi_ou_url="http://arxiv.org/abs/1"
            )
        ],
    )
    ssrn = FonteMockSucesso(
        nome="ssrn",
        resultados=[
            _criar_resultado(
                titulo="B",
                doi_ou_url="https://ssrn.com/abstract=2",
                fonte="ssrn",
            )
        ],
    )
    skill = SkillWebSearch(fontes=[arxiv, ssrn])

    resultado = skill.buscar(FiltrosBusca(termo="garch", fonte="arxiv"))
    assert arxiv.chamadas == 1
    assert ssrn.chamadas == 0
    assert len(resultado.resultados) == 1
    assert resultado.resultados[0].titulo == "A"


# ---------------------------------------------------------------------------
# Validação do contrato FontePapers
# ---------------------------------------------------------------------------


def test_fonte_invalida_no_construtor_lanca() -> None:
    """Fonte sem ``nome``/``buscar`` é rejeitada no construtor."""
    with pytest.raises(TypeError):
        SkillWebSearch(fontes=[object()])  # type: ignore[list-item]


def test_protocol_runtime_check_passa_para_mocks() -> None:
    """As mocks satisfazem :class:`FontePapers` via runtime_checkable."""
    fonte = FonteMockSucesso(nome="arxiv", resultados=[])
    assert isinstance(fonte, FontePapers)
