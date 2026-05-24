"""Rebuild manifesto + roda WF no mesmo processo Python.

Necessario porque o NT8 esta exportando tick file ativamente (cresce
varios MB/segundo) e qualquer chamada ``manifesto build`` num processo
separado deixa uma janela de tempo onde o tick muda e invalida o hash
calculado.

Uso (do diretorio CAOS_Orchestrator):

    python scripts/rodar_wf_atomico.py <id> <estrategia> <config> [<estrategia-args-json>]

Exemplo:

    python scripts/rodar_wf_atomico.py 2026-05-24-03 \\
        caos.walk_forward.estrategias.noise_area:EstrategiaNoiseArea \\
        e:/CAOS/05_BACKTEST/walk_forward/configs/noise_area_lookback90_topstep.yaml \\
        '{"lookback_dias": 90}'
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import yaml

from caos.data_manifest import DataManifestManager
from caos.walk_forward import RelatorioWriter, WalkForwardEngine
from caos.walk_forward.models import ConfiguracaoWalkForward, CustosOperacionais


def _carregar_estrategia(import_path: str, kwargs: dict):
    modulo_nome, classe_nome = import_path.split(":", 1)
    modulo = importlib.import_module(modulo_nome)
    classe = getattr(modulo, classe_nome)
    return classe(**kwargs)


def _carregar_config(caminho: Path) -> ConfiguracaoWalkForward:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    custos_payload = bruto.pop("custos", None)
    if custos_payload is not None:
        bruto["custos"] = CustosOperacionais(**custos_payload)
    return ConfiguracaoWalkForward(**bruto)


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    identificador = sys.argv[1]
    estrategia_path = sys.argv[2]
    config_path = Path(sys.argv[3])
    kwargs = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}

    raiz = Path(r"e:\CAOS").resolve()
    raiz_dados_full = raiz / "dados" / "MNQ"
    # Raiz isolada APENAS com os concat csvs estaveis. Evita que tick.txt
    # em escrita ativa do NT8 invalide o manifesto entre build e read.
    raiz_dados_iso = raiz / "dados" / "_wf_isolada"
    raiz_dados_iso.mkdir(exist_ok=True)
    # Symlink/junction nao funciona bem em Windows sem admin; copiar
    # arquivos pequenos (csvs) eh aceitavel — sao ~MB cada.
    fonte_orig = raiz_dados_full / "_concat_minute_last"
    fonte_iso = raiz_dados_iso / "_concat_minute_last"
    if fonte_iso.exists():
        # Mantemos a copia (rebuild incremental).
        pass
    else:
        import shutil
        shutil.copytree(fonte_orig, fonte_iso)
        print(f"[setup] copiei {fonte_orig} -> {fonte_iso}")

    fonte = fonte_iso
    raiz_dados = raiz_dados_iso
    raiz_relatorios = raiz / "05_BACKTEST" / "walk_forward" / "relatorios"

    # Etapa 1 - rebuild manifesto isolado (so cobre os csvs estaveis).
    print(f"[1/3] Rebuild manifesto em {raiz_dados}...")
    manager = DataManifestManager(raiz_dados=raiz_dados)
    resultado_build = manager.build(instrumento="MNQ")
    print(
        f"      {len(resultado_build.entradas)} entradas, "
        f"{len(resultado_build.falhas)} falhas"
    )

    # Etapa 2 - carregar estrategia e config.
    print(f"[2/3] Carregando estrategia {estrategia_path} kwargs={kwargs}")
    estrategia = _carregar_estrategia(estrategia_path, kwargs)
    configuracao = _carregar_config(config_path)

    # Etapa 3 - rodar WF.
    print(f"[3/3] Executando Walk-Forward {identificador} ...")
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
        print("  => manifesto invalidado.")
        return 1

    writer = RelatorioWriter()
    diretorio = writer.escrever(resultado, raiz_saida=raiz_relatorios)
    print(f"  relatorio:      {diretorio}")

    if resultado.status not in ("concluido",):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
