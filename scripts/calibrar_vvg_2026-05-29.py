"""Calibracao obrigatoria dos parametros pendentes da VVG Late-Session Reversal.

Spec: caos-vvg-late-session-reversal-mnq (Tarefa 1).
Decisao precedente: Decisao_2026-05-29-03 (year-stability, T >= 2.0,
MaxContratos=1 fixo). Paper-base: arXiv 2605.11423 (Mesfin).

Objetivo
--------
Congelar UMA unica vez (regra anti-overfit, R10.2) os quatro parametros
pendentes do classificador/estrategia VVG na janela de calibracao
2025-03-17 a 2025-06-30, **disjunta** do Walk-Forward longo
(2025-07-01 a 2026-05-15) e do hold-out (2026-06+):

1. ``multiplicador_volume``   in {1.3, 1.5, 1.7}
2. ``threshold_gap_pct``      in {0.0015, 0.003, 0.0045}
3. ``stop_pontos``            = round(ATR(14) mediano x 1.0 / tick) x tick
4. ``target_pontos``          = round(ATR(14) mediano x 2.0 / tick) x tick

A combinacao (multiplicador, threshold) escolhida e a que produz
elegibilidade na faixa 15-25% (coerente com ~17% reportado no abstract
do paper Mesfin); havendo varias na faixa, a mais proxima de 17%.

Features VVG por dia util (definicao herdada de R1.1 do requirements e
da dataclass ParametrosVvg do design.md):

- ``volume_morning``  = soma do volume das barras em [09:30, 10:00) EST.
- ``volume_baseline`` = media movel de N=10 dias do volume da janela
  morning [09:30, 10:00) EST, com ``.shift(1)`` (evita look-ahead).

  NOTA DE INTERPRETACAO (discrepancia tarefa vs design): o enunciado da
  Tarefa 1 descreve o baseline sobre a PRIMEIRA HORA [09:30, 10:30) (60
  min), enquanto ``volume_morning`` e medido em 30 min [09:30, 10:00).
  Comparar soma de 30 min contra media de soma de 60 min mistura
  unidades e enviesa a razao para baixo (vide secao de SENSIBILIDADE no
  relatorio: elegibilidade cai para ~1,9%, fora da faixa-alvo). O
  ``design.md`` desta spec ja resolveu essa ambiguidade: "a
  implementacao adota 09:30-10:00 (= mesma janela do volume_morning)
  para simplicidade". Seguimos o design (baseline tambem em 30 min),
  o que recupera a faixa 15-25% pretendida. O baseline de 60 min e
  reportado como SENSIBILIDADE para transparencia.
- ``gap_pct``         = abs(open_RTH(D) - close_RTH(D-1)) / close_RTH(D-1),
  onde D-1 e o dia util valido imediatamente anterior. open_RTH e a
  abertura da primeira barra do RTH (09:30 EST) e close_RTH e o fechamento
  da ultima barra do RTH (~15:59 EST) — interpretacao coerente com
  R1.1 ("open(09:30) - close(D-1)").

Conversao de fuso
-----------------
O dataset esta em UTC (sufixo 'Z'). RTH 09:30 EST = 13:30 UTC (EDT,
UTC-4) ou 14:30 UTC (EST, UTC-5) conforme horario de verao. NAO se
hardcoda offset: usa-se ``zoneinfo.ZoneInfo("America/New_York")`` para
tratar DST automaticamente. Em mar-jun/2025 os EUA estao em EDT.

Filtro de dia valido (herdado do Spec 4)
----------------------------------------
Descarta sabados/domingos (``weekday() >= 5``) e dias com menos de
``MIN_BARRAS_DIA_VALIDO=300`` barras de minuto. Reproduz a logica de
``_calcular_range_diario`` de ``orb_crabel.py`` (agrupamento por dia),
porem aqui o agrupamento e por **data local de Nova York**, pois as
janelas RTH sao definidas em horario do mercado.

Plataforma: Windows. Antes de rodar:
    set PYTHONIOENCODING=utf-8
    python scripts\\calibrar_vvg_2026-05-29.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, time
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Constantes da calibracao
# ----------------------------------------------------------------------

#: Caminho do dataset de calibracao (MNQ minute last, contrato 06-25).
CAMINHO_CSV = r"e:\CAOS\dados\MNQ\_concat_minute_last\01_MNQ_06-25.csv"

#: Fuso do mercado (CME RTH em horario de Nova York). DST automatico.
TZ_NY = ZoneInfo("America/New_York")
TZ_UTC = ZoneInfo("UTC")

#: Janela de calibracao (disjunta do WF longo 2025-07-01 a 2026-05-15).
JANELA_INICIO = pd.Timestamp("2025-03-17", tz="UTC")
JANELA_FIM = pd.Timestamp("2025-06-30 23:59:59", tz="UTC")

#: Tick size do MNQ em pontos (CME oficial).
TICK_SIZE_MNQ: float = 0.25

#: Minimo de barras de minuto para um dia ser valido (Spec 4 herdado).
MIN_BARRAS_DIA_VALIDO: int = 300

#: Janela do baseline rolling de volume, em dias uteis validos.
N_DIAS_BASELINE: int = 10

#: Janela do ATR diario.
N_DIAS_ATR: int = 14

#: Janelas RTH em horario local de Nova York (EST/EDT).
RTH_INICIO = time(9, 30)      # abertura do pregao regular
RTH_FIM = time(16, 0)         # fechamento do pregao regular
MORNING_FIM = time(10, 0)     # fim da janela volume_morning (30 min)
PRIMEIRA_HORA_FIM = time(10, 30)  # fim da janela de SENSIBILIDADE (60 min)

#: Grades do sweep (R10.2: valores discretos, sem otimizacao continua).
GRID_MULTIPLICADOR = [1.3, 1.5, 1.7]
GRID_THRESHOLD_GAP = [0.0015, 0.003, 0.0045]

#: Faixa-alvo de elegibilidade e ancora (~17% do abstract de Mesfin).
ELEGIBILIDADE_MIN = 15.0
ELEGIBILIDADE_MAX = 25.0
ELEGIBILIDADE_ANCORA = 17.0

#: Defaults antecipados no design.md (placeholders pre-registrados). Usados
#: APENAS como criterio de desempate determinístico quando duas combos
#: ficam igualmente proximas da ancora de 17%. Nao influem na faixa.
DESIGN_DEFAULT_MULT = 1.5
DESIGN_DEFAULT_GAP = 0.003


# ----------------------------------------------------------------------
# Carregamento e preparo dos dados
# ----------------------------------------------------------------------

def carregar_dados(caminho: str) -> pd.DataFrame:
    """Le o CSV minute last e devolve DataFrame com timestamp UTC + local NY.

    Schema esperado (verificado no cabecalho do arquivo):
    ``timestamp,open,high,low,close,volume`` com timestamp ISO sufixo 'Z'.
    """
    df = pd.read_csv(caminho)
    esperado = {"timestamp", "open", "high", "low", "close", "volume"}
    faltando = esperado - set(df.columns)
    if faltando:
        raise ValueError(f"Colunas ausentes no CSV: {sorted(faltando)}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Volume pode vir com celulas vazias (visto na 1a linha do arquivo) —
    # tratar como 0 para nao quebrar somas.
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    df = df.sort_values("timestamp").reset_index(drop=True)
    # Conversao de fuso (DST tratado pela zoneinfo).
    ny = df["timestamp"].dt.tz_convert(TZ_NY)
    df["data_ny"] = ny.dt.date
    df["hora_ny"] = ny.dt.time
    df["weekday"] = ny.dt.weekday  # 0=segunda ... 6=domingo
    return df


def filtrar_janela(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra a janela de calibracao 2025-03-17 a 2025-06-30 (UTC)."""
    mask = (df["timestamp"] >= JANELA_INICIO) & (df["timestamp"] <= JANELA_FIM)
    return df[mask].copy()


