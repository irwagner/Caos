"""Data_Manifest_Manager — orquestra build/verify do ``manifesto.json``.

Cobre os requisitos R15.1 a R15.6 do ``requirements.md`` e a linha
correspondente da tabela em ``design.md`` seção 6 (Data_Manifest_Manager).

Responsabilidades:

- ``build``: varre ``raiz_dados`` via :class:`SkillDataInspector`, ordena
  alfabeticamente, serializa em JSON canônico (``indent=2``,
  ``sort_keys=True``, ``ensure_ascii=False``) e grava de forma atômica
  (escreve em ``manifesto.json.tmp`` e renomeia).
- ``verify``: invoca :class:`SkillDataIntegrity` e devolve um wrapper
  :class:`ResultadoVerificacao` com sumário humano em pt-BR.

Formato JSON do manifesto (especificação canônica)::

    {
      "geracao": {
        "data_iso8601_utc": "2026-05-14T12:00:00Z",
        "instrumento": "MNQ"
      },
      "entradas": [
        {
          "nome_arquivo": "1m/MNQ-2026-01.csv",
          "tamanho_bytes": 1234,
          "mtime": "2026-05-14T11:55:00Z",
          "num_linhas": 100,
          "hash_sha256": "...",
          "periodo_inicial": "2026-01-02T13:30:00Z",
          "periodo_final":   "2026-01-29T20:00:00Z",
          "instrumento": "MNQ"
        }
      ],
      "falhas": [
        {"caminho_relativo": "...", "categoria": "...", "mensagem": "..."}
      ]
    }

A escolha de ``ensure_ascii=False`` preserva caracteres acentuados em
nomes de arquivo e mensagens de falha sem expandi-los para
``\\uXXXX``. Estamos em Windows + UTF-8 (regra ``plataforma-windows-cmd``),
então não há risco de problemas de codificação.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from caos.skills.data_inspector import (
    FalhaInspecao,
    SkillDataInspector,
)
from caos.skills.data_integrity import (
    ResultadoIntegridade,
    SkillDataIntegrity,
)
from caos.models import EntradaManifesto

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Nome canônico do arquivo de manifesto, sempre dentro de ``raiz_dados``.
NOME_MANIFESTO: str = "manifesto.json"

#: Sufixo do arquivo temporário usado na escrita atômica.
_SUFIXO_TMP: str = ".tmp"


# ---------------------------------------------------------------------------
# Modelos públicos de retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoBuild:
    """Resultado de :meth:`DataManifestManager.build`.

    Attributes
    ----------
    caminho_manifesto:
        Caminho absoluto do arquivo gravado.
    entradas:
        Lista de entradas que foram persistidas no manifesto.
    falhas:
        Falhas de inspeção registradas durante a varredura — gravadas no
        próprio JSON do manifesto sob a chave ``falhas`` (R15.3).
    escrito:
        ``True`` quando o arquivo foi gravado neste ``build``. Sempre
        ``True`` em fluxo normal; ``False`` reservado para futuras
        otimizações de "no-op se nada mudou".
    """

    caminho_manifesto: Path
    entradas: list[EntradaManifesto]
    falhas: list[FalhaInspecao]
    escrito: bool


@dataclass(frozen=True)
class ResultadoVerificacao:
    """Resultado de :meth:`DataManifestManager.verify`.

    Empacota :class:`ResultadoIntegridade` com um ``sumario_humano`` em
    pt-BR para a CLI.
    """

    integridade: ResultadoIntegridade
    sumario_humano: str = ""

    @property
    def ok(self) -> bool:
        return self.integridade.ok


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class DataManifestManager:
    """Gerencia o ciclo de vida do ``manifesto.json`` em ``raiz_dados``.

    Parameters
    ----------
    raiz_dados:
        Diretório alvo (``dados/MNQ/`` no Spec 1).
    caminho_manifesto:
        Override opcional do caminho do manifesto. Default:
        ``raiz_dados / "manifesto.json"``.
    invocador:
        Identificador propagado para as Skills internas (auditoria).
    """

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
            else raiz_resolvida / NOME_MANIFESTO
        )
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

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build(self, *, instrumento: str = "MNQ") -> ResultadoBuild:
        """Constrói/atualiza o ``manifesto.json``.

        Parameters
        ----------
        instrumento:
            Identificador do instrumento (default ``"MNQ"``). Propagado para
            as :class:`EntradaManifesto` produzidas e para o bloco
            ``geracao`` do JSON.
        """
        inspector = SkillDataInspector(
            invocador=self._invocador,
            raiz_dados=self._raiz_dados,
        )
        resultado = inspector.varrer_diretorio(instrumento=instrumento)

        # Ordenação alfabética por nome_arquivo é exigida para estabilidade
        # do JSON canônico (Property 10 — Data Manifest Integrity).
        entradas_ordenadas = sorted(
            resultado.entradas, key=lambda e: e.nome_arquivo
        )
        falhas_ordenadas = sorted(
            resultado.falhas, key=lambda f: f.caminho_relativo
        )

        payload = {
            "geracao": {
                "data_iso8601_utc": _agora_utc_iso(),
                "instrumento": instrumento,
            },
            "entradas": [
                _entrada_para_dict(e) for e in entradas_ordenadas
            ],
            "falhas": [
                _falha_para_dict(f) for f in falhas_ordenadas
            ],
        }

        self._gravar_atomico(payload)

        return ResultadoBuild(
            caminho_manifesto=self._caminho_manifesto,
            entradas=entradas_ordenadas,
            falhas=falhas_ordenadas,
            escrito=True,
        )

    def verify(self) -> ResultadoVerificacao:
        """Verifica integridade contra ``manifesto.json``.

        Wrapper sobre :meth:`SkillDataIntegrity.validar` que adiciona um
        ``sumario_humano`` em pt-BR para a CLI. Em caso de manifesto
        ausente, devolve um :class:`ResultadoVerificacao` com erro_global
        em vez de levantar exceção, para uniformizar o caminho de saída.
        """
        if not self._caminho_manifesto.is_file():
            integridade = ResultadoIntegridade(
                ok=False,
                erro_global=(
                    f"manifesto-ausente: {self._caminho_manifesto} não existe"
                ),
            )
            sumario = (
                f"manifesto.json ausente em {self._caminho_manifesto}.\n"
                "Execute 'caos manifesto build' primeiro."
            )
            return ResultadoVerificacao(
                integridade=integridade, sumario_humano=sumario
            )

        skill = SkillDataIntegrity(
            invocador=self._invocador,
            raiz_dados=self._raiz_dados,
            caminho_manifesto=self._caminho_manifesto,
        )
        integridade = skill.validar()
        return ResultadoVerificacao(
            integridade=integridade,
            sumario_humano=_resumir_integridade(integridade),
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _gravar_atomico(self, payload: dict[str, Any]) -> None:
        """Escreve o JSON canônico em ``.tmp`` e faz ``replace``.

        ``Path.replace`` é atômico no Windows quando origem e destino estão
        no mesmo volume (caso aqui — ambos em ``raiz_dados``).
        """
        bruto = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        # Newline final padrão para arquivos de texto Unix-friendly,
        # consumível por diff e Git sem warnings.
        if not bruto.endswith("\n"):
            bruto += "\n"

        tmp = self._caminho_manifesto.with_suffix(
            self._caminho_manifesto.suffix + _SUFIXO_TMP
        )
        # Garante diretório-pai existente (caso raiz_dados tenha sido
        # criada vazia mas o manifesto seja escrito em subpasta — não é o
        # caso default, mas é barato).
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(bruto, encoding="utf-8")
        tmp.replace(self._caminho_manifesto)


# ---------------------------------------------------------------------------
# Serialização
# ---------------------------------------------------------------------------


def _entrada_para_dict(entrada: EntradaManifesto) -> dict[str, Any]:
    """Converte :class:`EntradaManifesto` em dict JSON-serializable."""
    return {
        "nome_arquivo": entrada.nome_arquivo,
        "tamanho_bytes": entrada.tamanho_bytes,
        "mtime": _datetime_para_iso(entrada.mtime),
        "num_linhas": entrada.num_linhas,
        "hash_sha256": entrada.hash_sha256,
        "periodo_inicial": (
            _datetime_para_iso(entrada.periodo_inicial)
            if entrada.periodo_inicial is not None
            else None
        ),
        "periodo_final": (
            _datetime_para_iso(entrada.periodo_final)
            if entrada.periodo_final is not None
            else None
        ),
        "instrumento": entrada.instrumento,
    }


def _falha_para_dict(falha: FalhaInspecao) -> dict[str, Any]:
    return {
        "caminho_relativo": falha.caminho_relativo,
        "categoria": falha.categoria,
        "mensagem": falha.mensagem,
    }


def _datetime_para_iso(valor: datetime) -> str:
    """Serializa ``datetime`` UTC como ``YYYY-MM-DDTHH:MM:SSZ``.

    Garante UTC (offset zero). Se o ``datetime`` chega com outro offset,
    converte para UTC. ``microsecond`` é zerado para estabilidade do hash
    do manifesto entre re-builds.
    """
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    valor_utc = valor.astimezone(timezone.utc).replace(microsecond=0)
    return valor_utc.isoformat().replace("+00:00", "Z")


def _agora_utc_iso() -> str:
    """ISO 8601 UTC (sufixo ``Z``) sem microssegundos."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Sumário humano (CLI-friendly)
