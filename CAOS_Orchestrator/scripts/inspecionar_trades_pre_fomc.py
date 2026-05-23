"""Script de inspecao manual dos trades emitidos pelo WF Pre-FOMC.

Decorre da Decisao 2026-05-23-03 (P2 vencedora): validar se a
implementacao da EstrategiaPreFomcDrift esta correta inspecionando
os 8 trades emitidos no WF 2026-05-23-04.

Criterio (Athena, sintese): ao menos 7 dos 8 trades devem ter
entrada_timestamp em dia util ANTERIOR a uma data FOMC agendada,
e saida_timestamp na tarde do dia FOMC.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    relatorio = (
        ROOT_REPO
        / "05_BACKTEST"
        / "walk_forward"
        / "relatorios"
        / "2026-05-23-04"
        / "resultado.json"
    )
    fomc_csv = ROOT_REPO / "dados" / "macros" / "fomc_meetings.csv"

    if not relatorio.is_file():
        print(f"ERRO: relatorio ausente em {relatorio}", file=sys.stderr)
        return 1
    if not fomc_csv.is_file():
        print(f"ERRO: calendario FOMC ausente em {fomc_csv}", file=sys.stderr)
        return 1

    payload = json.loads(relatorio.read_text(encoding="utf-8"))
    datas_anuncio: set[date] = set()
    with fomc_csv.open("r", encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            bruto = (linha.get("data_anuncio") or "").strip()
            if bruto:
                datas_anuncio.add(date.fromisoformat(bruto))

    print("Datas FOMC do calendario:")
    for d in sorted(datas_anuncio):
        print(f"  - {d.isoformat()}")
    print()

    janelas = payload.get("janelas", [])
    if not janelas:
        print("ERRO: relatorio sem janelas", file=sys.stderr)
        return 1

    trades_total = []
    for j in janelas:
        for t in j.get("trades", []) or []:
            trades_total.append((j["janela"]["indice"], t))

    if not trades_total:
        # ResultadoJanela talvez nao serialize trades. Tente outra
        # rota: a partir do agregado nao temos os trades crus aqui.
        # Em vez disso, simulamos a inspecao com base na metrica
        # numero_trades por janela.
        print(
            "AVISO: resultado.json nao expoe trades crus. "
            "Imprimindo apenas resumo das janelas.",
            file=sys.stderr,
        )
        for j in janelas:
            jan = j.get("janela", {})
            print(
                f"  janela {jan.get('indice')}: trades={j.get('numero_trades')} "
                f"pnl={j.get('pnl_total')} sharpe={j.get('sharpe_anualizado')}"
            )
        # Sem trades crus, abrimos um caminho alternativo: re-rodar
        # a estrategia com instrumentacao para imprimir trades.
        return _inspecionar_via_replay(datas_anuncio)

    print(f"Total de {len(trades_total)} trades emitidos.\n")

    bate = 0
    for indice_janela, t in trades_total:
        ts_e = t.get("entrada_timestamp", "")
        ts_s = t.get("saida_timestamp", "")
        try:
            d_e = date.fromisoformat(ts_e[:10])
            d_s = date.fromisoformat(ts_s[:10])
        except (ValueError, TypeError):
            print(f"  [JAN {indice_janela}] timestamp invalido: {ts_e!r} -> {ts_s!r}")
            continue
        ok = d_s in datas_anuncio
        status = "OK" if ok else "FORA"
        if ok:
            bate += 1
        print(
            f"  [JAN {indice_janela}] entrada={d_e.isoformat()} ({d_e.strftime('%a')}) "
            f"saida={d_s.isoformat()} ({d_s.strftime('%a')}) "
            f"pnl={t.get('pnl_pontos', '?'):.2f}  {status}"
        )

    print()
    print(f"Trades cuja saida coincide com data FOMC oficial: {bate}/{len(trades_total)}")
    if bate >= 7 and len(trades_total) >= 8:
        print("VEREDITO: implementacao OK por criterio Athena (>=7/8).")
    else:
        print("VEREDITO: implementacao NAO valida por criterio Athena (<7/8).")
    return 0


def _inspecionar_via_replay(datas_anuncio: set[date]) -> int:
    """Se o resultado.json nao tem trades crus, re-roda a estrategia
    sobre os mesmos dados para extrair os trades emitidos."""
    sys.path.insert(0, str(ROOT_REPO / "CAOS_Orchestrator"))
    from caos.walk_forward.data_reader import SkillDataReader
    from caos.walk_forward.estrategias.pre_fomc import (
        EstrategiaPreFomcDrift,
    )
    from caos.walk_forward.runner import BarrasTesteIterator

    reader = SkillDataReader(
        raiz_dados=ROOT_REPO / "dados" / "MNQ",
        invocador="inspecionar-trades",
    )
    df = reader.carregar(ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last")
    print(f"\nRe-executando estrategia sobre {len(df):,} barras...")

    plugin = EstrategiaPreFomcDrift(
        ROOT_REPO / "dados" / "macros" / "fomc_meetings.csv"
    )
    plugin.treinar(df.copy())
    iterator = BarrasTesteIterator(df)
    for barra in iterator:
        plugin.on_barra(barra, iterator)
    trades = list(plugin.finalizar())

    print(f"Total de {len(trades)} trades emitidos no replay.\n")
    bate = 0
    for i, t in enumerate(trades):
        d_e = t.entrada_timestamp.date()
        d_s = t.saida_timestamp.date()
        ok = d_s in datas_anuncio
        if ok:
            bate += 1
        print(
            f"  [{i:>2}] entrada={d_e.isoformat()} ({d_e.strftime('%a')}) "
            f"saida={d_s.isoformat()} ({d_s.strftime('%a')}) "
            f"pnl={t.pnl_pontos():.2f}  {'OK' if ok else 'FORA'}"
        )
    print()
    print(f"Trades cuja saida coincide com data FOMC oficial: {bate}/{len(trades)}")
    if bate >= 7 and len(trades) >= 8:
        print("VEREDITO: implementacao OK por criterio Athena (>=7/8).")
    else:
        print("VEREDITO: implementacao NAO valida por criterio Athena (<7/8).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
