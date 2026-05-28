"""WF da estrategia aprovada COM ValueAreaFilter overlay vs SEM (baseline).

Compara duas variantes:
  A. Baseline: EstrategiaORBCrabelSFCB (composicao aprovada Decisao 2026-05-25-02)
  B. Overlay: EstrategiaValueAreaFilter(EstrategiaORBCrabelSFCB, modo='trend')
     — só permite entradas em dias TREND (abertura fora da VA do dia anterior)

Roda 5 configs WF sobre 14 meses (412k barras). Mede:
  - Sharpe mediana
  - PnL total
  - Trades total
  - % janelas lucrativas
  - Estatistica de regime (quantos dias TREND vs RANGE)

Saida: relatorio markdown em
05_BACKTEST/walk_forward/relatorios/wf-value-area-overlay-2026-05-27/.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(r"e:\CAOS\CAOS_Orchestrator").resolve()))

from caos.walk_forward.estrategias.composicao_aprovada import EstrategiaORBCrabelSFCB
from caos.walk_forward.estrategias.value_area_filter import (
    EstrategiaValueAreaFilter,
    ParametrosValueAreaFilter,
)
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

# Config 60+10 (mesma da Decisao original e da validacao longa de 27/05).
CONFIG_TREINO = 60
CONFIG_TESTE = 10

SAIDA = Path(r"e:\CAOS\05_BACKTEST\walk_forward\relatorios\wf-value-area-overlay-2026-05-27")
HASH_PLACEHOLDER = "0" * 64


def carregar_dados() -> pd.DataFrame:
    print(f"Carregando {len(CSVS)} CSVs...")
    dfs = []
    for csv in CSVS:
        d = pd.read_csv(csv, parse_dates=["timestamp"])
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
        dfs.append(d)
    df = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    print(f"  Total: {len(df)} barras, {df['timestamp'].min()} a {df['timestamp'].max()}")
    return df


def construir_baseline() -> EstrategiaORBCrabelSFCB:
    return EstrategiaORBCrabelSFCB()


def construir_overlay() -> EstrategiaValueAreaFilter:
    return EstrategiaValueAreaFilter(
        EstrategiaORBCrabelSFCB(),
        parametros=ParametrosValueAreaFilter(modo="range"),
    )


def rodar_wf(df: pd.DataFrame, estrategia, nome: str) -> dict:
    print(f"=== {nome} ===")
    config = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=CONFIG_TREINO,
        tamanho_teste_dias_uteis=CONFIG_TESTE,
        granularidade="1m",
        seed=42,
    )
    janelas = JanelaGenerator.gerar(df, config, HASH_PLACEHOLDER)
    print(f"  {len(janelas)} janelas geradas")
    resultados = []
    for i, j in enumerate(janelas, 1):
        r = BacktestRunner.executar(janela=j, dados=df, estrategia=estrategia, configuracao=config)
        resultados.append(r)
        if i % 5 == 0 or i == len(janelas):
            print(f"  janela {i}/{len(janelas)}: status={r.status}")

    bem_sucedidas = [r for r in resultados if r.status == "ok"]
    sharpes = [r.sharpe_anualizado for r in bem_sucedidas if r.sharpe_anualizado is not None]
    pnls = [r.pnl_total for r in resultados]
    trades = [r.numero_trades for r in resultados]
    drawdowns = [r.drawdown_maximo_percentual for r in bem_sucedidas
                 if r.drawdown_maximo_percentual is not None]
    win_rates = [r.win_rate for r in bem_sucedidas if r.win_rate is not None]

    sumario = {
        "nome": nome,
        "janelas_total": len(resultados),
        "janelas_ok": len(bem_sucedidas),
        "janelas_sem_trades": sum(1 for r in resultados if r.status == "sem-trades"),
        "janelas_falha": sum(1 for r in resultados if r.status == "falha"),
        "janelas_lucrativas": sum(1 for r in bem_sucedidas if r.pnl_total > 0),
        "janelas_perdedoras": sum(1 for r in bem_sucedidas if r.pnl_total < 0),
        "trades_total": sum(trades),
        "trades_mediana": statistics.median(trades) if trades else 0,
        "pnl_total_pts": sum(pnls),
        "pnl_total_usd": sum(pnls) * 2,
        "sharpe_mediana": statistics.median(sharpes) if sharpes else None,
        "drawdown_mediana": statistics.median(drawdowns) if drawdowns else None,
        "win_rate_mediana": statistics.median(win_rates) if win_rates else None,
    }

    sharpe_str = f"{sumario['sharpe_mediana']:+.2f}" if sumario['sharpe_mediana'] is not None else "n/a"
    print(f"  Sharpe mediana: {sharpe_str}")
    print(f"  PnL total: {sumario['pnl_total_pts']:+.2f} pts (USD {sumario['pnl_total_usd']:+.2f})")
    print(f"  Janelas: {sumario['janelas_lucrativas']} lucro / {sumario['janelas_perdedoras']} perda / {sumario['janelas_sem_trades']} sem-trades")
    print(f"  Trades total: {sumario['trades_total']}")

    # Para o overlay, capturar tambem estatistica de regime.
    if isinstance(estrategia, EstrategiaValueAreaFilter):
        regimes = estrategia.regime_por_dia
        tdays = sum(1 for r in regimes.values() if r == "TREND")
        rdays = sum(1 for r in regimes.values() if r == "RANGE")
        sumario["dias_trend"] = tdays
        sumario["dias_range"] = rdays
        sumario["pct_trend"] = tdays / max(len(regimes), 1) * 100
        print(f"  Regime: {tdays} TREND / {rdays} RANGE ({sumario['pct_trend']:.1f}% TREND)")
    print()
    return sumario


def gerar_relatorio_md(baseline: dict, overlay: dict, periodo: tuple) -> str:
    md = []
    md.append("# WF com Value Area Filter overlay (Decisao 2026-05-25-02)")
    md.append("")
    md.append(f"> Periodo: {periodo[0]} a {periodo[1]}")
    md.append(f"> Configuracao WF: treino={CONFIG_TREINO} dias uteis, teste={CONFIG_TESTE} dias uteis")
    md.append("> Filtro: Value Area do dia anterior (cobertura 70%, modo 'trend')")
    md.append("> Tese: estrategia ORB+NR7+SF+CB e estrategia de breakout — funciona melhor em dias TREND")
    md.append("")
    md.append("## Comparacao baseline vs overlay")
    md.append("")
    md.append("| Metrica | Baseline (sem VA) | Overlay (com VA, modo trend) | Delta |")
    md.append("|---|---|---|---|")

    def fmt(v, casas=2, sufixo=""):
        if v is None:
            return "n/a"
        if isinstance(v, int):
            return f"{v}"
        return f"{v:+.{casas}f}{sufixo}"

    metricas = [
        ("Janelas total", "janelas_total", 0),
        ("Janelas com trades", "janelas_ok", 0),
        ("Janelas sem trades", "janelas_sem_trades", 0),
        ("Janelas lucrativas", "janelas_lucrativas", 0),
        ("Janelas perdedoras", "janelas_perdedoras", 0),
        ("Trades total", "trades_total", 0),
        ("Trades mediana/janela", "trades_mediana", 0),
        ("PnL total (pts)", "pnl_total_pts", 2),
        ("PnL total (USD)", "pnl_total_usd", 2),
        ("Sharpe mediana", "sharpe_mediana", 2),
        ("Drawdown mediana", "drawdown_mediana", 4),
        ("Win rate mediana", "win_rate_mediana", 2),
    ]
    for label, chave, casas in metricas:
        b = baseline.get(chave)
        o = overlay.get(chave)
        delta = (o - b) if (b is not None and o is not None and isinstance(b, (int, float))) else None
        md.append(f"| {label} | {fmt(b, casas)} | {fmt(o, casas)} | {fmt(delta, casas) if delta is not None else 'n/a'} |")
    md.append("")
    md.append("## Estatistica de regime (overlay)")
    md.append("")
    md.append(f"- Dias TREND: {overlay.get('dias_trend', 0)}")
    md.append(f"- Dias RANGE: {overlay.get('dias_range', 0)}")
    md.append(f"- % TREND: {overlay.get('pct_trend', 0):.1f}%")
    md.append("")
    md.append("## Veredito")
    md.append("")
    sharpe_b = baseline.get("sharpe_mediana")
    sharpe_o = overlay.get("sharpe_mediana")
    pnl_b = baseline.get("pnl_total_usd", 0)
    pnl_o = overlay.get("pnl_total_usd", 0)
    if sharpe_o is not None and sharpe_b is not None:
        if sharpe_o > sharpe_b * 1.05 and pnl_o > pnl_b:
            md.append("**OVERLAY MELHORA** — Sharpe e PnL mais altos com filtro de regime.")
        elif sharpe_o < sharpe_b * 0.95 or pnl_o < pnl_b * 0.5:
            md.append("**OVERLAY DEGRADA** — filtro de regime reduz performance. Hipotese de Market Profile (80% rule) nao se aplica nesta estrategia.")
        else:
            md.append("**OVERLAY NEUTRO** — diferenca nao material. Filtro nao adiciona valor mas tambem nao prejudica.")
    md.append("")
    md.append("## Implicacoes")
    md.append("")
    md.append("- Se overlay melhora: incorporar como camada 4 da estrategia aprovada.")
    md.append("  Exige Debate formal (gatilho G5: muda regra de decisao da Decisao 2026-05-25-02).")
    md.append("- Se overlay degrada: refutado empiricamente. Valor do hold-out atual e do paper")
    md.append("  arXiv 2605.11423 (Volatility-Volume-Gap classifier) precisa ser investigado.")
    md.append("- Se neutro: deixar como overlay opcional, util para regimes especificos.")
    md.append("")
    md.append("## Notas")
    md.append("")
    md.append("- Baseline = `EstrategiaORBCrabelSFCB` (composicao aprovada Decisao 2026-05-25-02).")
    md.append("- Overlay = `EstrategiaValueAreaFilter(baseline, modo='trend')`.")
    md.append("- Cobertura VA = 70% (constante de Market Profile, CME Group).")
    md.append("- Sem novos parametros otimizaveis livres (Property anti-overfit).")
    md.append("")
    md.append("---")
    md.append("Gerado por `scripts/wf_value_area_overlay_2026-05-27.py`.")
    return "\n".join(md)


def main() -> int:
    df = carregar_dados()
    periodo = (str(df['timestamp'].min().date()), str(df['timestamp'].max().date()))

    baseline = rodar_wf(df, construir_baseline(), "BASELINE — sem VA filter")
    overlay = rodar_wf(df, construir_overlay(), "OVERLAY — com VA filter (modo trend)")

    SAIDA.mkdir(parents=True, exist_ok=True)
    md = gerar_relatorio_md(baseline, overlay, periodo)
    (SAIDA / "relatorio.md").write_text(md, encoding="utf-8")
    (SAIDA / "resultado.json").write_text(
        json.dumps({"periodo": periodo, "baseline": baseline, "overlay": overlay}, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("COMPARACAO FINAL")
    print("=" * 70)
    sharpe_b = f"{baseline.get('sharpe_mediana'):+.2f}" if baseline.get('sharpe_mediana') is not None else "n/a"
    sharpe_o = f"{overlay.get('sharpe_mediana'):+.2f}" if overlay.get('sharpe_mediana') is not None else "n/a"
    print(f"  Baseline Sharpe: {sharpe_b}, PnL: USD {baseline.get('pnl_total_usd', 0):+.2f}, Trades: {baseline.get('trades_total', 0)}")
    print(f"  Overlay  Sharpe: {sharpe_o}, PnL: USD {overlay.get('pnl_total_usd', 0):+.2f}, Trades: {overlay.get('trades_total', 0)}")
    print()
    print(f"Relatorio: {SAIDA / 'relatorio.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
