"""
Carrega universe.csv em companies (upsert por ticker).
Idempotente: pode rodar quantas vezes quiser.

Uso: python -m backend.etl.universe
"""
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"
CSV_PATH = ROOT / "universe.csv"


def _to_int(v, default=0):
    try:
        return int(v) if v not in (None, "") else default
    except (ValueError, TypeError):
        return default


def main() -> None:
    assert DB_PATH.exists(), f"DB não encontrado em {DB_PATH} — rode init_db primeiro"
    assert CSV_PATH.exists(), f"universe.csv não encontrado em {CSV_PATH}"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    started = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, status) VALUES (?, ?, ?)",
        ("universe", started, "running"),
    )
    run_id = cur.lastrowid

    n = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                continue
            yahoo = (row.get("yahoo_ticker") or "").strip() or None
            is_priv = _to_int(row.get("is_private"), 0)
            # privadas não têm yahoo_ticker válido
            if is_priv:
                yahoo = None

            cur.execute(
                """
                INSERT INTO companies
                  (ticker, yahoo_ticker, finnhub_ticker, name, subsector, country,
                   currency, fiscal_year_end, is_private, mkt_cap_rank_hint, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                  yahoo_ticker=excluded.yahoo_ticker,
                  finnhub_ticker=excluded.finnhub_ticker,
                  name=excluded.name,
                  subsector=excluded.subsector,
                  country=excluded.country,
                  currency=excluded.currency,
                  fiscal_year_end=excluded.fiscal_year_end,
                  is_private=excluded.is_private,
                  mkt_cap_rank_hint=excluded.mkt_cap_rank_hint,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    ticker,
                    yahoo,
                    yahoo if not is_priv else None,  # Finnhub costuma aceitar o mesmo ticker do Yahoo p/ US
                    (row.get("name") or "").strip(),
                    (row.get("subsector") or "").strip(),
                    (row.get("country") or "").strip() or None,
                    (row.get("currency") or "").strip() or None,
                    (row.get("fiscal_year_end") or "").strip() or None,
                    is_priv,
                    _to_int(row.get("mkt_cap_rank_hint"), None),
                ),
            )
            n += 1

    # Resumo por subsetor
    by_sub = dict(
        cur.execute(
            "SELECT subsector, COUNT(*) FROM companies GROUP BY subsector ORDER BY 2 DESC"
        ).fetchall()
    )
    total_pub = cur.execute("SELECT COUNT(*) FROM companies WHERE is_private=0").fetchone()[0]
    total_pvt = cur.execute("SELECT COUNT(*) FROM companies WHERE is_private=1").fetchone()[0]

    cur.execute(
        "UPDATE etl_runs SET finished_at=?, status=?, rows_upserted=?, message=? WHERE id=?",
        (datetime.utcnow().isoformat(timespec="seconds"), "ok", n, f"pub={total_pub} pvt={total_pvt}", run_id),
    )
    conn.commit()
    conn.close()

    print(f"[universe] {n} linhas upsertadas")
    print(f"  públicas: {total_pub}  |  privadas: {total_pvt}")
    print("  por subsetor:")
    for sub, c in by_sub.items():
        print(f"    {sub:22s} {c:3d}")


if __name__ == "__main__":
    main()
