"""Sweep de slippage_fracao_range na Noise Area mean-reversion.

Roda 5 WFs com diferentes nivel de friccao para medir o ponto de
break-even. Output: tabela ASCII no stdout + arquivo JSON no
relatorios/sweep-friccao-noise-area-2026-05-24/.

Motivacao: WF 2026-05-24-05 mostrou que a versao mean-reversion
da Noise Area tem PnL bruto positivo (~+420 pts) mas perde -180 pts
liquidos com slippage_fracao_range=0.075. O sweep identifica:

1. Em que nivel de friccao a estrategia vira positiva.
2. Qual seria a meta de spread efetivo no MNQ para a analise tick.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

# Garante import do pacote caos.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from caos.data_manifest import DataManifestManager  # noqa: E402
from caos.walk_forward import WalkForwardEngine  # noqa: E402
from caos.walk_forward.estrategias.noise_area import (  # noqa: E402
    EstrategiaNoiseArea,
)
from caos.walk_forward.models import (  # noqa: E402
    ConfiguracaoWalkForward,
    CustosOperacionais,
)


VALORES_SLIPPAGE_FRACAO = [0.0, 0.025, 0.05, 0.075, 0.10]


def main() -> int:
    raiz = Path(r"e:\CAOS").resolve()
    raiz_dados = raiz / "dados" / "_wf_isolada"
    fonte = raiz_dados / "_concat_minute_last"
    raiz_relatorios = raiz / "05_BACKTEST" / "walk_forward" / "relatorios"
    saida_dir = (
        raiz_relatorios / "caracterizacao-mnq-minute-2026-05-23"
    )

    # Rebuild manifesto uma vez.
    print(f"[setup] Rebuild manifesto em {raiz_dados}...")
    manager = DataManifestManager(raiz_dados=raiz_dados)
    manager.build(instrumento="MNQ")

    # Carrega config base.
    cfg_base_path = (
        raiz / "05_BACKTEST" / "walk_forward" / "configs"
        / "noise_area_inverter_topstep.yaml"
    )
    bruto = yaml.safe_load(cfg_base_path.read_text(encoding="utf-8"))
    custos_payload = bruto.pop("custos")

    resultados_sweep: list[dict] = []
    for i, sf in enumerate(VALORES_SLIPPAGE_FRACAO, start=10):
        custos = CustosOperacionais(**{**custos_payload, "slippage_fracao_range": sf})
        cfg = ConfiguracaoWalkForward(**bruto, custos=custos)
        estrategia = EstrategiaNoiseArea(inverter_sinais=True)
        engine = WalkForwardEngine(raiz_dados=raiz_dados)
        identificador = f"2026-05-24-{i:02d}"  # sweep usa indices 10..14
        print(f"\n[sweep] slippage_fracao_range={sf} ({identificador})")
        try:
            resultado = engine.executar(
                estrategia=estrategia,
                configuracao=cfg,
                fonte_dados=fonte,
                identificador=identificador,
            )
        except Exception as exc:
            print(f"  ERRO: {type(exc).__name__}: {exc}")
            continue

        agg = resultado.agregado_mediana or {}
        resultados_sweep.append(
            {
                "slippage_fracao_range": sf,
                "status": resultado.status,
                "janelas": len(resultado.janelas),
                "sharpe_anualizado": agg.get("sharpe_anualizado"),
                "pnl_total": agg.get("pnl_total"),
                "win_rate": agg.get("win_rate"),
                "calmar": agg.get("calmar"),
                "drawdown_pct": agg.get("drawdown_maximo_percentual"),
                "trades_medio": agg.get("numero_trades"),
            }
        )
        print(
            f"  Sharpe={agg.get('sharpe_anualizado'):.3f} "
            f"PnL={agg.get('pnl_total'):.1f} pts "
            f"WR={agg.get('win_rate'):.3f} "
            f"trades_medio={agg.get('numero_trades')}"
        )

    saida_dir.mkdir(parents=True, exist_ok=True)
    arquivo_json = saida_dir / "sweep-friccao-noise-area-2026-05-24.json"
    arquivo_json.write_text(
        json.dumps(
            {
                "estrategia": "EstrategiaNoiseArea (inverter_sinais=True)",
                "config_base": "noise_area_inverter_topstep.yaml",
                "valores_testados": VALORES_SLIPPAGE_FRACAO,
                "resultados": resultados_sweep,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n[done] JSON em {arquivo_json}")

    print()
    print("=" * 80)
    print(f"{'sf':>8} {'Sharpe':>10} {'PnL pts':>10} {'WR':>8} {'trades_med':>12}")
    print("=" * 80)
    for r in resultados_sweep:
        print(
            f"{r['slippage_fracao_range']:>8.3f} "
            f"{r['sharpe_anualizado']:>10.3f} "
            f"{r['pnl_total']:>10.1f} "
            f"{r['win_rate']:>8.3f} "
            f"{r['trades_medio']:>12.1f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
