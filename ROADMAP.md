# Roadmap

Status snapshot and intended direction for the dashboard. Items marked
`done` ship in the current `main`.

## Shipped

- **Universe & taxonomy** — 130 tickers across 10 subsectors, 27 business
  exposure buckets, idempotent seed scripts (`done`)
- **ETL pipeline** — yfinance for prices/multiples/estimates/vol, Finnhub
  for forward earnings calendar, scheduled daily on Windows Task Scheduler
  at 07:00 (`done`)
- **Thematic heatmap** — `theme × subsector` bullishness matrix with
  markdown rationale, focal ticker overlay highlighting subsector column
  and dotted cells where the ticker has high exposure (`done`)
- **Per-company drill-down** — valuation snapshot (P/E TTM & forward, P/B,
  P/S, PEG, EPS/revenue growth), consensus estimates, next earnings event,
  business exposures by category, historical day-after reactions, IV/RV
  panel (`done`)
- **Pair workspace** — cosine similarity, side-by-side stats, IV/vol-neutral
  sizing ratios, exposure overlap visualization, 12-month rebased
  performance chart with interactive crosshair (`done`)
- **Upcoming earnings feed** — chronological cards with mkt cap, forward
  P/E, EPS YoY, and inline last-4-quarter reactions, configurable 1/2/4/8w
  window (`done`)
- **Ticker overlay on heatmap** — focal ticker dotting cells where
  `ticker × theme score ≥ 40` with stronger dots above 70 (`done`)

## Next up

- **Editable subsector bullishness from the UI** — a tab to adjust
  `theme_subsector_bullishness` ratings without touching seed files,
  persisted directly to SQLite. Today this requires editing
  `themes_seed.py` and re-running the seed.
- **Sector rotation view** — monthly snapshots of bullishness ratings,
  visualized as a small-multiples timeline to show how the
  `theme × subsector` map has moved over recent months.
- **Pair P&L backtester** — given a chosen `(long, short)` pair and a
  date range, compute the realized P&L of a dollar-neutral or vol-neutral
  position and benchmark against the underlying single legs.
- **Catalyst calendar** — distinct from earnings events: investor days,
  major conferences (NVIDIA GTC, Apple WWDC), regulatory deadlines,
  product launches. Single-source-of-truth doc with cross-references
  from per-company pages.
- **Migration of ETL to GitHub Actions** — remove the dependency on a
  specific laptop. Free tier runners suffice for the daily refresh
  (~3 minutes runtime per pipeline stage).

## Open design questions

- **Direction overrides** — today these are stored per `(ticker × theme)`
  in `theme_ticker_exposure.direction_override`. Should there also be a
  global "max conviction" flag separate from binary long/short, to
  emphasize the strongest views in basket sizing?
- **Multi-currency normalization** — multiples and growth rates are
  reported in each ticker's native currency. For cross-currency comparison
  (e.g. USD vs JPY EPS growth), should the dashboard normalize, or leave
  it to the analyst?
- **History depth** — `yfinance.get_earnings_dates()` is shallow
  (typically 4–8 quarters). For longer history we'd need a paid data
  provider or a custom scraper of company IR pages. The cost/benefit
  isn't obvious.

## Known limitations

- SQLite single-writer constraint blocks concurrent ETL + uvicorn in dev.
  Acceptable today because the laptop is the single writer and the Render
  process is read-only.
- yfinance options chains are thin or missing for non-US listings,
  especially Taiwan (`2454.TW`) and some Hong Kong tickers. Those rows
  have realized vol but no implied vol/skew.
- Render free tier spins down after 15 minutes of inactivity; first
  request takes ~30 seconds to wake up. Upgrade tier removes this.
