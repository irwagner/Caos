"""
CLI do CAOS_Orchestrator.

Esta versão expõe (Task 17 / Spec 1):

* ``caos init`` (R1) — bootstrap idempotente do workspace.
* ``caos manifesto build|verify`` (R15) — gerência de
  ``dados/MNQ/manifesto.json``.
* ``caos hydra sync`` (R13) — sincroniza a cópia somente-leitura do
  Hydra em ``04_CODIGO/ninjascript/reference_hydra/``.
* ``caos debate <tema>`` — placeholder do fluxo de Debate. No Spec 1,
  apenas informa que a integração com o backend de subagente Kiro será
  habilitada em modo de produção; testes ponta-a-ponta de orquestração
  ficam na suíte property-based.
* ``caos perfil validar [nome]`` (R2) — valida 1 ou os 9 perfis em
  ``.kiro/agents/``.
* ``caos cache stats`` (R16) — sumariza ``CAOS_Orchestrator/.cache/``.
* ``caos budget status`` (R17) — mostra consumo diário de tokens.

Idioma da saída: pt-BR. Plataforma alvo: Windows + cmd (R3.2, R3.3).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from caos import init_workspace
from caos.data_manifest import DataManifestManager
from caos.hydra_sync import HydraReferenceSync
from caos.profile_loader import (
    ARQUIVOS_ESPERADOS,
    carregar_perfil,
    carregar_todos,
)


# ---------------------------------------------------------------------------
# Constantes de layout
# ---------------------------------------------------------------------------

#: Caminho relativo padrão para os dados do MNQ a partir da raiz do workspace.
#: Reflete o R1.7 e a regra de steering ``instrumento-mnq``. Centralizado aqui
#: para que o subcomando ``manifesto`` use o mesmo layout do ``init``.
_RAIZ_DADOS_MNQ_RELATIVO = Path("dados/MNQ")

#: Caminho relativo do diretório de perfis de agente (R1.2).
_DIR_AGENTS_RELATIVO = Path(".kiro/agents")

#: Caminho relativo do cache LLM (R16.1).
_DIR_CACHE_RELATIVO = Path("CAOS_Orchestrator/.cache")

#: Caminho relativo do diretório de orçamento de tokens (R17.5).
_DIR_BUDGET_RELATIVO = Path("CAOS_Orchestrator/.budget")


# ---------------------------------------------------------------------------
# Construção do parser
# ---------------------------------------------------------------------------


def _construir_parser() -> argparse.ArgumentParser:
    """Monta o parser raiz e os subparsers."""
    parser = argparse.ArgumentParser(
        prog="caos",
        description=(
            "Orquestrador do Conselho Multi-Agente CAOS. Subcomandos: "
            "init, manifesto, hydra, debate, perfil, cache, budget."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    # ---- caos init ----
    init_parser = sub.add_parser(
        "init",
        help="cria de forma idempotente a árvore de diretórios do workspace CAOS",
        description=(
            "Cria os diretórios canônicos do projeto CAOS na raiz informada. "
            "Idempotente: rodar várias vezes nunca destrói arquivos ou pastas "
            "pré-existentes."
        ),
    )
    init_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "raiz do workspace; se omitido, usa o diretório atual (cwd). "
            "Caminhos relativos são resolvidos contra a cwd."
        ),
    )

    # ---- caos manifesto ... ----
    manifesto_parser = sub.add_parser(
        "manifesto",
        help="gerencia o dados/MNQ/manifesto.json",
        description=(
            "Constrói (build) ou verifica (verify) o manifesto de "
            "integridade dos arquivos de dados do MNQ."
        ),
    )
    manifesto_sub = manifesto_parser.add_subparsers(
        dest="manifesto_comando", required=True
    )

    build_parser = manifesto_sub.add_parser(
        "build",
        help="varre dados/MNQ/ e (re)gera manifesto.json",
        description=(
            "Lê todos os arquivos sob dados/MNQ/ (recursivamente, ignorando "
            "manifesto.json), computa SHA-256 via streaming, deriva metadados "
            "e grava manifesto.json de forma atômica."
        ),
    )
    build_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )
    build_parser.add_argument(
        "--instrumento",
        type=str,
        default="MNQ",
        help="identificador do instrumento (default: MNQ).",
    )

    verify_parser = manifesto_sub.add_parser(
        "verify",
        help="verifica integridade dos arquivos contra manifesto.json",
        description=(
            "Recomputa SHA-256 dos arquivos em dados/MNQ/ e compara com o "
            "manifesto. Reporta divergências, arquivos ausentes e arquivos "
            "não registrados."
        ),
    )
    verify_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )

    # ---- caos hydra sync ----
    hydra_parser = sub.add_parser(
        "hydra",
        help="comandos de manutenção da cópia somente-leitura do Hydra (R13)",
        description=(
            "Sincroniza a cópia local de https://github.com/irwagner/hydra-trading "
            "em 04_CODIGO/ninjascript/reference_hydra/. A cópia é somente-referência "
            "(steering rule reference-hydra-readonly)."
        ),
    )
    hydra_sub = hydra_parser.add_subparsers(
        dest="hydra_comando", required=True
    )
    hydra_sync_parser = hydra_sub.add_parser(
        "sync",
        help="clona ou atualiza reference_hydra/ a partir do branch main",
        description=(
            "Executa git clone (na primeira vez) ou git fetch + reset --hard "
            "(em runs subsequentes) com timeout de 120s. Em qualquer falha, "
            "preserva a cópia local existente e reporta categoria de erro."
        ),
    )
    hydra_sync_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )

    # ---- caos debate <tema> ----
    debate_parser = sub.add_parser(
        "debate",
        help="abre um Debate sobre <tema> no Conselho",
        description=(
            "No Spec 1, este comando NÃO chama o backend de subagente "
            "(integração entrega no modo de produção do orquestrador). "
            "Para validação automatizada, use a suíte property-based em "
            "CAOS_Orchestrator/tests/property/."
        ),
    )
    debate_parser.add_argument(
        "tema_titulo",
        type=str,
        help="título curto do Debate (obrigatório).",
    )
    debate_parser.add_argument(
        "--descricao",
        type=str,
        default="",
        help="descrição livre opcional.",
    )
    debate_parser.add_argument(
        "--tags",
        type=str,
        default="",
        help="tags separadas por vírgula (ex.: ninjascript,risco).",
    )
    debate_parser.add_argument(
        "--csharp",
        action="store_true",
        help="marca o Debate como envolvendo código C#.",
    )
    debate_parser.add_argument(
        "--exposicao",
        action="store_true",
        help="marca o Debate como envolvendo alteração de exposição.",
    )
    debate_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )

    # ---- caos perfil validar [nome] ----
    perfil_parser = sub.add_parser(
        "perfil",
        help="comandos de inspeção de perfis de agente (R2)",
        description=(
            "Valida arquivos de perfil em .kiro/agents/ contra o schema "
            "AgentProfile."
        ),
    )
    perfil_sub = perfil_parser.add_subparsers(
        dest="perfil_comando", required=True
    )
    perfil_validar_parser = perfil_sub.add_parser(
        "validar",
        help="valida 1 perfil (por nome) ou os 9 perfis do Conselho",
        description=(
            "Sem argumento: valida os 9 perfis canônicos. "
            "Com <nome>: valida apenas o perfil .kiro/agents/<nome>.md."
        ),
    )
    perfil_validar_parser.add_argument(
        "nome",
        nargs="?",
        type=str,
        default=None,
        help="nome do agente (ex.: Athena). Se omitido, valida os 9.",
    )
    perfil_validar_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )

    # ---- caos cache stats ----
    cache_parser = sub.add_parser(
        "cache",
        help="comandos de inspeção do Skill_LLM_Cache (R16)",
        description=(
            "Lê CAOS_Orchestrator/.cache/ e reporta estatísticas básicas "
            "do cache de respostas LLM."
        ),
    )
    cache_sub = cache_parser.add_subparsers(
        dest="cache_comando", required=True
    )
    cache_stats_parser = cache_sub.add_parser(
        "stats",
        help="conta entradas e tamanho total em bytes do cache",
        description=(
            "Lista o número de arquivos *.json em "
            "<root>/CAOS_Orchestrator/.cache/ e o tamanho total em bytes."
        ),
    )
    cache_stats_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )

    # ---- caos budget status ----
    budget_parser = sub.add_parser(
        "budget",
        help="comandos de inspeção do Skill_Token_Budget (R17)",
        description=(
            "Lê CAOS_Orchestrator/.budget/ e reporta consumo diário de "
            "tokens por agente."
        ),
    )
    budget_sub = budget_parser.add_subparsers(
        dest="budget_comando", required=True
    )
    budget_status_parser = budget_sub.add_parser(
        "status",
        help="mostra consumo do dia (UTC) por agente",
        description=(
            "Lê <root>/CAOS_Orchestrator/.budget/<data>.json e formata "
            "consumo input/output/total por agente. Default: hoje UTC."
        ),
    )
    budget_status_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raiz do workspace; default = cwd.",
    )
    budget_status_parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="dia no formato AAAA-MM-DD (default: hoje UTC).",
    )

    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolver_raiz(args: argparse.Namespace) -> Path:
    """Resolve a raiz do workspace a partir de ``args.root``."""
    root = args.root if args.root is not None else Path.cwd()
    return Path(root).expanduser().resolve()


def _resolver_raiz_dados(args: argparse.Namespace) -> Path:
    """Resolve a raiz de dados para os subcomandos ``manifesto``."""
    return _resolver_raiz(args) / _RAIZ_DADOS_MNQ_RELATIVO


# ---------------------------------------------------------------------------
# Despachadores: init / manifesto
# ---------------------------------------------------------------------------


def _comando_init(args: argparse.Namespace) -> int:
    """Executa o subcomando ``init`` e imprime relatório humano."""
    raiz = _resolver_raiz(args)
    resultado = init_workspace.executar(raiz)
    relatorio = init_workspace.formatar_relatorio(resultado)
    if resultado.sucesso:
        print(relatorio)
        return 0
    print(relatorio, file=sys.stderr)
    return 1


def _comando_manifesto_build(args: argparse.Namespace) -> int:
    """Executa ``caos manifesto build``."""
    raiz_dados = _resolver_raiz_dados(args)
    if not raiz_dados.is_dir():
        print(
            f"ERRO: diretório de dados ausente em {raiz_dados}.\n"
            "Execute 'caos init' primeiro.",
            file=sys.stderr,
        )
        return 1
    gerente = DataManifestManager(raiz_dados=raiz_dados)
    resultado = gerente.build(instrumento=args.instrumento)
    print(f"Manifesto gravado em: {resultado.caminho_manifesto}")
    print(f"  entradas: {len(resultado.entradas)}")
    print(f"  falhas:   {len(resultado.falhas)}")
    if resultado.falhas:
        print("Falhas registradas no manifesto:")
        for f in resultado.falhas:
            print(f"  - {f.caminho_relativo} [{f.categoria}]: {f.mensagem}")
    return 0


def _comando_manifesto_verify(args: argparse.Namespace) -> int:
    """Executa ``caos manifesto verify``."""
    raiz_dados = _resolver_raiz_dados(args)
    if not raiz_dados.is_dir():
        print(
            f"ERRO: diretório de dados ausente em {raiz_dados}.\n"
            "Execute 'caos init' primeiro.",
            file=sys.stderr,
        )
        return 1
    gerente = DataManifestManager(raiz_dados=raiz_dados)
    resultado = gerente.verify()
    if resultado.ok:
        print(resultado.sumario_humano)
        return 0
    print(resultado.sumario_humano, file=sys.stderr)
    return 1


def _comando_manifesto(args: argparse.Namespace) -> int:
    if args.manifesto_comando == "build":
        return _comando_manifesto_build(args)
    if args.manifesto_comando == "verify":
        return _comando_manifesto_verify(args)
    print(
        f"subcomando manifesto desconhecido: {args.manifesto_comando!r}",
        file=sys.stderr,
    )
    return 2  # pragma: no cover


# ---------------------------------------------------------------------------
# Despachador: hydra sync
# ---------------------------------------------------------------------------


def _comando_hydra_sync(args: argparse.Namespace) -> int:
    """Executa ``caos hydra sync``."""
    raiz = _resolver_raiz(args)
    if not raiz.is_dir():
        print(
            f"ERRO: raiz {raiz} não existe ou não é diretório. "
            "Execute 'caos init' primeiro.",
            file=sys.stderr,
        )
        return 1
    sync = HydraReferenceSync(raiz_workspace=raiz)
    resultado = sync.sincronizar()
    if resultado.sucesso:
        rotulo = "clone novo" if resultado.cloned_now else "update incremental"
        print("Hydra_Reference_Sync concluído com sucesso.")
        print(f"  operação:       {rotulo}")
        print(f"  hash do commit: {resultado.hash_commit}")
        print(f"  caminho clone:  {resultado.caminho_clone}")
        print(f"  duração:        {resultado.duracao_ms} ms")
        return 0

    falha = resultado.falha
    print("Hydra_Reference_Sync FALHOU; cópia local preservada.", file=sys.stderr)
    if falha is not None:
        print(f"  categoria: {falha.categoria}", file=sys.stderr)
        print(f"  mensagem:  {falha.mensagem}", file=sys.stderr)
    print(f"  caminho clone: {resultado.caminho_clone}", file=sys.stderr)
    return 1


def _comando_hydra(args: argparse.Namespace) -> int:
    if args.hydra_comando == "sync":
        return _comando_hydra_sync(args)
    print(
        f"subcomando hydra desconhecido: {args.hydra_comando!r}",
        file=sys.stderr,
    )
    return 2  # pragma: no cover


# ---------------------------------------------------------------------------
# Despachador: debate (placeholder do Spec 1)
# ---------------------------------------------------------------------------


def _comando_debate(args: argparse.Namespace) -> int:
    """Stub do fluxo de Debate (Spec 1).

    No Spec 1 não há API direta de subagente exposta ao orquestrador para
    consumo ponta-a-ponta em CLI. Este comando documenta o formato dos
    argumentos e instrui o usuário sobre a suíte property-based.
    """
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    flags: list[str] = []
    if args.csharp:
        flags.append("csharp")
    if args.exposicao:
        flags.append("exposicao")

    print("CAOS — comando 'debate'")
    print(f"  tema:       {args.tema_titulo}")
    if args.descricao:
        print(f"  descricao:  {args.descricao}")
    if tags:
        print(f"  tags:       {', '.join(tags)}")
    if flags:
        print(f"  flags:      {', '.join(flags)}")
    print()
    print(
        "O comando 'debate' requer integração com o backend de subagente "
        "Kiro, que será habilitada quando o orquestrador for executado em "
        "modo de produção. Para teste em CI, use a suíte property-based em "
        "CAOS_Orchestrator/tests/property/."
    )
    return 0


# ---------------------------------------------------------------------------
# Despachador: perfil validar
# ---------------------------------------------------------------------------


def _comando_perfil_validar(args: argparse.Namespace) -> int:
    """Executa ``caos perfil validar [nome]``."""
    raiz = _resolver_raiz(args)
    diretorio_agents = raiz / _DIR_AGENTS_RELATIVO

    if args.nome is None:
        # Validar os 9 perfis.
        if not diretorio_agents.is_dir():
            print(
                f"ERRO: diretório de perfis ausente em {diretorio_agents}.\n"
                "Execute 'caos init' primeiro.",
                file=sys.stderr,
            )
            return 1
        resultado = carregar_todos(diretorio_agents)
        print(f"Diretório de perfis: {resultado.diretorio}")
        print(
            f"Perfis carregados: {len(resultado.perfis)} de "
            f"{len(ARQUIVOS_ESPERADOS)}"
        )
        for nome in sorted(resultado.perfis.keys()):
            perfil = resultado.perfis[nome]
            print(f"  [OK] {nome:<18} modelo={perfil.modelo}")
        if resultado.falhas:
            print("\nFalhas:", file=sys.stderr)
            for f in resultado.falhas:
                caminho = f.caminho.name if f.caminho is not None else "<n/a>"
                print(
                    f"  [FALHA] {caminho} [{f.categoria}]: {f.mensagem}",
                    file=sys.stderr,
                )
            return 1
        if not resultado.sucesso:
            return 1
        return 0

    # Validar perfil específico.
    nome = args.nome.strip()
    if not nome:
        print("ERRO: nome do agente não pode ser vazio.", file=sys.stderr)
        return 2
    caminho = diretorio_agents / f"{nome}.md"
    resultado = carregar_perfil(caminho)
    if resultado.sucesso and resultado.perfil is not None:
        perfil = resultado.perfil
        print(f"Perfil válido: {caminho}")
        print(f"  nome:               {perfil.nome}")
        print(f"  modelo:             {perfil.modelo}")
        print(
            f"  tags_especialidade: "
            f"{', '.join(perfil.tags_especialidade) or '(nenhuma)'}"
        )
        print(
            f"  skills_permitidas:  "
            f"{', '.join(perfil.skills_permitidas) or '(nenhuma)'}"
        )
        print(
            f"  escopo_de_decisao:  "
            f"{', '.join(perfil.escopo_de_decisao) or '(nenhum)'}"
        )
        return 0
    falha = resultado.falha
    print(f"Perfil INVÁLIDO: {caminho}", file=sys.stderr)
    if falha is not None:
        print(f"  categoria: {falha.categoria}", file=sys.stderr)
        print(f"  mensagem:  {falha.mensagem}", file=sys.stderr)
    return 1


def _comando_perfil(args: argparse.Namespace) -> int:
    if args.perfil_comando == "validar":
        return _comando_perfil_validar(args)
    print(
        f"subcomando perfil desconhecido: {args.perfil_comando!r}",
        file=sys.stderr,
    )
    return 2  # pragma: no cover


# ---------------------------------------------------------------------------
# Despachador: cache stats
# ---------------------------------------------------------------------------


def _comando_cache_stats(args: argparse.Namespace) -> int:
    """Executa ``caos cache stats``."""
    raiz = _resolver_raiz(args)
    diretorio = raiz / _DIR_CACHE_RELATIVO
    print(f"Diretório de cache: {diretorio}")
    if not diretorio.is_dir():
        print("  0 entradas (diretório ainda não criado).")
        return 0
    arquivos = sorted(p for p in diretorio.glob("*.json") if p.is_file())
    total_bytes = 0
    for p in arquivos:
        try:
            total_bytes += p.stat().st_size
        except OSError:
            # Arquivo desapareceu entre o glob e o stat — ignoramos.
            continue
    print(f"  {len(arquivos)} entradas")
    print(f"  tamanho total: {total_bytes} bytes")
    return 0


def _comando_cache(args: argparse.Namespace) -> int:
    if args.cache_comando == "stats":
        return _comando_cache_stats(args)
    print(
        f"subcomando cache desconhecido: {args.cache_comando!r}",
        file=sys.stderr,
    )
    return 2  # pragma: no cover


# ---------------------------------------------------------------------------
# Despachador: budget status
# ---------------------------------------------------------------------------


def _resolver_data_budget(valor: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Valida ``--data`` e retorna ``(data_iso, erro)``.

    Default = hoje UTC. Em caso de formato inválido, retorna
    ``(None, mensagem_erro)``.
    """
    if valor is None or valor == "":
        return datetime.now(timezone.utc).date().isoformat(), None
    try:
        # ``fromisoformat`` aceita ``AAAA-MM-DD`` desde Python 3.7.
        data = datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError as exc:
        return None, f"--data inválida: {valor!r} (esperado AAAA-MM-DD): {exc}"
    return data.isoformat(), None


