"""Normalizador de exports do NinjaTrader 8 (`.txt`) para CSV canônico.

Cobre o passo de importação de dados reais do MNQ. O NT8 exporta barras
históricas em arquivos texto com schema próprio:

- **Sem cabeçalho** — primeira linha já é dado.
- Separador **ponto-e-vírgula** (``;``).
- Timestamp:

  - granularidade ``minute`` → ``AAAAMMDD HHMMSS`` (ex.:
    ``20251215 030100``);
  - granularidade ``day``    → ``AAAAMMDD`` (ex.: ``20251215``).

- Colunas após o timestamp: ``open;high;low;close;volume`` (5 valores
  numéricos, separador ``;``).

O :mod:`caos.walk_forward.data_reader` (Spec 2) exige um schema
diferente: cabeçalho ``timestamp,open,high,low,close,volume``,
separador vírgula, timestamp ISO 8601 UTC, ordenação cronológica
estritamente crescente. Este módulo faz a tradução **fisicamente** —
gera ``*.csv`` no mesmo diretório do ``*.txt`` original. Os ``.txt``
ficam intactos para auditoria.

Convenções:

- **Naming dos `.txt`** segue formato NT8 nativo:
  ``MNQ <MM>-<YY>.<Serie>.txt`` (com espaço entre ``MNQ`` e o
  vencimento; ``Serie`` ∈ ``Ask``/``Bid``/``Last``). O diretório pai é
  ``dados/MNQ/MNQ_<MM>-<YY>/<minute|day>/`` (com underscore + hífen).
- **Naming dos `.csv`** gerados segue convenção interna do CAOS:
  ``<serie>.csv`` em minúsculas, no mesmo diretório.
- **Fuso horário do NT8** não é declarado no arquivo. Por padrão é
  tratado como ``America/Sao_Paulo`` (UTC-3 fixo desde fim do horário
  de verão brasileiro em 2019). Se a máquina do usuário estiver em
  outro fuso, basta passar ``fuso=`` para :func:`normalizar_arquivo` ou
  ``--fuso`` no CLI.
- **Idempotência:** se o ``*.csv`` destino existe e é mais recente que
  o ``*.txt`` origem, a normalização é pulada. Use ``forcar=True`` para
  reprocessar.

Sem dependência de pandas — leitura streaming linha-a-linha mantém o
custo de memória O(1) mesmo para arquivos grandes (>80k linhas).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from caos.walk_forward.fontes_dados import (
    GRANULARIDADES_VALIDAS,
    SERIES_VALIDAS,
    validar_contrato,
    validar_granularidade,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Fuso default assumido para timestamps exportados pelo NT8 quando o
#: usuário não declarou explicitamente. É o fuso de Brasília, que desde
#: 2019 é UTC-3 fixo (Brasil aboliu o horário de verão pelo Decreto
#: 9.772/2019). O usuário pode sobrescrever via ``--fuso``.
FUSO_DEFAULT_NT8: str = "America/Sao_Paulo"

#: Nome canônico esperado dos arquivos exportados pelo NT8 dentro de
#: ``dados/MNQ/<contrato>/<granularidade>/``. Captura ``MM``, ``YY`` e
#: ``Serie``. Aceita também a forma com underscore (``MNQ_03-26``) caso
#: o usuário renomeie manualmente — ambas convivem.
_REGEX_NOME_NT8 = re.compile(
    r"^MNQ[ _](?P<mes>\d{2})-(?P<ano>\d{2})\.(?P<serie>Ask|Bid|Last)\.txt$"
)

#: Cabeçalho canônico do CSV de saída (mesmo do
#: :data:`caos.walk_forward.data_reader.COLUNAS_OBRIGATORIAS`).
_CABECALHO_CSV = "timestamp,open,high,low,close,volume\n"

#: Formato do timestamp em arquivos ``minute/`` (com hora).
_FORMATO_TIMESTAMP_MINUTE = "%Y%m%d %H%M%S"

#: Formato do timestamp em arquivos ``day/`` (apenas data).
_FORMATO_TIMESTAMP_DAY = "%Y%m%d"


# ---------------------------------------------------------------------------
# Exceção tipificada
# ---------------------------------------------------------------------------


class NormalizadorNt8Error(RuntimeError):
    """Erro tipificado da normalização NT8 → CSV canônico.

    Categorias estáveis (verificadas pelos testes unitários):

    - ``arquivo-ausente``: ``arquivo_txt`` não existe ou não é regular.
    - ``fuso-invalido``: identificador IANA desconhecido na máquina.
    - ``nome-arquivo-fora-do-padrao``: nome do ``.txt`` não casa o
      regex de exports do NT8.
    - ``contrato-divergente``: o contrato embutido no nome do arquivo
      diverge do diretório pai (ex.: ``MNQ 06-25.Last.txt`` dentro de
      ``MNQ_03-26/``).
    - ``granularidade-divergente``: o diretório pai não é
      ``minute`` nem ``day``.
    - ``linha-malformada``: linha com número errado de campos.
    - ``timestamp-malformado``: timestamp não-parseável no formato
      esperado para a granularidade.
    - ``numero-invalido``: ``open|high|low|close|volume`` não numérico.
    - ``fora-de-ordem``: linhas não estritamente crescentes em
      ``timestamp``.
    - ``arquivo-vazio``: ``.txt`` sem nenhuma linha de dados.
    """

    def __init__(self, categoria: str, mensagem: str) -> None:
        self.categoria = categoria
        self.mensagem = mensagem
        super().__init__(f"{categoria}: {mensagem}")


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoNormalizacao:
    """Sumário de uma execução de :func:`normalizar_arquivo`.

    Atributos:

    - ``arquivo_txt``: path do ``.txt`` original (intocado).
    - ``arquivo_csv``: path do ``.csv`` gerado (ou que existia
      previamente quando ``pulado=True``).
    - ``linhas_lidas``: número de linhas de dados consumidas do ``.txt``.
    - ``linhas_escritas``: número de linhas de dados gravadas no
      ``.csv`` (excluindo cabeçalho). Igual a ``linhas_lidas`` em
      operações bem-sucedidas; ``0`` quando ``pulado=True``.
    - ``pulado``: ``True`` quando a normalização foi pulada por
      idempotência (``.csv`` mais novo que o ``.txt``). ``False`` em
      execuções efetivas e em ``forcar=True``.
    - ``tempo_ms``: duração da operação em milissegundos.
    - ``fuso``: nome IANA do fuso aplicado (apenas informativo —
      gravado no log/relatório).
    """

    arquivo_txt: Path
    arquivo_csv: Path
    linhas_lidas: int
    linhas_escritas: int
    pulado: bool
    tempo_ms: int
    fuso: str


# ---------------------------------------------------------------------------
# API pública: normalizar 1 arquivo
# ---------------------------------------------------------------------------


def normalizar_arquivo(
    *,
    arquivo_txt: Path,
    arquivo_csv: Path,
    granularidade: str,
    fuso: str = FUSO_DEFAULT_NT8,
    forcar: bool = False,
) -> ResultadoNormalizacao:
    """Normaliza um único ``.txt`` do NT8 em CSV canônico.

    Parameters
    ----------
    arquivo_txt:
        Path do arquivo de origem exportado pelo NT8.
    arquivo_csv:
        Path do arquivo CSV de saída (será criado/sobrescrito).
    granularidade:
        ``"minute"`` ou ``"day"`` — determina o formato de timestamp
        esperado e como construí-lo em UTC.
    fuso:
        Nome IANA do fuso a aplicar no parsing do timestamp local (ex.:
        ``"America/Sao_Paulo"``). Default = :data:`FUSO_DEFAULT_NT8`.
    forcar:
        Quando ``True``, sempre processa, mesmo que o ``.csv`` exista e
        seja mais recente que o ``.txt``. Default ``False``.

    Returns
    -------
    ResultadoNormalizacao
        Sumário da operação.

    Raises
    ------
    NormalizadorNt8Error
        Em qualquer das categorias documentadas em
        :class:`NormalizadorNt8Error`.
    """
    inicio = time.perf_counter()

    txt = Path(arquivo_txt)
    csv = Path(arquivo_csv)

    if not txt.is_file():
        raise NormalizadorNt8Error(
            "arquivo-ausente",
            f"arquivo de origem não encontrado: {txt}",
        )
    validar_granularidade(granularidade)
    if granularidade == "tick":
        # Por enquanto não suportamos tick — exports do NT8 para tick
        # exigem schema diferente (com bid/ask por tick). Quando o
        # usuário exportar, esta função ganhará uma implementação
        # dedicada.
        raise NormalizadorNt8Error(
            "granularidade-divergente",
            "granularidade 'tick' ainda não é suportada pelo normalizador",
        )

    # Valida fuso ANTES de tocar no arquivo — falha barata e descritiva.
    try:
        zona = ZoneInfo(fuso)
    except ZoneInfoNotFoundError as exc:
        raise NormalizadorNt8Error(
            "fuso-invalido",
            f"fuso IANA desconhecido: {fuso!r} ({exc})",
        ) from exc

    # Idempotência: pular se .csv existe e é mais novo que .txt.
    if (
        not forcar
        and csv.is_file()
        and csv.stat().st_mtime >= txt.stat().st_mtime
    ):
        tempo_ms = int((time.perf_counter() - inicio) * 1000)
        return ResultadoNormalizacao(
            arquivo_txt=txt,
            arquivo_csv=csv,
            linhas_lidas=0,
            linhas_escritas=0,
            pulado=True,
            tempo_ms=tempo_ms,
            fuso=fuso,
        )

    # Garante diretório de saída existente.
    csv.parent.mkdir(parents=True, exist_ok=True)

    # Strategy de parse de timestamp por granularidade.
    formato = (
        _FORMATO_TIMESTAMP_MINUTE
        if granularidade == "minute"
        else _FORMATO_TIMESTAMP_DAY
    )

    # Escrita atômica: grava em .csv.tmp e renomeia ao final. Evita
    # CSV parcialmente escrito se a normalização falhar no meio.
    csv_tmp = csv.with_suffix(csv.suffix + ".tmp")
    linhas_lidas = 0
    linhas_escritas = 0
    timestamp_anterior_utc: datetime | None = None

    try:
        with txt.open("r", encoding="utf-8", newline="") as origem, \
                csv_tmp.open("w", encoding="utf-8", newline="") as destino:
            destino.write(_CABECALHO_CSV)
            for numero_linha, bruto in _iter_linhas_uteis(origem):
                linhas_lidas += 1
                ts_utc, valores = _parsear_linha(
                    bruto=bruto,
                    formato=formato,
                    zona_local=zona,
                    arquivo=txt,
                    numero_linha=numero_linha,
                )
                if (
                    timestamp_anterior_utc is not None
                    and ts_utc <= timestamp_anterior_utc
                ):
                    raise NormalizadorNt8Error(
                        "fora-de-ordem",
                        (
                            f"linha {numero_linha} de {txt}: "
                            f"timestamp {ts_utc.isoformat()} <= "
                            f"{timestamp_anterior_utc.isoformat()} "
                            "(deve ser estritamente crescente)"
                        ),
                    )
                destino.write(_serializar_linha_csv(ts_utc, valores))
                linhas_escritas += 1
                timestamp_anterior_utc = ts_utc

        if linhas_escritas == 0:
            raise NormalizadorNt8Error(
                "arquivo-vazio",
                f"arquivo {txt} não contém nenhuma linha de dados",
            )

        # Rename atômico (Windows: substitui se existir).
        if csv.exists():
            csv.unlink()
        csv_tmp.replace(csv)
    except NormalizadorNt8Error:
        # Limpa o tmp parcialmente escrito antes de propagar.
        if csv_tmp.exists():
            try:
                csv_tmp.unlink()
            except OSError:
                pass
        raise
    except OSError as exc:
        if csv_tmp.exists():
            try:
                csv_tmp.unlink()
            except OSError:
                pass
        raise NormalizadorNt8Error(
            "linha-malformada",
            f"falha de I/O ao normalizar {txt}: {exc}",
        ) from exc

    tempo_ms = int((time.perf_counter() - inicio) * 1000)
    return ResultadoNormalizacao(
        arquivo_txt=txt,
        arquivo_csv=csv,
        linhas_lidas=linhas_lidas,
        linhas_escritas=linhas_escritas,
        pulado=False,
        tempo_ms=tempo_ms,
        fuso=fuso,
    )


# ---------------------------------------------------------------------------
# API pública: varredura recursiva
# ---------------------------------------------------------------------------


def detectar_destino_canonico(arquivo_txt: Path) -> Path:
    """Deriva o ``.csv`` canônico para um ``.txt`` exportado pelo NT8.

    Aplica o regex de naming NT8 ao nome do arquivo e devolve
    ``<dir>/<serie>.csv`` (em minúsculas) no mesmo diretório.

    Raises
    ------
    NormalizadorNt8Error
        ``nome-arquivo-fora-do-padrao`` se o nome não casa o regex.
    """
    txt = Path(arquivo_txt)
    match = _REGEX_NOME_NT8.match(txt.name)
    if match is None:
        raise NormalizadorNt8Error(
            "nome-arquivo-fora-do-padrao",
            (
                f"nome {txt.name!r} não casa o padrão de export do NT8 "
                "'MNQ <MM>-<YY>.<Ask|Bid|Last>.txt'"
            ),
        )
    serie = match.group("serie").lower()
    return txt.parent / f"{serie}.csv"


def varrer_e_normalizar(
    *,
    raiz_workspace: Path,
    fuso: str = FUSO_DEFAULT_NT8,
    forcar: bool = False,
) -> list[ResultadoNormalizacao]:
    """Varre ``dados/MNQ/<contrato>/<gran>/MNQ XX-YY.<Serie>.txt`` e
    normaliza todos os arquivos encontrados.

    Cada ``.txt`` produz um ``.csv`` no mesmo diretório. Arquivos cujo
    nome não casa o regex de export NT8 são silenciosamente ignorados
    (permite arquivos auxiliares no diretório sem disparar erro).

    Parameters
    ----------
    raiz_workspace:
        Raiz do workspace (contém ``dados/MNQ/``).
    fuso:
        Fuso IANA assumido para os timestamps locais do NT8.
    forcar:
        Reprocessa mesmo quando o ``.csv`` já é mais novo que o ``.txt``.

    Returns
    -------
    list[ResultadoNormalizacao]
        Um resultado por ``.txt`` processado, em ordem alfabética por
        path. Pode estar vazio se não houver nenhum ``.txt`` no
        diretório.

    Raises
    ------
    NormalizadorNt8Error
        Propagada se algum arquivo individual falhar (categorias
        documentadas em :class:`NormalizadorNt8Error`). A varredura
        para no primeiro erro — caller decide se quer reprocessar com
        ``forcar=True`` após corrigir.
    """
    raiz = Path(raiz_workspace).expanduser().resolve()
    if not raiz.is_dir():
        raise NormalizadorNt8Error(
            "arquivo-ausente",
            f"raiz_workspace {raiz_workspace!r} não é diretório existente",
        )
    raiz_mnq = raiz / "dados" / "MNQ"
    if not raiz_mnq.is_dir():
        return []

    resultados: list[ResultadoNormalizacao] = []
    for txt in sorted(raiz_mnq.rglob("*.txt"), key=lambda p: p.as_posix()):
        match = _REGEX_NOME_NT8.match(txt.name)
        if match is None:
            # Arquivo .txt fora do padrão (ex.: notas, README) — ignora.
            continue

        # Validação cruzada: contrato/granularidade do path × nome.
        diretorio_pai = txt.parent.name  # "minute" / "day"
        if diretorio_pai not in GRANULARIDADES_VALIDAS:
            raise NormalizadorNt8Error(
                "granularidade-divergente",
                (
                    f"diretório pai de {txt} é {diretorio_pai!r}; "
                    f"esperado um de {list(GRANULARIDADES_VALIDAS)}"
                ),
            )
        contrato_path = txt.parent.parent.name  # "MNQ_03-26"
        try:
            validar_contrato(contrato_path)
        except Exception as exc:
            raise NormalizadorNt8Error(
                "contrato-divergente",
                (
                    f"contrato extraído do path ({contrato_path!r}) "
                    f"para {txt} não é válido: {exc}"
                ),
            ) from exc
        contrato_nome = f"MNQ_{match.group('mes')}-{match.group('ano')}"
        if contrato_nome != contrato_path:
            raise NormalizadorNt8Error(
                "contrato-divergente",
                (
                    f"nome do arquivo {txt.name!r} indica contrato "
                    f"{contrato_nome!r} mas está em diretório "
                    f"{contrato_path!r}"
                ),
            )

        csv = detectar_destino_canonico(txt)
        resultado = normalizar_arquivo(
            arquivo_txt=txt,
            arquivo_csv=csv,
            granularidade=diretorio_pai,
            fuso=fuso,
            forcar=forcar,
        )
        resultados.append(resultado)

    return resultados


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _iter_linhas_uteis(arquivo) -> Iterator[tuple[int, str]]:
    """Yield ``(numero_linha_1based, conteudo_strip)`` para linhas não vazias."""
    for indice, bruto in enumerate(arquivo, start=1):
        conteudo = bruto.strip()
        if not conteudo:
            continue
        yield indice, conteudo


def _parsear_linha(
    *,
    bruto: str,
    formato: str,
    zona_local: ZoneInfo,
    arquivo: Path,
    numero_linha: int,
) -> tuple[datetime, tuple[str, str, str, str, str]]:
    """Parseia uma linha do export NT8 em ``(timestamp_utc, valores_str)``.

    Os valores numéricos são preservados como strings (sem perda de
    precisão); apenas validamos que são parseáveis como ``float``.
    """
    campos = bruto.split(";")
    if len(campos) != 6:
        raise NormalizadorNt8Error(
            "linha-malformada",
            (
                f"linha {numero_linha} de {arquivo}: esperados 6 campos "
                f"separados por ';', recebidos {len(campos)} ({bruto!r})"
            ),
        )
    timestamp_str, *valores = campos

    try:
        ingenuo = datetime.strptime(timestamp_str, formato)
    except ValueError as exc:
        raise NormalizadorNt8Error(
            "timestamp-malformado",
            (
                f"linha {numero_linha} de {arquivo}: timestamp "
                f"{timestamp_str!r} não casa o formato {formato!r} "
                f"({exc})"
            ),
        ) from exc

    # Valida que cada valor numérico é parseável (sem trocar
    # representação — preservamos o original para o CSV).
    for nome, valor in zip(
        ("open", "high", "low", "close", "volume"),
        valores,
    ):
        try:
            float(valor)
        except ValueError as exc:
            raise NormalizadorNt8Error(
                "numero-invalido",
                (
                    f"linha {numero_linha} de {arquivo}: campo {nome} "
                    f"com valor não-numérico {valor!r} ({exc})"
                ),
            ) from exc

    # Aplica fuso local e converte para UTC.
    ts_local = ingenuo.replace(tzinfo=zona_local)
    ts_utc = ts_local.astimezone(timezone.utc)
    return ts_utc, tuple(valores)  # type: ignore[return-value]


def _serializar_linha_csv(
    timestamp_utc: datetime,
    valores: tuple[str, str, str, str, str],
) -> str:
    """Formata a linha de saída no schema canônico.

    Timestamp emitido como ISO 8601 com sufixo ``Z`` (compatível com
    ``pandas.to_datetime(..., utc=True)``).
    """
    iso = timestamp_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{iso},{valores[0]},{valores[1]},{valores[2]},{valores[3]},{valores[4]}\n"


__all__ = [
    "FUSO_DEFAULT_NT8",
    "NormalizadorNt8Error",
    "ResultadoNormalizacao",
    "detectar_destino_canonico",
    "normalizar_arquivo",
    "varrer_e_normalizar",
]
