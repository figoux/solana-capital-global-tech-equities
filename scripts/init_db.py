"""
Cria (ou atualiza) o SQLite a partir de backend/db/schema.sql.
Seguro de rodar múltiplas vezes — todos os CREATE usam IF NOT EXISTS.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"
SCHEMA_PATH = ROOT / "backend" / "db" / "schema.sql"

def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(schema)
        conn.commit()

        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
        indexes = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        print(f"OK: SQLite em {DB_PATH}")
        print(f"Tabelas ({len(tables)}):")
        for t in tables:
            print(f"  - {t}")
        print(f"Indexes ({len(indexes)}):")
        for i in indexes:
            print(f"  - {i}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
