"""Script ad-hoc: caracteriza a serie MNQ minute consolidada.

Carrega o concat dos 5 contratos (mesma fonte usada nos WFs 2026-05-22-01
e 2026-05-23-02) e grava o relatorio Markdown em
``05_BACKTEST/walk_forward/relatorios/caracterizacao-mnq-minute-2026-05-23/``.

Decorre do item 3 da Decisao_Do_Conselho 2026-05-23-01 (analise descritiva
da serie) e fornece input para futuras Decisoes do Conselho sobre nova
familia estrategica (apos parar a ORB conforme Decisao 2026-05-23-02).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite rodar de qualquer cwd.
ROOT_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_REPO / "CAOS_Orchestrator"))

from caos.walk_forward.caracterizacao import caracterizar_serie
from caos.walk_forward.data_reader import SkillDataReader


def main() -> int:
    raiz_dados = ROOT_REPO / "dados" / "MNQ"
    fonte = ROOT_REPO / "dados" / "MNQ" / "_concat_minute_last"
    if not fonte.is_dir():
        print(f"ERRO: fonte de dados ausente em {fonte}", file=sys.stderr)
        return 1

    reader = SkillDataReader(raiz_dados=raiz_dados, invocador="script-caracterizar")
    print(f"Carregando {fonte}...")
    df = reader.carregar(fonte)
    print(f"Total de barras carregadas: {len(df):,}")

    print("Calculando caracterizacao...")
    relatorio = caracterizar_serie(df, instrumento="MNQ minute (concat 5 contratos)")
    md = relatorio.formatar_markdown()

    saida_dir = (
        ROOT_REPO
        / "05_BACKTEST"
        / "walk_forward"
        / "relatorios"
        / "caracterizacao-mnq-minute-2026-05-23"
    )
    saida_dir.mkdir(parents=True, exist_ok=True)
    saida_md = saida_dir / "caracterizacao.md"
    saida_md.write_text(md, encoding="utf-8")

    print(f"Relatorio gravado em: {saida_md}")
    print()
    # Imprime resumo curto na tela (sem mojibake — usa ASCII puro).
    rd = relatorio.range_diario
    print("== Resumo no console ==")
    print(f"Range diario mediano: {rd.mediana_pontos:.2f} pts (P05={rd.p05_pontos:.2f}, P95={rd.p95_pontos:.2f})")
    print(f"Razao P95/P05:        {rd.razao_p95_p05:.2f}")
    ac = relatorio.autocorrelacao
    print("Autocorrelacoes (rho) por lag:")
    for lag in sorted(ac.autocorrelacoes):
        print(f"  lag {lag:>3}min: {ac.autocorrelacoes[lag]:+.4f}")
    g = relatorio.gaps
    print(f"Gaps observados: {g.num_gaps_observados} (mediana={g.mediana_pontos:+.2f} pts; significativos={g.fracao_gaps_significativos:.2%})")
    vi = relatorio.volatilidade_intradia
    print(f"Hora de pico de vol:     {vi.hora_pico:02d}h UTC")
    print(f"Hora de calmaria:        {vi.hora_calmaria:02d}h UTC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
