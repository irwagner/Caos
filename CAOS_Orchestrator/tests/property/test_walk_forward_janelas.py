"""Property-based test do ``JanelaGenerator`` (Property 15 do design).

Implementa **Property 15 — Janelas Não-Sobrepostas** do ``design.md``
do Spec 2:

    For every pair of ``JanelaWF`` ``(j1, j2)`` produced by the same
    generator, ``j1.teste_fim < j2.teste_inicio`` OR
    ``j2.teste_fim < j1.teste_inicio``.

**Validates: Requirements 3.1**

Acima do enunciado literal, a Property 15 é estendida nesta suíte para
cobrir as demais garantias estruturais do gerador (R3.2, R3.3) que
dependem deterministicamente da mesma entrada. Isso evita criar uma
"propriedade nova" fora do design — todas as asserções abaixo são
consequência direta de R3.1, R3.2 ou R3.3:

1. **Quantidade exata de janelas** (R3.2): para histórico de ``N`` dias
   úteis, o gerador produz ``0`` quando ``N < treino + teste`` e
   exatamente ``floor((N - treino - teste) / passo) + 1`` caso contrário.
2. **Validação Pydantic** (R3.1, design 3): cada elemento retornado é
   instância de :class:`~caos.walk_forward.models.JanelaWF`.
3. **Fronteira contígua Treino→Teste** (R3.1): ``treino_fim ==
   teste_inicio`` para toda janela, garantindo que o cursor de Teste
   começa exatamente onde Treino terminou.
4. **Não-sobreposição entre Testes** (R3.1, enunciado canônico da
   Property 15): para qualquer par ``(j_i, j_{i+1})``,
   ``j_i.teste_fim <= j_{i+1}.teste_inicio``. Como o gerador devolve as
   janelas em ordem cronológica (R3.3), basta validar pares
   consecutivos para concluir não-sobreposição entre quaisquer pares.
5. **Índices contínuos 0-based** (R3.3): a sequência de ``indice`` é
   ``[0, 1, 2, ..., len(janelas) - 1]`` sem repetições nem buracos.

A estratégia gera tuplas ``(treino, teste, passo, n_dias)`` que cobrem
o espaço relevante:

- ``treino`` em ``[60, 120]`` (faixa válida de R2.1, mas teto reduzido
  em relação ao R2.1 ``[60, 504]`` para que cada amostra rode em <50ms).
- ``teste``  em ``[10, treino]`` (R2.2 — Treino ≥ Teste).
- ``passo``  em ``[teste, 60]`` (R3.1 — passo >= teste, sem
  sobreposição em Teste; teto pequeno preserva diversidade de janelas).
- ``n_dias`` em ``[teste, treino + 10 * teste]`` (cobre o caso de zero
  janelas, exatamente uma janela, e várias janelas).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from caos.walk_forward import (
    ConfiguracaoWalkForward,
    JanelaGenerator,
    JanelaWF,
)

HASH_FAKE = "0" * 63 + "f"


# ---------------------------------------------------------------------------
# Estratégias de geração
# ---------------------------------------------------------------------------


@st.composite
def _config_e_n_dias(draw: st.DrawFn) -> tuple[ConfiguracaoWalkForward, int]:
    """Gera ``(ConfiguracaoWalkForward, n_dias_uteis)`` com cobertura ampla.

    Retorna sempre um par auto-coerente:

    - ``teste <= treino`` (R2.2);
    - ``passo >= teste`` (R3.1);
    - ``n_dias`` cobre os três regimes da R3.2:

      * ``n_dias < treino + teste``  → 0 janelas;
      * ``n_dias == treino + teste`` → exatamente 1 janela;
      * ``n_dias > treino + teste``  → várias janelas.
    """
    treino = draw(st.integers(min_value=60, max_value=120))
    teste = draw(st.integers(min_value=10, max_value=min(treino, 60)))
    passo = draw(st.integers(min_value=teste, max_value=teste + 30))
    # n_dias cobre desde "menos do que cabe 1 janela" até "muitas janelas".
    n_dias = draw(
        st.integers(
            min_value=max(1, teste - 1),
            max_value=treino + 10 * teste,
        )
    )
    cfg = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=treino,
        tamanho_teste_dias_uteis=teste,
        passo_dias_uteis=passo,
        granularidade="1m",
    )
    return cfg, n_dias


def _bdays(quantidade: int) -> pd.DatetimeIndex:
    """Gera ``quantidade`` business days UTC consecutivos a partir de 2024-01-02."""
    if quantidade <= 0:
        return pd.DatetimeIndex([], tz="UTC")
    return pd.bdate_range("2024-01-02", periods=quantidade, tz="UTC")


# ---------------------------------------------------------------------------
# Property 15
# ---------------------------------------------------------------------------


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_config_e_n_dias())
def test_property_walk_forward_janelas(
    cfg_e_n: tuple[ConfiguracaoWalkForward, int],
) -> None:
    """**Validates: Requirements 3.1** (Property 15).

    Verifica em uma única passada as 5 garantias estruturais do
    ``JanelaGenerator`` listadas na docstring do módulo. Falha em
    qualquer uma delas indica violação direta de R3.1, R3.2 ou R3.3.
    """
    cfg, n_dias = cfg_e_n
    timestamps = _bdays(n_dias)

    janelas = JanelaGenerator.gerar(timestamps, cfg, HASH_FAKE)

    treino = cfg.tamanho_treino_dias_uteis
    teste = cfg.tamanho_teste_dias_uteis
    passo = cfg.passo_dias_uteis or teste

    # (1) Quantidade exata (R3.2).
    if n_dias < treino + teste:
        esperado = 0
    else:
        esperado = (n_dias - treino - teste) // passo + 1
    assert len(janelas) == esperado, (
        f"contagem de janelas divergiu: esperado {esperado}, "
        f"recebido {len(janelas)} "
        f"(treino={treino}, teste={teste}, passo={passo}, n_dias={n_dias})"
    )

    if not janelas:
        # Sem janelas, as demais asserções não se aplicam.
        return

    # (2) Cada elemento é instância de JanelaWF (R3.1, design 3).
    for j in janelas:
        assert isinstance(j, JanelaWF), (
            f"elemento {j!r} não é JanelaWF; "
            "JanelaGenerator deve devolver instâncias Pydantic v2 validadas"
        )

    # (5) Índices 0..N-1 contínuos (R3.3).
    indices = [j.indice for j in janelas]
    assert indices == list(range(len(janelas))), (
        f"índices não são 0-based contínuos: {indices}"
    )

    # (3) e (4): fronteira contígua Treino→Teste e Testes não-sobrepostos.
    for j in janelas:
        # (3) treino_fim == teste_inicio (R3.1).
        assert j.treino_fim == j.teste_inicio, (
            f"janela {j.indice}: treino_fim={j.treino_fim.isoformat()} != "
            f"teste_inicio={j.teste_inicio.isoformat()}"
        )

    for atual, prox in zip(janelas, janelas[1:]):
        # (4) Não-sobreposição entre Testes (R3.1) — enunciado canônico.
        assert atual.teste_fim <= prox.teste_inicio, (
            f"janelas {atual.indice} e {prox.indice} têm Testes sobrepostos: "
            f"{atual.teste_fim.isoformat()} > {prox.teste_inicio.isoformat()}"
        )


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(_config_e_n_dias())
def test_property_walk_forward_janelas_e_deterministico(
    cfg_e_n: tuple[ConfiguracaoWalkForward, int],
) -> None:
    """**Validates: Requirements 3.1, 3.3** (corolário determinístico).

    Duas invocações de ``JanelaGenerator.gerar`` com a mesma entrada
    devolvem listas byte-a-byte idênticas (R3.3 — geração determinística).
    Esta sub-propriedade é necessária para que a Property 14
    (determinismo do Walk-Forward inteiro) seja válida — caso contrário,
    a fonte de não-determinismo teria que estar fora do gerador.
    """
    cfg, n_dias = cfg_e_n
    timestamps = _bdays(n_dias)

    a = JanelaGenerator.gerar(timestamps, cfg, HASH_FAKE)
    b = JanelaGenerator.gerar(timestamps, cfg, HASH_FAKE)

    assert a == b, "JanelaGenerator deve ser determinístico (R3.3)"
    # Serialização canônica também deve coincidir.
    json_a = [j.model_dump_json() for j in a]
    json_b = [j.model_dump_json() for j in b]
    assert json_a == json_b
