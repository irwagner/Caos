"""Testes unitários do ``JanelaGenerator`` (Spec 2 — Task 3).

Cobre:

- Dados insuficientes ⇒ 0 janelas (R3.2).
- Exatamente 1 janela quando ``N == treino + teste``.
- N janelas com passo default (== ``tamanho_teste``).
- N janelas com passo customizado (overlap em Treino permitido,
  overlap em Teste proibido — R3.1).
- Determinismo: mesma entrada gera saída byte-a-byte idêntica.
- Índices 0..N-1 contínuos e estritamente crescentes.
- Aceita DataFrame com schema canônico, DatetimeIndex e iterável
  de timestamps.
- Filtra finais de semana (sábado/domingo).
- ``passo < tamanho_teste`` é rejeitado com :class:`ValueError`
  (R3.1 — sobreposição de Teste é proibida).

Cobre R3 do ``requirements.md`` do Spec 2.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from caos.walk_forward import (
    ConfiguracaoWalkForward,
    JanelaGenerator,
    JanelaWF,
    gerar_janelas,
)

UTC = timezone.utc
HASH_FAKE = "f" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(
    *,
    treino: int = 60,
    teste: int = 10,
    passo: int | None = None,
) -> ConfiguracaoWalkForward:
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=treino,
        tamanho_teste_dias_uteis=teste,
        passo_dias_uteis=passo,
        granularidade="1m",
    )


def _bdays(quantidade: int, inicio: str = "2024-01-02") -> pd.DatetimeIndex:
    """Gera ``quantidade`` business days UTC consecutivos."""
    return pd.bdate_range(inicio, periods=quantidade, tz="UTC")


def _dataframe_canonico(timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    """Constrói DataFrame com schema do Skill_Data_Reader."""
    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": [1.0] * n,
        }
    )


# ===========================================================================
# Casos básicos: 0, 1, N janelas
# ===========================================================================


class TestQuantidadeDeJanelas:
    """Cobre R3.2 — número de janelas geradas."""

    def test_dados_insuficientes_retorna_zero_janelas(self) -> None:
        # Total disponível < treino + teste ⇒ não cabe nem 1 janela.
        idx = _bdays(60 + 10 - 1)  # 69 dias úteis
        janelas = JanelaGenerator.gerar(idx, _config(treino=60, teste=10), HASH_FAKE)
        assert janelas == []

    def test_exatamente_treino_mais_teste_gera_1_janela(self) -> None:
        # Total == treino + teste ⇒ exatamente 1 janela.
        idx = _bdays(60 + 10)  # 70 dias úteis
        janelas = JanelaGenerator.gerar(idx, _config(treino=60, teste=10), HASH_FAKE)
        assert len(janelas) == 1
        assert janelas[0].indice == 0
        # Treino cobre os primeiros 60 dias; Teste cobre os 10 seguintes.
        # treino_fim == teste_inicio (R3.1, fronteira contígua).
        assert janelas[0].treino_inicio == idx[0].to_pydatetime()
        assert janelas[0].treino_fim == idx[60].to_pydatetime()
        assert janelas[0].teste_inicio == idx[60].to_pydatetime()

    def test_n_janelas_com_passo_default_igual_teste(self) -> None:
        # N=100, treino=60, teste=10, passo default=10
        # Janelas: floor((100 - 60 - 10)/10) + 1 = 4
        idx = _bdays(100)
        janelas = JanelaGenerator.gerar(idx, _config(treino=60, teste=10), HASH_FAKE)
        assert len(janelas) == 4
        # Os Testes são contíguos e disjuntos: [60..70), [70..80), [80..90), [90..100)
        assert janelas[0].teste_inicio == idx[60].to_pydatetime()
        assert janelas[1].teste_inicio == idx[70].to_pydatetime()
        assert janelas[2].teste_inicio == idx[80].to_pydatetime()
        assert janelas[3].teste_inicio == idx[90].to_pydatetime()

    def test_n_janelas_com_passo_customizado_maior_que_teste(self) -> None:
        # passo=20 > teste=10 ⇒ Testes têm "gap" entre si (folga em Treino).
        # N=200, treino=60, teste=10, passo=20:
        # Janelas: floor((200 - 60 - 10)/20) + 1 = 7
        idx = _bdays(200)
        janelas = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10, passo=20), HASH_FAKE
        )
        assert len(janelas) == 7
        # Janela k começa em índice k*20.
        for k, janela in enumerate(janelas):
            assert janela.treino_inicio == idx[k * 20].to_pydatetime()
            assert janela.teste_inicio == idx[k * 20 + 60].to_pydatetime()

    def test_n_janelas_com_passo_customizado_overlap_em_treino_permitido(
        self,
    ) -> None:
        # passo=10 == teste=10 mas treino=60 > passo ⇒ Treinos consecutivos
        # têm 50 dias em comum. R3.1 só proíbe overlap em Teste.
        idx = _bdays(100)
        janelas = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10, passo=10), HASH_FAKE
        )
        # Treinos da janela 0 e 1 se sobrepõem em [10..60) (50 dias úteis).
        assert janelas[0].treino_inicio < janelas[1].treino_inicio
        assert janelas[1].treino_inicio < janelas[0].treino_fim
        # Mas os Testes são disjuntos.
        assert janelas[0].teste_fim <= janelas[1].teste_inicio

    def test_dados_exatamente_um_a_menos_que_minimo(self) -> None:
        # Confirma fronteira: N = treino + teste - 1 ⇒ 0 janelas.
        idx = _bdays(60 + 10 - 1)
        assert JanelaGenerator.gerar(idx, _config(treino=60, teste=10), HASH_FAKE) == []


# ===========================================================================
# R3.1 — não-sobreposição entre Testes
# ===========================================================================


class TestNaoSobreposicaoTeste:
    """Cobre R3.1 — janelas de Teste não-sobrepostas."""

    def test_passo_menor_que_teste_e_rejeitado(self) -> None:
        # passo=5 < teste=10 ⇒ Testes se sobrepõem (proibido por R3.1).
        idx = _bdays(100)
        with pytest.raises(ValueError, match="passo_dias_uteis"):
            JanelaGenerator.gerar(
                idx, _config(treino=60, teste=10, passo=5), HASH_FAKE
            )

    @pytest.mark.parametrize("passo", [10, 11, 20, 50])
    def test_testes_sao_disjuntos_para_passo_valido(self, passo: int) -> None:
        idx = _bdays(300)
        janelas = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10, passo=passo), HASH_FAKE
        )
        assert len(janelas) >= 2
        for atual, prox in zip(janelas, janelas[1:]):
            # Property 15: Testes não se sobrepõem.
            assert atual.teste_fim <= prox.teste_inicio


# ===========================================================================
# Estrutura das JanelaWF retornadas
# ===========================================================================


class TestEstruturaDaJanela:
    """Cobre R3.1, R3.3 — fronteiras e indexação."""

    def test_treino_fim_igual_teste_inicio(self) -> None:
        idx = _bdays(100)
        janelas = JanelaGenerator.gerar(idx, _config(treino=60, teste=10), HASH_FAKE)
        for janela in janelas:
            assert janela.treino_fim == janela.teste_inicio

    def test_indices_zero_a_n_menos_um_continuos(self) -> None:
        idx = _bdays(200)
        janelas = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10, passo=10), HASH_FAKE
        )
        assert [j.indice for j in janelas] == list(range(len(janelas)))

    def test_todas_as_janelas_sao_modelos_pydantic(self) -> None:
        idx = _bdays(100)
        janelas = JanelaGenerator.gerar(idx, _config(treino=60, teste=10), HASH_FAKE)
        for janela in janelas:
            assert isinstance(janela, JanelaWF)

    def test_hash_dados_propagado_para_todas_as_janelas(self) -> None:
        idx = _bdays(100)
        hash_esperado = "0" * 63 + "1"
        janelas = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10), hash_esperado
        )
        for janela in janelas:
            assert janela.hash_dados == hash_esperado

    def test_ordem_cronologica_estritamente_crescente(self) -> None:
        idx = _bdays(200)
        janelas = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10, passo=15), HASH_FAKE
        )
        for atual, prox in zip(janelas, janelas[1:]):
            assert atual.treino_inicio < prox.treino_inicio
            assert atual.teste_inicio < prox.teste_inicio


# ===========================================================================
# Determinismo (R3.1, R7.1 — mesma entrada → mesma saída)
# ===========================================================================


class TestDeterminismo:
    """Mesma entrada deve produzir lista byte-a-byte idêntica."""

    def test_duas_invocacoes_geram_listas_iguais(self) -> None:
        idx = _bdays(150)
        cfg = _config(treino=60, teste=10, passo=12)
        a = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        b = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        assert a == b

    def test_serializacao_json_canonica_e_identica(self) -> None:
        idx = _bdays(150)
        cfg = _config(treino=60, teste=10, passo=12)
        a = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        b = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        json_a = [j.model_dump_json() for j in a]
        json_b = [j.model_dump_json() for j in b]
        assert json_a == json_b

    def test_funcao_livre_devolve_resultado_identico_ao_metodo_estatico(
        self,
    ) -> None:
        idx = _bdays(150)
        cfg = _config(treino=60, teste=10, passo=12)
        a = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        b = gerar_janelas(idx, cfg, HASH_FAKE)
        assert a == b


# ===========================================================================
# Aceitação de múltiplos formatos de entrada
# ===========================================================================


class TestEntradasAceitas:
    """O gerador aceita DataFrame, DatetimeIndex e Iterable[Timestamp]."""

    def test_dataframe_com_schema_canonico(self) -> None:
        idx = _bdays(100)
        df = _dataframe_canonico(idx)
        cfg = _config(treino=60, teste=10)
        janelas_idx = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        janelas_df = JanelaGenerator.gerar(df, cfg, HASH_FAKE)
        assert janelas_idx == janelas_df

    def test_iteravel_de_timestamps(self) -> None:
        idx = _bdays(100)
        cfg = _config(treino=60, teste=10)
        janelas_idx = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        janelas_iter = JanelaGenerator.gerar(list(idx), cfg, HASH_FAKE)
        assert janelas_idx == janelas_iter

    def test_dataframe_sem_coluna_timestamp_e_rejeitado(self) -> None:
        df = pd.DataFrame({"foo": [1, 2, 3]})
        with pytest.raises(ValueError, match="timestamp"):
            JanelaGenerator.gerar(df, _config(), HASH_FAKE)

    def test_timestamps_naive_rejeitados(self) -> None:
        # DatetimeIndex sem tz ⇒ erro descritivo.
        idx = pd.date_range("2024-01-02", periods=100, freq="B")
        with pytest.raises(ValueError, match="tzinfo"):
            JanelaGenerator.gerar(idx, _config(), HASH_FAKE)

    def test_filtro_de_finais_de_semana(self) -> None:
        # Inclui sábado e domingo no índice; o gerador deve descartá-los
        # ao calcular dias úteis.
        idx_completo = pd.date_range(
            "2024-01-01", periods=100, freq="D", tz="UTC"
        )
        idx_apenas_uteis = pd.bdate_range(
            "2024-01-01", periods=100, freq="B", tz="UTC"
        )
        # Mesmo número de dias úteis embutidos? Não necessariamente — o
        # importante é que o gerador colapse para o conjunto correto.
        cfg = _config(treino=60, teste=10)
        janelas_completo = JanelaGenerator.gerar(idx_completo, cfg, HASH_FAKE)
        # Quantidade de business days em idx_completo é diferente
        # (apenas seg-sex). Confirmamos que o gerador filtrou.
        bdays_no_completo = sum(1 for ts in idx_completo if ts.weekday() < 5)
        if bdays_no_completo >= 70:
            assert len(janelas_completo) >= 1
        # E que quaisquer fronteiras devolvidas só caem em dias úteis.
        for janela in janelas_completo:
            assert janela.treino_inicio.weekday() < 5
            assert janela.treino_fim.weekday() < 5
            assert janela.teste_inicio.weekday() < 5

    def test_iteravel_com_datetimes_python_funciona(self) -> None:
        # ``datetime`` puro com tzinfo UTC, em vez de pd.Timestamp.
        base = datetime(2024, 1, 2, tzinfo=UTC)
        # 100 datas — caller já filtra finais de semana (mais simples no teste).
        datas: list[datetime] = []
        atual = base
        while len(datas) < 100:
            if atual.weekday() < 5:
                datas.append(atual)
            atual = atual + timedelta(days=1)

        janelas = JanelaGenerator.gerar(
            datas, _config(treino=60, teste=10), HASH_FAKE
        )
        # bdate_range produz mesma sequência: serve como ground truth.
        idx = pd.DatetimeIndex(datas)
        janelas_idx = JanelaGenerator.gerar(
            idx, _config(treino=60, teste=10), HASH_FAKE
        )
        assert janelas == janelas_idx


# ===========================================================================
# Casos de borda
# ===========================================================================


class TestCasosDeBorda:
    """Edge cases miúdos que merecem cobertura explícita."""

    def test_dados_vazios_retorna_zero_janelas(self) -> None:
        idx = pd.DatetimeIndex([], tz="UTC")
        janelas = JanelaGenerator.gerar(idx, _config(), HASH_FAKE)
        assert janelas == []

    def test_passo_default_aplicado_pelo_validator(self) -> None:
        # Quando ``passo_dias_uteis`` é omitido, o validator do modelo
        # preenche com ``tamanho_teste_dias_uteis`` — o gerador deve
        # honrar esse valor.
        cfg = ConfiguracaoWalkForward(
            tamanho_treino_dias_uteis=60,
            tamanho_teste_dias_uteis=10,
            granularidade="1m",
        )
        assert cfg.passo_dias_uteis == 10
        idx = _bdays(100)
        janelas = JanelaGenerator.gerar(idx, cfg, HASH_FAKE)
        # floor((100 - 60 - 10)/10) + 1 = 4
        assert len(janelas) == 4

    def test_timestamps_nao_utc_sao_convertidos(self) -> None:
        # Se a entrada vier em outro fuso (ex: America/Sao_Paulo), o
        # gerador converte para UTC e prossegue.
        idx_local = pd.bdate_range(
            "2024-01-02", periods=100, tz="America/Sao_Paulo"
        )
        idx_utc = idx_local.tz_convert("UTC")
        cfg = _config(treino=60, teste=10)
        janelas_local = JanelaGenerator.gerar(idx_local, cfg, HASH_FAKE)
        janelas_utc = JanelaGenerator.gerar(idx_utc, cfg, HASH_FAKE)
        # A normalização ``midnight UTC`` pode diferir entre os dois
        # casos (porque o midnight São Paulo != midnight UTC do mesmo
        # dia local), mas a quantidade e a contiguidade Treino→Teste
        # devem ser preservadas em ambos.
        assert len(janelas_local) == len(janelas_utc)
        for j in janelas_local + janelas_utc:
            assert j.treino_fim == j.teste_inicio

    def test_timestamps_duplicados_sao_deduplicados(self) -> None:
        # Múltiplas barras intraday no mesmo dia útil ⇒ o gerador deve
        # tratá-las como 1 dia. Aqui o caller passa um índice com 4
        # barras por dia em 100 dias úteis = 400 timestamps, mas só
        # contam 100 dias.
        dias = _bdays(100)
        intraday = pd.DatetimeIndex(
            [d + pd.Timedelta(hours=h) for d in dias for h in (9, 10, 11, 12)]
        )
        cfg = _config(treino=60, teste=10)
        janelas = JanelaGenerator.gerar(intraday, cfg, HASH_FAKE)
        # Mesmo resultado se passássemos só os dias.
        janelas_dias = JanelaGenerator.gerar(dias, cfg, HASH_FAKE)
        assert janelas == janelas_dias
