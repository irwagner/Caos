"""Skill_Data_Inspector — varredura de metadados em ``dados/MNQ/``.

Cobre o R11.6 do ``requirements.md`` e a linha correspondente da tabela em
``design.md`` seção 6 (Skill_Data_Inspector):

- Lê metadados de cada arquivo em ``dados/MNQ/`` **sem carregar o conteúdo
  inteiro** — usa streaming em chunks de 1 MB.
- Computa SHA-256 incrementalmente e conta linhas no mesmo passe.
- Para arquivos ``*.csv``, deriva ``periodo_inicial`` (timestamp da 1ª linha
  de dados, após o header) e ``periodo_final`` (timestamp da última linha).
- Aplica timeout de 60s por arquivo (R11.6) via :mod:`concurrent.futures`,
  igual ao padrão da Task 1 (sem ``signal``, que é Unix-only).
- Devolve :class:`EntradaManifesto` (Pydantic v2) validada — reusa o modelo
  já declarado em ``caos/models.py``.

Decisões de implementação relevantes:

- A varredura é recursiva e ordenada alfabeticamente por caminho relativo
  POSIX, garantindo determinismo do resultado (Property 9, Property 10).
- Arquivos cujo nome relativo é exatamente ``manifesto.json`` (na raiz de
  ``raiz_dados``) são ignorados — eles são o **destino** do manifesto, não
  uma entrada dele.
- A contagem de linhas é feita por bytes (``\\n`` no stream), não por
  ``str.splitlines()``: isso evita carregar o arquivo na memória. Quando
  o último byte não é ``\\n`` mas há conteúdo, contamos +1 para a linha
  parcial final (comportamento idêntico a ``wc -l`` ajustado).
- A heurística de header CSV é deliberadamente simples (≥2 campos e nenhum
  parsea como datetime): suficiente para o domínio MNQ deste Spec 1, e
  testável de forma exaustiva.
- Datas parseadas a partir de strings sem fuso são tratadas como **UTC**
  por convenção do projeto CAOS (regra ``instrumento-mnq``: cotações já
  vêm em CME timezone, mas registramos no manifesto sempre como UTC para
  estabilidade de hash).
"""

from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import io
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, Optional

from caos.models import EntradaManifesto

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Tamanho do chunk usado no stream do arquivo. 1 MB é compromisso entre
#: número de chamadas ao kernel e uso de memória — arquivos de 1 GB rodam
#: em ~1024 chunks, pequeno o suficiente para nunca consumir mais de 1 MB
#: residente além dos buffers internos do hashing.
_TAMANHO_CHUNK_BYTES: int = 1 * 1024 * 1024

#: Limite de bytes para a heurística "linha completa" usada na detecção do
#: ``periodo_final``. Linhas CSV reais do MNQ ficam bem abaixo disso (~80
#: bytes por barra de 1m); o limite serve apenas como salvaguarda contra
#: arquivos malformados sem ``\\n`` por gigabytes.
_LIMITE_LINHA_BYTES: int = 64 * 1024

#: Nome reservado do manifesto, ignorado em :meth:`SkillDataInspector.varrer_diretorio`.
_NOME_MANIFESTO: str = "manifesto.json"


CategoriaFalha = Literal["erro-de-leitura", "timeout", "formato-inesperado"]
"""Categorias públicas de falha de inspeção (auditáveis no manifesto)."""


# ---------------------------------------------------------------------------
# Exceções e modelos auxiliares
# ---------------------------------------------------------------------------


class SkillDataInspectorError(RuntimeError):
    """Falha tipificada de leitura/inspeção de um arquivo de ``dados/MNQ/``.

    Usada quando o caller exige falha rápida em vez de coletar a falha como
    item do :class:`ResultadoVarreduraDados`.
    """

    def __init__(self, caminho: Path, motivo: str) -> None:
        self.caminho = Path(caminho)
        self.motivo = motivo
        super().__init__(
            f"falha ao inspecionar {caminho}: {motivo}"
        )