def _comando_budget_status(args: argparse.Namespace) -> int:
    """Executa ``caos budget status``."""
    raiz = _resolver_raiz(args)
    data_iso, erro = _resolver_data_budget(args.data)
    if erro is not None:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    diretorio = raiz / _DIR_BUDGET_RELATIVO
    caminho = diretorio / f"{data_iso}.json"
    print(f"Orçamento de tokens — dia {data_iso} (UTC)")
    print(f"  arquivo: {caminho}")
    if not caminho.is_file():
        print("  sem consumo registrado para o dia.")
        return 0

    try:
        bruto = caminho.read_text(encoding="utf-8")
        payload = json.loads(bruto)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"ERRO: arquivo de orçamento ilegível ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 1

    agentes_map = payload.get("agentes") if isinstance(payload, dict) else None
    if not isinstance(agentes_map, dict) or not agentes_map:
        print("  sem consumo registrado para o dia.")
        return 0

    print("  consumo por agente:")
    for nome in sorted(agentes_map.keys()):
        entrada = agentes_map[nome]
        if not isinstance(entrada, dict):
            continue
        try:
            t_input = int(entrada.get("tokens_input_consumidos", 0))
            t_output = int(entrada.get("tokens_output_consumidos", 0))
            t_total = int(entrada.get("tokens_total_consumidos", 0))
            orcamento = int(entrada.get("orcamento_diario_tokens", 0))
        except (TypeError, ValueError):
            print(f"    [FALHA] {nome}: entrada malformada", file=sys.stderr)
            continue
        saldo = orcamento - t_total
        print(
            f"    - {nome:<18} input={t_input} output={t_output} "
            f"total={t_total} orcamento={orcamento} saldo={saldo}"
        )
    return 0


def _comando_budget(args: argparse.Namespace) -> int:
    if args.budget_comando == "status":
        return _comando_budget_status(args)
    print(
        f"subcomando budget desconhecido: {args.budget_comando!r}",
        file=sys.stderr,
    )
    return 2  # pragma: no cover


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def cli(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada chamado pelo entry point ``caos``."""
    parser = _construir_parser()
    args = parser.parse_args(argv)
    if args.comando == "init":
        return _comando_init(args)
    if args.comando == "manifesto":
        return _comando_manifesto(args)
    if args.comando == "hydra":
        return _comando_hydra(args)
    if args.comando == "debate":
        return _comando_debate(args)
    if args.comando == "perfil":
        return _comando_perfil(args)
    if args.comando == "cache":
        return _comando_cache(args)
    if args.comando == "budget":
        return _comando_budget(args)
    parser.error(f"subcomando desconhecido: {args.comando!r}")
    return 2  # pragma: no cover


def main() -> None:
    """Ponto de entrada para ``python -m caos.main``."""
    sys.exit(cli())


if __name__ == "__main__":  # pragma: no cover
    main()
