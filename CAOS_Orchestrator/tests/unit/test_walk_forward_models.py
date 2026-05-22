"""Testes unitários dos modelos Pydantic v2 de ``caos.walk_forward.models``.

Cobre os 4 modelos públicos exigidos pela Task 1 do Spec
``caos-walk-forward``:

- :class:`ConfiguracaoWalkForward` — limites e regra Treino ≥ Teste (R2).
- :class:`JanelaWF` — ordem cronológica e UTC.
- :class:`ResultadoJanela` — métricas, status e regra de drawdown ≥ 0 (R6).
- :class:`ResultadoWalkForward` — agregação, índices crescentes e R10.2.

Cada modelo recebe pelo menos um caso válido (sanity check) e múltiplos
casos inválidos cobrindo: campos faltando, tipos errados, ranges fora
de limite, regex falho e regras cruzadas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from caos.walk_forward.models import (
    ConfiguracaoWalkForward,
    JanelaWF,
    ResultadoJanela,
    ResultadoWalkForward,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64

UTC = timezone.utc


def _config_valida(**overrides) -> dict:
    base = {
        "tamanho_treino_dias_uteis": 252,
        "tamanho_teste_dias_uteis": 63,
        "instrumento": "MNQ",
        "granularidade": "1m",
        "seed": 42,
    }
    base.update(overrides)
    return base


def _janela_valida(
    *,
    indice: int = 0,
    treino_inicio: datetime = datetime(2024, 1, 2, 13, 30, tzinfo=UTC),
    duracao_treino_dias: int = 252,
    duracao_teste_dias: int = 63,
    hash_dados: str = HASH_A,
) -> dict:
    treino_fim = treino_inicio + timedelta(days=duracao_treino_dias)
    teste_inicio = treino_fim
    teste_fim = teste_inicio + timedelta(days=duracao_teste_dias)
    return {
        "indice": indice,
        "treino_inicio": treino_inicio,
        "treino_fim": treino_fim,
        "teste_inicio": teste_inicio,
        "teste_fim": teste_fim,
        "hash_dados": hash_dados,
    }


def _resultado_janela_ok(**overrides) -> dict:
    base = {
        "janela": _janela_valida(),
        "estrategia": "exemplo_breakout",
        "configuracao": _config_valida(),
        "sharpe_anualizado": 1.25,
        "calmar": 0.85,
        "drawdown_maximo_percentual": 0.12,
        "drawdown_maximo_dias": 14,
        "win_rate": 0.55,
        "payoff_medio": 1.4,
        "mfe_medio": 32.5,
        "mae_medio": -18.0,
        "numero_trades": 47,
        "pnl_total": 1850.50,
        "look_ahead_violation": False,
        "status": "ok",
        "motivo_falha": None,
        "duracao_ms": 1234,
    }
    base.update(overrides)
    return base


def _resultado_janela_sem_trades(**overrides) -> dict:
    base = {
        "janela": _janela_valida(),
        "estrategia": "exemplo_breakout",
        "configuracao": _config_valida(),
        "sharpe_anualizado": None,
        "calmar": None,
        "drawdown_maximo_percentual": None,
        "drawdown_maximo_dias": None,
        "win_rate": None,
        "payoff_medio": None,
        "mfe_medio": None,
        "mae_medio": None,
        "numero_trades": 0,
        "pnl_total": 0.0,
        "look_ahead_violation": False,
        "status": "sem-trades",
        "motivo_falha": None,
        "duracao_ms": 1234,
    }
    base.update(overrides)
    return base


def _resultado_janela_falha(**overrides) -> dict:
    base = {
        "janela": _janela_valida(),
        "estrategia": "exemplo_breakout",
        "configuracao": _config_valida(),
        "sharpe_anualizado": None,
        "calmar": None,
        "drawdown_maximo_percentual": None,
        "drawdown_maximo_dias": None,
        "win_rate": None,
        "payoff_medio": None,
        "mfe_medio": None,
        "mae_medio": None,
        "numero_trades": 0,
        "pnl_total": 0.0,
        "look_ahead_violation": False,
        "status": "falha",
        "motivo_falha": "ValueError: divisão por zero ao calcular Sharpe",
        "duracao_ms": 50,
    }
    base.update(overrides)
    return base


# ===========================================================================
# ConfiguracaoWalkForward (R2)
# ===========================================================================


class TestConfiguracaoWalkForward:
    """Cobre R2.1 (ranges) e R2.2 (Treino ≥ Teste)."""

    def test_caso_valido_padrao(self) -> None:
        c = ConfiguracaoWalkForward(**_config_valida())
        assert c.tamanho_treino_dias_uteis == 252
        assert c.tamanho_teste_dias_uteis == 63
        assert c.instrumento == "MNQ"
        assert c.granularidade == "1m"
        assert c.seed == 42

    def test_passo_default_igual_teste(self) -> None:
        # R2.1 — passo defaulta para tamanho_teste_dias_uteis quando ausente.
        c = ConfiguracaoWalkForward(**_config_valida())
        assert c.passo_dias_uteis == 63

    def test_passo_explicito_preservado(self) -> None:
        c = ConfiguracaoWalkForward(**_config_valida(passo_dias_uteis=20))
        assert c.passo_dias_uteis == 20

    def test_granularidade_tick(self) -> None:
        c = ConfiguracaoWalkForward(**_config_valida(granularidade="tick"))
        assert c.granularidade == "tick"

    @pytest.mark.parametrize("treino", [59, 0, -1])
    def test_treino_abaixo_do_minimo(self, treino: int) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(
                **_config_valida(tamanho_treino_dias_uteis=treino)
            )

    @pytest.mark.parametrize("treino", [505, 1000])
    def test_treino_acima_do_maximo(self, treino: int) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(
                **_config_valida(tamanho_treino_dias_uteis=treino)
            )

    @pytest.mark.parametrize("teste", [9, 0, -5])
    def test_teste_abaixo_do_minimo(self, teste: int) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(
                **_config_valida(tamanho_teste_dias_uteis=teste)
            )

    @pytest.mark.parametrize("teste", [121, 200])
    def test_teste_acima_do_maximo(self, teste: int) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(
                **_config_valida(tamanho_teste_dias_uteis=teste)
            )

    def test_teste_maior_que_treino_e_rejeitado(self) -> None:
        # R2.2 — Treino sempre ≥ Teste. Aqui ambos respeitam ranges
        # individuais (treino=100, teste=120) mas violam a regra cruzada.
        with pytest.raises(ValidationError) as exc_info:
            ConfiguracaoWalkForward(
                **_config_valida(
                    tamanho_treino_dias_uteis=100,
                    tamanho_teste_dias_uteis=120,
                )
            )
        assert "Treino sempre" in str(exc_info.value) or "Treino" in str(
            exc_info.value
        )

    def test_treino_igual_teste_e_aceito(self) -> None:
        # Borda: Treino == Teste é permitido (R2.2 diz ≥, não >).
        c = ConfiguracaoWalkForward(
            **_config_valida(
                tamanho_treino_dias_uteis=120,
                tamanho_teste_dias_uteis=120,
            )
        )
        assert c.tamanho_treino_dias_uteis == 120
        assert c.tamanho_teste_dias_uteis == 120

    def test_passo_zero_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(**_config_valida(passo_dias_uteis=0))

    def test_granularidade_invalida(self) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(**_config_valida(granularidade="5m"))

    def test_extra_field_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ConfiguracaoWalkForward(
                **_config_valida(campo_inexistente="x")
            )

    def test_seed_pode_ser_negativo(self) -> None:
        # ``seed`` aceita qualquer int (random.seed também aceita negativos).
        c = ConfiguracaoWalkForward(**_config_valida(seed=-1))
        assert c.seed == -1


# ===========================================================================
# JanelaWF
# ===========================================================================


class TestJanelaWF:
    """Cobre ordem cronológica, exigência de UTC e formato do hash."""

    def test_caso_valido(self) -> None:
        j = JanelaWF(**_janela_valida())
        assert j.indice == 0
        assert j.treino_fim <= j.teste_inicio
        assert j.hash_dados == HASH_A

    def test_indice_negativo_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            JanelaWF(**_janela_valida(indice=-1))

    def test_treino_inicio_apos_treino_fim(self) -> None:
        ti = datetime(2024, 6, 1, tzinfo=UTC)
        tf = datetime(2024, 5, 1, tzinfo=UTC)
        with pytest.raises(ValidationError) as exc_info:
            JanelaWF(
                indice=0,
                treino_inicio=ti,
                treino_fim=tf,
                teste_inicio=datetime(2024, 7, 1, tzinfo=UTC),
                teste_fim=datetime(2024, 8, 1, tzinfo=UTC),
                hash_dados=HASH_A,
            )
        assert "treino_inicio" in str(exc_info.value)

    def test_treino_inicio_igual_treino_fim_rejeitado(self) -> None:
        # Estritamente menor: instante igual viola.
        ti = tf = datetime(2024, 5, 1, tzinfo=UTC)
        with pytest.raises(ValidationError):
            JanelaWF(
                indice=0,
                treino_inicio=ti,
                treino_fim=tf,
                teste_inicio=datetime(2024, 7, 1, tzinfo=UTC),
                teste_fim=datetime(2024, 8, 1, tzinfo=UTC),
                hash_dados=HASH_A,
            )

    def test_teste_inicio_apos_teste_fim(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            JanelaWF(
                indice=0,
                treino_inicio=datetime(2024, 1, 1, tzinfo=UTC),
                treino_fim=datetime(2024, 5, 1, tzinfo=UTC),
                teste_inicio=datetime(2024, 8, 1, tzinfo=UTC),
                teste_fim=datetime(2024, 7, 1, tzinfo=UTC),
                hash_dados=HASH_A,
            )
        assert "teste_inicio" in str(exc_info.value)

    def test_treino_sobrepoe_teste_rejeitado(self) -> None:
        # treino_fim > teste_inicio viola anti-lookahead estrutural (R5.3).
        with pytest.raises(ValidationError) as exc_info:
            JanelaWF(
                indice=0,
                treino_inicio=datetime(2024, 1, 1, tzinfo=UTC),
                treino_fim=datetime(2024, 6, 1, tzinfo=UTC),
                teste_inicio=datetime(2024, 5, 1, tzinfo=UTC),
                teste_fim=datetime(2024, 7, 1, tzinfo=UTC),
                hash_dados=HASH_A,
            )
        assert "treino_fim" in str(exc_info.value) and "teste_inicio" in str(
            exc_info.value
        )

    def test_treino_termina_exatamente_quando_teste_comeca_aceito(self) -> None:
        # Borda: treino_fim == teste_inicio é permitido (sem sobreposição).
        instante = datetime(2024, 5, 1, tzinfo=UTC)
        j = JanelaWF(
            indice=0,
            treino_inicio=datetime(2024, 1, 1, tzinfo=UTC),
            treino_fim=instante,
            teste_inicio=instante,
            teste_fim=datetime(2024, 7, 1, tzinfo=UTC),
            hash_dados=HASH_A,
        )
        assert j.treino_fim == j.teste_inicio

    def test_string_iso8601_z_aceita(self) -> None:
        j = JanelaWF(
            indice=0,
            treino_inicio="2024-01-02T13:30:00Z",
            treino_fim="2024-05-01T13:30:00Z",
            teste_inicio="2024-05-01T13:30:00Z",
            teste_fim="2024-07-01T13:30:00Z",
            hash_dados=HASH_A,
        )
        assert j.treino_inicio.tzinfo is not None

    def test_data_naive_rejeitada(self) -> None:
        with pytest.raises(ValidationError):
            JanelaWF(
                indice=0,
                treino_inicio=datetime(2024, 1, 1),  # naive
                treino_fim=datetime(2024, 5, 1, tzinfo=UTC),
                teste_inicio=datetime(2024, 5, 1, tzinfo=UTC),
                teste_fim=datetime(2024, 7, 1, tzinfo=UTC),
                hash_dados=HASH_A,
            )

    def test_offset_diferente_de_utc_rejeitado(self) -> None:
        offset_brasil = timezone(timedelta(hours=-3))
        with pytest.raises(ValidationError) as exc_info:
            JanelaWF(
                indice=0,
                treino_inicio=datetime(2024, 1, 1, tzinfo=offset_brasil),
                treino_fim=datetime(2024, 5, 1, tzinfo=UTC),
                teste_inicio=datetime(2024, 5, 1, tzinfo=UTC),
                teste_fim=datetime(2024, 7, 1, tzinfo=UTC),
                hash_dados=HASH_A,
            )
        assert "UTC" in str(exc_info.value)

    @pytest.mark.parametrize(
        "hash_invalido",
        ["", "abc", "z" * 64, "A" * 64, "a" * 63, "a" * 65],
    )
    def test_hash_dados_invalido(self, hash_invalido: str) -> None:
        with pytest.raises(ValidationError):
            JanelaWF(**_janela_valida(hash_dados=hash_invalido))

    def test_extra_field_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            payload = _janela_valida()
            payload["campo_extra"] = "x"
            JanelaWF(**payload)


# ===========================================================================
# ResultadoJanela (R6)
# ===========================================================================


class TestResultadoJanela:
    """Cobre métricas (R6), regras de status e drawdown não-negativo."""

    def test_caso_valido_ok(self) -> None:
        r = ResultadoJanela(**_resultado_janela_ok())
        assert r.status == "ok"
        assert r.numero_trades == 47

    def test_caso_valido_sem_trades(self) -> None:
        r = ResultadoJanela(**_resultado_janela_sem_trades())
        assert r.status == "sem-trades"
        assert r.numero_trades == 0
        assert r.sharpe_anualizado is None
        assert r.calmar is None
        assert r.win_rate is None

    def test_caso_valido_falha(self) -> None:
        r = ResultadoJanela(**_resultado_janela_falha())
        assert r.status == "falha"
        assert r.motivo_falha is not None

    # ---- Drawdown não-negativo (R6.1) -----------------------------------

    def test_drawdown_negativo_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(drawdown_maximo_percentual=-0.05))

    def test_drawdown_acima_de_um_rejeitado(self) -> None:
        # drawdown percentual em [0, 1].
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(drawdown_maximo_percentual=1.5))

    def test_drawdown_dias_negativo_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(drawdown_maximo_dias=-1))

    # ---- win_rate em [0, 1] ---------------------------------------------

    @pytest.mark.parametrize("win_rate", [-0.01, 1.01, 2.0, -5.0])
    def test_win_rate_fora_de_zero_um_rejeitado(self, win_rate: float) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(win_rate=win_rate))

    @pytest.mark.parametrize("win_rate", [0.0, 1.0, 0.5])
    def test_win_rate_dentro_dos_limites(self, win_rate: float) -> None:
        r = ResultadoJanela(**_resultado_janela_ok(win_rate=win_rate))
        assert r.win_rate == win_rate

    # ---- payoff_medio >= 0 ----------------------------------------------

    def test_payoff_medio_negativo_rejeitado(self) -> None:
        # Payoff médio é razão de magnitudes; não pode ser negativo.
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(payoff_medio=-0.5))

    # ---- numero_trades >= 0 ---------------------------------------------

    def test_numero_trades_negativo_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(numero_trades=-1))

    # ---- duracao_ms >= 0 ------------------------------------------------

    def test_duracao_ms_negativa_rejeitada(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(duracao_ms=-1))

    # ---- Regras cruzadas de status --------------------------------------

    def test_status_falha_exige_motivo_falha(self) -> None:
        # status="falha" sem motivo_falha viola R10.1.
        with pytest.raises(ValidationError) as exc_info:
            ResultadoJanela(
                **_resultado_janela_falha(motivo_falha=None)
            )
        assert "motivo_falha" in str(exc_info.value)

    def test_status_ok_com_zero_trades_rejeitado(self) -> None:
        # status="ok" sem trades é inconsistente — deve usar "sem-trades".
        with pytest.raises(ValidationError) as exc_info:
            ResultadoJanela(**_resultado_janela_ok(numero_trades=0))
        assert "sem-trades" in str(exc_info.value)

    def test_status_ok_com_motivo_falha_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(
                **_resultado_janela_ok(motivo_falha="ruído inesperado")
            )

    def test_status_sem_trades_com_trades_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(
                **_resultado_janela_sem_trades(numero_trades=3)
            )

    def test_status_sem_trades_com_metrica_preenchida_rejeitado(self) -> None:
        # R6.2: sem-trades exige métricas dependentes como None.
        with pytest.raises(ValidationError) as exc_info:
            ResultadoJanela(
                **_resultado_janela_sem_trades(sharpe_anualizado=1.5)
            )
        assert "sem-trades" in str(exc_info.value)

    def test_status_sem_trades_com_motivo_falha_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(
                **_resultado_janela_sem_trades(motivo_falha="qualquer coisa")
            )

    def test_motivo_falha_truncado_em_4096(self) -> None:
        # Limite de 4096 chars (R10.3).
        with pytest.raises(ValidationError):
            ResultadoJanela(
                **_resultado_janela_falha(motivo_falha="x" * 4097)
            )

    def test_motivo_falha_no_limite_aceito(self) -> None:
        r = ResultadoJanela(**_resultado_janela_falha(motivo_falha="x" * 4096))
        assert r.motivo_falha is not None
        assert len(r.motivo_falha) == 4096

    def test_status_invalido_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(status="ok-com-warnings"))

    def test_extra_field_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoJanela(**_resultado_janela_ok(campo_extra="x"))

    def test_pnl_total_pode_ser_negativo(self) -> None:
        r = ResultadoJanela(**_resultado_janela_ok(pnl_total=-1234.50))
        assert r.pnl_total == -1234.50

    def test_sharpe_pode_ser_negativo(self) -> None:
        r = ResultadoJanela(**_resultado_janela_ok(sharpe_anualizado=-2.1))
        assert r.sharpe_anualizado == -2.1


# ===========================================================================
# ResultadoWalkForward
# ===========================================================================


class TestResultadoWalkForward:
    """Cobre agregação de janelas, índices crescentes e R10.2."""

    def _construir_janela(
        self, indice: int, mes_inicio: int, *, status: str = "ok"
    ) -> dict:
        # Cada janela ocupa 1 mês de Treino + 1 mês de Teste, sem
        # sobreposição com a próxima.
        treino_inicio = datetime(2024, mes_inicio, 1, tzinfo=UTC)
        treino_fim = treino_inicio + timedelta(days=30)
        teste_inicio = treino_fim
        teste_fim = teste_inicio + timedelta(days=30)
        janela = {
            "indice": indice,
            "treino_inicio": treino_inicio,
            "treino_fim": treino_fim,
            "teste_inicio": teste_inicio,
            "teste_fim": teste_fim,
            "hash_dados": HASH_A,
        }
        if status == "ok":
            return _resultado_janela_ok(janela=janela)
        if status == "sem-trades":
            return _resultado_janela_sem_trades(janela=janela)
        if status == "falha":
            return _resultado_janela_falha(janela=janela)
        raise ValueError(status)

    def _resultado_valido(self, **overrides) -> dict:
        janelas = [
            self._construir_janela(0, 1),
            self._construir_janela(1, 3),
            self._construir_janela(2, 5),
        ]
        base = {
            "identificador": "2026-05-14-01",
            "estrategia": "exemplo_breakout",
            "configuracao": _config_valida(),
            "manifesto_hash": HASH_B,
            "janelas": janelas,
            "agregado_mediana": {"sharpe_anualizado": 1.25, "calmar": 0.85},
            "agregado_media": {"sharpe_anualizado": 1.10, "calmar": 0.78},
            "versoes_dependencias": {"pandas": "2.2.0", "numpy": "1.26.0"},
            "status": "concluido",
        }
        base.update(overrides)
        return base

    def test_caso_valido_concluido(self) -> None:
        r = ResultadoWalkForward(**self._resultado_valido())
        assert r.status == "concluido"
        assert len(r.janelas) == 3
        assert r.identificador == "2026-05-14-01"

    def test_identificador_formato_invalido(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoWalkForward(
                **self._resultado_valido(identificador="2026/05/14-01")
            )

    @pytest.mark.parametrize(
        "id_invalido",
        ["2026-5-14-01", "2026-05-14", "2026-05-14-1", "26-05-14-01"],
    )
    def test_identificador_formato_estrito(self, id_invalido: str) -> None:
        with pytest.raises(ValidationError):
            ResultadoWalkForward(
                **self._resultado_valido(identificador=id_invalido)
            )

    def test_manifesto_hash_invalido(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoWalkForward(
                **self._resultado_valido(manifesto_hash="abc")
            )

    def test_janelas_indices_nao_crescentes_rejeitado(self) -> None:
        # Indices fora de ordem: 0, 2, 1.
        janelas = [
            self._construir_janela(0, 1),
            self._construir_janela(2, 3),
            self._construir_janela(1, 5),
        ]
        with pytest.raises(ValidationError) as exc_info:
            ResultadoWalkForward(**self._resultado_valido(janelas=janelas))
        assert "indice" in str(exc_info.value)

    def test_janelas_com_indice_repetido_rejeitado(self) -> None:
        janelas = [
            self._construir_janela(0, 1),
            self._construir_janela(0, 3),
        ]
        with pytest.raises(ValidationError):
            ResultadoWalkForward(**self._resultado_valido(janelas=janelas))

    def test_janelas_sobrepostas_rejeitado(self) -> None:
        # Construímos manualmente janelas com sobreposição cronológica.
        j1 = _resultado_janela_ok(
            janela={
                "indice": 0,
                "treino_inicio": datetime(2024, 1, 1, tzinfo=UTC),
                "treino_fim": datetime(2024, 4, 1, tzinfo=UTC),
                "teste_inicio": datetime(2024, 4, 1, tzinfo=UTC),
                "teste_fim": datetime(2024, 6, 1, tzinfo=UTC),  # vai até junho
                "hash_dados": HASH_A,
            }
        )
        j2 = _resultado_janela_ok(
            janela={
                "indice": 1,
                "treino_inicio": datetime(2024, 2, 1, tzinfo=UTC),
                "treino_fim": datetime(2024, 5, 1, tzinfo=UTC),
                "teste_inicio": datetime(2024, 5, 1, tzinfo=UTC),  # sobrepõe j1
                "teste_fim": datetime(2024, 7, 1, tzinfo=UTC),
                "hash_dados": HASH_A,
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            ResultadoWalkForward(**self._resultado_valido(janelas=[j1, j2]))
        assert "não-sobrepostas" in str(exc_info.value) or "sobrepost" in str(
            exc_info.value
        )

    def test_status_concluido_sem_janelas_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoWalkForward(**self._resultado_valido(janelas=[]))

    def test_status_manifesto_invalido_exige_janelas_vazias(self) -> None:
        # status="manifesto-invalido" + janelas != [] → rejeitado.
        with pytest.raises(ValidationError):
            ResultadoWalkForward(
                **self._resultado_valido(status="manifesto-invalido")
            )

    def test_status_manifesto_invalido_com_janelas_vazias_aceito(self) -> None:
        r = ResultadoWalkForward(
            **self._resultado_valido(
                status="manifesto-invalido",
                janelas=[],
            )
        )
        assert r.status == "manifesto-invalido"
        assert r.janelas == []

    def test_status_abortado_por_falhas_exige_taxa_acima_de_30pct(self) -> None:
        # 3 janelas, 1 falha = 33,3% — aceito.
        janelas = [
            self._construir_janela(0, 1, status="ok"),
            self._construir_janela(1, 3, status="ok"),
            self._construir_janela(2, 5, status="falha"),
        ]
        r = ResultadoWalkForward(
            **self._resultado_valido(
                janelas=janelas,
                status="abortado-por-falhas",
            )
        )
        assert r.status == "abortado-por-falhas"

    def test_status_abortado_por_falhas_com_taxa_baixa_rejeitado(self) -> None:
        # 4 janelas, 1 falha = 25% — não basta para abortar.
        janelas = [
            self._construir_janela(0, 1, status="ok"),
            self._construir_janela(1, 3, status="ok"),
            self._construir_janela(2, 5, status="ok"),
            self._construir_janela(3, 7, status="falha"),
        ]
        with pytest.raises(ValidationError) as exc_info:
            ResultadoWalkForward(
                **self._resultado_valido(
                    janelas=janelas,
                    status="abortado-por-falhas",
                )
            )
        assert "30%" in str(exc_info.value) or "taxa" in str(exc_info.value)

    def test_status_invalido_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoWalkForward(
                **self._resultado_valido(status="em-andamento")
            )

    def test_extra_field_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            ResultadoWalkForward(
                **self._resultado_valido(campo_extra="x")
            )

    def test_uma_unica_janela_aceito(self) -> None:
        janelas = [self._construir_janela(0, 1)]
        r = ResultadoWalkForward(**self._resultado_valido(janelas=janelas))
        assert len(r.janelas) == 1
