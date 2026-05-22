"""Testes unitários dos modelos Pydantic v2 declarados em ``caos/models.py``.

Cobre os 12 modelos públicos exigidos pela Task 2 do Spec
``caos-conselho-infra``: ``AgentProfile``, ``NotaZettel``, ``Debate``,
``Turno``, ``Proposta``, ``Veto``, ``DecisaoDoConselho``, ``RegraSteering``,
``NotaPaper``, ``EntradaCache``, ``EstadoOrcamento`` e ``EntradaManifesto``.

Cada modelo recebe:
- Pelo menos um caso válido completo (sanity check).
- Pelo menos 3 casos inválidos cobrindo diferentes facetas (campos
  obrigatórios faltando, tipos errados, regex falho, ranges fora de limite,
  enums inválidos).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from caos.models import (
    AGENTES,
    AgentProfile,
    ConfiancaSchema,
    Debate,
    DecisaoDoConselho,
    DecisaoFinal,
    EntradaCache,
    EntradaManifesto,
    EstadoOrcamento,
    FormatoDeSaida,
    NotaPaper,
    NotaZettel,
    Proposta,
    RegraSteering,
    Turno,
    Veto,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 64 hex chars de exemplo (não é o hash real de nada — uso apenas para regex).
HASH_SHA256_VALIDO = "a" * 64
HASH_SHA256_OUTRO = "b" * 64

UTC_2026 = "2026-05-14T13:42:00Z"


def _formato_saida_valido() -> dict:
    return {
        "secoes_obrigatorias": ["Proposta", "Justificativa", "Riscos", "Confianca"],
        "confianca": {"tipo": "inteiro", "minimo": 0, "maximo": 100},
    }


def _agent_profile_valido() -> dict:
    return {
        "nome": "Cerberus",
        "modelo": "claude-sonnet-4.5",
        "tags_especialidade": ["risco", "circuit-breaker"],
        "skills_permitidas": ["Skill_CSV_Reader"],
        "escopo_de_decisao": ["veto_de_risco"],
        "formato_de_saida": _formato_saida_valido(),
        "system_prompt": "Você é Cerberus, o Gerente de Risco do Conselho CAOS.",
    }


def _nota_zettel_valida() -> dict:
    return {
        "titulo": "Estratégia de Liquidity Sweep no MNQ",
        "area": "Modulo_Institucional",
        "tags": ["order-flow", "liquidity-sweep"],
        "data_criacao": UTC_2026,
        "agente_autor": "Odin",
    }


def _proposta_valida() -> dict:
    return {
        "id": "P1",
        "autor": "Mister_M",
        "resumo": "Trailing 3 fases com gatilhos em 1R, 2R, 3R",
        "conteudo": "Conteúdo detalhado da proposta P1.",
        "confianca": 80,
    }


def _veto_risco_valido() -> dict:
    return {
        "tipo": "veto_de_risco",
        "autor": "Cerberus",
        "decisao": "aprovar-com-ressalvas",
        "proposta_alvo": "P2",
        "justificativa": "Delta de exposição +12%; razão R/R = 1,8",
        "categoria_tecnica": None,
    }


def _veto_tecnico_valido() -> dict:
    return {
        "tipo": "veto_tecnico",
        "autor": "Hermes",
        "decisao": "bloquear",
        "proposta_alvo": "P1",
        "justificativa": "MSBuild retornou exit code 1.",
        "categoria_tecnica": "compilacao_falhou",
    }


def _decisao_final_valida() -> dict:
    return {
        "proposta_aceita": "P1",
        "rationale": "Proposta P1 atinge consenso 2/3 sem veto bloqueante.",
    }


def _turno_valido() -> dict:
    return {
        "numero": 1,
        "agente": "Athena",
        "modelo": "claude-opus-4.7",
        "timestamp": "2026-05-14T14:00:12-03:00",
        "fase": "PROPOSTAS",
        "nao_deterministico": False,
        "notas_injetadas": ["Modulo_Risco/Trailing_Tres_Fases.md"],
        "contexto_hash_sha256": HASH_SHA256_VALIDO,
        "cache_hit": False,
        "status": "ok",
        "conteudo_markdown": "### Proposta\n...",
    }


def _debate_valido() -> dict:
    return {
        "identificador": "2026-05-14-01",
        "titulo": "implementacao-circuit-breaker-fase-2",
        "data_inicio": "2026-05-14T14:00:00Z",
        "data_fim": "2026-05-14T14:18:32Z",
        "agentes_participantes": ["Athena", "Cerberus", "Mister_M"],
        "modelos": {
            "Athena": "claude-opus-4.7",
            "Cerberus": "claude-sonnet-4.5",
            "Mister_M": "minimax-m2",
        },
        "contexto_hash_sha256": HASH_SHA256_VALIDO,
        "notas_injetadas": ["Modulo_Risco/Trailing_Tres_Fases.md"],
        "seeds": {"Athena": 42, "Cerberus": 42},
        "orcamento_de_turnos": 12,
        "turnos_consumidos": 9,
        "fase_final": "CONCLUIDO",
        "status": "concluido",
        "turnos": [],
    }


def _decisao_valida() -> dict:
    return {
        "identificador": "2026-05-14-01",
        "debate_relacionado": "2026-05-14-01-implementacao-circuit-breaker-fase-2.md",
        "agentes_participantes": ["Athena", "Cerberus", "Mister_M"],
        "propostas": [_proposta_valida()],
        "vetos": [],
        "decisao_final": _decisao_final_valida(),
        "links_zettel": ["[[Trailing_Tres_Fases]]"],
        "aprovado_walk_forward": True,
        "reproduzivel": "parcial",
        "regressao_detectada": False,
        "status": "concluido",
    }


def _regra_steering_valida() -> dict:
    return {
        "data": "2026-05-14",
        "autor": "Athena",
        "justificativa": "Documenta a distinção entre State.Historical e State.Realtime.",
    }


def _nota_paper_valida() -> dict:
    return {
        "titulo": "Volatility Clustering in Micro Futures",
        "area": "Papers",
        "tags": ["volatility", "garch"],
        "data_criacao": "2026-05-14T15:00:00Z",
        "agente_autor": "Explorador",
        "sharpe_replicado": 0.74,
        "sample_size": 504,
        "out_of_sample_periodo": 126,
        "instrumento_testado": "MNQ",
        "survivorship_bias_tratado": True,
        "status": "aprovada",
    }


def _entrada_cache_valida() -> dict:
    return {
        "chave": HASH_SHA256_VALIDO,
        "agente": "Athena",
        "modelo": "claude-opus-4.7",
        "seed": "42",
        "data_criacao": UTC_2026,
        "tokens_consumidos_estimados": 1234,
        "resposta": "Resposta cacheada.",
    }


def _estado_orcamento_valido() -> dict:
    return {
        "agente": "Athena",
        "tokens_input_consumidos": 1000,
        "tokens_output_consumidos": 500,
        "tokens_total_consumidos": 1500,
        "orcamento_diario_tokens": 100000,
    }


def _entrada_manifesto_valida() -> dict:
    return {
        "nome_arquivo": "1m/MNQ-2026-01.csv",
        "tamanho_bytes": 1_048_576,
        "mtime": UTC_2026,
        "num_linhas": 6500,
        "hash_sha256": HASH_SHA256_VALIDO,
        "periodo_inicial": "2026-01-02T13:30:00Z",
        "periodo_final": "2026-01-30T20:00:00Z",
        "instrumento": "MNQ",
    }


# ---------------------------------------------------------------------------
# AgentProfile
# ---------------------------------------------------------------------------


class TestAgentProfile:
    def test_caso_valido(self) -> None:
        perfil = AgentProfile(**_agent_profile_valido())
        assert perfil.nome == "Cerberus"
        assert perfil.modelo == "claude-sonnet-4.5"
        assert perfil.tags_especialidade == ["risco", "circuit-breaker"]
        assert isinstance(perfil.formato_de_saida, FormatoDeSaida)

    def test_aceita_skills_permitidas_vazia(self) -> None:
        # R2.2 admite lista vazia (alguns agentes não invocam Skills).
        dados = _agent_profile_valido()
        dados["skills_permitidas"] = []
        perfil = AgentProfile(**dados)
        assert perfil.skills_permitidas == []

    def test_invalido_modelo_divergente_para_agente(self) -> None:
        # R2.3: Cerberus exige claude-sonnet-4.5.
        dados = _agent_profile_valido()
        dados["modelo"] = "claude-haiku-4.5"
        with pytest.raises(ValidationError) as exc:
            AgentProfile(**dados)
        assert "agente" in str(exc.value).lower() or "modelo" in str(exc.value).lower()

    def test_invalido_nome_fora_do_enum(self) -> None:
        dados = _agent_profile_valido()
        dados["nome"] = "Loki"
        with pytest.raises(ValidationError):
            AgentProfile(**dados)

    def test_invalido_skill_desconhecida(self) -> None:
        dados = _agent_profile_valido()
        dados["skills_permitidas"] = ["Skill_Inexistente"]
        with pytest.raises(ValidationError):
            AgentProfile(**dados)

    def test_invalido_system_prompt_vazio(self) -> None:
        dados = _agent_profile_valido()
        dados["system_prompt"] = ""
        with pytest.raises(ValidationError):
            AgentProfile(**dados)

    def test_invalido_system_prompt_excede_8000(self) -> None:
        dados = _agent_profile_valido()
        dados["system_prompt"] = "x" * 8001
        with pytest.raises(ValidationError):
            AgentProfile(**dados)

    def test_invalido_tags_vazio(self) -> None:
        dados = _agent_profile_valido()
        dados["tags_especialidade"] = []
        with pytest.raises(ValidationError):
            AgentProfile(**dados)

    def test_invalido_extra_field_proibido(self) -> None:
        dados = _agent_profile_valido()
        dados["campo_estranho"] = "x"
        with pytest.raises(ValidationError):
            AgentProfile(**dados)

    @pytest.mark.parametrize(
        "agente, modelo_correto",
        [
            ("Athena", "claude-opus-4.7"),
            ("Odin", "claude-sonnet-4.5"),
            ("Manolo", "claude-haiku-4.5"),
            ("Rodrigo", "deepseek-v3.1"),
            ("Hermes", "qwen3-coder"),
            ("Hermes", "deepseek-v3.1"),
            ("Mister_M", "minimax-m2"),
            ("Mister_M", "qwen3"),
            ("Explorador", "claude-sonnet-4.5"),
            ("Devils_Advocate", "minimax-m2"),
        ],
    )
    def test_pares_agente_modelo_validos(self, agente: str, modelo_correto: str) -> None:
        dados = _agent_profile_valido()
        dados["nome"] = agente
        dados["modelo"] = modelo_correto
        perfil = AgentProfile(**dados)
        assert perfil.nome == agente
        assert perfil.modelo == modelo_correto


# ---------------------------------------------------------------------------
# Sub-modelo FormatoDeSaida / ConfiancaSchema
# ---------------------------------------------------------------------------


class TestFormatoDeSaida:
    def test_caso_valido(self) -> None:
        formato = FormatoDeSaida(**_formato_saida_valido())
        assert formato.secoes_obrigatorias == [
            "Proposta",
            "Justificativa",
            "Riscos",
            "Confianca",
        ]

    def test_invalido_ordem_diferente(self) -> None:
        dados = _formato_saida_valido()
        dados["secoes_obrigatorias"] = [
            "Justificativa",
            "Proposta",
            "Riscos",
            "Confianca",
        ]
        with pytest.raises(ValidationError):
            FormatoDeSaida(**dados)

    def test_invalido_intervalo_confianca(self) -> None:
        dados = _formato_saida_valido()
        dados["confianca"] = {"tipo": "inteiro", "minimo": 10, "maximo": 90}
        with pytest.raises(ValidationError):
            FormatoDeSaida(**dados)

    def test_invalido_tipo_confianca(self) -> None:
        with pytest.raises(ValidationError):
            ConfiancaSchema(tipo="float", minimo=0, maximo=100)


# ---------------------------------------------------------------------------
# NotaZettel
# ---------------------------------------------------------------------------


class TestNotaZettel:
    def test_caso_valido(self) -> None:
        nota = NotaZettel(**_nota_zettel_valida())
        assert nota.area == "Modulo_Institucional"
        assert nota.data_criacao.tzinfo is not None
        assert nota.data_criacao.utcoffset().total_seconds() == 0

    def test_caso_valido_com_corpo_e_links(self) -> None:
        dados = _nota_zettel_valida()
        dados["corpo_markdown"] = "# Título\n\nLink para [[OutraNota]] aqui."
        dados["wiki_links"] = ["OutraNota"]
        nota = NotaZettel(**dados)
        assert nota.wiki_links == ["OutraNota"]

    def test_invalido_area_fora_enum(self) -> None:
        dados = _nota_zettel_valida()
        dados["area"] = "Modulo_Inexistente"
        with pytest.raises(ValidationError):
            NotaZettel(**dados)

    def test_invalido_data_sem_fuso(self) -> None:
        dados = _nota_zettel_valida()
        dados["data_criacao"] = "2026-05-14T13:42:00"
        with pytest.raises(ValidationError):
            NotaZettel(**dados)

    def test_invalido_data_offset_nao_utc(self) -> None:
        dados = _nota_zettel_valida()
        dados["data_criacao"] = "2026-05-14T13:42:00-03:00"
        with pytest.raises(ValidationError):
            NotaZettel(**dados)

    def test_invalido_titulo_vazio(self) -> None:
        dados = _nota_zettel_valida()
        dados["titulo"] = ""
        with pytest.raises(ValidationError):
            NotaZettel(**dados)

    def test_invalido_tags_excede_20(self) -> None:
        dados = _nota_zettel_valida()
        dados["tags"] = [f"tag-{i}" for i in range(21)]
        with pytest.raises(ValidationError):
            NotaZettel(**dados)

    def test_invalido_agente_autor_fora_enum(self) -> None:
        dados = _nota_zettel_valida()
        dados["agente_autor"] = "Loki"
        with pytest.raises(ValidationError):
            NotaZettel(**dados)


# ---------------------------------------------------------------------------
# Proposta
# ---------------------------------------------------------------------------


class TestProposta:
    def test_caso_valido(self) -> None:
        proposta = Proposta(**_proposta_valida())
        assert proposta.id == "P1"
        assert proposta.confianca == 80

    def test_invalido_id_formato_errado(self) -> None:
        dados = _proposta_valida()
        dados["id"] = "Proposta-1"
        with pytest.raises(ValidationError):
            Proposta(**dados)

    def test_invalido_confianca_fora_intervalo(self) -> None:
        dados = _proposta_valida()
        dados["confianca"] = 150
        with pytest.raises(ValidationError):
            Proposta(**dados)

    def test_invalido_confianca_negativa(self) -> None:
        dados = _proposta_valida()
        dados["confianca"] = -1
        with pytest.raises(ValidationError):
            Proposta(**dados)

    def test_invalido_resumo_excede_500(self) -> None:
        dados = _proposta_valida()
        dados["resumo"] = "x" * 501
        with pytest.raises(ValidationError):
            Proposta(**dados)

    def test_invalido_autor_fora_enum(self) -> None:
        dados = _proposta_valida()
        dados["autor"] = "Loki"
        with pytest.raises(ValidationError):
            Proposta(**dados)


# ---------------------------------------------------------------------------
# Veto
# ---------------------------------------------------------------------------


class TestVeto:
    def test_veto_de_risco_valido(self) -> None:
        veto = Veto(**_veto_risco_valido())
        assert veto.tipo == "veto_de_risco"
        assert veto.autor == "Cerberus"

    def test_veto_tecnico_valido(self) -> None:
        veto = Veto(**_veto_tecnico_valido())
        assert veto.tipo == "veto_tecnico"
        assert veto.categoria_tecnica == "compilacao_falhou"

    def test_invalido_veto_de_risco_autor_errado(self) -> None:
        dados = _veto_risco_valido()
        dados["autor"] = "Hermes"
        with pytest.raises(ValidationError):
            Veto(**dados)

    def test_invalido_veto_de_risco_com_categoria_tecnica(self) -> None:
        dados = _veto_risco_valido()
        dados["categoria_tecnica"] = "compilacao_falhou"
        with pytest.raises(ValidationError):
            Veto(**dados)

    def test_invalido_veto_tecnico_autor_errado(self) -> None:
        dados = _veto_tecnico_valido()
        dados["autor"] = "Cerberus"
        with pytest.raises(ValidationError):
            Veto(**dados)

    def test_invalido_veto_tecnico_decisao_errada(self) -> None:
        dados = _veto_tecnico_valido()
        dados["decisao"] = "aprovar-com-ressalvas"
        with pytest.raises(ValidationError):
            Veto(**dados)

    def test_invalido_veto_tecnico_sem_categoria(self) -> None:
        dados = _veto_tecnico_valido()
        dados["categoria_tecnica"] = None
        with pytest.raises(ValidationError):
            Veto(**dados)

    def test_invalido_proposta_alvo_formato(self) -> None:
        dados = _veto_risco_valido()
        dados["proposta_alvo"] = "PA"
        with pytest.raises(ValidationError):
            Veto(**dados)


# ---------------------------------------------------------------------------
# Turno
# ---------------------------------------------------------------------------


class TestTurno:
    def test_caso_valido(self) -> None:
        turno = Turno(**_turno_valido())
        assert turno.numero == 1
        assert turno.fase == "PROPOSTAS"

    def test_aceita_offset_nao_utc(self) -> None:
        # Turno aceita qualquer fuso, contanto que tzinfo esteja presente.
        dados = _turno_valido()
        dados["timestamp"] = "2026-05-14T11:00:12-03:00"
        turno = Turno(**dados)
        assert turno.timestamp.tzinfo is not None

    def test_invalido_fase_fora_enum(self) -> None:
        dados = _turno_valido()
        dados["fase"] = "FASE_INEXISTENTE"
        with pytest.raises(ValidationError):
            Turno(**dados)

    def test_invalido_numero_zero(self) -> None:
        dados = _turno_valido()
        dados["numero"] = 0
        with pytest.raises(ValidationError):
            Turno(**dados)

    def test_invalido_hash_formato(self) -> None:
        dados = _turno_valido()
        dados["contexto_hash_sha256"] = "naoehex"
        with pytest.raises(ValidationError):
            Turno(**dados)

    def test_invalido_status_fora_enum(self) -> None:
        dados = _turno_valido()
        dados["status"] = "outro-status"
        with pytest.raises(ValidationError):
            Turno(**dados)

    def test_invalido_timestamp_sem_tz(self) -> None:
        dados = _turno_valido()
        dados["timestamp"] = "2026-05-14T14:00:12"
        with pytest.raises(ValidationError):
            Turno(**dados)


# ---------------------------------------------------------------------------
# Debate
# ---------------------------------------------------------------------------


class TestDebate:
    def test_caso_valido(self) -> None:
        debate = Debate(**_debate_valido())
        assert debate.identificador == "2026-05-14-01"
        assert debate.orcamento_de_turnos == 12

    def test_invalido_identificador_formato(self) -> None:
        dados = _debate_valido()
        dados["identificador"] = "2026-05-14"
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_titulo_com_maiusculas(self) -> None:
        dados = _debate_valido()
        dados["titulo"] = "Implementacao-CircuitBreaker"
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_titulo_excede_60_chars(self) -> None:
        dados = _debate_valido()
        dados["titulo"] = "a" * 61
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_orcamento_abaixo_minimo(self) -> None:
        dados = _debate_valido()
        dados["orcamento_de_turnos"] = 3
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_orcamento_acima_maximo(self) -> None:
        dados = _debate_valido()
        dados["orcamento_de_turnos"] = 101
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_agentes_participantes_vazio(self) -> None:
        dados = _debate_valido()
        dados["agentes_participantes"] = []
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_status_fora_enum(self) -> None:
        dados = _debate_valido()
        dados["status"] = "qualquer-coisa"
        with pytest.raises(ValidationError):
            Debate(**dados)

    def test_invalido_hash_formato(self) -> None:
        dados = _debate_valido()
        dados["contexto_hash_sha256"] = "Z" * 64
        with pytest.raises(ValidationError):
            Debate(**dados)


# ---------------------------------------------------------------------------
# DecisaoDoConselho
# ---------------------------------------------------------------------------


class TestDecisaoDoConselho:
    def test_caso_valido(self) -> None:
        decisao = DecisaoDoConselho(**_decisao_valida())
        assert decisao.identificador == "2026-05-14-01"
        assert decisao.reproduzivel == "parcial"
        assert decisao.decisao_final.proposta_aceita == "P1"

    def test_aceita_proposta_aceita_none(self) -> None:
        # Em casos sem-quorum / timeout, decisao_final.proposta_aceita pode ser None.
        dados = _decisao_valida()
        dados["decisao_final"] = {
            "proposta_aceita": None,
            "rationale": "Sem quórum atingido.",
        }
        dados["status"] = "sem-quorum"
        decisao = DecisaoDoConselho(**dados)
        assert decisao.decisao_final.proposta_aceita is None

    def test_invalido_propostas_vazia(self) -> None:
        dados = _decisao_valida()
        dados["propostas"] = []
        with pytest.raises(ValidationError):
            DecisaoDoConselho(**dados)

    def test_invalido_links_zettel_vazia(self) -> None:
        dados = _decisao_valida()
        dados["links_zettel"] = []
        with pytest.raises(ValidationError):
            DecisaoDoConselho(**dados)

    def test_invalido_link_zettel_formato(self) -> None:
        dados = _decisao_valida()
        dados["links_zettel"] = ["Trailing_Tres_Fases"]  # falta [[ ]]
        with pytest.raises(ValidationError):
            DecisaoDoConselho(**dados)

    def test_invalido_reproduzivel_fora_enum(self) -> None:
        dados = _decisao_valida()
        dados["reproduzivel"] = "talvez"
        with pytest.raises(ValidationError):
            DecisaoDoConselho(**dados)

    def test_invalido_identificador_formato(self) -> None:
        dados = _decisao_valida()
        dados["identificador"] = "2026/05/14-01"
        with pytest.raises(ValidationError):
            DecisaoDoConselho(**dados)


# ---------------------------------------------------------------------------
# RegraSteering
# ---------------------------------------------------------------------------


class TestRegraSteering:
    def test_caso_valido(self) -> None:
        regra = RegraSteering(**_regra_steering_valida())
        assert regra.autor == "Athena"
        assert isinstance(regra.data, date)

    def test_aceita_autor_usuario(self) -> None:
        dados = _regra_steering_valida()
        dados["autor"] = "usuario"
        regra = RegraSteering(**dados)
        assert regra.autor == "usuario"

    def test_invalido_data_formato_errado(self) -> None:
        dados = _regra_steering_valida()
        dados["data"] = "14/05/2026"
        with pytest.raises(ValidationError):
            RegraSteering(**dados)

    def test_invalido_autor_fora_enum(self) -> None:
        dados = _regra_steering_valida()
        dados["autor"] = "Cerberus"
        with pytest.raises(ValidationError):
            RegraSteering(**dados)

    def test_invalido_justificativa_curta(self) -> None:
        dados = _regra_steering_valida()
        dados["justificativa"] = "curta"
        with pytest.raises(ValidationError):
            RegraSteering(**dados)

    def test_invalido_autor_com_acento(self) -> None:
        # A regra normaliza para 'usuario' sem acento (R3.5 + decisão de
        # padronização documentada no design.md seção 3.5).
        dados = _regra_steering_valida()
        dados["autor"] = "usuário"
        with pytest.raises(ValidationError):
            RegraSteering(**dados)


# ---------------------------------------------------------------------------
# NotaPaper
# ---------------------------------------------------------------------------


class TestNotaPaper:
    def test_caso_valido(self) -> None:
        paper = NotaPaper(**_nota_paper_valida())
        assert paper.area == "Papers"
        assert paper.status == "aprovada"

    def test_invalido_area_diferente_de_papers(self) -> None:
        dados = _nota_paper_valida()
        dados["area"] = "Modulo_Institucional"
        with pytest.raises(ValidationError):
            NotaPaper(**dados)

    def test_invalido_sample_size_negativo(self) -> None:
        dados = _nota_paper_valida()
        dados["sample_size"] = -1
        with pytest.raises(ValidationError):
            NotaPaper(**dados)

    def test_invalido_status_fora_enum(self) -> None:
        dados = _nota_paper_valida()
        dados["status"] = "ok"
        with pytest.raises(ValidationError):
            NotaPaper(**dados)

    def test_invalido_instrumento_vazio(self) -> None:
        dados = _nota_paper_valida()
        dados["instrumento_testado"] = ""
        with pytest.raises(ValidationError):
            NotaPaper(**dados)


# ---------------------------------------------------------------------------
# EntradaCache
# ---------------------------------------------------------------------------


class TestEntradaCache:
    def test_caso_valido(self) -> None:
        entrada = EntradaCache(**_entrada_cache_valida())
        assert entrada.chave == HASH_SHA256_VALIDO
        assert entrada.tokens_consumidos_estimados == 1234

    def test_aceita_seed_vazia(self) -> None:
        dados = _entrada_cache_valida()
        dados["seed"] = ""
        entrada = EntradaCache(**dados)
        assert entrada.seed == ""

    def test_invalido_chave_nao_hex(self) -> None:
        dados = _entrada_cache_valida()
        dados["chave"] = "Z" * 64
        with pytest.raises(ValidationError):
            EntradaCache(**dados)

    def test_invalido_chave_tamanho(self) -> None:
        dados = _entrada_cache_valida()
        dados["chave"] = "a" * 32
        with pytest.raises(ValidationError):
            EntradaCache(**dados)

    def test_invalido_tokens_negativos(self) -> None:
        dados = _entrada_cache_valida()
        dados["tokens_consumidos_estimados"] = -10
        with pytest.raises(ValidationError):
            EntradaCache(**dados)

    def test_invalido_modelo_fora_enum(self) -> None:
        dados = _entrada_cache_valida()
        dados["modelo"] = "gpt-4"
        with pytest.raises(ValidationError):
            EntradaCache(**dados)

    def test_invalido_data_sem_tz(self) -> None:
        dados = _entrada_cache_valida()
        dados["data_criacao"] = "2026-05-14T13:42:00"
        with pytest.raises(ValidationError):
            EntradaCache(**dados)


# ---------------------------------------------------------------------------
# EstadoOrcamento
# ---------------------------------------------------------------------------


class TestEstadoOrcamento:
    def test_caso_valido(self) -> None:
        estado = EstadoOrcamento(**_estado_orcamento_valido())
        assert estado.tokens_total_consumidos == 1500

    def test_invalido_total_diferente_da_soma(self) -> None:
        dados = _estado_orcamento_valido()
        dados["tokens_total_consumidos"] = 9999
        with pytest.raises(ValidationError):
            EstadoOrcamento(**dados)

    def test_invalido_tokens_negativos(self) -> None:
        dados = _estado_orcamento_valido()
        dados["tokens_input_consumidos"] = -1
        with pytest.raises(ValidationError):
            EstadoOrcamento(**dados)

    def test_invalido_agente_fora_enum(self) -> None:
        dados = _estado_orcamento_valido()
        dados["agente"] = "Loki"
        with pytest.raises(ValidationError):
            EstadoOrcamento(**dados)

    def test_invalido_orcamento_negativo(self) -> None:
        dados = _estado_orcamento_valido()
        dados["orcamento_diario_tokens"] = -1
        with pytest.raises(ValidationError):
            EstadoOrcamento(**dados)


# ---------------------------------------------------------------------------
# EntradaManifesto
# ---------------------------------------------------------------------------


class TestEntradaManifesto:
    def test_caso_valido(self) -> None:
        entrada = EntradaManifesto(**_entrada_manifesto_valida())
        assert entrada.instrumento == "MNQ"
        assert entrada.mtime.tzinfo is not None

    def test_default_instrumento_mnq(self) -> None:
        dados = _entrada_manifesto_valida()
        dados.pop("instrumento")
        entrada = EntradaManifesto(**dados)
        assert entrada.instrumento == "MNQ"

    def test_invalido_caminho_com_backslash(self) -> None:
        dados = _entrada_manifesto_valida()
        dados["nome_arquivo"] = "1m\\MNQ-2026-01.csv"
        with pytest.raises(ValidationError):
            EntradaManifesto(**dados)

    def test_invalido_caminho_absoluto(self) -> None:
        dados = _entrada_manifesto_valida()
        dados["nome_arquivo"] = "/dados/MNQ/1m/MNQ-2026-01.csv"
        with pytest.raises(ValidationError):
            EntradaManifesto(**dados)

    def test_invalido_hash_formato(self) -> None:
        dados = _entrada_manifesto_valida()
        dados["hash_sha256"] = "Z" * 64
        with pytest.raises(ValidationError):
            EntradaManifesto(**dados)

    def test_invalido_tamanho_negativo(self) -> None:
        dados = _entrada_manifesto_valida()
        dados["tamanho_bytes"] = -1
        with pytest.raises(ValidationError):
            EntradaManifesto(**dados)

    def test_invalido_mtime_sem_tz(self) -> None:
        dados = _entrada_manifesto_valida()
        dados["mtime"] = "2026-05-14T13:42:00"
        with pytest.raises(ValidationError):
            EntradaManifesto(**dados)


# ---------------------------------------------------------------------------
# Sanity checks transversais
# ---------------------------------------------------------------------------


def test_constante_agentes_tem_9_elementos() -> None:
    assert len(AGENTES) == 9
    assert len(set(AGENTES)) == 9


def test_decisao_final_isolada_valida() -> None:
    """Sub-modelo DecisaoFinal exposto no __all__ para uso direto em testes."""
    df = DecisaoFinal(proposta_aceita="P1", rationale="ok")
    assert df.proposta_aceita == "P1"


def test_decisao_final_rejeita_proposta_aceita_formato_errado() -> None:
    with pytest.raises(ValidationError):
        DecisaoFinal(proposta_aceita="proposta-1", rationale="ok")


def test_nota_zettel_aceita_datetime_objeto() -> None:
    """Garante que ``data_criacao`` aceita ``datetime`` já tipado quando UTC."""
    dados = _nota_zettel_valida()
    dados["data_criacao"] = datetime(2026, 5, 14, 13, 42, 0, tzinfo=timezone.utc)
    nota = NotaZettel(**dados)
    assert nota.data_criacao.utcoffset().total_seconds() == 0
