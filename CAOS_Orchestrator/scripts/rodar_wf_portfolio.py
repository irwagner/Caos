"""Roda mini-portfolio Pre-FOMC + Crabel NR7+SpreadFilter no WF.

Constroi:
1. EstrategiaPreFomcDrift(meetings_csv)
2. EstrategiaSpreadFilter(EstrategiaORBCrabel(nr7), modo=mediana_diaria)
3. EstrategiaPortfolio([1, 2])

Roda WF padrao (60+60). Salva resultado e imprime estatisticas
por componente alem das metricas agregadas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from caos.data_manifest import DataManifestManager
from caos.walk_forward import RelatorioWriter, WalkForwardEngine
from caos.walk_forward.estrategias.orb_crabel import EstrategiaORBCrabel
from caos.walk_forward.estrategias.portfolio import EstrategiaPortfolio
from caos.walk_forward.estrategias.pre_fomc import EstrategiaPreFomcDrift
from caos.walk_forward.estrategias.spread_filter import (
    EstrategiaSpreadFilter,
    ParametrosSpreadFilter,
)
from caos.walk_forward.models import ConfiguracaoWalkForward, CustosOperacionais


def _carregar_config(caminho: Path) -> ConfiguracaoWalkForward:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    custos_payload = bruto.pop("custos", None)
    if custos_payload is not None:
        bruto["custos"] = CustosOperacionais(**custos_payload)
    return ConfiguracaoWalkForward(**bruto)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    identificador = sys.argv[1]

    raiz = Path(r"e:\CAOS").resolve()
    raiz_dados_iso = raiz / "dados" / "_wf_isolada"
    fonte = raiz_dados_iso / "_concat_minute_last"

    print(f"[1/4] Rebuild manifesto em {raiz_dados_iso}...")
    manager = DataManifestManager(raiz_dados=raiz_dados_iso)
    resultado_build = manager.build(instrumento="MNQ")
    print(f"      {len(resultado_build.entradas)} entradas")

    # Componente 1: Pre-FOMC.
    csv_fomc = raiz / "dados" / "macros" / "fomc_meetings.csv"
    pre_fomc = EstrategiaPreFomcDrift(caminho_meetings_csv=csv_fomc)
    print(f"[2/4] Componente 1: EstrategiaPreFomcDrift "
          f"({len(pre_fomc.janelas_fomc)} meetings)")

    # Componente 2: Crabel NR7 + Spread Filter.
    crabel = EstrategiaORBCrabel(modo_nr="nr7")
    paths_spread = list(
        (raiz / "dados" / "MNQ").glob("MNQ_*/tick/spread_minuto.csv")
    )
    crabel_filtrado = EstrategiaSpreadFilter(
        crabel,
        parametros=ParametrosSpreadFilter(
            modo="mediana_diaria",
            minutos_warmup_dia=30,
        ),
        caminhos_spread_csv=paths_spread,
    )
    print(f"[2/4] Componente 2: EstrategiaORBCrabel(nr7) + SpreadFilter "
          f"(running median, {len(paths_spread)} CSVs spread)")

    # Portfolio.
    portfolio = EstrategiaPortfolio(
        [pre_fomc, crabel_filtrado],
        nome="Portfolio_PreFOMC_NR7SF",
    )
    print(f"[3/4] EstrategiaPortfolio = [PreFOMC, NR7+SF]")

    # Config.
    config_path = raiz / "05_BACKTEST" / "walk_forward" / "configs" / "noise_area_topstep.yaml"
    configuracao = _carregar_config(config_path)

    print(f"[4/4] Executando Walk-Forward {identificador}...")
    engine = WalkForwardEngine(raiz_dados=raiz_dados_iso)
    resultado = engine.executar(
        estrategia=portfolio,
        configuracao=configuracao,
        fonte_dados=fonte,
        identificador=identificador,
    )

    print()
    print(f"Walk-Forward concluido.")
    print(f"  identificador: {resultado.identificador}")
    print(f"  status:        {resultado.status}")
    print(f"  janelas:       {len(resultado.janelas)}")
    print()
    print(f"Trades por componente (ultima janela): "
          f"{portfolio.num_trades_por_componente}")

    raiz_relatorios = raiz / "05_BACKTEST" / "walk_forward" / "relatorios"
    writer = RelatorioWriter()
    writer.escrever(resultado, raiz_saida=raiz_relatorios)

    if resultado.status != "concluido":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
