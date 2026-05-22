"""Skill_Data_Reader — leitor de CSVs históricos do MNQ (Spec 2).

Cobre o R4 do ``requirements.md`` do Spec 2 e a linha correspondente da
tabela em ``design.md`` seção 4 (Components and Interfaces).

Responsabilidades:

- Carregar CSVs históricos de ``dados/MNQ/`` (por path explícito, lista
  de paths ou diretório recursivo).
- Validar schema rígido em cada CSV: colunas
  ``timestamp,open,high,low,close,volume`` exatamente nessa ordem,
  ``timestamp`` em ISO 8601 UTC, demais colunas numéricas.
- Validar ordenação cronológica estrita por ``timestamp`` dentro de
  cada arquivo e na concatenação final.
- Antes da **primeira** leitura de qualquer CSV, invocar
  :class:`SkillDataIntegrity` (Spec 1) contra ``manifesto.json`` e
  abortar se houver divergências (R4.1, R4.2).

Exceções tipificadas (nomes em pt-BR conforme design):

- :class:`ManifestoInvalidoError` — Skill_Data_Integrity rejeitou o
  manifesto (hash divergente, arquivo não-registrado, manifesto ausente
  ou malformado, timeout). Carrega ``arquivos_afetados``.
- :class:`SchemaInvalidoError` — coluna faltando, ordem de colunas
  errada, tipo numérico inválido, timestamp não-parseável ou sem fuso
  UTC. Carrega ``caminho`` e ``detalhes``.
- :class:`DadosForaDeOrdemError` — timestamps não estritamente crescentes
  dentro de um arquivo ou entre arquivos da mesma carga. Carrega
  ``caminho`` e o par de timestamps invertidos.

Decisões de implementação:

- Parsing via ``pandas.read_csv`` com ``dtype`` explícito: rápido e
  idiomático, e ``pandas`` já é dependência do projeto.
- Timestamps são **convertidos para UTC** após parsing e devolvidos no
  DataFrame como ``datetime64[ns, UTC]``.
- O método público :meth:`SkillDataReader.carregar` é o ponto de entrada
  esperado pelo ``BacktestRunner``; aceita ``Path`` (arquivo ou
  diretório) ou ``Iterable[Path]`` (lista explícita) e retorna um único
  DataFrame indexado-implicitamente por ordem cronológica.
- A integridade do manifesto é checada **uma única vez** por instância,
  na primeira chamada que precise de leitura. Chamadas subsequentes
  reusam o resultado em cache. Para forçar revalidação, instancie um
  novo :class:`SkillDataReader`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

import pandas as pd

from caos.skills.data_integrity import (
    SkillDataIntegrity,
    SkillDataIntegrityError,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Schema canônico do CSV consumido pelo Walk-Forward (design seção 3 — Schema
#: do CSV consumido em ``dados/MNQ/``). A ordem é exigida.
COLUNAS_OBRIGATORIAS: tuple[str, ...] = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

#: Colunas de preço/volume que devem ser numéricas (float). Excluímos
#: ``timestamp`` que é tratada à parte como datetime.
COLUNAS_NUMERICAS: tuple[str, ...] = ("open", "high", "low", "close", "volume")

#: Nome canônico do arquivo de manifesto dentro de ``raiz_dados`` (igual ao
#: declarado em :mod:`caos.data_manifest`). Importamos por nome para
#: evitar dependência circular sob carga de módulo.
_NOME_MANIFESTO: str = "manifesto.json"


# ---------------------------------------------------------------------------
# Exceções tipificadas (nomes em pt-BR conforme design)
# ---------------------------------------------------------------------------


class WalkForwardDataReaderError(RuntimeError):
    """Classe-base das exceções de :class:`SkillDataReader`.

    Útil para callers que queiram capturar qualquer falha do Reader em um
    único ``except`` sem se importar com a categoria.
    """


class ManifestoInvalidoError(WalkForwardDataReaderError):
    """Manifesto de dados está inválido (R4.2).

    Levantada quando :class:`SkillDataIntegrity` rejeita o ``manifesto.json``
    (hash divergente, arquivo não-registrado, manifesto ausente,
    manifesto malformado ou timeout de validação).

    Atributos:

    - ``categoria``: texto da categoria devolvida pela Skill_Data_Integrity
      (ex.: ``"manifesto-divergente"``, ``"arquivo-nao-registrado"``).
    - ``arquivos_afetados``: lista de caminhos POSIX afetados (R4.2 — o
      caller pode listá-los na mensagem de erro).
    """

    def __init__(
        self,
        *,
        categoria: str,
        mensagem: str,
        arquivos_afetados: list[str],
    ) -> None:
        self.categoria = categoria
        self.mensagem = mensagem
        # Cópia defensiva.
        self.arquivos_afetados: list[str] = list(arquivos_afetados)
        super().__init__(f"manifesto-invalido ({categoria}): {mensagem}")


class SchemaInvalidoError(WalkForwardDataReaderError):
    """CSV não respeita o schema canônico (R4 — schema CSV).

    Cobre:

    - coluna obrigatória faltando ou em ordem errada;
    - tipo numérico inválido em ``open|high|low|close|volume``;
    - ``timestamp`` não-parseável ou sem fuso UTC.
    """

    def __init__(self, caminho: Path, detalhes: str) -> None:
        self.caminho = Path(caminho)
        self.detalhes = detalhes
        super().__init__(
            f"schema-invalido em {self.caminho.as_posix()}: {detalhes}"
        )


class DadosForaDeOrdemError(WalkForwardDataReaderError):
    """Timestamps não estão em ordem estritamente crescente (R4 — schema CSV).

    Pode ser disparada tanto dentro de um único CSV quanto entre CSVs
    sucessivos da mesma carga. ``timestamp_anterior`` e
    ``timestamp_atual`` são os dois valores envolvidos na violação
    (em UTC, ISO 8601).
    """

    def __init__(
        self,
        caminho: Path,
        *,
        timestamp_anterior: pd.Timestamp,
        timestamp_atual: pd.Timestamp,
    ) -> None:
        self.caminho = Path(caminho)
        self.timestamp_anterior = timestamp_anterior
        self.timestamp_atual = timestamp_atual
        super().__init__(
            "dados-fora-de-ordem em "
            f"{self.caminho.as_posix()}: "
            f"timestamp {timestamp_atual.isoformat()} "
            f"<= {timestamp_anterior.isoformat()} (deve ser estritamente "
            "crescente)"
        )


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillDataReader:
    """Leitor de CSVs históricos do MNQ com schema rígido e integridade.

    Parameters
    ----------
    raiz_dados:
        Diretório raiz dos dados (ex.: ``dados/MNQ/``). Deve existir.
    caminho_manifesto:
        Override opcional do path do manifesto. Default:
        ``raiz_dados / "manifesto.json"``.
    invocador:
        Identificador do agente invocador (auditoria — propagado para a
        Skill_Data_Integrity).

    Notes
    -----
    O construtor não lê nenhum dado do disco além da validação de que
    ``raiz_dados`` é diretório. A integridade do manifesto é validada
    de forma preguiçosa na primeira chamada que precise de leitura
    (R4.1: invocada antes da **primeira** leitura).
    """

    NOME: str = "Skill_Data_Reader"

    def __init__(
        self,
        *,
        raiz_dados: Path,
        caminho_manifesto: Optional[Path] = None,
        invocador: Optional[str] = None,
    ) -> None:
        raiz_resolvida = Path(raiz_dados)
        if not raiz_resolvida.is_dir():
            raise ValueError(
                "raiz_dados deve apontar para um diretório existente; "
                f"recebido {raiz_dados!r}"
            )
        self._raiz_dados = raiz_resolvida
        self._caminho_manifesto = (
            Path(caminho_manifesto)
            if caminho_manifesto is not None
            else raiz_resolvida / _NOME_MANIFESTO
        )
        self._invocador = invocador
        # Flag de cache da validação de integridade. False ⇒ ainda não
        # validado nesta instância. True ⇒ já validado com sucesso.
        self._integridade_validada: bool = False

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def raiz_dados(self) -> Path:
        return self._raiz_dados

    @property
    def caminho_manifesto(self) -> Path:
        return self._caminho_manifesto

    @property
    def invocador(self) -> Optional[str]:
        return self._invocador

    @property
    def integridade_validada(self) -> bool:
        """``True`` se a Skill_Data_Integrity já foi invocada com sucesso."""
        return self._integridade_validada

    # ------------------------------------------------------------------
    # Integridade
    # ------------------------------------------------------------------

    def validar_integridade(self) -> None:
        """Invoca :class:`SkillDataIntegrity` contra ``manifesto.json``.

        Idempotente: a validação efetiva só acontece na primeira chamada;
        chamadas subsequentes são no-op enquanto ``integridade_validada``
        for ``True``.

        Raises
        ------
        ManifestoInvalidoError
            Quando o manifesto está ausente, malformado, divergente, ou
            algum arquivo presente em disco está fora do registro.
        """
        if self._integridade_validada:
            return

        if not self._caminho_manifesto.is_file():
            raise ManifestoInvalidoError(
                categoria="manifesto-ausente",
                mensagem=(
                    f"{self._caminho_manifesto} não existe. "
                    "Execute 'caos manifesto build' antes do walk-forward."
                ),
                arquivos_afetados=[],
            )

        skill = SkillDataIntegrity(
            invocador=self._invocador,
            raiz_dados=self._raiz_dados,
            caminho_manifesto=self._caminho_manifesto,
        )
        resultado = skill.validar()
        try:
            resultado.assert_ok()
        except SkillDataIntegrityError as exc:
            # Re-empacota com nome em pt-BR conforme design do Spec 2.
            raise ManifestoInvalidoError(
                categoria=exc.categoria,
                mensagem=exc.mensagem,
                arquivos_afetados=exc.arquivos_afetados,
            ) from exc

        self._integridade_validada = True

    # ------------------------------------------------------------------
    # Leitura — API pública principal
    # ------------------------------------------------------------------

    def carregar(
        self,
        fonte: Union[Path, str, Iterable[Path]],
    ) -> pd.DataFrame:
        """Carrega 1 ou N CSVs em um único :class:`~pandas.DataFrame`.

        Antes da primeira leitura, invoca :meth:`validar_integridade`
        (R4.1). Em seguida, resolve ``fonte`` em uma lista ordenada de
        paths e lê cada CSV via :meth:`ler_csv` (que aplica schema e
        ordenação cronológica). Por fim, concatena todos os DataFrames e
        valida a continuidade cronológica entre arquivos.

        Parameters
        ----------
        fonte:
            Pode ser:

            - ``Path`` para um arquivo CSV individual;
            - ``Path`` para um diretório (varredura recursiva, ordenada
              alfabeticamente por caminho relativo POSIX, considerando
              apenas ``*.csv``);
            - ``Iterable[Path]`` com a lista explícita de paths a
              concatenar (na ordem fornecida — o caller é responsável
              por ordená-la cronologicamente, mas o Reader também valida
              a ordenação dos timestamps resultantes).

        Returns
        -------
        pandas.DataFrame
            DataFrame com índice ``RangeIndex`` (0..N-1) e colunas
            ``timestamp,open,high,low,close,volume``. ``timestamp`` é
            ``datetime64[ns, UTC]``; demais colunas são ``float64``.

        Raises
        ------
        ManifestoInvalidoError
            Manifesto rejeitado pela Skill_Data_Integrity.
        SchemaInvalidoError
            Algum CSV não respeita o schema canônico.
        DadosForaDeOrdemError
            Timestamps fora de ordem dentro de um arquivo ou entre
            arquivos consecutivos.
        FileNotFoundError
            Algum dos paths fornecidos (ou descobertos no diretório) não
            existe ou não é arquivo regular.
        """
        # R4.1: invoca Skill_Data_Integrity ANTES da primeira leitura.
        self.validar_integridade()

        paths = self._resolver_fonte(fonte)
        if not paths:
            # Nada a carregar — devolve DataFrame vazio com schema correto.
            return _dataframe_vazio()

        dataframes: list[pd.DataFrame] = []
        for path in paths:
            dataframes.append(self.ler_csv(path))

        if len(dataframes) == 1:
            return dataframes[0].reset_index(drop=True)

        # Concatena preservando ordem dos arquivos. Em seguida valida
        # continuidade cronológica entre arquivos (último timestamp do
        # arquivo i deve ser estritamente menor que primeiro do i+1).
        for indice in range(len(dataframes) - 1):
            df_atual = dataframes[indice]
            df_proximo = dataframes[indice + 1]
            if df_atual.empty or df_proximo.empty:
                continue
            ts_anterior = df_atual["timestamp"].iloc[-1]
            ts_atual = df_proximo["timestamp"].iloc[0]
            if ts_atual <= ts_anterior:
                raise DadosForaDeOrdemError(
                    paths[indice + 1],
                    timestamp_anterior=ts_anterior,
                    timestamp_atual=ts_atual,
                )

        combinado = pd.concat(dataframes, ignore_index=True)
        return combinado

    # ------------------------------------------------------------------
    # Leitura — leitura de um arquivo individual
    # ------------------------------------------------------------------

    def ler_csv(self, caminho: Path) -> pd.DataFrame:
        """Lê e valida um único CSV, retornando-o como :class:`~pandas.DataFrame`.

        Não invoca :meth:`validar_integridade` por si só — cabe ao caller
        (normalmente :meth:`carregar`) garantir essa invocação. Esta
        separação permite testes unitários do schema sem precisar
        construir um manifesto.

        Parameters
        ----------
        caminho:
            Path do arquivo CSV. Pode ser absoluto ou relativo a
            :attr:`raiz_dados`.

        Returns
        -------
        pandas.DataFrame
            DataFrame com schema canônico (colunas e tipos descritos em
            :meth:`carregar`).

        Raises
        ------
        SchemaInvalidoError
            Coluna faltando, ordem de colunas errada, tipo inválido ou
            timestamp não-parseável.
        DadosForaDeOrdemError
            Timestamps não estritamente crescentes dentro do arquivo.
        FileNotFoundError
            Arquivo inexistente.
        """
        caminho_resolvido = Path(caminho)
        if not caminho_resolvido.is_absolute():
            caminho_resolvido = (self._raiz_dados / caminho_resolvido).resolve()
        else:
            caminho_resolvido = caminho_resolvido.resolve()

        if not caminho_resolvido.is_file():
            raise FileNotFoundError(
                f"arquivo de dados ausente: {caminho_resolvido}"
            )

        # Leitura com pandas. Lemos ``timestamp`` como string para
        # controlar o parsing de fuso horário e devolver mensagens de
        # erro mais descritivas que o default do pandas.
        try:
            df = pd.read_csv(
                caminho_resolvido,
                dtype={
                    "timestamp": "string",
                    "open": "float64",
                    "high": "float64",
                    "low": "float64",
                    "close": "float64",
                    "volume": "float64",
                },
            )
        except ValueError as exc:
            # ValueError do pandas captura conversão numérica falha
            # (R4 — tipos numéricos exigidos).
            raise SchemaInvalidoError(
                caminho_resolvido,
                f"falha ao parsear CSV: {exc}",
            ) from exc
        except pd.errors.ParserError as exc:
            raise SchemaInvalidoError(
                caminho_resolvido,
                f"CSV malformado: {exc}",
            ) from exc

        # Validação 1: schema (colunas exatas, na ordem exigida).
        colunas_obtidas = tuple(df.columns)
        if colunas_obtidas != COLUNAS_OBRIGATORIAS:
            faltando = [
                c for c in COLUNAS_OBRIGATORIAS if c not in colunas_obtidas
            ]
            extras = [
                c for c in colunas_obtidas if c not in COLUNAS_OBRIGATORIAS
            ]
            partes: list[str] = []
            if faltando:
                partes.append(f"colunas faltando: {faltando}")
            if extras:
                partes.append(f"colunas extras: {extras}")
            if not partes:
                partes.append(
                    "ordem de colunas incorreta — esperado "
                    f"{list(COLUNAS_OBRIGATORIAS)}, recebido "
                    f"{list(colunas_obtidas)}"
                )
            raise SchemaInvalidoError(
                caminho_resolvido,
                "; ".join(partes),
            )

        # Validação 2: timestamp parseável e em UTC.
        df = df.copy()
        try:
            timestamps = pd.to_datetime(
                df["timestamp"], utc=True, errors="raise"
            )
        except (ValueError, TypeError) as exc:
            raise SchemaInvalidoError(
                caminho_resolvido,
                (
                    "coluna 'timestamp' contém valores não-parseáveis como "
                    f"ISO 8601 UTC: {exc}"
                ),
            ) from exc
        if timestamps.isna().any():
            primeiros_invalidos = (
                df.loc[timestamps.isna(), "timestamp"].head(3).tolist()
            )
            raise SchemaInvalidoError(
                caminho_resolvido,
                (
                    "coluna 'timestamp' contém valores não-parseáveis "
                    f"(primeiros 3): {primeiros_invalidos}"
                ),
            )
        df["timestamp"] = timestamps

        # Validação 3: colunas numéricas devem ser float (sem NaN
        # silencioso). ``read_csv`` com ``dtype="float64"`` já tentou
        # converter; valores não numéricos viraram NaN ou ValueError.
        for coluna in COLUNAS_NUMERICAS:
            if df[coluna].isna().any():
                primeiros_invalidos = df.loc[df[coluna].isna()].head(3)
                raise SchemaInvalidoError(
                    caminho_resolvido,
                    (
                        f"coluna {coluna!r} contém valores não-numéricos ou "
                        "NaN; primeiras linhas problemáticas:\n"
                        f"{primeiros_invalidos.to_dict(orient='records')}"
                    ),
                )

        # Validação 4: timestamps estritamente crescentes (R4 — linhas
        # ordenadas cronologicamente).
        if len(df) >= 2:
            diffs = df["timestamp"].diff().iloc[1:]
            # Qualquer delta <= 0 indica violação. Procuramos a primeira
            # ocorrência para devolver mensagem actionable.
            mascara_violacao = diffs <= pd.Timedelta(0)
            if bool(mascara_violacao.any()):
                # Índice da primeira linha (no DataFrame original) que
                # quebra a ordem.
                indice_violacao = mascara_violacao.idxmax()
                raise DadosForaDeOrdemError(
                    caminho_resolvido,
                    timestamp_anterior=df["timestamp"].iloc[
                        df.index.get_loc(indice_violacao) - 1
                    ],
                    timestamp_atual=df["timestamp"].loc[indice_violacao],
                )

        return df

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _resolver_fonte(
        self,
        fonte: Union[Path, str, Iterable[Path]],
    ) -> list[Path]:
        """Resolve ``fonte`` em lista ordenada de paths absolutos de CSV.

        Regras:

        - ``Path``/``str`` apontando para arquivo: devolve ``[arquivo]``.
        - ``Path``/``str`` apontando para diretório: varredura recursiva
          de ``*.csv`` em ordem alfabética por caminho relativo POSIX.
        - ``Iterable[Path]``: lista usada na ordem fornecida (sem
          re-ordenação — o caller controla).
        """
        if isinstance(fonte, (str, Path)):
            caminho = Path(fonte)
            if not caminho.is_absolute():
                caminho = (self._raiz_dados / caminho).resolve()
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
            raise FileNotFoundError(
                f"fonte não encontrada (nem arquivo nem diretório): {caminho}"
            )

        # Iterable explícito de paths.
        paths: list[Path] = []
        for item in fonte:
            p = Path(item)
            if not p.is_absolute():
                p = (self._raiz_dados / p).resolve()
            else:
                p = p.resolve()
            paths.append(p)
        return paths


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------


def _dataframe_vazio() -> pd.DataFrame:
    """DataFrame vazio com o schema canônico, usado quando ``fonte`` está vazia."""
    return pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            "open": pd.Series(dtype="float64"),
            "high": pd.Series(dtype="float64"),
            "low": pd.Series(dtype="float64"),
            "close": pd.Series(dtype="float64"),
            "volume": pd.Series(dtype="float64"),
        }
    )


__all__ = [
    "COLUNAS_OBRIGATORIAS",
    "COLUNAS_NUMERICAS",
    "DadosForaDeOrdemError",
    "ManifestoInvalidoError",
    "SchemaInvalidoError",
    "SkillDataReader",
    "WalkForwardDataReaderError",
]
