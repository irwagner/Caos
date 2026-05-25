"""Agrega tick.txt do NT8 em ofi_minuto.csv (streaming).

Estende o agregar_spread_tick.py existente para classificar aggressor
de cada Last (Lee-Ready algorithm) e emitir Trade Flow Imbalance (TFI)
por minuto.

Para cada minuto produz, alem das colunas de spread:

- buy_volume:    volume das operacoes classificadas como buy aggressive.
- sell_volume:   volume das operacoes classificadas como sell aggressive.
- tfi:           buy_volume - sell_volume (Trade Flow Imbalance).
- tfi_norm:      tfi / (buy_volume + sell_volume) ∈ [-1, 1].
- num_buys:      contagem de ticks classificados como buy.
- num_sells:     contagem de ticks classificados como sell.
- num_unclass:   ticks que nao foi possivel classificar (sem bid/ask correntes).

Algoritmo de classificacao (Lee-Ready 1991, simplificado):
  1. Se last_price >= ask_corrente -> buy.
  2. Se last_price <= bid_corrente -> sell.
  3. Caso contrario: tick rule (comparar com ultimo last_price visto).
     - Se subiu: buy. Se desceu: sell. Se igual: usa direcao do tick anterior.
  4. Se nao tem bid/ask correntes ainda (warmup), incrementa num_unclass.

OFI vs TFI (terminologia):
- OFI tradicional usa book depth (top of book + 2nd, 3rd levels). Nao
  temos depth no NT8 export. Usamos TFI que e o proxy mais comum quando
  so temos top of book bid/ask + Last.
- Cont-Larrard 2014 (Order Book Dynamics in Liquid Markets) mostra que
  TFI e OFI sao altamente correlacionados em mercados liquidos como ES/NQ.

Uso: python scripts/agregar_ofi_tick.py <contrato>
Ex.:  python scripts/agregar_ofi_tick.py MNQ_06-25
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, mean


def parsear_timestamp_nt8(bruto: str) -> datetime | None:
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
        frac_int = int(frac_s[:6].ljust(6, "0"))
        return datetime(ano, mes, dia, hora, minuto, seg, frac_int, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def chave_minuto(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def main(contrato: str) -> int:
    raiz = Path(r"e:\CAOS\dados\MNQ") / contrato / "tick"
    if not raiz.is_dir():
        print(f"ERRO: {raiz} nao existe.", file=sys.stderr)
        return 1

    base_nome = contrato.replace("_", " ")
    arq_last = raiz / f"{base_nome}.Last.txt"
    arq_bid = raiz / f"{base_nome}.Bid.txt"
    arq_ask = raiz / f"{base_nome}.Ask.txt"

    for arq in (arq_last, arq_bid, arq_ask):
        if not arq.is_file():
            print(f"ERRO: {arq} nao existe.", file=sys.stderr)
            return 1

    saida = raiz / "ofi_minuto.csv"
    if saida.is_file() and saida.stat().st_size > 100 * 1024:
        print(f"[skip] {saida} ja existe ({saida.stat().st_size/1e6:.1f} MB). "
              f"Remova manualmente para reprocessar.")
        return 0

    print(f"[setup] contrato={contrato}")
    print(f"  Last: {arq_last.stat().st_size / 1e9:.2f} GB")
    print(f"  Bid:  {arq_bid.stat().st_size / 1e9:.2f} GB")
    print(f"  Ask:  {arq_ask.stat().st_size / 1e9:.2f} GB")
    print(f"  saida: {saida}")

    minuto_atual: datetime | None = None
    last_prices: list[float] = []
    bid_corrente: float | None = None
    ask_corrente: float | None = None
    ultimo_last_price: float | None = None
    direcao_tick_anterior: int = 0  # +1 buy / -1 sell / 0 unknown

    # Por minuto:
    buy_volume = 0
    sell_volume = 0
    num_buys = 0
    num_sells = 0
    num_unclass = 0
    bid_values: list[float] = []
    ask_values: list[float] = []
    last_volumes_minuto: list[int] = []

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
            "bid_avg",
            "ask_avg",
            "spread_avg",
            "buy_volume",
            "sell_volume",
            "num_buys",
            "num_sells",
            "num_unclass",
            "tfi",
            "tfi_norm",
        ])

        def flush_minuto() -> None:
            nonlocal minutos_emitidos
            if minuto_atual is None:
                return
            n_last = len(last_prices)
            vol_total = sum(last_volumes_minuto)
            last_first = last_prices[0] if last_prices else None
            last_last_val = last_prices[-1] if last_prices else None
            last_high = max(last_prices) if last_prices else None
            last_low = min(last_prices) if last_prices else None
            bid_a = mean(bid_values) if bid_values else None
            ask_a = mean(ask_values) if ask_values else None
            spread_a = (ask_a - bid_a) if (bid_a is not None and ask_a is not None) else None
            tfi = buy_volume - sell_volume
            denom = buy_volume + sell_volume
            tfi_n = (tfi / denom) if denom > 0 else None

            writer.writerow([
                minuto_atual.strftime("%Y-%m-%dT%H:%M:00Z"),
                n_last,
                vol_total,
                last_first,
                last_last_val,
                last_high,
                last_low,
                bid_a,
                ask_a,
                spread_a,
                buy_volume,
                sell_volume,
                num_buys,
                num_sells,
                num_unclass,
                tfi,
                tfi_n,
            ])
            minutos_emitidos += 1

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
                cands = []
                for tag, line in (("L", cur_last), ("B", cur_bid), ("A", cur_ask)):
                    if line is None:
                        continue
                    idx = line.find(";")
                    if idx < 0:
                        continue
                    ts_s = line[:idx]
                    ts = parsear_timestamp_nt8(ts_s)
                    cands.append((tag, ts, line))

                if not cands:
                    break

                cands_validos = [c for c in cands if c[1] is not None]
                if not cands_validos:
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

                novo_minuto = chave_minuto(ts)
                if minuto_atual is None:
                    minuto_atual = novo_minuto
                elif novo_minuto > minuto_atual:
                    flush_minuto()
                    minuto_atual = novo_minuto
                    last_prices = []
                    last_volumes_minuto = []
                    bid_values = []
                    ask_values = []
                    buy_volume = 0
                    sell_volume = 0
                    num_buys = 0
                    num_sells = 0
                    num_unclass = 0

                campos = line.split(";")

                if tag == "L" and len(campos) >= 5:
                    try:
                        price = float(campos[1])
                        vol = int(campos[4])
                        last_prices.append(price)
                        last_volumes_minuto.append(vol)

                        # Lee-Ready classification.
                        if bid_corrente is None or ask_corrente is None:
                            num_unclass += 1
                            if ultimo_last_price is not None:
                                if price > ultimo_last_price:
                                    direcao_tick_anterior = 1
                                elif price < ultimo_last_price:
                                    direcao_tick_anterior = -1
                            ultimo_last_price = price
                        else:
                            classificacao = 0  # 0 = unclass
                            if price >= ask_corrente:
                                classificacao = 1
                            elif price <= bid_corrente:
                                classificacao = -1
                            else:
                                # Tick rule.
                                if ultimo_last_price is not None:
                                    if price > ultimo_last_price:
                                        classificacao = 1
                                    elif price < ultimo_last_price:
                                        classificacao = -1
                                    else:
                                        classificacao = direcao_tick_anterior
                                else:
                                    classificacao = 0

                            if classificacao == 1:
                                buy_volume += vol
                                num_buys += 1
                                direcao_tick_anterior = 1
                            elif classificacao == -1:
                                sell_volume += vol
                                num_sells += 1
                                direcao_tick_anterior = -1
                            else:
                                num_unclass += 1

                            if ultimo_last_price is not None:
                                if price > ultimo_last_price:
                                    direcao_tick_anterior = 1
                                elif price < ultimo_last_price:
                                    direcao_tick_anterior = -1
                            ultimo_last_price = price
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

            flush_minuto()
        finally:
            f_last.close()
            f_bid.close()
            f_ask.close()

    elapsed = (datetime.now(timezone.utc) - inicio_real).total_seconds()
    print(f"\n[done] {linhas_processadas:,} linhas, {minutos_emitidos} minutos "
          f"em {elapsed:.1f}s. Output: {saida.stat().st_size / 1e6:.1f} MB.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
