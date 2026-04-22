"""
Puxa OHLCV diário via yfinance para todos os tickers com is_private=0 e active=1.
Default: 2 anos de histórico. Upsert em prices(ticker, date).

Uso:
    python -m backend.etl.prices_yf                     # todos os públicos, 2 anos
    python -m backend.etl.prices_yf --tickers NVDA,AMD   # apenas esses
    python -m backend.etl.prices_yf --period 5y          # janela customizada
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

SLEEP_BETWEEN = 0.2  # seg entre requests — Yahoo pode rate-limit


def fetch_and_upsert(cur, ticker: str, yahoo_ticker: str, period: str) -> tuple[int, str]:
    """Retorna (rows, status_message)."""
    try:
        tk = yf.Ticker(yahoo_ticker)
        hist = tk.history(period=period, auto_adjust=False, actions=False)
    except Exception as e:
        return 0, f"error: {e.__class__.__name__}: {e}"

    if hist is None or hist.empty:
        return 0, "empty"

    rows = 0
    for idx, r in hist.iterrows():
        date_str = idx.strftime("%Y-%m-%d")
        cur.execute(
            """
            INSERT INTO prices (ticker, date, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
              open=excluded.open, high=excluded.high, low=excluded.low,
              close=excluded.close, adj_close=excluded.adj_close, volume=excluded.volume
            """,
            (
                ticker,
                date_str,
                float(r["Open"]) if r["Open"] == r["Open"] else None,
                float(r["High"]) if r["High"] == r["High"] else None,
                float(r["Low"]) if r["Low"] == r["Low"] else None,
                float(r["Close"]) if r["Close"] == r["Close"] else None,
                float(r.get("Adj Close", r["Close"])) if r["Close"] == r["Close"] else None,
                int(r["Volume"]) if r["Volume"] == r["Volume"] else None,
            ),
        )
        rows += 1
    return rows, "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="", help="CSV de tickers (ex: NVDA,AMD)")
    ap.add_argument("--period", default="2y", help="yfinance period: 1y,2y,5y,max")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if args.tickers.strip():
        wanted = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        placeholders = ",".join("?" * len(wanted))
        query = (
            f"SELECT ticker, yahoo_ticker FROM companies "
            f"WHERE is_private=0 AND active=1 AND ticker IN ({placeholders})"
        )
        rows_sel = cur.execute(query, wanted).fetchall()
    else:
        rows_sel = cur.execute(
            "SELECT ticker, yahoo_ticker FROM companies "
            "WHERE is_private=0 AND active=1 AND yahoo_ticker IS NOT NULL "
            "ORDER BY mkt_cap_rank_hint IS NULL, mkt_cap_rank_hint"
        ).fetchall()

    if not rows_sel:
        print("Nada a processar. Rode universe.py primeiro?")
        return

    started = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, status) VALUES (?, ?, ?)",
        ("prices_yf", started, "running"),
    )
    run_id = cur.lastrowid
    conn.commit()

    total_rows = 0
    n_ok = n_empty = n_err = 0
    errors: list[str] = []

    print(f"[prices] período={args.period} | {len(rows_sel)} tickers")
    for i, (ticker, yahoo) in enumerate(rows_sel, 1):
        n, msg = fetch_and_upsert(cur, ticker, yahoo, args.period)
        total_rows += n
        if msg == "ok":
            n_ok += 1
            status_char = "."
        elif msg == "empty":
            n_empty += 1
            status_char = "_"
            errors.append(f"{ticker} ({yahoo}): empty")
        else:
            n_err += 1
            status_char = "X"
            errors.append(f"{ticker} ({yahoo}): {msg}")

        sys.stdout.write(status_char)
        if i % 10 == 0 or i == len(rows_sel):
            sys.stdout.write(f" {i}/{len(rows_sel)}\n")
        sys.stdout.flush()

        if i % 20 == 0:
            conn.commit()
        time.sleep(SLEEP_BETWEEN)

    conn.commit()

    finished = datetime.utcnow().isoformat(timespec="seconds")
    status = "ok" if n_err == 0 else ("partial" if n_ok > 0 else "failed")
    msg_final = f"ok={n_ok} empty={n_empty} err={n_err}"
    cur.execute(
        "UPDATE etl_runs SET finished_at=?, status=?, rows_upserted=?, message=? WHERE id=?",
        (finished, status, total_rows, msg_final, run_id),
    )
    conn.commit()
    conn.close()

    print(f"\n[prices] done: {msg_final} | {total_rows} rows upsertados")
    if errors:
        print("\nPrimeiros problemas (até 15):")
        for e in errors[:15]:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
