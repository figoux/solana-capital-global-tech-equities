"""
Volatilidade — RV (realized) e IV (implied) via yfinance.

RV:   annualized close-to-close, janelas 30/60/90 trading days (padrão: últimos N dias).
IV:   ATM IV at expiry ~30d / 60d / 90d, extraída da options chain.
Skew: 25d = IV(25d put) - IV(25d call) @ ~30d expiry.
      Aproximação: usa strike ~20% OTM de cada lado (delta 25 aprox).

Tickers sem options chain (ADRs, .HK, .KS, etc.) ficam só com RV.

Uso:
    python -m backend.etl.vol_yf
    python -m backend.etl.vol_yf --tickers NVDA AMZN AMD
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

TRADING_DAYS_YEAR = 252


def realized_vol_from_prices(conn: sqlite3.Connection, ticker: str) -> dict:
    """Calcula RV 30/60/90d annualized a partir da tabela prices."""
    df = pd.read_sql_query(
        "SELECT date, adj_close FROM prices WHERE ticker=? ORDER BY date",
        conn,
        params=(ticker,),
    )
    if len(df) < 90:
        return {}
    df["ret"] = np.log(df["adj_close"] / df["adj_close"].shift(1))
    out = {}
    for w in (30, 60, 90):
        s = df["ret"].tail(w).std(ddof=1)
        if pd.notna(s):
            out[f"rv_{w}d"] = float(s * math.sqrt(TRADING_DAYS_YEAR))
    return out


def implied_vol_from_chain(yahoo_ticker: str) -> dict:
    """ATM IV em ~30/60/90d + skew 25d. Silencia erros — retorna {} se sem dados."""
    try:
        tk = yf.Ticker(yahoo_ticker)
        expiries = tk.options
        if not expiries:
            return {}
        spot = (tk.fast_info.get("last_price") or tk.info.get("regularMarketPrice"))
        if not spot:
            return {}
        today = date.today()

        def pick_expiry(target_days: int) -> str | None:
            best, best_diff = None, 9999
            for e in expiries:
                try:
                    d = (datetime.strptime(e, "%Y-%m-%d").date() - today).days
                    if 7 <= d <= 400:  # filtra weeklies degeneradas e LEAPS
                        diff = abs(d - target_days)
                        if diff < best_diff:
                            best_diff, best = diff, e
                except ValueError:
                    continue
            return best

        out: dict = {}
        for w, target in ((30, 30), (60, 60), (90, 90)):
            exp = pick_expiry(target)
            if not exp:
                continue
            try:
                chain = tk.option_chain(exp)
            except Exception:
                continue
            calls, puts = chain.calls, chain.puts
            if calls.empty or puts.empty:
                continue

            # ATM IV = média das 3 strikes mais próximas do spot (calls+puts)
            calls = calls.assign(_dist=(calls["strike"] - spot).abs()).sort_values("_dist").head(3)
            puts = puts.assign(_dist=(puts["strike"] - spot).abs()).sort_values("_dist").head(3)
            ivs = pd.concat([calls["impliedVolatility"], puts["impliedVolatility"]]).dropna()
            if len(ivs):
                out[f"iv_{w}d_atm"] = float(ivs.mean())

            # Skew 25d (só no bucket 30d)
            if w == 30:
                # 25-delta put ≈ strike ~12-15% OTM (spot × 0.88); 25-delta call ≈ spot × 1.12
                put_strike_target = spot * 0.88
                call_strike_target = spot * 1.12
                puts_full = chain.puts
                calls_full = chain.calls
                pp = puts_full.iloc[(puts_full["strike"] - put_strike_target).abs().argsort()[:1]]
                cc = calls_full.iloc[(calls_full["strike"] - call_strike_target).abs().argsort()[:1]]
                if not pp.empty and not cc.empty:
                    put_iv = pp["impliedVolatility"].iloc[0]
                    call_iv = cc["impliedVolatility"].iloc[0]
                    if pd.notna(put_iv) and pd.notna(call_iv):
                        out["iv_skew_25d"] = float(put_iv - call_iv)

        return out
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", help="Subset (default: all public active)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if args.tickers:
        rows = [
            r for r in cur.execute(
                "SELECT ticker, yahoo_ticker FROM companies WHERE ticker IN ("
                + ",".join("?" * len(args.tickers))
                + ")",
                args.tickers,
            ).fetchall()
        ]
    else:
        rows = cur.execute(
            "SELECT ticker, yahoo_ticker FROM companies "
            "WHERE is_private=0 AND active=1 ORDER BY mkt_cap_rank_hint IS NULL, mkt_cap_rank_hint"
        ).fetchall()

    today = date.today().isoformat()
    ok = 0
    with_iv = 0
    errs = 0
    for ticker, yt in rows:
        try:
            row: dict = {"ticker": ticker, "as_of_date": today, "source": "yfinance", "locked": 0}
            rv = realized_vol_from_prices(conn, ticker)
            row.update(rv)
            if yt:
                iv = implied_vol_from_chain(yt)
                row.update(iv)
                if iv:
                    with_iv += 1

            cols = list(row.keys())
            placeholders = ",".join("?" * len(cols))
            updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("ticker", "as_of_date"))
            cur.execute(
                f"INSERT INTO volatility ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(ticker, as_of_date) DO UPDATE SET {updates} "
                f"WHERE COALESCE(volatility.locked,0)=0",
                list(row.values()),
            )
            ok += 1
            if ok % 20 == 0:
                print(f"  ... {ok}/{len(rows)}")
            time.sleep(0.15)
        except Exception as e:
            print(f"  [err] {ticker}: {e}")
            errs += 1

    conn.commit()

    # Report
    print(f"\n[vol_yf] ok={ok} with_iv={with_iv} errs={errs}")
    # Sample
    for t in ("NVDA", "AMZN", "AMD"):
        r = cur.execute(
            "SELECT rv_30d, rv_60d, iv_30d_atm, iv_60d_atm, iv_skew_25d "
            "FROM volatility WHERE ticker=? ORDER BY as_of_date DESC LIMIT 1",
            (t,),
        ).fetchone()
        if r:
            fmt = lambda x: f"{x*100:.1f}%" if x else "—"
            print(f"  {t:6s} RV30={fmt(r[0])} RV60={fmt(r[1])} | IV30={fmt(r[2])} IV60={fmt(r[3])} | skew25={r[4] and f'{r[4]*100:+.1f}pt'}")

    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, finished_at, status, rows_upserted, message) "
        "VALUES (?, ?, ?, 'ok', ?, ?)",
        (
            "vol_yf",
            datetime.now().isoformat(timespec="seconds"),
            datetime.now().isoformat(timespec="seconds"),
            ok,
            f"ok={ok} with_iv={with_iv} errs={errs}",
        ),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
