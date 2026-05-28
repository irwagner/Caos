"""WF longo de validacao da Decisao 2026-05-25-02 sob filtro corrigido.

Roda 5 configuracoes diferentes de janela sobre 14 meses de dados
agregados (5 contratos MNQ_06-25 a MNQ_06-26) e gera relatorio
consolidado para avaliar robustez da estrategia
EstrategiaCircuitBreaker(EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7))).

Decisao 2026-05-26-01 exige Sharpe mediana >= 1.0 para manter aprovacao
da Decisao original 2026-05-25-02. Este script e a validacao definitiva
sob bug fix do NR7.

Configuracoes testadas (treino + teste em dias uteis):
1. 60 + 10  (configuracao da Decisao original)
2. 60 + 20  (teste maior, mais robusto)
3. 80 + 20  (treino maior)
4. 100 + 20 (treino bem maior, menos janelas)
5. 120 + 20 (treino enorme, poucas janelas, mais estabilidade)

Saida: relatorio markdown + json em
05_BACKTEST/walk_forward/relatorios/wf-validacao-longa-2026-05-27/.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(r"e:\CAOS\CAOS_Orchestrator").resolve()))

from caos.walk_forward.estrategias.composicao_aprovada import EstrategiaORBCrabelSFCB
from caos.walk_forward.janelas import JanelaGenerator
from caos.walk_forward.models import ConfiguracaoWalkForward
from caos.walk_forward.runner import BacktestRunner


CSVS = [
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\02_MNQ_09-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\03_MNQ_12-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\04_MNQ_03-26.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\05_MNQ_06-26.csv"),
]

CONFIGS = [
    {"nome": "60+10", "treino": 60, "teste": 10},
    {"nome": "60+20", "treino": 60, "teste": 20},
    {"nome": "80+20", "treino": 80, "teste": 20},
    {"nome": "100+20", "treino": 100, "teste": 20},
    {"nome": "120+20", "treino": 120, "teste": 20},
]

SAIDA = Path(r"e:\CAOS\05_BACKTEST\walk_forward\relatorios\wf-validacao-longa-2026-05-27")
HASH_PLACEHOLDER = "0" * 64


def carregar_dados() -> pd.DataFrame:
    print(f"Carregando {len(CSVS)} CSVs...")
    dfs = []
    for csv in CSVS:
        d = pd.read_csv(csv, parse_dates=["timestamp"])
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
        dfs.append(d)
        print(f"  {csv.name}: {len(d)} barras")
    df = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    print(f"  Total: {len(df)} barras, {df['timestamp'].min()} a {df['timestamp'].max()}")
    print()
    return df


def rodar_wf_para_config(df: pd.DataFrame, cfg: dict) -> dict[str, Any]:
    print(f"=== Configuracao {cfg['nome']} (treino={cfg['treino']}, teste={cfg['teste']}) ===")
    estrategia = EstrategiaORBCrabelSFCB()
    config = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=cfg["treino"],
        tamanho_teste_dias_uteis=cfg["teste"],
        granularidade="1m",
        seed=42,
    )
    janelas = JanelaGenerator.gerar(df, config, HASH_PLACEHOLDER)
    print(f"  {len(janelas)} janelas geradas")
    if not janelas:
        return {"nome": cfg["nome"], "erro": "sem-janelas"}

    resultados = []
    for i, j in enumerate(janelas, 1):
        r = BacktestRunner.executar(janela=j, dados=df, estrategia=estrategia, configuracao=config)
        resultados.append(r)
        if i % 5 == 0 or i == len(janelas):
            print(f"  janela {i}/{len(janelas)}: {j.treino_inicio.date()} -> {j.teste_fim.date()}  status={r.status}")

    bem_sucedidas = [r for r in resultados if r.status == "ok"]
    sharpes = [r.sharpe_anualizado for r in bem_sucedidas if r.sharpe_anualizado is not None]
    pnls = [r.pnl_total for r in resultados]
    pnls_ok = [r.pnl_total for r in bem_sucedidas]
    trades = [r.numero_trades for r in resultados]
    drawdowns = [r.drawdown_maximo_percentual for r in bem_sucedidas
                 if r.drawdown_maximo_percentual is not None]
    win_rates = [r.win_rate for r in bem_sucedidas if r.win_rate is not None]
    calmars = [r.calmar for r in bem_sucedidas if r.calmar is not None]

    sumario = {
        "nome": cfg["nome"],
        "treino_dias": cfg["treino"],
        "teste_dias": cfg["teste"],
        "janelas_total": len(resultados),
        "janelas_ok": len(bem_sucedidas),
        "janelas_sem_trades": sum(1 for r in resultados if r.status == "sem-trades"),
        "janelas_falha": sum(1 for r in resultados if r.status == "falha"),
        "trades_total": sum(trades),
        "trades_mediana": statistics.median(trades) if trades else 0,
        "trades_media": statistics.mean(trades) if trades else 0,
        "pnl_total_pts": sum(pnls),
        "pnl_total_usd": sum(pnls) * 2,  # MNQ = USD 2/pt
        "pnl_mediana_pts": statistics.median(pnls_ok) if pnls_ok else 0,
        "sharpe_mediana": statistics.median(sharpes) if sharpes else None,
        "sharpe_media": statistics.mean(sharpes) if sharpes else None,
        "calmar_mediana": statistics.median(calmars) if calmars else None,
        "drawdown_mediana": statistics.median(drawdowns) if drawdowns else None,
        "drawdown_max": max(drawdowns) if drawdowns else None,
        "win_rate_mediana": statistics.median(win_rates) if win_rates else None,
        "janelas_lucrativas": sum(1 for r in bem_sucedidas if r.pnl_total > 0),
        "janelas_perdedoras": sum(1 for r in bem_sucedidas if r.pnl_total < 0),
    }

    print(f"  Sharpe mediana: {sumario['sharpe_mediana']:+.2f}" if sumario['sharpe_mediana'] is not None else "  Sharpe mediana: n/a")
    print(f"  PnL total: {sumario['pnl_total_pts']:+.2f} pts (USD {sumario['pnl_total_usd']:+.2f})")
    print(f"  Janelas: {sumario['janelas_lucrativas']} lucro / {sumario['janelas_perdedoras']} perda / {sumario['janelas_sem_trades']} sem-trades")
    print(f"  Trades total: {sumario['trades_total']}, mediana/janela: {sumario['trades_mediana']}")
    print()
    return sumario


def gerar_relatorio_md(sumarios: list[dict], dados_periodo: tuple) -> str:
    """Gera relatorio markdown da validacao."""
    md = []
    md.append("# Validacao Longa do WF apos Bug Fix NR7 (Decisao 2026-05-26-01)")
    md.append("")
    md.append(f"> Periodo: {dados_periodo[0]} a {dados_periodo[1]}")
    md.append("> Estrategia: `EstrategiaORBCrabelSFCB` (composicao aprovada Decisao 2026-05-25-02)")
    md.append("> Filtro NR7 corrigido: descarta sabados/domingos e dias com < 300 barras de minuto")
    md.append("")
    md.append("## Configuracoes testadas")
    md.append("")
    md.append("| Config | Treino (dias) | Teste (dias) | Janelas | Lucrativas | Perdedoras | Sem trades |")
    md.append("|---|---|---|---|---|---|---|")
    for s in sumarios:
        md.append(
            f"| {s['nome']} | {s['treino_dias']} | {s['teste_dias']} | "
            f"{s['janelas_total']} | {s['janelas_lucrativas']} | "
            f"{s['janelas_perdedoras']} | {s['janelas_sem_trades']} |"
        )
    md.append("")
    md.append("## Metricas consolidadas (mediana entre janelas com trades)")
    md.append("")
    md.append("| Config | Sharpe mediana | Calmar mediana | DD mediana | DD max | Win rate | PnL total (pts) | PnL total (USD) | Trades total |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for s in sumarios:
        sharpe = f"{s['sharpe_mediana']:+.2f}" if s['sharpe_mediana'] is not None else "n/a"
        calmar = f"{s['calmar_mediana']:+.2f}" if s['calmar_mediana'] is not None else "n/a"
        dd_med = f"{s['drawdown_mediana']:.4f}" if s['drawdown_mediana'] is not None else "n/a"
        dd_max = f"{s['drawdown_max']:.4f}" if s['drawdown_max'] is not None else "n/a"
        wr = f"{s['win_rate_mediana']:.2f}" if s['win_rate_mediana'] is not None else "n/a"
        md.append(
            f"| {s['nome']} | {sharpe} | {calmar} | {dd_med} | {dd_max} | {wr} | "
            f"{s['pnl_total_pts']:+.2f} | {s['pnl_total_usd']:+.2f} | {s['trades_total']} |"
        )
    md.append("")
    md.append("## Criterio de aprovacao (Decisao 2026-05-26-01)")
    md.append("")
    md.append("- **Sharpe mediana >= 1.0 em majoria das configuracoes** mantem Decisao 2026-05-25-02.")
    md.append("- **Sharpe mediana < 1.0 em majoria** invalida aprovacao, exige Debate de seguimento.")
    md.append("")
    sharpes_ok = [s for s in sumarios if s.get('sharpe_mediana') is not None and s['sharpe_mediana'] >= 1.0]
    md.append(f"### Resultado: {len(sharpes_ok)} de {len(sumarios)} configuracoes com Sharpe mediana >= 1.0")
    md.append("")
    if len(sharpes_ok) >= 3:
        md.append("**APROVACAO MANTIDA** — estrategia robusta sob diferentes janelas WF.")
    elif len(sharpes_ok) >= 1:
        md.append("**APROVACAO PARCIAL** — robustez questionavel, depende da janela.")
    else:
        md.append("**APROVACAO INVALIDADA** — estrategia falha sob filtro NR7 corrigido.")
    md.append("")
    md.append("## PnL total por configuracao (USD, MNQ 1 contrato)")
    md.append("")
    md.append("| Config | PnL total | PnL anualizado (~12 meses) |")
    md.append("|---|---|---|")
    # Estimativa: 14 meses de dados, anualiza pra 12 meses
    for s in sumarios:
        anualizado = s['pnl_total_usd'] * 12 / 14
        md.append(f"| {s['nome']} | USD {s['pnl_total_usd']:+.2f} | USD {anualizado:+.2f}/ano |")
    md.append("")
    md.append("## Notas")
    md.append("")
    md.append("- Backtest assume MaxContratos=1 (pre-condicao da Decisao 2026-05-25-02).")
    md.append("- MNQ: USD 2 por ponto. PnL em pontos × 2 = PnL em USD.")
    md.append("- Sharpe anualizado computado pelo MetricasCalculator do Spec 2.")
    md.append("- Valores `n/a` em janelas significam sem trades suficientes para metricas validas.")
    md.append("")
    md.append("---")
    md.append("Gerado por `scripts/wf_validacao_longa_2026-05-27.py`.")
    return "\n".join(md)


def main() -> int:
    df = carregar_dados()
    periodo = (str(df['timestamp'].min().date()), str(df['timestamp'].max().date()))
    sumarios = []
    for cfg in CONFIGS:
        s = rodar_wf_para_config(df, cfg)
        sumarios.append(s)

    SAIDA.mkdir(parents=True, exist_ok=True)
    md = gerar_relatorio_md(sumarios, periodo)
    (SAIDA / "relatorio.md").write_text(md, encoding="utf-8")
    (SAIDA / "resultado.json").write_text(
        json.dumps({"periodo": periodo, "configuracoes": sumarios}, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("VALIDACAO LONGA — RESUMO FINAL")
    print("=" * 70)
    print()
    print(f"{'Config':<8} {'Sharpe med':>11} {'PnL total':>12} {'Trades':>8} {'Janelas (L/P/S)':>18}")
    print("-" * 65)
    for s in sumarios:
        sharpe = f"{s['sharpe_mediana']:+.2f}" if s['sharpe_mediana'] is not None else "n/a"
        l_p_s = f"{s['janelas_lucrativas']}/{s['janelas_perdedoras']}/{s['janelas_sem_trades']}"
        print(f"{s['nome']:<8} {sharpe:>11} {s['pnl_total_usd']:>+11.2f} {s['trades_total']:>8} {l_p_s:>18}")
    print()
    print(f"Relatorio: {SAIDA / 'relatorio.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
