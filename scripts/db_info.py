"""
Sanity-check rápido do estado do SQLite.

Uso: python scripts/db_info.py
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Companies
    n_total = cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    n_pub = cur.execute("SELECT COUNT(*) FROM companies WHERE is_private=0 AND active=1").fetchone()[0]
    n_pvt = cur.execute("SELECT COUNT(*) FROM companies WHERE is_private=1").fetchone()[0]
    n_inactive = cur.execute("SELECT COUNT(*) FROM companies WHERE active=0").fetchone()[0]
    print(f"[companies] total={n_total} | public-active={n_pub} | private={n_pvt} | inactive={n_inactive}")

    # Prices
    r = cur.execute("SELECT COUNT(DISTINCT ticker), COUNT(*), MIN(date), MAX(date) FROM prices").fetchone()
    print(f"[prices]    tickers={r[0]} | rows={r[1]} | range={r[2]} -> {r[3]}")

    # Públicos ativos sem preço
    rows = cur.execute(
        """
        SELECT c.ticker, c.yahoo_ticker, c.name, c.subsector
        FROM companies c
        WHERE c.is_private=0 AND c.active=1
          AND c.ticker NOT IN (SELECT DISTINCT ticker FROM prices)
        ORDER BY c.mkt_cap_rank_hint
        """
    ).fetchall()
    if rows:
        print(f"\n[!] {len(rows)} tickers publico-ativos SEM preço:")
        for t, y, name, sub in rows:
            print(f"    {t:10s} ({y or '-':10s}) | {sub:20s} | {name}")
    else:
        print("\n[ok] todos os públicos ativos têm preço")

    # Multiples
    r = cur.execute("SELECT COUNT(DISTINCT ticker), COUNT(*), MAX(as_of_date) FROM multiples").fetchone()
    print(f"[multiples] tickers={r[0]} | rows={r[1]} | latest={r[2]}")

    # Estimates
    r = cur.execute(
        "SELECT COUNT(DISTINCT ticker), COUNT(*), MAX(as_of_date), "
        "       COUNT(DISTINCT fiscal_period) "
        "FROM estimates WHERE source='yfinance'"
    ).fetchone()
    print(f"[estimates] tickers={r[0]} | rows={r[1]} | latest={r[2]} | periods={r[3]}")

    # Sample NVDA
    row = cur.execute(
        "SELECT ticker, as_of_date, mkt_cap_usd, fwd_pe_ntm, fwd_pe_fy1, fwd_pe_fy2, "
        "       eps_growth_fy1, eps_growth_fy2, peg_ntm "
        "FROM multiples WHERE ticker='NVDA' ORDER BY as_of_date DESC LIMIT 1"
    ).fetchone()
    if row:
        mcap_b = (row[2] / 1e9) if row[2] else None
        print(
            f"\n[sample NVDA] {row[1]} | mkt_cap=${mcap_b:.0f}B | "
            f"fwd P/E NTM={row[3]} FY1={row[4] and round(row[4],1)} FY2={row[5] and round(row[5],1)} | "
            f"EPS growth FY1={row[6] and f'{row[6]*100:.1f}%'} FY2={row[7] and f'{row[7]*100:.1f}%'} | PEG={row[8]}"
        )

    # Themes + Exposures + Mapping
    def table_exists(t):
        return cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None

    if table_exists("themes"):
        n_t = cur.execute("SELECT COUNT(*) FROM themes").fetchone()[0]
        n_b = cur.execute("SELECT COUNT(*) FROM theme_subsector_bullishness").fetchone()[0]
        print(f"\n[themes]    themes={n_t} | bullishness_cells={n_b}")

    if table_exists("business_exposures"):
        n_buckets = cur.execute("SELECT COUNT(*) FROM business_exposures").fetchone()[0]
        print(f"[exposures] buckets={n_buckets}")

    if table_exists("ticker_exposure"):
        n_te = cur.execute("SELECT COUNT(*) FROM ticker_exposure").fetchone()[0]
        n_te_tickers = cur.execute("SELECT COUNT(DISTINCT ticker) FROM ticker_exposure").fetchone()[0]
        print(f"[ticker_exp] tickers={n_te_tickers} | rows={n_te}")

    if table_exists("theme_exposure_mapping"):
        n_m = cur.execute("SELECT COUNT(*) FROM theme_exposure_mapping").fetchone()[0]
        n_mt = cur.execute("SELECT COUNT(DISTINCT theme_id) FROM theme_exposure_mapping").fetchone()[0]
        print(f"[theme_map] themes={n_mt} | rows={n_m}")

    # v_ticker_theme_score sanity — top 3 por tema selecionado
    try:
        for t_id in ("gpu_vs_asic", "cpu_demand", "humanoides"):
            rows = cur.execute(
                "SELECT ticker, score FROM v_ticker_theme_score WHERE theme_id=? AND score>0 "
                "ORDER BY score DESC LIMIT 3",
                (t_id,),
            ).fetchall()
            if rows:
                top = ", ".join(f"{t}:{s:.0f}" for t, s in rows)
                print(f"  {t_id:18s} → {top}")
    except sqlite3.OperationalError:
        pass  # view ainda não existe

    # Últimos ETL runs
    print("\n[etl_runs] últimos 6:")
    for row in cur.execute(
        "SELECT id, job_name, started_at, status, rows_upserted, message FROM etl_runs ORDER BY id DESC LIMIT 6"
    ).fetchall():
        print(f"    #{row[0]:3d} {row[1]:18s} {row[2]} | {row[3] or '-':8s} | rows={row[4]} | {row[5] or ''}")

    conn.close()


if __name__ == "__main__":
    main()
