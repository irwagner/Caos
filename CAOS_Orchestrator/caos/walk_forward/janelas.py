"""JanelaGenerator — geração determinística de janelas Walk-Forward (Spec 2 — Task 3).

Cobre o R3 do ``requirements.md`` do Spec 2 e a linha correspondente da
tabela em ``design.md`` seção 4 (Components and Interfaces).

Responsabilidade
----------------
Produzir, de forma 100% determinística, a lista de :class:`JanelaWF`
que será consumida pelo ``BacktestRunner`` e pelo ``WalkForwardEngine``.
A entrada é um conjunto de barras (DataFrame com schema canônico do
``Skill_Data_Reader``, ou ``DatetimeIndex``, ou iterável de timestamps
tz-aware UTC) somada a uma :class:`ConfiguracaoWalkForward` válida.

Regras aplicadas
----------------
- **R3.1** Janelas não-sobrepostas em Teste: o gerador exige
  ``passo_dias_uteis >= tamanho_teste_dias_uteis`` e devolve janelas
  cujos pares ``(teste_inicio, teste_fim)`` são disjuntos. Sobreposição
  em Treino é permitida (passo < tamanho_treino_dias_uteis).
- **R3.2** Quantidade de janelas: dada uma quantidade ``N`` de dias
  úteis disponíveis, são produzidas
  ``floor((N - tamanho_treino - tamanho_teste) / passo) + 1`` janelas
  quando ``N >= tamanho_treino + tamanho_teste``; caso contrário, lista
  vazia (dados insuficientes). Cada janela cabe **inteira** no histórico
  (Treino + Teste). A formulação difere ligeiramente de
  ``floor((N - tamanho_treino) / passo)`` literal do requirements porque
  exige que o Teste também caiba — interpretação consistente com o
  default ``passo == tamanho_teste`` e com R3.1 (não-sobreposição).
- **R3.3** Ordenação cronológica e ``indice`` 0-based estritamente
  crescente (0, 1, 2, ...). O ``NN`` 01..99 dentro do mesmo dia de
  execução é responsabilidade do ``WalkForwardEngine`` (Task 6) ao
  montar o ``identificador`` do ``ResultadoWalkForward``; o
  ``JanelaGenerator`` apenas cuida do índice 0-based.

Convenção de fronteiras (chave para a contiguidade Treino→Teste)
----------------------------------------------------------------
Cada dia útil é representado pelo ``Timestamp`` à meia-noite UTC daquele
dia. Para a janela ``k``:

- ``treino_inicio = dias[k*passo]``
- ``treino_fim    = dias[k*passo + tamanho_treino]``
- ``teste_inicio  = treino_fim``  (R3.1, e instrução explícita da Task 3)
- ``teste_fim     = dias[k*passo + tamanho_treino + tamanho_teste]``
  (ou ``dias[-1] + BDay(1)`` quando o índice ultrapassa o histórico
  disponível — caso típico da última janela quando ``passo ==
  tamanho_teste``).

Assim, uma barra com ``timestamp = t`` pertence ao Treino da janela ``k``
sse ``treino_inicio <= t < treino_fim`` e ao Teste sse
``teste_inicio <= t < teste_fim`` (semi-aberto à direita).

Ergonomia
---------
- :class:`JanelaGenerator` expõe ``gerar(...)`` como :func:`staticmethod`
  e a função-livre :func:`gerar_janelas` é alias de mesmo comportamento;
  ambas devolvem ``list[JanelaWF]`` deterministicamente.
- Erros de configuração (passo < tamanho_teste) viram :class:`ValueError`
  com mensagem em pt-BR (R3.1 — convenção de idioma).
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Union

import pandas as pd
from pandas.tseries.offsets import BDay

from caos.walk_forward.models import ConfiguracaoWalkForward, JanelaWF

# ---------------------------------------------------------------------------
# Tipos de entrada aceitos pelo gerador
# ---------------------------------------------------------------------------

#: Tipo união do parâmetro ``dados`` aceito por :meth:`JanelaGenerator.gerar`.
#:
#: - :class:`pandas.DataFrame` com schema canônico do ``Skill_Data_Reader``
#:   (coluna ``timestamp`` em ``datetime64[ns, UTC]``);
#: - :class:`pandas.DatetimeIndex` tz-aware UTC;
#: - :class:`Iterable` de :class:`pandas.Timestamp` ou :class:`datetime.datetime`,
#:   todos tz-aware UTC.
EntradaDados = Union[
    pd.DataFrame,
    pd.DatetimeIndex,
    Iterable[pd.Timestamp],
    Iterable[datetime],
]


# ---------------------------------------------------------------------------
# JanelaGenerator
# ---------------------------------------------------------------------------


class JanelaGenerator:
    """Gera lista determinística de :class:`JanelaWF` (R3).

    O gerador é puramente funcional: não mantém estado interno entre
    chamadas e não consulta o disco. Toda a informação necessária é
    fornecida pelos parâmetros de :meth:`gerar`.
    """

    NOME: str = "JanelaGenerator"

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    @staticmethod
    def gerar(
        dados: EntradaDados,
        configuracao: ConfiguracaoWalkForward,
        hash_dados: str,
    ) -> list[JanelaWF]:
        """Produz a lista de :class:`JanelaWF` para ``dados``.

        Parameters
        ----------
        dados:
            DataFrame (com coluna ``timestamp`` UTC), DatetimeIndex UTC
            ou iterável de timestamps tz-aware UTC. Apenas as datas
            (componente ``year-month-day`` em UTC) são usadas; horários
            são descartados após extração da data.
        configuracao:
            :class:`ConfiguracaoWalkForward` validada (Pydantic v2). O
            campo ``passo_dias_uteis`` precisa ser ``>=
            tamanho_teste_dias_uteis`` para satisfazer R3.1 (sem
            sobreposição em Teste).
        hash_dados:
            SHA-256 hex (64 chars ``[0-9a-f]``) do subset de dados
            usado. Repassado idêntico para cada :class:`JanelaWF`. O
            cálculo do hash é responsabilidade do caller (normalmente o
            ``WalkForwardEngine``), pois ele depende do conteúdo dos
            CSVs lidos pelo ``Skill_Data_Reader``.

        Returns
        -------
        list[JanelaWF]
            Lista possivelmente vazia, com ``indice`` 0-based estritamente
            crescente (0, 1, 2, ...). Vazia quando os dados fornecidos
            têm menos de ``tamanho_treino_dias_uteis +
            tamanho_teste_dias_uteis`` dias úteis.

        Raises
        ------
        ValueError
            Quando ``passo_dias_uteis < tamanho_teste_dias_uteis``
            (sobreposição entre janelas de Teste — R3.1) ou quando os
            timestamps fornecidos não são tz-aware UTC.
        """
        # 1. R3.1 — passo deve ser >= tamanho_teste para não sobrepor Testes.
        if configuracao.passo_dias_uteis is None:
            # Sanidade extra: o validator do modelo já preenche o default,
            # mas defendemos contra mutação acidental do objeto.
            raise ValueError(
                "ConfiguracaoWalkForward.passo_dias_uteis está None; "
                "o validator deveria tê-lo preenchido com "
                "tamanho_teste_dias_uteis"
            )
        if configuracao.passo_dias_uteis < configuracao.tamanho_teste_dias_uteis:
            raise ValueError(
                "passo_dias_uteis "
                f"({configuracao.passo_dias_uteis}) deve ser >= "
                "tamanho_teste_dias_uteis "
                f"({configuracao.tamanho_teste_dias_uteis}) para evitar "
                "sobreposição entre janelas de Teste (R3.1)"
            )

        # 2. Normaliza a entrada em lista ordenada de business days
        # (Timestamps UTC à meia-noite).
        dias = JanelaGenerator._extrair_dias_uteis(dados)
        n = len(dias)

        treino = configuracao.tamanho_treino_dias_uteis
        teste = configuracao.tamanho_teste_dias_uteis
        passo = configuracao.passo_dias_uteis

        # 3. R3.2 — janela só é gerada se Treino + Teste cabem inteiros.
        if n < treino + teste:
            return []

        # Quantidade de janelas que cabem (cada janela exige
        # k*passo + treino + teste <= n, com k 0-based).
        num_janelas = (n - treino - teste) // passo + 1

        # 4. Constrói cada JanelaWF.
        janelas: list[JanelaWF] = []
        for k in range(num_janelas):
            ti_idx = k * passo
            tf_idx = ti_idx + treino  # primeiro dia do Teste
            te_fim_idx = tf_idx + teste  # primeiro dia APÓS o Teste

            treino_inicio = dias[ti_idx]
            treino_fim = dias[tf_idx]  # == teste_inicio (R3.1)
            teste_inicio = treino_fim
            if te_fim_idx < n:
                teste_fim = dias[te_fim_idx]
            else:
                # Última janela cujo Teste termina exatamente no fim do
                # histórico: sintetiza fronteira com o próximo business
                # day após o último dia de Teste (BDay(1) preserva tz UTC).
                teste_fim = dias[te_fim_idx - 1] + BDay(1)

            janelas.append(
                JanelaWF(
                    indice=k,
                    treino_inicio=treino_inicio.to_pydatetime(),
                    treino_fim=treino_fim.to_pydatetime(),
                    teste_inicio=teste_inicio.to_pydatetime(),
                    teste_fim=teste_fim.to_pydatetime(),
                    hash_dados=hash_dados,
                )
            )

        return janelas

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _extrair_dias_uteis(dados: EntradaDados) -> list[pd.Timestamp]:
        """Extrai lista ordenada de business days UTC (sem repetição).

        Aceita as três formas de entrada documentadas em :data:`EntradaDados`.
        Sempre filtra finais de semana (sábado/domingo) — feriados
        permanecem se houver dados neles, pois o pipeline opera sobre
        os dias **disponíveis** no histórico, não sobre um calendário
        externo (ver R3.2).

        Returns
        -------
        list[pandas.Timestamp]
            Cada elemento é um :class:`~pandas.Timestamp` à meia-noite
            UTC; a lista é ordenada cronologicamente e sem duplicatas.
        """
        if isinstance(dados, pd.DataFrame):
            if "timestamp" not in dados.columns:
                raise ValueError(
                    "DataFrame de entrada deve conter coluna 'timestamp' "
                    "(schema canônico do Skill_Data_Reader)"
                )
            timestamps = pd.DatetimeIndex(dados["timestamp"])
        elif isinstance(dados, pd.DatetimeIndex):
            timestamps = dados
        else:
            # Iterable[pd.Timestamp | datetime].
            timestamps = pd.DatetimeIndex(list(dados))

        if len(timestamps) == 0:
            return []

        # Garante tz-aware UTC.
        if timestamps.tz is None:
            raise ValueError(
                "timestamps de entrada devem ter tzinfo UTC; "
                "recebido DatetimeIndex naive (sem fuso horário)"
            )
        if str(timestamps.tz) != "UTC":
            timestamps = timestamps.tz_convert("UTC")

        # Reduz a 1 entrada por dia útil:
        # 1) ``normalize()`` zera HH:MM:SS preservando tz UTC;
        # 2) ``unique()`` deduplica (preserva ordem original);
        # 3) ordenação explícita garante determinismo;
        # 4) filtro ``weekday < 5`` exclui sábado(5) e domingo(6).
        normalizados = timestamps.normalize().unique()
        ordenados = pd.DatetimeIndex(normalizados).sort_values()
        dias_uteis_idx = ordenados[ordenados.weekday < 5]

        # Converte explicitamente para list[Timestamp] para retorno
        # estável e iteração indexada por inteiro.
        return [pd.Timestamp(d) for d in dias_uteis_idx]


# ---------------------------------------------------------------------------
# Função-livre (alias ergonômico)
# ---------------------------------------------------------------------------


def gerar_janelas(
    dados: EntradaDados,
    configuracao: ConfiguracaoWalkForward,
    hash_dados: str,
) -> list[JanelaWF]:
    """Atalho funcional para :meth:`JanelaGenerator.gerar`.

    Útil em call sites que preferem estilo procedural ao invocar uma
    classe estática. O comportamento é idêntico.
    """
    return JanelaGenerator.gerar(dados, configuracao, hash_dados)


__all__ = [
    "EntradaDados",
    "JanelaGenerator",
    "gerar_janelas",
]
