"""
Popula earnings_events (upcoming) com datas dos próximos earnings.

Estratégia:
  1. Finnhub earnings_calendar (rápido, eventos com EPS/Rev estimates para US) — próximas 8 semanas
  2. Fallback: tk.calendar do yfinance para não-US que não vierem no Finnhub

Uso:
    python -m backend.etl.earnings_cal                # próximas 8 semanas (default)
    python -m backend.etl.earnings_cal --weeks 12
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import finnhub
import yfinance as yf

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"


def _fiscal_period(d: date) -> str:
    """Converte data de report em rótulo 'YYYYQn' — aproximação (assume CY quarter)."""
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def _report_time(hour_code: str | None) -> str:
    if not hour_code:
        return "unknown"
    h = hour_code.lower()
    if h in ("bmo", "dmh"):  # before market open / during market
        return "bmo"
    if h in ("amc", "dmt"):  # after market close
        return "amc"
    return "unknown"


def fetch_finnhub(client, from_d: date, to_d: date) -> list[dict]:
    """Pega todos os eventos do calendar no range (US + alguns internacionais)."""
    out: list[dict] = []
    # Finnhub free tier tem rate limit; chamamos um range completo (não precisa paginar)
    try:
        cal = client.earnings_calendar(
            _from=from_d.isoformat(),
            to=to_d.isoformat(),
            symbol="",
            international=False,
        )
        out.extend(cal.get("earningsCalendar") or [])
    except Exception as e:
        print(f"[finnhub] erro no calendar: {e}", file=sys.stderr)
    return out


def fetch_yf_calendar(ticker: str, yahoo_ticker: str) -> dict | None:
    """Fallback p/ 1 ticker: tk.calendar tem 'Earnings Date'."""
    try:
        tk = yf.Ticker(yahoo_ticker)
        cal = tk.calendar
    except Exception:
        return None
    if not cal:
        return None
    # calendar é dict (yfinance >=0.2.37) com 'Earnings Date' -> list[datetime]
    ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
    if not ed:
        return None
    first = ed[0] if isinstance(ed, (list, tuple)) else ed
    try:
        d = first.date() if hasattr(first, "date") else first
    except Exception:
        return None
    return {
        "date": d.isoformat(),
        "hour": "unknown",
        "epsEstimate": cal.get("Earnings Average") if isinstance(cal, dict) else None,
        "revenueEstimate": cal.get("Revenue Average") if isinstance(cal, dict) else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=8)
    args = ap.parse_args()

    if load_dotenv:
        load_dotenv(ROOT / ".env")
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        raise SystemExit("FINNHUB_API_KEY não configurada em .env")
    client = finnhub.Client(api_key=api_key)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Universo de tickers que nos interessam
    rows = cur.execute(
        "SELECT ticker, yahoo_ticker, finnhub_ticker, currency FROM companies "
        "WHERE is_private=0 AND active=1"
    ).fetchall()
    our_by_yahoo = {y: (t, y, f, c) for (t, y, f, c) in rows if y}
    # fallback index por "canonical" ticker (US símbolo)
    our_by_ticker = {t: (t, y, f, c) for (t, y, f, c) in rows}

    from_d = date.today()
    to_d = from_d + timedelta(weeks=args.weeks)

    started = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, status) VALUES (?, ?, ?)",
        ("earnings_cal", started, "running"),
    )
    run_id = cur.lastrowid
    conn.commit()

    # 1. Finnhub batch
    print(f"[finnhub] buscando earnings calendar {from_d} → {to_d}")
    cal = fetch_finnhub(client, from_d, to_d)
    print(f"[finnhub] {len(cal)} eventos totais no range")

    # Filtra só os que estão no nosso universo (por símbolo que o Finnhub retorna)
    matched = []
    our_tickers_seen: set[str] = set()
    for ev in cal:
        sym = ev.get("symbol")
        if not sym:
            continue
        # Finnhub usa símbolo "US-style" (ex: NVDA, AAPL) p/ US, ou com sufixo pra intl
        if sym in our_by_ticker:
            t = sym
        elif sym in our_by_yahoo:
            t = our_by_yahoo[sym][0]
        else:
            continue
        matched.append((t, ev))
        our_tickers_seen.add(t)

    # Upsert cada evento matched
    n_upserts = 0
    for t, ev in matched:
        report_date = ev.get("date")
        if not report_date:
            continue
        d_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
        period = _fiscal_period(d_obj)
        cur.execute(
            """
            INSERT INTO earnings_events
              (ticker, fiscal_period, report_date, report_time, status, eps_est, rev_est, currency)
            VALUES (?, ?, ?, ?, 'upcoming', ?, ?, ?)
            ON CONFLICT(ticker, fiscal_period) DO UPDATE SET
              report_date=excluded.report_date, report_time=excluded.report_time,
              eps_est=COALESCE(excluded.eps_est, earnings_events.eps_est),
              rev_est=COALESCE(excluded.rev_est, earnings_events.rev_est),
              status=CASE WHEN earnings_events.status='reported' THEN 'reported' ELSE 'upcoming' END
            """,
            (
                t, period, report_date, _report_time(ev.get("hour")),
                ev.get("epsEstimate"), ev.get("revenueEstimate"), "USD",
            ),
        )
        n_upserts += 1
    print(f"[finnhub] {n_upserts} eventos gravados para nosso universo ({len(our_tickers_seen)} tickers únicos)")

    # 2. Fallback yfinance para os que NÃO apareceram no Finnhub
    missing = [t for t in our_by_ticker if t not in our_tickers_seen]
    print(f"\n[yf-cal] {len(missing)} tickers sem evento do Finnhub — tentando yfinance.calendar")
    yf_hits = 0
    for i, t in enumerate(missing, 1):
        rec = our_by_ticker[t]
        yahoo = rec[1]
        if not yahoo:
            continue
        info = fetch_yf_calendar(t, yahoo)
        if not info:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(0.15)
            continue
        d_obj = datetime.strptime(info["date"], "%Y-%m-%d").date()
        if d_obj < from_d or d_obj > to_d:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(0.15)
            continue
        period = _fiscal_period(d_obj)
        cur.execute(
            """
            INSERT INTO earnings_events
              (ticker, fiscal_period, report_date, report_time, status, eps_est, rev_est, currency)
            VALUES (?, ?, ?, ?, 'upcoming', ?, ?, ?)
            ON CONFLICT(ticker, fiscal_period) DO UPDATE SET
              report_date=excluded.report_date, report_time=excluded.report_time,
              eps_est=COALESCE(excluded.eps_est, earnings_events.eps_est),
              rev_est=COALESCE(excluded.rev_est, earnings_events.rev_est)
            """,
            (t, period, info["date"], info.get("hour", "unknown"),
             info.get("epsEstimate"), info.get("revenueEstimate"), None),
        )
        yf_hits += 1
        sys.stdout.write("+")
        sys.stdout.flush()
        if i % 20 == 0:
            conn.commit()
            print(f" {i}/{len(missing)}")
        time.sleep(0.15)
    print(f"\n[yf-cal] {yf_hits} eventos adicionais via yfinance.calendar")

    conn.commit()

    # Stats finais
    tot = cur.execute(
        "SELECT COUNT(*) FROM earnings_events WHERE status='upcoming' AND report_date BETWEEN ? AND ?",
        (from_d.isoformat(), to_d.isoformat()),
    ).fetchone()[0]
    by_week = cur.execute(
        """
        SELECT strftime('%Y-W%W', report_date) w, COUNT(*) c
        FROM earnings_events
        WHERE status='upcoming' AND report_date BETWEEN ? AND ?
        GROUP BY w ORDER BY w
        """,
        (from_d.isoformat(), to_d.isoformat()),
    ).fetchall()
    print(f"\n[total upcoming] {tot} eventos no range")
    for w, c in by_week:
        print(f"  {w}: {c}")

    finished = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "UPDATE etl_runs SET finished_at=?, status=?, rows_upserted=?, message=? WHERE id=?",
        (finished, "ok", n_upserts + yf_hits, f"finnhub={n_upserts} yf={yf_hits} total_upcoming={tot}", run_id),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
