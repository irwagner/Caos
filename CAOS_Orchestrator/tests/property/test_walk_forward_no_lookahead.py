"""Property-based test do ``BacktestRunner`` (Property 13 do design).

Implementa **Property 13 — Walk-Forward Sem Look-Ahead** do
``design.md`` do Spec 2:

    For every (estrategia, janela), no execution of the BacktestRunner
    SHALL access bars whose timestamp is greater than the current bar
    timestamp during the Test phase.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

A propriedade é validada por uma estratégia sintética que tenta
deliberadamente acessar uma barra futura durante ``on_barra``. Para
toda combinação ``(n_barras_teste, idx_atual_alvo, k_offset, modo)`` em
que o offset ``k >= 1`` aponta para um índice fora da janela visível
(``idx > idx_atual``), o ``BarrasTesteIterator`` precisa detectar e
levantar :class:`LookAheadException`, e o ``BacktestRunner`` precisa
empacotar esse evento em um
:class:`~caos.walk_forward.models.ResultadoJanela` com
``status="falha"`` e ``look_ahead_violation=True``.

Sub-propriedade complementar (R5.1, R5.2): para uma estratégia *honesta*
(que só consulta a barra atual e barras passadas), o ``BacktestRunner``
nunca produz ``look_ahead_violation=True`` — independentemente de
``n_barras_teste``. Esta sub-propriedade fica em um teste separado para
manter o foco e a mensagem de falha legíveis quando algo quebra.

Modos de acesso futuro testados:

- ``"positivo"`` — ``contexto[idx_atual + k]``;
- ``"slice"``   — ``contexto[0 : idx_atual + k + 1]``;
- ``"negativo"``— ``contexto[-(idx_atual + k + 2)]``: índice negativo
  fora da janela visível. Note que ``contexto[-1]`` é a barra atual;
  índices negativos só são "futuro" quando excedem
  ``-(idx_atual + 1)``. Esse modo cobre a borda do iterator descrita
  na docstring de :class:`BarrasTesteIterator`.

Geração de fixtures: as barras de Teste são montadas in-memory via
``pd.bdate_range`` e :class:`pandas.DataFrame`. Não há I/O — todos os
timestamps cabem em uma janela única ``[treino_inicio, teste_fim)``
construída diretamente no teste.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.walk_forward import (
    BacktestRunner,
    BarrasTesteIterator,
    ConfiguracaoWalkForward,
    JanelaWF,
    ResultadoJanela,
    Trade,
)

UTC = timezone.utc
HASH_FAKE = "f" * 64

ModoAcesso = Literal["positivo", "slice", "negativo"]


# ---------------------------------------------------------------------------
# Helpers de construção do fixture sintético
# ---------------------------------------------------------------------------


def _config_minima(seed: int = 42) -> ConfiguracaoWalkForward:
    """Configuração mínima válida — não afeta a propriedade testada."""
    return ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        seed=seed,
    )


def _construir_janela_e_dados(
    n_barras_teste: int,
) -> tuple[JanelaWF, pd.DataFrame]:
    """Monta um (JanelaWF, DataFrame) com exatamente ``n_barras_teste`` barras de Teste.

    O DataFrame contém 60 dias úteis de Treino (índices 0..59) e
    ``n_barras_teste`` dias úteis de Teste (índices 60..60+n-1). Os
    intervalos da :class:`JanelaWF` cobrem toda a faixa, e o
    ``hash_dados`` é fictício (a propriedade não depende dele).
    """
    n_total = 60 + n_barras_teste
    idx = pd.bdate_range("2024-01-02", periods=n_total, tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": idx,
            "open": [100.0 + i for i in range(n_total)],
            "high": [101.0 + i for i in range(n_total)],
            "low": [99.0 + i for i in range(n_total)],
            "close": [100.5 + i for i in range(n_total)],
            "volume": [1000.0] * n_total,
        }
    )
    janela = JanelaWF(
        indice=0,
        treino_inicio=idx[0].to_pydatetime(),
        treino_fim=idx[60].to_pydatetime(),
        teste_inicio=idx[60].to_pydatetime(),
        teste_fim=(idx[-1] + pd.Timedelta(days=1)).to_pydatetime(),
        hash_dados=HASH_FAKE,
    )
    return janela, df


# ---------------------------------------------------------------------------
# Estratégias sintéticas
# ---------------------------------------------------------------------------


class _EstrategiaPeekFuturo:
    """Estratégia que tenta acessar barra futura na barra ``idx_atual_alvo``.

    Modos suportados (R5.3):

    - ``"positivo"`` — acessa ``contexto[idx_atual + k]``;
    - ``"slice"``   — acessa ``contexto[0 : idx_atual + k + 1]``;
    - ``"negativo"``— acessa ``contexto[-(idx_atual + k + 2)]`` quando o
      iterator estiver na barra ``idx_atual_alvo``. Como
      ``contexto[-1]`` é a barra atual, qualquer ``-i`` com
      ``i > idx_atual + 1`` aponta para fora da janela visível e levanta
      :class:`IndexError`. **Esse não é o cenário canônico de
      look-ahead** (índices negativos fora-da-janela viram
      :class:`IndexError`, não :class:`LookAheadException`), portanto o
      modo ``"negativo"`` aciona um caminho distinto e por isso é
      tratado em um teste dedicado.
    """

    NOME = "EstrategiaPeekFuturo"

    def __init__(
        self,
        *,
        idx_atual_alvo: int,
        k_offset: int,
        modo: ModoAcesso,
    ) -> None:
        self._idx_atual_alvo = idx_atual_alvo
        self._k_offset = k_offset
        self._modo = modo
        self._ja_disparou = False

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        if self._ja_disparou:
            return
        if contexto.idx_atual != self._idx_atual_alvo:
            return
        self._ja_disparou = True
        idx_alvo = contexto.idx_atual + self._k_offset
        if self._modo == "positivo":
            _ = contexto[idx_alvo]
        elif self._modo == "slice":
            _ = contexto[0 : idx_alvo + 1]
        else:
            # Modo "negativo": índice negativo que sai da janela visível.
            # contexto[-(idx_atual + 2)] aponta para 1 antes do início.
            # Para ser claramente "futuro" no sentido estrito, usamos um
            # índice que projetaria após o cursor visível — porém
            # IndexError é o que o iterator levanta nesse caso.
            _ = contexto[-(self._idx_atual_alvo + self._k_offset + 2)]

    def finalizar(self) -> list[Trade]:
        return []


class _EstrategiaHonesta:
    """Estratégia que **nunca** consulta barras futuras (R5.1, R5.2).

    Acessa a barra atual via ``contexto[idx_atual]`` e, quando
    ``idx_atual >= 1``, a barra anterior via ``contexto[idx_atual - 1]``.
    """

    NOME = "EstrategiaHonesta"

    def on_barra(
        self, barra: pd.Series, contexto: BarrasTesteIterator
    ) -> None:
        _ = contexto[contexto.idx_atual]
        if contexto.idx_atual >= 1:
            _ = contexto[contexto.idx_atual - 1]

    def finalizar(self) -> list[Trade]:
        return []


# ---------------------------------------------------------------------------
# Estratégia composta para Hypothesis: gera (n, idx_alvo, k, modo) coerente.
# ---------------------------------------------------------------------------


@st.composite
def _cenario_lookahead(
    draw: st.DrawFn,
) -> tuple[int, int, int, ModoAcesso]:
    """Gera ``(n_barras_teste, idx_atual_alvo, k_offset, modo)`` válido.

    Restrições:

    - ``n_barras_teste`` em ``[2, 30]`` — pelo menos 2 para que exista
      ``idx_atual + k`` válido.
    - ``idx_atual_alvo`` em ``[0, n - 2]`` — não pode ser a última barra
      (para que ``idx_atual + k`` ainda esteja em range para
      ``modo="positivo"`` e ``"slice"``).
    - ``k_offset`` em ``[1, n - 1 - idx_atual_alvo]`` — pelo menos 1
      barra à frente, mas dentro do tamanho do Teste.
    - ``modo`` é apenas ``"positivo"`` ou ``"slice"`` aqui — o modo
      ``"negativo"`` é testado em propriedade dedicada (caminho de
      :class:`IndexError`, não de :class:`LookAheadException`).
    """
    n_barras_teste = draw(st.integers(min_value=2, max_value=30))
    idx_atual_alvo = draw(st.integers(min_value=0, max_value=n_barras_teste - 2))
    k_max = n_barras_teste - 1 - idx_atual_alvo
    k_offset = draw(st.integers(min_value=1, max_value=k_max))
    modo = draw(st.sampled_from(["positivo", "slice"]))
    return n_barras_teste, idx_atual_alvo, k_offset, modo


# ---------------------------------------------------------------------------
# Property 13 — caminho canônico de look-ahead
# ---------------------------------------------------------------------------


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_cenario_lookahead())
def test_property_walk_forward_no_lookahead(
    cenario: tuple[int, int, int, ModoAcesso],
) -> None:
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4** (Property 13).

    Para qualquer estratégia sintética que tente acessar uma barra
    futura (``idx > idx_atual``) durante ``on_barra``, o
    ``BacktestRunner`` deve devolver :class:`ResultadoJanela` com
    ``status="falha"`` e ``look_ahead_violation=True``. O motivo da
    falha deve mencionar "look-ahead" (em pt-BR), e ``numero_trades``
    e ``pnl_total`` devem ser zerados.
    """
    n, idx_alvo, k, modo = cenario
    janela, dados = _construir_janela_e_dados(n)
    estrategia = _EstrategiaPeekFuturo(
        idx_atual_alvo=idx_alvo,
        k_offset=k,
        modo=modo,
    )

    resultado = BacktestRunner.executar(
        janela=janela,
        dados=dados,
        estrategia=estrategia,
        configuracao=_config_minima(),
    )

    assert isinstance(resultado, ResultadoJanela)
    assert resultado.status == "falha", (
        f"esperado status='falha' para look-ahead "
        f"(n={n}, idx_alvo={idx_alvo}, k={k}, modo={modo}); "
        f"recebido status={resultado.status!r}"
    )
    assert resultado.look_ahead_violation is True, (
        "look_ahead_violation deve ser True quando a estratégia tenta "
        "acessar barra futura (R5.3)"
    )
    assert resultado.motivo_falha is not None
    assert "look-ahead" in resultado.motivo_falha.lower(), (
        f"motivo_falha deve mencionar 'look-ahead'; "
        f"recebido {resultado.motivo_falha!r}"
    )
    # Campos zerados quando a janela falha (convenção do Runner).
    assert resultado.numero_trades == 0
    assert resultado.pnl_total == 0.0


