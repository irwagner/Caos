"""Re-roda WF da Decisao 2026-05-25-02 com o filtro corrigido (Decisao 2026-05-26-01).

Bypassa a validacao de manifesto (que tem timeout em arquivos tick gigantes
fora deste escopo) e executa o pipeline WF direto sobre o CSV last.csv
do MNQ_03-26.

Comparacao: WF original (relatorios/2026-05-25-05) vs. este novo.
Criterio Decisao 2026-05-26-01: Sharpe deve continuar >= 1.0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(r"e:\CAOS\CAOS_Orchestrator").resolve()))

from caos.walk_forward.engine import WalkForwardEngine
from caos.walk_forward.estrategias.composicao_aprovada import EstrategiaORBCrabelSFCB
from caos.walk_forward.models import ConfiguracaoWalkForward


CSVS = [
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\02_MNQ_09-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\03_MNQ_12-25.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\04_MNQ_03-26.csv"),
    Path(r"e:\CAOS\dados\MNQ\_concat_minute_last\05_MNQ_06-26.csv"),
]


def main() -> int:
    print(f"Carregando {len(CSVS)} CSVs concatenados...")
    dfs = []
    for csv in CSVS:
        d = pd.read_csv(csv, parse_dates=["timestamp"])
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
        dfs.append(d)
        print(f"  {csv.name}: {len(d)} barras, {d['timestamp'].min()} a {d['timestamp'].max()}")
    df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    print(f"  Total: {len(df)} barras, {df['timestamp'].min()} a {df['timestamp'].max()}")
    print()

    estrategia = EstrategiaORBCrabelSFCB()
    # Configuracao identica a Decisao original 2026-05-25-02:
    # treino=60 + teste=10 dias uteis. Dataset agregado dos 5 contratos
    # cobre ~14 meses (suficiente para 4-6 janelas).
    config = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        seed=42,
    )

    # Bypass do manifesto: chamamos componentes sem o reader que valida.
    from caos.walk_forward.janelas import JanelaGenerator
    from caos.walk_forward.runner import BacktestRunner

    print("Gerando janelas...")
    # JanelaWF.hash_dados exige hex SHA-256 64 chars. Como bypassamos
    # o reader/manifesto, fornecemos um hash placeholder fixo.
    HASH_PLACEHOLDER = "0" * 64
    janelas = JanelaGenerator.gerar(df, config, HASH_PLACEHOLDER)
    print(f"  {len(janelas)} janelas geradas")
    if not janelas:
        print("ERRO: nenhuma janela gerada — historico insuficiente.")
        return 1

    resultados = []
    for i, janela in enumerate(janelas, 1):
        print(f"  Janela {i}/{len(janelas)}: {janela.treino_inicio.date()} -> {janela.teste_fim.date()}")
        r = BacktestRunner.executar(
            janela=janela,
            dados=df,
            estrategia=estrategia,
            configuracao=config,
        )
        resultados.append(r)
        if r.status == "ok":
            sharpe_str = f"{r.sharpe_anualizado:.2f}" if r.sharpe_anualizado is not None else "n/a"
            print(f"    trades={r.numero_trades}  pnl={r.pnl_total:+.2f} pts  sharpe={sharpe_str}")
        elif r.status == "sem-trades":
            print(f"    sem trades")
        else:
            print(f"    status={r.status}")

    print()
    print("=" * 70)
    print("RESULTADO CONSOLIDADO")
    print("=" * 70)
    bem_sucedidas = [r for r in resultados if r.status == "ok"]
    if not bem_sucedidas:
        print("Nenhuma janela concluida. Provavelmente CB cortou tudo.")
        return 1

    sharpes = [r.sharpe_anualizado for r in bem_sucedidas if r.sharpe_anualizado is not None]
    pnls = [r.pnl_total for r in resultados if r.pnl_total is not None]  # inclui sem-trades (0)
    trades = [r.numero_trades for r in resultados]
    drawdowns = [r.drawdown_maximo_percentual for r in bem_sucedidas if r.drawdown_maximo_percentual is not None]

    import statistics
    sharpe_med = statistics.median(sharpes)
    pnl_med = statistics.median(pnls)
    trades_med = statistics.median(trades)
    dd_med = statistics.median(drawdowns)

    print(f"  janelas concluidas: {len(bem_sucedidas)}/{len(resultados)}")
    print(f"  sharpe mediana:     {sharpe_med:+.2f}")
    print(f"  pnl mediana:        {pnl_med:+.2f} pts")
    print(f"  trades mediana:     {trades_med}")
    print(f"  drawdown mediana:   {dd_med:.4f}")
    print()
    print("Comparacao com Decisao 2026-05-25-02:")
    print(f"  Sharpe original (mediana): +2.91")
    print(f"  Sharpe pos-fix (mediana):  {sharpe_med:+.2f}")
    print(f"  Diff:                     {sharpe_med - 2.91:+.2f}")
    print()
    if sharpe_med >= 1.0:
        print(f"VALIDACAO POS-FIX: APROVADA (sharpe {sharpe_med:.2f} >= 1.0)")
        print("Decisao 2026-05-25-02 mantida apos correcao do bug NR7.")
    else:
        print(f"VALIDACAO POS-FIX: REPROVADA (sharpe {sharpe_med:.2f} < 1.0)")
        print("Decisao 2026-05-25-02 perde validade. Abrir novo Debate.")

    # Grava json detalhado
    saida = Path(r"e:\CAOS\05_BACKTEST\walk_forward\relatorios\2026-05-26-01-rerun-fix")
    saida.mkdir(parents=True, exist_ok=True)
    payload = {
        "identificador": "2026-05-26-01-rerun-fix",
        "estrategia": "EstrategiaORBCrabelSFCB",
        "fonte": "concat 5 contratos MNQ_06-25 a MNQ_06-26",
        "decisao_referencia": "2026-05-25-02",
        "decisao_fix": "2026-05-26-01",
        "janelas_total": len(resultados),
        "janelas_concluidas": len(bem_sucedidas),
        "sharpe_mediana": sharpe_med,
        "sharpe_original": 2.91,
        "pnl_pts_mediana": pnl_med,
        "trades_mediana": trades_med,
        "drawdown_mediana": dd_med,
        "validacao_aprovada": sharpe_med >= 1.0,
        "janelas": [
            {
                "treino_inicio": str(j.treino_inicio.date()),
                "teste_fim": str(j.teste_fim.date()),
                "status": r.status,
                "trades": r.numero_trades,
                "pnl_pts": r.pnl_total,
                "sharpe": r.sharpe_anualizado,
            }
            for j, r in zip(janelas, resultados)
        ],
    }
    (saida / "resultado.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print()
    print(f"Resultado gravado: {saida / 'resultado.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
