"""
mag6_erp.py — daily Big Tech 6 Equity Risk Premium ETL.

For each of the MAG6 tickers (AAPL, MSFT, GOOGL, AMZN, META, NVDA):

1. Build TTM EPS series from yfinance quarterly earnings.
2. Cross with adjusted close to compute pe_ttm and earning_yield each day.
3. Pull US Treasury 5Y (^FVX) daily series.
4. Apply per-ticker hardcoded credit spread to get bond_yield.
5. Compute ERP = earning_yield - bond_yield.
6. Upsert into mag6_erp_history.

The current snapshot also pulls fwd_pe_fy1 from the multiples table for the
"current" table in the UI. Historical series stays TTM-based for consistency
(yfinance doesn't expose historical forward consensus).

Usage:
    python -m backend.etl.mag6_erp                  # full backfill + today
    python -m backend.etl.mag6_erp --today          # only today's snapshot
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

# Big Tech 6 — MAG7 ex-TSLA (Tesla's P/E doesn't fit the ERP framing)
MAG6 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]

# Credit spreads vs US Treasury 5Y (basis points), hardcoded by rating.
# Source: Moody's / S&P long-term ratings as of 2026-Q1, IG bond market spreads.
# Review quarterly — main movers are AMZN/META (capex-driven leverage) and NVDA (rating migration).
SPREADS_BPS = {
    "AAPL":  35,   # Aaa/AA+ — Apple has $160B cash but $100B debt → high-quality IG
    "MSFT":  30,   # Aaa/AAA — only true AAA in the group, tightest spread
    "GOOGL": 40,   # Aa1/AA+ — strong but issues less debt, small liquidity premium
    "AMZN":  55,   # A1/AA  — datacenter capex levered, one notch lower
    "META":  60,   # A1/AA- — AI capex + buybacks raised leverage
    "NVDA":  65,   # A1/A+  — newest IG issuer, fewer outstanding bonds, more spread
}

TREASURY_5Y_TICKER = "^FVX"  # CBOE 5-Year Treasury Note Yield


def _build_ttm_eps_series(ticker: str) -> pd.Series:
    """Returns a Series indexed by report_date with rolling 4-quarter trailing EPS."""
    try:
        tk = yf.Ticker(ticker)
        # quarterly_income_stmt returns recent quarters (typically 5-8 columns)
        df = tk.quarterly_income_stmt
        if df is None or df.empty or "Diluted EPS" not in df.index:
            return pd.Series(dtype=float)
        eps_q = df.loc["Diluted EPS"].dropna()
        eps_q.index = pd.to_datetime(eps_q.index)
        eps_q = eps_q.sort_index()
        # Rolling sum of 4 quarters = TTM
        eps_ttm = eps_q.rolling(window=4, min_periods=4).sum()
        eps_ttm = eps_ttm.dropna()
        return eps_ttm
    except Exception as e:
        print(f"  [warn] {ticker} EPS fetch failed: {e.__class__.__name__}")
        return pd.Series(dtype=float)


def _get_treasury_5y_series(start: str, end: str) -> pd.Series:
    """Returns Treasury 5Y yield (in pct) indexed by date."""
    try:
        df = yf.Ticker(TREASURY_5Y_TICKER).history(start=start, end=end, auto_adjust=False)
        if df.empty:
            return pd.Series(dtype=float)
        # ^FVX is quoted in percent already (e.g. 4.40 = 4.40%)
        s = df["Close"].copy()
        s.index = s.index.tz_localize(None) if s.index.tz else s.index
        s.index = pd.to_datetime(s.index).date
        return s
    except Exception as e:
        print(f"  [warn] treasury fetch failed: {e.__class__.__name__}")
        return pd.Series(dtype=float)


def _get_price_series(cur, ticker: str) -> pd.Series:
    """Returns adj_close series from local prices table."""
    rows = cur.execute(
        "SELECT date, adj_close FROM prices WHERE ticker=? ORDER BY date ASC",
        (ticker,),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(
        [r[1] for r in rows],
        index=pd.to_datetime([r[0] for r in rows]).date,
        dtype=float,
    )
    return s


def _fwd_pe_fy1(cur, ticker: str) -> float | None:
    """Most recent fwd_pe_fy1 from multiples table."""
    row = cur.execute(
        "SELECT fwd_pe_fy1 FROM multiples WHERE ticker=? ORDER BY as_of_date DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return row[0] if row and row[0] else None


def process_ticker(cur, ticker: str, treasury_series: pd.Series) -> int:
    """Backfill TTM-based ERP series for one ticker. Returns rows upserted."""
    eps_ttm_series = _build_ttm_eps_series(ticker)
    if eps_ttm_series.empty:
        print(f"  [skip] {ticker}: no EPS TTM data")
        return 0

    price_series = _get_price_series(cur, ticker)
    if price_series.empty:
        print(f"  [skip] {ticker}: no prices in DB")
        return 0

    spread = SPREADS_BPS.get(ticker, 50)
    fwd_pe_fy1 = _fwd_pe_fy1(cur, ticker)  # snapshot, applies to last row only

    # Build daily EPS_TTM via forward-fill from quarterly report dates
    full_dates = pd.date_range(
        start=max(price_series.index.min(), eps_ttm_series.index.min().date()),
        end=price_series.index.max(),
        freq="D",
    ).date
    eps_daily = pd.Series(index=full_dates, dtype=float)
    for report_date, eps_val in eps_ttm_series.items():
        eps_daily.loc[eps_daily.index >= report_date.date()] = eps_val
    eps_daily = eps_daily.ffill().dropna()

    rows_upserted = 0
    last_date = max(eps_daily.index)
    for d in eps_daily.index:
        if d not in price_series.index:
            continue
        price = price_series.loc[d]
        eps_ttm = eps_daily.loc[d]
        if not eps_ttm or eps_ttm <= 0:
            continue
        pe_ttm = price / eps_ttm
        earning_yield = (1.0 / pe_ttm) * 100  # in percent
        treasury_5y = treasury_series.get(d)
        if treasury_5y is None or pd.isna(treasury_5y):
            continue
        bond_yield = treasury_5y + spread / 100.0
        erp = earning_yield - bond_yield

        # Only the most-recent day gets fwd_pe_fy1 attached
        fwd_pe = fwd_pe_fy1 if d == last_date else None

        cur.execute(
            """
            INSERT INTO mag6_erp_history
              (date, ticker, price, eps_ttm, pe_ttm, pe_fwd_fy1,
               earning_yield, treasury_5y, spread_bps, bond_yield, erp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, ticker) DO UPDATE SET
              price=excluded.price,
              eps_ttm=excluded.eps_ttm,
              pe_ttm=excluded.pe_ttm,
              pe_fwd_fy1=COALESCE(excluded.pe_fwd_fy1, mag6_erp_history.pe_fwd_fy1),
              earning_yield=excluded.earning_yield,
              treasury_5y=excluded.treasury_5y,
              spread_bps=excluded.spread_bps,
              bond_yield=excluded.bond_yield,
              erp=excluded.erp
            """,
            (
                d.isoformat(), ticker, float(price), float(eps_ttm), float(pe_ttm), fwd_pe,
                float(earning_yield), float(treasury_5y), spread, float(bond_yield), float(erp),
            ),
        )
        rows_upserted += 1
    return rows_upserted


def main(today_only: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=365 * 6)  # 6y window to be safe
    print(f"[mag6_erp] fetching treasury 5Y from {start_date} to {end_date}")
    treasury_series = _get_treasury_5y_series(start_date.isoformat(), end_date.isoformat())
    if treasury_series.empty:
        print("[mag6_erp] FATAL: treasury series is empty, aborting")
        conn.close()
        return
    print(f"[mag6_erp] treasury 5Y range: {treasury_series.iloc[0]:.2f}% -> {treasury_series.iloc[-1]:.2f}%  ({len(treasury_series)} days)")

    total_rows = 0
    for ticker in MAG6:
        print(f"[mag6_erp] processing {ticker} (spread={SPREADS_BPS[ticker]}bps)")
        n = process_ticker(cur, ticker, treasury_series)
        total_rows += n
        print(f"  {ticker}: {n} rows upserted")
    conn.commit()

    # Sanity sample
    print(f"[mag6_erp] total upserted: {total_rows}")
    sample = cur.execute(
        "SELECT date, ticker, ROUND(pe_ttm,1), ROUND(earning_yield,2), "
        "ROUND(bond_yield,2), ROUND(erp,2) "
        "FROM mag6_erp_history WHERE date=(SELECT MAX(date) FROM mag6_erp_history) "
        "ORDER BY ticker"
    ).fetchall()
    print("Latest snapshot:")
    print(f"  {'date':12s} {'tkr':6s} {'pe_ttm':>7s} {'e_yld':>7s} {'bond_y':>7s} {'erp':>7s}")
    for r in sample:
        print(f"  {r[0]:12s} {r[1]:6s} {r[2]:>7} {r[3]:>7} {r[4]:>7} {r[5]:>7}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true", help="reserved for future incremental mode")
    args = ap.parse_args()
    main(today_only=args.today)
