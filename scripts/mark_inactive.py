"""
Marca tickers como active=0 (delisted / M&A / mudou de ticker).

Uso:
    python scripts/mark_inactive.py JNPR --reason "Acquired by HPE Jul-2025"
    python scripts/mark_inactive.py JNPR NOK --reason "test"
"""
import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for t in args.tickers:
        cur.execute(
            "UPDATE companies SET active=0, updated_at=CURRENT_TIMESTAMP WHERE ticker=?",
            (t.upper(),),
        )
        print(f"  {t.upper()}: active=0 (rows={cur.rowcount})")
    conn.commit()
    conn.close()
    if args.reason:
        print(f"\nRazão: {args.reason}")
        print("(Grave em notes/companies/<ticker>.md se quiser histórico.)")


if __name__ == "__main__":
    main()
