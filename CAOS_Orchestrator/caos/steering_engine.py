"""Steering_Engine — carregamento e validação de regras em ``.kiro/steering/``.

Este módulo cobre o componente ``Steering_Engine`` descrito em ``design.md``
(seção 2 — Componentes e Interfaces; seção 3.5 — Modelo de regra de Steering)
e os critérios R3.1 a R3.6, R7.3, R7.4, R13.4, R17.2 e R17.6 do
``requirements.md``.

Responsabilidades:

- Varrer ``.kiro/steering/*.md`` lendo cabeçalho YAML + corpo Markdown via
  ``python-frontmatter``.
- Validar o cabeçalho contra :class:`caos.models.RegraSteering`
  (data, autor, justificativa). Campos extras de frontmatter (por exemplo
  ``orcamento`` ou ``orcamentos``) são preservados em ``metadata_raw`` mas
  NÃO entram no schema Pydantic — Spec não permite estender ``RegraSteering``
  silenciosamente.
- Classificar regras inválidas por categoria (``frontmatter-ausente``,
  ``frontmatter-malformado``, ``campo-obrigatorio-faltando``,
  ``data-formato-invalido``, ``autor-invalido``, ``justificativa-vazia``,
  ``validacao-pydantic``).
- Expor ao orquestrador (Athena) as configurações operacionais:

  * ``get_orcamento_de_turnos()`` — R7.3, R7.4: faixa válida 4..100, default 12.
  * ``get_orcamento_de_tokens(agente)`` — R17.2, R17.6: mínimo 10.000, default
    1.000.000.
  * ``get_ninjascript_apis_autorizadas()`` — R6.3 + R13.4: whitelist consumida
    por Hermes em sua avaliação técnica.

Mensagens de erro, warnings e categorias são em pt-BR (R3.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import frontmatter
from pydantic import ValidationError

from caos.models import RegraSteering

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Campos do frontmatter que são consumidos por :class:`RegraSteering`.
#:
#: Quaisquer outros campos (``orcamento``, ``orcamentos``, etc.) são preservados
#: em ``metadata_raw`` para consumo dedicado pelos métodos da
#: :class:`SteeringEngine`, sem violar ``extra="forbid"`` do schema.
_CAMPOS_REGRA_STEERING: frozenset[str] = frozenset(
    {"data", "autor", "justificativa"}
)

#: Faixa válida de ``Orcamento_De_Turnos`` (R7.2).
ORCAMENTO_TURNOS_MIN = 4
ORCAMENTO_TURNOS_MAX = 100
ORCAMENTO_TURNOS_DEFAULT = 12

#: Mínimo de ``Orcamento_Diario_Tokens`` por agente (R17.6).
ORCAMENTO_TOKENS_MIN = 10_000
ORCAMENTO_TOKENS_DEFAULT = 1_000_000

#: Nome (sem extensão) dos arquivos consumidos pelos métodos públicos.
ARQUIVO_ORCAMENTO_TURNOS = "orcamento-de-turnos"
ARQUIVO_ORCAMENTO_TOKENS = "orcamento-de-tokens"
ARQUIVO_NINJASCRIPT_API = "ninjascript-api"

#: Regex usada para extrair ``orcamento: NN`` do corpo Markdown como fallback.
_REGEX_ORCAMENTO_BODY = re.compile(
    r"^\s*orcamento\s*:\s*(\S+)\s*$", re.MULTILINE | re.IGNORECASE
)

CategoriaFalhaSteering = Literal[
    "frontmatter-ausente",
    "frontmatter-malformado",
    "campo-obrigatorio-faltando",
    "data-formato-invalido",
    "autor-invalido",
    "justificativa-vazia",
    "validacao-pydantic",
]
"""Categorias de falha possíveis ao carregar uma regra de Steering."""


# ---------------------------------------------------------------------------
# Estruturas de retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FalhaSteering:
    """Descrição estruturada de uma regra de Steering inválida.

    ``caminho`` aponta para o arquivo afetado. ``detalhes`` carrega informação
    suplementar (lista de campos faltantes, erros do Pydantic, exceção crua,
    etc.) para registro em log e auditoria.
    """

    caminho: Path
    categoria: CategoriaFalhaSteering
    mensagem: str
    detalhes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoCarregamentoSteering:
    """Resultado da varredura de ``.kiro/steering/``.

    ``regras`` mapeia ``nome_arquivo_sem_extensao -> RegraSteering`` apenas
    para regras válidas. ``falhas`` enumera todas as regras inválidas — a
    varredura não interrompe na primeira falha, para permitir relatório
    completo ao usuário (R3.6 exige sinalização explícita do arquivo e do
    campo problemático).

    ``metadata_raw`` preserva o frontmatter completo (incluindo campos
    extras como ``orcamento`` e ``orcamentos``) para consumo pelos métodos
    da :class:`SteeringEngine`. Indexado pelo mesmo
    ``nome_arquivo_sem_extensao``.
    """

    diretorio: Path
    regras: dict[str, RegraSteering] = field(default_factory=dict)
    falhas: list[FalhaSteering] = field(default_factory=list)
    metadata_raw: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def sucesso(self) -> bool:
        """``True`` se nenhuma falha foi registrada."""
        return not self.falhas


# ---------------------------------------------------------------------------
# Carregamento — função pública
# ---------------------------------------------------------------------------


def carregar_regras(diretorio_steering: Path) -> ResultadoCarregamentoSteering:
    """Carrega e valida todas as regras de Steering em ``diretorio_steering``.

    Parameters
    ----------
    diretorio_steering:
        Caminho para ``.kiro/steering/``.

    Notes
    -----
    Quando o diretório não existe ou não é uma pasta, retorna um
    :class:`ResultadoCarregamentoSteering` vazio — sem regras e sem falhas.
    A construção de :class:`SteeringEngine` é quem lança ``FileNotFoundError``
    nesse caso, dado que a engine exige diretório existente para operar.

    A varredura é determinística: arquivos são processados em ordem
    alfabética para que o conteúdo de ``regras`` seja estável entre execuções.
    """
    diretorio = Path(diretorio_steering)
    regras: dict[str, RegraSteering] = {}
    falhas: list[FalhaSteering] = []
    metadata_raw: dict[str, dict[str, Any]] = {}

    if not diretorio.exists() or not diretorio.is_dir():
        return ResultadoCarregamentoSteering(
            diretorio=diretorio,
            regras=regras,
            falhas=falhas,
            metadata_raw=metadata_raw,
        )

    arquivos = sorted(p for p in diretorio.iterdir() if p.suffix == ".md")
    for caminho in arquivos:
        chave = caminho.stem
        resultado_regra, raw = _carregar_um(caminho)
        if isinstance(resultado_regra, RegraSteering):
            regras[chave] = resultado_regra
            metadata_raw[chave] = raw
        elif isinstance(resultado_regra, FalhaSteering):
            falhas.append(resultado_regra)
            # Preservamos metadata_raw mesmo quando há falha de validação,
            # para que callers possam inspecionar campos extras se desejarem.
            if raw:
                metadata_raw[chave] = raw

    return ResultadoCarregamentoSteering(
        diretorio=diretorio,
        regras=regras,
        falhas=falhas,
        metadata_raw=metadata_raw,
    )


# ---------------------------------------------------------------------------
# Carregamento — auxiliares internos
# ---------------------------------------------------------------------------


def _carregar_um(
    caminho: Path,
) -> tuple[RegraSteering | FalhaSteering, dict[str, Any]]:
    """Carrega uma única regra. Retorna ``(RegraSteering | FalhaSteering, raw)``.

    ``raw`` é o dicionário de frontmatter completo (com campos extras como
    ``orcamento``), ou ``{}`` em caso de falha de parsing antes da extração.
    """
    # 1) Parsing do frontmatter.
    try:
        with open(caminho, "r", encoding="utf-8") as fp:
            post = frontmatter.load(fp)
    except Exception as exc:
        return (
            FalhaSteering(
                caminho=caminho,
                categoria="frontmatter-malformado",
                mensagem=(
                    f"frontmatter YAML malformado em {caminho}: {exc}"
                ),
                detalhes={"excecao": type(exc).__name__, "erro": str(exc)},
            ),
            {},
        )

    metadata_raw: dict[str, Any] = dict(post.metadata or {})
    corpo = post.content or ""

    # 2) Detectar frontmatter totalmente ausente: python-frontmatter retorna
    #    metadata vazia tanto para arquivos sem '---' quanto para frontmatter
    #    com '---' mas vazio. Distinguimos inspecionando o início do arquivo.
    if not metadata_raw:
        try:
            inicio = caminho.read_text(encoding="utf-8").lstrip()
        except OSError:
            inicio = ""
        if not inicio.startswith("---"):
            return (
                FalhaSteering(
                    caminho=caminho,
                    categoria="frontmatter-ausente",
                    mensagem=(
                        f"arquivo {caminho} não contém bloco YAML "
                        "frontmatter delimitado por '---'"
                    ),
                ),
                {},
            )

    # 3) Construir RegraSteering apenas com campos do schema.
    dados = {
        k: v for k, v in metadata_raw.items() if k in _CAMPOS_REGRA_STEERING
    }
    dados["corpo_markdown"] = corpo
    dados["nome_arquivo"] = caminho.name

    try:
        regra = RegraSteering(**dados)
    except ValidationError as exc:
        falha = _mapear_validation_error_steering(caminho, metadata_raw, exc)
        return falha, metadata_raw
    except TypeError as exc:
        return (
            FalhaSteering(
                caminho=caminho,
                categoria="frontmatter-malformado",
                mensagem=(
                    f"frontmatter de {caminho} contém estrutura "
                    f"incompatível: {exc}"
                ),
                detalhes={"erro": str(exc)},
            ),
            metadata_raw,
        )

    return regra, metadata_raw


def _mapear_validation_error_steering(
    caminho: Path,
    metadata: dict[str, Any],
    exc: ValidationError,
) -> FalhaSteering:
    """Mapeia ``ValidationError`` para a categoria mais específica possível.

    Heurística (em ordem de prioridade):

    1. Erro em ``data`` -> ``data-formato-invalido``.
    2. Erro em ``autor`` -> ``autor-invalido``.
    3. Erro em ``justificativa`` -> ``justificativa-vazia``.
    4. Algum erro do tipo ``missing`` -> ``campo-obrigatorio-faltando``.
    5. Caso contrário -> ``validacao-pydantic``.
    """
    erros = exc.errors()

    campos_faltando: list[str] = []
    erro_em_data = False
    erro_em_autor = False
    erro_em_justificativa = False

    for erro in erros:
        loc = tuple(str(x) for x in erro.get("loc", ()))
        tipo = erro.get("type", "")
        if tipo == "missing" and loc:
            # Erros 'missing' viram categoria 'campo-obrigatorio-faltando'
            # e NÃO são contabilizados como problema de formato/valor do
            # campo específico — caso contrário, omitir 'data' inteiramente
            # seria classificado como 'data-formato-invalido', o que é
            # impreciso.
            campos_faltando.append(loc[0])
            continue
        if "data" in loc:
            erro_em_data = True
        if "autor" in loc:
            erro_em_autor = True
        if "justificativa" in loc:
            erro_em_justificativa = True

    # Ordem de prioridade — a primeira que casar define a categoria.
    # 'campos_faltando' tem prioridade sobre erros de formato/valor: ausência
    # total do campo é um problema mais fundamental que valor inválido.
    if campos_faltando:
        return FalhaSteering(
            caminho=caminho,
            categoria="campo-obrigatorio-faltando",
            mensagem=(
                f"regra em {caminho} tem campos obrigatórios faltando: "
                f"{sorted(set(campos_faltando))}"
            ),
            detalhes={
                "campos_faltando": sorted(set(campos_faltando)),
                "erros_pydantic": erros,
            },
        )

    if erro_em_data:
        return FalhaSteering(
            caminho=caminho,
            categoria="data-formato-invalido",
            mensagem=(
                f"campo 'data' inválido em {caminho}: "
                f"recebido {metadata.get('data')!r} "
                "(esperado formato YYYY-MM-DD)"
            ),
            detalhes={
                "valor_recebido": metadata.get("data"),
                "erros_pydantic": erros,
            },
        )

    if erro_em_autor:
        return FalhaSteering(
            caminho=caminho,
            categoria="autor-invalido",
            mensagem=(
                f"campo 'autor' inválido em {caminho}: "
                f"recebido {metadata.get('autor')!r} "
                "(esperado 'Athena' ou 'usuario')"
            ),
            detalhes={
                "valor_recebido": metadata.get("autor"),
                "erros_pydantic": erros,
            },
        )

    if erro_em_justificativa:
        return FalhaSteering(
            caminho=caminho,
            categoria="justificativa-vazia",
            mensagem=(
                f"campo 'justificativa' vazio ou muito curto em {caminho} "
                "(mínimo 10 caracteres)"
            ),
            detalhes={
                "valor_recebido": metadata.get("justificativa"),
                "erros_pydantic": erros,
            },
        )

    return FalhaSteering(
        caminho=caminho,
        categoria="validacao-pydantic",
        mensagem=(
            f"regra em {caminho} falhou validação do schema RegraSteering: "
            f"{exc.error_count()} erro(s)"
        ),
        detalhes={"erros_pydantic": erros},
    )


# ---------------------------------------------------------------------------
# SteeringEngine — API pública orientada a objeto
# ---------------------------------------------------------------------------


class SteeringEngine:
    """Engine que expõe regras de Steering ao orquestrador.

    Carrega o diretório na construção e mantém um cache em memória até a
    chamada explícita de :meth:`recarregar`. ``warnings`` acumula mensagens
    sobre configurações inválidas que caíram em default (R7.4, R17.6).
    """

    def __init__(self, diretorio_steering: Path) -> None:
        diretorio = Path(diretorio_steering)
        if not diretorio.exists() or not diretorio.is_dir():
            raise FileNotFoundError(
                f"diretório de steering não existe ou não é pasta: {diretorio}"
            )
        self._diretorio = diretorio
        self._regras: dict[str, RegraSteering] = {}
        self._falhas: list[FalhaSteering] = []
        self._metadata_raw: dict[str, dict[str, Any]] = {}
        self._warnings: list[str] = []
        self.recarregar()

    # ------------------------------------------------------------------
    # Carregamento / inspeção
    # ------------------------------------------------------------------

    def recarregar(self) -> None:
        """Recarrega todo o diretório de steering, zerando os warnings."""
        self._warnings = []
        resultado = carregar_regras(self._diretorio)
        self._regras = dict(resultado.regras)
        self._falhas = list(resultado.falhas)
        self._metadata_raw = dict(resultado.metadata_raw)

    def regras_validas(self) -> dict[str, RegraSteering]:
        """Mapeia ``nome_arquivo_sem_extensao -> RegraSteering`` válida."""
        return dict(self._regras)

    def regras_invalidas(self) -> list[FalhaSteering]:
        """Lista as falhas detectadas no carregamento."""
        return list(self._falhas)

    def warnings(self) -> list[str]:
        """Warnings acumulados (configs inválidas que caíram em default)."""
        return list(self._warnings)

    @property
    def diretorio(self) -> Path:
        return self._diretorio

    # ------------------------------------------------------------------
    # R7.3 / R7.4 — Orçamento de turnos
    # ------------------------------------------------------------------

    def get_orcamento_de_turnos(self) -> int:
        """Retorna o ``Orcamento_De_Turnos`` configurado, ou o default 12.

        Fontes consultadas, em ordem:

        1. Frontmatter da regra ``orcamento-de-turnos`` — campo ``orcamento``.
        2. Corpo Markdown da regra — primeira ocorrência de
           ``orcamento: <valor>`` (case-insensitive).

        Aplica R7.4: se o valor estiver fora de [4, 100] ou não for inteiro,
        registra um warning interno e retorna o default 12.
        """
        if ARQUIVO_ORCAMENTO_TURNOS not in self._regras:
            # Regra ausente é silenciosa: o caller usa o default sem warning,
            # pois isso é o estado-base esperado do projeto (R7.1).
            return ORCAMENTO_TURNOS_DEFAULT

        # 1) Frontmatter.
        raw = self._metadata_raw.get(ARQUIVO_ORCAMENTO_TURNOS, {})
        valor: Any = raw.get("orcamento")

        # 2) Fallback no corpo.
        if valor is None:
            corpo = self._regras[ARQUIVO_ORCAMENTO_TURNOS].corpo_markdown or ""
            match = _REGEX_ORCAMENTO_BODY.search(corpo)
            if match:
                valor = match.group(1)

        if valor is None:
            return ORCAMENTO_TURNOS_DEFAULT

        valor_int = _coercer_inteiro(valor)
        if valor_int is None:
            self._warnings.append(
                f"Orcamento_De_Turnos inválido (não é inteiro): {valor!r}; "
                f"aplicando default {ORCAMENTO_TURNOS_DEFAULT}."
            )
            return ORCAMENTO_TURNOS_DEFAULT

        if not (
            ORCAMENTO_TURNOS_MIN <= valor_int <= ORCAMENTO_TURNOS_MAX
        ):
            self._warnings.append(
                f"Orcamento_De_Turnos {valor_int} fora do intervalo "
                f"[{ORCAMENTO_TURNOS_MIN}, {ORCAMENTO_TURNOS_MAX}]; "
                f"aplicando default {ORCAMENTO_TURNOS_DEFAULT}."
            )
            return ORCAMENTO_TURNOS_DEFAULT

        return valor_int

    # ------------------------------------------------------------------
    # R17.2 / R17.6 — Orçamento de tokens por agente
    # ------------------------------------------------------------------

    def get_orcamento_de_tokens(self, agente: str) -> int:
        """Retorna o ``orcamento_diario_tokens`` para ``agente``.

        Fonte: frontmatter da regra ``orcamento-de-tokens`` — campo
        ``orcamentos`` (mapa ``agente -> int``).

        Aplica R17.6: valores < 10.000 ou não inteiros caem para o default
        1.000.000 e adicionam warning. Agente não listado também recebe o
        default, mas sem warning (estado-base aceitável).
        """
        if ARQUIVO_ORCAMENTO_TOKENS not in self._regras:
            return ORCAMENTO_TOKENS_DEFAULT

        raw = self._metadata_raw.get(ARQUIVO_ORCAMENTO_TOKENS, {})
        orcamentos = raw.get("orcamentos")
        if not isinstance(orcamentos, dict):
            # Estrutura ausente ou inválida — agente não listado.
            return ORCAMENTO_TOKENS_DEFAULT

        if agente not in orcamentos:
            return ORCAMENTO_TOKENS_DEFAULT

        valor = orcamentos[agente]
        valor_int = _coercer_inteiro(valor)
        if valor_int is None:
            self._warnings.append(
                f"orcamento_diario_tokens inválido (não é inteiro) para "
                f"agente {agente!r}: {valor!r}; aplicando default "
                f"{ORCAMENTO_TOKENS_DEFAULT}."
            )
            return ORCAMENTO_TOKENS_DEFAULT

        if valor_int < ORCAMENTO_TOKENS_MIN:
            self._warnings.append(
                f"orcamento_diario_tokens {valor_int} para {agente!r} é "
                f"menor que mínimo {ORCAMENTO_TOKENS_MIN}; aplicando "
                f"default {ORCAMENTO_TOKENS_DEFAULT}."
            )
            return ORCAMENTO_TOKENS_DEFAULT

        return valor_int

    # ------------------------------------------------------------------
    # R6.3 — Whitelist de APIs NinjaScript autorizadas
    # ------------------------------------------------------------------

    def get_ninjascript_apis_autorizadas(self) -> list[str]:
        """Retorna a whitelist de APIs/tipos NinjaScript autorizados.

        Fonte: corpo Markdown da regra ``ninjascript-api`` — qualquer linha
        cujo conteúdo (após ``strip``) começa com ``- `` é tratada como item
        da whitelist (descartando o marcador). A ordem original é preservada.

        Quando a regra está ausente ou seu corpo não contém itens, retorna
        lista vazia. Hermes é responsável por emitir Veto_Tecnico
        ``steering_indisponivel`` nesse caso (R6.4) — não é responsabilidade
        da engine.
        """
        if ARQUIVO_NINJASCRIPT_API not in self._regras:
            return []

        corpo = self._regras[ARQUIVO_NINJASCRIPT_API].corpo_markdown or ""
        itens: list[str] = []
        for linha in corpo.splitlines():
            stripped = linha.strip()
            if stripped.startswith("- "):
                # Remove o marcador '- ' e qualquer comentário inline com '#'.
                conteudo = stripped[2:].strip()
                # Conteúdo até o primeiro espaço/comentário para itens
                # com texto descritivo após o nome (ex: '- Strategy   # base').
                if "#" in conteudo:
                    conteudo = conteudo.split("#", 1)[0].rstrip()
                if conteudo:
                    itens.append(conteudo)
        return itens


# ---------------------------------------------------------------------------
# Coerção numérica
# ---------------------------------------------------------------------------


def _coercer_inteiro(valor: Any) -> Optional[int]:
    """Converte ``valor`` em ``int`` ou retorna ``None`` em caso de falha.

    Aceita:

    - ``int`` (mas não ``bool``, dado que ``isinstance(True, int) is True``
      em Python e queremos rejeitar booleanos como configuração de orçamento).
    - ``str`` cujo conteúdo, após ``strip``, é parseável por ``int(...)``.
    - ``float`` exato (sem parte fracionária).

    Rejeita ``None``, listas, dicts e strings malformadas.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if valor.is_integer():
            return int(valor)
        return None
    if isinstance(valor, str):
        bruto = valor.strip()
        if not bruto:
            return None
        try:
            return int(bruto)
        except ValueError:
            return None
    return None


__all__ = [
    "ORCAMENTO_TURNOS_MIN",
    "ORCAMENTO_TURNOS_MAX",
    "ORCAMENTO_TURNOS_DEFAULT",
    "ORCAMENTO_TOKENS_MIN",
    "ORCAMENTO_TOKENS_DEFAULT",
    "ARQUIVO_ORCAMENTO_TURNOS",
    "ARQUIVO_ORCAMENTO_TOKENS",
    "ARQUIVO_NINJASCRIPT_API",
    "CategoriaFalhaSteering",
    "FalhaSteering",
    "ResultadoCarregamentoSteering",
    "SteeringEngine",
    "carregar_regras",
]
