"""RelatorioWriter — serialização de Resultado_Walk_Forward (Spec 2 — Task 7).

Cobre **R8** do ``requirements.md``:

- R8.1: gerar arquivo Markdown com frontmatter compatível com
  :class:`caos.models.NotaZettel` (área ``Decisoes_do_Conselho``).
- R8.2: o Markdown contém tabela das métricas por janela e o agregado,
  em pt-BR.

Design (Sec 4 — RelatorioWriter; Sec 6 — Outputs):
- Escreve dois arquivos por execução em
  ``<raiz_saida>/<identificador>/``:
  - ``resultado.json``: JSON canônico determinístico
    (``indent=2``, ``sort_keys=True``, ``ensure_ascii=False``) — mesma
    convenção de :mod:`caos.data_manifest` e :mod:`caos.skills.token_budget`.
  - ``relatorio.md``: Markdown human-readable com frontmatter YAML
    (``yaml.safe_dump(..., sort_keys=True)``) compatível com
    :class:`NotaZettel`.
- Escrita é atômica (``arquivo.tmp`` + ``Path.replace``), mesmo padrão
  de :mod:`caos.council_recorder`.
- Quando ``commit_council=True``, o writer sintetiza um par mínimo
  ``(Debate, DecisaoDoConselho)`` a partir do
  :class:`ResultadoWalkForward` e invoca
  :meth:`caos.council_recorder.CouncilRecorder.gravar`. Para esse modo,
  o writer DEVE ser construído com ``recorder=...`` — caso contrário,
  :class:`ValueError` é levantado.

Convenções: pt-BR (R3.2 do Spec 1), Pydantic v2, Windows + cmd.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from caos.council_recorder import CouncilRecorder, ResultadoGravacao
from caos.models import (
    Debate,
    DecisaoDoConselho,
    DecisaoFinal,
    Proposta,
)
from caos.walk_forward.models import ResultadoJanela, ResultadoWalkForward

# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Subdiretório-padrão de saída (relativo à raiz ``05_BACKTEST/``).
SUBDIR_RELATORIOS: str = "relatorios"

#: Nome canônico do arquivo JSON dentro de ``<identificador>/``.
NOME_ARQUIVO_JSON: str = "resultado.json"

#: Nome canônico do arquivo Markdown dentro de ``<identificador>/``.
NOME_ARQUIVO_MD: str = "relatorio.md"

#: Área NotaZettel destino do relatório (R8.1).
AREA_NOTA_ZETTEL: str = "Decisoes_do_Conselho"

#: Agente autor padrão das notas Zettel geradas pelo Walk-Forward.
#: Athena curadora dos resultados (Spec 1, regra de steering).
AGENTE_AUTOR_PADRAO: str = "Athena"

#: Modelo LLM associado ao Athena na síntese de Debate/Decisão.
#: Mantém compatibilidade com :data:`caos.models.MODELOS_PERMITIDOS`.
MODELO_ATHENA_PADRAO: str = "claude-opus-4.7"

# Regex auxiliares (mesmas convenções de ``caos.models``).
_REGEX_IDENTIFICADOR_WF = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})$")
_REGEX_SLUG_TITULO = re.compile(r"^[a-z0-9-]{1,60}$")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _slug_kebab(texto: str, *, fallback: str = "estrategia") -> str:
    """Converte ``texto`` em slug kebab-case com no máximo 60 chars.

    - Idempotente quando já está em ``[a-z0-9-]{1,60}``.
    - Caso contrário, normaliza: ``lower()``, troca sequências
      não-alfanuméricas por ``-``, colapsa hifens consecutivos,
      remove hifens das pontas e trunca a 60.
    - Slug vazio (após normalização) retorna ``fallback``.
    """
    if _REGEX_SLUG_TITULO.match(texto):
        return texto
    bruto = texto.lower().strip()
    bruto = re.sub(r"[^a-z0-9]+", "-", bruto)
    bruto = re.sub(r"-+", "-", bruto)
    bruto = bruto.strip("-")
    bruto = bruto[:60]
    if not bruto:
        return fallback
    return bruto


def _data_criacao_de_identificador(identificador: str) -> datetime:
    """Deriva ``data_criacao`` (UTC, 00:00:00) do identificador AAAA-MM-DD-NN.

    Mantém determinismo: o mesmo identificador sempre produz o mesmo
    ``data_criacao``, sem depender de ``datetime.now()`` (R7.1 do Spec 2).
    """
    match = _REGEX_IDENTIFICADOR_WF.match(identificador)
    if not match:
        raise ValueError(
            "identificador deve seguir o padrão AAAA-MM-DD-NN; "
            f"recebido {identificador!r}"
        )
    ano, mes, dia, _seq = (int(g) for g in match.groups())
    return datetime(ano, mes, dia, 0, 0, 0, tzinfo=timezone.utc)


def _datetime_para_iso(valor: Optional[datetime]) -> Optional[str]:
    """Serializa ``datetime`` em ISO 8601 estável.

    UTC explícito vira sufixo ``Z`` (mais compacto) — mesma convenção do
    :mod:`caos.council_recorder`. Microssegundos são descartados.
    """
    if valor is None:
        return None
    sem_us = valor.replace(microsecond=0)
    iso = sem_us.isoformat()
    if sem_us.utcoffset() == timedelta(0):
        iso = iso.replace("+00:00", "Z")
    return iso


def _escrita_atomica(caminho: Path, conteudo: str) -> None:
    """Escreve ``conteudo`` em ``caminho`` via ``.tmp`` + ``Path.replace``.

    Mesma estratégia de :mod:`caos.council_recorder`,
    :mod:`caos.data_manifest` e :mod:`caos.skills.token_budget`:

    1. Cria o diretório-pai se necessário.
    2. Escreve em ``caminho.tmp`` com ``newline="\\n"`` (sem CRLF em
       Windows).
    3. ``Path.replace`` promove o arquivo final atomicamente.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8", newline="\n")
    tmp.replace(caminho)


