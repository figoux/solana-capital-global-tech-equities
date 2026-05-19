# Solana Capital Global Tech Equities

[![CI](https://github.com/figoux/solana-capital-global-tech-equities/actions/workflows/ci.yml/badge.svg)](https://github.com/figoux/solana-capital-global-tech-equities/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

A research dashboard for global technology equities, focused on **pair trading**,
**earnings tracking**, and **thematic exposure analysis**. Designed for an
equity long/short PM workflow — it answers the questions you ask in the hour
before a print: *what's the right hedge for this name, where is the IV cheap,
who reports next week, what did the stock do last quarter.*

```
                       ┌────────────────────────┐
                       │   Render (FastAPI)     │
                       │   serves dashboard     │
                       └───────────▲────────────┘
                                   │
                                   │ deploy on push
                                   │
┌────────────────┐    ┌────────────┴────────────┐
│  yfinance      │───▶│  Local ETL (Python)     │───▶ git push
│  Finnhub       │    │  → dashboard.db (SQLite)│
└────────────────┘    └─────────────────────────┘
```

The application is a single FastAPI process with a server-rendered Alpine.js
frontend. The ETL pipeline runs locally on a schedule (Windows Task Scheduler
in our setup), updates a SQLite snapshot, commits it to the repo, and Render
redeploys with the new data.

---

## Screenshots

| Heatmap (themes × subsectors) | Per-company page |
|:---:|:---:|
| ![Heatmap](docs/img/heatmap.png) | ![Company](docs/img/company.png) |
| **Pair workspace with 12m chart** | **Upcoming earnings feed** |
| ![Pair](docs/img/pair.png) | ![Earnings](docs/img/earnings.png) |

---

## What it actually shows

- **Thematic heatmap** — a matrix of `theme × subsector` bullishness ratings, with
  per-cell rationale stored in markdown. Click any theme row to drill into the
  exposed tickers and a suggested long/short basket.
- **Per-company page** — valuation snapshot (P/E forward & TTM, P/B, P/S, PEG,
  growth metrics), consensus estimates, next earnings event, business exposure
  weights by category, and historical day-after earnings reactions for the last
  four quarters.
- **Pair trading workspace** — cosine similarity between any two tickers based
  on business exposure weights, side-by-side multiples & volatility stats,
  IV-neutral and vol-neutral sizing ratios, an exposure overlap visualization,
  and a 12-month rebased performance chart with an interactive crosshair.
- **Upcoming earnings feed** — chronological cards for the next 1/2/4/8 weeks,
  each showing mkt cap, forward P/E, EPS YoY growth, and the last four
  earnings reactions inline.
- **Focal ticker overlay** — pick a ticker and the heatmap highlights its
  subsector column and dots the cells where that ticker has a theme score
  above 40 (strong dot above 70).

## Tech stack

| Layer | Tool |
|---|---|
| Backend | FastAPI, Uvicorn |
| Database | SQLite (`backend/db/dashboard.db`, committed to the repo) |
| Frontend | Alpine.js + Tailwind CSS via CDN — no build step |
| Charts | Inline SVG (no chart library dependency) |
| Data ingestion | `yfinance`, `finnhub-python`, `lxml` (for earnings dates) |
| Deploy | Render (free tier) |

No Webpack, no React, no npm, no Docker. The whole frontend is three
self-contained HTML files served by FastAPI.

---

## Quickstart (local)

```bash
git clone https://github.com/figoux/solana-capital-global-tech-equities.git
cd solana-capital-global-tech-equities

pip install -r requirements.txt

# The DB ships populated in the repo — no setup needed to view existing data
uvicorn backend.api.server:app --host 127.0.0.1 --port 8000

# Open http://127.0.0.1:8000
```

That's it. The dashboard works against the snapshot of `dashboard.db` in the
repo. No API keys, no env vars, no auth required for read-only viewing.

## Quickstart (deploy)

The included `render.yaml` is a Render Blueprint. Connect the repo to Render
and it provisions a free web service automatically.

```
https://dashboard.render.com → New + → Blueprint → connect this repo → Apply
```

Build takes ~5 minutes. After that, every `git push` triggers a redeploy in
~2 minutes.

If you want to gate your deployment behind HTTP Basic auth (e.g. for an
internal-only mirror), set `DASHBOARD_PASSWORD` as an env var on the service
— the server picks it up automatically and requires login. Leave it unset
for an open, public dashboard.

---

## Refreshing the data (ETL pipeline)

The ETL is a sequence of Python modules. Each can be run independently or as
part of the daily refresh script.

```bash
# 1. Universe & taxonomy (one-time or after CSV edits)
python -m backend.etl.universe                  # loads universe.csv → companies table
python -m backend.etl.business_exposures_seed   # taxonomy of 27 exposure buckets
python -m backend.etl.exposures_seed            # ticker → bucket weights
python -m backend.etl.themes_seed               # theme definitions
python -m backend.etl.theme_mapping_seed        # theme → bucket weights

# 2. Market data refresh (run daily)
python -m backend.etl.prices_yf                 # 2y of daily OHLCV
python -m backend.etl.fundamentals_yf           # multiples, EPS/revenue estimates
python -m backend.etl.vol_yf                    # realized & implied vol from options
python -m backend.etl.earnings_cal              # upcoming earnings via Finnhub + yfinance
python -m backend.etl.earnings_history_yf       # historical day-after reactions

# 3. Recompute derivatives
python -m backend.etl.pairs_compute             # cosine similarity matrix
```

`scripts/daily_update.ps1` runs the full sequence and commits the DB. We have
it scheduled at 07:00 daily via Windows Task Scheduler. A `cron` equivalent
on Linux is straightforward.

### Optional: Finnhub API key

`earnings_cal.py` uses Finnhub for forward-looking earnings calendar coverage
that yfinance misses. The free tier is sufficient.

```bash
cp .env.example .env
# Edit .env and set FINNHUB_API_KEY
```

Without a key, the script falls back to `yfinance.calendar` (works but covers
fewer names).

---

## Customizing for your own universe

The default universe is 130 global tech tickers (US, EU, Asia). To adapt to
your own coverage:

1. **Edit `universe.csv`** — one row per ticker. Required fields: `ticker`,
   `yahoo_ticker`, `name`, `subsector`, `country`, `currency`. Set
   `is_private=1` for unlisted names you want tagged but not fetched.

2. **Edit `backend/etl/exposures_seed.py`** — map each ticker to one or more
   business exposure buckets (weights sum to 100). The 27 buckets cover
   Consumer, Cloud/Data, Hardware/Semis, Fintech, and Frontier categories.
   Add new buckets in `business_exposures_seed.py` if your domain needs them.

3. **Edit `backend/etl/themes_seed.py`** — define investment themes and rate
   each `(theme × subsector)` cell from −2 (very bearish) to +2 (very bullish)
   with an optional markdown rationale.

4. **Re-run the seed scripts** in the order shown above, then `pairs_compute`
   to recompute the similarity matrix.

The dashboard reflects changes automatically on the next request.

---

## Project structure

```
.
├── backend/
│   ├── api/
│   │   └── server.py            # FastAPI app + all REST endpoints
│   ├── db/
│   │   ├── dashboard.db         # SQLite snapshot (committed)
│   │   └── schema.sql           # canonical schema
│   └── etl/                     # one module per pipeline stage
├── frontend/
│   ├── index.html               # dashboard home — heatmap + upcoming earnings
│   ├── company.html             # per-ticker drill-down
│   ├── pair.html                # pair workspace with 12m chart
│   └── theme.html               # theme drill-down with suggested basket
├── scripts/
│   ├── daily_update.ps1         # full ETL + git push (Windows)
│   ├── migrate.py               # idempotent schema migrations
│   └── db_info.py               # sanity-check counts and freshness
├── universe.csv                 # ticker universe (editable)
├── render.yaml                  # Render Blueprint
└── requirements.txt
```

---

## Methodology notes

**Cosine similarity for pairs.** Each ticker is a vector in 27-dimensional
exposure space (one dimension per business bucket, weight 0–100). Pair
similarity is the cosine of the angle between two such vectors. The matrix
is stored in `pairs_similarity` and the top-N peers per ticker are surfaced
in the UI. Values above 0.7 usually mean "trades as a pair," below 0.4 means
"different businesses despite shared subsector."

**Theme scores.** A `(ticker × theme)` score is the weighted sum of the
ticker's exposure weights times the theme's bucket weights, normalized to
0–100. A manual `direction_override` can pin a ticker's direction (long/short)
inside a theme regardless of its subsector-level bullishness rating.

**Day-after reactions.** For each historical earnings date, the reaction
is `close_after / close_before − 1`, where the choice of `before`/`after`
depends on whether the company reports BMO (before market open) or AMC
(after market close). When the timing is unknown, the fallback compares
`close[D+1]` to `close[D−1]` which captures the event either way.

**IV / RV / skew.** Implied vol is the median of ATM puts/calls in the
nearest two expiries weighted to 30-day and 60-day buckets. Skew is the
spread between the 25-delta put IV and the 25-delta call IV. Realized
vol is the annualized close-to-close standard deviation over the trailing
30 and 60 sessions.

---

## Limitations & known gaps

- SQLite single-file storage is fine for read-heavy single-process workloads,
  not for concurrent writes. Don't run the ETL while uvicorn is hot.
- yfinance options chains are unreliable for some non-US listings (notably
  Taiwan and Hong Kong). Those tickers show RV but no IV/skew.
- The free Render tier spins down after 15 minutes of inactivity. First
  request after spin-down takes ~30 seconds. Upgrade tier to keep warm.
- Earnings history depth depends on `yfinance.get_earnings_dates()`, which
  typically returns 4–8 past quarters. Recently-IPO'd names will have shorter
  histories.

---

## Contributing

PRs welcome, especially:

- **New universe entries** with reasoned exposure splits
- **New themes** with subsector ratings and rationale
- **Frontend additions** that respect the "no build step" constraint
- **ETL connectors** for non-yfinance data sources (Polygon, Refinitiv, etc.)

Please open an issue first for anything that changes the schema or the API
surface.

---

## License

MIT — see [LICENSE](./LICENSE).
