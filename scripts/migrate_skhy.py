"""
Migração one-off: SKHY (Nasdaq ADR, IPO 10-jul-2026) vira ticker canônico do SK Hynix.

O que faz (idempotente — pode rodar mais de uma vez):
  1. Garante a linha SKHY em companies (rode backend.etl.universe antes, ou cria stub aqui).
  2. Move dados QUALITATIVOS + earnings de 000660.KS -> SKHY:
       earnings_events, earnings_history, guidance, notes, catalysts,
       theme_ticker_exposure, ticker_exposure
  3. NÃO move prices / volatility / multiples / estimates — a série KRW histórica
     fica com 000660.KS (que permanece ativo como perna local do prêmio ADR).
     SKHY acumula série USD limpa desde o IPO via ETL diário.
  4. Remove pares antigos de 000660.KS em pairs_similarity (recomputados pelo
     pairs_compute com SKHY, que herda o vetor de exposures).

Uso: python scripts/migrate_skhy.py
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

OLD = "000660.KS"
NEW = "SKHY"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    has_new = cur.execute("SELECT COUNT(*) FROM companies WHERE ticker=?", (NEW,)).fetchone()[0]
    if not has_new:
        # stub — backend.etl.universe sobrescreve com os dados do CSV
        cur.execute(
            "INSERT INTO companies (ticker, yahoo_ticker, finnhub_ticker, name, subsector, country, currency, fiscal_year_end, is_private) "
            "VALUES (?, ?, ?, 'SK Hynix ADR', 'Semis', 'KR', 'USD', 'Dec', 0)",
            (NEW, NEW, NEW),
        )
        print(f"  + companies: stub {NEW} criado (rode backend.etl.universe depois)")

    # Tabelas com FK/coluna ticker — mover OLD -> NEW
    ticker_tables = [
        "earnings_events",
        "earnings_history",
        "guidance",
        "theme_ticker_exposure",
        "ticker_exposure",
    ]
    for t in ticker_tables:
        # remove colisões (linha já existente em NEW com mesma PK) antes do UPDATE
        n = cur.execute(f"UPDATE OR IGNORE {t} SET ticker=? WHERE ticker=?", (NEW, OLD)).rowcount
        left = cur.execute(f"SELECT COUNT(*) FROM {t} WHERE ticker=?", (OLD,)).fetchone()[0]
        if left:
            cur.execute(f"DELETE FROM {t} WHERE ticker=?", (OLD,))
        print(f"  {t}: {n} movidas, {left} colisões descartadas")

    # notes/catalysts usam scope_type/scope_value
    for t in ("notes", "catalysts"):
        n = cur.execute(
            f"UPDATE {t} SET scope_value=? WHERE scope_type='ticker' AND scope_value=?",
            (NEW, OLD),
        ).rowcount
        print(f"  {t}: {n} movidas")

    # pairs antigos do OLD saem; pairs_compute recomputa com NEW
    n = cur.execute(
        "DELETE FROM pairs_similarity WHERE ticker_a=? OR ticker_b=?", (OLD, OLD)
    ).rowcount
    print(f"  pairs_similarity: {n} removidas (recompute com pairs_compute)")

    conn.commit()
    conn.close()
    print(f"[migrate_skhy] done — {NEW} canônico; {OLD} segue ativo como perna local (prices/vol KRW preservados)")


if __name__ == "__main__":
    main()
