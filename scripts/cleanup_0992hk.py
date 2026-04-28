"""
Remove 0992.HK do DB (substituido pelo ADR US LNVGY).
Idempotente — se ja foi rodado, nao faz nada.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    n_before = cur.execute("SELECT COUNT(*) FROM companies WHERE ticker='0992.HK'").fetchone()[0]
    if n_before == 0:
        print("[cleanup] 0992.HK ja removido — nada a fazer")
        conn.close()
        return

    tables = [
        "ticker_exposure",
        "theme_ticker_exposure",
        "multiples",
        "estimates",
        "earnings_events",
        "earnings_history",
        "volatility",
        "prices",
        "pairs_similarity",  # tem ticker_a e ticker_b
        "companies",
    ]
    for t in tables:
        if t == "pairs_similarity":
            r = cur.execute("DELETE FROM pairs_similarity WHERE ticker_a='0992.HK' OR ticker_b='0992.HK'").rowcount
        else:
            r = cur.execute(f"DELETE FROM {t} WHERE ticker='0992.HK'").rowcount
        print(f"  {t}: {r} rows deleted")
    conn.commit()
    conn.close()
    print("[cleanup] done — 0992.HK removido (LNVGY assume papel)")


if __name__ == "__main__":
    main()