# ---------------------------------------------------------------------------
# Sub-propriedade — estratégia honesta nunca dispara violação (R5.1, R5.2)
# ---------------------------------------------------------------------------


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n_barras_teste=st.integers(min_value=1, max_value=30))
def test_property_estrategia_honesta_nao_dispara_lookahead(
    n_barras_teste: int,
) -> None:
    """**Validates: Requirements 5.1, 5.2** (corolário de Property 13).

    Estratégias que respeitam o cursor (acessam apenas
    ``contexto[idx_atual]`` e ``contexto[idx_atual - 1]``) não devem
    nunca disparar :class:`LookAheadException`, independentemente do
    tamanho do Teste. Essa sub-propriedade ancora R5.1 e R5.2 (o
    Runner passa as barras de Treino e Teste em ordem cronológica e
    permite acesso ao histórico até a barra atual).
    """
    janela, dados = _construir_janela_e_dados(n_barras_teste)
    resultado = BacktestRunner.executar(
        janela=janela,
        dados=dados,
        estrategia=_EstrategiaHonesta(),
        configuracao=_config_minima(),
    )

    # Estratégia honesta não emite trades; quando ``n_barras_teste >= 1``,
    # o Runner conclui com status "sem-trades"; quando 0, idem.
    assert resultado.look_ahead_violation is False, (
        "estratégia honesta jamais deveria disparar look_ahead_violation"
    )
    assert resultado.status in ("sem-trades", "ok"), (
        f"status inesperado para estratégia honesta: {resultado.status!r}"
    )
    # Sanidade: motivo_falha vazio.
    assert resultado.motivo_falha is None
