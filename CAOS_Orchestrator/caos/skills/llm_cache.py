"""Skill_LLM_Cache — cache determinístico de respostas LLM (R11.8, R16).

Esta Skill armazena e recupera respostas cacheadas de invocações de agentes LLM
em ``CAOS_Orchestrator/.cache/`` com um arquivo JSON por entrada. O nome do
arquivo é o hex SHA-256 da chave de cache, computado canonicamente sobre
``(agente, modelo, hash_prompt, hash_contexto, seed)`` (R16.1, R16.2).

Resumo do contrato:

- :meth:`SkillLLMCache.computar_chave` produz a chave hex SHA-256 a partir dos
  cinco componentes. ``seed`` aceita string vazia para representar modelos sem
  suporte a seed (R16.2).
- :meth:`SkillLLMCache.consultar` retorna :class:`EntradaCache` quando há hit
  válido e :data:`None` em qualquer caso de miss — incluindo arquivo ausente,
  JSON corrompido, schema divergente ou leitura que excede 1 segundo (R16.7).
  Warnings sobre leituras corrompidas/timeout ficam acumulados em
  :meth:`SkillLLMCache.warnings`.
- :meth:`SkillLLMCache.gravar` persiste atomicamente via ``.tmp`` + ``replace``
  com JSON canônico (``sort_keys=True``, ``indent=2``, ``ensure_ascii=False``).
- :meth:`SkillLLMCache.cache_hit` é açúcar para
  ``self.consultar(chave) is not None``.

A política de **não consultar/gravar quando turno é ``nao-deterministico``**
(R16.5) é responsabilidade do caller (Athena/Council_Recorder) — esta Skill é
um cache puro e não conhece o estado do turno.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from caos.models import EntradaCache

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Diretório default do cache, relativo ao caller. O construtor recebe um
#: caminho explícito (preferencialmente absoluto) — esta constante existe
#: apenas como referência canônica do layout em disco (R16.1).
DIRETORIO_CACHE_PADRAO: Path = Path("CAOS_Orchestrator/.cache")

#: Timeout de leitura de uma entrada (R16.7). Acima disso a entrada é tratada
#: como ausente e um warning é registrado.
_TIMEOUT_LEITURA_CACHE_S: float = 1.0

#: Regex de validação de hash SHA-256 hex (64 chars).
_REGEX_HASH_SHA256 = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


@dataclass
class _Estado:
    """Estado interno mutável (warnings) — separado para clareza de tipo."""

    warnings: list[str] = field(default_factory=list)


class SkillLLMCache:
    """Cache JSON determinístico de respostas LLM em disco.

    Parameters
    ----------
    diretorio_cache:
        Diretório onde os arquivos ``<chave>.json`` são lidos/gravados. Será
        criado (e seus pais) se ainda não existir.
    invocador:
        Identificador opcional do agente invocador, exposto em
        :attr:`invocador` para auditoria pelo caller.
    """

    NOME: str = "Skill_LLM_Cache"
    TIMEOUT_LEITURA_S: float = _TIMEOUT_LEITURA_CACHE_S

    def __init__(
        self,
        *,
        diretorio_cache: Path,
        invocador: Optional[str] = None,
    ) -> None:
        diretorio = Path(diretorio_cache)
        diretorio.mkdir(parents=True, exist_ok=True)
        self._diretorio_cache = diretorio
        self._invocador = invocador
        self._estado = _Estado()

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def diretorio_cache(self) -> Path:
        """Diretório raiz do cache em disco."""
        return self._diretorio_cache

    @property
    def invocador(self) -> Optional[str]:
        """Agente invocador, se informado no construtor."""
        return self._invocador

    def warnings(self) -> list[str]:
        """Warnings acumulados sobre leituras corrompidas/timeout (R16.7)."""
        return list(self._estado.warnings)

    # ------------------------------------------------------------------
    # Chave de cache (R16.2)
    # ------------------------------------------------------------------

    def computar_chave(
        self,
        *,
        agente: str,
        modelo: str,
        hash_prompt: str,
        hash_contexto: str,
        seed: str,
    ) -> str:
        """Calcula a chave SHA-256 hex sobre os cinco componentes (R16.2).

        Concatena canonicamente ``f"{agente}|{modelo}|{hash_prompt}|"
        f"{hash_contexto}|{seed}"`` em UTF-8 e devolve o hex do digest.

        Parameters
        ----------
        agente:
            Nome canônico do agente (ex.: ``"Athena"``).
        modelo:
            Identificador do modelo (ex.: ``"claude-sonnet-4.5"``).
        hash_prompt, hash_contexto:
            Strings hex de 64 caracteres (SHA-256 hex) — qualquer outro
            formato dispara :class:`ValueError`.
        seed:
            String com o seed numérico (ex.: ``"42"``) ou string vazia para
            modelos sem suporte a seed (R16.2).

        Raises
        ------
        ValueError
            Quando ``agente``, ``modelo``, ``hash_prompt`` ou
            ``hash_contexto`` estão fora do formato esperado.
        """
        if not isinstance(agente, str) or not agente:
            raise ValueError(
                f"agente deve ser string não vazia; recebido {agente!r}"
            )
        if not isinstance(modelo, str) or not modelo:
            raise ValueError(
                f"modelo deve ser string não vazia; recebido {modelo!r}"
            )
        if not _REGEX_HASH_SHA256.fullmatch(hash_prompt or ""):
            raise ValueError(
                "hash_prompt deve ser hex SHA-256 (64 chars [0-9a-f]); "
                f"recebido {hash_prompt!r}"
            )
        if not _REGEX_HASH_SHA256.fullmatch(hash_contexto or ""):
            raise ValueError(
                "hash_contexto deve ser hex SHA-256 (64 chars [0-9a-f]); "
                f"recebido {hash_contexto!r}"
            )
        if not isinstance(seed, str):
            # Seed precisa ser string para que vazio represente "sem seed"
            # de forma inequívoca (R16.2). Inteiros devem ser str(int) pelo
            # caller.
            raise ValueError(
                f"seed deve ser string (use '' quando ausente); "
                f"recebido tipo {type(seed).__name__}"
            )

        bruto = f"{agente}|{modelo}|{hash_prompt}|{hash_contexto}|{seed}"
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Leitura (R16.3, R16.7)
    # ------------------------------------------------------------------

    def consultar(self, chave: str) -> Optional[EntradaCache]:
        """Consulta a entrada de cache associada a ``chave``.

        Retorna :class:`EntradaCache` em caso de hit. Em qualquer das condições
        abaixo retorna :data:`None`, o que o caller deve registrar como
        ``cache_hit: false``:

        - Arquivo inexistente (cache miss real).
        - Leitura excedeu :data:`_TIMEOUT_LEITURA_CACHE_S` (R16.7).
        - JSON inválido / arquivo corrompido (R16.7).
        - Payload válido como JSON mas inválido para :class:`EntradaCache`.

        Quando o motivo é corrupção/timeout, um warning é registrado em
        :meth:`warnings` para auditoria.
        """
        if not isinstance(chave, str) or not _REGEX_HASH_SHA256.fullmatch(
            chave
        ):
            # Chave malformada nunca pode ter um arquivo correspondente
            # válido. Tratamos como miss silencioso para não vazar exceção
            # ao caller — ele cobre esse caso pelo computar_chave acima.
            return None

        caminho = self._diretorio_cache / f"{chave}.json"
        if not caminho.is_file():
            return None

        # Aplicação do timeout de 1 segundo (R16.7) via executor de thread
        # única — mantém o padrão das demais Skills (não usa signal,
        # Unix-only).
        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=1
            ) as executor:
                future = executor.submit(_ler_json_arquivo, caminho)
                try:
                    payload = future.result(
                        timeout=_TIMEOUT_LEITURA_CACHE_S
                    )
                except concurrent.futures.TimeoutError:
                    self._estado.warnings.append(
                        f"timeout ao ler entrada de cache: {caminho}"
                    )
                    return None
        except OSError as exc:
            # Erros do executor (raros) — tratamos como miss com warning.
            self._estado.warnings.append(
                f"erro ao consultar cache em {caminho}: {exc}"
            )
            return None

        if payload is _MARCADOR_JSON_INVALIDO:
            self._estado.warnings.append(
                f"cache corrompido (JSON inválido) em {caminho}"
            )
            return None
        if isinstance(payload, _LeituraFalhou):
            self._estado.warnings.append(
                f"cache corrompido (erro de leitura) em {caminho}: "
                f"{payload.mensagem}"
            )
            return None

        try:
            return EntradaCache.model_validate(payload)
        except Exception as exc:
            self._estado.warnings.append(
                f"cache corrompido (schema inválido) em {caminho}: {exc}"
            )
            return None

    def cache_hit(self, chave: str) -> bool:
        """Açúcar para ``self.consultar(chave) is not None``."""
        return self.consultar(chave) is not None

    # ------------------------------------------------------------------
    # Escrita (R16.4, R16.6)
    # ------------------------------------------------------------------

    def gravar(self, entrada: EntradaCache) -> None:
        """Grava ``entrada`` em disco com escrita atômica (R16.4, R16.6).

        Estratégia: escreve primeiro em ``<chave>.json.tmp`` e depois aplica
        ``Path.replace`` para um swap atômico (no Windows o
        ``ReplaceFile`` subjacente é atômico no nível do filesystem para
        arquivos no mesmo diretório).

        O JSON é canônico: ``indent=2``, ``sort_keys=True``,
        ``ensure_ascii=False`` e ``default=str`` para datetimes — para o
        layout ficar comparável byte-a-byte entre execuções com mesma
        :class:`EntradaCache`.
        """
        if not isinstance(entrada, EntradaCache):
            raise TypeError(
                "entrada deve ser EntradaCache; "
                f"recebido {type(entrada).__name__}"
            )

        caminho = self._diretorio_cache / f"{entrada.chave}.json"
        caminho_tmp = caminho.with_suffix(caminho.suffix + ".tmp")

        # ``model_dump(mode='json')`` aplica conversão de datetime para
        # string ISO 8601 já no nível do Pydantic, garantindo que a
        # serialização bata com a esperada por ``model_validate`` na
        # leitura subsequente.
        payload = entrada.model_dump(mode="json")
        bruto = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

        try:
            caminho_tmp.write_text(bruto, encoding="utf-8")
            caminho_tmp.replace(caminho)
        finally:
            # ``replace`` move o tmp; só é necessário limpar se o write_text
            # falhou antes do replace conseguir mover.
            if caminho_tmp.exists():
                try:
                    caminho_tmp.unlink()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LeituraFalhou:
    """Sinaliza erro de leitura no thread auxiliar.

    Usar uma instância (em vez de propagar exceção pelo ``future.result``)
    evita logs de traceback em casos esperados (arquivo corrompido).
    """

    mensagem: str


#: Marcador retornado quando o arquivo existe mas seu conteúdo não é JSON
#: válido. Usar um sentinel é mais simples que propagar
#: :class:`json.JSONDecodeError` pelo executor.
_MARCADOR_JSON_INVALIDO: Any = object()


def _ler_json_arquivo(caminho: Path) -> Any:
    """Lê e parseia o JSON do arquivo. Retorna marcador ou erro tipificado.

    Esta função é executada em thread separada (timeout via futures). Não
    levanta exceções para o caller; em vez disso, retorna:

    - O ``payload`` parseado em caso de sucesso.
    - :data:`_MARCADOR_JSON_INVALIDO` quando o arquivo existe mas o JSON
      é inválido.
    - :class:`_LeituraFalhou` para qualquer outro erro de I/O.
    """
    try:
        bruto = caminho.read_text(encoding="utf-8")
    except OSError as exc:
        return _LeituraFalhou(mensagem=str(exc))

    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return _MARCADOR_JSON_INVALIDO


__all__ = [
    "DIRETORIO_CACHE_PADRAO",
    "SkillLLMCache",
]