# ----------------------------------------------------------------------
# Features diarias
# ----------------------------------------------------------------------

@dataclass
class FeaturesDia:
    """Features VVG + OHLC diario de um unico dia util."""

    data: date
    n_barras: int
    valido: bool
    open_rth: float
    close_rth: float
    high_rth: float
    low_rth: float
    high_dia: float
    low_dia: float
    close_dia: float
    volume_morning: float       # soma volume [09:30, 10:00)
    volume_primeira_hora: float  # soma volume [09:30, 10:30)


def _entre(horas: pd.Series, ini: time, fim: time) -> pd.Series:
    """Mascara booleana ``ini <= hora < fim`` para coluna ``hora_ny``."""
    return (horas >= ini) & (horas < fim)


def construir_features_diarias(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega o minute em features por dia util de Nova York.

    Devolve DataFrame indexado por ``data`` (ordenado) com as colunas de
    :class:`FeaturesDia` mais ``gap_pct``, ``volume_baseline``, ``tr`` e
    ``atr14``. Dias invalidos (fim de semana ou < 300 barras ou sem RTH)
    sao mantidos com ``valido=False`` para transparencia, mas excluidos
    dos calculos de baseline/gap/ATR.
    """
    registros: list[FeaturesDia] = []
    for data_ny, grupo in df.groupby("data_ny"):
        n_barras = len(grupo)
        weekday = int(grupo["weekday"].iloc[0])
        rth = grupo[_entre(grupo["hora_ny"], RTH_INICIO, RTH_FIM)]
        tem_rth = not rth.empty
        morning = grupo[_entre(grupo["hora_ny"], RTH_INICIO, MORNING_FIM)]
        primeira_hora = grupo[
            _entre(grupo["hora_ny"], RTH_INICIO, PRIMEIRA_HORA_FIM)
        ]
        valido = (
            weekday < 5
            and n_barras >= MIN_BARRAS_DIA_VALIDO
            and tem_rth
            and not morning.empty
        )
        registros.append(
            FeaturesDia(
                data=data_ny,
                n_barras=n_barras,
                valido=valido,
                open_rth=float(rth["open"].iloc[0]) if tem_rth else float("nan"),
                close_rth=float(rth["close"].iloc[-1]) if tem_rth else float("nan"),
                high_rth=float(rth["high"].max()) if tem_rth else float("nan"),
                low_rth=float(rth["low"].min()) if tem_rth else float("nan"),
                high_dia=float(grupo["high"].max()),
                low_dia=float(grupo["low"].min()),
                close_dia=float(grupo["close"].iloc[-1]),
                volume_morning=float(morning["volume"].sum()),
                volume_primeira_hora=float(primeira_hora["volume"].sum()),
            )
        )

    feat = pd.DataFrame([r.__dict__ for r in registros]).sort_values("data")
    feat = feat.reset_index(drop=True)

    # A partir daqui, tudo e calculado SOMENTE sobre dias validos, em ordem.
    validos = feat[feat["valido"]].copy().reset_index(drop=True)

    # Baseline rolling de 10 dias, com shift(1) para nao usar o proprio
    # dia (anti look-ahead).
    #
    # PRINCIPAL (segue design.md): baseline sobre a MESMA janela morning
    # de 30 min usada por volume_morning. Mantem unidades coerentes.
    validos["volume_baseline"] = (
        validos["volume_morning"]
        .rolling(window=N_DIAS_BASELINE, min_periods=N_DIAS_BASELINE)
        .mean()
        .shift(1)
    )
    # SENSIBILIDADE (literal do enunciado da Tarefa 1): baseline sobre a
    # primeira hora de 60 min. Reportado apenas para transparencia; NAO e
    # o usado na selecao.
    validos["volume_baseline_60min"] = (
        validos["volume_primeira_hora"]
        .rolling(window=N_DIAS_BASELINE, min_periods=N_DIAS_BASELINE)
        .mean()
        .shift(1)
    )

    # Gap percentual: abertura RTH do dia vs fechamento RTH do dia valido
    # anterior.
    close_rth_anterior = validos["close_rth"].shift(1)
    validos["gap_pct"] = (
        (validos["open_rth"] - close_rth_anterior).abs() / close_rth_anterior
    )

    # ATR(14) diario PRINCIPAL (prescrito pela Tarefa 1): True Range sobre
    # o range diario completo (24h Globex), close do dia valido anterior.
    close_dia_anterior = validos["close_dia"].shift(1)
    tr = pd.concat(
        [
            (validos["high_dia"] - validos["low_dia"]).abs(),
            (validos["high_dia"] - close_dia_anterior).abs(),
            (validos["low_dia"] - close_dia_anterior).abs(),
        ],
        axis=1,
    ).max(axis=1)
    validos["tr"] = tr
    validos["range_dia"] = validos["high_dia"] - validos["low_dia"]
    validos["atr14"] = (
        tr.rolling(window=N_DIAS_ATR, min_periods=N_DIAS_ATR).mean()
    )

    # ATR(14) de SENSIBILIDADE: range somente do RTH (09:30-16:00). Mais
    # coerente com o horizonte intradiario do trade, reportado para
    # transparencia (NAO usado para congelar stop/target).
    close_rth_ant = validos["close_rth"].shift(1)
    tr_rth = pd.concat(
        [
            (validos["high_rth"] - validos["low_rth"]).abs(),
            (validos["high_rth"] - close_rth_ant).abs(),
            (validos["low_rth"] - close_rth_ant).abs(),
        ],
        axis=1,
    ).max(axis=1)
    validos["range_rth"] = validos["high_rth"] - validos["low_rth"]
    validos["atr14_rth"] = (
        tr_rth.rolling(window=N_DIAS_ATR, min_periods=N_DIAS_ATR).mean()
    )

    # Reanexa as colunas calculadas ao frame completo (dias invalidos ficam
    # com NaN nessas colunas).
    cols_calc = [
        "volume_baseline",
        "volume_baseline_60min",
        "gap_pct",
        "tr",
        "range_dia",
        "atr14",
        "range_rth",
        "atr14_rth",
    ]
    feat = feat.merge(
        validos[["data", *cols_calc]], on="data", how="left"
    )
    return feat


# ----------------------------------------------------------------------
# Sweep de elegibilidade
# ----------------------------------------------------------------------

@dataclass
class ResultadoCombo:
    multiplicador: float
    threshold_gap: float
    n_positivos: int
    pct_elegibilidade: float


def dias_classificaveis(feat: pd.DataFrame) -> pd.DataFrame:
    """Subconjunto de dias validos com baseline E gap disponiveis.

    Um dia so e classificavel quando ja possui >= N_DIAS_BASELINE dias
    validos anteriores (baseline nao-NaN) e tem um dia valido anterior
    para o gap (gap nao-NaN). Dias em warmup nunca sao VVG-positivos
    (R1.4), por isso o denominador da elegibilidade e o numero de dias
    classificaveis.
    """
    return feat[
        feat["valido"]
        & feat["volume_baseline"].notna()
        & feat["gap_pct"].notna()
    ].copy()


def rodar_sweep(
    feat: pd.DataFrame, coluna_baseline: str = "volume_baseline"
) -> list[ResultadoCombo]:
    """Conta dias VVG-positivos para cada combinacao do grid.

    ``coluna_baseline`` permite alternar entre o baseline PRINCIPAL (30
    min, ``volume_baseline``) e o de SENSIBILIDADE (60 min,
    ``volume_baseline_60min``).
    """
    classificaveis = feat[
        feat["valido"]
        & feat[coluna_baseline].notna()
        & feat["gap_pct"].notna()
    ].copy()
    n = len(classificaveis)
    resultados: list[ResultadoCombo] = []
    for mult in GRID_MULTIPLICADOR:
        for thr in GRID_THRESHOLD_GAP:
            positivos = classificaveis[
                (classificaveis["volume_morning"]
                 >= mult * classificaveis[coluna_baseline])
                & (classificaveis["gap_pct"] >= thr)
            ]
            n_pos = int(len(positivos))
            pct = (100.0 * n_pos / n) if n else 0.0
            resultados.append(ResultadoCombo(mult, thr, n_pos, pct))
    return resultados


def selecionar_combo(
    resultados: list[ResultadoCombo],
) -> tuple[ResultadoCombo, bool]:
    """Seleciona a combinacao alvo.

    Prioridade:
    1. Combos com elegibilidade em [15, 25]% — escolher a mais proxima de
       17%.
    2. Empate na distancia a 17%: desempata pela proximidade aos defaults
       antecipados no design.md (mult=1.5, gap=0.003), preferindo manter
       o multiplicador de volume pre-registrado. Criterio totalmente
       determinístico (sem random).
    3. Se nenhuma cair na faixa, escolher globalmente a mais proxima de
       17% e sinalizar ``na_faixa=False``.

    Devolve ``(combo, na_faixa)``.
    """
    def chave(r: ResultadoCombo) -> tuple[float, float, float]:
        dist_ancora = abs(r.pct_elegibilidade - ELEGIBILIDADE_ANCORA)
        dist_mult = abs(r.multiplicador - DESIGN_DEFAULT_MULT)
        dist_gap = abs(r.threshold_gap - DESIGN_DEFAULT_GAP)
        return (round(dist_ancora, 6), dist_mult, dist_gap)

    na_faixa = [
        r for r in resultados
        if ELEGIBILIDADE_MIN <= r.pct_elegibilidade <= ELEGIBILIDADE_MAX
    ]
    if na_faixa:
        return min(na_faixa, key=chave), True
    return min(resultados, key=chave), False


# ----------------------------------------------------------------------
# Stop / Target via ATR
# ----------------------------------------------------------------------

def arredondar_tick(valor: float) -> float:
    """Arredonda para o multiplo de tick MNQ mais proximo (0.25 pts)."""
    return round(valor / TICK_SIZE_MNQ) * TICK_SIZE_MNQ


def derivar_stop_target(atr_mediano: float) -> tuple[float, float]:
    """``stop = ATR x 1.0``; ``target = ATR x 2.0`` arredondados ao tick."""
    stop = arredondar_tick(atr_mediano * 1.0)
    target = arredondar_tick(atr_mediano * 2.0)
    return stop, target


# ----------------------------------------------------------------------
# Relatorio
# ----------------------------------------------------------------------

def imprimir_relatorio(feat: pd.DataFrame) -> None:
    """Imprime a tabela completa de calibracao."""
    validos = feat[feat["valido"]].copy()
    classificaveis = dias_classificaveis(feat)
    n_total_dias = len(feat)
    n_validos = len(validos)
    n_classificaveis = len(classificaveis)

    data_ini = feat["data"].min()
    data_fim = feat["data"].max()

    print("=" * 70)
    print(" CALIBRACAO VVG LATE-SESSION REVERSAL — 2026-05-29")
    print(" Spec: caos-vvg-late-session-reversal-mnq | Tarefa 1")
    print("=" * 70)
    print(f"Dataset            : {CAMINHO_CSV}")
    print(f"Janela calibracao  : {data_ini} a {data_fim} (local NY)")
    print(f"Barras carregadas  : {int(feat['n_barras'].sum()):,}")
    print(f"Dias no periodo    : {n_total_dias}")
    print(f"Dias uteis validos : {n_validos} "
          f"(weekday<5 e >= {MIN_BARRAS_DIA_VALIDO} barras)")
    print(f"Dias classificaveis: {n_classificaveis} "
          f"(com baseline de {N_DIAS_BASELINE}d e gap disponiveis)")
    print(f"Warmup descartado  : {n_validos - n_classificaveis} dias "
          f"(baseline/gap incompletos — R1.4)")

    # --- Estatisticas de range / ATR ---
    serie_range = validos["range_dia"].dropna()
    serie_atr = validos["atr14"].dropna()
    serie_range_rth = validos["range_rth"].dropna()
    serie_atr_rth = validos["atr14_rth"].dropna()
    print("\n" + "-" * 70)
    print(" RANGE DIARIO E ATR(14) — em pontos MNQ")
    print("-" * 70)
    print(f"Range 24h Globex : media={serie_range.mean():8.2f}  "
          f"mediana={serie_range.median():8.2f}  "
          f"(n={len(serie_range)})")
    if len(serie_atr):
        print(f"ATR(14) 24h      : media={serie_atr.mean():8.2f}  "
              f"mediana={serie_atr.median():8.2f}  "
              f"(n={len(serie_atr)})  <- PRESCRITO p/ stop/target")
    else:
        print("ATR(14) 24h      : INDISPONIVEL — janela < 14 dias validos")
    print(f"Range RTH-only   : media={serie_range_rth.mean():8.2f}  "
          f"mediana={serie_range_rth.median():8.2f}  "
          f"(n={len(serie_range_rth)})  [sensibilidade]")
    if len(serie_atr_rth):
        print(f"ATR(14) RTH-only : media={serie_atr_rth.mean():8.2f}  "
              f"mediana={serie_atr_rth.median():8.2f}  "
              f"(n={len(serie_atr_rth)})  [sensibilidade]")

    # --- Estatisticas de volume / gap (diagnostico) ---
    print("\n" + "-" * 70)
    print(" FEATURES VVG (dias classificaveis) — diagnostico")
    print("-" * 70)
    if n_classificaveis:
        razao = (classificaveis["volume_morning"]
                 / classificaveis["volume_baseline"])
        print(f"volume_morning    : media={classificaveis['volume_morning'].mean():12.1f}  "
              f"mediana={classificaveis['volume_morning'].median():12.1f}")
        print(f"volume_baseline   : media={classificaveis['volume_baseline'].mean():12.1f}  "
              f"mediana={classificaveis['volume_baseline'].median():12.1f}")
        print(f"razao morning/base: media={razao.mean():12.3f}  "
              f"mediana={razao.median():12.3f}  max={razao.max():12.3f}")
        print(f"gap_pct           : media={classificaveis['gap_pct'].mean()*100:11.3f}%  "
              f"mediana={classificaveis['gap_pct'].median()*100:11.3f}%  "
              f"max={classificaveis['gap_pct'].max()*100:8.3f}%")

    # --- Sweep ---
    resultados = rodar_sweep(feat, "volume_baseline")
    print("\n" + "-" * 70)
    print(" SWEEP PRINCIPAL (baseline 30 min — segue design.md)")
    print(" denominador = dias classificaveis")
    print("-" * 70)
    print(f"{'mult_volume':<14}{'threshold_gap':<16}"
          f"{'dias VVG+':<12}{'% elegib.':<12}{'faixa 15-25%':<14}")
    for r in resultados:
        na = "SIM" if ELEGIBILIDADE_MIN <= r.pct_elegibilidade <= ELEGIBILIDADE_MAX else "-"
        print(f"{r.multiplicador:<14}{r.threshold_gap:<16}"
              f"{r.n_positivos:<12}{r.pct_elegibilidade:<12.1f}{na:<14}")

    # --- Sweep de sensibilidade (baseline 60 min, literal do enunciado) ---
    resultados_60 = rodar_sweep(feat, "volume_baseline_60min")
    print("\n" + "-" * 70)
    print(" SWEEP SENSIBILIDADE (baseline 60 min — literal do enunciado)")
    print(" Mistura unidades (morning 30 min vs baseline 60 min) -> vies p/ baixo")
    print("-" * 70)
    print(f"{'mult_volume':<14}{'threshold_gap':<16}"
          f"{'dias VVG+':<12}{'% elegib.':<12}{'faixa 15-25%':<14}")
    for r in resultados_60:
        na = "SIM" if ELEGIBILIDADE_MIN <= r.pct_elegibilidade <= ELEGIBILIDADE_MAX else "-"
        print(f"{r.multiplicador:<14}{r.threshold_gap:<16}"
              f"{r.n_positivos:<12}{r.pct_elegibilidade:<12.1f}{na:<14}")

    # --- Selecao ---
    combo, na_faixa = selecionar_combo(resultados)
    print("\n" + "-" * 70)
    print(" COMBINACAO SELECIONADA")
    print("-" * 70)
    print(f"multiplicador_volume = {combo.multiplicador}")
    print(f"threshold_gap_pct    = {combo.threshold_gap}")
    print(f"n_dias_baseline      = {N_DIAS_BASELINE}")
    print(f"elegibilidade        = {combo.pct_elegibilidade:.1f}% "
          f"({combo.n_positivos}/{n_classificaveis} dias)")
    if na_faixa:
        print(f"-> DENTRO da faixa 15-25% (ancora {ELEGIBILIDADE_ANCORA}%).")
    else:
        print(f"-> FORA da faixa 15-25%. Escolhida a mais proxima de "
              f"{ELEGIBILIDADE_ANCORA}% (vide AVISO abaixo).")

    # --- Stop / Target ---
    print("\n" + "-" * 70)
    print(" STOP / TARGET via ATR(14) mediano (PRESCRITO: ATR 24h)")
    print("-" * 70)
    if len(serie_atr):
        atr_med = float(serie_atr.median())
        stop, target = derivar_stop_target(atr_med)
        print(f"ATR(14) 24h mediano  = {atr_med:.2f} pontos")
        print(f"stop_pontos  = round({atr_med:.2f} x 1.0 / {TICK_SIZE_MNQ}) "
              f"x {TICK_SIZE_MNQ} = {stop:.2f} pontos")
        print(f"target_pontos= round({atr_med:.2f} x 2.0 / {TICK_SIZE_MNQ}) "
              f"x {TICK_SIZE_MNQ} = {target:.2f} pontos")
        print(f"  (em USD/contrato MNQ: stop ~= USD {stop * 2:.0f}, "
              f"target ~= USD {target * 2:.0f})")
        print("\n[AVISO DE RISCO] O ATR(14) diario reflete o range de ~23h do")
        print("Globex, mas o trade VVG dura ~80 min (14:30->15:50 EST). Stop de")
        print(f"{stop:.0f} pts (USD {stop*2:.0f}) consome grande fracao do TDD")
        print("Topstep (USD 2.500) num unico trade. Vide Zettel para tratamento.")
        if len(serie_atr_rth):
            atr_rth_med = float(serie_atr_rth.median())
            stop_rth, target_rth = derivar_stop_target(atr_rth_med)
            print(f"\n[SENSIBILIDADE] ATR(14) RTH-only mediano = {atr_rth_med:.2f} pts")
            print(f"  stop_rth = {stop_rth:.2f} pts | target_rth = {target_rth:.2f} pts")
    else:
        stop = target = float("nan")
        print("ATR(14) INDISPONIVEL — stop/target nao derivaveis nesta janela.")

    # --- Resumo final dos 5 valores congelados ---
    print("\n" + "=" * 70)
    print(" VALORES FINAIS CONGELADOS (anti-overfit — NAO recalibrar)")
    print("=" * 70)
    print(f"multiplicador_volume = {combo.multiplicador}")
    print(f"threshold_gap_pct    = {combo.threshold_gap}")
    print(f"n_dias_baseline      = {N_DIAS_BASELINE}")
    print(f"stop_pontos          = {stop:.2f}" if len(serie_atr) else
          "stop_pontos          = INDISPONIVEL")
    print(f"target_pontos        = {target:.2f}" if len(serie_atr) else
          "target_pontos        = INDISPONIVEL")
    print(f"elegibilidade        = {combo.pct_elegibilidade:.1f}% "
          f"({'NA FAIXA 15-25%' if na_faixa else 'FORA DA FAIXA 15-25%'})")
    print("=" * 70)


def main() -> None:
    df = carregar_dados(CAMINHO_CSV)
    df_janela = filtrar_janela(df)
    if df_janela.empty:
        print("ERRO: nenhuma barra na janela de calibracao.", file=sys.stderr)
        sys.exit(1)
    feat = construir_features_diarias(df_janela)
    imprimir_relatorio(feat)


if __name__ == "__main__":
    main()
