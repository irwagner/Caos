"""Skill_Data_Integrity — verificação de integridade contra ``manifesto.json``.

Cobre o R11.7 do ``requirements.md`` (parte de dados) e os requisitos R15.4,
R15.5 e R15.6, além da Property 10 (Data Manifest Integrity) do ``design.md``.

Resumo do contrato:

- Recebe a raiz de dados (``dados/MNQ/``) e o caminho do manifesto.
- Para cada entrada do manifesto, recomputa o SHA-256 do arquivo no disco
  via streaming e compara com o registrado.
- Para cada arquivo presente em disco mas ausente do manifesto, marca
  como ``nao-registrado``.
- Para cada arquivo registrado mas ausente em disco, marca como
  ``arquivo-ausente``.
- Aplica timeout total de 120 segundos via ``time.monotonic()`` (não usa
  thread, pois o stream é serial — a checagem do deadline acontece entre
  arquivos).
- O método :meth:`SkillDataIntegrity.validar` **não** levanta exceção em
  divergências: devolve um :class:`ResultadoIntegridade` para inspeção
  programática. O caller que precisar abortar leitura (R15.5) deve chamar
  :meth:`ResultadoIntegridade.assert_ok`.

Decisões de implementação:

- O hash incremental usa ``hashlib.sha256`` em chunks de 1 MB (mesma
  constante do ``data_inspector``). É serializável e determinístico.
- Manifesto malformado (JSON inválido ou schema fora do esperado) é
  reportado em ``erro_global`` em vez de propagar ``json.JSONDecodeError``,
  para que o caller sempre receba um :class:`ResultadoIntegridade`. Quando
  o caller chama :meth:`ResultadoIntegridade.assert_ok`, a exceção
  tipificada :class:`SkillDataIntegrityError` é levantada com a categoria
  correta.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Optional

from caos.models import EntradaManifesto

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Tamanho do chunk no streaming de hash. Mesma constante do data_inspector
#: para manter performance comparável e simplificar mental model.
_TAMANHO_CHUNK_BYTES: int = 1 * 1024 * 1024

#: Nome reservado do manifesto, ignorado no scan de "nao-registrados".
_NOME_MANIFESTO: str = "manifesto.json"


CategoriaErroIntegridade = Literal[
    "manifesto-divergente",
    "arquivo-nao-registrado",
    "manifesto-ausente",
    "manifesto-malformado",
    "timeout",
]
"""Categorias públicas de erro tipificado retornado por :class:`SkillDataIntegrityError`."""


MotivoDivergencia = Literal["hash-divergente", "arquivo-ausente"]
"""Motivos por que uma :class:`Divergencia` foi registrada."""


# ---------------------------------------------------------------------------
# Modelos públicos de retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Divergencia:
    """Diferença entre uma entrada do manifesto e o estado em disco.

    ``hash_atual`` é ``None`` quando o arquivo está ausente em disco
    (motivo ``arquivo-ausente``).
    """

    nome_arquivo: str
    hash_esperado: str
    hash_atual: Optional[str]
    motivo: MotivoDivergencia


@dataclass(frozen=True)
class ResultadoIntegridade:
    """Resultado de :meth:`SkillDataIntegrity.validar`.

    Atributos:

    ok:
        ``True`` se o manifesto está coerente com o disco e não há arquivos
        sem registro. Equivalente a
        ``not (divergencias or nao_registrados or arquivos_ausentes or erro_global)``.
    divergencias:
        Lista de divergências de hash encontradas.
    nao_registrados:
        Caminhos relativos POSIX de arquivos presentes em disco mas
        ausentes do manifesto.
    arquivos_ausentes:
        Caminhos relativos POSIX de arquivos registrados no manifesto mas
        ausentes em disco. Note que estes também aparecem em
        :attr:`divergencias` com motivo ``arquivo-ausente`` — duplicação é
        intencional, pois callers diferentes preferem diferentes recortes.
    erro_global:
        Mensagem descrevendo timeout, manifesto ausente ou manifesto
        malformado. ``None`` quando a validação ocorreu sem erro de fluxo.
    """

    ok: bool
    divergencias: list[Divergencia] = field(default_factory=list)
    nao_registrados: list[str] = field(default_factory=list)
    arquivos_ausentes: list[str] = field(default_factory=list)
    erro_global: Optional[str] = None

    def assert_ok(self) -> None:
        """Levanta :class:`SkillDataIntegrityError` quando ``ok`` é ``False``.

        Útil para callers que precisam abortar leitura imediatamente em
        qualquer divergência (R15.5).
        """
        if self.ok:
            return

        if self.erro_global is not None:
            # erro_global tem mensagens prefixadas conforme a categoria.
            categoria: CategoriaErroIntegridade
            if self.erro_global.startswith("manifesto-ausente"):
                categoria = "manifesto-ausente"
            elif self.erro_global.startswith("manifesto-malformado"):
                categoria = "manifesto-malformado"
            elif self.erro_global.startswith("timeout"):
                categoria = "timeout"
            else:
                # Defensivo: trata como malformado.
                categoria = "manifesto-malformado"
            raise SkillDataIntegrityError(
                categoria=categoria,
                mensagem=self.erro_global,
                arquivos_afetados=[],
            )

        if self.divergencias:
            afetados = [d.nome_arquivo for d in self.divergencias]
            raise SkillDataIntegrityError(
                categoria="manifesto-divergente",
                mensagem=(
                    f"manifesto-divergente: {len(afetados)} divergência(s) "
                    f"detectada(s)"
                ),
                arquivos_afetados=afetados,
            )

        if self.nao_registrados:
            raise SkillDataIntegrityError(
                categoria="arquivo-nao-registrado",
                mensagem=(
                    f"arquivo-nao-registrado: {len(self.nao_registrados)} "
                    "arquivo(s) presentes em disco fora do manifesto"
                ),
                arquivos_afetados=list(self.nao_registrados),
            )

        # Defensivo: se ok é False mas as listas estão vazias, ainda assim
        # levanta um erro genérico para preservar o contrato de assert_ok.
        raise SkillDataIntegrityError(  # pragma: no cover
            categoria="manifesto-divergente",
            mensagem="estado inválido: ok=False sem divergências detectáveis",
            arquivos_afetados=[],
        )


# ---------------------------------------------------------------------------
# Exceção tipificada
# ---------------------------------------------------------------------------


class SkillDataIntegrityError(RuntimeError):
    """Falha tipificada de integridade do manifesto (R15.5).

    Contém a ``categoria`` (controlada por :data:`CategoriaErroIntegridade`)
    e a lista de ``arquivos_afetados`` para que o caller possa decidir o
    quão restritiva deve ser sua resposta.
    """

    def __init__(
        self,
        *,
        categoria: CategoriaErroIntegridade,
        mensagem: str,
        arquivos_afetados: list[str],
    ) -> None:
        self.categoria = categoria
        self.mensagem = mensagem
        # Cópia para evitar mutação acidental.
        self.arquivos_afetados: list[str] = list(arquivos_afetados)
        super().__init__(f"{categoria}: {mensagem}")


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillDataIntegrity:
    """Recomputa hashes de ``raiz_dados`` e compara com ``manifesto.json``.

    Parameters
    ----------
    invocador:
        Identificador do agente invocador (auditoria — ver
        ``data_manifest.DataManifestManager`` que envolve esta Skill).
    raiz_dados:
        Diretório alvo da varredura.
    caminho_manifesto:
        Arquivo JSON do manifesto. Deve existir.
    """

    NOME: str = "Skill_Data_Integrity"
    TIMEOUT_TOTAL_S: float = 120.0

    def __init__(
        self,
        *,
        invocador: Optional[str] = None,
        raiz_dados: Path,
        caminho_manifesto: Path,
    ) -> None:
        raiz_resolvida = Path(raiz_dados)
        if not raiz_resolvida.is_dir():
            raise ValueError(
                "raiz_dados deve apontar para um diretório existente; "
                f"recebido {raiz_dados!r}"
            )
        manifesto_resolvido = Path(caminho_manifesto)
        if not manifesto_resolvido.is_file():
            raise ValueError(
                "caminho_manifesto deve apontar para um arquivo existente; "
                f"recebido {caminho_manifesto!r}"
            )
        self._raiz_dados = raiz_resolvida
        self._caminho_manifesto = manifesto_resolvido
        self._invocador = invocador

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

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def validar(self) -> ResultadoIntegridade:
        """Executa a validação completa e devolve o :class:`ResultadoIntegridade`.

        Não levanta exceção em divergências; o caller que precisar abortar
        leitura imediatamente deve chamar :meth:`ResultadoIntegridade.assert_ok`.
        """
        deadline_ns = time.monotonic_ns() + int(self.TIMEOUT_TOTAL_S * 1e9)

        # 1. Carrega o manifesto. Erros aqui são reportados em erro_global
        #    para que o caller sempre receba um ResultadoIntegridade.
        try:
            entradas_manifesto = self._carregar_manifesto()
        except _ManifestoMalformado as exc:
            return ResultadoIntegridade(
                ok=False,
                erro_global=f"manifesto-malformado: {exc}",
            )

        entradas_por_nome = {e.nome_arquivo: e for e in entradas_manifesto}

        # 2. Compara cada entrada do manifesto com o disco.
        divergencias: list[Divergencia] = []
        arquivos_ausentes: list[str] = []
        for entrada in entradas_manifesto:
            if time.monotonic_ns() >= deadline_ns:
                return ResultadoIntegridade(
                    ok=False,
                    divergencias=divergencias,
                    arquivos_ausentes=arquivos_ausentes,
                    erro_global=(
                        f"timeout: validação excedeu "
                        f"{int(self.TIMEOUT_TOTAL_S)}s"
                    ),
                )

            caminho = self._raiz_dados / entrada.nome_arquivo
            if not caminho.is_file():
                arquivos_ausentes.append(entrada.nome_arquivo)
                divergencias.append(
                    Divergencia(
                        nome_arquivo=entrada.nome_arquivo,
                        hash_esperado=entrada.hash_sha256,
                        hash_atual=None,
                        motivo="arquivo-ausente",
                    )
                )
                continue

            try:
                hash_atual = _hash_sha256_streaming(caminho)
            except OSError as exc:
                # Trata erro de I/O como divergência: hash impossível de
                # recomputar significa que não podemos confirmar integridade.
                divergencias.append(
                    Divergencia(
                        nome_arquivo=entrada.nome_arquivo,
                        hash_esperado=entrada.hash_sha256,
                        hash_atual=None,
                        motivo="arquivo-ausente",
                    )
                )
                arquivos_ausentes.append(entrada.nome_arquivo)
                continue

            if hash_atual != entrada.hash_sha256:
                divergencias.append(
                    Divergencia(
                        nome_arquivo=entrada.nome_arquivo,
                        hash_esperado=entrada.hash_sha256,
                        hash_atual=hash_atual,
                        motivo="hash-divergente",
                    )
                )

        # 3. Detecta arquivos em disco fora do manifesto.
        nao_registrados: list[str] = []
        for caminho in _iterar_arquivos(self._raiz_dados):
            if time.monotonic_ns() >= deadline_ns:
                return ResultadoIntegridade(
                    ok=False,
                    divergencias=divergencias,
                    arquivos_ausentes=arquivos_ausentes,
                    nao_registrados=nao_registrados,
                    erro_global=(
                        f"timeout: validação excedeu "
                        f"{int(self.TIMEOUT_TOTAL_S)}s"
                    ),
                )
            relativo = caminho.relative_to(self._raiz_dados).as_posix()
            if relativo == _NOME_MANIFESTO:
                continue
            if relativo not in entradas_por_nome:
                nao_registrados.append(relativo)

        ok = (
            not divergencias
            and not nao_registrados
            and not arquivos_ausentes
        )

        return ResultadoIntegridade(
            ok=ok,
            divergencias=divergencias,
            nao_registrados=nao_registrados,
            arquivos_ausentes=arquivos_ausentes,
            erro_global=None,
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _carregar_manifesto(self) -> list[EntradaManifesto]:
        """Lê e valida o JSON do manifesto, devolvendo a lista de entradas.

        Levanta :class:`_ManifestoMalformado` em qualquer falha de parsing
        ou schema. Não propaga ``json.JSONDecodeError`` para fora.
        """
        try:
            bruto = self._caminho_manifesto.read_text(encoding="utf-8")
        except OSError as exc:
            raise _ManifestoMalformado(
                f"falha ao ler arquivo: {exc}"
            ) from exc
        try:
            payload = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise _ManifestoMalformado(
                f"JSON inválido: {exc.msg} em linha {exc.lineno}"
            ) from exc
        if not isinstance(payload, dict):
            raise _ManifestoMalformado(
                f"manifesto deve ser objeto JSON; recebido {type(payload).__name__}"
            )
        entradas_raw = payload.get("entradas")
        if not isinstance(entradas_raw, list):
            raise _ManifestoMalformado(
                "campo 'entradas' ausente ou não é lista"
            )
        entradas: list[EntradaManifesto] = []
        for indice, item in enumerate(entradas_raw):
            try:
                entradas.append(EntradaManifesto.model_validate(item))
            except Exception as exc:
                raise _ManifestoMalformado(
                    f"entrada[{indice}] inválida: {exc}"
                ) from exc
        return entradas


# ---------------------------------------------------------------------------
# Helpers de baixo nível
# ---------------------------------------------------------------------------


class _ManifestoMalformado(Exception):
    """Erro interno de parsing do manifesto, mapeado para erro_global."""


def _hash_sha256_streaming(caminho: Path) -> str:
    """Recomputa SHA-256 em streaming. Levanta ``OSError`` em falha de I/O."""
    sha256 = hashlib.sha256()
    with caminho.open("rb") as f:
        while True:
            chunk = f.read(_TAMANHO_CHUNK_BYTES)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def _iterar_arquivos(raiz: Path) -> Iterable[Path]:
    """Itera recursivamente em ordem alfabética por caminho relativo POSIX."""
    arquivos: list[Path] = []
    for caminho in raiz.rglob("*"):
        if caminho.is_file():
            arquivos.append(caminho)
    arquivos.sort(key=lambda p: p.relative_to(raiz).as_posix())
    return arquivos


__all__ = [
    "CategoriaErroIntegridade",
    "Divergencia",
    "MotivoDivergencia",
    "ResultadoIntegridade",
    "SkillDataIntegrity",
    "SkillDataIntegrityError",
]
