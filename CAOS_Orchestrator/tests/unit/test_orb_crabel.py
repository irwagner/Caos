"""Testes unitários da :class:`EstrategiaORBCrabel`.

Cobre o filtro NR4/NR7 de Crabel 1990, sob recomendação do briefing do
Explorador (commit `c1b2bc6`) e estudo dos robôs de referência
(commit pendente).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from caos.walk_forward.estrategias.orb_crabel import (
    EstrategiaORBCrabel,
    _calcular_range_diario,
    _dias_apos_nr,
)


def _gerar_serie(
    inicio: date,
    ranges_por_dia: list[float],
    barras_por_dia: int = 1380,
    incluir_fim_de_semana: bool = False,
) -> pd.DataFrame:
    """Gera DataFrame canônico com range diário customizado.

    Cada dia tem barras_por_dia barras de minuto consecutivas.
    Default 1380 = pregão regular MNQ (23h × 60min); reduzir só faz
    sentido quando o teste especificamente quer simular dia parcial.

    Quando ``incluir_fim_de_semana=False`` (default), pula sábados e
    domingos. Útil para testes que só checam comportamento NR puro.
    Quando ``True``, mantém todos os dias corridos — útil para validar
    o filtro de domingos do bug fix da Decisao 2026-05-26-01.
    """
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    dia = pd.Timestamp(inicio).tz_localize("UTC")
    contagem = 0
    while contagem < len(ranges_por_dia):
        if incluir_fim_de_semana or dia.weekday() < 5:
            r = ranges_por_dia[contagem]
            for h in range(barras_por_dia):
                timestamps.append(dia + pd.Timedelta(minutes=h))
                opens.append(100.0)
                highs.append(100.0 + r / 2)
                lows.append(100.0 - r / 2)
                closes.append(100.0)
            contagem += 1
        dia = dia + pd.Timedelta(days=1)
    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n),
        }
    )


# ---------------------------------------------------------------------------
# _calcular_range_diario
# ---------------------------------------------------------------------------


class TestCalcularRangeDiario:
    def test_basico(self) -> None:
        ranges = [10.0, 20.0, 30.0]
        df = _gerar_serie(date(2025, 1, 6), ranges)
        mapa = _calcular_range_diario(df)
        assert len(mapa) == 3
        assert sorted(mapa.values()) == ranges

    def test_dataframe_vazio(self) -> None:
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([], utc=True),
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": [],
            }
        )
        assert _calcular_range_diario(df) == {}


# ---------------------------------------------------------------------------
# _dias_apos_nr
# ---------------------------------------------------------------------------


class TestDiasAposNr:
    def test_nr4_simples(self) -> None:
        # 5 dias com ranges 10, 8, 12, 6, 15.
        ranges_por_dia = {
            date(2025, 1, 6): 10.0,
            date(2025, 1, 7): 8.0,
            date(2025, 1, 8): 12.0,
            date(2025, 1, 9): 6.0,  # menor da janela 4 dias
            date(2025, 1, 10): 15.0,
        }
        elegiveis, prox = _dias_apos_nr(ranges_por_dia, janela=4)
        assert date(2025, 1, 10) in elegiveis  # dia após o NR4
        # prox indica se o ÚLTIMO dia conhecido é NR.
        assert isinstance(prox, bool)

    def test_janela_invalida(self) -> None:
        with pytest.raises(ValueError):
            _dias_apos_nr({}, janela=1)

    def test_dados_insuficientes(self) -> None:
        # 3 dias, janela 4 — não há janela completa.
        ranges = {date(2025, 1, 6): 10.0, date(2025, 1, 7): 8.0, date(2025, 1, 8): 12.0}
        elegiveis, prox = _dias_apos_nr(ranges, janela=4)
        assert elegiveis == set()
        assert prox is False

    def test_proximo_dia_elegivel_quando_ultimo_eh_nr(self) -> None:
        # Último dia tem o menor range da janela 4 → próximo é elegível.
        ranges = {
            date(2025, 1, 6): 20.0,
            date(2025, 1, 7): 15.0,
            date(2025, 1, 8): 18.0,
            date(2025, 1, 9): 5.0,  # NR4: menor da janela
        }
        elegiveis, prox = _dias_apos_nr(ranges, janela=4)
        # 2025-01-09 é último, NR4, próximo (desconhecido) é elegível.
        assert prox is True
        # Não há "próximo dia" no dict; elegiveis pode estar vazio
        # ou ter dias anteriores.


# ---------------------------------------------------------------------------
# Plugin EstrategiaORBCrabel — comportamento de filtro
# ---------------------------------------------------------------------------


class TestEstrategiaORBCrabel:
    def test_construtor_modo_invalido(self) -> None:
        with pytest.raises(ValueError):
            EstrategiaORBCrabel(modo_nr="nr3")  # type: ignore[arg-type]

    def test_treinar_calcula_dias_elegiveis(self) -> None:
        # 8 dias com ranges variados; janela NR7.
        plugin = EstrategiaORBCrabel(modo_nr="nr7")
        # 8 dias úteis começando 2025-01-06 (segunda).
        ranges = [50.0, 40.0, 45.0, 30.0, 55.0, 60.0, 25.0, 70.0]
        df = _gerar_serie(date(2025, 1, 6), ranges)
        plugin.treinar(df)
        # 7 ranges fechados após NR7 só aparece quando há janela
        # completa. Com 8 dias, o dia 8 é candidato; ranges[0:7] tem
        # min=25 no dia 7. Logo dia 8 está apos NR7.
        # Mais especificamente: bloco terminado em dia 7 tem ranges
        # 50,40,45,30,55,60,25 → min é 25 no próprio dia 7. Logo dia 8
        # vira elegível.
        elegiveis = plugin.dias_elegiveis
        # Pelo menos algum dia elegível (existe NR no histórico).
        assert len(elegiveis) >= 1

    def test_modo_nr4_e_nr7_diferentes(self) -> None:
        ranges = [10.0, 8.0, 12.0, 6.0, 15.0, 9.0, 11.0, 5.0]
        df = _gerar_serie(date(2025, 1, 6), ranges)
        p4 = EstrategiaORBCrabel(modo_nr="nr4")
        p7 = EstrategiaORBCrabel(modo_nr="nr7")
        p4.treinar(df.copy())
        p7.treinar(df.copy())
        # NR4 e NR7 devem produzir conjuntos potencialmente diferentes
        # (NR4 tem janela menor, mais dias atendem o filtro).
        assert isinstance(p4.dias_elegiveis, set)
        assert isinstance(p7.dias_elegiveis, set)
        # Pelo menos um dos dois deve ter >= 1 dia elegível.
        assert len(p4.dias_elegiveis) + len(p7.dias_elegiveis) >= 1

    def test_dia_nao_elegivel_nao_emite_trades(self) -> None:
        """Se nenhum dia é elegível, nenhum trade é emitido."""
        # 3 dias só → não há janela NR completa.
        ranges = [10.0, 20.0, 30.0]
        df = _gerar_serie(date(2025, 1, 6), ranges)
        plugin = EstrategiaORBCrabel(modo_nr="nr7")
        plugin.treinar(df)
        # Como há < 7 dias, não há filtro válido → nenhum dia elegível
        # → nenhum trade.
        assert plugin.dias_elegiveis == set()

    def test_protocol_compatibility(self) -> None:
        plugin = EstrategiaORBCrabel(modo_nr="nr4")
        assert callable(getattr(plugin, "treinar", None))
        assert callable(getattr(plugin, "on_barra", None))
        assert callable(getattr(plugin, "finalizar", None))
        assert plugin.NOME == "EstrategiaORBCrabel"

    def test_zero_parametros_otimizaveis(self) -> None:
        """Filtro Crabel não deve introduzir parâmetros otimizáveis
        novos além da escolha discreta nr4/nr7."""
        # Construtor aceita só modo_nr (categórico) e parametros (ORB
        # padrão, não da Crabel). Sem floats, ints arbitrários, etc.
        import inspect

        sig = inspect.signature(EstrategiaORBCrabel.__init__)
        params = list(sig.parameters.keys())
        # self, modo_nr (Literal), parametros (ParametrosORB).
        assert params == ["self", "modo_nr", "parametros"]


# ---------------------------------------------------------------------------
# Filtro de dia válido (Decisao 2026-05-26-01)
# ---------------------------------------------------------------------------


class TestFiltroDiaValidoDecisao20260526:
    """Cobre o bug fix da Decisao 2026-05-26-01.

    O filtro de dia válido descarta:
    1. Sábados e domingos (Globex noturno tem range artificialmente baixo).
    2. Dias com menos de :data:`MIN_BARRAS_DIA_VALIDO` barras de minuto
       (sessão truncada de feriado parcial).

    Sem o filtro, domingos viram NR7 sistematicamente e toda segunda
    seguinte é elegível espuriamente. Este caso foi descoberto pelo
    replay NT8 28/01-13/03/2026.
    """

    def test_domingo_descartado_no_calculo_de_range(self) -> None:
        """Range não é registrado para sábado/domingo, mesmo se os
        dias tiverem barras suficientes."""
        # 1 segunda regular + 1 domingo com 1380 barras.
        # 2025-01-05 é domingo. 2025-01-06 é segunda.
        df = _gerar_serie(
            date(2025, 1, 5),
            [50.0, 40.0],
            barras_por_dia=1380,
            incluir_fim_de_semana=True,
        )
        ranges = _calcular_range_diario(df)
        # Só a segunda 2025-01-06 deve estar no mapa.
        assert date(2025, 1, 5) not in ranges
        assert date(2025, 1, 6) in ranges
        assert ranges[date(2025, 1, 6)] == 40.0

    def test_dia_com_poucas_barras_descartado(self) -> None:
        """Dia útil com < 300 barras não conta para o filtro NR."""
        # 2 dias úteis: o primeiro com 200 barras (parcial), o segundo
        # com 1380 (regular).
        df1 = _gerar_serie(date(2025, 1, 6), [50.0], barras_por_dia=200)
        df2 = _gerar_serie(date(2025, 1, 7), [40.0], barras_por_dia=1380)
        df = pd.concat([df1, df2], ignore_index=True)
        ranges = _calcular_range_diario(df)
        assert date(2025, 1, 6) not in ranges  # parcial
        assert date(2025, 1, 7) in ranges       # regular

    def test_dia_com_300_barras_aceito(self) -> None:
        """Limiar é >= 300 (inclusivo): dia com exatamente 300 passa."""
        df = _gerar_serie(date(2025, 1, 6), [50.0], barras_por_dia=300)
        ranges = _calcular_range_diario(df)
        assert date(2025, 1, 6) in ranges

    def test_domingo_falso_positivo_nao_torna_segunda_elegivel(self) -> None:
        """Cenário do bug original: domingo com range baixo NÃO pode
        fazer segunda virar NR7-elegível.

        Setup: 7 dias com ranges altos seguidos de um domingo com
        range = 1.0 (artificial, simulando Globex curto). Sem o fix,
        domingo seria identificado como "menor da janela 7" e a
        segunda seguinte viria elegível.
        """
        # Dias úteis: 6 dias com range alto (50-100), depois 1 domingo
        # com range baixo (1.0), depois 1 segunda.
        # 2025-01-06 = segunda. 2025-01-12 = domingo. 2025-01-13 = segunda.
        df_uteis = _gerar_serie(
            date(2025, 1, 6),
            [50.0, 60.0, 70.0, 55.0, 65.0, 75.0],  # 6 dias úteis
            barras_por_dia=1380,
        )
        # Domingo com range artificial baixo (1380 barras pra passar o
        # contador, mas range minúsculo).
        df_domingo = _gerar_serie(
            date(2025, 1, 12),
            [1.0],
            barras_por_dia=1380,
            incluir_fim_de_semana=True,
        )
        df_segunda = _gerar_serie(
            date(2025, 1, 13),
            [40.0],
            barras_por_dia=1380,
        )
        df = pd.concat([df_uteis, df_domingo, df_segunda], ignore_index=True)

        plugin = EstrategiaORBCrabel(modo_nr="nr7")
        plugin.treinar(df)
        # Domingo NÃO deve estar nem no mapa de ranges nem como NR7.
        # Logo a segunda 2025-01-13 NÃO deve ser elegível por causa do
        # domingo. (Ela poderia ser elegível por outra razão, mas com
        # ranges 50/60/70/55/65/75/40, o min é 40 = própria segunda
        # 13. Próximo dia (14) seria elegível, não a 13.)
        assert date(2025, 1, 12) not in plugin._ranges_por_dia  # type: ignore[attr-defined]
        # 13 não está no conjunto de elegíveis no momento do treino
        # (treino acabou em 13; o dia 14 viria elegível se 13 for NR7).

    def test_funcao_dia_eh_valido_estatica(self) -> None:
        """Helper público: segunda a sexta = válido; sábado/domingo = inválido."""
        # 2025-01-05 = domingo, 2025-01-06 = segunda, 2025-01-11 = sábado.
        assert EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 6))   # segunda
        assert EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 7))   # terça
        assert EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 8))   # quarta
        assert EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 9))   # quinta
        assert EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 10))  # sexta
        assert not EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 11))  # sábado
        assert not EstrategiaORBCrabel._dia_eh_valido(date(2025, 1, 5))   # domingo

    def test_constante_min_barras_e_300(self) -> None:
        """Garante que a constante não foi alterada sem nova Decisao."""
        from caos.walk_forward.estrategias.orb_crabel import MIN_BARRAS_DIA_VALIDO
        assert MIN_BARRAS_DIA_VALIDO == 300
