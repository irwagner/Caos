"""Failure_Handler — tratamento determinístico de falhas no Conselho CAOS.

Cobre a Task 14 do Spec ``caos-conselho-infra`` (R5.6 e R14.1–R14.5).

Três caminhos de falha são tratados aqui:

1. **Skill failure** — :func:`registrar_falha_skill` constrói um
   :class:`RegistroFalhaSkill` imutável a partir de
   ``(skill_nome, exit_code, stderr, duracao_ms, motivo)``, truncando
   ``stderr`` a 4096 caracteres (R14.1, R14.2).

2. **Modelo indisponível** — :func:`chamar_modelo_com_retries` invoca um
   ``callable_modelo`` até 3 vezes, com backoff mínimo de 2 segundos entre
   tentativas (R14.3). Considera falha quando o callable:

   - levanta :class:`TimeoutError` (ou a duração da invocação excede
     ``timeout_s_por_tentativa``) → ``falha == "timeout"``;
   - levanta qualquer outra exceção → ``falha == "transporte"``;
   - retorna ``None`` ou string vazia/só-whitespace → ``falha == "resposta-vazia"``.

3. **Agentes indisponíveis** — :class:`FailureHandler` mantém uma lista
   de :class:`StatusAgenteIndisponivel`. Quando ela ultrapassa o limiar
   (default ``2`` — estritamente mais que dois, R14.4),
   :meth:`FailureHandler.deve_abortar` retorna ``True`` e
   :meth:`FailureHandler.abortar_debate` aciona o
   :class:`~caos.council_recorder.CouncilRecorder` para persistir o
   debate parcial e a Decisao_Do_Conselho com
   ``status='abortado-por-indisponibilidade'`` (R14.5).

Convenções:

- Todas as mensagens visíveis ao usuário estão em pt-BR.
- ``time.sleep`` é o único ponto de espera; pode ser substituído via
  ``monkeypatch`` em testes para evitar atrasos reais.
- As dataclasses são ``frozen`` para prevenir mutação acidental — o
  Council_Recorder consome esses registros como evidência auditável.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from caos.council_recorder import CouncilRecorder, ResultadoGravacao
from caos.models import Debate, DecisaoDoConselho

# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Limite máximo de caracteres do ``stderr`` registrado por falha de Skill (R14.1).
LIMITE_STDERR_CHARS: int = 4096

#: Número padrão de tentativas em :func:`chamar_modelo_com_retries` (R14.3).
TENTATIVAS_PADRAO: int = 3

#: Timeout (segundos) por tentativa em :func:`chamar_modelo_com_retries` (R14.3).
TIMEOUT_PADRAO_POR_TENTATIVA_S: float = 60.0

#: Backoff mínimo (segundos) entre tentativas (R14.3).
BACKOFF_MINIMO_S: float = 2.0

#: Limiar padrão de agentes indisponíveis para abortar Debate (R14.4).
#:
#: A regra é estritamente "mais que 2" — então ``limiar=2`` significa que
#: ``deve_abortar()`` retorna True somente quando há 3 ou mais agentes na
#: lista interna.
LIMIAR_AGENTES_INDISPONIVEIS_PADRAO: int = 2

# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------


MotivoFalhaSkill = Literal["exit-code-nao-zero", "timeout"]

FalhaModelo = Literal["timeout", "transporte", "resposta-vazia"]


@dataclass(frozen=True)
class RegistroFalhaSkill:
    """Registro imutável de uma falha de invocação de Skill (R14.1, R14.2).

    O ``stderr_truncado`` é a versão de ``stderr`` cortada a no máximo
    :data:`LIMITE_STDERR_CHARS` caracteres. O Council_Recorder grava esse
    bloco no turno responsável pela Skill.
    """

    nome_skill: str
    exit_code: Optional[int]
    motivo: MotivoFalhaSkill
    stderr_truncado: str
    duracao_ms: int


@dataclass(frozen=True)
class ResultadoChamadaModelo:
    """Resultado da invocação tolerante a falhas de um modelo (R14.3).

    ``sucesso`` é ``True`` quando a primeira resposta válida foi obtida
    em ``tentativa <= max_tentativas``. ``falha`` carrega a categoria da
    *última* tentativa (relevante apenas quando ``sucesso == False``).
    ``duracao_ms`` é o tempo total acumulado de todas as tentativas
    (incluindo o backoff entre elas).
    """

    sucesso: bool
    resposta: Optional[str]
    falha: Optional[FalhaModelo]
    tentativa: int
    duracao_ms: int


@dataclass(frozen=True)
class StatusAgenteIndisponivel:
    """Representa um agente marcado como indisponível em um turno (R14.4)."""

    agente: str
    motivo: str
    turno: int


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def registrar_falha_skill(
    skill_nome: str,
    exit_code: Optional[int],
    stderr: str,
    duracao_ms: int,
    *,
    motivo: MotivoFalhaSkill,
) -> RegistroFalhaSkill:
    """Constrói um :class:`RegistroFalhaSkill` truncando ``stderr``.

    Parameters
    ----------
    skill_nome:
        Nome canônico da Skill (ex.: ``"Skill_MSBuild"``). Não pode ser
        vazio nem somente whitespace.
    exit_code:
        Código de saída observado. Pode ser ``None`` quando o processo
        nem chegou a ser iniciado (falha de spawn) ou quando o canal
        usado é um timeout — nesse caso convenciona-se ``exit_code=-1``
        no chamador.
    stderr:
        Conteúdo bruto do canal de erro do processo. Será truncado a
        :data:`LIMITE_STDERR_CHARS` caracteres.
    duracao_ms:
        Duração total da invocação até a observação da falha. Deve ser
        ``>= 0``.
    motivo:
        ``"exit-code-nao-zero"`` ou ``"timeout"``. Outros valores
        levantam :class:`ValueError`.

    Returns
    -------
    RegistroFalhaSkill
        Registro imutável pronto para serialização pelo Council_Recorder.

    Raises
    ------
    ValueError
        Quando ``skill_nome`` é vazio, ``duracao_ms`` é negativo ou
        ``motivo`` está fora do conjunto permitido.
    """
    if not isinstance(skill_nome, str) or not skill_nome.strip():
        raise ValueError(
            f"skill_nome deve ser string não-vazia; recebido {skill_nome!r}"
        )
    if duracao_ms < 0:
        raise ValueError(
            f"duracao_ms deve ser >= 0; recebido {duracao_ms!r}"
        )
    if motivo not in ("exit-code-nao-zero", "timeout"):
        raise ValueError(
            "motivo deve ser 'exit-code-nao-zero' ou 'timeout'; "
            f"recebido {motivo!r}"
        )

    # ``stderr`` pode vir como ``None`` quando o processo nem produziu
    # nada (timeout precoce). Tratamos como string vazia para preservar
    # o invariante ``isinstance(stderr_truncado, str)``.
    bruto = stderr if isinstance(stderr, str) else ""
    if len(bruto) > LIMITE_STDERR_CHARS:
        bruto = bruto[:LIMITE_STDERR_CHARS]

    return RegistroFalhaSkill(
        nome_skill=skill_nome,
        exit_code=exit_code,
        motivo=motivo,
        stderr_truncado=bruto,
        duracao_ms=duracao_ms,
    )


def chamar_modelo_com_retries(
    callable_modelo: Callable[[], Optional[str]],
    *,
    max_tentativas: int = TENTATIVAS_PADRAO,
    timeout_s_por_tentativa: float = TIMEOUT_PADRAO_POR_TENTATIVA_S,
    backoff_min_s: float = BACKOFF_MINIMO_S,
) -> ResultadoChamadaModelo:
    """Invoca ``callable_modelo`` com retries e backoff (R14.3).

    Estratégia:

    1. Para cada tentativa em ``1..max_tentativas``:

       a. Mede ``time.monotonic()`` antes e depois da invocação.
       b. Se levantar :class:`TimeoutError` ou se a duração observada
          exceder ``timeout_s_por_tentativa``, classifica como
          ``"timeout"``.
       c. Se levantar qualquer outra exceção, classifica como
          ``"transporte"``.
       d. Se retornar ``None`` ou string vazia/só-whitespace, classifica
          como ``"resposta-vazia"``.
       e. Se retornar string não-vazia, retorna sucesso imediatamente.

    2. Entre tentativas (não após a última), dorme
       ``max(backoff_min_s, BACKOFF_MINIMO_S)`` segundos.

    3. Após esgotar ``max_tentativas``, devolve ``sucesso=False`` com a
       categoria da última falha observada.

    O método ``time.sleep`` é deliberadamente simples para que testes
    consigam substituí-lo via ``monkeypatch``.

    Parameters
    ----------
    callable_modelo:
        Função sem argumentos que retorna a resposta do modelo (string)
        ou ``None``/``""`` em caso de resposta vazia. Pode levantar
        :class:`TimeoutError` para sinalizar timeout interno ou qualquer
        outra exceção para sinalizar erro de transporte.
    max_tentativas:
        Número máximo de tentativas (R14.3 fixa em 3, mas o parâmetro é
        ajustável para uso pelo orquestrador). Deve ser ``>= 1``.
    timeout_s_por_tentativa:
        Limite máximo aceitável para a duração de cada tentativa antes
        de classificá-la como timeout. Deve ser ``> 0``.
    backoff_min_s:
        Tempo mínimo de espera entre tentativas. R14.3 exige ``>= 2``.
        Valores menores são elevados ao mínimo de :data:`BACKOFF_MINIMO_S`.

    Returns
    -------
    ResultadoChamadaModelo
        Resultado consolidado da sequência de tentativas.

    Raises
    ------
    ValueError
        Quando algum parâmetro numérico está fora dos limites válidos.
    """
    if max_tentativas < 1:
        raise ValueError(
            f"max_tentativas deve ser >= 1; recebido {max_tentativas!r}"
        )
    if timeout_s_por_tentativa <= 0:
        raise ValueError(
            "timeout_s_por_tentativa deve ser > 0; "
            f"recebido {timeout_s_por_tentativa!r}"
        )

    backoff_efetivo = max(float(backoff_min_s), BACKOFF_MINIMO_S)

    inicio_total = time.monotonic()
    ultima_falha: Optional[FalhaModelo] = None
    ultima_tentativa: int = 0

    for tentativa in range(1, max_tentativas + 1):
        ultima_tentativa = tentativa
        inicio_tentativa = time.monotonic()
        falha_observada: Optional[FalhaModelo] = None
        resposta: Optional[str] = None

        try:
            resposta = callable_modelo()
        except TimeoutError:
            falha_observada = "timeout"
        except Exception:  # noqa: BLE001 — qualquer falha não-timeout é "transporte".
            falha_observada = "transporte"

        duracao_tentativa = time.monotonic() - inicio_tentativa
        # Se a tentativa demorou mais que o orçamento por tentativa,
        # reclassificamos como timeout — mesmo que ela tenha "sucesso".
        # Isso preserva a semântica do R14.3: respostas tardias são
        # tratadas como falha de timeout.
        if (
            falha_observada is None
            and duracao_tentativa > timeout_s_por_tentativa
        ):
            falha_observada = "timeout"
            resposta = None

        # Se nenhuma exceção e dentro do tempo, avalia o conteúdo.
        if falha_observada is None:
            if resposta is None or not isinstance(resposta, str) or not resposta.strip():
                falha_observada = "resposta-vazia"
                resposta = None

        if falha_observada is None:
            # Sucesso: encerra o loop sem dormir.
            duracao_ms_total = int(
                (time.monotonic() - inicio_total) * 1000
            )
            return ResultadoChamadaModelo(
                sucesso=True,
                resposta=resposta,
                falha=None,
                tentativa=tentativa,
                duracao_ms=duracao_ms_total,
            )

        ultima_falha = falha_observada

        # Aplica backoff antes da próxima tentativa, exceto após a última.
        if tentativa < max_tentativas:
            time.sleep(backoff_efetivo)

    duracao_ms_total = int((time.monotonic() - inicio_total) * 1000)
    return ResultadoChamadaModelo(
        sucesso=False,
        resposta=None,
        falha=ultima_falha,
        tentativa=ultima_tentativa,
        duracao_ms=duracao_ms_total,
    )


# ---------------------------------------------------------------------------
# FailureHandler
# ---------------------------------------------------------------------------


class FailureHandler:
    """Coordena a contagem de agentes indisponíveis e o abort de Debate.

    Parameters
    ----------
    council_recorder:
        Instância de :class:`CouncilRecorder` usada por
        :meth:`abortar_debate` para persistir os arquivos parciais e
        criar o commit dedicado (R14.5). Pode ser ``None`` quando o
        handler é usado apenas para registro e contagem (testes que
        não exercitam o caminho de abortagem).
    limiar_agentes_indisponiveis:
        Número máximo de agentes indisponíveis tolerado antes de
        :meth:`deve_abortar` passar a retornar ``True``. R14.4 exige
        que esse valor seja **estritamente menor** que a contagem para
        disparar o abort — i.e., com o default ``2``, o abort dispara
        a partir do 3º agente indisponível.
    """

    def __init__(
        self,
        *,
        council_recorder: Optional[CouncilRecorder] = None,
        limiar_agentes_indisponiveis: int = LIMIAR_AGENTES_INDISPONIVEIS_PADRAO,
    ) -> None:
        if limiar_agentes_indisponiveis < 0:
            raise ValueError(
                "limiar_agentes_indisponiveis deve ser >= 0; "
                f"recebido {limiar_agentes_indisponiveis!r}"
            )
        self._council_recorder = council_recorder
        self._limiar = int(limiar_agentes_indisponiveis)
        self._indisponiveis: list[StatusAgenteIndisponivel] = []

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def council_recorder(self) -> Optional[CouncilRecorder]:
        """Instância injetada de Council_Recorder, se houver."""
        return self._council_recorder

    @property
    def limiar(self) -> int:
        """Limiar configurado de agentes indisponíveis."""
        return self._limiar

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def marcar_agente_indisponivel(
        self, agente: str, motivo: str, turno: int
    ) -> None:
        """Adiciona ``agente`` à lista interna de indisponíveis.

        Parameters
        ----------
        agente:
            Nome do agente (ex.: ``"Cerberus"``). Não pode ser vazio.
        motivo:
            Texto livre em pt-BR explicando a indisponibilidade.
        turno:
            Número sequencial do turno em que a falha foi observada.
            Deve ser ``>= 1`` (alinhado a :class:`Turno.numero`).
        """
        if not isinstance(agente, str) or not agente.strip():
            raise ValueError(
                f"agente deve ser string não-vazia; recebido {agente!r}"
            )
        if not isinstance(motivo, str) or not motivo.strip():
            raise ValueError(
                f"motivo deve ser string não-vazia; recebido {motivo!r}"
            )
        if not isinstance(turno, int) or turno < 1:
            raise ValueError(
                f"turno deve ser inteiro >= 1; recebido {turno!r}"
            )
        self._indisponiveis.append(
            StatusAgenteIndisponivel(
                agente=agente, motivo=motivo, turno=turno
            )
        )

    def agentes_indisponiveis(self) -> list[StatusAgenteIndisponivel]:
        """Retorna uma cópia da lista de agentes indisponíveis registrados."""
        return list(self._indisponiveis)

    def deve_abortar(self) -> bool:
        """Retorna ``True`` se o limiar foi ultrapassado (R14.4).

        R14.4 exige *estritamente mais que 2* agentes indisponíveis para
        disparar o abort, então usamos ``>`` (não ``>=``).
        """
        return len(self._indisponiveis) > self._limiar

    def abortar_debate(
        self,
        debate: Debate,
        decisao_parcial: DecisaoDoConselho,
        turno_abortagem: int,
    ) -> ResultadoGravacao:
        """Persiste o Debate parcial e a Decisão como abortados (R14.4, R14.5).

        Ajusta a Decisao_Do_Conselho para:

        - ``status = "abortado-por-indisponibilidade"``;
        - ``decisao_final.rationale`` contendo o rationale original
          seguido por uma linha listando os agentes indisponíveis e o
          número do turno em que o abort foi disparado.

        Em seguida, invoca :meth:`CouncilRecorder.gravar` com o par
        ``(debate, decisao_atualizada)``. O Debate é repassado tal qual
        recebido — cabe ao chamador garantir que ``debate.status``
        e ``debate.fase_final`` reflitam a abortagem.

        Parameters
        ----------
        debate:
            Debate parcial. Deve ser válido segundo o schema Pydantic.
        decisao_parcial:
            Decisao_Do_Conselho parcial. Será copiada com updates antes
            da gravação — o objeto original permanece inalterado.
        turno_abortagem:
            Número do turno em que o abort foi disparado. Deve ser
            ``>= 1``.

        Returns
        -------
        ResultadoGravacao
            Resultado da gravação pelo Council_Recorder. ``sucesso`` é
            ``True`` quando ambos os arquivos foram escritos e o
            commit dedicado foi criado.

        Raises
        ------
        RuntimeError
            Quando :attr:`council_recorder` é ``None`` — sem Recorder
            não há como satisfazer R14.5.
        ValueError
            Quando ``turno_abortagem`` é inválido.
        """
        # Validação de inputs vem antes da checagem de Recorder, para que
        # o erro mais específico (e mais útil ao chamador) aflore primeiro.
        if not isinstance(turno_abortagem, int) or turno_abortagem < 1:
            raise ValueError(
                "turno_abortagem deve ser inteiro >= 1; "
                f"recebido {turno_abortagem!r}"
            )
        if self._council_recorder is None:
            raise RuntimeError(
                "abortar_debate requer um CouncilRecorder injetado em "
                "FailureHandler.__init__ (R14.5)"
            )

        decisao_atualizada = self._decisao_abortada(
            decisao_parcial, turno_abortagem
        )
        return self._council_recorder.gravar(debate, decisao_atualizada)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _decisao_abortada(
        self,
        decisao_parcial: DecisaoDoConselho,
        turno_abortagem: int,
    ) -> DecisaoDoConselho:
        """Devolve uma cópia da decisão com status e rationale ajustados.

        O rationale resultante preserva o texto original (para não perder
        evidência) e acrescenta um sufixo determinístico contendo:

        - a lista de agentes indisponíveis em ordem alfabética;
        - o número do turno em que o abort foi disparado.

        ``model_copy(update=...)`` é usado em vez de mutação direta
        porque o orquestrador pode reter referências ao objeto original
        (por exemplo, para diagnóstico em testes).
        """
        nomes_ordenados = sorted({s.agente for s in self._indisponiveis})
        sufixo = (
            "\n\n[Aborto por indisponibilidade] "
            f"agentes_indisponiveis={nomes_ordenados}; "
            f"turno_abortagem={turno_abortagem}."
        )
        rationale_original = decisao_parcial.decisao_final.rationale.rstrip()
        rationale_novo = rationale_original + sufixo

        decisao_final_atualizada = decisao_parcial.decisao_final.model_copy(
            update={"rationale": rationale_novo}
        )
        return decisao_parcial.model_copy(
            update={
                "status": "abortado-por-indisponibilidade",
                "decisao_final": decisao_final_atualizada,
            }
        )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

__all__ = [
    # Constantes
    "LIMITE_STDERR_CHARS",
    "TENTATIVAS_PADRAO",
    "TIMEOUT_PADRAO_POR_TENTATIVA_S",
    "BACKOFF_MINIMO_S",
    "LIMIAR_AGENTES_INDISPONIVEIS_PADRAO",
    # Tipos
    "MotivoFalhaSkill",
    "FalhaModelo",
    "RegistroFalhaSkill",
    "ResultadoChamadaModelo",
    "StatusAgenteIndisponivel",
    # Funções
    "registrar_falha_skill",
    "chamar_modelo_com_retries",
    # Classe
    "FailureHandler",
]