def _formatar_metric(valor: Any) -> str:
    """Formata um valor de métrica para a tabela Markdown.

    - ``None`` (métrica não aplicável, R6.2) vira ``"—"``.
    - ``bool`` vira ``"sim"``/``"não"`` (mantém pt-BR).
    - ``float`` é formatado com 4 casas decimais; valores inteiros
      preservam representação inteira para legibilidade.
    - Demais tipos caem em ``str(...)``.
    """
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, int):
        return f"{valor}"
    if isinstance(valor, float):
        if valor != valor:  # NaN (não esperado, mas defensivo)
            return "—"
        return f"{valor:.4f}"
    return str(valor)


# ---------------------------------------------------------------------------
# Renderização Markdown
# ---------------------------------------------------------------------------

#: Colunas da tabela "Métricas por Janela", em ordem (atributo, rótulo pt-BR).
_COLUNAS_TABELA_JANELAS: tuple[tuple[str, str], ...] = (
    ("indice", "Índice"),
    ("status", "Status"),
    ("numero_trades", "Trades"),
    ("pnl_total", "PnL"),
    ("sharpe_anualizado", "Sharpe"),
    ("calmar", "Calmar"),
    ("drawdown_maximo_percentual", "Drawdown %"),
    ("drawdown_maximo_dias", "Drawdown dias"),
    ("win_rate", "Win rate"),
    ("payoff_medio", "Payoff médio"),
    ("mfe_medio", "MFE médio"),
    ("mae_medio", "MAE médio"),
    ("look_ahead_violation", "Look-ahead?"),
    ("duracao_ms", "Duração (ms)"),
)


def _linha_tabela_janela(resultado_janela: ResultadoJanela) -> str:
    """Renderiza uma linha da tabela "Métricas por Janela"."""
    valores: list[str] = []
    for atributo, _rotulo in _COLUNAS_TABELA_JANELAS:
        if atributo == "indice":
            valor: Any = resultado_janela.janela.indice
        else:
            valor = getattr(resultado_janela, atributo, None)
        valores.append(_formatar_metric(valor))
    return "| " + " | ".join(valores) + " |"


