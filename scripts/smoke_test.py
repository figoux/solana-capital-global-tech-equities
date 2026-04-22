"""
Smoke test — confirma que yfinance e o SQLite estão funcionando.
Puxa 4 tickers representativos (US, EU, KR, HK) e imprime metadados.
"""
import sqlite3
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

TEST_TICKERS = [
    ("NVDA", "US"),
    ("ASML", "EU"),
    ("005930.KS", "KR"),
    ("9988.HK", "HK"),
]

def main() -> None:
    # 1. Check DB is there
    assert DB_PATH.exists(), f"DB não encontrado em {DB_PATH} — rode scripts/init_db.py primeiro"
    conn = sqlite3.connect(DB_PATH)
    n_tables = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    conn.close()
    print(f"[db] {DB_PATH.name} OK — {n_tables} tabelas")

    # 2. yfinance pulls
    print("\n[yfinance] Puxando 4 tickers representativos...")
    print(f"{'ticker':10s} | {'name':30s} | {'mkt_cap':>15s} | {'fwd_pe':>8s} | {'currency':8s}")
    print("-" * 85)
    for t, region in TEST_TICKERS:
        try:
            info = yf.Ticker(t).info
            name = str(info.get("shortName") or info.get("longName") or "?")[:30]
            mkt = info.get("marketCap")
            mkt_s = f"{mkt/1e9:.1f}B" if mkt else "?"
            fwd_pe = info.get("forwardPE")
            fwd_pe_s = f"{fwd_pe:.1f}" if isinstance(fwd_pe, (int, float)) else "?"
            curr = info.get("currency") or "?"
            print(f"{t:10s} | {name:30s} | {mkt_s:>15s} | {fwd_pe_s:>8s} | {curr:8s}")
        except Exception as e:
            print(f"{t:10s} | ERRO: {e}")

    print("\n[ok] Se as 4 linhas apareceram com mkt_cap preenchido, o yfinance está tudo certo.")
    print("    Warning sobre 'expecting value' ou '404' é comum quando Yahoo rate-limita — roda de novo em 30s.")

if __name__ == "__main__":
    main()
