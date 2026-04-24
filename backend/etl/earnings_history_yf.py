"""
earnings_history_yf.py - Calcula reacao dia-apos release dos ultimos N trimestres.

Para cada ticker publico ativo:
  1. Pega datas historicas via tk.get_earnings_dates() (yfinance)
  2. Para cada data passada (limit=6 trimestres), consulta tabela prices local
  3. Calcula reacao baseada em report_time (bmo/amc/unknown):
       - bmo: reaction = (close mesmo dia) / (close dia anterior) - 1
       - amc: reaction = (close dia seguinte) / (close mesmo dia) - 1
       - unknown: reaction = (close dia seguinte) / (close dia anterior) - 1  (cobre ambos casos)
  4. Upsert em earnings_history

Uso:
    python -m backend.etl.earnings_history_yf                    # todos os publicos
    python -m backend.etl.earnings_history_yf --tickers NVDA,AMD # so esses
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

SLEEP_BETWEEN = 0.25
N_QUARTERS = 6  # quantos trimestres historicos pegar por ticker


def _fiscal_period(date_str: str) -> str:
    """YYYY-MM-DD -> 'YYYYQn'. Mapeia mes -> quarter calendario (aproximacao)."""
    y, m, _ = date_str.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}Q{q}"


def _price_on_or_before(cur, ticker: str, target_date: str) -> tuple[str, float] | None:
    """Retorna (date, close) do ultimo dia de trade em ou antes de target_date."""
    row = cur.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date <= ? ORDER BY date DESC LIMIT 1",
        (ticker, target_date),
    ).fetchone()
    return (row[0], row[1]) if row else None


def _price_after(cur, ticker: str, target_date: str) -> tuple[str, float] | None:
    """Retorna (date, close) do primeiro dia de trade estritamente apos target_date."""
    row = cur.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date > ? ORDER BY date ASC LIMIT 1",
        (ticker, target_date),
    ).fetchone()
    return (row[0], row[1]) if row else None


def _price_on(cur, ticker: str, target_date: str) -> tuple[str, float] | None:
    """Retorna (date, close) do proprio target_date se existir, senao None."""
    row = cur.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date=? LIMIT 1",
        (ticker, target_date),
    ).fetchone()
    return (row[0], row[1]) if row else None


def _get_report_time(cur, ticker: str, fiscal_period: str) -> str:
    """Pega report_time do earnings_events se disponivel, senao 'unknown'."""
    row = cur.execute(
        "SELECT report_time FROM earnings_events WHERE ticker=? AND fiscal_period=?",
        (ticker, fiscal_period),
    ).fetchone()
    return row[0] if row and row[0] else "unknown"


def process_ticker(cur, ticker: str, yahoo_ticker: str, debug: bool = False) -> tuple[int, str]:
    """Retorna (rows_upsertadas, status)."""
    try:
        tk = yf.Ticker(yahoo_ticker)
        df = tk.get_earnings_dates(limit=N_QUARTERS * 2)  # pega mais, filtra passados
    except Exception as e:
        if debug:
            import traceback
            traceback.print_exc()
        return 0, f"error: {e.__class__.__name__}: {str(e)[:150]}"

    if df is None or df.empty:
        return 0, "no earnings dates"

    # Filtra datas passadas (tz-aware -> converte pra date local)
    import pandas as pd
    now = pd.Timestamp.now(tz=df.index.tz if hasattr(df.index, "tz") else None)

    past_dates = [idx for idx in df.index if idx < now][:N_QUARTERS]
    if not past_dates:
        return 0, "no past dates"

    rows_upserted = 0
    for idx in past_dates:
        report_date = idx.strftime("%Y-%m-%d")
        period = _fiscal_period(report_date)
        report_time = _get_report_time(cur, ticker, period)

        # Escolhe close_before e close_after baseado em report_time
        if report_time == "bmo":
            # Report antes do open: reacao = close mesmo dia vs close dia anterior
            before = _price_on_or_before(cur, ticker, _prev_day(report_date))
            after = _price_on(cur, ticker, report_date) or _price_after(cur, ticker, _prev_day(report_date))
        elif report_time == "amc":
            # Report apos o close: reacao = close dia seguinte vs close mesmo dia
            before = _price_on(cur, ticker, report_date) or _price_on_or_before(cur, ticker, report_date)
            after = _price_after(cur, ticker, report_date)
        else:
            # Unknown: reacao = close dia seguinte vs close dia anterior (cobre ambos)
            before = _price_on_or_before(cur, ticker, _prev_day(report_date))
            after = _price_after(cur, ticker, report_date)

        if not before or not after:
            continue

        close_before = before[1]
        close_after = after[1]
        reaction = (close_after / close_before - 1) * 100 if close_before else None

        cur.execute(
            """
            INSERT INTO earnings_history
              (ticker, fiscal_period, report_date, close_before, close_after, reaction_pct, report_time, updated_at)
            VALUES (?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticker, fiscal_period) DO UPDATE SET
              report_date=excluded.report_date,
              close_before=excluded.close_before,
              close_after=excluded.close_after,
              reaction_pct=excluded.reaction_pct,
              report_time=excluded.report_time,
              updated_at=CURRENT_TIMESTAMP
            """,
            (ticker, period, report_date, close_before, close_after, reaction, report_time),
        )
        rows_upserted += 1

    return rows_upserted, "ok"


def _prev_day(date_str: str) -> str:
    from datetime import date, timedelta
    y, m, d = map(int, date_str.split("-"))
    return (date(y, m, d) - timedelta(days=1)).isoformat()


def main(tickers: list[str] | None = None, debug: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    query = "SELECT ticker, yahoo_ticker FROM companies WHERE is_private=0 AND active=1 AND yahoo_ticker IS NOT NULL"
    params: tuple = ()
    if tickers:
        placeholders = ",".join("?" * len(tickers))
        query += f" AND ticker IN ({placeholders})"
        params = tuple(t.upper() for t in tickers)

    rows = cur.execute(query, params).fetchall()
    n_total = len(rows)
    print(f"[earnings_history] {n_total} tickers")

    ok = errs = no_data = 0
    rows_total = 0
    error_samples: list[str] = []
    for i, (tk, yt) in enumerate(rows, 1):
        n, status = process_ticker(cur, tk, yt, debug=debug)
        rows_total += n
        if status == "ok":
            ok += 1
        elif "no " in status:
            no_data += 1
        else:
            errs += 1
            if len(error_samples) < 3:
                error_samples.append(f"{tk}: {status}")
        if i % 20 == 0:
            print(f"  ... {i}/{n_total}")
            conn.commit()
        time.sleep(SLEEP_BETWEEN)

    if error_samples:
        print("First errors:")
        for s in error_samples:
            print(f"  {s}")

    conn.commit()
    print(f"[earnings_history] ok={ok} no_data={no_data} errs={errs} | {rows_total} rows upserted")

    # Sanity: amostra
    sample = cur.execute(
        "SELECT ticker, fiscal_period, report_date, reaction_pct FROM earnings_history "
        "WHERE ticker IN ('NVDA','AMZN','MSFT','AAPL') ORDER BY ticker, report_date DESC LIMIT 20"
    ).fetchall()
    if sample:
        print("Sample reactions:")
        for t, p, d, r in sample:
            print(f"  {t:8s} {p}  {d}  {r:+.1f}%" if r is not None else f"  {t:8s} {p}  {d}  n/a")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default=None, help="csv de tickers")
    ap.add_argument("--debug", action="store_true", help="print full traceback")
    args = ap.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    main(tickers, debug=args.debug)
