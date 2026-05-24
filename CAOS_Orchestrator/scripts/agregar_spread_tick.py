"""Agrega tick.txt do NT8 em spread_minuto.csv (streaming).

Para cada minuto, produz:

- num_ticks_last: numero de operacoes (volume tick)
- volume_total:   soma do volume das operacoes
- last_first / last_last / last_high / last_low: agregados de price
- bid_min / bid_max / bid_avg: estatistica do bid no minuto
- ask_min / ask_max / ask_avg: estatistica do ask no minuto
- spread_avg: ask_avg - bid_avg (em pontos)
- spread_median: mediana dos spread instantaneos amostrados a cada
  par bid/ask sequencial.
- spread_min / spread_max

Estrategia de streaming:

- Le os tres arquivos (.Last.txt, .Bid.txt, .Ask.txt) em paralelo,
  por contrato.
- Mantem buffer de bid/ask correntes (ultimo valor visto) para
  calcular spread quando um Last entra.
- Agrega em estruturas por minuto e flush a cada novo minuto.

Uso: python scripts/agregar_spread_tick.py <contrato>
Ex.:  python scripts/agregar_spread_tick.py MNQ_06-25
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median, mean


def parsear_timestamp_nt8(bruto: str) -> datetime | None:
    """Converte 'AAAAMMDD HHMMSS FRAC' em datetime UTC.

    FRAC pode ter ate 7 digitos (decimicrossegundos). Trunca a 6
    para microssegundos (precisao do datetime).
    """
    try:
        partes = bruto.split(" ")
        if len(partes) != 3:
            return None
        data_s, hms_s, frac_s = partes
        ano = int(data_s[0:4])
        mes = int(data_s[4:6])
        dia = int(data_s[6:8])
        hora = int(hms_s[0:2])
        minuto = int(hms_s[2:4])
        seg = int(hms_s[4:6])
        # FRAC tem 7 digitos => fracao de segundo em 100ns. 6 digitos => us.
        frac_int = int(frac_s[:6].ljust(6, "0"))  # microsec
        return datetime(ano, mes, dia, hora, minuto, seg, frac_int, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def chave_minuto(ts: datetime) -> datetime:
    """Trunca para o minuto inteiro UTC."""
    return ts.replace(second=0, microsecond=0)


def main(contrato: str) -> int:
    raiz = Path(r"e:\CAOS\dados\MNQ") / contrato / "tick"
    if not raiz.is_dir():
        print(f"ERRO: {raiz} nao existe.", file=sys.stderr)
        return 1

    base_nome = contrato.replace("_", " ")  # MNQ 06-25
    arq_last = raiz / f"{base_nome}.Last.txt"
    arq_bid = raiz / f"{base_nome}.Bid.txt"
    arq_ask = raiz / f"{base_nome}.Ask.txt"

    for arq in (arq_last, arq_bid, arq_ask):
        if not arq.is_file():
            print(f"ERRO: {arq} nao existe.", file=sys.stderr)
            return 1

    print(f"[setup] contrato={contrato}")
    print(f"  Last: {arq_last.stat().st_size / 1e9:.2f} GB")
    print(f"  Bid:  {arq_bid.stat().st_size / 1e9:.2f} GB")
    print(f"  Ask:  {arq_ask.stat().st_size / 1e9:.2f} GB")

    # Estado por minuto.
    # Para evitar carregar tudo, vamos processar em ordem cronologica
    # ASSUMINDO que os 3 arquivos estao ordenados por timestamp (geralmente
    # estao). Faz merge stream comparando timestamps.
    saida = raiz / "spread_minuto.csv"
    print(f"  saida: {saida}")

    # Resume safety: pula se ja existe e tem >100 KB (provavelmente
    # completo). Evita reprocessar 50 GB de tick por engano.
    if saida.is_file() and saida.stat().st_size > 100 * 1024:
        print(f"  [skip] spread_minuto.csv ja existe ({saida.stat().st_size/1e6:.1f} MB). "
              f"Remova manualmente para reprocessar.")
        return 0

    minuto_atual: datetime | None = None
    last_prices: list[float] = []
    last_volumes: list[int] = []
    bid_values: list[float] = []
    ask_values: list[float] = []
    bid_corrente: float | None = None
    ask_corrente: float | None = None
    spreads_amostrados: list[float] = []

    linhas_processadas = 0
    minutos_emitidos = 0
    inicio_real = datetime.now(timezone.utc)

    with saida.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([
            "minuto_utc",
            "num_ticks_last",
            "volume_total",
            "last_first",
            "last_last",
            "last_high",
            "last_low",
            "bid_min",
            "bid_max",
            "bid_avg",
            "ask_min",
            "ask_max",
            "ask_avg",
            "spread_avg",
            "spread_median",
            "spread_min",
            "spread_max",
            "spread_n_amostras",
        ])

        def flush_minuto() -> None:
            nonlocal minutos_emitidos
            if minuto_atual is None:
                return
            num_last = len(last_prices)
            vol_total = sum(last_volumes)
            last_first = last_prices[0] if last_prices else None
            last_last_val = last_prices[-1] if last_prices else None
            last_high = max(last_prices) if last_prices else None
            last_low = min(last_prices) if last_prices else None
            bid_min = min(bid_values) if bid_values else None
            bid_max = max(bid_values) if bid_values else None
            bid_avg = mean(bid_values) if bid_values else None
            ask_min = min(ask_values) if ask_values else None
            ask_max = max(ask_values) if ask_values else None
            ask_avg = mean(ask_values) if ask_values else None
            if bid_avg is not None and ask_avg is not None:
                spread_avg_val = ask_avg - bid_avg
            else:
                spread_avg_val = None
            spread_median_val = median(spreads_amostrados) if spreads_amostrados else None
            spread_min_val = min(spreads_amostrados) if spreads_amostrados else None
            spread_max_val = max(spreads_amostrados) if spreads_amostrados else None

            writer.writerow([
                minuto_atual.strftime("%Y-%m-%dT%H:%M:00Z"),
                num_last,
                vol_total,
                last_first,
                last_last_val,
                last_high,
                last_low,
                bid_min,
                bid_max,
                bid_avg,
                ask_min,
                ask_max,
                ask_avg,
                spread_avg_val,
                spread_median_val,
                spread_min_val,
                spread_max_val,
                len(spreads_amostrados),
            ])
            minutos_emitidos += 1

        # 3-way merge: avanca o iterator de menor timestamp.
        f_last = arq_last.open("r", encoding="utf-8")
        f_bid = arq_bid.open("r", encoding="utf-8")
        f_ask = arq_ask.open("r", encoding="utf-8")

        def proxima(f):
            line = f.readline()
            if not line:
                return None
            return line.rstrip("\n")

        cur_last = proxima(f_last)
        cur_bid = proxima(f_bid)
        cur_ask = proxima(f_ask)

        try:
            while cur_last is not None or cur_bid is not None or cur_ask is not None:
                # Decide qual fonte avancar (menor timestamp).
                # Parsear apenas o timestamp para comparacao.
                cands = []
                for tag, line in (("L", cur_last), ("B", cur_bid), ("A", cur_ask)):
                    if line is None:
                        continue
                    # Timestamp e tudo antes do primeiro ';'.
                    idx = line.find(";")
                    if idx < 0:
                        continue
                    ts_s = line[:idx]
                    ts = parsear_timestamp_nt8(ts_s)
                    if ts is None:
                        # Linha malformada: pular.
                        cands.append((tag, None, line))
                        continue
                    cands.append((tag, ts, line))

                if not cands:
                    break

                # Escolhe o de menor timestamp (None vira ultimo).
                cands_validos = [c for c in cands if c[1] is not None]
                if not cands_validos:
                    # Avanca todos que sao None timestamp (skip linhas malformadas).
                    for tag, _, _ in cands:
                        if tag == "L":
                            cur_last = proxima(f_last)
                        elif tag == "B":
                            cur_bid = proxima(f_bid)
                        elif tag == "A":
                            cur_ask = proxima(f_ask)
                    continue

                cands_validos.sort(key=lambda x: x[1])
                tag, ts, line = cands_validos[0]

                # Detectar transicao de minuto.
                novo_minuto = chave_minuto(ts)
                if minuto_atual is None:
                    minuto_atual = novo_minuto
                elif novo_minuto > minuto_atual:
                    flush_minuto()
                    minuto_atual = novo_minuto
                    last_prices = []
                    last_volumes = []
                    bid_values = []
                    ask_values = []
                    spreads_amostrados = []

                # Parsear campos.
                campos = line.split(";")
                if tag == "L" and len(campos) >= 5:
                    try:
                        price = float(campos[1])
                        vol = int(campos[4])
                        last_prices.append(price)
                        last_volumes.append(vol)
                        # Amostra spread se temos bid+ask correntes.
                        if bid_corrente is not None and ask_corrente is not None:
                            spreads_amostrados.append(ask_corrente - bid_corrente)
                    except (ValueError, IndexError):
                        pass
                elif tag == "B" and len(campos) >= 2:
                    try:
                        price = float(campos[1])
                        bid_corrente = price
                        bid_values.append(price)
                    except (ValueError, IndexError):
                        pass
                elif tag == "A" and len(campos) >= 2:
                    try:
                        price = float(campos[1])
                        ask_corrente = price
                        ask_values.append(price)
                    except (ValueError, IndexError):
                        pass

                # Avanca a fonte escolhida.
                if tag == "L":
                    cur_last = proxima(f_last)
                elif tag == "B":
                    cur_bid = proxima(f_bid)
                elif tag == "A":
                    cur_ask = proxima(f_ask)

                linhas_processadas += 1
                if linhas_processadas % 1_000_000 == 0:
                    elapsed = (datetime.now(timezone.utc) - inicio_real).total_seconds()
                    rate = linhas_processadas / max(elapsed, 0.1)
                    print(
                        f"  [progress] {linhas_processadas:>12,} linhas  "
                        f"{minutos_emitidos:>6} min  "
                        f"{rate:>8.0f} lin/s  "
                        f"ts={ts.isoformat()}"
                    )

            # Flush ultimo minuto.
            flush_minuto()
        finally:
            f_last.close()
            f_bid.close()
            f_ask.close()

    elapsed = (datetime.now(timezone.utc) - inicio_real).total_seconds()
    print(f"\n[done] {linhas_processadas:,} linhas processadas, "
          f"{minutos_emitidos} minutos emitidos em {elapsed:.1f}s.")
    print(f"  output: {saida} ({saida.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
