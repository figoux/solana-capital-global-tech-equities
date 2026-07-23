"""
Prêmio histórico ADR vs ação local. Popula a tabela adr_premium.

Para cada data com pregão comum (ADR + local + FX):
    local_in_adr_ccy = (local_close / fx_local_per_usd) * ratio
    premium_pct      = (adr_close / local_in_adr_ccy - 1) * 100

ratio = quantas ações LOCAIS 1 ADR representa (TSM: 5.0; SKHY: 0.1 — 10 ADS = 1 ord).
Ratio None = auto-detecta (mediana de adr_close / local_in_usd, arredondada ao
candidato mais próximo) e loga o valor — confira vs prospecto no primeiro run.

Nota de timing: compara closes do MESMO dia-calendário (Seul/Taipei fecham horas
antes de NY), o skew intradiário é inerente a monitores diários deste tipo.

Idempotente (upsert por pair_id+date). Uso:
    python -m backend.etl.adr_premium
    python -m backend.etl.adr_premium --pair SKHY
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

# pair_id -> config. fx é sempre "<ADR-ccy><local-ccy>=X" (local por 1 unidade da moeda do ADR).
PAIRS: dict[str, dict] = {
    "SKHY": {
        "name": "SK Hynix",
        "adr": "SKHY",          # Nasdaq, USD (IPO 2026-07-10)
        "local": "000660.KS",   # KRX, KRW
        "fx": "USDKRW=X",
        "ratio": 0.1,            # 10 ADS = 1 ação ordinária (F-1/424B4 do IPO Jul-2026)
        "start": "2026-07-09",  # véspera do IPO — sem emenda com o GDR (decisão Filipe 2026-07-23)
    },
    "TSM": {
        "name": "TSMC",
        "adr": "TSM",           # NYSE, USD
        "local": "2330.TW",     # TWSE, TWD
        "fx": "USDTWD=X",
        "ratio": 5.0,            # 1 ADR = 5 ações locais (fixo, conhecido)
        "start": None,           # None = 5 anos
    },
}

RATIO_CANDIDATES = [0.05, 0.1, 0.125, 0.2, 0.25, 0.5, 1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 8.0, 10.0, 20.0]


def _fetch(ticker: str, start: str, end: str) -> pd.Series:
    try:
        df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return pd.Series(dtype=float)
        s = df["Close"].copy()
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        s.index = pd.to_datetime(s.index).date
        s = s[~pd.Series(s.index).duplicated(keep="last").values]
        return s.astype(float).dropna()
    except Exception as e:
        print(f"  [warn] {ticker}: {e.__class__.__name__}: {e}")
        return pd.Series(dtype=float)


def _detect_ratio(adr_s: pd.Series, local_s: pd.Series, fx_s: pd.Series) -> float | None:
    common = sorted(set(adr_s.index) & set(local_s.index) & set(fx_s.index))
    if len(common) < 3:
        return None
    vals = []
    for d in common:
        fx = fx_s.loc[d]
        local_in_usd = local_s.loc[d] / fx if fx > 0 else 0
        if local_in_usd <= 0 or adr_s.loc[d] <= 0:
            continue
        # ratio = ações locais por 1 ADR  =>  adr_px ≈ local_in_usd * ratio
        vals.append(adr_s.loc[d] / local_in_usd)
    if not vals:
        return None
    raw = float(pd.Series(vals).median())
    best = min(RATIO_CANDIDATES, key=lambda c: abs(c - raw))
    # sanity: o candidato precisa estar a <15% do valor bruto, senão devolve o bruto
    if abs(best - raw) / raw > 0.15:
        print(f"  [warn] ratio bruto {raw:.3f} longe do candidato {best} — usando bruto")
        return round(raw, 4)
    return best


def run_pair(cur: sqlite3.Cursor, pair_id: str, cfg: dict) -> int:
    end = date.today() + timedelta(days=1)
    start = cfg["start"] or (end - timedelta(days=365 * 5 + 30)).isoformat()

    print(f"[adr_premium] {pair_id}: {cfg['adr']} vs {cfg['local']} (fx {cfg['fx']}) desde {start}")
    adr_s = _fetch(cfg["adr"], start, end.isoformat())
    local_s = _fetch(cfg["local"], start, end.isoformat())
    fx_s = _fetch(cfg["fx"], start, end.isoformat())
    print(f"  fetched: adr={len(adr_s)} local={len(local_s)} fx={len(fx_s)} dias")

    if adr_s.empty or local_s.empty or fx_s.empty:
        print(f"  [skip] {pair_id}: série vazia")
        return 0

    ratio = cfg["ratio"]
    if ratio is None:
        ratio = _detect_ratio(adr_s, local_s, fx_s)
        if ratio is None:
            print(f"  [skip] {pair_id}: não foi possível detectar ratio")
            return 0
        print(f"  ratio auto-detectado: 1 ADR = {ratio} ações locais  << CONFERIR vs prospecto")
    else:
        print(f"  ratio fixo: 1 ADR = {ratio} ações locais")

    common = sorted(set(adr_s.index) & set(local_s.index) & set(fx_s.index))
    n = 0
    for d in common:
        adr_px, local_px, fx = adr_s.loc[d], local_s.loc[d], fx_s.loc[d]
        if adr_px <= 0 or local_px <= 0 or fx <= 0:
            continue
        local_in_adr = (local_px / fx) * ratio
        if local_in_adr <= 0:
            continue
        premium = (adr_px / local_in_adr - 1.0) * 100.0
        cur.execute(
            """
            INSERT INTO adr_premium (pair_id, date, adr_close, local_close, fx, local_in_adr_ccy, ratio, premium_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pair_id, date) DO UPDATE SET
              adr_close=excluded.adr_close, local_close=excluded.local_close,
              fx=excluded.fx, local_in_adr_ccy=excluded.local_in_adr_ccy,
              ratio=excluded.ratio, premium_pct=excluded.premium_pct
            """,
            (pair_id, d.isoformat(), round(adr_px, 4), round(local_px, 4), round(fx, 6),
             round(local_in_adr, 4), ratio, round(premium, 4)),
        )
        n += 1
    last = cur.execute(
        "SELECT date, premium_pct FROM adr_premium WHERE pair_id=? ORDER BY date DESC LIMIT 1", (pair_id,)
    ).fetchone()
    if last:
        print(f"  {n} dias upsertados | último: {last[0]} premium {last[1]:+.2f}%")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", choices=list(PAIRS), help="roda só um par")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    started = datetime.now().isoformat(timespec="seconds")

    total = 0
    pairs = {args.pair: PAIRS[args.pair]} if args.pair else PAIRS
    for pair_id, cfg in pairs.items():
        total += run_pair(cur, pair_id, cfg)
        conn.commit()

    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, finished_at, status, rows_upserted, message) "
        "VALUES (?, ?, ?, 'ok', ?, ?)",
        ("adr_premium", started, datetime.now().isoformat(timespec="seconds"), total,
         f"pairs={','.join(pairs)}"),
    )
    conn.commit()
    conn.close()
    print(f"[adr_premium] done — {total} linhas")


if __name__ == "__main__":
    main()
