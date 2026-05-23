"""Resolução de fontes de dados em ``dados/MNQ/<contrato>/<granularidade>/<serie>.csv``.

Camada fina entre o CLI/Engine e o :class:`Skill_Data_Reader`. Recebe
identificadores de alto nível (``contrato``, ``granularidade``,
``serie``) e devolve o ``Path`` absoluto do CSV correspondente.

Estrutura esperada de ``dados/MNQ/`` (definida em ``dados/MNQ/README.md``):

```
dados/MNQ/
├── MNQ_<MM>-<YY>/        # ex: MNQ_03-26
│   ├── minute/
│   │   ├── ask.csv
│   │   ├── bid.csv
│   │   └── last.csv
│   ├── day/
│   │   ├── ask.csv
│   │   ├── bid.csv
│   │   └── last.csv
│   └── tick/             # opcional, futuro
│       ├── ask.csv
│       ├── bid.csv
│       └── last.csv
└── manifesto.json
```

Convenções (Spec 2 + Spec 5 — refator pós-coleta de dados reais):

- ``contrato`` segue regex ``^MNQ_(03|06|09|12)-\d{2}$`` (CME publica
  apenas vencimentos trimestrais; ano de 2 dígitos).
- ``granularidade`` é literal: ``"minute"`` ou ``"day"`` (``tick`` será
  adicionado quando o usuário exportar).
- ``serie`` é literal: ``"ask"``, ``"bid"`` ou ``"last"``.

Sem dependência do runtime do NinjaTrader 8 — é puro filesystem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constantes e tipos
# ---------------------------------------------------------------------------

#: Granularidades suportadas pelo Walk-Forward (Spec 2). ``tick`` reservado
#: para extensão futura (estratégias de order flow).
Granularidade = Literal["minute", "day", "tick"]

#: Séries disponíveis em cada contrato/granularidade.
SerieTrade = Literal["ask", "bid", "last"]

GRANULARIDADES_VALIDAS: tuple[str, ...] = ("minute", "day", "tick")
SERIES_VALIDAS: tuple[str, ...] = ("ask", "bid", "last")

#: Regex do nome canônico de contrato (``MNQ_03-26`` etc.). CME só publica
#: 03/06/09/12; aceitamos qualquer ano de 2 dígitos para preparar 2025-2099.
_REGEX_CONTRATO = re.compile(r"^MNQ_(03|06|09|12)-\d{2}$")

#: Subdiretório padrão dos dados do MNQ a partir da raiz do workspace.
DIR_RAIZ_MNQ_RELATIVO: Path = Path("dados") / "MNQ"


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------


class FonteDadosError(RuntimeError):
    """Erro tipificado da camada de fontes de dados.

    Categorias estáveis:

    - ``contrato-invalido``: nome de contrato fora do padrão.
    - ``granularidade-invalida``: granularidade desconhecida.
    - ``serie-invalida``: série desconhecida.
    - ``arquivo-ausente``: arquivo CSV esperado não está presente.
    - ``raiz-invalida``: raiz do workspace ou de dados inexistente.
    """

    def __init__(self, categoria: str, mensagem: str) -> None:
        self.categoria = categoria
        self.mensagem = mensagem
        super().__init__(f"{categoria}: {mensagem}")


# ---------------------------------------------------------------------------
# Resolução
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FonteCsv:
    """Endereçamento canônico de um CSV de mercado.

    Contém os 3 identificadores de alto nível (``contrato``,
    ``granularidade``, ``serie``) e o ``caminho`` absoluto resolvido.
    Usado como entrada do :class:`SkillDataReader` quando o caller
    quer um arquivo específico em vez de varredura recursiva.
    """

    contrato: str
    granularidade: Granularidade
    serie: SerieTrade
    caminho: Path

    def existe(self) -> bool:
        """``True`` se o arquivo está presente no disco."""
        return self.caminho.is_file()


def validar_contrato(contrato: str) -> None:
    """Valida o nome do contrato. Levanta ``FonteDadosError`` em violação."""
    if not isinstance(contrato, str) or not _REGEX_CONTRATO.match(contrato):
        raise FonteDadosError(
            "contrato-invalido",
            f"contrato {contrato!r} deve casar regex ^MNQ_(03|06|09|12)-\\d{{2}}$",
        )


def validar_granularidade(granularidade: str) -> None:
    if granularidade not in GRANULARIDADES_VALIDAS:
        raise FonteDadosError(
            "granularidade-invalida",
            f"granularidade {granularidade!r} deve ser uma de {list(GRANULARIDADES_VALIDAS)}",
        )


def validar_serie(serie: str) -> None:
    if serie not in SERIES_VALIDAS:
        raise FonteDadosError(
            "serie-invalida",
            f"serie {serie!r} deve ser uma de {list(SERIES_VALIDAS)}",
        )


def resolver_fonte(
    *,
    raiz_workspace: Path,
    contrato: str,
    granularidade: str,
    serie: str = "last",
) -> FonteCsv:
    """Resolve ``contrato/granularidade/serie`` no path absoluto do CSV.

    Não verifica se o arquivo existe (use :meth:`FonteCsv.existe`); apenas
    monta o caminho canônico e valida os identificadores.

    Raises
    ------
    FonteDadosError
        Quando ``contrato``, ``granularidade`` ou ``serie`` violam o
        contrato declarado, ou quando ``raiz_workspace`` não é diretório.
    """
    raiz = Path(raiz_workspace).expanduser().resolve()
    if not raiz.is_dir():
        raise FonteDadosError(
            "raiz-invalida",
            f"raiz_workspace {raiz_workspace!r} não é um diretório existente",
        )
    validar_contrato(contrato)
    validar_granularidade(granularidade)
    validar_serie(serie)

    caminho = (
        raiz
        / DIR_RAIZ_MNQ_RELATIVO
        / contrato
        / granularidade
        / f"{serie}.csv"
    )
    return FonteCsv(
        contrato=contrato,
        granularidade=granularidade,  # type: ignore[arg-type]
        serie=serie,  # type: ignore[arg-type]
        caminho=caminho.resolve(),
    )


def listar_contratos_disponiveis(raiz_workspace: Path) -> list[str]:
    """Lista contratos com diretório criado em ``dados/MNQ/``.

    Útil para CLI ``caos walk-forward run`` autocompletar e para o
    Conselho saber sobre quais contratos pode debater.

    Não exige que os CSVs estejam presentes — apenas que o diretório
    exista. Filtra por regex canônico, então diretórios fora do padrão
    são silenciosamente ignorados.
    """
    raiz = Path(raiz_workspace).expanduser().resolve()
    raiz_mnq = raiz / DIR_RAIZ_MNQ_RELATIVO
    if not raiz_mnq.is_dir():
        return []
    contratos: list[str] = []
    for entrada in sorted(raiz_mnq.iterdir()):
        if entrada.is_dir() and _REGEX_CONTRATO.match(entrada.name):
            contratos.append(entrada.name)
    return contratos


def listar_csvs_existentes(raiz_workspace: Path, contrato: str) -> list[FonteCsv]:
    """Lista todos os CSVs presentes para ``contrato`` (todas
    granularidades × todas séries).

    Devolve apenas as :class:`FonteCsv` cujo arquivo existe no disco.
    Útil para o Skill_Data_Integrity descobrir o universo a hashear.
    """
    validar_contrato(contrato)
    raiz = Path(raiz_workspace).expanduser().resolve()
    if not raiz.is_dir():
        raise FonteDadosError(
            "raiz-invalida",
            f"raiz_workspace {raiz_workspace!r} não é um diretório existente",
        )
    presentes: list[FonteCsv] = []
    for granularidade in GRANULARIDADES_VALIDAS:
        for serie in SERIES_VALIDAS:
            fonte = resolver_fonte(
                raiz_workspace=raiz,
                contrato=contrato,
                granularidade=granularidade,
                serie=serie,
            )
            if fonte.existe():
                presentes.append(fonte)
    return presentes


__all__ = [
    "DIR_RAIZ_MNQ_RELATIVO",
    "FonteCsv",
    "FonteDadosError",
    "GRANULARIDADES_VALIDAS",
    "Granularidade",
    "SERIES_VALIDAS",
    "SerieTrade",
    "listar_contratos_disponiveis",
    "listar_csvs_existentes",
    "resolver_fonte",
    "validar_contrato",
    "validar_granularidade",
    "validar_serie",
]
