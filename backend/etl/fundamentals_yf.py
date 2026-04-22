"""
Puxa fundamentals + consensus estimates via yfinance.

Popula duas tabelas num único run:
  1. multiples   -> snapshot diário de mkt cap, fwd P/E, EPS/rev growth, PEG, div yield
  2. estimates   -> consensus EPS/revenue por trimestre e por FY (source='yfinance')

Uso:
    python -m backend.etl.fundamentals_yf                    # todos os públicos ativos
    python -m backend.etl.fundamentals_yf --tickers NVDA,AMD  # apenas esses
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

SLEEP_BETWEEN = 0.25  # Yahoo rate-limit


def _f(x):
    """Safe float coercion (NaN/None -> None)."""
    if x is None:
        return None
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _i(x):
    try:
        if x is None:
            return None
        i = int(x)
        return i
    except (TypeError, ValueError):
        return None


def _fx_to_usd(ticker: yf.Ticker, currency: str | None) -> float:
    """Retorna multiplicador FX currency->USD usando yfinance. USD=1."""
    if not currency or currency.upper() == "USD":
        return 1.0
    pair = f"{currency.upper()}USD=X"
    try:
        hist = yf.Ticker(pair).history(period="5d", auto_adjust=False)
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 1.0  # fallback: sem conversão (flag em notes seria bom no futuro)


def _period_label(period_key: str, fye_month_num: int | None = None) -> tuple[str, str] | None:
    """
    yfinance usa strings: '0q','+1q','0y','+1y','-1y','+5y'.
    Convertemos p/ fiscal_period + period_type:
      '0q'  -> ('CURR_Q','quarter')   # current quarter
      '+1q' -> ('NEXT_Q','quarter')
      '0y'  -> ('FY1','annual')       # current FY
      '+1y' -> ('FY2','annual')
      '-1y' -> ('FY0','annual')       # last reported FY
    Retornamos rótulos relativos — dashboard mapeia para ano fiscal quando precisar.
    """
    mapping = {
        "0q":  ("CURR_Q", "quarter"),
        "+1q": ("NEXT_Q", "quarter"),
        "0y":  ("FY1", "annual"),
        "+1y": ("FY2", "annual"),
        "-1y": ("FY0", "annual"),
        "+5y": ("FY_LT5Y", "annual"),
        "-5y": ("FY_PAST5Y", "annual"),
    }
    return mapping.get(period_key)


def process_ticker(cur, ticker: str, yahoo_ticker: str, reporting_ccy: str | None) -> dict:
    """
    Retorna dict com contadores: {'multiples':1/0, 'estimates':N, 'note':str}
    """
    out = {"multiples": 0, "estimates": 0, "note": ""}
    try:
        tk = yf.Ticker(yahoo_ticker)
        info = tk.info or {}
    except Exception as e:
        out["note"] = f"info fail: {e.__class__.__name__}"
        return out

    as_of = date.today().isoformat()
    ccy = (info.get("currency") or reporting_ccy or "USD").upper()

    # ----- 1. multiples (normalizado p/ USD onde possível) -----
    mkt_cap_raw = _f(info.get("marketCap"))
    ev_raw = _f(info.get("enterpriseValue"))
    fx = 1.0
    if mkt_cap_raw and ccy != "USD":
        fx = _fx_to_usd(tk, ccy)

    mkt_cap_usd = mkt_cap_raw * fx if mkt_cap_raw else None
    ev_usd = ev_raw * fx if ev_raw else None

    fwd_pe = _f(info.get("forwardPE"))
    pe_ttm = _f(info.get("trailingPE"))
    ps_ntm = _f(info.get("priceToSalesTrailing12Months"))  # yfinance chama TTM aqui, mas é o que dá
    div_yield = _f(info.get("dividendYield"))
    # PEG: yfinance expõe trailingPegRatio (mais estável que "pegRatio")
    peg = _f(info.get("trailingPegRatio")) or _f(info.get("pegRatio"))

    # ----- 2. estimates via yfinance (novos properties) -----
    eps_by_period: dict[str, dict] = {}
    rev_by_period: dict[str, dict] = {}
    growth_by_period: dict[str, dict] = {}

    try:
        ee = tk.earnings_estimate
        if ee is not None and not ee.empty:
            for idx, row in ee.iterrows():
                lbl = _period_label(str(idx))
                if not lbl:
                    continue
                eps_by_period[lbl[0]] = {
                    "type": lbl[1],
                    "mean": _f(row.get("avg")),
                    "low":  _f(row.get("low")),
                    "high": _f(row.get("high")),
                    "count": _i(row.get("numberOfAnalysts")),
                }
    except Exception as e:
        out["note"] += f" eps_est: {e.__class__.__name__};"

    try:
        re = tk.revenue_estimate
        if re is not None and not re.empty:
            for idx, row in re.iterrows():
                lbl = _period_label(str(idx))
                if not lbl:
                    continue
                rev_by_period[lbl[0]] = {
                    "type": lbl[1],
                    "mean": _f(row.get("avg")),
                    "low":  _f(row.get("low")),
                    "high": _f(row.get("high")),
                    "count": _i(row.get("numberOfAnalysts")),
                }
    except Exception as e:
        out["note"] += f" rev_est: {e.__class__.__name__};"

    try:
        ge = tk.growth_estimates
        if ge is not None and not ge.empty:
            for idx, row in ge.iterrows():
                lbl = _period_label(str(idx))
                if not lbl:
                    continue
                growth_by_period[lbl[0]] = _f(row.get("stockTrend"))
    except Exception:
        pass

    # derive growth rates p/ multiples a partir de eps_by_period e info
    trailing_eps = _f(info.get("trailingEps"))
    fy1_eps = (eps_by_period.get("FY1") or {}).get("mean")
    fy2_eps = (eps_by_period.get("FY2") or {}).get("mean")

    def _growth(new, old):
        if new is None or old is None or old == 0:
            return None
        return (new - old) / abs(old)

    eps_growth_fy1 = _growth(fy1_eps, trailing_eps)
    eps_growth_fy2 = _growth(fy2_eps, fy1_eps)
    eps_growth_ntm = growth_by_period.get("0y")  # aprox

    # Revenue growth similar — usamos totalRevenue se vier
    rev_ttm = _f(info.get("totalRevenue"))
    fy1_rev = (rev_by_period.get("FY1") or {}).get("mean")
    fy2_rev = (rev_by_period.get("FY2") or {}).get("mean")
    rev_growth_fy1 = _growth(fy1_rev, rev_ttm)
    rev_growth_fy2 = _growth(fy2_rev, fy1_rev)

    # fwd P/E FY1/FY2: price / eps_fyN
    current_price = _f(info.get("currentPrice")) or _f(info.get("regularMarketPrice"))
    fwd_pe_fy1 = (current_price / fy1_eps) if (current_price and fy1_eps and fy1_eps > 0) else None
    fwd_pe_fy2 = (current_price / fy2_eps) if (current_price and fy2_eps and fy2_eps > 0) else None

    cur.execute(
        """
        INSERT INTO multiples
          (ticker, as_of_date, mkt_cap_usd, ev_usd, fwd_pe_ntm, fwd_pe_fy1, fwd_pe_fy2,
           pe_ttm, ev_ebitda_ntm, ps_ntm, eps_growth_ntm, eps_growth_fy1, eps_growth_fy2,
           rev_growth_ntm, rev_growth_fy1, rev_growth_fy2, peg_ntm, dividend_yield)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker, as_of_date) DO UPDATE SET
          mkt_cap_usd=excluded.mkt_cap_usd, ev_usd=excluded.ev_usd,
          fwd_pe_ntm=excluded.fwd_pe_ntm, fwd_pe_fy1=excluded.fwd_pe_fy1, fwd_pe_fy2=excluded.fwd_pe_fy2,
          pe_ttm=excluded.pe_ttm, ps_ntm=excluded.ps_ntm,
          eps_growth_ntm=excluded.eps_growth_ntm, eps_growth_fy1=excluded.eps_growth_fy1, eps_growth_fy2=excluded.eps_growth_fy2,
          rev_growth_ntm=excluded.rev_growth_ntm, rev_growth_fy1=excluded.rev_growth_fy1, rev_growth_fy2=excluded.rev_growth_fy2,
          peg_ntm=excluded.peg_ntm, dividend_yield=excluded.dividend_yield
        """,
        (
            ticker, as_of, mkt_cap_usd, ev_usd, fwd_pe, fwd_pe_fy1, fwd_pe_fy2,
            pe_ttm, None, ps_ntm, eps_growth_ntm, eps_growth_fy1, eps_growth_fy2,
            None, rev_growth_fy1, rev_growth_fy2, peg, div_yield,
        ),
    )
    out["multiples"] = 1

    # ----- 3. upsert estimates (source='yfinance') -----
    all_periods = set(eps_by_period) | set(rev_by_period)
    n_est = 0
    for p in all_periods:
        eps = eps_by_period.get(p, {})
        rev = rev_by_period.get(p, {})
        period_type = eps.get("type") or rev.get("type") or "annual"
        cur.execute(
            """
            INSERT INTO estimates
              (ticker, fiscal_period, period_type, eps_mean, eps_low, eps_high, eps_count,
               revenue_mean, revenue_low, revenue_high, revenue_count, ebitda_mean,
               currency, as_of_date, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, fiscal_period, as_of_date, source) DO UPDATE SET
              eps_mean=excluded.eps_mean, eps_low=excluded.eps_low, eps_high=excluded.eps_high,
              eps_count=excluded.eps_count,
              revenue_mean=excluded.revenue_mean, revenue_low=excluded.revenue_low,
              revenue_high=excluded.revenue_high, revenue_count=excluded.revenue_count
            """,
            (
                ticker, p, period_type,
                eps.get("mean"), eps.get("low"), eps.get("high"), eps.get("count"),
                rev.get("mean"), rev.get("low"), rev.get("high"), rev.get("count"),
                None, ccy, as_of, "yfinance",
            ),
        )
        n_est += 1
    out["estimates"] = n_est

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="", help="CSV de tickers (ex: NVDA,AMD)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if args.tickers.strip():
        wanted = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        placeholders = ",".join("?" * len(wanted))
        rows = cur.execute(
            f"SELECT ticker, yahoo_ticker, currency FROM companies "
            f"WHERE is_private=0 AND active=1 AND ticker IN ({placeholders})",
            wanted,
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT ticker, yahoo_ticker, currency FROM companies "
            "WHERE is_private=0 AND active=1 AND yahoo_ticker IS NOT NULL "
            "ORDER BY mkt_cap_rank_hint IS NULL, mkt_cap_rank_hint"
        ).fetchall()

    if not rows:
        print("Nada a processar.")
        return

    started = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, status) VALUES (?, ?, ?)",
        ("fundamentals_yf", started, "running"),
    )
    run_id = cur.lastrowid
    conn.commit()

    n_ok = n_err = 0
    tot_est = 0
    errors: list[str] = []
    print(f"[fundamentals] {len(rows)} tickers")
    for i, (ticker, yahoo, ccy) in enumerate(rows, 1):
        res = process_ticker(cur, ticker, yahoo, ccy)
        if res["multiples"] == 1:
            n_ok += 1
            tot_est += res["estimates"]
            sys.stdout.write(".")
        else:
            n_err += 1
            sys.stdout.write("X")
            errors.append(f"{ticker}: {res['note']}")

        if i % 10 == 0 or i == len(rows):
            sys.stdout.write(f" {i}/{len(rows)}\n")
        sys.stdout.flush()

        if i % 20 == 0:
            conn.commit()
        time.sleep(SLEEP_BETWEEN)

    conn.commit()

    finished = datetime.now().isoformat(timespec="seconds")
    status = "ok" if n_err == 0 else ("partial" if n_ok else "failed")
    msg = f"mult_ok={n_ok} mult_err={n_err} est_rows={tot_est}"
    cur.execute(
        "UPDATE etl_runs SET finished_at=?, status=?, rows_upserted=?, message=? WHERE id=?",
        (finished, status, n_ok + tot_est, msg, run_id),
    )
    conn.commit()
    conn.close()

    print(f"\n[fundamentals] done: {msg}")
    if errors:
        print("\nProblemas (até 15):")
        for e in errors[:15]:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