# ---------------------------------------------------------------------------


def _resumir_integridade(integridade: ResultadoIntegridade) -> str:
    """Formata o resultado em pt-BR para exibição na CLI."""
    if integridade.ok:
        return "Manifesto íntegro: nenhum desvio detectado."

    linhas: list[str] = []
    if integridade.erro_global is not None:
        linhas.append(f"ERRO GLOBAL: {integridade.erro_global}")
        return "\n".join(linhas)

    if integridade.divergencias:
        linhas.append(
            f"Divergências de hash: {len(integridade.divergencias)}"
        )
        for d in integridade.divergencias:
            linhas.append(
                f"  - {d.nome_arquivo} ({d.motivo})"
            )

    if integridade.arquivos_ausentes:
        linhas.append(
            f"Arquivos no manifesto mas ausentes em disco: "
            f"{len(integridade.arquivos_ausentes)}"
        )
        for nome in integridade.arquivos_ausentes:
            linhas.append(f"  - {nome}")

    if integridade.nao_registrados:
        linhas.append(
            f"Arquivos em disco fora do manifesto: "
            f"{len(integridade.nao_registrados)}"
        )
        for nome in integridade.nao_registrados:
            linhas.append(f"  - {nome}")

    return "\n".join(linhas)


__all__ = [
    "NOME_MANIFESTO",
    "DataManifestManager",
    "ResultadoBuild",
    "ResultadoVerificacao",
]
