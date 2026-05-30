"""Plugin ``EstrategiaVvgLateSessionReversal`` para o Walk-Forward (Spec —
VVG Late-Session Reversal, Tarefa 4).

Adaptador fino que conecta as duas camadas puras/stateful da estratégia ao
protocolo :class:`caos.walk_forward.runner.Estrategia` consumido pelo
:class:`caos.walk_forward.engine.WalkForwardEngine`:

- :class:`~caos.walk_forward.estrategias.vvg_classifier.VvgClassifier`
  (Tarefa 3) — classifica cada dia útil como VVG-positivo/negativo a partir
  das barras de minuto (baseline rolling de volume + gap). É **stateful mas
  determinístico**.
- :func:`~caos.walk_forward.estrategias.vvg_logica.decidir_acao` (Tarefa 2)
  — função **pura** que, dado ``(barra, estado, parametros)``, devolve uma
  das 4 ações canônicas (``LONG``/``SHORT``/``FECHAR``/``NADA``) e um
  **novo** estado. O flag ``vvg_positivo`` é fornecido EXTERNAMENTE por este
  plugin (a partir do classificador) antes de chamar ``decidir_acao``.

O plugin é deliberadamente **fino**: NÃO reimplementa a regra de decisão
(reusa ``decidir_acao``) e NÃO recalcula VVG (reusa ``VvgClassifier``). Sua
única responsabilidade própria é a **simulação do motor de execução** —
abrir/fechar posição local e, sobretudo, simular se o stop ou o target foi
atingido *intrabar* antes do encerramento forçado de fim de sessão (ver
"Simulação de stop/target intrabar" abaixo). Esse motor de execução vive no
adaptador, não na função pura — alinhado ao design (``decidir_acao`` só
emite ``FECHAR`` no fim de sessão; stop/target são do motor).

Schema de Trade — alinhamento com o código real do Spec 2
---------------------------------------------------------
O ``design.md`` desta feature esboça um ``Trade`` "rico" (com ``pnl_usd``,
``metadados={...}`` etc.). Esse esboço **nunca foi implementado**: a fonte
da verdade é :class:`caos.walk_forward.metricas.Trade`, um modelo Pydantic
com **8 campos** e ``extra="forbid"`` — sem ``pnl_usd``, sem ``metadados``.
O plugin ``EstrategiaORB`` (Spec 4), citado como referência de protocolo,
emite exatamente esse Trade canônico de 8 campos. Portanto:

- Cada :class:`~caos.walk_forward.metricas.Trade` emitido usa **somente** o
  schema canônico (entrada/saída timestamp+preço, ``lado``, ``contratos=1``,
  ``mfe_pontos``, ``mae_pontos``).
- Os metadados pedidos pela Tarefa 4 (``vvg_positivo``, ``drift_pontos``,
  ``motivo_saida``) NÃO cabem no Trade (``extra="forbid"``). Preservamos
  cada um numa **estrutura paralela** alinhada por índice
  (:attr:`metadados_trades`), para auditoria/depuração, sem violar o schema
  nem quebrar a normalização do ``BacktestRunner``.

Custos operacionais — aplicados pelo runner, não pelo plugin
------------------------------------------------------------
A fricção (slippage + comissão) é aplicada **uma vez** pelo
``BacktestRunner`` via ``_aplicar_custos_operacionais(trades,
configuracao.custos)`` — exatamente como ocorre com o ``EstrategiaORB``,
que NÃO desconta custos no próprio plugin. Aplicar custos aqui também
causaria **dupla contagem**. Mantemos o parâmetro ``custos`` no
construtor por compatibilidade com a assinatura do ``design.md`` e o
expomos via :attr:`custos`, mas ele NÃO é descontado dos preços emitidos.
O ``Trade`` canônico carrega preços brutos; o PnL líquido em pontos sai do
``MetricasCalculator`` após a fricção do runner.

MaxContratos conceitual = 1
---------------------------
Toda posição aqui é de **1 contrato** (``contratos=1`` em todo Trade),
refletindo o ``MaxContratos = 1`` fixo permanente (R4.1). O sizing real do
NT8 é responsabilidade da subclasse C# ``StrategyVvgLateSessionReversal``
(via ``Strategy_CAOS``), fora do escopo deste plugin.

Convenções: identificadores Python idiomáticos (snake_case);
docstrings/mensagens em pt-BR; termos técnicos em inglês.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import List, Optional, Sequence

import pandas as pd

from caos.walk_forward.estrategias.vvg_classifier import (
    ResultadoClassificacao,
    VvgClassifier,
)
from caos.walk_forward.estrategias.vvg_logica import (
    AcaoVvg,
    Barra,
    EstadoVvg,
    ParametrosVvg,
    decidir_acao,
    registrar_saida_externa,
)
from caos.walk_forward.metricas import Trade
from caos.walk_forward.models import CustosOperacionais
from caos.walk_forward.runner import BarrasTesteIterator


class _PosicaoAberta:
    """Estado interno do trade em andamento (motor de execução do plugin).

    Carrega, além do necessário para emitir o :class:`Trade` canônico
    (preços/timestamp de entrada e excursões), os níveis de stop/target já
    materializados em **preço** e os metadados de auditoria
    (``vvg_positivo``, ``drift_pontos``) capturados no momento da entrada.
    """

    __slots__ = (
        "lado",
        "entrada_timestamp",
        "entrada_preco",
        "stop_preco",
        "alvo_preco",
        "mfe_pontos",
        "mae_pontos",
        "vvg_positivo",
        "drift_pontos",
    )

    def __init__(
        self,
        *,
        lado: str,
        entrada_timestamp,
        entrada_preco: float,
        stop_preco: float,
        alvo_preco: float,
        vvg_positivo: bool,
        drift_pontos: float,
    ) -> None:
        self.lado = lado
        self.entrada_timestamp = entrada_timestamp
        self.entrada_preco = entrada_preco
        self.stop_preco = stop_preco
        self.alvo_preco = alvo_preco
        # Excursões em pontos (convenção do MetricasCalculator: mfe >= 0,
        # mae <= 0). Acumuladas barra-a-barra enquanto a posição vive.
        self.mfe_pontos = 0.0
        self.mae_pontos = 0.0
        # Metadados de auditoria (não cabem no Trade canônico).
        self.vvg_positivo = vvg_positivo
        self.drift_pontos = drift_pontos


class EstrategiaVvgLateSessionReversal:
    """Estratégia VVG Late-Session Reversal plugada no Walk-Forward.

    Implementa o protocolo :class:`caos.walk_forward.runner.Estrategia`
    (``treinar`` opcional, ``on_barra`` e ``finalizar`` obrigatórios) do
    Spec 2.

    Parameters
    ----------
    parametros:
        :class:`ParametrosVvg` opcional. Default usa
        :meth:`ParametrosVvg.PadraoConfigurado` (valores CONGELADOS na
        calibração da Tarefa 1).
    custos:
        :class:`CustosOperacionais` opcional, default
        :meth:`CustosOperacionais.topstep_mnq`. Guardado por compatibilidade
        com a assinatura do design; a fricção é de fato aplicada pelo
        ``BacktestRunner`` (ver docstring do módulo).
    """

    NOME: str = "EstrategiaVvgLateSessionReversal"

    def __init__(
        self,
        parametros: Optional[ParametrosVvg] = None,
        custos: Optional[CustosOperacionais] = None,
    ) -> None:
        self._params: ParametrosVvg = (
            parametros
            if parametros is not None
            else ParametrosVvg.PadraoConfigurado()
        )
        self._custos: CustosOperacionais = (
            custos if custos is not None else CustosOperacionais.topstep_mnq()
        )

        # Camadas reusadas (Tarefas 2 e 3).
        self._classificador: VvgClassifier = VvgClassifier(self._params)
        self._estado: EstadoVvg = EstadoVvg()

        # Saída do plugin.
        self._trades: List[Trade] = []
        #: Metadados por trade, alinhados por índice com ``self._trades``.
        self._metadados_trades: List[dict] = []

        # Motor de execução interno.
        self._posicao: Optional[_PosicaoAberta] = None
        #: Último resultado de classificação (debug/auditoria).
        self._ultimo_resultado: Optional[ResultadoClassificacao] = None

    # ------------------------------------------------------------------
    # Protocolo Estrategia (Spec 2)
    # ------------------------------------------------------------------

    def treinar(self, historico: pd.DataFrame) -> None:
        """Aquece o classificador com as barras de Treino — sem emitir trades.

        O Engine chama ``treinar`` uma vez por janela, com todas as barras
        de Treino. Resetamos o estado interno (determinismo por janela) e
        iteramos o histórico **somente pelo classificador**, para que o
        baseline rolling de volume já esteja preenchido quando o
        Periodo_Teste começar. A função pura :func:`decidir_acao` NÃO é
        chamada aqui — nenhum trade é aberto durante o treino.

        Observação importante: a **mesma** instância de classificador
        aquecida aqui é reusada em :meth:`on_barra`, preservando o estado
        rolling (baseline e ``close(D-1)``) na transição Treino→Teste.
        """
        # Reset por janela (determinismo — R6.2).
        self._classificador = VvgClassifier(self._params)
        self._estado = EstadoVvg()
        self._trades = []
        self._metadados_trades = []
        self._posicao = None
        self._ultimo_resultado = None

        # Aquecimento: só atualiza o estado rolling do classificador.
        for _, barra in historico.iterrows():
            self._classificador.on_barra(barra)

    def on_barra(self, barra_pd: pd.Series, contexto: BarrasTesteIterator) -> None:
        """Processa uma barra do Periodo_Teste.

        Ordem das etapas (precedência cronológica dentro da barra):

        a. Atualiza o classificador; se ele fechar a janela morning,
           propaga ``vvg_positivo`` para o estado.
        b. **Simulação de stop/target intrabar**: se há posição aberta
           (de uma barra anterior), atualiza excursões e verifica se o
           ``high``/``low`` desta barra tocou o stop ou o target. Se sim,
           fecha o trade naquele preço e registra a saída externa no
           estado. Isso roda ANTES de :func:`decidir_acao` porque um toque
           intrabar precede, no tempo, o ``close`` da barra (que é o
           gatilho do force-close de fim de sessão).
        c. Chama :func:`decidir_acao` (função pura) com o estado atual.
        d. Despacha a ação: ``LONG``/``SHORT`` abre posição; ``FECHAR``
           encerra por fim de sessão (R2.5); ``NADA`` não faz nada.
        """
        # (a) Classificador → vvg_positivo.
        resultado = self._classificador.on_barra(barra_pd)
        if resultado is not None:
            self._ultimo_resultado = resultado
            # Mutação direta antes da cópia interna de decidir_acao.
            self._estado.vvg_positivo = resultado.vvg_positivo

        barra = self._barra_de_series(barra_pd)

        # (b) Simulação de stop/target intrabar (somente com posição aberta).
        if self._posicao is not None:
            self._atualizar_excursoes(barra)
            saida = self._checar_stop_target(barra)
            if saida is not None:
                preco_saida, motivo = saida
                self._fechar_posicao(barra, preco_saida, motivo)
                # Mantém o estado da função pura coerente (1 trade/dia — R2.6).
                self._estado = registrar_saida_externa(self._estado)

        # (c) Decisão pura.
        acao, novo_estado = decidir_acao(barra, self._estado, self._params)
        self._estado = novo_estado

        # (d) Despacho da ação.
        if acao == AcaoVvg.LONG:
            self._abrir_posicao(barra, lado="long")
        elif acao == AcaoVvg.SHORT:
            self._abrir_posicao(barra, lado="short")
        elif acao == AcaoVvg.FECHAR:
            # Force-close de fim de sessão (15:50 NY): sai pelo close da barra.
            self._fechar_posicao(barra, barra.close, "encerramento-forcado")

    def finalizar(self) -> Sequence[Trade]:
        """Fecha posição pendente (defensivo) e devolve a lista de trades.

        Em operação normal o force-close de 15:50 NY (R2.5) já encerrou a
        posição antes do fim do Teste. Se ainda houver posição aberta
        (ex.: Teste terminou antes do horário de encerramento), fechamos
        pelo **preço de entrada** — evita PnL fictício, mesmo padrão do
        ``EstrategiaORB``.
        """
        if self._posicao is not None:
            p = self._posicao
            ts_aprox = p.entrada_timestamp + timedelta(seconds=1)
            barra_fech = Barra(
                timestamp=ts_aprox,
                open=p.entrada_preco,
                high=p.entrada_preco,
                low=p.entrada_preco,
                close=p.entrada_preco,
                volume=0.0,
            )
            self._fechar_posicao(barra_fech, p.entrada_preco, "encerramento-forcado")
        return list(self._trades)

    # ------------------------------------------------------------------
    # Motor de execução (helpers privados)
    # ------------------------------------------------------------------

    @staticmethod
    def _barra_de_series(barra_pd: pd.Series) -> Barra:
        """Converte a :class:`pandas.Series` da barra para :class:`Barra`.

        Normaliza o ``timestamp`` para UTC com offset 0 (exigência de
        ``vvg_logica._validar_barra``): naive é assumido UTC; tz-aware é
        convertido via ``astimezone(UTC)``.
        """
        ts = pd.Timestamp(barra_pd["timestamp"]).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        return Barra(
            timestamp=ts,
            open=float(barra_pd["open"]),
            high=float(barra_pd["high"]),
            low=float(barra_pd["low"]),
            close=float(barra_pd["close"]),
            volume=float(barra_pd["volume"]),
        )

    def _abrir_posicao(self, barra: Barra, *, lado: str) -> None:
        """Abre posição de 1 contrato e materializa stop/target em preço.

        - ``long``  → ``stop = entrada - stop_pontos``,
          ``alvo = entrada + target_pontos``.
        - ``short`` → ``stop = entrada + stop_pontos``,
          ``alvo = entrada - target_pontos``.

        ``drift_pontos`` (metadado) é lido do estado já atualizado por
        :func:`decidir_acao`: ``drift_close_referencia - open_dia_atual``.
        """
        entrada = barra.close
        if lado == "long":
            stop_preco = entrada - self._params.stop_pontos
            alvo_preco = entrada + self._params.target_pontos
        else:  # short
            stop_preco = entrada + self._params.stop_pontos
            alvo_preco = entrada - self._params.target_pontos

        drift_pontos = 0.0
        if (
            self._estado.drift_close_referencia is not None
            and self._estado.open_dia_atual is not None
        ):
            drift_pontos = (
                self._estado.drift_close_referencia - self._estado.open_dia_atual
            )

        self._posicao = _PosicaoAberta(
            lado=lado,
            entrada_timestamp=barra.timestamp,
            entrada_preco=entrada,
            stop_preco=stop_preco,
            alvo_preco=alvo_preco,
            vvg_positivo=self._estado.vvg_positivo,
            drift_pontos=drift_pontos,
        )

    def _checar_stop_target(self, barra: Barra) -> Optional[tuple[float, str]]:
        """Verifica se a barra tocou stop ou target; devolve ``(preco, motivo)``.

        **Ordem de prioridade (conservadora)**: o **stop é checado ANTES**
        do target. Se uma mesma barra de 1 minuto tocar os dois níveis
        (``low <= stop`` e ``high >= target`` para um long; análogo para
        short), assumimos o **pior caso = stop primeiro**. Como não há
        informação intrabar de qual extremo veio antes, a escolha
        conservadora evita superestimar o PnL. Na prática, com
        ``stop_pontos=472.25`` e ``target_pontos=944.25``, uma barra de
        minuto tocar ambos exigiria range > ~1416 pts (irrealista no MNQ),
        mas a regra é aplicada mesmo assim por robustez.

        Devolve ``None`` se nenhum nível foi tocado nesta barra.
        """
        p = self._posicao
        assert p is not None  # garantido pelo chamador
        if p.lado == "long":
            # Stop abaixo, target acima. Stop primeiro (conservador).
            if barra.low <= p.stop_preco:
                return (p.stop_preco, "stop")
            if barra.high >= p.alvo_preco:
                return (p.alvo_preco, "target")
        else:  # short
            # Stop acima, target abaixo. Stop primeiro (conservador).
            if barra.high >= p.stop_preco:
                return (p.stop_preco, "stop")
            if barra.low <= p.alvo_preco:
                return (p.alvo_preco, "target")
        return None

    def _atualizar_excursoes(self, barra: Barra) -> None:
        """Atualiza MFE/MAE da posição com a excursão da barra corrente."""
        p = self._posicao
        if p is None:
            return
        if p.lado == "long":
            mfe_potencial = barra.high - p.entrada_preco
            mae_potencial = barra.low - p.entrada_preco
        else:  # short
            mfe_potencial = p.entrada_preco - barra.low
            mae_potencial = p.entrada_preco - barra.high
        if mfe_potencial > p.mfe_pontos:
            p.mfe_pontos = mfe_potencial
        if mae_potencial < p.mae_pontos:
            p.mae_pontos = mae_potencial

    def _fechar_posicao(self, barra: Barra, preco_saida: float, motivo: str) -> None:
        """Fecha a posição aberta, emite o :class:`Trade` canônico e o metadado.

        ``motivo`` é um de ``"stop"`` / ``"target"`` / ``"encerramento-forcado"``
        e vai para :attr:`metadados_trades` (não para o Trade canônico, que
        proíbe campos extras).
        """
        p = self._posicao
        if p is None:
            return

        # Última atualização das excursões com a barra de fechamento.
        self._atualizar_excursoes(barra)

        # Trade exige saida_timestamp estritamente posterior à entrada.
        saida_ts = barra.timestamp
        if saida_ts <= p.entrada_timestamp:
            saida_ts = p.entrada_timestamp + timedelta(seconds=1)

        trade = Trade(
            entrada_timestamp=p.entrada_timestamp,
            saida_timestamp=saida_ts,
            entrada_preco=p.entrada_preco,
            saida_preco=preco_saida,
            lado=p.lado,  # type: ignore[arg-type]  # Literal["long","short"]
            contratos=1,  # MaxContratos conceitual = 1 (R4.1).
            mfe_pontos=p.mfe_pontos,
            mae_pontos=p.mae_pontos,
        )
        self._trades.append(trade)
        self._metadados_trades.append(
            {
                "vvg_positivo": p.vvg_positivo,
                "drift_pontos": p.drift_pontos,
                "motivo_saida": motivo,
            }
        )
        self._posicao = None

    # ------------------------------------------------------------------
    # Acessores úteis em testes / auditoria
    # ------------------------------------------------------------------

    @property
    def parametros(self) -> ParametrosVvg:
        return self._params

    @property
    def custos(self) -> CustosOperacionais:
        return self._custos

    @property
    def estado(self) -> EstadoVvg:
        return self._estado

    @property
    def trades(self) -> Sequence[Trade]:
        return tuple(self._trades)

    @property
    def metadados_trades(self) -> Sequence[dict]:
        """Metadados (``vvg_positivo``, ``drift_pontos``, ``motivo_saida``)
        alinhados por índice com :attr:`trades`."""
        return tuple(self._metadados_trades)


__all__ = ["EstrategiaVvgLateSessionReversal"]
