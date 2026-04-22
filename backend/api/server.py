"""
FastAPI server — Solana Global Tech dashboard.

Run:
    uvicorn backend.api.server:app --reload --host 127.0.0.1 --port 8000

Pages:
    GET  /                             -> frontend/index.html
    GET  /company/{ticker}             -> frontend/company.html
    GET  /theme/{theme_id}             -> frontend/theme.html
    GET  /pair/{a}/{b}                 -> frontend/pair.html

API:
    GET  /api/heatmap                  -> matriz temas × subsetores
    GET  /api/earnings/week?n=2        -> earnings nas próximas N semanas
    GET  /api/company/{ticker}         -> detalhe de 1 ticker (+ pairs suggestion)
    GET  /api/universe                 -> lista resumida p/ dropdown
    GET  /api/theme/{theme_id}         -> detalhe do tema (tickers expostos, basket, earnings)
    GET  /api/theme/{theme_id}/pairs   -> pair trades intra-tema
    GET  /api/pairs/{ticker}           -> peers do ticker com vol comparison
    GET  /api/pair/{a}/{b}             -> detalhe de par A×B
    POST /api/override/direction       -> ajusta direction_override (theme × ticker)
    POST /api/override/exposure        -> lock/ajusta ticker_exposure (não implementado v1)
"""
from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"
FRONTEND_DIR = ROOT / "frontend"

# -------------------- Auth (HTTP Basic, opt-in via env) --------------------
# Local dev: não seta DASHBOARD_PASSWORD → sem auth
# Render/prod: seta DASHBOARD_USER + DASHBOARD_PASSWORD → exige login em TODAS rotas
_security = HTTPBasic(auto_error=False)


def _auth(
    request: Request,
    creds: Optional[HTTPBasicCredentials] = Depends(_security),
) -> str:
    # Health endpoint sempre publico (Render healthcheck)
    if request.url.path == "/health":
        return "health"
    expected_pass = os.environ.get("DASHBOARD_PASSWORD", "")
    if not expected_pass:
        return "anon"  # auth disabled (local dev)
    expected_user = os.environ.get("DASHBOARD_USER", "solana")
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth required",
            headers={"WWW-Authenticate": 'Basic realm="Solana Global Tech"'},
        )
    ok_user = secrets.compare_digest(creds.username, expected_user)
    ok_pass = secrets.compare_digest(creds.password, expected_pass)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Solana Global Tech"'},
        )
    return creds.username


app = FastAPI(title="Solana Global Tech", dependencies=[Depends(_auth)])


@app.get("/health")
def health():
    """Public healthcheck — Render bate aqui a cada ~30s."""
    return {"status": "ok"}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# -------------------- Pages --------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/company/{ticker}")
def company_page(ticker: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "company.html")


@app.get("/theme/{theme_id}")
def theme_page(theme_id: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "theme.html")


@app.get("/pair/{a}/{b}")
def pair_page(a: str, b: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "pair.html")


# -------------------- API --------------------