@dataclass(frozen=True)
class FalhaInspecao:
    """Falha de inspeção de um arquivo individual durante a varredura.

    Mantida separada do :class:`SkillDataInspectorError` para permitir que
    :meth:`SkillDataInspector.varrer_diretorio` continue processando os
    demais arquivos mesmo após uma falha pontual (R11.6 — varredura é
    melhor-esforço).
    """

    caminho_relativo: str
    categoria: CategoriaFalha
    mensagem: str


@dataclass(frozen=True)
class ResultadoVarreduraDados:
    """Resultado de :meth:`SkillDataInspector.varrer_diretorio`."""

    entradas: list[EntradaManifesto] = field(default_factory=list)
    falhas: list[FalhaInspecao] = field(default_factory=list)

    @property
    def sucesso(self) -> bool:
        """``True`` se nenhuma falha foi registrada."""
        return not self.falhas


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillDataInspector:
    """Inspeciona arquivos de ``dados/MNQ/`` com streaming e timeout.

    Parameters
    ----------
    invocador:
        Identificador do agente que está chamando a Skill. Disponível para
        consumidores que queiram registrá-lo em auditoria de turnos —
        nesta Skill a auditoria fica ao nível do
        :class:`caos.data_manifest.DataManifestManager` (build/verify), não
        por arquivo.
    raiz_dados:
        Diretório alvo da varredura. Deve existir como diretório.
    """

    NOME: str = "Skill_Data_Inspector"
    TIMEOUT_POR_ARQUIVO_S: float = 60.0

    def __init__(
        self,
        *,
        invocador: Optional[str] = None,
        raiz_dados: Path,
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
        """Diretório raiz da varredura (resolvido absoluto)."""
        return self._raiz_dados

    @property
    def invocador(self) -> Optional[str]:
        """Agente invocador, se informado no construtor."""
        return self._invocador

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def inspecionar_arquivo(
        self,
        caminho: Path,
        *,
        instrumento: str = "MNQ",
    ) -> EntradaManifesto:
        """Inspeciona um único arquivo e devolve sua :class:`EntradaManifesto`.

        Aplica timeout de :attr:`TIMEOUT_POR_ARQUIVO_S` (60s) via
        :class:`concurrent.futures.ThreadPoolExecutor`. Em qualquer falha de
        leitura levanta :class:`SkillDataInspectorError`.

        Parameters
        ----------
        caminho:
            Caminho do arquivo. Pode ser absoluto ou relativo a
            :attr:`raiz_dados`.
        instrumento:
            Identificador do instrumento (default ``"MNQ"``, ver
            ``.kiro/steering/instrumento-mnq``).

        Returns
        -------
        EntradaManifesto
            Entrada validada via Pydantic, com ``nome_arquivo`` em forma
            POSIX relativa a :attr:`raiz_dados`.
        """
        caminho_resolvido = Path(caminho)
        if not caminho_resolvido.is_absolute():
            caminho_resolvido = (self._raiz_dados / caminho_resolvido).resolve()
        else:
            caminho_resolvido = caminho_resolvido.resolve()

        if not caminho_resolvido.is_file():
            raise SkillDataInspectorError(
                caminho_resolvido, "arquivo inexistente ou não-regular"
            )

        # Garantia de containment: o arquivo precisa estar sob raiz_dados,
        # caso contrário o caminho relativo POSIX exigido por
        # EntradaManifesto não faz sentido.
        try:
            relativo = caminho_resolvido.relative_to(self._raiz_dados)
        except ValueError as exc:
            raise SkillDataInspectorError(
                caminho_resolvido,
                f"arquivo fora de raiz_dados ({self._raiz_dados}): {exc}",
            ) from exc

        nome_arquivo_posix = relativo.as_posix()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
            future = exe.submit(
                _inspecionar_streaming,
                caminho_resolvido,
                nome_arquivo_posix,
                instrumento,
            )
            try:
                return future.result(timeout=self.TIMEOUT_POR_ARQUIVO_S)
            except concurrent.futures.TimeoutError as exc:
                raise SkillDataInspectorError(
                    caminho_resolvido,
                    (
                        "timeout excedido após "
                        f"{int(self.TIMEOUT_POR_ARQUIVO_S)}s"
                    ),
                ) from exc

    def varrer_diretorio(
        self, *, instrumento: str = "MNQ"
    ) -> ResultadoVarreduraDados:
        """Varre :attr:`raiz_dados` recursivamente em ordem alfabética.

        Ignora ``manifesto.json`` na raiz (ele é o **destino** do manifesto,
        não uma entrada). Falhas individuais não interrompem a varredura;
        elas são acumuladas em ``falhas`` no resultado.
        """
        entradas: list[EntradaManifesto] = []
        falhas: list[FalhaInspecao] = []

        for caminho in _iterar_arquivos(self._raiz_dados):
            relativo_posix = caminho.relative_to(self._raiz_dados).as_posix()
            if relativo_posix == _NOME_MANIFESTO:
                continue
            try:
                entrada = self.inspecionar_arquivo(
                    caminho, instrumento=instrumento
                )
            except SkillDataInspectorError as exc:
                # Mapeia o motivo textual para a categoria pública.
                categoria: CategoriaFalha
                motivo = exc.motivo
                if motivo.startswith("timeout"):
                    categoria = "timeout"
                elif "formato" in motivo:
                    categoria = "formato-inesperado"
                else:
                    categoria = "erro-de-leitura"
                falhas.append(
                    FalhaInspecao(
                        caminho_relativo=relativo_posix,
                        categoria=categoria,
                        mensagem=motivo,
                    )
                )
                continue
            entradas.append(entrada)

        return ResultadoVarreduraDados(entradas=entradas, falhas=falhas)


# ---------------------------------------------------------------------------
# Funções de baixo nível (módulo-level para serem importáveis em testes)
# ---------------------------------------------------------------------------


def _iterar_arquivos(raiz: Path) -> Iterable[Path]:
    """Itera recursivamente sobre arquivos de ``raiz`` em ordem alfabética.

    Ordem usa caminho relativo POSIX para ser estável entre execuções e
    independente de detalhes do sistema de arquivos (Windows ``rglob`` em
    geral devolve em ordem de inserção do diretório).
    """
    arquivos: list[Path] = []
    for caminho in raiz.rglob("*"):
        if caminho.is_file():
            arquivos.append(caminho)
    arquivos.sort(key=lambda p: p.relative_to(raiz).as_posix())
    return arquivos


def _inspecionar_streaming(
    caminho: Path,
    nome_arquivo_posix: str,
    instrumento: str,
) -> EntradaManifesto:
    """Lê o arquivo em chunks e devolve a :class:`EntradaManifesto` final.

    Esta função roda dentro do executor do :meth:`SkillDataInspector.inspecionar_arquivo`
    para que o timeout possa cortá-la sem usar ``signal`` (Unix-only).
    """
    try:
        stat = caminho.stat()
    except OSError as exc:
        raise SkillDataInspectorError(
            caminho, f"falha ao ler stat: {exc}"
        ) from exc

    tamanho_bytes = stat.st_size
    # mtime para datetime UTC truncado ao segundo.
    mtime_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(
        microsecond=0
    )

    sha256 = hashlib.sha256()
    num_linhas = 0
    ultimo_byte_eh_newline = True  # arquivo vazio conta 0 linhas
    teve_conteudo = False

    # Buffer da última linha completa lida (em bytes), para detectar o
    # ``periodo_final`` em CSVs sem ter que carregar o arquivo todo.
    ultima_linha_completa_bytes: bytes = b""
    # Buffer da linha "em construção" (ainda sem ``\\n``).
    linha_em_construcao = bytearray()

    eh_csv = caminho.suffix.lower() == ".csv"

    try:
        with caminho.open("rb") as f:
            while True:
                chunk = f.read(_TAMANHO_CHUNK_BYTES)
                if not chunk:
                    break
                teve_conteudo = True
                sha256.update(chunk)
                # Conta '\n' do chunk diretamente — Path.open('rb') preserva
                # bytes brutos, sem tradução CRLF→LF.
                num_linhas += chunk.count(b"\n")
                ultimo_byte_eh_newline = chunk.endswith(b"\n")

                if eh_csv:
                    # Mantém a última linha completa observada.
                    # Estratégia: concatena o chunk ao linha_em_construcao,
                    # particiona pelo último '\n', e pega a penúltima
                    # quebra como "última linha completa".
                    linha_em_construcao.extend(chunk)
                    if b"\n" in linha_em_construcao:
                        # Tudo até o último '\n' são linhas completas;
                        # mantemos a última delas.
                        # rsplit em b"\n", maxsplit=1 → [completas, resto]
                        completas, resto = linha_em_construcao.rsplit(
                            b"\n", 1
                        )
                        # Dentro de "completas" pode haver várias linhas;
                        # nos interessa a última (split por b"\n" preserva
                        # ordem).
                        if b"\n" in completas:
                            ultima_linha_completa_bytes = (
                                completas.rsplit(b"\n", 1)[1]
                            )
                        else:
                            ultima_linha_completa_bytes = completas
                        linha_em_construcao = bytearray(resto)
                        # Salvaguarda contra arquivos malformados (linhas
                        # gigantes sem '\n') que estourariam memória.
                        if len(linha_em_construcao) > _LIMITE_LINHA_BYTES:
                            # Trunca preservando o início (suficiente para
                            # parsing de header/datetime no início da linha).
                            del linha_em_construcao[_LIMITE_LINHA_BYTES:]
    except OSError as exc:
        raise SkillDataInspectorError(
            caminho, f"erro de leitura: {exc}"
        ) from exc

    # Última linha sem '\n' final ainda conta como linha (R: alinhamento
    # com `wc -l` modificado; CSVs podem terminar sem newline).
    if teve_conteudo and not ultimo_byte_eh_newline:
        num_linhas += 1
        # Em CSV, a linha em construção remanescente é a última linha real.
        if eh_csv and linha_em_construcao:
            ultima_linha_completa_bytes = bytes(linha_em_construcao)

    hash_hex = sha256.hexdigest()

    periodo_inicial: Optional[datetime] = None
    periodo_final: Optional[datetime] = None

    if eh_csv and num_linhas > 0:
        periodo_inicial, periodo_final = _derivar_periodos_csv(
            caminho,
            ultima_linha_completa_bytes,
        )

    try:
        return EntradaManifesto(
            nome_arquivo=nome_arquivo_posix,
            tamanho_bytes=tamanho_bytes,
            mtime=mtime_dt,
            num_linhas=num_linhas,
            hash_sha256=hash_hex,
            periodo_inicial=periodo_inicial,
            periodo_final=periodo_final,
            instrumento=instrumento,
        )
    except Exception as exc:  # pragma: no cover - falha de validação Pydantic
        raise SkillDataInspectorError(
            caminho, f"falha ao montar EntradaManifesto: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Heurísticas CSV
# ---------------------------------------------------------------------------


def _derivar_periodos_csv(
    caminho: Path,
    ultima_linha_completa_bytes: bytes,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Deriva ``(periodo_inicial, periodo_final)`` para um CSV.

    Estratégia:

    - Lê apenas as duas primeiras linhas para classificar header e parsear
      ``periodo_inicial``.
    - Usa ``ultima_linha_completa_bytes`` (já capturado no stream) para
      ``periodo_final``.

    Em qualquer falha de parsing, retorna ``(None, None)`` — período é
    informativo, não crítico para integridade (que é garantida pelo SHA-256).
    """
    try:
        with caminho.open("rb") as f:
            primeiras = f.read(_LIMITE_LINHA_BYTES * 4)
    except OSError:
        return (None, None)

    # Trabalhamos com texto decodificado para usar csv.reader, mas só sobre
    # as primeiras linhas — não o arquivo todo.
    texto = primeiras.decode("utf-8", errors="replace")
    leitor = csv.reader(io.StringIO(texto))
    try:
        primeira_linha = next(leitor)
    except StopIteration:
        return (None, None)

    if len(primeira_linha) < 2:
        return (None, None)

    # Heurística de header: se nenhum dos campos da primeira linha parsea
    # como datetime, considera header.
    primeira_linha_eh_header = not any(
        _tentar_parsear_datetime(c) is not None for c in primeira_linha
    )

    if primeira_linha_eh_header:
        try:
            primeira_dados = next(leitor)
        except StopIteration:
            # Apenas header, sem dados
            return (None, None)
    else:
        primeira_dados = primeira_linha

    if not primeira_dados:
        return (None, None)
    periodo_inicial = _tentar_parsear_datetime(primeira_dados[0])

    # Última linha: parsea o conteúdo bruto capturado no stream.
    periodo_final: Optional[datetime] = None
    if ultima_linha_completa_bytes:
        ultima_linha_str = ultima_linha_completa_bytes.decode(
            "utf-8", errors="replace"
        )
        # Pode ser igual a um header em arquivos de 1 linha de header + 1
        # de dados onde a "última linha completa" capturada é o próprio
        # header. Nesse caso usamos primeira_dados como fallback.
        leitor_ultimo = csv.reader(io.StringIO(ultima_linha_str))
        try:
            campos_ultimo = next(leitor_ultimo)
        except StopIteration:
            campos_ultimo = []
        if campos_ultimo:
            periodo_final = _tentar_parsear_datetime(campos_ultimo[0])

    if periodo_final is None and periodo_inicial is not None:
        # Arquivos com 1 linha de dados: inicial == final.
        periodo_final = periodo_inicial

    return (periodo_inicial, periodo_final)


def _tentar_parsear_datetime(valor: str) -> Optional[datetime]:
    """Tenta parsear ``valor`` em datetime UTC, devolvendo ``None`` se falhar.

    Formatos tentados em ordem:

    1. ``datetime.fromisoformat`` (cobre ``YYYY-MM-DDTHH:MM:SS`` e
       variações com offset).
    2. ``%Y-%m-%d %H:%M:%S``.
    3. ``%Y-%m-%d``.

    O resultado é normalizado para UTC: se ``tzinfo`` está ausente,
    assume UTC; se está presente com outro offset, converte para UTC.
    """
    if not valor:
        return None
    bruto = valor.strip()
    if not bruto:
        return None

    # Tentativa 1: ISO 8601.
    try:
        # ``fromisoformat`` em 3.11+ aceita 'Z' diretamente em algumas
        # versões; normalizamos por segurança.
        normalizado = bruto[:-1] + "+00:00" if bruto.endswith("Z") else bruto
        dt = datetime.fromisoformat(normalizado)
    except ValueError:
        dt = None

    if dt is None:
        # Tentativa 2: 'YYYY-MM-DD HH:MM:SS'.
        try:
            dt = datetime.strptime(bruto, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = None

    if dt is None:
        # Tentativa 3: 'YYYY-MM-DD'.
        try:
            dt = datetime.strptime(bruto, "%Y-%m-%d")
        except ValueError:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


__all__ = [
    "CategoriaFalha",
    "FalhaInspecao",
    "ResultadoVarreduraDados",
    "SkillDataInspector",
    "SkillDataInspectorError",
]
