"""BacktestRunner + LookAhead detection (Spec 2 — Task 4).

Cobre **R5** do ``requirements.md`` do Spec 2 (isolamento Treino/Teste sem
look-ahead) e a linha correspondente da tabela em ``design.md`` seção 4
(Components and Interfaces).

Componentes públicos
--------------------
- :class:`Estrategia` — :class:`typing.Protocol` plugável (com
  ``on_barra``/``finalizar``; ``treinar`` é opcional).
- :class:`Trade` — modelo Pydantic v2 mínimo emitido pela estratégia ao
  fim do Periodo_Teste; consumido em Task 5 (MetricasCalculator).
- :class:`BarrasTesteIterator` — iterator anti-look-ahead que envolve as
  barras do Teste; expõe apenas barras ``0..idx_atual`` à estratégia.
- :class:`LookAheadException` — exceção tipificada com ``idx_atual`` e
  ``idx_acessado`` para auditoria.
- :class:`BacktestRunner` — executa uma janela e retorna
  :class:`~caos.walk_forward.models.ResultadoJanela`.

Fluxo de execução de uma janela
-------------------------------
1. ``random.seed(seed)`` e ``numpy.random.seed(seed)`` antes de tocar a
   estratégia (R7.1 — reprodutibilidade por janela).
2. Slice ``[treino_inicio, treino_fim)`` é passado a
   ``estrategia.treinar(historico_treino)`` (cópia defensiva). Esse
   método é opcional — estratégias sem fase de treino o omitem.
3. Slice ``[teste_inicio, teste_fim)`` é envolvido em
   :class:`BarrasTesteIterator`. O Runner itera sobre o iterator e
   chama ``estrategia.on_barra(barra, contexto)`` para cada barra (em
   ordem cronológica). O ``contexto`` é o próprio iterator e é a
   única forma autorizada da estratégia consultar histórico —
   tentativas de acesso a ``idx > idx_atual`` levantam
   :class:`LookAheadException`.
4. ``estrategia.finalizar()`` é chamado uma vez ao final; deve retornar
   uma sequência de :class:`Trade`.
5. O Runner empacota tudo em :class:`ResultadoJanela` (status ``ok``,
   ``sem-trades`` ou ``falha`` — R6.2, R10.1).

Mapeamento de status (decidido pela R5 + R6.2 + R10.1):

- Sucesso com ``len(trades) >= 1`` ⇒ ``status="ok"``.
- Sucesso com ``len(trades) == 0`` (inclusive Teste vazio) ⇒
  ``status="sem-trades"``.
- :class:`LookAheadException` ⇒ ``status="falha"``,
  ``look_ahead_violation=True``, ``motivo_falha`` preenchido.
- Qualquer outra exceção ⇒ ``status="falha"``, ``motivo_falha``
  preenchido.

Convivência de dois modelos de Trade
------------------------------------
Historicamente a Task 4 introduziu :class:`Trade` (este módulo) como
modelo mínimo (``pnl``/``mfe``/``mae``) e a Task 5 introduziu
:class:`caos.walk_forward.metricas.Trade` como modelo canônico (rico,
com ``entrada_preco``/``saida_preco``/``lado``/``contratos``/...). A
Task 6 (``WalkForwardEngine``) precisa de métricas completas por janela.
Para reconciliar sem quebrar testes pré-existentes, o Runner detecta
o tipo dos trades retornados por ``estrategia.finalizar()``:

- Se **todos** os trades forem instâncias de
  :class:`caos.walk_forward.metricas.Trade`, o Runner delega o cálculo
  ao :class:`~caos.walk_forward.metricas.MetricasCalculator` e devolve
  um :class:`~caos.walk_forward.models.ResultadoJanela` com métricas
  completas (Sharpe, Calmar, drawdown, etc.).
- Caso contrário (lista vazia ou contendo o :class:`Trade` mínimo
  abaixo), o Runner mantém o comportamento legado: ``ResultadoJanela``
  com apenas ``numero_trades`` e ``pnl_total`` populados.

Convenções: pt-BR (R3.2 do Spec 1), Pydantic v2, Windows + cmd.
"""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import (
    Any,
    Optional,
    Protocol,
    Sequence,
    Union,
    runtime_checkable,
)

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from caos.walk_forward.models import (
    ConfiguracaoWalkForward,
    CustosOperacionais,
    JanelaWF,
    ResultadoJanela,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Limite de truncamento aplicado ao campo ``motivo_falha`` (R10.3).
_MOTIVO_FALHA_LIMITE: int = 4096

#: Nome de coluna obrigatório no DataFrame de entrada do Runner.
_COLUNA_TIMESTAMP: str = "timestamp"


# ---------------------------------------------------------------------------
# Trade — modelo emitido pela estratégia
# ---------------------------------------------------------------------------


class Trade(BaseModel):
    """Trade fechado emitido pela :class:`Estrategia` ao fim do Teste.

    Modelo deliberadamente mínimo nesta task: apenas o suficiente para o
    Runner contar trades (``numero_trades``) e somar PnL (``pnl_total``).
    O cálculo de Sharpe, Calmar, drawdown, win rate, MFE/MAE médios e
    payoff médio fica para a Task 5 (``MetricasCalculator``).

    Campos:

    - ``pnl``: PnL realizado do trade. Pode ser negativo (loss). A
      unidade (pontos do índice ou USD) é convenção da estratégia, não
      do Runner.
    - ``mfe``: *Maximum Favorable Excursion* — magnitude máxima do
      preço a favor durante o trade. Convenção: ``>= 0``. Default ``0.0``
      para estratégias que ainda não rastreiam excursões.
    - ``mae``: *Maximum Adverse Excursion* — magnitude máxima do preço
      contra o trade. Convenção: ``<= 0``. Default ``0.0``.
    - ``timestamp_entrada`` / ``timestamp_saida``: opcionais — Task 5
      pode usá-los para Calmar e drawdown em dias.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pnl: float
    mfe: float = 0.0
    mae: float = 0.0
    timestamp_entrada: Optional[datetime] = None
    timestamp_saida: Optional[datetime] = None


# ---------------------------------------------------------------------------
# LookAheadException
# ---------------------------------------------------------------------------


class LookAheadException(RuntimeError):
    """Lançada quando a estratégia tenta acessar uma barra futura (R5.3).

    Atributos:

    - ``idx_atual``: cursor da barra corrente no
      :class:`BarrasTesteIterator` no instante da violação.
    - ``idx_acessado``: índice (0-based) que a estratégia tentou
      acessar e que excedeu o cursor.

    A mensagem é estável em pt-BR e não depende de detalhes do pandas,
    para facilitar asserts de teste e auditoria no relatório de janela.
    """

    def __init__(self, *, idx_atual: int, idx_acessado: int) -> None:
        self.idx_atual = idx_atual
        self.idx_acessado = idx_acessado
        super().__init__(
            "look-ahead detectado: estratégia tentou acessar barra "
            f"idx={idx_acessado}, mas o cursor atual é "
            f"idx_atual={idx_atual} (R5)"
        )


# ---------------------------------------------------------------------------
# BarrasTesteIterator
# ---------------------------------------------------------------------------


class BarrasTesteIterator:
    """Iterator sobre as barras do Periodo_Teste com detecção de look-ahead.

    Garante R5.2 e R5.3: durante a iteração, a estratégia consegue ver
    apenas a barra no cursor ``idx_atual`` e barras anteriores
    ``0..idx_atual-1``. Qualquer tentativa de acesso a ``i > idx_atual``
    levanta :class:`LookAheadException`.

    Modos de acesso suportados:

    - **Iteração** (``for barra in iterator``): produz cada barra em
      ordem cronológica, avançando o cursor.
    - **Indexação positiva** (``iterator[i]``): só permitida se
      ``i <= idx_atual``; do contrário, ``LookAheadException``.
    - **Indexação negativa** (``iterator[-1]``, ``iterator[-2]``...):
      relativa à janela visível (``idx_atual + 1`` barras), nunca ao
      tamanho total do Teste — assim a estratégia não vaza informação
      sobre o futuro pela diferença de tamanhos.
    - **Fatiamento** (``iterator[a:b]``): permitido apenas se
      ``b <= idx_atual + 1``; do contrário, ``LookAheadException``.
    - **Propriedades públicas**: ``idx_atual``, ``barra_atual``,
      ``total_visivel``, ``__len__``.

    O atributo subjacente ``_df`` é privado (prefixo ``_``) para
    desencorajar acesso direto. Acesso via atributo público a métodos
    do pandas que retornariam barras futuras (``.iloc[k]``,
    ``.loc[...]``) também não é exposto.

    Notes
    -----
    Re-iterar o mesmo objeto reseta o cursor para ``-1``. Isso é útil
    em testes mas o ``BacktestRunner`` itera apenas uma vez por janela.
    """

    def __init__(self, barras: pd.DataFrame) -> None:
        # Cópia defensiva + reset_index para indexação iloc estável (0..N-1).
        self._df: pd.DataFrame = barras.reset_index(drop=True).copy()
        self._idx_atual: int = -1

    # ------------------------------------------------------------------
    # Propriedades de estado
    # ------------------------------------------------------------------

    @property
    def idx_atual(self) -> int:
        """Cursor da barra corrente (``-1`` antes de iniciar a iteração)."""
        return self._idx_atual

    @property
    def total_visivel(self) -> int:
        """Quantidade de barras já vistas (cursor + 1)."""
        return self._idx_atual + 1

    @property
    def barra_atual(self) -> pd.Series:
        """A barra no cursor atual.

        Raises
        ------
        IndexError
            Se a iteração ainda não começou (``idx_atual == -1``).
        """
        if self._idx_atual < 0:
            raise IndexError(
                "iteração ainda não iniciou; barra_atual é indefinida"
            )
        return self._df.iloc[self._idx_atual]

    # ------------------------------------------------------------------
    # Protocolo iterador
    # ------------------------------------------------------------------

    def __iter__(self) -> "BarrasTesteIterator":
        # Reset explícito permite re-iterar (útil em testes).
        self._idx_atual = -1
        return self

    def __next__(self) -> pd.Series:
        proximo = self._idx_atual + 1
        if proximo >= len(self._df):
            raise StopIteration
        self._idx_atual = proximo
        return self._df.iloc[self._idx_atual]

    def __len__(self) -> int:
        # Apenas a janela visível — esconde do consumidor o tamanho total.
        return self.total_visivel

    # ------------------------------------------------------------------
    # Indexação com detecção de look-ahead
    # ------------------------------------------------------------------

    def __getitem__(
        self, idx: Union[int, slice]
    ) -> Union[pd.Series, pd.DataFrame]:
        if isinstance(idx, slice):
            return self._getitem_slice(idx)
        if isinstance(idx, (int, np.integer)):
            return self._getitem_int(int(idx))
        raise TypeError(
            "BarrasTesteIterator aceita apenas índices inteiros ou "
            f"slices; recebido {type(idx).__name__}"
        )

    def _getitem_int(self, idx: int) -> pd.Series:
        if idx >= 0:
            if idx > self._idx_atual:
                raise LookAheadException(
                    idx_atual=self._idx_atual,
                    idx_acessado=idx,
                )
            return self._df.iloc[idx]
        # Negativo ⇒ relativo à janela visível (não ao tamanho total).
        real = self._idx_atual + 1 + idx
        if real < 0:
            raise IndexError(
                f"índice negativo {idx} fora do range visível "
                f"(idx_atual={self._idx_atual}); requer "
                f"idx >= -{self._idx_atual + 1}"
            )
        return self._df.iloc[real]

    def _getitem_slice(self, slc: slice) -> pd.DataFrame:
        # Convenção: ``stop=None`` significa "até o fim da janela visível".
        start = 0 if slc.start is None else int(slc.start)
        step = 1 if slc.step is None else int(slc.step)
        stop_efetivo = (
            self._idx_atual + 1 if slc.stop is None else int(slc.stop)
        )

        # Detecção de look-ahead em ambos os limites.
        if slc.stop is not None and stop_efetivo > self._idx_atual + 1:
            raise LookAheadException(
                idx_atual=self._idx_atual,
                idx_acessado=stop_efetivo - 1,
            )
        if start > self._idx_atual + 1:
            raise LookAheadException(
                idx_atual=self._idx_atual,
                idx_acessado=start,
            )
        return self._df.iloc[start:stop_efetivo:step]


# ---------------------------------------------------------------------------
# Estrategia Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Estrategia(Protocol):
    """Protocolo plugável de estratégia de trading no Walk-Forward (design 5).

    O :class:`BacktestRunner` instancia (ou recebe) a estratégia uma
    vez por janela e a alimenta nesta ordem:

    1. (**Opcional**) ``treinar(historico_treino)`` — recebe
       :class:`pandas.DataFrame` com todas as barras de Treino de uma
       só vez (cópia defensiva, read-only). Estratégias sem fase de
       treino podem omitir o método; o Runner detecta via
       :func:`getattr` e pula a chamada.
    2. ``on_barra(barra, contexto)`` — chamado para **cada** barra do
       Teste em ordem cronológica. ``barra`` é a :class:`pandas.Series`
       da barra corrente; ``contexto`` é o
       :class:`BarrasTesteIterator` com detecção de look-ahead.
    3. ``finalizar()`` — chamado uma vez ao fim do Teste. Deve retornar
       uma sequência (lista, tupla, etc.) de :class:`Trade` ou de dicts
       compatíveis com :class:`Trade.model_validate`.

    Apenas ``on_barra`` e ``finalizar`` são exigidos pelo Protocol; o
    decorator :func:`runtime_checkable` permite ``isinstance(obj,
    Estrategia)`` em testes que querem validar a aderência ao
    contrato.
    """

    def on_barra(
        self,
        barra: pd.Series,
        contexto: "BarrasTesteIterator",
    ) -> None:
        """Notifica a estratégia da barra atual no Periodo_Teste."""
        ...

    def finalizar(self) -> Sequence[Trade]:
        """Retorna a lista de :class:`Trade` fechados na janela."""
        ...


# ---------------------------------------------------------------------------
# BacktestRunner
# ---------------------------------------------------------------------------


class BacktestRunner:
    """Executa uma janela de Walk-Forward com isolamento Treino/Teste.

    Cobre **R5**: durante o Periodo_Teste, a estratégia recebe barras
    barra-a-barra em ordem cronológica e qualquer tentativa de acesso
    a barras futuras é detectada via :class:`BarrasTesteIterator` que
    levanta :class:`LookAheadException`. O Runner empacota o resultado
    em :class:`~caos.walk_forward.models.ResultadoJanela` com
    ``look_ahead_violation=True`` quando a violação ocorre.
    """

    NOME: str = "BacktestRunner"

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    @staticmethod
    def executar(
        janela: JanelaWF,
        dados: pd.DataFrame,
        estrategia: Estrategia,
        configuracao: ConfiguracaoWalkForward,
    ) -> ResultadoJanela:
        """Executa a janela e retorna :class:`ResultadoJanela`.

        Parameters
        ----------
        janela:
            :class:`JanelaWF` a ser executada (define os intervalos
            ``[treino_inicio, treino_fim)`` e ``[teste_inicio,
            teste_fim)``).
        dados:
            :class:`pandas.DataFrame` canônico (schema do
            ``Skill_Data_Reader``) que cobre **ambos** os intervalos da
            janela. Filtragem é feita internamente por comparação
            de ``timestamp``.
        estrategia:
            Implementação compatível com :class:`Estrategia`
            (``on_barra``/``finalizar`` obrigatórios; ``treinar``
            opcional).
        configuracao:
            :class:`ConfiguracaoWalkForward` validada (Pydantic v2). O
            campo ``seed`` é aplicado a :func:`random.seed` e
            :func:`numpy.random.seed` antes da fase de treino.

        Returns
        -------
        ResultadoJanela
            Resultado tipificado da janela com status ``ok``,
            ``sem-trades`` ou ``falha``.
        """
        nome_estrategia = _resolver_nome_estrategia(estrategia)
        inicio_ns = time.monotonic_ns()
        try:
            return BacktestRunner._executar_interno(
                janela=janela,
                dados=dados,
                estrategia=estrategia,
                configuracao=configuracao,
                nome_estrategia=nome_estrategia,
                inicio_ns=inicio_ns,
            )
        except LookAheadException as exc:
            # Tratamento explícito da violação de R5.3: status ``falha``
            # com ``look_ahead_violation=True``.
            return _resultado_falha(
                janela=janela,
                nome_estrategia=nome_estrategia,
                configuracao=configuracao,
                inicio_ns=inicio_ns,
                motivo=str(exc),
                look_ahead=True,
            )
        except Exception as exc:
            # Qualquer outra exceção ⇒ status ``falha`` (R10.1).
            motivo = f"{type(exc).__name__}: {exc}"
            return _resultado_falha(
                janela=janela,
                nome_estrategia=nome_estrategia,
                configuracao=configuracao,
                inicio_ns=inicio_ns,
                motivo=motivo,
                look_ahead=False,
            )

    # ------------------------------------------------------------------
    # Núcleo (sem captura de exceções — caller é ``executar``)
    # ------------------------------------------------------------------

    @staticmethod
    def _executar_interno(
        *,
        janela: JanelaWF,
        dados: pd.DataFrame,
        estrategia: Estrategia,
        configuracao: ConfiguracaoWalkForward,
        nome_estrategia: str,
        inicio_ns: int,
    ) -> ResultadoJanela:
        # Validação mínima do schema de entrada.
        if _COLUNA_TIMESTAMP not in dados.columns:
            raise ValueError(
                f"DataFrame 'dados' não contém coluna {_COLUNA_TIMESTAMP!r} "
                "(schema canônico do Skill_Data_Reader)"
            )

        # Slice em Treino e Teste por intervalo semi-aberto à direita
        # (compatível com a convenção do JanelaGenerator).
        treino_inicio = pd.Timestamp(janela.treino_inicio)
        treino_fim = pd.Timestamp(janela.treino_fim)
        teste_inicio = pd.Timestamp(janela.teste_inicio)
        teste_fim = pd.Timestamp(janela.teste_fim)

        treino_df = dados[
            (dados[_COLUNA_TIMESTAMP] >= treino_inicio)
            & (dados[_COLUNA_TIMESTAMP] < treino_fim)
        ].reset_index(drop=True)
        teste_df = dados[
            (dados[_COLUNA_TIMESTAMP] >= teste_inicio)
            & (dados[_COLUNA_TIMESTAMP] < teste_fim)
        ].reset_index(drop=True)

        # R7.1 — reprodutibilidade: aplicar seed antes da estratégia.
        random.seed(configuracao.seed)
        np.random.seed(configuracao.seed)

        # Fase 1 — Treino (opcional).
        treinar = getattr(estrategia, "treinar", None)
        if callable(treinar):
            # Cópia defensiva — a estratégia recebe DataFrame "read-only".
            treinar(treino_df.copy())

        # Fase 2 — Teste com iterator anti-look-ahead.
        iterator = BarrasTesteIterator(teste_df)
        if len(teste_df) == 0:
            # Sem barras no Teste ⇒ não há trades possíveis (R6.2).
            return _resultado_sem_trades(
                janela=janela,
                nome_estrategia=nome_estrategia,
                configuracao=configuracao,
                inicio_ns=inicio_ns,
            )

        for barra in iterator:
            estrategia.on_barra(barra, iterator)

        # Fase 3 — Coleta de trades.
        finalizar = getattr(estrategia, "finalizar", None)
        if callable(finalizar):
            trades_brutos = list(finalizar() or [])
        else:
            trades_brutos = []
        trades = _normalizar_trades(trades_brutos)

        # Aplica fricção (slippage + comissão) — Decisao_2026-05-23-01.
        # Quando configuracao.custos é None ou zerado, é no-op.
        trades = _aplicar_custos_operacionais(trades, configuracao.custos)

        numero_trades = len(trades)

        if numero_trades == 0:
            # Janela rodou sem incidentes mas estratégia não emitiu trades.
            return _resultado_sem_trades(
                janela=janela,
                nome_estrategia=nome_estrategia,
                configuracao=configuracao,
                inicio_ns=inicio_ns,
            )

        # Reconciliação dos dois modelos de Trade (ver docstring do
        # módulo). Se todos os trades forem ``metricas.Trade``, delega
        # cálculo completo ao :class:`MetricasCalculator`. Caso contrário
        # mantém o caminho legado (apenas ``numero_trades`` + ``pnl_total``).
        from caos.walk_forward.metricas import (
            MetricasCalculator as _MetricasCalculator,
            Trade as _TradeMetricas,
        )

        if all(isinstance(t, _TradeMetricas) for t in trades):
            duracao_ms_calc = _duracao_ms(inicio_ns)
            return _MetricasCalculator.calcular(
                trades=trades,
                janela=janela,
                estrategia=nome_estrategia,
                configuracao=configuracao,
                duracao_ms=duracao_ms_calc,
                look_ahead_violation=False,
            )

        # Caminho legado (Trade mínimo) — preserva testes da Task 4.
        pnl_total = float(sum(t.pnl for t in trades))

        # Status ``ok`` — métricas detalhadas ficam para Task 5
        # (MetricasCalculator). Por ora, apenas ``numero_trades`` e
        # ``pnl_total`` são preenchidos; o restante permanece ``None``.
        return ResultadoJanela(
            janela=janela,
            estrategia=nome_estrategia,
            configuracao=configuracao,
            numero_trades=numero_trades,
            pnl_total=pnl_total,
            look_ahead_violation=False,
            status="ok",
            motivo_falha=None,
            duracao_ms=_duracao_ms(inicio_ns),
        )


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------


def _resolver_nome_estrategia(estrategia: Any) -> str:
    """Retorna o nome (curto) da estratégia para registro em ResultadoJanela.

    Procura os atributos públicos ``nome`` (lowercase) e ``NOME``
    (uppercase) na ordem; em ambos os casos exige que o valor seja
    string não-vazia. Se nenhum estiver disponível, recai para o nome
    do tipo (``type(estrategia).__name__``). O resultado é truncado a
    200 caracteres para caber no campo ``ResultadoJanela.estrategia``.
    """
    for atributo in ("nome", "NOME"):
        valor = getattr(estrategia, atributo, None)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()[:200]
    return type(estrategia).__name__[:200]


def _normalizar_trades(trades_brutos: list[Any]) -> list[Any]:
    """Aceita lista de :class:`Trade` (mínimo ou rico) ou de dicts.

    Estratégias podem retornar:

    - Instâncias de :class:`caos.walk_forward.runner.Trade` (modelo
      mínimo desta task);
    - Instâncias de :class:`caos.walk_forward.metricas.Trade` (modelo
      rico — necessário para o ``WalkForwardEngine``);
    - Dicts compatíveis com :meth:`Trade.model_validate` (modelo mínimo).

    Qualquer outro tipo levanta :class:`TypeError`, que será capturado
    pelo ``BacktestRunner.executar`` e empacotado em ``status="falha"``.
    """
    # Importação local para evitar ciclo na carga do módulo.
    from caos.walk_forward.metricas import Trade as _TradeMetricas

    trades: list[Any] = []
    for bruto in trades_brutos:
        if isinstance(bruto, (Trade, _TradeMetricas)):
            trades.append(bruto)
        elif isinstance(bruto, dict):
            trades.append(Trade.model_validate(bruto))
        else:
            raise TypeError(
                "estrategia.finalizar() retornou item inesperado de tipo "
                f"{type(bruto).__name__}; esperado Trade (mínimo ou rico) "
                "ou dict"
            )
    return trades


def _aplicar_custos_operacionais(
    trades: list[Any],
    custos: Optional[CustosOperacionais],
) -> list[Any]:
    """Aplica fricção de execução (slippage + comissão) a cada trade.

    Modelo: cada trade paga 2 lados (entrada + saída). Para preservar
    a semântica de ``trade.pnl_pontos()`` (geometria entrada→saída em
    pontos × contratos), deslocamos o ``entrada_preco`` e o
    ``saida_preco`` na direção desfavorável pela metade do custo total
    em pontos por contrato. Trades ``long`` ficam com entrada um pouco
    mais cara e saída um pouco mais barata; ``short`` o oposto.

    Trades do modelo mínimo (:class:`runner.Trade`) recebem desconto
    direto no campo ``pnl`` — não têm preços a deslocar.

    Quando ``custos`` é ``None`` ou ``custos.eh_zerado()``, devolve a
    lista original sem cópia (no-op rápido para o caminho legado).
    """
    if custos is None or custos.eh_zerado():
        return trades

    # Importação local para evitar ciclo.
    from caos.walk_forward.metricas import Trade as _TradeMetricas

    ajustados: list[Any] = []
    for t in trades:
        if isinstance(t, _TradeMetricas):
            # Custo total round-trip em pontos × contratos.
            custo_total_pts = custos.custo_total_pontos(t.contratos)
            # Custo por lado em pontos (já dividido por contratos).
            custo_por_lado_pts_unit = custo_total_pts / (2.0 * t.contratos)
            if t.lado == "long":
                # Pago caro na entrada, vendo barato na saída.
                novo_entrada = t.entrada_preco + custo_por_lado_pts_unit
                nova_saida = t.saida_preco - custo_por_lado_pts_unit
            else:  # short
                novo_entrada = t.entrada_preco - custo_por_lado_pts_unit
                nova_saida = t.saida_preco + custo_por_lado_pts_unit
            ajustados.append(
                t.model_copy(
                    update={
                        "entrada_preco": novo_entrada,
                        "saida_preco": nova_saida,
                    }
                )
            )
        elif isinstance(t, Trade):
            # Modelo mínimo: trade não conhece ``contratos``; assumimos
            # 1 contrato (caminho legado de testes da Task 4).
            custo_total_pts = custos.custo_total_pontos(1)
            ajustados.append(
                t.model_copy(update={"pnl": float(t.pnl) - custo_total_pts})
            )
        else:
            # Tipo desconhecido — passa adiante intacto. O caller já
            # validou em _normalizar_trades.
            ajustados.append(t)
    return ajustados


def _resultado_falha(
    *,
    janela: JanelaWF,
    nome_estrategia: str,
    configuracao: ConfiguracaoWalkForward,
    inicio_ns: int,
    motivo: str,
    look_ahead: bool,
) -> ResultadoJanela:
    """Constrói :class:`ResultadoJanela` com status ``falha`` (R10.1)."""
    motivo_truncado = motivo[:_MOTIVO_FALHA_LIMITE]
    if not motivo_truncado:
        # ResultadoJanela exige motivo_falha não vazio quando status='falha'.
        motivo_truncado = "falha sem mensagem"
    return ResultadoJanela(
        janela=janela,
        estrategia=nome_estrategia,
        configuracao=configuracao,
        numero_trades=0,
        pnl_total=0.0,
        look_ahead_violation=look_ahead,
        status="falha",
        motivo_falha=motivo_truncado,
        duracao_ms=_duracao_ms(inicio_ns),
    )


def _resultado_sem_trades(
    *,
    janela: JanelaWF,
    nome_estrategia: str,
    configuracao: ConfiguracaoWalkForward,
    inicio_ns: int,
) -> ResultadoJanela:
    """Constrói :class:`ResultadoJanela` com status ``sem-trades`` (R6.2)."""
    return ResultadoJanela(
        janela=janela,
        estrategia=nome_estrategia,
        configuracao=configuracao,
        numero_trades=0,
        pnl_total=0.0,
        look_ahead_violation=False,
        status="sem-trades",
        motivo_falha=None,
        duracao_ms=_duracao_ms(inicio_ns),
    )


def _duracao_ms(inicio_ns: int) -> int:
    """Diferença em milissegundos entre ``time.monotonic_ns()`` e ``inicio_ns``."""
    return max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)


__all__ = [
    "BacktestRunner",
    "BarrasTesteIterator",
    "Estrategia",
    "LookAheadException",
    "Trade",
]