@app.get("/api/universe")
def universe():
    conn = _db()
    rows = conn.execute(
        "SELECT ticker, name, subsector, country, is_private, active "
        "FROM companies ORDER BY mkt_cap_rank_hint IS NULL, mkt_cap_rank_hint"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/heatmap")
def heatmap():
    """Retorna { subsectors:[...], themes:[{theme_id,name,category,cells:{sub:bullishness}}]}"""
    conn = _db()
    subs = [r[0] for r in conn.execute(
        "SELECT DISTINCT subsector FROM companies WHERE active=1 AND is_private=0 ORDER BY subsector"
    ).fetchall()]

    themes_rows = conn.execute(
        "SELECT theme_id, name, category, sort_order FROM themes WHERE active=1 ORDER BY sort_order"
    ).fetchall()

    bull_rows = conn.execute(
        "SELECT theme_id, subsector, bullishness, rationale_md FROM theme_subsector_bullishness"
    ).fetchall()
    bull: dict[tuple[str, str], dict] = {}
    for b in bull_rows:
        bull[(b["theme_id"], b["subsector"])] = {"b": b["bullishness"], "md": b["rationale_md"]}

    # Contagem de tickers por subsetor
    counts = dict(conn.execute(
        "SELECT subsector, COUNT(*) FROM companies WHERE active=1 AND is_private=0 GROUP BY subsector"
    ).fetchall())
    conn.close()

    out_themes = []
    for t in themes_rows:
        cells = {}
        for sub in subs:
            v = bull.get((t["theme_id"], sub))
            cells[sub] = {"b": v["b"] if v else 0, "md": v["md"] if v else None}
        out_themes.append({
            "theme_id": t["theme_id"],
            "name": t["name"],
            "category": t["category"],
            "cells": cells,
        })
    return {"subsectors": subs, "subsector_counts": counts, "themes": out_themes}


@app.get("/api/earnings/week")
def earnings_week(n: int = 2):
    """Earnings nas próximas N semanas (default 2)."""
    conn = _db()
    start = date.today()
    end = start + timedelta(weeks=n)
    rows = conn.execute(
        """
        SELECT
            e.ticker, e.fiscal_period, e.report_date, e.report_time, e.status,
            e.eps_est, e.rev_est,
            c.name, c.subsector, c.country, c.currency,
            m.mkt_cap_usd, m.fwd_pe_ntm, m.fwd_pe_fy1, m.fwd_pe_fy2,
            m.eps_growth_fy1, m.eps_growth_fy2, m.peg_ntm
        FROM earnings_events e
        JOIN companies c ON c.ticker = e.ticker
        LEFT JOIN multiples m ON m.ticker = e.ticker
            AND m.as_of_date = (SELECT MAX(as_of_date) FROM multiples WHERE ticker=e.ticker)
        WHERE e.status='upcoming' AND e.report_date BETWEEN ? AND ?
        ORDER BY e.report_date, m.mkt_cap_usd DESC
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/company/{ticker}")
def company_detail(ticker: str):
    ticker = ticker.upper()
    conn = _db()
    c = conn.execute(
        "SELECT * FROM companies WHERE ticker=?",
        (ticker,),
    ).fetchone()
    if not c:
        conn.close()
        raise HTTPException(404, f"Ticker {ticker} não encontrado")

    mult = conn.execute(
        "SELECT * FROM multiples WHERE ticker=? ORDER BY as_of_date DESC LIMIT 1",
        (ticker,),
    ).fetchone()

    ests = conn.execute(
        "SELECT fiscal_period, period_type, eps_mean, eps_low, eps_high, eps_count, "
        "       revenue_mean, revenue_low, revenue_high, currency "
        "FROM estimates WHERE ticker=? AND as_of_date=(SELECT MAX(as_of_date) FROM estimates WHERE ticker=?) "
        "ORDER BY CASE fiscal_period "
        "  WHEN 'FY0' THEN 0 WHEN 'CURR_Q' THEN 1 WHEN 'NEXT_Q' THEN 2 "
        "  WHEN 'FY1' THEN 3 WHEN 'FY2' THEN 4 ELSE 99 END",
        (ticker, ticker),
    ).fetchall()

    next_earn = conn.execute(
        "SELECT fiscal_period, report_date, report_time, status, eps_est, rev_est "
        "FROM earnings_events WHERE ticker=? AND status='upcoming' "
        "ORDER BY report_date LIMIT 1",
        (ticker,),
    ).fetchone()

    prices = conn.execute(
        "SELECT date, close, adj_close, volume FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 252",
        (ticker,),
    ).fetchall()

    themes_tags = conn.execute(
        "SELECT t.theme_id, t.name, tte.exposure FROM theme_ticker_exposure tte "
        "JOIN themes t ON t.theme_id=tte.theme_id WHERE tte.ticker=? ORDER BY tte.exposure DESC",
        (ticker,),
    ).fetchall()

    exposures = conn.execute(
        "SELECT e.exposure_id, e.name, e.category, te.weight_pct, te.source, te.locked "
        "FROM ticker_exposure te JOIN business_exposures e ON e.exposure_id=te.exposure_id "
        "WHERE te.ticker=? ORDER BY te.weight_pct DESC",
        (ticker,),
    ).fetchall()

    vol = conn.execute(
        "SELECT * FROM volatility WHERE ticker=? ORDER BY as_of_date DESC LIMIT 1",
        (ticker,),
    ).fetchone()

    conn.close()
    return {
        "company": dict(c),
        "multiples": dict(mult) if mult else None,
        "estimates": [dict(e) for e in ests],
        "next_earnings": dict(next_earn) if next_earn else None,
        "prices_last_year": [dict(p) for p in reversed(prices)],
        "themes": [dict(t) for t in themes_tags],
        "exposures": [dict(e) for e in exposures],
        "volatility": dict(vol) if vol else None,
    }


# -------------------- Theme drill-down --------------------

@app.get("/api/theme/{theme_id}")
def theme_detail(theme_id: str, min_score: float = 20.0, top_n: int = 30):
    """Retorna tema + tickers expostos (score > min_score) + basket sugerido + earnings próximos."""
    conn = _db()
    theme = conn.execute("SELECT * FROM themes WHERE theme_id=?", (theme_id,)).fetchone()
    if not theme:
        conn.close()
        raise HTTPException(404, f"Theme {theme_id} não encontrado")

    # Bullishness matrix by subsector (pra calcular direção default)
    bull_rows = conn.execute(
        "SELECT subsector, bullishness, rationale_md FROM theme_subsector_bullishness WHERE theme_id=?",
        (theme_id,),
    ).fetchall()
    bull_map = {r["subsector"]: r["bullishness"] for r in bull_rows}

    # Tickers expostos (auto-score via mapping)
    ticker_rows = conn.execute(
        """
        SELECT
          v.ticker, v.score, v.source, v.direction_override,
          c.name, c.subsector, c.country, c.currency, c.is_private,
          m.mkt_cap_usd, m.fwd_pe_ntm, m.fwd_pe_fy1, m.eps_growth_fy1, m.rev_growth_fy1,
          vol.rv_30d, vol.iv_30d_atm, vol.iv_skew_25d,
          e.report_date AS next_earnings_date, e.fiscal_period AS next_earnings_period
        FROM v_ticker_theme_score v
        JOIN companies c ON c.ticker=v.ticker
        LEFT JOIN multiples m ON m.ticker=v.ticker
          AND m.as_of_date=(SELECT MAX(as_of_date) FROM multiples WHERE ticker=v.ticker)
        LEFT JOIN volatility vol ON vol.ticker=v.ticker
          AND vol.as_of_date=(SELECT MAX(as_of_date) FROM volatility WHERE ticker=v.ticker)
        LEFT JOIN earnings_events e ON e.ticker=v.ticker AND e.status='upcoming'
          AND e.report_date=(SELECT MIN(report_date) FROM earnings_events WHERE ticker=v.ticker AND status='upcoming')
        WHERE v.theme_id=? AND v.score >= ? AND c.active=1
        ORDER BY v.score DESC, m.mkt_cap_usd DESC
        LIMIT ?
        """,
        (theme_id, min_score, top_n),
    ).fetchall()

    # Direção de cada ticker: override manual > bullishness do subsetor
    tickers = []
    for r in ticker_rows:
        d = dict(r)
        subsector_bull = bull_map.get(d["subsector"], 0)
        d["subsector_bull"] = subsector_bull
        # direção final: override explícito vira ±1, senão deriva do sinal da bullishness
        if d["direction_override"] is not None:
            d["direction"] = d["direction_override"]
        elif subsector_bull > 0:
            d["direction"] = 1
        elif subsector_bull < 0:
            d["direction"] = -1
        else:
            d["direction"] = 0
        tickers.append(d)

    # Basket sugerido: split em long (direction=1) e short (direction=-1), equal-weight
    longs = [t for t in tickers if t["direction"] == 1][:10]
    shorts = [t for t in tickers if t["direction"] == -1][:5]
    basket = {
        "longs": [{"ticker": t["ticker"], "weight_pct": round(100.0 / len(longs), 1) if longs else 0}
                  for t in longs],
        "shorts": [{"ticker": t["ticker"], "weight_pct": round(100.0 / len(shorts), 1) if shorts else 0}
                   for t in shorts],
        "method": "equal_weight",
    }

    # Earnings próximos (4 semanas) filtrado pelos tickers expostos
    tickers_set = [t["ticker"] for t in tickers]
    upcoming_earnings = []
    if tickers_set:
        placeholders = ",".join("?" * len(tickers_set))
        upcoming_earnings = [
            dict(r) for r in conn.execute(
                f"""
                SELECT e.ticker, e.fiscal_period, e.report_date, e.report_time,
                       e.eps_est, e.rev_est, c.name, c.subsector
                FROM earnings_events e JOIN companies c ON c.ticker=e.ticker
                WHERE e.ticker IN ({placeholders}) AND e.status='upcoming'
                  AND e.report_date BETWEEN ? AND ?
                ORDER BY e.report_date
                """,
                (*tickers_set, date.today().isoformat(),
                 (date.today() + timedelta(weeks=4)).isoformat()),
            ).fetchall()
        ]

    conn.close()
    return {
        "theme": dict(theme),
        "bullishness_by_subsector": bull_map,
        "tickers": tickers,
        "basket": basket,
        "upcoming_earnings": upcoming_earnings,
        "total_exposed": len(tickers),
    }


@app.get("/api/theme/{theme_id}/pairs")
def theme_pairs(theme_id: str, min_score: float = 40.0, top_n: int = 10):
    """Pair trades intra-tema: acha pares dentro dos tickers expostos com alta cosine sim."""
    conn = _db()
    tickers = [
        r[0] for r in conn.execute(
            "SELECT ticker FROM v_ticker_theme_score WHERE theme_id=? AND score>=? ORDER BY score DESC",
            (theme_id, min_score),
        ).fetchall()
    ]
    if len(tickers) < 2:
        conn.close()
        return {"pairs": []}

    placeholders = ",".join("?" * len(tickers))
    rows = conn.execute(
        f"""
        SELECT
          p.ticker_a, p.ticker_b, p.cosine_sim, p.shared_exposure_top,
          ca.subsector AS sub_a, cb.subsector AS sub_b,
          va.iv_30d_atm AS iv_a, vb.iv_30d_atm AS iv_b,
          va.rv_30d AS rv_a, vb.rv_30d AS rv_b,
          ma.mkt_cap_usd AS mcap_a, mb.mkt_cap_usd AS mcap_b,
          ma.fwd_pe_fy1 AS pe_a, mb.fwd_pe_fy1 AS pe_b
        FROM pairs_similarity p
        JOIN companies ca ON ca.ticker=p.ticker_a
        JOIN companies cb ON cb.ticker=p.ticker_b
        LEFT JOIN volatility va ON va.ticker=p.ticker_a
          AND va.as_of_date=(SELECT MAX(as_of_date) FROM volatility WHERE ticker=p.ticker_a)
        LEFT JOIN volatility vb ON vb.ticker=p.ticker_b
          AND vb.as_of_date=(SELECT MAX(as_of_date) FROM volatility WHERE ticker=p.ticker_b)
        LEFT JOIN multiples ma ON ma.ticker=p.ticker_a
          AND ma.as_of_date=(SELECT MAX(as_of_date) FROM multiples WHERE ticker=p.ticker_a)
        LEFT JOIN multiples mb ON mb.ticker=p.ticker_b
          AND mb.as_of_date=(SELECT MAX(as_of_date) FROM multiples WHERE ticker=p.ticker_b)
        WHERE p.ticker_a IN ({placeholders}) AND p.ticker_b IN ({placeholders})
          AND p.ticker_a < p.ticker_b
        ORDER BY p.cosine_sim DESC
        LIMIT ?
        """,
        (*tickers, *tickers, top_n),
    ).fetchall()
    conn.close()

    # Para cada par, calcula iv_spread (long lado cheap IV, short lado rich IV)
    pairs = []
    for r in rows:
        d = dict(r)
        iv_a, iv_b = d.get("iv_a"), d.get("iv_b")
        if iv_a and iv_b:
            d["iv_spread_pts"] = round((iv_a - iv_b) * 100, 2)
            d["suggested_trade"] = f"Long {r['ticker_a' if iv_a < iv_b else 'ticker_b']} / Short {r['ticker_b' if iv_a < iv_b else 'ticker_a']}"
        pairs.append(d)
    return {"pairs": pairs, "n_tickers_in_theme": len(tickers)}


# -------------------- Pair trading --------------------

@app.get("/api/pairs/{ticker}")
def pairs_of_ticker(ticker: str, top_n: int = 10):
    """Peers por cosine similarity, com vol + mults comparados."""
    ticker = ticker.upper()
    conn = _db()

    # Ticker principal + stats
    focal = conn.execute(
        """
        SELECT c.ticker, c.name, c.subsector,
               m.mkt_cap_usd, m.fwd_pe_fy1, m.eps_growth_fy1,
               v.rv_30d, v.iv_30d_atm, v.iv_skew_25d, v.iv_60d_atm
        FROM companies c
        LEFT JOIN multiples m ON m.ticker=c.ticker
          AND m.as_of_date=(SELECT MAX(as_of_date) FROM multiples WHERE ticker=c.ticker)
        LEFT JOIN volatility v ON v.ticker=c.ticker
          AND v.as_of_date=(SELECT MAX(as_of_date) FROM volatility WHERE ticker=c.ticker)
        WHERE c.ticker=?
        """,
        (ticker,),
    ).fetchone()
    if not focal:
        conn.close()
        raise HTTPException(404, f"Ticker {ticker} não encontrado")

    # Peers via pairs_similarity
    peers_rows = conn.execute(
        """
        SELECT
          CASE WHEN p.ticker_a=? THEN p.ticker_b ELSE p.ticker_a END AS peer,
          p.cosine_sim, p.shared_exposure_top
        FROM pairs_similarity p
        WHERE p.ticker_a=? OR p.ticker_b=?
        ORDER BY p.cosine_sim DESC
        LIMIT ?
        """,
        (ticker, ticker, ticker, top_n),
    ).fetchall()

    peers = []
    for pr in peers_rows:
        peer = pr["peer"]
        stats = conn.execute(
            """
            SELECT c.ticker, c.name, c.subsector, c.country,
                   m.mkt_cap_usd, m.fwd_pe_fy1, m.eps_growth_fy1,
                   v.rv_30d, v.iv_30d_atm, v.iv_60d_atm, v.iv_skew_25d,
                   e.report_date AS next_earnings_date
            FROM companies c
            LEFT JOIN multiples m ON m.ticker=c.ticker
              AND m.as_of_date=(SELECT MAX(as_of_date) FROM multiples WHERE ticker=c.ticker)
            LEFT JOIN volatility v ON v.ticker=c.ticker
              AND v.as_of_date=(SELECT MAX(as_of_date) FROM volatility WHERE ticker=c.ticker)
            LEFT JOIN earnings_events e ON e.ticker=c.ticker AND e.status='upcoming'
              AND e.report_date=(SELECT MIN(report_date) FROM earnings_events WHERE ticker=c.ticker AND status='upcoming')
            WHERE c.ticker=?
            """,
            (peer,),
        ).fetchone()
        if not stats:
            continue
        d = dict(stats)
        d["cosine_sim"] = pr["cosine_sim"]
        d["shared_exposure_top"] = pr["shared_exposure_top"]
        # Deltas vs focal para análise de par
        if focal["iv_30d_atm"] and d["iv_30d_atm"]:
            d["iv_spread_pts"] = round((d["iv_30d_atm"] - focal["iv_30d_atm"]) * 100, 2)
        if focal["rv_30d"] and d["rv_30d"]:
            d["rv_spread_pts"] = round((d["rv_30d"] - focal["rv_30d"]) * 100, 2)
        if focal["fwd_pe_fy1"] and d["fwd_pe_fy1"]:
            d["pe_spread"] = round(d["fwd_pe_fy1"] - focal["fwd_pe_fy1"], 1)
        # IV/RV ratio pra detectar "IV caro vs realized"
        if d["iv_30d_atm"] and d["rv_30d"]:
            d["iv_rv_ratio"] = round(d["iv_30d_atm"] / d["rv_30d"], 2)
        peers.append(d)

    focal_d = dict(focal)
    if focal_d.get("iv_30d_atm") and focal_d.get("rv_30d"):
        focal_d["iv_rv_ratio"] = round(focal_d["iv_30d_atm"] / focal_d["rv_30d"], 2)

    conn.close()
    return {"focal": focal_d, "peers": peers}


@app.get("/api/pair/{a}/{b}")
def pair_detail(a: str, b: str):
    """Detalhe full de um par A×B: exposições sobrepostas, vol ratios, sugestão de ratio."""
    a, b = a.upper(), b.upper()
    conn = _db()

    def _ticker_stats(t: str) -> dict | None:
        row = conn.execute(
            """
            SELECT c.ticker, c.name, c.subsector, c.currency, c.country,
                   m.mkt_cap_usd, m.fwd_pe_ntm, m.fwd_pe_fy1, m.fwd_pe_fy2,
                   m.eps_growth_fy1, m.rev_growth_fy1, m.peg_ntm,
                   v.rv_30d, v.rv_60d, v.iv_30d_atm, v.iv_60d_atm, v.iv_skew_25d,
                   e.report_date AS next_earnings_date, e.fiscal_period AS next_earnings_period
            FROM companies c
            LEFT JOIN multiples m ON m.ticker=c.ticker
              AND m.as_of_date=(SELECT MAX(as_of_date) FROM multiples WHERE ticker=c.ticker)
            LEFT JOIN volatility v ON v.ticker=c.ticker
              AND v.as_of_date=(SELECT MAX(as_of_date) FROM volatility WHERE ticker=c.ticker)
            LEFT JOIN earnings_events e ON e.ticker=c.ticker AND e.status='upcoming'
              AND e.report_date=(SELECT MIN(report_date) FROM earnings_events WHERE ticker=c.ticker AND status='upcoming')
            WHERE c.ticker=?
            """,
            (t,),
        ).fetchone()
        return dict(row) if row else None

    sa, sb = _ticker_stats(a), _ticker_stats(b)
    if not sa or not sb:
        conn.close()
        raise HTTPException(404, f"Ticker(s) não encontrado(s): {a}/{b}")

    # Exposures de cada lado + overlap
    exp_a = {r[0]: r[1] for r in conn.execute(
        "SELECT exposure_id, weight_pct FROM ticker_exposure WHERE ticker=?", (a,)).fetchall()}
    exp_b = {r[0]: r[1] for r in conn.execute(
        "SELECT exposure_id, weight_pct FROM ticker_exposure WHERE ticker=?", (b,)).fetchall()}
    bucket_names = dict(conn.execute("SELECT exposure_id, name FROM business_exposures").fetchall())
    all_keys = sorted(set(exp_a) | set(exp_b))
    exposures = [
        {
            "exposure_id": k,
            "name": bucket_names.get(k, k),
            "weight_a": exp_a.get(k, 0),
            "weight_b": exp_b.get(k, 0),
            "overlap": min(exp_a.get(k, 0), exp_b.get(k, 0)),
        }
        for k in all_keys
    ]
    exposures.sort(key=lambda x: -x["overlap"])

    # Cosine sim (se precomputada)
    sim_row = conn.execute(
        "SELECT cosine_sim, shared_exposure_top FROM pairs_similarity "
        "WHERE (ticker_a=? AND ticker_b=?) OR (ticker_a=? AND ticker_b=?)",
        (a, b, b, a),
    ).fetchone()
    cosine_sim = sim_row["cosine_sim"] if sim_row else None

    # Ratios sugeridos
    ratios: dict = {}
    if sa["iv_30d_atm"] and sb["iv_30d_atm"]:
        ratios["vol_neutral_ratio"] = round(sa["iv_30d_atm"] / sb["iv_30d_atm"], 3)
        ratios["iv_spread_pts"] = round((sa["iv_30d_atm"] - sb["iv_30d_atm"]) * 100, 2)
    if sa["fwd_pe_fy1"] and sb["fwd_pe_fy1"]:
        ratios["pe_spread"] = round(sa["fwd_pe_fy1"] - sb["fwd_pe_fy1"], 1)
    if sa["mkt_cap_usd"] and sb["mkt_cap_usd"]:
        ratios["mcap_ratio"] = round(sa["mkt_cap_usd"] / sb["mkt_cap_usd"], 2)

    conn.close()
    return {
        "a": sa,
        "b": sb,
        "cosine_sim": cosine_sim,
        "exposures_compared": exposures,
        "ratios": ratios,
    }


# -------------------- Ticker overlay on heatmap --------------------

@app.get("/api/ticker-theme-matrix/{ticker}")
def ticker_theme_matrix(ticker: str):
    """Scores do ticker em todos os temas + subsetor do ticker.
    Pra overlay do heatmap: dots nas células onde ticker × tema tem score alto."""
    ticker = ticker.upper()
    conn = _db()
    c = conn.execute(
        "SELECT ticker, name, subsector FROM companies WHERE ticker=?", (ticker,)
    ).fetchone()
    if not c:
        conn.close()
        raise HTTPException(404, f"Ticker {ticker} não encontrado")

    scores = [
        dict(r) for r in conn.execute(
            "SELECT theme_id, score, source, direction_override "
            "FROM v_ticker_theme_score WHERE ticker=?",
            (ticker,),
        ).fetchall()
    ]
    conn.close()
    return {
        "ticker": c["ticker"],
        "name": c["name"],
        "subsector": c["subsector"],
        "scores": scores,
    }


@app.get("/api/exposures-compared/{ticker}")
def exposures_compared(ticker: str, n_peers: int = 5):
    """Ticker focal + top-N peers por cosine sim com weights em matriz (category -> buckets -> ticker -> weight)."""
    ticker = ticker.upper()
    conn = _db()
    focal = conn.execute(
        "SELECT ticker, name, subsector FROM companies WHERE ticker=?", (ticker,)
    ).fetchone()
    if not focal:
        conn.close()
        raise HTTPException(404, f"Ticker {ticker} não encontrado")

    peer_rows = conn.execute(
        """
        SELECT CASE WHEN p.ticker_a=? THEN p.ticker_b ELSE p.ticker_a END AS peer,
               p.cosine_sim
        FROM pairs_similarity p
        WHERE p.ticker_a=? OR p.ticker_b=?
        ORDER BY p.cosine_sim DESC LIMIT ?
        """,
        (ticker, ticker, ticker, n_peers),
    ).fetchall()
    tickers = [ticker] + [r["peer"] for r in peer_rows]

    buckets = [
        dict(r) for r in conn.execute(
            "SELECT exposure_id, name, category, sort_order "
            "FROM business_exposures WHERE active=1 ORDER BY sort_order"
        ).fetchall()
    ]

    placeholders = ",".join("?" * len(tickers))
    w_rows = conn.execute(
        f"SELECT ticker, exposure_id, weight_pct FROM ticker_exposure "
        f"WHERE ticker IN ({placeholders})",
        tickers,
    ).fetchall()
    weights: dict = {}
    for r in w_rows:
        weights.setdefault(r["exposure_id"], {})[r["ticker"]] = r["weight_pct"]

    # Só buckets com ao menos 1 peso no conjunto (não polui grade com vazios)
    active_buckets = [b for b in buckets if b["exposure_id"] in weights]
    by_category: dict = {}
    for b in active_buckets:
        by_category.setdefault(b["category"], []).append(b)

    meta = {
        r["ticker"]: {"name": r["name"], "subsector": r["subsector"]}
        for r in conn.execute(
            f"SELECT ticker, name, subsector FROM companies WHERE ticker IN ({placeholders})",
            tickers,
        ).fetchall()
    }
    cosine_map = {r["peer"]: r["cosine_sim"] for r in peer_rows}

    conn.close()
    return {
        "focal": dict(focal),
        "tickers": tickers,
        "cosine_map": cosine_map,
        "meta": meta,
        "categories": list(by_category.keys()),
        "buckets_by_category": by_category,
        "weights": weights,
    }


# -------------------- Overrides (POST) --------------------

class DirectionOverrideBody(BaseModel):
    theme_id: str
    ticker: str
    direction: int | None  # -1, 0, 1, or null to clear
    rationale_md: str | None = None


@app.post("/api/override/direction")
def set_direction_override(body: DirectionOverrideBody):
    """Define direction_override em theme_ticker_exposure.
    direction=null limpa o override (volta a usar default do subsetor)."""
    if body.direction not in (-1, 0, 1, None):
        raise HTTPException(400, "direction deve ser -1, 0, 1 ou null")
    conn = _db()
    cur = conn.cursor()
    # Upsert — se não existe linha, cria com exposure=0 (é só pra segurar o override)
    cur.execute(
        """
        INSERT INTO theme_ticker_exposure (theme_id, ticker, exposure, direction, direction_override, rationale_md, updated_at, source)
        VALUES (?, ?, 0, 'long', ?, ?, CURRENT_TIMESTAMP, 'manual')
        ON CONFLICT(theme_id, ticker) DO UPDATE SET
          direction_override=excluded.direction_override,
          rationale_md=COALESCE(excluded.rationale_md, theme_ticker_exposure.rationale_md),
          updated_at=CURRENT_TIMESTAMP,
          source='manual'
        """,
        (body.theme_id, body.ticker, body.direction, body.rationale_md),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "theme_id": body.theme_id, "ticker": body.ticker, "direction": body.direction}


# -------------------- Static files --------------------

if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
