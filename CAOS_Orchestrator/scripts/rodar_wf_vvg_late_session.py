"""Walk-Forward longo de validação da VVG Late-Session Reversal (Tarefa 11).

Esta é a tarefa da **verdade** do spec ``caos-vvg-late-session-reversal-mnq``:
roda o WF longo (60+10 anchored) sobre 2025-07-01 a 2026-05-15 e aplica os
critérios pré-registrados de aprovação/descarte (R7.3 + emenda da
``Decisao_2026-05-29-03``). Os parâmetros foram CONGELADOS na calibração da
Tarefa 1 (``Calibracao_VVG_2026-05-29.md``) — NÃO há recalibração.

Composição canônica (R3.3):

    EstrategiaCircuitBreaker(
        EstrategiaSpreadFilter(
            EstrategiaVvgLateSessionReversal(),
            modo="mediana_diaria", warmup=30, running_median=True,
        ),
        diario=-250, semanal=-750, janela=-1000,
    )

Critérios pré-registrados (R7.3 + emenda year-stability):

  1. Sharpe mediana   >= 1.0   (sobre os cortes do WF)
  2. Calmar mediana   >= 1.5   (sobre os cortes do WF)
  3. PnL total        >  0     (soma das janelas, 1 contrato MNQ)
  4. Year-stability   >= 3/4   trimestres com Sharpe positivo
                               (2025-Q3, 2025-Q4, 2026-Q1, 2026-Q2)

Se TODOS passam -> aprovação (R7.5). Se QUALQUER falha -> fallback A
automático (R9), sem novo Debate (regra anti-overfit, pré-registrada).

O script NÃO escreve as notas Zettel de aprovação/refutação nem mexe no
STATE-OF-RESEARCH — ele apenas produz NÚMEROS e a decisão automática, gravando
o relatório canônico em ``05_BACKTEST/walk_forward/relatorios/<id>/`` e um
``criterios.json`` com a avaliação. As notas do Conselho são escritas pelo
agente a partir destes números.

Plataforma: Windows + cmd. Idioma: pt-BR. Uso:

    set PYTHONIOENCODING=utf-8
    python scripts\rodar_wf_vvg_late_session.py 2026-05-29-04
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from caos.data_manifest import DataManifestManager
from caos.walk_forward import RelatorioWriter, WalkForwardEngine
from caos.walk_forward.estrategias.circuit_breaker import (
    EstrategiaCircuitBreaker,
    ParametrosCircuitBreaker,
)
from caos.walk_forward.estrategias.spread_filter import (
    EstrategiaSpreadFilter,
    ParametrosSpreadFilter,
)
from caos.walk_forward.estrategias.vvg_classifier import VvgClassifier
from caos.walk_forward.estrategias.vvg_late_session_reversal import (
    EstrategiaVvgLateSessionReversal,
)
from caos.walk_forward.estrategias.vvg_logica import ParametrosVvg
from caos.walk_forward.models import ConfiguracaoWalkForward, CustosOperacionais
from caos.walk_forward.runner import BacktestRunner
from caos.walk_forward.janelas import JanelaGenerator
from caos.walk_forward.models import JanelaWF

# ---------------------------------------------------------------------------
# Constantes do experimento (CONGELADAS — não recalibrar)
# ---------------------------------------------------------------------------

RAIZ = Path(r"e:\CAOS").resolve()
RAIZ_DADOS_ISO = RAIZ / "dados" / "_wf_isolada"
FONTE_DIR = RAIZ_DADOS_ISO / "_concat_minute_last"

#: Arquivos que cobrem a janela do WF longo + warmup (file 01 = calibração,
#: usado APENAS como warmup de treino; os cortes de Teste caem em 2025-07+).
ARQUIVOS_WF = [
    FONTE_DIR / "01_MNQ_06-25.csv",  # 2025-03-17 .. 2025-06-13 (warmup/treino)
    FONTE_DIR / "02_MNQ_09-25.csv",  # 2025-06-16 .. 2025-09-13
    FONTE_DIR / "03_MNQ_12-25.csv",  # 2025-09-15 .. 2025-12-15
    FONTE_DIR / "04_MNQ_03-26.csv",  # 2025-12-15 .. 2026-03-14
    FONTE_DIR / "05_MNQ_06-26.csv",  # 2026-03-16 .. 2026-05-18
]

#: Janela nominal do WF longo (R7.1).
WF_INICIO = pd.Timestamp("2025-07-01T00:00:00Z")
WF_FIM = pd.Timestamp("2026-05-15T00:00:00Z")

#: Trimestres para year-stability (emenda Decisao_2026-05-29-03). Semi-aberto.
TRIMESTRES = [
    ("2025-Q3", pd.Timestamp("2025-07-01T00:00:00Z"), pd.Timestamp("2025-10-01T00:00:00Z")),
    ("2025-Q4", pd.Timestamp("2025-10-01T00:00:00Z"), pd.Timestamp("2026-01-01T00:00:00Z")),
    ("2026-Q1", pd.Timestamp("2026-01-01T00:00:00Z"), pd.Timestamp("2026-04-01T00:00:00Z")),
    ("2026-Q2", pd.Timestamp("2026-04-01T00:00:00Z"), pd.Timestamp("2026-05-15T00:00:00Z")),
]

#: Critérios pré-registrados (R7.3 + emenda).
SHARPE_MIN = 1.0
CALMAR_MIN = 1.5
YEAR_STABILITY_MIN = 3  # de 4 trimestres

#: Custos Topstep MNQ (mesma fricção da Decisao_2026-05-25-02, comparabilidade).
CUSTOS = CustosOperacionais.topstep_mnq(slippage_pontos_por_lado=0.25)

#: Hash dummy para JanelaWF sintéticas dos trimestres (não auditado aqui).
_HASH_DUMMY = "0" * 64


# ---------------------------------------------------------------------------
# Construtores de estratégia
# ---------------------------------------------------------------------------


def _construir_vvg_pura() -> EstrategiaVvgLateSessionReversal:
    """Plugin VVG puro com os parâmetros CONGELADOS (Tarefa 1)."""
    return EstrategiaVvgLateSessionReversal(
        parametros=ParametrosVvg.PadraoConfigurado(),
        custos=CUSTOS,
    )


def _construir_composicao() -> EstrategiaCircuitBreaker:
    """Composição canônica CB(SF(VVG)) (R3.3) com configs aprovadas."""
    vvg = _construir_vvg_pura()
    paths_spread = list((RAIZ / "dados" / "MNQ").glob("MNQ_*/tick/spread_minuto.csv"))
    sf = EstrategiaSpreadFilter(
        vvg,
        parametros=ParametrosSpreadFilter(
            modo="mediana_diaria",
            minutos_warmup_dia=30,
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
    # Nome descritivo para o relatório.
    cb.nome = "VVG-Late-Session CB(SF(VVG))"
    return cb


# ---------------------------------------------------------------------------
# Métricas auxiliares
# ---------------------------------------------------------------------------


def _pnl_total_janelas(resultado) -> float:
    """Soma o ``pnl_total`` de todas as janelas com status != falha."""
    total = 0.0
    for r in resultado.janelas:
        if r.status != "falha" and r.pnl_total is not None:
            total += float(r.pnl_total)
    return total


def _mediana_finita(resultado, metrica: str) -> Optional[float]:
    """Mediana dos valores finitos de ``metrica`` nas janelas."""
    valores = []
    for r in resultado.janelas:
        v = getattr(r, metrica, None)
        if v is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if vf == vf:  # not NaN
            valores.append(vf)
    if not valores:
        return None
    return float(statistics.median(valores))


def _contar_trades(resultado) -> int:
    return int(sum(int(r.numero_trades) for r in resultado.janelas))


def _janela_trimestre(
    dados: pd.DataFrame,
    inicio: pd.Timestamp,
    fim: pd.Timestamp,
) -> JanelaWF:
    """Constrói uma JanelaWF cujo Teste é [inicio, fim) e o Treino são ~90
    dias corridos antes de ``inicio`` (warmup do classificador)."""
    treino_inicio = inicio - pd.Timedelta(days=95)
    # Garante que o treino não anteceda o início dos dados.
    primeiro_ts = pd.Timestamp(dados["timestamp"].iloc[0])
    if treino_inicio < primeiro_ts:
        treino_inicio = primeiro_ts
    return JanelaWF(
        indice=0,
        treino_inicio=treino_inicio.to_pydatetime(),
        treino_fim=inicio.to_pydatetime(),
        teste_inicio=inicio.to_pydatetime(),
        teste_fim=fim.to_pydatetime(),
        hash_dados=_HASH_DUMMY,
    )


def _sharpe_trimestre(
    dados: pd.DataFrame,
    construtor,
    inicio: pd.Timestamp,
    fim: pd.Timestamp,
) -> tuple[Optional[float], int, float]:
    """Roda um BacktestRunner sobre o trimestre [inicio, fim) e devolve
    ``(sharpe, numero_trades, pnl_total)``. Sharpe pode ser ``None`` (sem
    trades suficientes)."""
    config = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=60,
        granularidade="1m",
        seed=42,
        custos=CUSTOS,
    )
    janela = _janela_trimestre(dados, inicio, fim)
    estrategia = construtor()
    res = BacktestRunner.executar(
        janela=janela,
        dados=dados,
        estrategia=estrategia,
        configuracao=config,
    )
    return res.sharpe_anualizado, int(res.numero_trades), float(res.pnl_total)


def _contar_dias_vvg_positivos(dados: pd.DataFrame) -> int:
    """Conta dias VVG-positivos na janela do WF (2025-07-01 .. 2026-05-15),
    rodando um classificador fresco sobre todo o histórico (warmup natural)."""
    classificador = VvgClassifier(ParametrosVvg.PadraoConfigurado())
    positivos = 0
    for _, barra in dados.iterrows():
        ts = pd.Timestamp(barra["timestamp"])
        resultado = classificador.on_barra(barra)
        if resultado is None:
            continue
        if WF_INICIO <= ts < WF_FIM and resultado.vvg_positivo:
            positivos += 1
    return positivos


# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------


def main() -> int:
    identificador = sys.argv[1] if len(sys.argv) > 1 else "2026-05-29-04"

    print("=" * 72)
    print(" WALK-FORWARD LONGO — VVG LATE-SESSION REVERSAL (Tarefa 11)")
    print(f" Identificador: {identificador}")
    print(" Spec: caos-vvg-late-session-reversal-mnq | parâmetros CONGELADOS")
    print("=" * 72)

    # --- Integridade: rebuild do manifesto isolado (padrão dos WF anteriores).
    print("Reconstruindo manifesto isolado...")
    DataManifestManager(raiz_dados=RAIZ_DADOS_ISO).build(instrumento="MNQ")

    cfg = ConfiguracaoWalkForward(
        tamanho_treino_dias_uteis=60,
        tamanho_teste_dias_uteis=10,
        granularidade="1m",
        seed=42,
        custos=CUSTOS,
    )

    engine = WalkForwardEngine(raiz_dados=RAIZ_DADOS_ISO)

    # ------------------------------------------------------------------
    # 1. WF da composição canônica CB(SF(VVG)) — alvo formal dos critérios.
    # ------------------------------------------------------------------
    print("\n[1/4] Rodando WF da composição canônica CB(SF(VVG))...")
    resultado_comp = engine.executar(
        estrategia=_construir_composicao(),
        configuracao=cfg,
        fonte_dados=ARQUIVOS_WF,
        identificador=identificador,
    )
    print(f"   status={resultado_comp.status} | janelas={len(resultado_comp.janelas)}")

    # ------------------------------------------------------------------
    # 2. WF do VVG puro — diagnóstico (núcleo do edge, sem overlays).
    # ------------------------------------------------------------------
    print("\n[2/4] Rodando WF do VVG puro (diagnóstico)...")
    resultado_vvg = engine.executar(
        estrategia=_construir_vvg_pura(),
        configuracao=cfg,
        fonte_dados=ARQUIVOS_WF,
        identificador=identificador,
    )
    print(f"   status={resultado_vvg.status} | janelas={len(resultado_vvg.janelas)}")

    # ------------------------------------------------------------------
    # 3. Year-stability por trimestre (BacktestRunner dedicado).
    # ------------------------------------------------------------------
    print("\n[3/4] Calculando year-stability por trimestre...")
    from caos.walk_forward.data_reader import SkillDataReader

    dados = SkillDataReader(raiz_dados=RAIZ_DADOS_ISO).carregar(ARQUIVOS_WF)

    year_comp: dict[str, dict] = {}
    year_vvg: dict[str, dict] = {}
    for nome_q, ini, fim in TRIMESTRES:
        s_c, n_c, p_c = _sharpe_trimestre(dados, _construir_composicao, ini, fim)
        s_v, n_v, p_v = _sharpe_trimestre(dados, _construir_vvg_pura, ini, fim)
        year_comp[nome_q] = {"sharpe": s_c, "trades": n_c, "pnl": p_c}
        year_vvg[nome_q] = {"sharpe": s_v, "trades": n_v, "pnl": p_v}
        print(
            f"   {nome_q}: CB(SF(VVG)) sharpe={s_c} trades={n_c} pnl={p_c:.2f} | "
            f"VVG puro sharpe={s_v} trades={n_v} pnl={p_v:.2f}"
        )

    # ------------------------------------------------------------------
    # 4. Contagem de dias VVG-positivos na janela do WF.
    # ------------------------------------------------------------------
    print("\n[4/4] Contando dias VVG-positivos na janela 2025-07 .. 2026-05...")
    dias_vvg_pos = _contar_dias_vvg_positivos(dados)
    print(f"   dias VVG-positivos = {dias_vvg_pos}")

    # ------------------------------------------------------------------
    # Métricas e avaliação dos critérios (alvo formal = composição).
    # ------------------------------------------------------------------
    def _metricas(resultado, year: dict) -> dict:
        sharpe_med = _mediana_finita(resultado, "sharpe_anualizado")
        calmar_med = _mediana_finita(resultado, "calmar")
        pnl_total = _pnl_total_janelas(resultado)
        n_trades = _contar_trades(resultado)
        trimestres_pos = sum(
            1 for q in year.values()
            if q["sharpe"] is not None and q["sharpe"] > 0
        )
        return {
            "sharpe_mediana": sharpe_med,
            "calmar_mediana": calmar_med,
            "pnl_total": pnl_total,
            "numero_trades": n_trades,
            "year_stability_positivos": trimestres_pos,
        }

    m_comp = _metricas(resultado_comp, year_comp)
    m_vvg = _metricas(resultado_vvg, year_vvg)

    def _avaliar(m: dict) -> dict:
        sh = m["sharpe_mediana"]
        ca = m["calmar_mediana"]
        c1 = sh is not None and sh >= SHARPE_MIN
        c2 = ca is not None and ca >= CALMAR_MIN
        c3 = m["pnl_total"] > 0
        c4 = m["year_stability_positivos"] >= YEAR_STABILITY_MIN
        return {
            "c1_sharpe_mediana_>=1.0": c1,
            "c2_calmar_mediana_>=1.5": c2,
            "c3_pnl_total_>0": c3,
            "c4_year_stability_>=3/4": c4,
            "aprovado": c1 and c2 and c3 and c4,
        }

    aval_comp = _avaliar(m_comp)
    aval_vvg = _avaliar(m_vvg)

    aprovado = aval_comp["aprovado"]
    caminho = "APROVACAO" if aprovado else "FALLBACK_A_REFUTACAO"

    # ------------------------------------------------------------------
    # Relatório.
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print(" RESULTADOS — ALVO FORMAL: COMPOSIÇÃO CB(SF(VVG)) (R3.3)")
    print("=" * 72)
    print(f" Sharpe mediana : {m_comp['sharpe_mediana']}  (criterio >= {SHARPE_MIN})")
    print(f" Calmar mediana : {m_comp['calmar_mediana']}  (criterio >= {CALMAR_MIN})")
    print(f" PnL total      : {m_comp['pnl_total']:.2f} pts  (criterio > 0)")
    print(f" Numero trades  : {m_comp['numero_trades']}")
    print(f" Year-stability : {m_comp['year_stability_positivos']}/4 trimestres "
          f"positivos  (criterio >= {YEAR_STABILITY_MIN}/4)")
    print(f" Dias VVG+      : {dias_vvg_pos}")
    print("-" * 72)
    for k, v in aval_comp.items():
        print(f"   {k}: {v}")
    print("=" * 72)
    print(" DIAGNÓSTICO — VVG PURO (sem overlays)")
    print("=" * 72)
    print(f" Sharpe mediana : {m_vvg['sharpe_mediana']}")
    print(f" Calmar mediana : {m_vvg['calmar_mediana']}")
    print(f" PnL total      : {m_vvg['pnl_total']:.2f} pts")
    print(f" Numero trades  : {m_vvg['numero_trades']}")
    print(f" Year-stability : {m_vvg['year_stability_positivos']}/4 trimestres positivos")
    print("=" * 72)
    print(f" CAMINHO ACIONADO: {caminho}")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Persistência: relatório canônico (composição) + criterios.json.
    # ------------------------------------------------------------------
    raiz_relatorios = RAIZ / "05_BACKTEST" / "walk_forward" / "relatorios"
    diretorio = RelatorioWriter().escrever(resultado_comp, raiz_saida=raiz_relatorios)
    print(f"\nRelatório canônico gravado em: {diretorio}")

    criterios_payload = {
        "identificador": identificador,
        "gerado_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "janela_wf": {"inicio": WF_INICIO.isoformat(), "fim": WF_FIM.isoformat()},
        "config_wf": "60+10 anchored",
        "custos": CUSTOS.model_dump(),
        "parametros_congelados": {
            "multiplicador_volume": 1.5,
            "threshold_gap_pct": 0.0015,
            "n_dias_baseline": 10,
            "stop_pontos": 472.25,
            "target_pontos": 944.25,
        },
        "dias_vvg_positivos": dias_vvg_pos,
        "criterios_pre_registrados": {
            "sharpe_mediana_min": SHARPE_MIN,
            "calmar_mediana_min": CALMAR_MIN,
            "pnl_total_min": 0.0,
            "year_stability_min": f"{YEAR_STABILITY_MIN}/4",
        },
        "composicao_canonica_CB_SF_VVG": {
            "status_wf": resultado_comp.status,
            "num_janelas": len(resultado_comp.janelas),
            "metricas": m_comp,
            "year_stability_trimestres": year_comp,
            "avaliacao": aval_comp,
        },
        "vvg_puro_diagnostico": {
            "status_wf": resultado_vvg.status,
            "num_janelas": len(resultado_vvg.janelas),
            "metricas": m_vvg,
            "year_stability_trimestres": year_vvg,
            "avaliacao": aval_vvg,
        },
        "decisao_automatica": {
            "aprovado": aprovado,
            "caminho": caminho,
        },
    }
    caminho_criterios = diretorio / "criterios.json"
    caminho_criterios.write_text(
        json.dumps(criterios_payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Avaliação dos critérios gravada em: {caminho_criterios}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
