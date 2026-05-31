"""Testes unitários da função pura ``decidir_acao`` da VVG Late-Session
Reversal (Spec — Tarefa 8).

Cobre as Properties 1, 5, 6, 7, 8, 9 e 12 do ``design.md`` desta feature,
além da validação de :class:`ParametrosVvg`:

- Property 1 (R2.1): ``decidir_acao`` é pura — não muta o estado recebido e
  é idempotente.
- Property 5 (R2.1): dias VVG-negativos nunca emitem trade (sempre NADA).
- Property 6 (R2.1): LONG/SHORT só são emitidos exatamente em 14:30 EST.
- Property 7 (R2.5): posição aberta + 15:50 EST → FECHAR (encerramento
  forçado de fim de sessão).
- Property 8 (R2.6): após um trade fechado no dia, novas barras → NADA
  (no máximo 1 trade por dia).
- Property 9 (R2.2): a entrada é OPOSTA ao drift — ``drift > 0`` → SHORT;
  ``drift <= 0`` → LONG.
- Property 12 (R4.1): o despacho conceitual é de 1 contrato; aqui validamos
  que toda entrada LONG/SHORT corresponde a exatamente uma posição (1 trade)
  e que o plugin emite ``contratos=1`` (ver ``test_vvg_plugin.py``).

Convenção de fuso (ver docstring de ``vvg_logica``): a :class:`Barra` chega
com ``timestamp`` em UTC; ``decidir_acao`` converte para horário de Nova
York. Os timestamps de teste são construídos em NY (via ``zoneinfo``) e
convertidos para UTC — assim 09:30 EDT = 13:30 UTC, 14:30 EDT = 18:30 UTC,
15:50 EDT = 19:50 UTC (horário de verão americano; usamos uma data de
julho, garantidamente EDT).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from caos.walk_forward.estrategias.vvg_logica import (
    AcaoVvg,
    Barra,
    EstadoVvg,
    ParametrosVvg,
    decidir_acao,
    registrar_saida_externa,
)

# ---------------------------------------------------------------------------
# Helpers de timestamp e barra
# ---------------------------------------------------------------------------

NY = ZoneInfo("America/New_York")
UTC = timezone.utc

#: Data-base dos testes: uma terça de julho (garantidamente EDT = UTC-4).
DATA = date(2025, 7, 8)


def _ts(hora: int, minuto: int = 0, *, dia: date = DATA) -> datetime:
    """Constrói um timestamp UTC a partir de um horário de Nova York.

    Localiza ``hora:minuto`` em ``America/New_York`` e converte para UTC,
    de forma que o DST (EST/EDT) seja resolvido pela ``zoneinfo`` — sem
    offset hardcoded.
    """
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=NY).astimezone(
        UTC
    )


def _barra(
    ts: datetime,
    *,
    o: float = 100.0,
    c: float = 100.0,
    h: float | None = None,
    l: float | None = None,
    v: float = 1000.0,
) -> Barra:
    """Barra OHLCV com high/low coerentes por default."""
    if h is None:
        h = max(o, c) + 1.0
    if l is None:
        l = min(o, c) - 1.0
    return Barra(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def _estado_pronto(
    *,
    vvg: bool = True,
    posicao: bool = False,
    direcao: str | None = None,
    preco: float | None = None,
    trade_fechado: bool = False,
    open_dia: float = 100.0,
) -> EstadoVvg:
    """Estado já no dia corrente (``DATA``), evitando o reset diário.

    ``dia_corrente`` é fixado em :data:`DATA` para que ``decidir_acao`` não
    dispare o reset de início de dia (que zera ``vvg_positivo``).
    """
    return EstadoVvg(
        dia_corrente=DATA,
        open_dia_atual=open_dia,
        vvg_positivo=vvg,
        posicao_aberta=posicao,
        direcao_atual=direcao,  # type: ignore[arg-type]
        preco_entrada=preco,
        trade_fechado_hoje=trade_fechado,
    )


PARAMS = ParametrosVvg.PadraoConfigurado()


# ---------------------------------------------------------------------------
# Property 1 — pureza e idempotência (R2.1)
# ---------------------------------------------------------------------------


class TestProperty1Pureza:
    def test_decidir_acao_pura_nao_muta_estado(self) -> None:
        """O estado original não é mutado; um NOVO estado é devolvido."""
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        barra = _barra(_ts(14, 30), o=100.0, c=105.0)  # drift +5 → SHORT

        acao, novo = decidir_acao(barra, estado, PARAMS)

        # A ação efetiva muda o estado de saída...
        assert acao == AcaoVvg.SHORT
        assert novo is not estado
        assert novo.posicao_aberta is True
        assert novo.direcao_atual == "SHORT"
        assert novo.preco_entrada == 105.0

        # ...mas o estado de entrada permanece intacto (pureza).
        assert estado.posicao_aberta is False
        assert estado.direcao_atual is None
        assert estado.preco_entrada is None
        assert estado.drift_close_referencia is None
        assert estado.vvg_positivo is True

    def test_decidir_acao_idempotente(self) -> None:
        """Duas chamadas com a mesma (barra, estado) → mesma ação e estado."""
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        barra = _barra(_ts(14, 30), o=100.0, c=95.0)  # drift -5 → LONG

        acao1, novo1 = decidir_acao(barra, estado, PARAMS)
        acao2, novo2 = decidir_acao(barra, estado, PARAMS)

        assert acao1 == acao2 == AcaoVvg.LONG
        assert novo1 == novo2  # EstadoVvg é dataclass → __eq__ por campos


# ---------------------------------------------------------------------------
# Property 5 — dias VVG-negativos nunca emitem trade (R2.1)
# ---------------------------------------------------------------------------


class TestProperty5VvgNegativo:
    @pytest.mark.parametrize("hora,minuto", [(13, 30), (14, 0), (14, 30), (15, 0)])
    @pytest.mark.parametrize("close", [90.0, 100.0, 110.0])
    def test_dia_vvg_negativo_emite_nada(
        self, hora: int, minuto: int, close: float
    ) -> None:
        estado = _estado_pronto(vvg=False, open_dia=100.0)
        barra = _barra(_ts(hora, minuto), o=100.0, c=close)
        acao, _ = decidir_acao(barra, estado, PARAMS)
        assert acao == AcaoVvg.NADA


# ---------------------------------------------------------------------------
# Property 6 — entrada apenas às 14:30 EST (R2.1)
# ---------------------------------------------------------------------------


class TestProperty6HorarioEntrada:
    @pytest.mark.parametrize(
        "hora,minuto",
        [(9, 30), (10, 0), (13, 30), (14, 0), (14, 29), (14, 31), (15, 0), (15, 49)],
    )
    def test_entrada_apenas_no_horario(self, hora: int, minuto: int) -> None:
        """Fora de 14:30 EST, sem posição, nunca há LONG/SHORT."""
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        barra = _barra(_ts(hora, minuto), o=100.0, c=110.0)  # drift +10
        acao, _ = decidir_acao(barra, estado, PARAMS)
        assert acao not in (AcaoVvg.LONG, AcaoVvg.SHORT)
        assert acao == AcaoVvg.NADA

    def test_exatamente_no_horario_emite(self) -> None:
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        barra = _barra(_ts(14, 30), o=100.0, c=110.0)
        acao, _ = decidir_acao(barra, estado, PARAMS)
        assert acao in (AcaoVvg.LONG, AcaoVvg.SHORT)


# ---------------------------------------------------------------------------
# Property 9 — entrada OPOSTA ao drift (R2.2)
# ---------------------------------------------------------------------------


class TestProperty9DirecaoOpostaAoDrift:
    @pytest.mark.parametrize("close", [100.25, 101.0, 150.0])
    def test_entrada_short_quando_drift_positivo(self, close: float) -> None:
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        barra = _barra(_ts(14, 30), o=100.0, c=close)  # drift > 0
        acao, novo = decidir_acao(barra, estado, PARAMS)
        assert acao == AcaoVvg.SHORT
        assert novo.direcao_atual == "SHORT"
        assert novo.sinal_atual == "vvg-rev-short"

    @pytest.mark.parametrize("close", [99.75, 50.0, 100.0])
    def test_entrada_long_quando_drift_negativo(self, close: float) -> None:
        """``drift <= 0`` (inclui drift exatamente 0) → LONG."""
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        barra = _barra(_ts(14, 30), o=100.0, c=close)  # drift <= 0
        acao, novo = decidir_acao(barra, estado, PARAMS)
        assert acao == AcaoVvg.LONG
        assert novo.direcao_atual == "LONG"
        assert novo.sinal_atual == "vvg-rev-long"


# ---------------------------------------------------------------------------
# Property 7 — encerramento forçado às 15:50 EST (R2.5)
# ---------------------------------------------------------------------------


class TestProperty7EncerramentoForcado:
    @pytest.mark.parametrize("hora,minuto", [(15, 50), (15, 51), (15, 59)])
    def test_encerramento_forcado(self, hora: int, minuto: int) -> None:
        estado = _estado_pronto(
            vvg=True, posicao=True, direcao="SHORT", preco=100.0, open_dia=100.0
        )
        barra = _barra(_ts(hora, minuto), o=100.0, c=100.0)
        acao, novo = decidir_acao(barra, estado, PARAMS)
        assert acao == AcaoVvg.FECHAR
        assert novo.posicao_aberta is False
        assert novo.trade_fechado_hoje is True

    def test_antes_do_encerramento_mantem_posicao(self) -> None:
        """Com posição aberta antes de 15:50 → NADA (mantém posição)."""
        estado = _estado_pronto(
            vvg=True, posicao=True, direcao="LONG", preco=100.0, open_dia=100.0
        )
        barra = _barra(_ts(15, 49), o=100.0, c=100.0)
        acao, novo = decidir_acao(barra, estado, PARAMS)
        assert acao == AcaoVvg.NADA
        assert novo.posicao_aberta is True


# ---------------------------------------------------------------------------
# Property 8 — no máximo 1 trade por dia (R2.6)
# ---------------------------------------------------------------------------


class TestProperty8UmTradePorDia:
    def test_um_trade_por_dia_apos_force_close(self) -> None:
        """Sequência completa: entra 14:30, fecha 15:50, não reentra no dia."""
        estado = _estado_pronto(vvg=True, open_dia=100.0)

        # Entrada às 14:30 (drift +10 → SHORT).
        acao_entrada, estado = decidir_acao(
            _barra(_ts(14, 30), o=100.0, c=110.0), estado, PARAMS
        )
        assert acao_entrada == AcaoVvg.SHORT

        # Force-close às 15:50.
        acao_fecha, estado = decidir_acao(
            _barra(_ts(15, 50), o=110.0, c=108.0), estado, PARAMS
        )
        assert acao_fecha == AcaoVvg.FECHAR
        assert estado.trade_fechado_hoje is True

        # Barra extra no mesmo dia (mesmo voltando a 14:30 hipoteticamente) → NADA.
        acao_extra, _ = decidir_acao(
            _barra(_ts(15, 55), o=108.0, c=120.0), estado, PARAMS
        )
        assert acao_extra == AcaoVvg.NADA

    def test_apos_saida_externa_nao_reentra(self) -> None:
        """Após stop/target (registrar_saida_externa) não reentra no mesmo dia."""
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        # Simula trade aberto e fechado por stop/target (motor de execução).
        estado = registrar_saida_externa(estado)
        assert estado.trade_fechado_hoje is True

        # Nova barra às 14:30 com drift forte → ainda assim NADA (guard R2.6).
        acao, _ = decidir_acao(_barra(_ts(14, 30), o=100.0, c=130.0), estado, PARAMS)
        assert acao == AcaoVvg.NADA

    def test_novo_dia_libera_trade(self) -> None:
        """Mudança de dia reseta ``trade_fechado_hoje`` (mas zera vvg_positivo)."""
        estado = _estado_pronto(vvg=True, open_dia=100.0, trade_fechado=True)
        # Primeira barra do novo dia (RTH) — reset diário ocorre aqui.
        novo_dia = DATA + timedelta(days=1)
        _, estado = decidir_acao(
            _barra(_ts(9, 30, dia=novo_dia), o=100.0, c=100.0), estado, PARAMS
        )
        assert estado.trade_fechado_hoje is False
        # vvg_positivo é zerado no reset (será reescrito pelo classificador).
        assert estado.vvg_positivo is False


# ---------------------------------------------------------------------------
# Validação de ParametrosVvg (R10)
# ---------------------------------------------------------------------------


class TestParametrosValidacao:
    def test_defaults_validos(self) -> None:
        p = ParametrosVvg()
        assert p.multiplicador_volume == 1.5
        assert p.threshold_gap_pct == 0.0015
        assert p.n_dias_baseline == 10
        assert p.stop_pontos == 472.25
        assert p.target_pontos == 944.25

    @pytest.mark.parametrize("mult", [1.0, 0.5, 0.0, -1.0])
    def test_multiplicador_menor_igual_um_rejeitado(self, mult: float) -> None:
        with pytest.raises(ValueError, match="multiplicador_volume"):
            ParametrosVvg(multiplicador_volume=mult)

    @pytest.mark.parametrize("thr", [0.0, -0.001])
    def test_threshold_gap_nao_positivo_rejeitado(self, thr: float) -> None:
        with pytest.raises(ValueError, match="threshold_gap_pct"):
            ParametrosVvg(threshold_gap_pct=thr)

    @pytest.mark.parametrize("n", [1, 0, -3])
    def test_n_dias_baseline_menor_que_dois_rejeitado(self, n: int) -> None:
        with pytest.raises(ValueError, match="n_dias_baseline"):
            ParametrosVvg(n_dias_baseline=n)

    @pytest.mark.parametrize("stop", [0.0, -10.0])
    def test_stop_nao_positivo_rejeitado(self, stop: float) -> None:
        with pytest.raises(ValueError, match="stop_pontos"):
            ParametrosVvg(stop_pontos=stop)

    @pytest.mark.parametrize("target", [472.25, 400.0, 0.0])
    def test_target_menor_igual_stop_rejeitado(self, target: float) -> None:
        # stop default = 472.25; target <= stop deve falhar.
        with pytest.raises(ValueError, match="target_pontos"):
            ParametrosVvg(target_pontos=target)

    def test_horarios_incoerentes_rejeitados(self) -> None:
        # hora_entrada depois de hora_encerramento viola a cadeia cronológica.
        with pytest.raises(ValueError):
            ParametrosVvg(
                hora_entrada_est=time(15, 55),
                hora_encerramento_est=time(15, 50),
            )


# ---------------------------------------------------------------------------
# Property 12 — máximo 1 contrato por trade (R4.1)
# ---------------------------------------------------------------------------


class TestProperty12MaxContratosUm:
    """``MaxContratos = 1`` fixo permanente (R4.1).

    A função pura :func:`decidir_acao` não carrega o tamanho da posição
    (isso é responsabilidade do motor de execução do plugin / da subclasse
    C#). O que ``decidir_acao`` garante é o **despacho conceitual de uma
    única posição** por entrada: cada ação ``LONG``/``SHORT`` abre
    exatamente uma posição (``posicao_aberta=True``), e enquanto ela vive
    nenhuma nova entrada é emitida. A materialização ``contratos=1`` é
    verificada na camada plugin (``test_vvg_plugin.py``).
    """

    def test_entrada_abre_exatamente_uma_posicao(self) -> None:
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        acao, novo = decidir_acao(
            _barra(_ts(14, 30), o=100.0, c=110.0), estado, PARAMS
        )
        assert acao in (AcaoVvg.LONG, AcaoVvg.SHORT)
        # Uma única posição aberta — sem campo de "quantidade" > 1 no estado.
        assert novo.posicao_aberta is True
        assert novo.direcao_atual in ("LONG", "SHORT")
        assert novo.preco_entrada == 110.0

    def test_nao_acumula_segunda_posicao_no_mesmo_dia(self) -> None:
        """Com posição aberta, uma nova barra às 14:30 NÃO abre 2ª posição."""
        estado = _estado_pronto(
            vvg=True, posicao=True, direcao="SHORT", preco=110.0, open_dia=100.0
        )
        # Mesmo às 14:30, com posição aberta antes do encerramento → NADA.
        acao, novo = decidir_acao(
            _barra(_ts(14, 30), o=100.0, c=120.0), estado, PARAMS
        )
        assert acao == AcaoVvg.NADA
        assert novo.posicao_aberta is True
        # Direção/preço da posição original preservados (não acumula).
        assert novo.direcao_atual == "SHORT"
        assert novo.preco_entrada == 110.0


# ---------------------------------------------------------------------------
# Conversão de fuso UTC → Nova York (EDT/EST) — base da decisão
# ---------------------------------------------------------------------------


class TestConversaoFusoHorario:
    """Verifica que ``decidir_acao`` mapeia corretamente o ``timestamp`` UTC
    para o horário de Nova York, resolvendo DST (EDT/EST) pela ``zoneinfo``.

    O ponto crítico: a entrada ocorre às 14:30 horário de Nova York,
    qualquer que seja a época do ano. Construímos a MESMA barra (14:30 NY)
    em duas datas — uma em julho (EDT = UTC-4 → 18:30 UTC) e outra em
    janeiro (EST = UTC-5 → 19:30 UTC) — e exigimos a mesma decisão de
    entrada em ambas, provando que o offset não é hardcoded.
    """

    def test_1430_ny_em_julho_e_1830_utc(self) -> None:
        """Julho = horário de verão (EDT): 14:30 NY corresponde a 18:30 UTC."""
        dia_julho = date(2025, 7, 8)
        ts = _ts(14, 30, dia=dia_julho)
        # _ts já converte NY → UTC; confirmamos o offset esperado.
        assert ts.hour == 18 and ts.minute == 30
        assert ts.tzinfo == UTC

        estado = EstadoVvg(
            dia_corrente=dia_julho, open_dia_atual=100.0, vvg_positivo=True
        )
        acao, _ = decidir_acao(_barra(ts, o=100.0, c=110.0), estado, PARAMS)
        assert acao == AcaoVvg.SHORT  # drift +10 → SHORT

    def test_1430_ny_em_janeiro_e_1930_utc(self) -> None:
        """Janeiro = horário padrão (EST): 14:30 NY corresponde a 19:30 UTC."""
        dia_jan = date(2025, 1, 14)
        ts = _ts(14, 30, dia=dia_jan)
        assert ts.hour == 19 and ts.minute == 30
        assert ts.tzinfo == UTC

        estado = EstadoVvg(
            dia_corrente=dia_jan, open_dia_atual=100.0, vvg_positivo=True
        )
        acao, _ = decidir_acao(_barra(ts, o=100.0, c=110.0), estado, PARAMS)
        assert acao == AcaoVvg.SHORT  # mesma decisão, offset diferente

    def test_barra_construida_em_utc_puro_decide_no_horario_certo(self) -> None:
        """Constrói a barra diretamente em UTC (sem helper NY) e verifica que
        a decisão cai na barra certa.

        Em janeiro (EST), 14:30 NY = 19:30 UTC. Uma barra às 19:30 UTC deve
        disparar a entrada; uma barra às 18:30 UTC (= 13:30 NY) NÃO deve.
        """
        dia_jan = date(2025, 1, 14)

        # 19:30 UTC = 14:30 EST → entrada.
        ts_entrada = datetime(2025, 1, 14, 19, 30, tzinfo=UTC)
        estado = EstadoVvg(
            dia_corrente=dia_jan, open_dia_atual=100.0, vvg_positivo=True
        )
        acao, _ = decidir_acao(_barra(ts_entrada, o=100.0, c=95.0), estado, PARAMS)
        assert acao == AcaoVvg.LONG  # drift -5 → LONG

        # 18:30 UTC = 13:30 EST → fora do horário de entrada → NADA.
        ts_cedo = datetime(2025, 1, 14, 18, 30, tzinfo=UTC)
        estado2 = EstadoVvg(
            dia_corrente=dia_jan, open_dia_atual=100.0, vvg_positivo=True
        )
        acao2, _ = decidir_acao(_barra(ts_cedo, o=100.0, c=95.0), estado2, PARAMS)
        assert acao2 == AcaoVvg.NADA

    def test_timestamp_naive_rejeitado(self) -> None:
        """Barra com ``timestamp`` naive (sem tz) é rejeitada por
        ``decidir_acao`` (exige UTC tz-aware)."""
        ts_naive = datetime(2025, 7, 8, 18, 30)  # sem tzinfo
        estado = _estado_pronto(vvg=True, open_dia=100.0)
        with pytest.raises(ValueError, match="tz-aware"):
            decidir_acao(_barra(ts_naive, o=100.0, c=110.0), estado, PARAMS)
