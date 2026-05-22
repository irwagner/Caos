"""Testes unitários da estratégia ORB (Spec 4 — Task 5).

Cobre R8.1 do ``requirements.md`` do Spec 4:

- Range vazio (sessão sem barras dentro do Periodo_OR) → ``NADA``.
- Range degenerado (``high_or - low_or <= range_minimo_pontos``) → ``NADA``.
- Rompimento LONG limpo → ``LONG`` com stop = ``low_or``, alvo correto.
- Rompimento SHORT limpo → ``SHORT`` com stop = ``high_or``, alvo correto.
- Cooldown ativo após uma saída → recusa nova entrada.
- Hora de corte ultrapassada → ``NADA`` mesmo com rompimento.
- Fim de sessão com posição aberta → ``FECHAR``.
- ``entrou_nesta_sessao`` ⇒ recusa segunda entrada (R2.3).
- Validação de :class:`ParametrosORB` (ranges de R5).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

from caos.walk_forward.estrategias.orb_logica import (
    Barra,
    DecisaoORB,
    EstadoORB,
    ParametrosORB,
    decidir_acao,
    registrar_abertura_de_posicao,
    registrar_fechamento_de_posicao,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _barra(
    *,
    ts: datetime,
    o: float = 100.0,
    h: float = 100.0,
    l: float = 100.0,
    c: float = 100.0,
    v: float = 1000.0,
) -> Barra:
    return Barra(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def _ts(hora: int, minuto: int = 0, dia: int = 2) -> datetime:
    """Timestamp UTC em 2026-01-<dia> às <hora>:<minuto>."""
    return datetime(2026, 1, dia, hora, minuto, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ParametrosORB — validação de ranges
# ---------------------------------------------------------------------------


class TestParametrosORB:
    def test_defaults_validos(self) -> None:
        p = ParametrosORB()
        assert p.minutos_or == 30
        assert p.risco_multiplicador == 1.0
        assert p.alvo_multiplicador == 2.0

    @pytest.mark.parametrize("minutos", [4, 61, 0, -1])
    def test_minutos_or_fora_de_range(self, minutos: int) -> None:
        with pytest.raises(ValueError, match="minutos_or"):
            ParametrosORB(minutos_or=minutos)

    @pytest.mark.parametrize("mult", [0.4, 2.1, 0.0])
    def test_risco_multiplicador_fora_de_range(self, mult: float) -> None:
        with pytest.raises(ValueError, match="risco_multiplicador"):
            ParametrosORB(risco_multiplicador=mult)

    @pytest.mark.parametrize("mult", [0.4, 5.1])
    def test_alvo_multiplicador_fora_de_range(self, mult: float) -> None:
        with pytest.raises(ValueError, match="alvo_multiplicador"):
            ParametrosORB(alvo_multiplicador=mult)

    @pytest.mark.parametrize("cd", [-1, 121])
    def test_cooldown_fora_de_range(self, cd: int) -> None:
        with pytest.raises(ValueError, match="cooldown_minutos"):
            ParametrosORB(cooldown_minutos=cd)

    def test_sessao_inicio_apos_fim_rejeitado(self) -> None:
        with pytest.raises(ValueError, match="sessao_inicio_utc"):
            ParametrosORB(
                sessao_inicio_utc=time(20, 0),
                sessao_fim_utc=time(13, 30),
                hora_corte_entradas_utc=time(15, 0),
            )

    def test_corte_fora_da_janela_rejeitado(self) -> None:
        with pytest.raises(ValueError, match="hora_corte_entradas_utc"):
            ParametrosORB(hora_corte_entradas_utc=time(8, 0))


# ---------------------------------------------------------------------------
# Validação da Barra
# ---------------------------------------------------------------------------


class TestValidacaoBarra:
    def test_timestamp_naive_rejeitado(self) -> None:
        b = Barra(
            timestamp=datetime(2026, 1, 2, 14, 0),  # naive
            open=100,
            high=101,
            low=99,
            close=100.5,
            volume=1000,
        )
        with pytest.raises(ValueError, match="tz-aware"):
            decidir_acao(b, EstadoORB(), ParametrosORB())

    def test_timestamp_offset_nao_zero_rejeitado(self) -> None:
        offset_brasil = timezone(timedelta(hours=-3))
        b = Barra(
            timestamp=datetime(2026, 1, 2, 14, 0, tzinfo=offset_brasil),
            open=100,
            high=101,
            low=99,
            close=100.5,
            volume=1000,
        )
        with pytest.raises(ValueError, match="UTC"):
            decidir_acao(b, EstadoORB(), ParametrosORB())

    def test_high_nan_rejeitado(self) -> None:
        b = Barra(timestamp=_ts(14), open=100, high=float("nan"), low=99, close=100, volume=1000)
        with pytest.raises(ValueError, match="high"):
            decidir_acao(b, EstadoORB(), ParametrosORB())


# ---------------------------------------------------------------------------
# Acumulação do Opening Range (R1)
# ---------------------------------------------------------------------------


class TestAcumulacaoOR:
    def test_barra_dentro_do_or_acumula(self) -> None:
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # Sessão começa 13:30; barras em 13:30, 13:45 estão dentro do OR.
        b1 = _barra(ts=_ts(13, 30), o=100, h=105, l=99, c=104, v=1000)
        d1 = decidir_acao(b1, estado, params)
        assert d1.acao == "NADA"
        assert d1.motivo == "acumulando-or"
        assert estado.high_or == 105
        assert estado.low_or == 99
        assert estado.or_formado is False

        b2 = _barra(ts=_ts(13, 45), o=104, h=110, l=98, c=109, v=1000)
        d2 = decidir_acao(b2, estado, params)
        assert d2.acao == "NADA"
        assert estado.high_or == 110
        assert estado.low_or == 98

    def test_barra_apos_or_marca_formado(self) -> None:
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # 13:30–14:00 forma o OR; 14:00 é a primeira barra fora.
        decidir_acao(_barra(ts=_ts(13, 30), h=105, l=99, c=104), estado, params)
        decidir_acao(_barra(ts=_ts(13, 45), h=110, l=98, c=109), estado, params)
        d3 = decidir_acao(
            _barra(ts=_ts(14, 0), o=109, h=111, l=108, c=110.5),
            estado,
            params,
        )
        assert estado.or_formado is True
        # 110.5 NÃO rompe high_or=110 estritamente (close=110.5 > 110, então rompe!).
        # Vamos validar que a decisão é coerente — neste caso, é LONG.
        assert d3.acao == "LONG"

    def test_or_vazio_pula_sessao(self) -> None:
        """R1.4 — sem barras no Periodo_OR, sessão é pulada."""
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # Primeira barra da sessão chega 14:30 (após o fim do OR 13:30–14:00).
        b = _barra(ts=_ts(14, 30), h=110, l=100, c=109)
        d = decidir_acao(b, estado, params)
        assert d.acao == "NADA"
        assert d.motivo == "or-vazio"
        assert estado.or_formado is True
        # Mesmo com mais barras depois, a sessão fica pulada.
        d2 = decidir_acao(_barra(ts=_ts(15, 0), c=200), estado, params)
        assert d2.acao == "NADA"


# ---------------------------------------------------------------------------
# Rompimentos (R2)
# ---------------------------------------------------------------------------


class TestRompimentos:
    def _setup_or_normal(self) -> tuple[EstadoORB, ParametrosORB]:
        """Cria estado com OR formado em [99, 110] e devolve (estado, params)."""
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        decidir_acao(_barra(ts=_ts(13, 30), h=110, l=99, c=104), estado, params)
        decidir_acao(_barra(ts=_ts(13, 45), h=110, l=99, c=105), estado, params)
        return estado, params

    def test_rompimento_long_emite_long(self) -> None:
        estado, params = self._setup_or_normal()
        # Close=115 rompe high=110 estritamente.
        d = decidir_acao(_barra(ts=_ts(14, 0), c=115), estado, params)
        assert d.acao == "LONG"
        assert d.stop == 99  # low_or
        # alvo = 115 + (110-99) * 1.0 * 2.0 = 115 + 22 = 137.
        assert d.alvo == pytest.approx(137.0)
        assert d.motivo == "rompimento-long"

    def test_rompimento_short_emite_short(self) -> None:
        estado, params = self._setup_or_normal()
        d = decidir_acao(_barra(ts=_ts(14, 0), c=95), estado, params)
        assert d.acao == "SHORT"
        assert d.stop == 110  # high_or
        # alvo = 95 - (110-99) * 1.0 * 2.0 = 95 - 22 = 73.
        assert d.alvo == pytest.approx(73.0)

    def test_close_igual_a_high_or_nao_rompe(self) -> None:
        """R2.1 exige `>` estrito, não `>=`."""
        estado, params = self._setup_or_normal()
        d = decidir_acao(_barra(ts=_ts(14, 0), c=110.0), estado, params)
        assert d.acao == "NADA"
        assert d.motivo == "sem-rompimento"

    def test_range_degenerado_pula(self) -> None:
        """R3.3 — high_or - low_or <= range_minimo_pontos."""
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # OR de [99.7, 100.0] = 0.3 ponto, abaixo do default 0.5.
        decidir_acao(_barra(ts=_ts(13, 30), h=100.0, l=99.7, c=99.9), estado, params)
        d = decidir_acao(_barra(ts=_ts(14, 0), c=110), estado, params)
        assert d.acao == "NADA"
        assert d.motivo == "range-degenerado"


# ---------------------------------------------------------------------------
# Cooldown e segunda entrada (R2.3, R4)
# ---------------------------------------------------------------------------


class TestCooldownEEntradaUnica:
    def test_segunda_entrada_na_mesma_sessao_bloqueada(self) -> None:
        """R2.3 — após primeira entrada na sessão, nova é bloqueada até o próximo dia."""
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # Forma o OR.
        decidir_acao(_barra(ts=_ts(13, 30), h=110, l=99, c=104), estado, params)
        # Entra LONG.
        d1 = decidir_acao(_barra(ts=_ts(14, 0), c=115), estado, params)
        assert d1.acao == "LONG"
        registrar_abertura_de_posicao(estado, d1)
        # Simula fechamento (PnL realizado).
        registrar_fechamento_de_posicao(estado, _ts(14, 30), params)
        # Tenta segunda entrada após cooldown — bloqueada por R2.3.
        ts_pos_cooldown = _ts(14, 30) + timedelta(minutes=params.cooldown_minutos + 5)
        d2 = decidir_acao(_barra(ts=ts_pos_cooldown, c=120), estado, params)
        assert d2.acao == "NADA"
        assert d2.motivo == "ja-entrou-nesta-sessao"

    def test_cooldown_bloqueia_nova_entrada(self) -> None:
        estado = EstadoORB()
        # Permitimos múltiplas entradas via R2.3 desabilitada (entrou_nesta_sessao=False).
        # Para isolar o cooldown, abrimos e fechamos sem marcar entrou_nesta_sessao.
        params = ParametrosORB(minutos_or=30, cooldown_minutos=15)
        decidir_acao(_barra(ts=_ts(13, 30), h=110, l=99, c=104), estado, params)
        d1 = decidir_acao(_barra(ts=_ts(14, 0), c=115), estado, params)
        assert d1.acao == "LONG"
        # Manualmente fecha sem registrar entrou_nesta_sessao para isolar cooldown.
        estado.posicao = "NADA"
        estado.cooldown_ate = _ts(14, 0) + timedelta(minutes=15)
        # Tenta nova entrada DENTRO do cooldown.
        d_dentro = decidir_acao(_barra(ts=_ts(14, 5), c=120), estado, params)
        assert d_dentro.acao == "NADA"
        assert d_dentro.motivo == "cooldown"

    def test_apos_hora_de_corte_bloqueia(self) -> None:
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30, hora_corte_entradas_utc=time(15, 0))
        decidir_acao(_barra(ts=_ts(13, 30), h=110, l=99, c=104), estado, params)
        # Rompimento LONG às 15:30 — após o corte de 15:00.
        d = decidir_acao(_barra(ts=_ts(15, 30), c=120), estado, params)
        assert d.acao == "NADA"
        assert d.motivo == "apos-hora-de-corte"


# ---------------------------------------------------------------------------
# Fim de sessão com posição aberta (R4.3)
# ---------------------------------------------------------------------------


class TestFimDeSessao:
    def test_fim_de_sessao_fecha_posicao_aberta(self) -> None:
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30, sessao_fim_utc=time(20, 0))
        decidir_acao(_barra(ts=_ts(13, 30), h=110, l=99, c=104), estado, params)
        d_long = decidir_acao(_barra(ts=_ts(14, 0), c=115), estado, params)
        assert d_long.acao == "LONG"
        registrar_abertura_de_posicao(estado, d_long)
        # Última barra da sessão (19:59 UTC, dentro da janela [sessao_fim - 1min, sessao_fim)).
        d_fim = decidir_acao(_barra(ts=_ts(19, 59), c=120), estado, params)
        assert d_fim.acao == "FECHAR"
        assert d_fim.motivo == "fim-de-sessao"

    def test_barra_fora_da_sessao_e_nada(self) -> None:
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # 12:00 é antes da sessão (13:30–20:00).
        d = decidir_acao(_barra(ts=_ts(12, 0), c=100), estado, params)
        assert d.acao == "NADA"
        assert d.motivo == "fora-da-sessao"


# ---------------------------------------------------------------------------
# Reset entre sessões (R1.3)
# ---------------------------------------------------------------------------


class TestResetEntreSessoes:
    def test_mudanca_de_dia_reseta_estado_or(self) -> None:
        estado = EstadoORB()
        params = ParametrosORB(minutos_or=30)
        # Sessão dia 2.
        decidir_acao(_barra(ts=_ts(13, 30, dia=2), h=110, l=99, c=104), estado, params)
        d_long_dia2 = decidir_acao(_barra(ts=_ts(14, 0, dia=2), c=115), estado, params)
        assert d_long_dia2.acao == "LONG"
        registrar_abertura_de_posicao(estado, d_long_dia2)
        registrar_fechamento_de_posicao(estado, _ts(14, 30, dia=2), params)
        # Próxima barra é no dia 3 — deve resetar tudo.
        d_dia3 = decidir_acao(_barra(ts=_ts(13, 30, dia=3), h=200, l=190, c=195), estado, params)
        assert d_dia3.motivo == "acumulando-or"  # OR resetado, está acumulando de novo
        assert estado.entrou_nesta_sessao is False
        assert estado.cooldown_ate is None
        assert estado.high_or == 200
        assert estado.low_or == 190