def _renderizar_corpo_markdown(resultado: ResultadoWalkForward) -> str:
    """Constrói o corpo Markdown (sem frontmatter) do relatório.

    Estrutura (pt-BR, R8.2):

    1. Cabeçalho ``# Relatório Walk-Forward — <identificador>``.
    2. Bloco de resumo (estratégia, status, manifesto_hash, configuração).
    3. Tabela "Métricas por Janela" com 1 linha por janela.
    4. Tabela "Agregado (mediana)" — métrica × valor.
    5. Tabela "Agregado (média)" — métrica × valor.
    6. Bloco "Versões de Dependências".
    """
    linhas: list[str] = []
    linhas.append(f"# Relatório Walk-Forward — {resultado.identificador}")
    linhas.append("")

    # ----- Resumo -----
    linhas.append("## Resumo")
    linhas.append("")
    cfg = resultado.configuracao
    resumo = [
        ("Estratégia", resultado.estrategia),
        ("Status", resultado.status),
        ("Identificador", resultado.identificador),
        ("Manifesto (SHA-256)", resultado.manifesto_hash),
        ("Instrumento", cfg.instrumento),
        ("Granularidade", cfg.granularidade),
        ("Treino (dias úteis)", str(cfg.tamanho_treino_dias_uteis)),
        ("Teste (dias úteis)", str(cfg.tamanho_teste_dias_uteis)),
        ("Passo (dias úteis)", str(cfg.passo_dias_uteis)),
        ("Seed", str(cfg.seed)),
        ("Total de janelas", str(len(resultado.janelas))),
    ]
    linhas.append("| Campo | Valor |")
    linhas.append("|---|---|")
    for campo, valor in resumo:
        linhas.append(f"| {campo} | {valor} |")
    linhas.append("")

    # ----- Métricas por Janela -----
    linhas.append("## Métricas por Janela")
    linhas.append("")
    if not resultado.janelas:
        linhas.append("_Sem janelas registradas (status terminal)._")
        linhas.append("")
    else:
        cabecalho = "| " + " | ".join(rot for _, rot in _COLUNAS_TABELA_JANELAS) + " |"
        separador = "|" + "|".join(["---"] * len(_COLUNAS_TABELA_JANELAS)) + "|"
        linhas.append(cabecalho)
        linhas.append(separador)
        for janela in resultado.janelas:
            linhas.append(_linha_tabela_janela(janela))
        linhas.append("")

    # ----- Agregado (mediana) -----
    linhas.append("## Agregado (mediana)")
    linhas.append("")
    if not resultado.agregado_mediana:
        linhas.append("_Sem métricas agregáveis disponíveis._")
        linhas.append("")
    else:
        linhas.append("| Métrica | Mediana |")
        linhas.append("|---|---|")
        for metrica in sorted(resultado.agregado_mediana):
            valor = resultado.agregado_mediana[metrica]
            linhas.append(f"| {metrica} | {_formatar_metric(valor)} |")
        linhas.append("")

    # ----- Agregado (média) -----
    linhas.append("## Agregado (média)")
    linhas.append("")
    if not resultado.agregado_media:
        linhas.append("_Sem métricas agregáveis disponíveis._")
        linhas.append("")
    else:
        linhas.append("| Métrica | Média |")
        linhas.append("|---|---|")
        for metrica in sorted(resultado.agregado_media):
            valor = resultado.agregado_media[metrica]
            linhas.append(f"| {metrica} | {_formatar_metric(valor)} |")
        linhas.append("")

    # ----- Versões -----
    linhas.append("## Versões de Dependências")
    linhas.append("")
    if not resultado.versoes_dependencias:
        linhas.append("_Não registradas._")
        linhas.append("")
    else:
        linhas.append("| Dependência | Versão |")
        linhas.append("|---|---|")
        for nome in sorted(resultado.versoes_dependencias):
            linhas.append(
                f"| {nome} | {resultado.versoes_dependencias[nome]} |"
            )
        linhas.append("")

    return "\n".join(linhas).rstrip() + "\n"


def _construir_frontmatter(resultado: ResultadoWalkForward) -> dict[str, Any]:
    """Constrói o dicionário de frontmatter compatível com NotaZettel.

    Inclui:

    - Campos obrigatórios de :class:`NotaZettel` (R8.1):
      ``titulo``, ``area`` (``"Decisoes_do_Conselho"``), ``tags``,
      ``data_criacao`` (UTC), ``agente_autor`` (``"Athena"``).
    - Campos específicos do Walk-Forward úteis para auditoria humana:
      ``id``, ``identificador``, ``manifesto_hash``, ``estrategia``,
      ``status``, ``num_janelas``.
    """
    slug_estrategia = _slug_kebab(resultado.estrategia, fallback="estrategia")
    titulo = (
        f"Walk-Forward {resultado.identificador} — {resultado.estrategia}"
    )[:200]
    data_criacao = _data_criacao_de_identificador(resultado.identificador)

    tags = ["walk-forward", slug_estrategia, resultado.status]
    # tags devem ser únicos preservando ordem (NotaZettel não exige
    # unicidade, mas evitar duplicatas é higiênico).
    vistos: set[str] = set()
    tags_unicos: list[str] = []
    for tag in tags:
        if tag not in vistos:
            vistos.add(tag)
            tags_unicos.append(tag)

    return {
        # NotaZettel (R8.1).
        "titulo": titulo,
        "area": AREA_NOTA_ZETTEL,
        "tags": tags_unicos,
        "data_criacao": _datetime_para_iso(data_criacao),
        "agente_autor": AGENTE_AUTOR_PADRAO,
        # Específicos do Walk-Forward.
        "id": resultado.identificador,
        "identificador": resultado.identificador,
        "estrategia": resultado.estrategia,
        "manifesto_hash": resultado.manifesto_hash,
        "status": resultado.status,
        "num_janelas": len(resultado.janelas),
    }


