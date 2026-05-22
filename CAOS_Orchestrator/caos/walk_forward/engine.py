"""WalkForwardEngine — orquestrador do pipeline Walk-Forward (Spec 2 — Task 6).

Cobre **R7** (reprodutibilidade) e **R10** (tratamento de falhas) do
``requirements.md`` do Spec 2 e a linha correspondente da tabela em
``design.md`` seção 4 (Components and Interfaces — ``WalkForwardEngine``).

Responsabilidades
-----------------
1. **Integridade** dos dados antes de qualquer leitura: invoca
   :class:`~caos.walk_forward.data_reader.SkillDataReader` que por sua
   vez invoca o ``Skill_Data_Integrity`` (Spec 1). Em
   :class:`~caos.walk_forward.data_reader.ManifestoInvalidoError` o
   pipeline aborta cedo retornando :class:`ResultadoWalkForward` com
   ``status="manifesto-invalido"`` e ``janelas=[]`` (R4.2).
2. **Geração de janelas** via
   :class:`~caos.walk_forward.janelas.JanelaGenerator` (R3).
3. **Execução por janela** via
   :class:`~caos.walk_forward.runner.BacktestRunner.executar`. Quando a
   estratégia produz trades no modelo rico
   (:class:`caos.walk_forward.metricas.Trade`), o Runner já delega o
   cálculo a :class:`~caos.walk_forward.metricas.MetricasCalculator`.
4. **Agregação** das métricas por mediana (canônica, R6.3) e média
   (auxiliar) usando apenas valores **finitos** (não-``None`` e não-NaN).
5. **Aborto por falhas** quando a taxa de janelas com
   ``status="falha"`` é estritamente maior que 30% (R10.2). Nesse caso o
   ``ResultadoWalkForward`` é devolvido com
   ``status="abortado-por-falhas"``.
6. **Cabeçalho de auditoria**:
   - ``manifesto_hash``: SHA-256 hex agregado dos arquivos lidos. O
     :class:`SkillDataReader` valida o manifesto, mas não devolve o
     hash agregado por chamada — o engine recalcula o agregado a
     partir do conteúdo dos CSVs efetivamente carregados (estratégia
     simples e estável: SHA-256 dos bytes UTF-8 dos arquivos
     concatenados em ordem alfabética, formato canônico).
   - ``versoes_dependencias``: versões de :mod:`pandas` e :mod:`numpy`
     no ambiente de execução (R7.2).

Reconciliação dos modelos de Trade
----------------------------------
Estratégias plugáveis devem retornar :class:`caos.walk_forward.metricas.Trade`
em ``finalizar()`` para que o Engine possa calcular métricas completas
por janela (Sharpe, Calmar, drawdown, etc.). O modelo
:class:`caos.walk_forward.runner.Trade` permanece exposto para
compatibilidade com testes da Task 4, mas não é o modelo canônico do
pipeline. Decisão registrada também na docstring do
:mod:`caos.walk_forward.runner`.

Interface pública
-----------------
- :class:`WalkForwardEngine` — fachada com método único
  :meth:`WalkForwardEngine.executar`.
- :data:`FonteDados` — alias de tipo do parâmetro ``fonte_dados``.

Convenções: pt-BR (R3.2 do Spec 1), Pydantic v2, Windows + cmd.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import numpy
import pandas

from caos.walk_forward.data_reader import (
    ManifestoInvalidoError,
    SkillDataReader,
)
from caos.walk_forward.janelas import JanelaGenerator
from caos.walk_forward.metricas import MetricasCalculator
from caos.walk_forward.models import (
    ConfiguracaoWalkForward,
    ResultadoJanela,
    ResultadoWalkForward,
)
from caos.walk_forward.runner import BacktestRunner, Estrategia

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Limiar de aborto por taxa de falhas (R10.2). Estritamente maior.
LIMIAR_TAXA_FALHAS: float = 0.30

#: Métricas agregáveis numericamente (R6.3). ``drawdown_maximo_dias`` é
#: agregado também — é inteiro mas a mediana/média de inteiros vira float.
METRICAS_AGREGAVEIS: tuple[str, ...] = (
    "sharpe_anualizado",
    "calmar",
    "drawdown_maximo_percentual",
    "drawdown_maximo_dias",
    "win_rate",
    "payoff_medio",
    "mfe_medio",
    "mae_medio",
    "numero_trades",
    "pnl_total",
)

#: Tipo união do parâmetro ``fonte_dados`` aceito pelo engine.
FonteDados = Union[Path, str, Iterable[Path]]


# ---------------------------------------------------------------------------
# WalkForwardEngine
# ---------------------------------------------------------------------------


class WalkForwardEngine:
    """Orquestrador do pipeline Walk-Forward (R7, R10).

    Parameters
    ----------
    raiz_dados:
        Diretório raiz dos dados (``dados/MNQ/``). Deve existir.
    invocador:
        Identificador opcional do agente invocador (auditoria — propagado
        ao :class:`SkillDataReader`).
    """

    NOME: str = "WalkForwardEngine"

    def __init__(
        self,
        *,
        raiz_dados: Path,
        invocador: Optional[str] = None,
    ) -> None:
        raiz_resolvida = Path(raiz_dados)
        if not raiz_resolvida.is_dir():
            raise ValueError(
                "raiz_dados deve apontar para um diretório existente; "
                f"recebido {raiz_dados!r}"
            )
        self._raiz_dados = raiz_resolvida
        self._invocador = invocador

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def raiz_dados(self) -> Path:
        return self._raiz_dados

    @property
    def invocador(self) -> Optional[str]:
        return self._invocador

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def executar(
        self,
        estrategia: Estrategia,
        configuracao: ConfiguracaoWalkForward,
        fonte_dados: FonteDados,
        identificador: str,
    ) -> ResultadoWalkForward:
        """Executa o pipeline completo e devolve :class:`ResultadoWalkForward`.

        Fluxo (R10 — falhas individuais não invalidam o WF inteiro):

        1. Constrói :class:`SkillDataReader` e tenta carregar
           ``fonte_dados``. Em :class:`ManifestoInvalidoError`, devolve
           :class:`ResultadoWalkForward` com
           ``status="manifesto-invalido"`` e ``janelas=[]`` (R4.2).
        2. Calcula ``manifesto_hash`` a partir dos paths efetivamente
           lidos.
        3. Gera as janelas via :class:`JanelaGenerator`. Se a lista
           retornar vazia (dados insuficientes), devolve
           :class:`ResultadoWalkForward` com ``status="concluido"``,
           ``janelas=[]``? Não — o model exige ``janelas != []`` quando
           ``status != "manifesto-invalido"``. Por isso, dados
           insuficientes são tratados como **erro de configuração** e
           levantam :class:`ValueError` (caller corrige a config).
        4. Para cada janela, invoca :meth:`BacktestRunner.executar`.
           Eventuais exceções de execução já são capturadas internamente
           pelo Runner e devolvidas como
           :class:`ResultadoJanela` com ``status="falha"`` (R10.1). A
           Engine apenas coleta os resultados.
        5. Se a taxa de janelas com ``status="falha"`` for **estritamente
           maior** que 30%, devolve com ``status="abortado-por-falhas"``
           (R10.2).
        6. Caso contrário, agrega métricas por mediana e média e devolve
           com ``status="concluido"`` (R6.3, R10).

        Parameters
        ----------
        estrategia:
            Implementação compatível com :class:`Estrategia`.
        configuracao:
            :class:`ConfiguracaoWalkForward` validada.
        fonte_dados:
            Path para arquivo único, diretório (varredura recursiva de
            ``*.csv``) ou lista explícita de paths. Mesma semântica de
            :meth:`SkillDataReader.carregar`.
        identificador:
            Identificador da execução no formato ``AAAA-MM-DD-NN`` (R1.3,
            R3.3). O Engine apenas valida via Pydantic (regex no model).
        """
        nome_estrategia = _resolver_nome_estrategia(estrategia)
        versoes = _versoes_dependencias()

        reader = SkillDataReader(
            raiz_dados=self._raiz_dados,
            invocador=self._invocador,
        )

        # ------------------------------------------------------------------
        # Fase 1 — integridade + leitura.
        # ------------------------------------------------------------------
        try:
            barras = reader.carregar(fonte_dados)
        except ManifestoInvalidoError:
            # R4.2 — aborta cedo com status "manifesto-invalido".
            return ResultadoWalkForward(
                identificador=identificador,
                estrategia=nome_estrategia,
                configuracao=configuracao,
                manifesto_hash=_HASH_PLACEHOLDER,
                janelas=[],
                agregado_mediana={},
                agregado_media={},
                versoes_dependencias=versoes,
                status="manifesto-invalido",
            )

        # Hash agregado dos CSVs efetivamente lidos (R4.3).
        paths_lidos = _resolver_paths_lidos(self._raiz_dados, fonte_dados)
        manifesto_hash = _hash_agregado_arquivos(paths_lidos)

        # ------------------------------------------------------------------
        # Fase 2 — geração de janelas (R3).
        # ------------------------------------------------------------------
        janelas = JanelaGenerator.gerar(barras, configuracao, manifesto_hash)
        if not janelas:
            # ResultadoWalkForward exige >=1 janela quando status != "manifesto-invalido".
            # Tratamos "dados insuficientes" como erro de configuração.
            raise ValueError(
                "JanelaGenerator não produziu janelas para os dados "
                "fornecidos: histórico insuficiente para "
                f"tamanho_treino_dias_uteis={configuracao.tamanho_treino_dias_uteis} + "
                f"tamanho_teste_dias_uteis={configuracao.tamanho_teste_dias_uteis} "
                "(R3.2)"
            )

        # ------------------------------------------------------------------
        # Fase 3 — execução por janela (R10.1 — falhas individuais OK).
        # ------------------------------------------------------------------
        resultados: list[ResultadoJanela] = []
        for janela in janelas:
            # Estratégias plugáveis costumam guardar estado interno entre
            # ``treinar`` e ``finalizar``. Para isolar janelas, reusamos
            # a mesma instância — a estratégia é responsável por resetar
            # estado em ``treinar``. Caso o caller precise de instâncias
            # frescas, pode passar uma factory ao invés de uma instância.
            resultado = BacktestRunner.executar(
                janela=janela,
                dados=barras,
                estrategia=estrategia,
                configuracao=configuracao,
            )
            resultados.append(resultado)

        # ------------------------------------------------------------------
        # Fase 4 — taxa de falhas (R10.2).
        # ------------------------------------------------------------------
        total = len(resultados)
        falhas = sum(1 for r in resultados if r.status == "falha")
        taxa = falhas / total if total > 0 else 0.0
        if taxa > LIMIAR_TAXA_FALHAS:
            return ResultadoWalkForward(
                identificador=identificador,
                estrategia=nome_estrategia,
                configuracao=configuracao,
                manifesto_hash=manifesto_hash,
                janelas=resultados,
                agregado_mediana={},
                agregado_media={},
                versoes_dependencias=versoes,
                status="abortado-por-falhas",
            )

        # ------------------------------------------------------------------
        # Fase 5 — agregação (R6.3 — mediana canônica, média auxiliar).
        # ------------------------------------------------------------------
        agregado_mediana = _agregar(resultados, statistics.median)
        agregado_media = _agregar(resultados, statistics.fmean)

        return ResultadoWalkForward(
            identificador=identificador,
            estrategia=nome_estrategia,
            configuracao=configuracao,
            manifesto_hash=manifesto_hash,
            janelas=resultados,
            agregado_mediana=agregado_mediana,
            agregado_media=agregado_media,
            versoes_dependencias=versoes,
            status="concluido",
        )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


#: Hash placeholder usado quando o manifesto é inválido (R4.2). 64 zeros.
_HASH_PLACEHOLDER: str = "0" * 64


def _resolver_nome_estrategia(estrategia: Any) -> str:
    """Mesma heurística do Runner — extrai nome curto da estratégia."""
    for atributo in ("nome", "NOME"):
        valor = getattr(estrategia, atributo, None)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()[:200]
    return type(estrategia).__name__[:200]


def _versoes_dependencias() -> dict[str, str]:
    """Coleta versões de pandas, numpy e Python (R7.2)."""
    return {
        "pandas": str(pandas.__version__),
        "numpy": str(numpy.__version__),
        "python": ".".join(str(p) for p in sys.version_info[:3]),
    }


def _resolver_paths_lidos(
    raiz_dados: Path,
    fonte: FonteDados,
) -> list[Path]:
    """Resolve ``fonte`` na lista ordenada de paths absolutos de CSV.

    Réplica da lógica privada de :class:`SkillDataReader._resolver_fonte`
    para evitar dependência de método com underscore — a Task 6
    precisa dos paths para calcular ``manifesto_hash`` de forma
    determinística e auditável.
    """
    if isinstance(fonte, (str, Path)):
        caminho = Path(fonte)
        if not caminho.is_absolute():
            caminho = (raiz_dados / caminho).resolve()
        else:
            caminho = caminho.resolve()
        if caminho.is_file():
            return [caminho]
        if caminho.is_dir():
            csvs = sorted(
                caminho.rglob("*.csv"),
                key=lambda p: p.relative_to(caminho).as_posix(),
            )
            return [p.resolve() for p in csvs]
        return []

    paths: list[Path] = []
    for item in fonte:
        p = Path(item)
        if not p.is_absolute():
            p = (raiz_dados / p).resolve()
        else:
            p = p.resolve()
        paths.append(p)
    return paths


def _hash_agregado_arquivos(paths: Iterable[Path]) -> str:
    """SHA-256 hex agregado dos CSVs lidos (R4.3).

    Para cada path, alimenta o digest com:

    - O nome (POSIX) do arquivo seguido de ``\\n``;
    - O conteúdo do arquivo lido em modo binário, em chunks de 1 MB;
    - Um separador ``\\x00``.

    Paths são ordenados alfabeticamente (POSIX) antes do digest para
    garantir determinismo (R7.1). Lista vazia produz o hash do
    separador apenas, que ainda é um SHA-256 válido — porém o caller
    raramente invocará com lista vazia em fluxo normal.
    """
    digest = hashlib.sha256()
    paths_ordenados = sorted(paths, key=lambda p: p.as_posix())
    for path in paths_ordenados:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\n")
        if path.is_file():
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        digest.update(b"\x00")
    return digest.hexdigest()


def _agregar(
    resultados: list[ResultadoJanela],
    agregador,
) -> dict[str, float]:
    """Aplica ``agregador`` (median/fmean) sobre cada métrica agregável.

    Apenas valores **finitos** (não-``None`` e não-NaN) entram no
    cálculo. Métricas que não tiverem ao menos 1 valor finito são
    omitidas do dicionário de saída — assim, em uma execução com 100%
    de janelas ``sem-trades`` o agregado fica vazio em vez de quebrar
    com ``StatisticsError``.
    """
    agregado: dict[str, float] = {}
    for nome in METRICAS_AGREGAVEIS:
        valores: list[float] = []
        for r in resultados:
            valor = getattr(r, nome, None)
            if valor is None:
                continue
            try:
                valor_float = float(valor)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(valor_float):
                continue
            valores.append(valor_float)
        if not valores:
            continue
        agregado[nome] = float(agregador(valores))
    return agregado


__all__ = [
    "FonteDados",
    "LIMIAR_TAXA_FALHAS",
    "METRICAS_AGREGAVEIS",
    "WalkForwardEngine",
]
