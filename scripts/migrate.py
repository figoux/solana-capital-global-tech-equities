"""
Aplica migrações pendentes no SQLite. Idempotente.

Uso: python scripts/migrate.py
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"


def column_exists(conn, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # M002 — theme_exposure_mapping + direction_override
    cur.execute("""
        CREATE TABLE IF NOT EXISTS theme_exposure_mapping (
            theme_id      TEXT NOT NULL,
            exposure_id   TEXT NOT NULL,
            weight        REAL NOT NULL,
            updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (theme_id, exposure_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tem_theme ON theme_exposure_mapping(theme_id)")

    if not column_exists(cur, "theme_ticker_exposure", "direction_override"):
        cur.execute("ALTER TABLE theme_ticker_exposure ADD COLUMN direction_override INTEGER")
        print("  + theme_ticker_exposure.direction_override")

    if not column_exists(cur, "theme_ticker_exposure", "source"):
        cur.execute("ALTER TABLE theme_ticker_exposure ADD COLUMN source TEXT DEFAULT 'auto'")
        print("  + theme_ticker_exposure.source")

    # M003 — view p/ pair trading: score 0-100 por (ticker × tema)
    # Score = SUM(ticker_exposure.weight_pct × theme_mapping.weight) — scale 0-100
    # (ex: NVDA em gpu_vs_asic = 70×1.0 + 10×0.3 = 73)
    # Manual override (theme_ticker_exposure.exposure em 0-3) escalado ×33 p/ alinhar
    cur.execute("DROP VIEW IF EXISTS v_ticker_theme_score")
    cur.execute("""
        CREATE VIEW v_ticker_theme_score AS
        SELECT
          c.ticker,
          t.theme_id,
          COALESCE(
            tte.exposure * 33,
            ROUND(SUM(te.weight_pct * tem.weight), 1)
          ) AS score,
          CASE WHEN tte.exposure IS NOT NULL THEN 'manual' ELSE 'auto' END AS source,
          tte.direction_override AS direction_override
        FROM companies c
        CROSS JOIN themes t
        LEFT JOIN theme_ticker_exposure tte ON tte.ticker=c.ticker AND tte.theme_id=t.theme_id
        LEFT JOIN ticker_exposure te ON te.ticker=c.ticker
        LEFT JOIN theme_exposure_mapping tem ON tem.theme_id=t.theme_id AND tem.exposure_id=te.exposure_id
        WHERE c.active=1 AND t.active=1
        GROUP BY c.ticker, t.theme_id
    """)

    # M004 — pb_ttm column em multiples
    if not column_exists(cur, "multiples", "pb_ttm"):
        cur.execute("ALTER TABLE multiples ADD COLUMN pb_ttm REAL")
        print("  + multiples.pb_ttm")

    # M005 — earnings_history table (reacao dia-apos release)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history (
          ticker            TEXT NOT NULL,
          fiscal_period     TEXT NOT NULL,
          report_date       TEXT NOT NULL,
          close_before      REAL,
          close_after       REAL,
          reaction_pct      REAL,
          report_time       TEXT,
          updated_at        TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (ticker, fiscal_period),
          FOREIGN KEY (ticker) REFERENCES companies(ticker)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_eh_ticker_date ON earnings_history(ticker, report_date DESC)")

    # M006 — mag6_erp_history table (daily ERP per Big Tech 6 + treasury + spreads)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mag6_erp_history (
          date           TEXT NOT NULL,
          ticker         TEXT NOT NULL,
          price          REAL,
          eps_ttm        REAL,
          pe_ttm         REAL,
          pe_fwd_fy1     REAL,
          earning_yield  REAL,
          treasury_5y    REAL,
          spread_bps     INTEGER,
          bond_yield     REAL,
          erp            REAL,
          PRIMARY KEY (date, ticker)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mag6_erp_date ON mag6_erp_history(date DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mag6_erp_ticker ON mag6_erp_history(ticker, date DESC)")

    # M007 — adr_premium table (prêmio histórico ADR vs ação local)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS adr_premium (
          pair_id          TEXT NOT NULL,     -- 'SKHY', 'TSM'
          date             TEXT NOT NULL,     -- YYYY-MM-DD
          adr_close        REAL,              -- close do ADR na moeda do ADR (USD)
          local_close      REAL,              -- close da ação local na moeda local
          fx               REAL,              -- FX local-per-USD usado na conversão
          local_in_adr_ccy REAL,              -- local convertido p/ moeda do ADR, ajustado pelo ratio
          ratio            REAL,              -- ações locais por 1 ADR
          premium_pct      REAL,              -- (adr / local_in_adr_ccy - 1) * 100
          PRIMARY KEY (pair_id, date)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_adr_premium_date ON adr_premium(pair_id, date DESC)")

    conn.commit()
    conn.close()
    print("[migrate] done")


if __name__ == "__main__":
    main()