def _serializar_markdown(resultado: ResultadoWalkForward) -> str:
    """Serializa ``resultado`` em Markdown completo (frontmatter + corpo)."""
    frontmatter = _construir_frontmatter(resultado)
    yaml_str = yaml.safe_dump(
        frontmatter,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
    )
    corpo = _renderizar_corpo_markdown(resultado)
    return f"---\n{yaml_str}---\n\n{corpo}"


def _serializar_json(resultado: ResultadoWalkForward) -> str:
    """Serializa ``resultado`` em JSON canônico determinístico.

    ``model_dump(mode="json")`` produz tipos JSON-compatíveis
    (datetimes como string ISO 8601). ``json.dumps`` com ``indent=2``,
    ``sort_keys=True`` e ``ensure_ascii=False`` garante representação
    estável byte-a-byte entre execuções com mesmo input (R7.1).
    """
    payload = resultado.model_dump(mode="json")
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


# ---------------------------------------------------------------------------
# Síntese de Debate + Decisão para CouncilRecorder
# ---------------------------------------------------------------------------


def _sintetizar_debate_e_decisao(
    resultado: ResultadoWalkForward,
) -> tuple[Debate, DecisaoDoConselho]:
    """Constrói um par mínimo ``(Debate, DecisaoDoConselho)`` a partir do WF.

    Esta síntese existe para que o RelatorioWriter possa invocar
    :meth:`CouncilRecorder.gravar` sem exigir do chamador a montagem
    manual dos schemas YAML do Spec 1. O Debate é minimal mas válido:

    - ``identificador`` = ``resultado.identificador``;
    - ``titulo`` = slug do nome da estratégia (kebab-case, ≤ 60 chars);
    - Athena como único agente participante (curadoria de WF);
    - ``contexto_hash_sha256`` = ``manifesto_hash``;
    - ``orcamento_de_turnos`` = 12 (default da regra de steering);
    - ``turnos_consumidos`` = 0; ``fase_final`` = ``CONCLUIDO``.

    A decisão registra uma proposta única ``P1`` (autor Athena) com
    o resumo e rationale derivados do status do WF, e um wiki-link
    ``[[Walk_Forward_<identificador>]]`` apontando para a nota gerada
    em ``05_BACKTEST/relatorios/``. ``aprovado_walk_forward`` é
    ``True`` somente quando ``resultado.status == "concluido"``.
    """
    slug = _slug_kebab(resultado.estrategia, fallback="estrategia")
    data_inicio = _data_criacao_de_identificador(resultado.identificador)

    debate = Debate(
        identificador=resultado.identificador,
        titulo=slug,
        data_inicio=data_inicio,
        data_fim=data_inicio,
        agentes_participantes=["Athena"],
        modelos={"Athena": MODELO_ATHENA_PADRAO},
        contexto_hash_sha256=resultado.manifesto_hash,
        notas_injetadas=[],
        seeds={"Athena": resultado.configuracao.seed},
        orcamento_de_turnos=12,
        turnos_consumidos=0,
        fase_final="CONCLUIDO",
        status="concluido",
        turnos=[],
    )

    rationale = (
        f"Walk-Forward {resultado.identificador} concluído com status "
        f"{resultado.status!r} para a estratégia {resultado.estrategia!r}. "
        f"{len(resultado.janelas)} janela(s) avaliada(s); "
        f"manifesto_hash={resultado.manifesto_hash}."
    )
    proposta = Proposta(
        id="P1",
        autor="Athena",
        resumo=(
            f"Registro do Resultado_Walk_Forward {resultado.identificador} "
            f"da estratégia {resultado.estrategia}"
        )[:500],
        conteudo=rationale,
        confianca=80,
    )
    decisao = DecisaoDoConselho(
        identificador=resultado.identificador,
        debate_relacionado=f"{resultado.identificador}-{slug}.md",
        agentes_participantes=["Athena"],
        propostas=[proposta],
        vetos=[],
        decisao_final=DecisaoFinal(
            proposta_aceita="P1",
            rationale=rationale,
        ),
        links_zettel=[f"[[Walk_Forward_{resultado.identificador}]]"],
        aprovado_walk_forward=(resultado.status == "concluido"),
        reproduzivel="parcial",
        regressao_detectada=False,
        status="concluido",
    )
    return debate, decisao


