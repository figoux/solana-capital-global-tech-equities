"""
hynix_premium.py - Standalone Hynix ADR premium analyzer.

NOT part of the dashboard. Runs locally, prints to terminal, saves CSV.

For each fetched date, computes:
    local_in_eur = local_price_KRW / fx_per_eur
    premium_pct  = (adr_price_eur / local_in_eur - 1) * 100

Then reports current value + 1Y and 5Y rolling-mean snapshots, plus min/max,
and saves the full daily series to logs/hynix_premium.csv for plotting in Excel.

Usage:
    python scripts/hynix_premium.py
    python scripts/hynix_premium.py --adr HY9H.DE     # try XETRA listing
    python scripts/hynix_premium.py --adr HXSCY       # OTC US, USD-denominated
    python scripts/hynix_premium.py --years 3         # shorter window
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"


def _fetch(ticker: str, start: str, end: str) -> pd.Series:
    try:
        df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return pd.Series(dtype=float)
        s = df["Close"].copy()
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        s.index = pd.to_datetime(s.index).date
        s = s[~pd.Series(s.index).duplicated(keep="last").values]
        return s.astype(float).dropna()
    except Exception as e:
        print(f"  [warn] {ticker}: {e.__class__.__name__}: {e}")
        return pd.Series(dtype=float)


def main(adr_ticker: str, years: int, adr_ccy: str, fx_ticker: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    local_ticker = "000660.KS"
    ratio = 1.0

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=365 * years + 30)

    print(f"\n=== Hynix ADR Premium ===")
    print(f"ADR:    {adr_ticker:12s} ({adr_ccy})")
    print(f"Local:  {local_ticker:12s} (KRW)")
    print(f"FX:     {fx_ticker:12s} (units {adr_ccy}-per-KRW or KRW-per-{adr_ccy})")
    print(f"Ratio:  {ratio} ADR : 1 ord share")
    print(f"Window: {years}y ({start} -> {end})\n")

    print("Fetching series...")
    adr_s = _fetch(adr_ticker, start.isoformat(), end.isoformat())
    print(f"  ADR   {adr_ticker:12s} {len(adr_s):5d} days")
    local_s = _fetch(local_ticker, start.isoformat(), end.isoformat())
    print(f"  local {local_ticker:12s} {len(local_s):5d} days")
    fx_s = _fetch(fx_ticker, start.isoformat(), end.isoformat())
    print(f"  fx    {fx_ticker:12s} {len(fx_s):5d} days")

    if adr_s.empty:
        print(f"\n[abort] ADR ticker '{adr_ticker}' returned no data. Try a different ticker:")
        print("  python scripts/hynix_premium.py --adr HY9H.DE")
        print("  python scripts/hynix_premium.py --adr HY9H.BE")
        print("  python scripts/hynix_premium.py --adr HXSCY  --adr-ccy USD  --fx USDKRW=X")
        sys.exit(1)
    if local_s.empty or fx_s.empty:
        print("\n[abort] local or fx returned empty")
        sys.exit(1)

    common = sorted(set(adr_s.index) & set(local_s.index) & set(fx_s.index))
    if len(common) < 30:
        print(f"\n[abort] only {len(common)} common dates")
        sys.exit(1)
    print(f"\nCommon dates: {len(common)} ({common[0]} -> {common[-1]})\n")

    # Determine FX direction: KRW-per-ADR-ccy vs ADR-ccy-per-KRW
    # yfinance "EURKRW=X" returns KRW per 1 EUR. "USDKRW=X" same. So fx_value is large (~1400).
    # If user passes "KRWEUR=X" or "KRWUSD=X", it returns small (~0.00067).
    # Heuristic: if median fx > 10, assume KRW-per-ADR-ccy. Otherwise invert.
    median_fx = fx_s.median()
    direction = "KRW-per-ADR-ccy" if median_fx > 10 else "ADR-ccy-per-KRW"
    print(f"FX direction detected: {direction}  (median value: {median_fx:.4f})\n")

    # Build series
    records = []
    for d in common:
        local_krw = local_s.loc[d]
        adr_px = adr_s.loc[d]
        fx = fx_s.loc[d]
        if fx <= 0 or local_krw <= 0 or adr_px <= 0:
            continue
        if direction == "KRW-per-ADR-ccy":
            local_in_adr = (local_krw / fx) / ratio
        else:
            local_in_adr = (local_krw * fx) / ratio
        if local_in_adr <= 0:
            continue
        premium = (adr_px / local_in_adr - 1.0) * 100.0
        records.append({
            "date": d.isoformat(),
            "local_krw": local_krw,
            "adr_price": adr_px,
            "fx": fx,
            "local_in_adr": local_in_adr,
            "premium_pct": premium,
        })

    if not records:
        print("[abort] no valid records computed")
        sys.exit(1)

    df = pd.DataFrame(records)
    df["rolling_1y"] = df["premium_pct"].rolling(window=252, min_periods=60).mean()
    df["rolling_5y"] = df["premium_pct"].rolling(window=1260, min_periods=252).mean()

    last = df.iloc[-1]
    avg_1y = df["rolling_1y"].iloc[-1]
    avg_5y = df["rolling_5y"].iloc[-1]

    print(f"=== Components (today, {last['date']}) ===")
    print(f"  ADR  {adr_ticker} ({adr_ccy}):   {last['adr_price']:>12,.2f}")
    print(f"  Local 000660.KS (KRW):  {last['local_krw']:>12,.0f}")
    print(f"  FX {fx_ticker}:         {last['fx']:>12,.4f}")
    print(f"  Local in {adr_ccy}:           {last['local_in_adr']:>12,.2f}")
    print(f"  Ratio:                  {ratio:>12,.1f} : 1")
    print(f"  -> PREMIUM:             {last['premium_pct']:>+11.3f}%\n")

    print(f"=== Statistics ===")
    print(f"  Current premium:         {last['premium_pct']:>+11.3f}%")
    print(f"  1Y rolling average:      {avg_1y:>+11.3f}%   (current is {(last['premium_pct']-avg_1y)*100:+.0f}bp vs 1Y)")
    print(f"  5Y rolling average:      {avg_5y:>+11.3f}%   (current is {(last['premium_pct']-avg_5y)*100:+.0f}bp vs 5Y)")
    print(f"  Min over period:         {df['premium_pct'].min():>+11.3f}%   ({df.loc[df['premium_pct'].idxmin(), 'date']})")
    print(f"  Max over period:         {df['premium_pct'].max():>+11.3f}%   ({df.loc[df['premium_pct'].idxmax(), 'date']})")
    print(f"  Median (full period):    {df['premium_pct'].median():>+11.3f}%")
    print(f"  History range:           {df['date'].iloc[0]} -> {df['date'].iloc[-1]} ({len(df)} days)\n")

    # Histogram (10 buckets across observed range)
    print(f"=== Distribution (full history) ===")
    lo, hi = df["premium_pct"].min(), df["premium_pct"].max()
    n_buckets = 10
    width = (hi - lo) / n_buckets
    for i in range(n_buckets):
        bucket_lo = lo + i * width
        bucket_hi = lo + (i + 1) * width
        count = df[(df["premium_pct"] >= bucket_lo) & (df["premium_pct"] < bucket_hi)].shape[0]
        if i == n_buckets - 1:
            count = df[(df["premium_pct"] >= bucket_lo) & (df["premium_pct"] <= bucket_hi)].shape[0]
        bar_len = int(count / max(1, df.shape[0]) * 60)
        bar = "*" * bar_len
        marker = "  <- CURRENT" if bucket_lo <= last['premium_pct'] <= bucket_hi else ""
        print(f"  [{bucket_lo:+6.2f}% .. {bucket_hi:+6.2f}%]  {count:4d}  {bar}{marker}")
    print()

    out_csv = LOG_DIR / "hynix_premium.csv"
    df.to_csv(out_csv, index=False, float_format="%.4f")
    print(f"=== Saved: {out_csv} ({len(df)} rows) ===")
    print(f"Columns: date, local_krw, adr_price, fx, local_in_adr, premium_pct, rolling_1y, rolling_5y\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--adr", default="HY9H.F", help="ADR ticker on yfinance (try HY9H.F / HY9H.DE / HY9H.BE / HXSCY)")
    ap.add_argument("--adr-ccy", default="EUR", help="ADR currency (default EUR)")
    ap.add_argument("--fx", default="EURKRW=X", help="FX ticker (default EURKRW=X)")
    ap.add_argument("--years", type=int, default=5, help="years of history to fetch")
    args = ap.parse_args()
    main(adr_ticker=args.adr, years=args.years, adr_ccy=args.adr_ccy, fx_ticker=args.fx)
