"""Roda WFs com EstrategiaSpreadFilter envolvendo uma estrategia interna.

Compativel com a infra do rodar_wf_atomico.py (raiz isolada
dados/_wf_isolada/) mas instancia o overlay direto em Python.

Uso:
  python scripts/rodar_wf_spread_filter.py <id> <classe-interna> <config> <kwargs-internos> <modo>

Exemplo:
  python scripts/rodar_wf_spread_filter.py 2026-05-24-19 \\
      caos.walk_forward.estrategias.pre_fomc:EstrategiaPreFomcDrift \\
      e:/CAOS/05_BACKTEST/walk_forward/configs/pre_fomc_topstep.yaml \\
      '{"caminho_meetings_csv": "e:/CAOS/dados/macros/fomc_meetings.csv"}' \\
      hora_otima
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import yaml

from caos.data_manifest import DataManifestManager
from caos.walk_forward import RelatorioWriter, WalkForwardEngine
from caos.walk_forward.estrategias.spread_filter import (
    EstrategiaSpreadFilter,
    ParametrosSpreadFilter,
)
from caos.walk_forward.models import ConfiguracaoWalkForward, CustosOperacionais


def _carregar_classe(import_path: str):
    modulo_nome, classe_nome = import_path.split(":", 1)
    modulo = importlib.import_module(modulo_nome)
    return getattr(modulo, classe_nome)


def _carregar_config(caminho: Path) -> ConfiguracaoWalkForward:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    custos_payload = bruto.pop("custos", None)
    if custos_payload is not None:
        bruto["custos"] = CustosOperacionais(**custos_payload)
    return ConfiguracaoWalkForward(**bruto)


def main() -> int:
    if len(sys.argv) < 6:
        print(__doc__)
        return 2
    identificador = sys.argv[1]
    classe_path = sys.argv[2]
    config_path = Path(sys.argv[3])
    kwargs_internos = json.loads(sys.argv[4]) if sys.argv[4] else {}
    modo = sys.argv[5]

    raiz = Path(r"e:\CAOS").resolve()
    raiz_dados_full = raiz / "dados" / "MNQ"
    raiz_dados_iso = raiz / "dados" / "_wf_isolada"
    raiz_dados_iso.mkdir(exist_ok=True)
    fonte_orig = raiz_dados_full / "_concat_minute_last"
    fonte_iso = raiz_dados_iso / "_concat_minute_last"
    if not fonte_iso.exists():
        import shutil
        shutil.copytree(fonte_orig, fonte_iso)

    fonte = fonte_iso
    raiz_dados = raiz_dados_iso

    print(f"[1/4] Rebuild manifesto em {raiz_dados}...")
    manager = DataManifestManager(raiz_dados=raiz_dados)
    resultado_build = manager.build(instrumento="MNQ")
    print(f"      {len(resultado_build.entradas)} entradas, "
          f"{len(resultado_build.falhas)} falhas")

    print(f"[2/4] Construindo estrategia interna {classe_path} "
          f"kwargs={kwargs_internos}")
    Classe = _carregar_classe(classe_path)
    interna = Classe(**kwargs_internos)

    print(f"[3/4] Wrapping em EstrategiaSpreadFilter modo={modo}")
    paths_spread = list(
        (raiz / "dados" / "MNQ").glob("MNQ_*/tick/spread_minuto.csv")
    )
    print(f"      spread CSVs disponiveis: {len(paths_spread)}")
    parametros = ParametrosSpreadFilter(modo=modo)  # type: ignore[arg-type]
    estrategia = EstrategiaSpreadFilter(
        interna,
        parametros=parametros,
        caminhos_spread_csv=paths_spread,
    )

    configuracao = _carregar_config(config_path)

    print(f"[4/4] Executando Walk-Forward {identificador} ...")
    engine = WalkForwardEngine(raiz_dados=raiz_dados)
    resultado = engine.executar(
        estrategia=estrategia,
        configuracao=configuracao,
        fonte_dados=fonte,
        identificador=identificador,
    )

    print()
    print(f"Walk-Forward concluido.")
    print(f"  identificador:  {resultado.identificador}")
    print(f"  estrategia:     {resultado.estrategia}")
    print(f"  status:         {resultado.status}")
    print(f"  janelas:        {len(resultado.janelas)}")
    print(f"  manifesto_hash: {resultado.manifesto_hash}")

    if resultado.status == "manifesto-invalido":
        return 1

    raiz_relatorios = raiz / "05_BACKTEST" / "walk_forward" / "relatorios"
    writer = RelatorioWriter()
    diretorio = writer.escrever(resultado, raiz_saida=raiz_relatorios)
    print(f"  relatorio:      {diretorio}")

    # Estatisticas do filtro.
    stats = estrategia.estatisticas
    bloqueadas = stats["barras_bloqueadas"]
    recebidas = stats["barras_recebidas"]
    if recebidas > 0:
        pct_bloq = 100.0 * bloqueadas / recebidas
        print(f"  filtro: {bloqueadas:,}/{recebidas:,} barras bloqueadas ({pct_bloq:.1f}%)")

    return 0 if resultado.status == "concluido" else 1


if __name__ == "__main__":
    sys.exit(main())