# ---------------------------------------------------------------------------
# RelatorioWriter
# ---------------------------------------------------------------------------


class RelatorioWriter:
    """Escreve ``ResultadoWalkForward`` em JSON canônico + Markdown auditável.

    Parameters
    ----------
    recorder:
        Instância opcional de :class:`CouncilRecorder`. Necessária apenas
        quando :meth:`escrever` é chamado com ``commit_council=True``.
    """

    NOME: str = "RelatorioWriter"

    def __init__(self, *, recorder: Optional[CouncilRecorder] = None) -> None:
        self._recorder = recorder

    # ------------------------------------------------------------------
    # Propriedades públicas
    # ------------------------------------------------------------------

    @property
    def recorder(self) -> Optional[CouncilRecorder]:
        """``CouncilRecorder`` injetado, ou ``None`` se ausente."""
        return self._recorder

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def escrever(
        self,
        resultado: ResultadoWalkForward,
        raiz_saida: Path,
        commit_council: bool = False,
    ) -> Path:
        """Persiste ``resultado`` e devolve o diretório criado.

        Estrutura final:

        ```
        <raiz_saida>/
          <resultado.identificador>/
            resultado.json
            relatorio.md
        ```

        Quando ``commit_council=True``, sintetiza Debate + Decisão a
        partir do resultado e invoca :meth:`CouncilRecorder.gravar`. O
        recorder DEVE ter sido injetado no construtor; caso contrário,
        :class:`ValueError` é levantado **antes** de qualquer escrita
        no disco para evitar artefatos parciais.
        """
        if commit_council and self._recorder is None:
            raise ValueError(
                "commit_council=True exige RelatorioWriter construído com "
                "recorder=<CouncilRecorder>; recebido recorder=None"
            )

        raiz = Path(raiz_saida)
        diretorio = raiz / resultado.identificador
        caminho_json = diretorio / NOME_ARQUIVO_JSON
        caminho_md = diretorio / NOME_ARQUIVO_MD

        # Serialização (puramente em memória — falhas aqui não deixam
        # arquivos parciais no disco).
        conteudo_json = _serializar_json(resultado)
        conteudo_md = _serializar_markdown(resultado)

        # Escrita atômica.
        _escrita_atomica(caminho_json, conteudo_json)
        _escrita_atomica(caminho_md, conteudo_md)

        # Integração opcional com Council.
        if commit_council:
            assert self._recorder is not None  # garantido pelo guard acima
            debate, decisao = _sintetizar_debate_e_decisao(resultado)
            self._recorder.gravar(debate, decisao)

        return diretorio


# ---------------------------------------------------------------------------
# Função utilitária equivalente (estilo funcional)
# ---------------------------------------------------------------------------


def escrever_relatorio(
    resultado: ResultadoWalkForward,
    raiz_saida: Path,
    *,
    commit_council: bool = False,
    recorder: Optional[CouncilRecorder] = None,
) -> Path:
    """Atalho funcional para :meth:`RelatorioWriter.escrever`.

    Útil para callers que não querem manter uma instância de Writer.
    Quando ``commit_council=True``, o ``recorder`` é obrigatório e
    propagado ao Writer.
    """
    writer = RelatorioWriter(recorder=recorder)
    return writer.escrever(
        resultado=resultado,
        raiz_saida=raiz_saida,
        commit_council=commit_council,
    )


__all__ = [
    "AREA_NOTA_ZETTEL",
    "AGENTE_AUTOR_PADRAO",
    "MODELO_ATHENA_PADRAO",
    "NOME_ARQUIVO_JSON",
    "NOME_ARQUIVO_MD",
    "SUBDIR_RELATORIOS",
    "RelatorioWriter",
    "escrever_relatorio",
]
