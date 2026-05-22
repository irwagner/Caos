"""Testes unitários do :mod:`caos.determinism_auditor` (Task 11).

Cobre R9.1 (estrutura), R9.2 (turnos pulados), R9.3 (normalização e
comparação byte-a-byte), R9.4 (derivação de ``reproduzivel``) e R9.5
(detecção de regressão).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

from caos.determinism_auditor import (
    ResultadoComparacao,
    ResultadoRegressao,
    comparar_turnos_byte_a_byte,
    derivar_reproduzivel,
    detectar_regressao,
    normalizar_texto,
)
from caos.models import (
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
    Turno,
    Veto,
)


# ---------------------------------------------------------------------------
# Helpers de construção de fixtures sintéticas
# ---------------------------------------------------------------------------


_HASH_VALIDO_A = "a" * 64
_HASH_VALIDO_B = "b" * 64


def _construir_turno(
    *,
    numero: int = 1,
    agente: str = "Athena",
    fase: str = "PROPOSTAS",
    nao_deterministico: bool = False,
    conteudo: Optional[str] = "Conteúdo determinístico padrão.\n",
    notas: Optional[list[str]] = None,
    contexto_hash: Optional[str] = _HASH_VALIDO_A,
    status: str = "ok",
) -> Turno:
    return Turno(
        numero=numero,
        agente=agente,  # type: ignore[arg-type]
        modelo="claude-opus-4.7",
        timestamp=datetime(2026, 5, 14, 14, 0, numero, tzinfo=timezone.utc),
        fase=fase,  # type: ignore[arg-type]
        nao_deterministico=nao_deterministico,
        notas_injetadas=list(notas or []),
        contexto_hash_sha256=contexto_hash,
        status=status,  # type: ignore[arg-type]
        conteudo_markdown=conteudo,
    )


def _construir_decisao(
    *,
    identificador: str = "2026-05-14-01",
    proposta_aceita: Optional[str] = "P1",
    vetos: Optional[list[Veto]] = None,
    reproduzivel: str = "true",
) -> DecisaoDoConselho:
    return DecisaoDoConselho(
        identificador=identificador,
        debate_relacionado=f"{identificador}-titulo.md",
        agentes_participantes=["Athena", "Cerberus"],
        propostas=[
            Proposta(
                id="P1",
                autor="Manolo",
                resumo="resumo curto",
                conteudo="conteudo da proposta",
                confianca=70,
            ),
            Proposta(
                id="P2",
                autor="Odin",
                resumo="resumo curto B",
                conteudo="conteudo da proposta B",
                confianca=60,
            ),
        ],
        vetos=list(vetos or []),
        decisao_final=DecisaoFinal(
            proposta_aceita=proposta_aceita,
            rationale="rationale sintético da síntese final",
        ),
        links_zettel=["[[Modulo_Risco/X]]"],
        aprovado_walk_forward=False,
        reproduzivel=reproduzivel,  # type: ignore[arg-type]
        regressao_detectada=False,
        status="concluido",
    )


# ---------------------------------------------------------------------------
# R9.4 — derivar_reproduzivel
# ---------------------------------------------------------------------------


class TestDerivarReproduzivel:
    def test_derivar_reproduzivel_lista_vazia(self) -> None:
        assert derivar_reproduzivel([]) == "true"

    def test_derivar_reproduzivel_nenhum_nao_deterministico(self) -> None:
        turnos = [
            _construir_turno(numero=1, nao_deterministico=False),
            _construir_turno(numero=2, nao_deterministico=False),
            _construir_turno(numero=3, nao_deterministico=False),
        ]
        assert derivar_reproduzivel(turnos) == "true"

    def test_derivar_reproduzivel_todos_nao_deterministicos(self) -> None:
        turnos = [
            _construir_turno(numero=1, nao_deterministico=True),
            _construir_turno(numero=2, nao_deterministico=True),
        ]
        assert derivar_reproduzivel(turnos) == "false"

    def test_derivar_reproduzivel_misto(self) -> None:
        turnos = [
            _construir_turno(numero=1, nao_deterministico=True),
            _construir_turno(numero=2, nao_deterministico=False),
            _construir_turno(numero=3, nao_deterministico=True),
        ]
        assert derivar_reproduzivel(turnos) == "parcial"


# ---------------------------------------------------------------------------
# R9.3 — normalizar_texto
# ---------------------------------------------------------------------------


class TestNormalizarTexto:
    def test_normalizar_crlf_para_lf(self) -> None:
        entrada = "linha 1\r\nlinha 2\r\nfim"
        esperado = "linha 1\nlinha 2\nfim"
        assert normalizar_texto(entrada) == esperado

    def test_normalizar_remove_trailing_ws(self) -> None:
        entrada = "alpha   \nbeta\t\t\ngamma\n"
        esperado = "alpha\nbeta\ngamma\n"
        assert normalizar_texto(entrada) == esperado

    def test_normalizar_preserva_linhas_em_branco(self) -> None:
        entrada = "linha\n\n\noutra\n"
        # Linhas em branco intermediárias são preservadas.
        assert normalizar_texto(entrada) == "linha\n\n\noutra\n"

    def test_normalizar_preserva_espacos_internos(self) -> None:
        entrada = "palavra  com  duplos   espacos   \n"
        esperado = "palavra  com  duplos   espacos\n"
        assert normalizar_texto(entrada) == esperado

    def test_normalizar_string_vazia(self) -> None:
        assert normalizar_texto("") == ""

    def test_normalizar_combinacao_crlf_e_trailing(self) -> None:
        entrada = "uma  \r\ndois\t\r\ntres   \r\n"
        esperado = "uma\ndois\ntres\n"
        assert normalizar_texto(entrada) == esperado

    def test_normalizar_idempotente(self) -> None:
        entrada = "uma  \r\ndois\t\r\ntres   \r\n"
        primeira = normalizar_texto(entrada)
        segunda = normalizar_texto(primeira)
        assert primeira == segunda


# ---------------------------------------------------------------------------
# R9.2 / R9.3 — comparar_turnos_byte_a_byte
# ---------------------------------------------------------------------------


class TestCompararTurnosByteABYte:
    def test_comparar_turnos_iguais_apos_normalizacao(self) -> None:
        # Mesmo conteúdo, mas com CRLF + trailing whitespace divergente.
        t1 = _construir_turno(conteudo="linha 1   \r\nlinha 2\r\n")
        t2 = _construir_turno(conteudo="linha 1\nlinha 2\t\n")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert isinstance(res, ResultadoComparacao)
        assert res.iguais is True
        assert res.motivo == "iguais"
        assert res.diff_descricao is None

    def test_comparar_turnos_pulado_quando_t1_nao_deterministico(self) -> None:
        t1 = _construir_turno(nao_deterministico=True, conteudo="X")
        t2 = _construir_turno(nao_deterministico=False, conteudo="Y")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.iguais is False
        assert res.motivo == "pulado-nao-deterministico"

    def test_comparar_turnos_pulado_quando_t2_nao_deterministico(self) -> None:
        t1 = _construir_turno(nao_deterministico=False, conteudo="X")
        t2 = _construir_turno(nao_deterministico=True, conteudo="X")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.iguais is False
        assert res.motivo == "pulado-nao-deterministico"

    def test_comparar_turnos_diferentes_quando_conteudo_difere(self) -> None:
        t1 = _construir_turno(conteudo="primeira versão\n")
        t2 = _construir_turno(conteudo="segunda versão\n")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.iguais is False
        assert res.motivo == "diferentes"
        assert res.diff_descricao is not None
        assert "conteudo_markdown" in res.diff_descricao

    def test_comparar_turnos_metadados_divergentes_numero(self) -> None:
        t1 = _construir_turno(numero=1, conteudo="X")
        t2 = _construir_turno(numero=2, conteudo="X")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.iguais is False
        assert res.motivo == "metadados-divergentes"
        assert res.diff_descricao is not None
        assert "numero" in res.diff_descricao

    def test_comparar_turnos_metadados_divergentes_agente(self) -> None:
        t1 = _construir_turno(agente="Athena", conteudo="X")
        t2 = _construir_turno(agente="Cerberus", conteudo="X")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.motivo == "metadados-divergentes"
        assert "agente" in (res.diff_descricao or "")

    def test_comparar_turnos_metadados_divergentes_fase(self) -> None:
        t1 = _construir_turno(fase="PROPOSTAS", conteudo="X")
        t2 = _construir_turno(fase="CRITICA", conteudo="X")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.motivo == "metadados-divergentes"
        assert "fase" in (res.diff_descricao or "")

    def test_comparar_turnos_metadados_divergentes_status(self) -> None:
        t1 = _construir_turno(status="ok", conteudo="X")
        t2 = _construir_turno(status="ausente", conteudo="X")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.motivo == "metadados-divergentes"
        assert "status" in (res.diff_descricao or "")

    def test_comparar_turnos_metadados_divergentes_contexto_hash(self) -> None:
        t1 = _construir_turno(contexto_hash=_HASH_VALIDO_A, conteudo="X")
        t2 = _construir_turno(contexto_hash=_HASH_VALIDO_B, conteudo="X")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.motivo == "metadados-divergentes"
        assert "contexto_hash_sha256" in (res.diff_descricao or "")

    def test_comparar_turnos_notas_injetadas_como_set(self) -> None:
        # Mesmo conjunto, ordem diferente → iguais.
        t1 = _construir_turno(notas=["A.md", "B.md"], conteudo="X\n")
        t2 = _construir_turno(notas=["B.md", "A.md"], conteudo="X\n")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.iguais is True
        assert res.motivo == "iguais"

    def test_comparar_turnos_notas_injetadas_divergem(self) -> None:
        t1 = _construir_turno(notas=["A.md", "B.md"], conteudo="X\n")
        t2 = _construir_turno(notas=["A.md", "C.md"], conteudo="X\n")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.motivo == "metadados-divergentes"
        assert "notas_injetadas" in (res.diff_descricao or "")

    def test_comparar_turnos_conteudo_none_tratado_como_vazio(self) -> None:
        t1 = _construir_turno(conteudo=None)
        t2 = _construir_turno(conteudo="")
        res = comparar_turnos_byte_a_byte(t1, t2)
        assert res.iguais is True
        assert res.motivo == "iguais"


# ---------------------------------------------------------------------------
# R9.5 — detectar_regressao
# ---------------------------------------------------------------------------


class TestDetectarRegressao:
    def test_detectar_regressao_decisao_anterior_none(self) -> None:
        atual = _construir_decisao(proposta_aceita="P1")
        res = detectar_regressao(atual, None)
        assert isinstance(res, ResultadoRegressao)
        assert res.regressao_detectada is False
        assert res.diff_proposta is None
        assert res.diff_vetos is None

    def test_detectar_regressao_decisoes_iguais(self) -> None:
        atual = _construir_decisao(
            proposta_aceita="P1",
            vetos=[
                Veto(
                    tipo="veto_de_risco",
                    autor="Cerberus",
                    decisao="aprovar-com-ressalvas",
                    proposta_alvo="P2",
                    justificativa="ok",
                )
            ],
        )
        anterior = _construir_decisao(
            proposta_aceita="P1",
            vetos=[
                Veto(
                    tipo="veto_de_risco",
                    autor="Cerberus",
                    decisao="aprovar-com-ressalvas",
                    proposta_alvo="P2",
                    # Justificativa diferente NÃO conta como regressão.
                    justificativa="texto diferente, mesma decisão",
                )
            ],
        )
        res = detectar_regressao(atual, anterior)
        assert res.regressao_detectada is False
        assert res.diff_proposta is None
        assert res.diff_vetos is None

    def test_detectar_regressao_proposta_diferente(self) -> None:
        atual = _construir_decisao(proposta_aceita="P1")
        anterior = _construir_decisao(proposta_aceita="P2")
        res = detectar_regressao(atual, anterior)
        assert res.regressao_detectada is True
        assert res.diff_proposta == ("P2", "P1")
        assert res.diff_vetos is None

    def test_detectar_regressao_proposta_none_para_p1(self) -> None:
        # Aceitar transição None → P1 também é divergência.
        atual = _construir_decisao(proposta_aceita="P1")
        anterior = _construir_decisao(proposta_aceita=None)
        res = detectar_regressao(atual, anterior)
        assert res.regressao_detectada is True
        assert res.diff_proposta == (None, "P1")

    def test_detectar_regressao_vetos_diferentes(self) -> None:
        veto_a = Veto(
            tipo="veto_de_risco",
            autor="Cerberus",
            decisao="aprovar-com-ressalvas",
            proposta_alvo="P1",
            justificativa="x",
        )
        veto_b = Veto(
            tipo="veto_de_risco",
            autor="Cerberus",
            decisao="bloquear",
            proposta_alvo="P1",
            justificativa="x",
        )
        atual = _construir_decisao(proposta_aceita="P1", vetos=[veto_a])
        anterior = _construir_decisao(proposta_aceita="P1", vetos=[veto_b])
        res = detectar_regressao(atual, anterior)
        assert res.regressao_detectada is True
        assert res.diff_proposta is None
        assert res.diff_vetos is not None
        apenas_anterior, apenas_atual = res.diff_vetos
        assert (
            "veto_de_risco",
            "Cerberus",
            "bloquear",
            "P1",
        ) in apenas_anterior
        assert (
            "veto_de_risco",
            "Cerberus",
            "aprovar-com-ressalvas",
            "P1",
        ) in apenas_atual

    def test_detectar_regressao_proposta_e_vetos_diferem(self) -> None:
        veto = Veto(
            tipo="veto_de_risco",
            autor="Cerberus",
            decisao="aprovar-com-ressalvas",
            proposta_alvo="P1",
            justificativa="x",
        )
        atual = _construir_decisao(proposta_aceita="P1", vetos=[veto])
        anterior = _construir_decisao(proposta_aceita="P2", vetos=[])
        res = detectar_regressao(atual, anterior)
        assert res.regressao_detectada is True
        assert res.diff_proposta == ("P2", "P1")
        assert res.diff_vetos is not None
