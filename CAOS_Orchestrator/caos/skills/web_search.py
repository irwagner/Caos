"""Skill_Web_Search — consulta de papers em arXiv e SSRN com filtros.

Cobre o R11.4 do ``requirements.md`` e a linha correspondente da tabela em
``design.md`` seção 6 (Skill_Web_Search):

- Consulta arXiv e SSRN com filtros de termo, intervalo de anos e autores.
- Limite total: 50 resultados por consulta (R11.4).
- Timeout total: 60 segundos por consulta (R11.4), repartido entre as fontes.
- Resultados estruturados em :class:`ResultadoBusca` com campos ``titulo``,
  ``autores``, ``ano``, ``doi_ou_url``, ``abstract`` e ``fonte``.
- Auditoria estruturada via :class:`RegistroAuditoriaSkill`.

Padrão de extensibilidade — :class:`FontePapers`:

A Skill recebe uma lista de implementações de :class:`FontePapers` (Protocol)
no construtor. Isso permite que testes injetem fontes mockadas sem nenhuma
chamada real à internet, atendendo à exigência do enunciado da Task 8 e à
política de CI offline. Em produção, o construtor default usa
:class:`FonteArXiv` (HTTP real contra ``export.arxiv.org``) e
:class:`FonteSSRN` (placeholder retornando lista vazia, pois SSRN não
expõe API pública estável — será implementado em Spec futuro).

Decisões de implementação:

- **Timeout por fonte**: o deadline total de 60s é dividido proporcionalmente
  entre as fontes ativas. Cada fonte recebe ``deadline_s = restante / fontes_restantes``,
  então uma fonte rápida não atrapalha as outras. Quando uma fonte excede
  seu deadline, o erro é capturado e registrado como ``"<fonte>-timeout"`` em
  :attr:`ResultadoWebSearch.erros`, sem abortar a consulta.
- **Deduplicação**: resultados com mesmo ``doi_ou_url`` (normalizado para
  lowercase com strip) são considerados duplicatas. O primeiro encontrado
  vence (ordem das fontes informada ao construtor).
- **Limite de 50**: aplicado APÓS a deduplicação para garantir o teto do
  R11.4 mesmo quando duas fontes retornam blocos sobrepostos.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path  # noqa: F401 - mantido por simetria com demais Skills
from typing import Any, Iterable, Literal, Optional, Protocol, runtime_checkable

from caos.skills._base import (
    RegistroAuditoriaSkill,
    StatusSkill,
    _hash_parametros_sha256,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Timeout total da consulta (R11.4).
TIMEOUT_S: float = 60.0

#: Limite máximo de resultados retornados (R11.4).
LIMITE_RESULTADOS: int = 50

#: Ano mínimo aceitável em ``ano_inicio``/``ano_fim`` (R11.4).
ANO_MIN: int = 1900


def _ano_atual_utc() -> int:
    """Ano corrente em UTC. Encapsulado para facilitar mock em testes."""
    return datetime.now(timezone.utc).year


#: Default usado quando o caller deixa ``ano_fim`` em branco.
ANO_MAX_DEFAULT: int = _ano_atual_utc()

#: Endpoint público da API Atom do arXiv. Usamos HTTP por compatibilidade
#: com ambientes corporativos onde HTTPS pode estar bloqueado para esta
#: API específica; o conteúdo retornado é metadado público.
_URL_ARXIV_BASE: str = "http://export.arxiv.org/api/query"

#: Tipos públicos para identificação da fonte.
NomeFonte = Literal["arxiv", "ssrn"]


# ---------------------------------------------------------------------------
# Modelos públicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FiltrosBusca:
    """Filtros aplicados a uma consulta.

    Attributes
    ----------
    termo:
        Termo de busca (≥1 caractere após strip).
    ano_inicio, ano_fim:
        Intervalo fechado [ano_inicio, ano_fim] em [ANO_MIN, ANO_MAX_DEFAULT].
        Ambos opcionais; quando informados, ``ano_inicio <= ano_fim``.
    autores:
        Lista de nomes de autor para refinar a busca. Strings não vazias.
    fonte:
        ``"arxiv"``, ``"ssrn"`` ou ``"ambos"`` (default).
    """

    termo: str
    ano_inicio: Optional[int] = None
    ano_fim: Optional[int] = None
    autores: tuple[str, ...] = ()
    fonte: Literal["arxiv", "ssrn", "ambos"] = "ambos"


@dataclass(frozen=True)
class ResultadoBusca:
    """Resultado individual normalizado entre fontes.

    Attributes
    ----------
    titulo:
        Título do paper (whitespace colapsado).
    autores:
        Tupla imutável de nomes de autor.
    ano:
        Ano de publicação (``None`` quando não recuperável).
    doi_ou_url:
        Identificador único — DOI quando disponível, URL canônica caso
        contrário. Usado para deduplicação.
    abstract:
        Resumo do paper (whitespace colapsado, pode ser string vazia).
    fonte:
        ``"arxiv"`` ou ``"ssrn"``.
    """

    titulo: str
    autores: tuple[str, ...]
    ano: Optional[int]
    doi_ou_url: str
    abstract: str
    fonte: NomeFonte


@dataclass(frozen=True)
class ResultadoWebSearch:
    """Saída estruturada de :meth:`SkillWebSearch.buscar`.

    Attributes
    ----------
    filtros:
        Filtros usados na consulta (eco de entrada para auditabilidade).
    resultados:
        Tupla de até :data:`LIMITE_RESULTADOS` resultados, deduplicados.
    duracao_ms:
        Tempo total da consulta.
    status:
        ``"skill-ok"`` se ≥1 fonte respondeu sem erro;
        ``"skill-falha"`` se todas as fontes falharam;
        ``"skill-timeout"`` se o orçamento de tempo total foi exaurido
        antes de qualquer resposta.
    auditoria:
        :class:`RegistroAuditoriaSkill` para o Council_Recorder.
    erros:
        Tupla de strings curtas descrevendo falhas por fonte
        (ex.: ``"arxiv-timeout"``, ``"ssrn-erro"``).
    """

    filtros: FiltrosBusca
    resultados: tuple[ResultadoBusca, ...]
    duracao_ms: int
    status: StatusSkill
    auditoria: RegistroAuditoriaSkill
    erros: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Protocolo de fonte e exceção
# ---------------------------------------------------------------------------


class FonteIndisponivel(RuntimeError):
    """Falha tipificada de uma fonte (timeout, rede, parse ou outro).

    O ``categoria`` é uma string curta usada como entrada em
    :attr:`ResultadoWebSearch.erros` (ex.: ``"arxiv-timeout"``,
    ``"ssrn-erro"``).
    """

    def __init__(self, categoria: str) -> None:
        if not isinstance(categoria, str) or not categoria:
            raise ValueError("categoria deve ser string não vazia")
        self.categoria = categoria
        super().__init__(categoria)


@runtime_checkable
class FontePapers(Protocol):
    """Protocolo das fontes plugáveis em :class:`SkillWebSearch`.

    Implementações precisam expor:

    - atributo ``nome``: ``"arxiv"`` ou ``"ssrn"``;
    - método :meth:`buscar`: aceita :class:`FiltrosBusca` e ``deadline_s``,
      e devolve uma lista de :class:`ResultadoBusca`. Pode levantar
      :class:`FonteIndisponivel` para sinalizar falhas tipificadas.
    """

    nome: NomeFonte

    def buscar(
        self,
        filtros: FiltrosBusca,
        *,
        deadline_s: float,
    ) -> list[ResultadoBusca]:
        ...


# ---------------------------------------------------------------------------
# Fonte: arXiv
# ---------------------------------------------------------------------------


class FonteArXiv:
    """Implementação de :class:`FontePapers` para arXiv (HTTP Atom).

    A query é construída concatenando ``all:{termo}`` com filtros opcionais
    de autor (``+AND+au:"<autor>"``) e ano (``+AND+submittedDate:[...]``).

    Em qualquer falha (HTTPError, URLError, timeout, parse) levanta
    :class:`FonteIndisponivel` com categoria curta. Não retorna lista
    parcial em caso de erro — o caller controla parcialidade via deadlines.
    """

    nome: NomeFonte = "arxiv"

    def __init__(self, *, url_base: str = _URL_ARXIV_BASE) -> None:
        self._url_base = url_base

    def buscar(
        self,
        filtros: FiltrosBusca,
        *,
        deadline_s: float,
    ) -> list[ResultadoBusca]:
        """Consulta a API Atom do arXiv aplicando ``filtros``.

        Parameters
        ----------
        filtros:
            Filtros já validados pelo caller.
        deadline_s:
            Timeout (segundos) para a chamada HTTP; valores ≤0 levantam
            :class:`FonteIndisponivel` com categoria ``"arxiv-timeout"`` sem
            tentar a chamada.
        """
        if deadline_s <= 0:
            raise FonteIndisponivel("arxiv-timeout")

        url = self._construir_url(filtros)

        try:
            with urllib.request.urlopen(url, timeout=deadline_s) as resp:
                xml_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            raise FonteIndisponivel(f"arxiv-http-{exc.code}") from exc
        except urllib.error.URLError as exc:
            # ``URLError`` é levantado também em timeouts; distinguimos pela
            # mensagem para emitir categoria mais informativa.
            mensagem = str(getattr(exc, "reason", exc)).lower()
            if "timed out" in mensagem or "timeout" in mensagem:
                raise FonteIndisponivel("arxiv-timeout") from exc
            raise FonteIndisponivel("arxiv-erro") from exc
        except TimeoutError as exc:
            raise FonteIndisponivel("arxiv-timeout") from exc
        except OSError as exc:  # pragma: no cover - cobre erros de socket raros
            raise FonteIndisponivel("arxiv-erro") from exc

        try:
            return self._parsear_atom(xml_bytes)
        except ET.ParseError as exc:
            raise FonteIndisponivel("arxiv-parse") from exc

    # ------------------------------------------------------------------
    # Construção da URL
    # ------------------------------------------------------------------

    def _construir_url(self, filtros: FiltrosBusca) -> str:
        """Monta a URL final usando ``urlencode`` (escapa termos com espaço)."""
        partes_query: list[str] = [f"all:{filtros.termo}"]
        for autor in filtros.autores:
            # Aspas no valor garantem matching de nome composto. O
            # urlencode posterior cuida de escapar as aspas.
            partes_query.append(f'au:"{autor}"')
        if filtros.ano_inicio is not None or filtros.ano_fim is not None:
            ano_inicio = filtros.ano_inicio or ANO_MIN
            ano_fim = filtros.ano_fim or ANO_MAX_DEFAULT
            faixa = (
                f"submittedDate:["
                f"{ano_inicio}01010000+TO+{ano_fim}12312359"
                f"]"
            )
            partes_query.append(faixa)
        search_query = "+AND+".join(partes_query)

        # ``urlencode`` aplicado apenas aos parâmetros estáveis; a parte
        # ``search_query`` é juntada manualmente porque o arXiv exige a
        # sintaxe ``+AND+`` literal entre cláusulas.
        params = urllib.parse.urlencode(
            {
                "start": 0,
                "max_results": LIMITE_RESULTADOS,
            }
        )
        return f"{self._url_base}?search_query={search_query}&{params}"

    # ------------------------------------------------------------------
    # Parsing do Atom
    # ------------------------------------------------------------------

    def _parsear_atom(self, xml_bytes: bytes) -> list[ResultadoBusca]:
        """Parser público (com underline) usado também em testes unitários.

        Levanta :class:`xml.etree.ElementTree.ParseError` em XML malformado;
        é capturado pelo caller (:meth:`buscar`) e mapeado para
        :class:`FonteIndisponivel`.
        """
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        root = ET.fromstring(xml_bytes)
        resultados: list[ResultadoBusca] = []
        for entry in root.findall("atom:entry", ns):
            titulo = _texto_limpo(_text_de(entry.find("atom:title", ns)))
            abstract = _texto_limpo(_text_de(entry.find("atom:summary", ns)))
            autores = tuple(
                _texto_limpo(_text_de(a.find("atom:name", ns)))
                for a in entry.findall("atom:author", ns)
                if _text_de(a.find("atom:name", ns)).strip()
            )
            ano: Optional[int] = None
            published = _text_de(entry.find("atom:published", ns)).strip()
            if len(published) >= 4 and published[:4].isdigit():
                ano = int(published[:4])
            doi_ou_url = _texto_limpo(_text_de(entry.find("atom:id", ns)))
            if not doi_ou_url:
                # Sem ``id`` o resultado não é deduplicável; pulamos.
                continue
            if not titulo:
                continue
            resultados.append(
                ResultadoBusca(
                    titulo=titulo,
                    autores=autores,
                    ano=ano,
                    doi_ou_url=doi_ou_url,
                    abstract=abstract,
                    fonte="arxiv",
                )
            )
        return resultados


def _text_de(elemento: Optional[ET.Element]) -> str:
    """Devolve ``elemento.text or ''`` defensivamente (None-safe)."""
    if elemento is None:
        return ""
    return elemento.text or ""


def _texto_limpo(valor: str) -> str:
    """Colapsa whitespace (incluindo newlines) para single-space e dá strip."""
    if not valor:
        return ""
    return " ".join(valor.split())


# ---------------------------------------------------------------------------
# Fonte: SSRN (placeholder)
# ---------------------------------------------------------------------------


class FonteSSRN:
    """Placeholder de :class:`FontePapers` para SSRN.

    SSRN não expõe API pública estável (a API legada do SSRN exige token e
    contrato corporativo). Esta classe existe para satisfazer o contrato
    do design seção 6 sem fazer scraping não autorizado: retorna sempre
    lista vazia, sem levantar exceção. A :class:`SkillWebSearch` adiciona
    automaticamente ``"ssrn-nao-disponivel"`` aos erros para sinalizar a
    limitação ao usuário.

    Implementação real ficará em Spec futuro, condicional a uma decisão do
    Conselho aprovando o uso de algum proxy autorizado.
    """

    nome: NomeFonte = "ssrn"

    def buscar(
        self,
        filtros: FiltrosBusca,
        *,
        deadline_s: float,
    ) -> list[ResultadoBusca]:
        # Mantemos a assinatura completa para casar com o protocolo, mas
        # retornamos vazio sem fazer chamada de rede. Os parâmetros são
        # ignorados intencionalmente.
        del filtros, deadline_s
        return []


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillWebSearch:
    """Busca papers em arXiv e SSRN aplicando filtros antibias.

    Parameters
    ----------
    invocador:
        Identificador do agente invocador (tipicamente ``"Explorador"``).
    fontes:
        Iterável de implementações de :class:`FontePapers`. Default é
        ``[FonteArXiv(), FonteSSRN()]``. Em testes, injete fontes mock para
        evitar chamadas à internet.
    """

    NOME: str = "Skill_Web_Search"
    TIMEOUT_S: float = TIMEOUT_S
    LIMITE_RESULTADOS: int = LIMITE_RESULTADOS

    def __init__(
        self,
        *,
        invocador: Optional[str] = None,
        fontes: Optional[Iterable[FontePapers]] = None,
    ) -> None:
        self._invocador = invocador
        if fontes is None:
            self._fontes: tuple[FontePapers, ...] = (FonteArXiv(), FonteSSRN())
        else:
            self._fontes = tuple(fontes)
        for f in self._fontes:
            if not hasattr(f, "nome") or not hasattr(f, "buscar"):
                raise TypeError(
                    "fontes devem implementar FontePapers; "
                    f"recebido objeto sem atributos requeridos: {f!r}"
                )

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def invocador(self) -> Optional[str]:
        """Agente invocador, se informado no construtor."""
        return self._invocador

    @property
    def fontes(self) -> tuple[FontePapers, ...]:
        """Tupla imutável das fontes registradas."""
        return self._fontes

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def buscar(self, filtros: FiltrosBusca) -> ResultadoWebSearch:
        """Executa a consulta consolidada nas fontes ativas.

        Aplica:

        - validação de :class:`FiltrosBusca`;
        - filtragem de fontes ativas pelo campo :attr:`FiltrosBusca.fonte`;
        - timeout total :data:`TIMEOUT_S`, repartido entre as fontes;
        - deduplicação por ``doi_ou_url``;
        - truncagem ao limite de :data:`LIMITE_RESULTADOS`.
        """
        _validar_filtros(filtros)

        fontes_ativas = self._selecionar_fontes(filtros.fonte)

        # Hash dos parâmetros — feito antes da execução para que a auditoria
        # exista mesmo se nenhuma fonte responder.
        parametros_canonicos = _filtros_para_dict(filtros)
        hash_params = _hash_parametros_sha256(parametros_canonicos)
        timestamp_inicio = _agora_utc_iso()
        inicio_ns = time.monotonic_ns()
        deadline_total_ns = inicio_ns + int(TIMEOUT_S * 1_000_000_000)

        resultados_por_chave: dict[str, ResultadoBusca] = {}
        ordem_chaves: list[str] = []
        erros: list[str] = []
        sucessos = 0

        for indice, fonte in enumerate(fontes_ativas):
            restantes = max(1, len(fontes_ativas) - indice)
            tempo_restante_ns = max(0, deadline_total_ns - time.monotonic_ns())
            if tempo_restante_ns <= 0:
                erros.append(f"{fonte.nome}-timeout")
                continue
            deadline_fonte_s = (tempo_restante_ns / 1_000_000_000) / restantes

            try:
                lista = fonte.buscar(filtros, deadline_s=deadline_fonte_s)
            except FonteIndisponivel as exc:
                erros.append(exc.categoria)
                continue
            except Exception as exc:  # pragma: no cover - rede inesperada
                # Captura defensiva: ``buscar`` não deve levantar nada além
                # de :class:`FonteIndisponivel`, mas qualquer outro erro
                # vira ``"<fonte>-erro"`` para preservar a auditabilidade.
                erros.append(f"{fonte.nome}-erro")
                del exc
                continue

            sucessos += 1
            if fonte.nome == "ssrn" and not lista:
                # Sinaliza explicitamente a limitação documentada do SSRN
                # (placeholder) sem contar como falha — sucesso permanece
                # incrementado.
                erros.append("ssrn-nao-disponivel")

            for item in lista:
                chave = _normalizar_chave_dedup(item.doi_ou_url)
                if chave in resultados_por_chave:
                    continue
                resultados_por_chave[chave] = item
                ordem_chaves.append(chave)
                if len(ordem_chaves) >= LIMITE_RESULTADOS:
                    break

            if len(ordem_chaves) >= LIMITE_RESULTADOS:
                break

        resultados_truncados = tuple(
            resultados_por_chave[chave]
            for chave in ordem_chaves[:LIMITE_RESULTADOS]
        )

        duracao_ms = _ms_desde(inicio_ns)
        status = _derivar_status(
            sucessos=sucessos,
            falhas_efetivas=_contar_falhas_efetivas(erros),
            total_fontes=len(fontes_ativas),
            duracao_ms=duracao_ms,
        )
        motivo = _derivar_motivo(status, erros)

        auditoria = RegistroAuditoriaSkill(
            nome=self.NOME,
            invocador=self._invocador,
            timestamp=timestamp_inicio,
            parametros_hash_sha256=hash_params,
            exit_code=0 if status == "skill-ok" else -1,
            duracao_ms=duracao_ms,
            status=status,
            motivo=motivo,
            truncado_stdout=False,
            truncado_stderr=False,
        )

        return ResultadoWebSearch(
            filtros=filtros,
            resultados=resultados_truncados,
            duracao_ms=duracao_ms,
            status=status,
            auditoria=auditoria,
            erros=tuple(erros),
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _selecionar_fontes(
        self, escolha: Literal["arxiv", "ssrn", "ambos"]
    ) -> tuple[FontePapers, ...]:
        """Filtra :attr:`fontes` pelo nome solicitado em :class:`FiltrosBusca`."""
        if escolha == "ambos":
            return self._fontes
        return tuple(f for f in self._fontes if f.nome == escolha)


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------


def _validar_filtros(filtros: FiltrosBusca) -> None:
    """Valida :class:`FiltrosBusca` antes de qualquer chamada de fonte.

    Erros são levantados como ``ValueError`` para preservar o contrato
    consistente das demais Skills.
    """
    if not isinstance(filtros, FiltrosBusca):
        raise TypeError(
            "filtros deve ser FiltrosBusca; "
            f"recebido {type(filtros).__name__}"
        )
    if not isinstance(filtros.termo, str) or not filtros.termo.strip():
        raise ValueError("termo deve ser string não vazia")
    ano_max_corrente = _ano_atual_utc()
    if filtros.ano_inicio is not None:
        if not isinstance(filtros.ano_inicio, int):
            raise ValueError(
                f"ano_inicio deve ser inteiro; recebido {filtros.ano_inicio!r}"
            )
        if not (ANO_MIN <= filtros.ano_inicio <= ano_max_corrente):
            raise ValueError(
                f"ano_inicio deve estar em [{ANO_MIN}, {ano_max_corrente}]; "
                f"recebido {filtros.ano_inicio}"
            )
    if filtros.ano_fim is not None:
        if not isinstance(filtros.ano_fim, int):
            raise ValueError(
                f"ano_fim deve ser inteiro; recebido {filtros.ano_fim!r}"
            )
        if not (ANO_MIN <= filtros.ano_fim <= ano_max_corrente):
            raise ValueError(
                f"ano_fim deve estar em [{ANO_MIN}, {ano_max_corrente}]; "
                f"recebido {filtros.ano_fim}"
            )
    if (
        filtros.ano_inicio is not None
        and filtros.ano_fim is not None
        and filtros.ano_inicio > filtros.ano_fim
    ):
        raise ValueError(
            "ano_inicio deve ser ≤ ano_fim; "
            f"recebido {filtros.ano_inicio} > {filtros.ano_fim}"
        )
    if not isinstance(filtros.autores, tuple):
        raise ValueError(
            "autores deve ser tupla; "
            f"recebido {type(filtros.autores).__name__}"
        )
    for indice, autor in enumerate(filtros.autores):
        if not isinstance(autor, str) or not autor.strip():
            raise ValueError(
                "todos os autores devem ser strings não vazias; "
                f"autores[{indice}]={autor!r}"
            )


def _filtros_para_dict(filtros: FiltrosBusca) -> dict[str, Any]:
    """Converte :class:`FiltrosBusca` em dict canônico para hashing."""
    return {
        "termo": filtros.termo,
        "ano_inicio": filtros.ano_inicio,
        "ano_fim": filtros.ano_fim,
        "autores": list(filtros.autores),
        "fonte": filtros.fonte,
    }


def _normalizar_chave_dedup(doi_ou_url: str) -> str:
    """Normaliza ``doi_ou_url`` para deduplicação case-insensitive."""
    return doi_ou_url.strip().lower()


def _agora_utc_iso() -> str:
    """ISO 8601 UTC sem microssegundos, com sufixo ``Z``."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _ms_desde(inicio_ns: int) -> int:
    """Diferença em ms desde ``inicio_ns`` (``time.monotonic_ns``)."""
    return max(0, (time.monotonic_ns() - inicio_ns) // 1_000_000)


def _contar_falhas_efetivas(erros: list[str]) -> int:
    """Conta entradas de ``erros`` que indicam falha real (≠ ``ssrn-nao-disponivel``).

    O placeholder do SSRN não é contado como falha, pois a fonte respondeu
    como esperado pela documentação atual; a string apenas registra a
    limitação para o usuário.
    """
    return sum(1 for e in erros if e != "ssrn-nao-disponivel")


def _derivar_status(
    *,
    sucessos: int,
    falhas_efetivas: int,
    total_fontes: int,
    duracao_ms: int,
) -> StatusSkill:
    """Aplica a tabela de transição de status descrita no docstring do módulo.

    - ``skill-ok`` quando ≥1 fonte respondeu sem erro real.
    - ``skill-falha`` quando todas as fontes falharam (``falhas_efetivas ==
      total_fontes`` ou ``sucessos == 0`` com falhas).
    - ``skill-timeout`` quando o tempo total chegou ao limite e nenhuma
      fonte respondeu.
    """
    if total_fontes == 0:
        # Sem fontes ativas: não há como reportar sucesso. Tratamos como
        # falha para manter a convenção de "skill-ok exige pelo menos uma
        # fonte respondendo".
        return "skill-falha"
    if sucessos > 0:
        return "skill-ok"
    if duracao_ms >= int(TIMEOUT_S * 1000) and falhas_efetivas == 0:
        return "skill-timeout"
    return "skill-falha"


def _derivar_motivo(status: StatusSkill, erros: list[str]) -> Optional[str]:
    """Texto livre em pt-BR para ``auditoria.motivo``."""
    if status == "skill-ok":
        return None
    if not erros:
        return f"status={status} sem erros reportados"
    return f"status={status}; erros={','.join(erros)}"


__all__ = [
    "ANO_MAX_DEFAULT",
    "ANO_MIN",
    "FiltrosBusca",
    "FontePapers",
    "FonteArXiv",
    "FonteIndisponivel",
    "FonteSSRN",
    "LIMITE_RESULTADOS",
    "NomeFonte",
    "ResultadoBusca",
    "ResultadoWebSearch",
    "SkillWebSearch",
    "TIMEOUT_S",
]
