# Contributing

Thanks for considering a contribution. This repo is research code maintained
by one person, so a few light conventions help.

## Before opening a PR

- For **anything that changes the schema** (`backend/db/schema.sql` or any
  `scripts/migrate.py` change) or the **API surface** (`backend/api/server.py`
  endpoints), open an issue first to discuss the design. Schema migrations
  are easy to get wrong and hard to undo.
- For **universe edits, exposure rebalances, or theme rating tweaks**, just
  open the PR. Include a one-line rationale in the commit message or PR
  description — these changes are research opinions, and the reasoning
  matters more than the diff.
- For **frontend changes**, keep the "no build step" constraint. Alpine.js
  + Tailwind via CDN. No Webpack, no React, no npm.

## Running the test loop

There is no test suite yet — coverage is something a contributor could
meaningfully help with. The current verification loop is:

```bash
# Schema sanity
python scripts/migrate.py

# Reseed (idempotent — safe to re-run)
python -m backend.etl.universe
python -m backend.etl.business_exposures_seed
python -m backend.etl.exposures_seed
python -m backend.etl.themes_seed
python -m backend.etl.theme_mapping_seed

# Recompute derivatives
python -m backend.etl.pairs_compute

# Start server, hit /health
uvicorn backend.api.server:app --port 8000 &
curl http://127.0.0.1:8000/health
```

If `pairs_compute` produces a matrix of the expected size and the API
returns `{"status": "ok"}`, the change is unlikely to have broken anything
structural.

## Style

- Python: PEP 8, type hints where they aid readability, no enforced linter
  yet. Docstrings on every ETL module's `main()`.
- HTML/JS: 2-space indent. Alpine `x-data` blocks live in a `<script>` tag
  at the bottom of each page (no separate JS files for now).
- Commit messages: imperative mood, scoped. Good: `feat: add 12m chart on
  pair page`. Bad: `Updated stuff`.

## What's especially welcome

- **New universe entries** with reasoned exposure splits — name, country,
  subsector classification, and 1–2 sentences on the business mix.
- **New themes** with subsector ratings (−2..+2) and per-cell markdown
  rationale.
- **ETL connectors** for non-yfinance data sources (Polygon, EOD Historical
  Data, Refinitiv, IEX Cloud). yfinance's options coverage is the weakest
  link today.
- **Tests** — `pytest` smoke tests for each ETL module would significantly
  raise confidence in PRs that touch the pipeline.
- **i18n / English translations** of the in-repo docs that are still in
  Portuguese (notably `BUSINESS_EXPOSURES.md`).
