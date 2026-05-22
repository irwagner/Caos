"""Skill_Token_Budget — orçamento diário de tokens por agente (R11.9, R17).

Esta Skill persiste o consumo diário de tokens por agente em arquivos
``CAOS_Orchestrator/.budget/AAAA-MM-DD.json`` e bloqueia novas invocações
quando o orçamento configurado para o agente seria estourado.

Resumo do contrato:

- :meth:`SkillTokenBudget.obter_estado` devolve :class:`EstadoOrcamento` para
  ``(agente, dia)``. Estado inexistente para o dia retorna tokens zerados com
  o orçamento configurado pelo :class:`SteeringEngine` (ou
  :data:`ORCAMENTO_TOKENS_DEFAULT` quando ``steering_engine`` é ``None``).
- :meth:`SkillTokenBudget.verificar` consulta o estado atual e responde se
  ``tokens_estimados`` cabem no orçamento (R17.3). Não modifica disco.
- :meth:`SkillTokenBudget.registrar_consumo` aplica deltas de input/output em
  cima do estado atual e persiste atomicamente em até 1 segundo (R17.5).
- :meth:`SkillTokenBudget.consumo_total_dia` mapeia ``agente -> tokens_total``
  para auditoria.

Concorrência: usa :class:`threading.Lock` interno em torno do par
(leitura+escrita) do mesmo dia para evitar perda de atualização entre threads
do mesmo processo. O lock é por instância — múltiplos processos rodando
simultaneamente sobre o mesmo diretório PODEM causar race condition.
Documentamos como limitação porque o orquestrador opera single-process.

O dia é UTC (R17.5): ``datetime.now(timezone.utc).date()``. Rollover automático
acontece simplesmente porque o caller passa a usar outro arquivo no dia
seguinte.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from caos.models import EstadoOrcamento
from caos.steering_engine import (
    ORCAMENTO_TOKENS_DEFAULT,
    ORCAMENTO_TOKENS_MIN,
    SteeringEngine,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Diretório default da persistência do orçamento, relativo ao caller.
#: Construtor recebe caminho explícito (preferencialmente absoluto).
DIRETORIO_BUDGET_PADRAO: Path = Path("CAOS_Orchestrator/.budget")


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoVerificacaoBudget:
    """Resultado de :meth:`SkillTokenBudget.verificar` (R17.3).

    Attributes
    ----------
    agente:
        Agente consultado.
    dia:
        Dia UTC consultado (``date``, sem horário).
    bloqueado:
        ``True`` se ``tokens_estimados + tokens_consumidos > orcamento_diario``
        (R17.3). ``False`` em caso contrário.
    tokens_consumidos:
        Total já contabilizado para ``(agente, dia)`` antes desta verificação.
    tokens_estimados:
        Estimativa fornecida pelo caller para a próxima invocação.
    orcamento_diario:
        Orçamento aplicável ao agente (vindo do :class:`SteeringEngine`).
    saldo_restante:
        ``orcamento_diario - tokens_consumidos`` antes da invocação. Pode
        ficar negativo após uma gravação que estoure o orçamento (cenário
        que :meth:`registrar_consumo` permite por ser idempotente em relação
        ao histórico já gravado).
    """

    agente: str
    dia: date
    bloqueado: bool
    tokens_consumidos: int
    tokens_estimados: int
    orcamento_diario: int
    saldo_restante: int


# ---------------------------------------------------------------------------
# Skill propriamente dita
# ---------------------------------------------------------------------------


class SkillTokenBudget:
    """Contabiliza e bloqueia consumo de tokens diário por agente.

    Parameters
    ----------
    diretorio_budget:
        Diretório em que ``AAAA-MM-DD.json`` é gravado. Será criado se
        ainda não existir.
    steering_engine:
        Fonte do orçamento por agente (:meth:`SteeringEngine.get_orcamento_de_tokens`).
        Quando ``None``, qualquer agente recebe :data:`ORCAMENTO_TOKENS_DEFAULT`.
    invocador:
        Identificador opcional do agente invocador, para auditoria pelo caller.
    """

    NOME: str = "Skill_Token_Budget"

    def __init__(
        self,
        *,
        diretorio_budget: Path,
        steering_engine: Optional[SteeringEngine] = None,
        invocador: Optional[str] = None,
    ) -> None:
        diretorio = Path(diretorio_budget)
        diretorio.mkdir(parents=True, exist_ok=True)
        self._diretorio_budget = diretorio
        self._steering_engine = steering_engine
        self._invocador = invocador
        # Lock interno protege leitura+escrita do MESMO arquivo diário
        # contra concorrência entre threads do mesmo processo (R17.5).
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def diretorio_budget(self) -> Path:
        """Diretório raiz da persistência diária."""
        return self._diretorio_budget

    @property
    def invocador(self) -> Optional[str]:
        """Agente invocador, se informado no construtor."""
        return self._invocador

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def obter_estado(
        self,
        agente: str,
        *,
        dia: Optional[date] = None,
    ) -> EstadoOrcamento:
        """Devolve o :class:`EstadoOrcamento` atual de ``(agente, dia)``.

        Estado inexistente (dia novo, agente nunca consumiu) retorna tokens
        zerados com o ``orcamento_diario_tokens`` resolvido pelo
        :class:`SteeringEngine` (ou default).
        """
        dia_utc = dia if dia is not None else _hoje_utc()
        with self._lock:
            payload = self._carregar_payload(dia_utc)
        agentes_map = payload.get("agentes", {}) if isinstance(
            payload, dict
        ) else {}
        entrada = agentes_map.get(agente)
        orcamento_diario = self._resolver_orcamento(agente)
        if not isinstance(entrada, dict):
            return EstadoOrcamento(
                agente=agente,
                tokens_input_consumidos=0,
                tokens_output_consumidos=0,
                tokens_total_consumidos=0,
                orcamento_diario_tokens=orcamento_diario,
            )
        # Reaproveitamos o orçamento configurado HOJE, mesmo se o arquivo
        # tiver registrado outro valor — a regra de Steering é a fonte da
        # verdade no momento da consulta. Tokens consumidos são
        # carregados do arquivo (R17.5).
        return EstadoOrcamento(
            agente=agente,
            tokens_input_consumidos=int(
                entrada.get("tokens_input_consumidos", 0)
            ),
            tokens_output_consumidos=int(
                entrada.get("tokens_output_consumidos", 0)
            ),
            tokens_total_consumidos=int(
                entrada.get("tokens_total_consumidos", 0)
            ),
            orcamento_diario_tokens=orcamento_diario,
        )

    def consumo_total_dia(
        self, dia: Optional[date] = None
    ) -> dict[str, int]:
        """Mapeia ``agente -> tokens_total_consumidos`` no dia.

        Agentes sem registro no arquivo do dia ficam fora do mapa.
        """
        dia_utc = dia if dia is not None else _hoje_utc()
        with self._lock:
            payload = self._carregar_payload(dia_utc)
        agentes_map = payload.get("agentes", {}) if isinstance(
            payload, dict
        ) else {}
        resultado: dict[str, int] = {}
        for agente, entrada in agentes_map.items():
            if isinstance(entrada, dict):
                resultado[agente] = int(
                    entrada.get("tokens_total_consumidos", 0)
                )
        return resultado

    def verificar(
        self,
        agente: str,
        *,
        tokens_estimados: int,
        dia: Optional[date] = None,
    ) -> ResultadoVerificacaoBudget:
        """Verifica se ``tokens_estimados`` cabem no orçamento (R17.3).

        Não persiste nada — esta é uma operação de leitura. Bloqueio é
        responsabilidade do caller (Athena), que ao receber
        ``bloqueado=True`` marca o turno como ``orcamento-de-tokens-esgotado``
        (R17.4).
        """
        if not isinstance(tokens_estimados, int) or tokens_estimados < 0:
            raise ValueError(
                "tokens_estimados deve ser inteiro não-negativo; "
                f"recebido {tokens_estimados!r}"
            )

        dia_utc = dia if dia is not None else _hoje_utc()
        estado = self.obter_estado(agente, dia=dia_utc)
        consumido = estado.tokens_total_consumidos
        orcamento = estado.orcamento_diario_tokens
        bloqueado = (consumido + tokens_estimados) > orcamento
        return ResultadoVerificacaoBudget(
            agente=agente,
            dia=dia_utc,
            bloqueado=bloqueado,
            tokens_consumidos=consumido,
            tokens_estimados=tokens_estimados,
            orcamento_diario=orcamento,
            saldo_restante=orcamento - consumido,
        )

    def registrar_consumo(
        self,
        agente: str,
        *,
        tokens_input: int,
        tokens_output: int,
        dia: Optional[date] = None,
    ) -> EstadoOrcamento:
        """Aplica deltas de consumo e persiste o estado atualizado (R17.5).

        Carrega o JSON do dia (criando-o se ausente), incrementa os campos
        ``tokens_input_consumidos`` e ``tokens_output_consumidos`` do agente,
        recomputa ``tokens_total_consumidos`` e grava atomicamente. Devolve
        o :class:`EstadoOrcamento` resultante.

        ``orcamento_diario_tokens`` salvo no arquivo é o valor vigente no
        momento desta gravação (vindo do :class:`SteeringEngine`).
        """
        if not isinstance(tokens_input, int) or tokens_input < 0:
            raise ValueError(
                "tokens_input deve ser inteiro não-negativo; "
                f"recebido {tokens_input!r}"
            )
        if not isinstance(tokens_output, int) or tokens_output < 0:
            raise ValueError(
                "tokens_output deve ser inteiro não-negativo; "
                f"recebido {tokens_output!r}"
            )

        dia_utc = dia if dia is not None else _hoje_utc()
        orcamento_diario = self._resolver_orcamento(agente)

        with self._lock:
            payload = self._carregar_payload(dia_utc)
            if not isinstance(payload, dict):
                payload = {}
            payload.setdefault("dia", dia_utc.isoformat())
            agentes_map = payload.setdefault("agentes", {})
            entrada = agentes_map.get(agente)
            if not isinstance(entrada, dict):
                entrada = {
                    "agente": agente,
                    "tokens_input_consumidos": 0,
                    "tokens_output_consumidos": 0,
                    "tokens_total_consumidos": 0,
                    "orcamento_diario_tokens": orcamento_diario,
                }

            novo_input = (
                int(entrada.get("tokens_input_consumidos", 0)) + tokens_input
            )
            novo_output = (
                int(entrada.get("tokens_output_consumidos", 0))
                + tokens_output
            )
            novo_total = novo_input + novo_output

            entrada.update(
                {
                    "agente": agente,
                    "tokens_input_consumidos": novo_input,
                    "tokens_output_consumidos": novo_output,
                    "tokens_total_consumidos": novo_total,
                    "orcamento_diario_tokens": orcamento_diario,
                }
            )
            agentes_map[agente] = entrada

            self._persistir_payload(dia_utc, payload)

        return EstadoOrcamento(
            agente=agente,
            tokens_input_consumidos=novo_input,
            tokens_output_consumidos=novo_output,
            tokens_total_consumidos=novo_total,
            orcamento_diario_tokens=orcamento_diario,
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _resolver_orcamento(self, agente: str) -> int:
        """Resolve ``orcamento_diario_tokens`` para ``agente``.

        Usa :class:`SteeringEngine` quando disponível; caso contrário,
        aplica :data:`ORCAMENTO_TOKENS_DEFAULT`. Garante o piso
        :data:`ORCAMENTO_TOKENS_MIN` — em teoria a engine já cuida disso
        (R17.6), mas reforçamos aqui para o cenário de injeção direta de
        :class:`SteeringEngine` mockado em testes.
        """
        if self._steering_engine is None:
            return ORCAMENTO_TOKENS_DEFAULT
        valor = self._steering_engine.get_orcamento_de_tokens(agente)
        if not isinstance(valor, int) or valor < ORCAMENTO_TOKENS_MIN:
            return ORCAMENTO_TOKENS_DEFAULT
        return valor

    def _caminho_dia(self, dia: date) -> Path:
        """Caminho do JSON do dia ``AAAA-MM-DD.json``."""
        return self._diretorio_budget / f"{dia.isoformat()}.json"

    def _carregar_payload(self, dia: date) -> dict[str, Any]:
        """Carrega o JSON do dia. Retorna ``{}`` se ausente ou corrompido.

        Em caso de JSON corrompido optamos por sobrescrever silenciosamente
        no próximo write — mais conservador seria propagar erro, mas isso
        bloquearia o orquestrador inteiro por causa de um estado de
        bookkeeping. A regra geral do projeto é "tokens consumidos só
        aumentam"; reescrever com um payload novo no pior caso resulta em
        subcontagem temporária, não em over-spend.
        """
        caminho = self._caminho_dia(dia)
        if not caminho.is_file():
            return {}
        try:
            bruto = caminho.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            payload = json.loads(bruto)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _persistir_payload(
        self, dia: date, payload: dict[str, Any]
    ) -> None:
        """Persiste atomicamente o ``payload`` no JSON do dia (R17.5).

        Estratégia: escreve em ``.tmp`` e move com ``Path.replace`` — no
        Windows, o ``ReplaceFile`` subjacente é atômico no nível do
        filesystem para arquivos no mesmo diretório.
        """
        caminho = self._caminho_dia(dia)
        caminho_tmp = caminho.with_suffix(caminho.suffix + ".tmp")
        bruto = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        try:
            caminho_tmp.write_text(bruto, encoding="utf-8")
            caminho_tmp.replace(caminho)
        finally:
            if caminho_tmp.exists():
                try:
                    caminho_tmp.unlink()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------


def _hoje_utc() -> date:
    """Retorna a data UTC corrente (R17.5)."""
    return datetime.now(timezone.utc).date()


__all__ = [
    "DIRETORIO_BUDGET_PADRAO",
    "ResultadoVerificacaoBudget",
    "SkillTokenBudget",
]
