"""
Computa similaridade entre tickers via cosine similarity no vetor de business exposures.

Cosine sim ∈ [0, 1]:
    1.0 = exposure mix idêntico (e.g. KLAC vs LRCX ambos wfe_equipment=100)
    0.7+ = peers fortes (AMD vs NVDA, ambos ai_compute pesado)
    0.3-0.6 = overlap parcial
    <0.3 = exposures quase disjuntas

Popula tabela pairs_similarity. Idempotente (DROP + recompute).

Uso:
    python -m backend.etl.pairs_compute
    python -m backend.etl.pairs_compute --min-sim 0.4  (threshold p/ salvar)
    python -m backend.etl.pairs_compute --top-n 20     (por ticker, top N peers)
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"


def build_matrix(conn: sqlite3.Connection) -> tuple[list[str], list[str], np.ndarray]:
    """Retorna (tickers, buckets, matriz [n_tickers × n_buckets])."""
    tickers = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT c.ticker FROM companies c "
            "JOIN ticker_exposure te ON te.ticker=c.ticker "
            "WHERE c.active=1 ORDER BY c.ticker"
        ).fetchall()
    ]
    buckets = [
        r[0] for r in conn.execute(
            "SELECT exposure_id FROM business_exposures ORDER BY sort_order"
        ).fetchall()
    ]
    t_idx = {t: i for i, t in enumerate(tickers)}
    b_idx = {b: i for i, b in enumerate(buckets)}

    M = np.zeros((len(tickers), len(buckets)), dtype=float)
    for t, b, w in conn.execute(
        "SELECT ticker, exposure_id, weight_pct FROM ticker_exposure"
    ).fetchall():
        if t in t_idx and b in b_idx:
            M[t_idx[t], b_idx[b]] = w
    return tickers, buckets, M


def cosine_matrix(M: np.ndarray) -> np.ndarray:
    """Retorna matriz n×n com cosine similarity entre linhas."""
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    safe = np.where(norms > 0, norms, 1)
    Mn = M / safe
    return Mn @ Mn.T


def top_shared_bucket(a_vec: np.ndarray, b_vec: np.ndarray, buckets: list[str]) -> str:
    """Retorna 'ecommerce: 52 vs 100' — o bucket com maior overlap."""
    overlap = np.minimum(a_vec, b_vec)
    if overlap.max() == 0:
        return ""
    i = int(overlap.argmax())
    return f"{buckets[i]}: {a_vec[i]:.0f} vs {b_vec[i]:.0f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-sim", type=float, default=0.30,
                        help="Similaridade mínima p/ gravar (default 0.30)")
    parser.add_argument("--top-n", type=int, default=15,
                        help="Top N peers por ticker (default 15)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tickers, buckets, M = build_matrix(conn)
    if not tickers:
        print("[pairs_compute] nenhum ticker com exposure. Rode exposures_seed primeiro.")
        return

    S = cosine_matrix(M)
    print(f"[pairs_compute] matrix={len(tickers)}×{len(buckets)} | similarity={S.shape}")

    today = date.today().isoformat()
    cur.execute("DELETE FROM pairs_similarity")

    n_rows = 0
    for i, ta in enumerate(tickers):
        # Ordena peers de ta por similaridade DESC (excluindo ele mesmo)
        sims = S[i].copy()
        sims[i] = -1
        order = np.argsort(-sims)
        kept = 0
        for j in order:
            if kept >= args.top_n:
                break
            sim = float(sims[j])
            if sim < args.min_sim:
                break
            tb = tickers[j]
            shared = top_shared_bucket(M[i], M[j], buckets)
            cur.execute(
                "INSERT OR REPLACE INTO pairs_similarity (ticker_a, ticker_b, cosine_sim, shared_exposure_top, as_of_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (ta, tb, round(sim, 4), shared, today),
            )
            n_rows += 1
            kept += 1

    conn.commit()
    print(f"[pairs_compute] {n_rows} pairs gravados (min_sim={args.min_sim}, top_n={args.top_n})")

    # Samples: top peers de alguns tickers icônicos
    print("\nTop peers amostra:")
    for t in ("NVDA", "AMZN", "MSFT", "AAPL", "ISRG", "V", "COIN"):
        rows = cur.execute(
            "SELECT ticker_b, cosine_sim, shared_exposure_top "
            "FROM pairs_similarity WHERE ticker_a=? ORDER BY cosine_sim DESC LIMIT 5",
            (t,),
        ).fetchall()
        if rows:
            print(f"  {t}:")
            for b, s, sh in rows:
                print(f"    {b:12s} sim={s:.3f}  [{sh}]")

    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, finished_at, status, rows_upserted, message) "
        "VALUES (?, ?, ?, 'ok', ?, ?)",
        (
            "pairs_compute",
            datetime.now().isoformat(timespec="seconds"),
            datetime.now().isoformat(timespec="seconds"),
            n_rows,
            f"matrix={len(tickers)}x{len(buckets)} pairs={n_rows}",
        ),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
