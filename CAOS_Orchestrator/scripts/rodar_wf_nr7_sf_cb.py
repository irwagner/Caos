"""Roda WF do Crabel NR7 + Spread Filter + Circuit Breaker.

Composicao:
  CircuitBreaker (limite_diario=-250 / semanal=-750 / janela=-1000)
    -> SpreadFilter (mediana_diaria, running median)
       -> ORBCrabel (nr7)

Hipotese: o circuit breaker reduz a magnitude da janela 1 (que
sozinha perdeu -1711 pts no WF 2026-05-25-02) para algo dentro
do envelope Topstep, atendendo o criterio bloqueante #2 da
Decisao 2026-05-25-01.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from caos.data_manifest import DataManifestManager
from caos.walk_forward import RelatorioWriter, WalkForwardEngine
from caos.walk_forward.estrategias.circuit_breaker import (
    EstrategiaCircuitBreaker,
    ParametrosCircuitBreaker,
)
from caos.walk_forward.estrategias.orb_crabel import EstrategiaORBCrabel
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

    manager = DataManifestManager(raiz_dados=raiz_dados_iso)
    manager.build(instrumento="MNQ")

    crabel = EstrategiaORBCrabel(modo_nr="nr7")
    paths_spread = list(
        (raiz / "dados" / "MNQ").glob("MNQ_*/tick/spread_minuto.csv")
    )
    sf = EstrategiaSpreadFilter(
        crabel,
        parametros=ParametrosSpreadFilter(
            modo="mediana_diaria", minutos_warmup_dia=30,
        ),
        caminhos_spread_csv=paths_spread,
    )
    cb = EstrategiaCircuitBreaker(
        sf,
        parametros=ParametrosCircuitBreaker(
            limite_diario_pts=-250.0,
            limite_semanal_pts=-750.0,
            limite_janela_pts=-1000.0,
        ),
    )

    config_path = raiz / "05_BACKTEST" / "walk_forward" / "configs" / "noise_area_topstep.yaml"
    cfg = _carregar_config(config_path)

    print(f"Executando Walk-Forward {identificador}...")
    print("Composicao: CircuitBreaker(daily=-250, weekly=-750, window=-1000)")
    print("            -> SpreadFilter(mediana_diaria, running median)")
    print("               -> ORBCrabel(nr7)")
    engine = WalkForwardEngine(raiz_dados=raiz_dados_iso)
    resultado = engine.executar(
        estrategia=cb,
        configuracao=cfg,
        fonte_dados=fonte,
        identificador=identificador,
    )
    print()
    print(f"Status: {resultado.status} | Janelas: {len(resultado.janelas)}")
    print(f"Trades descartados pelo CB: {cb.trades_descartados}")

    raiz_relatorios = raiz / "05_BACKTEST" / "walk_forward" / "relatorios"
    RelatorioWriter().escrever(resultado, raiz_saida=raiz_relatorios)

    return 0 if resultado.status == "concluido" else 1


if __name__ == "__main__":
    sys.exit(main())
