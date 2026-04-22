-- ================================================================
-- Solana Global Tech — SQLite schema
-- Created: 2026-04-22
-- One-file DB at backend/db/dashboard.db
-- ================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------- Core reference ----------

CREATE TABLE IF NOT EXISTS companies (
  ticker             TEXT PRIMARY KEY,          -- our canonical ticker (usually US-listed if ADR exists)
  yahoo_ticker       TEXT,                      -- what yfinance needs (e.g. 005930.KS, 1810.HK); NULL for privates
  finnhub_ticker     TEXT,                      -- Finnhub symbol; may differ for non-US
  name               TEXT NOT NULL,
  subsector          TEXT NOT NULL,             -- 'Semis','SaaS','Internet','OEMs','WFEs','Cloud/Data','Cybersecurity','Financial Services','Networking','Robotics'
  country            TEXT,
  currency           TEXT,                      -- reporting currency (USD, EUR, JPY, ...)
  primary_exchange   TEXT,
  fiscal_year_end    TEXT,                      -- 'Dec','Mar','Jun','Sep','Jan'
  is_private         INTEGER DEFAULT 0,         -- 1 = private company, skip price/estimates ETL
  active             INTEGER DEFAULT 1,         -- soft delete flag
  mkt_cap_rank_hint  INTEGER,                   -- rough ordering when universe was defined
  created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Price / multiples snapshot ----------

CREATE TABLE IF NOT EXISTS prices (
  ticker     TEXT NOT NULL,
  date       TEXT NOT NULL,                     -- YYYY-MM-DD trading day
  open       REAL, high REAL, low REAL, close REAL, adj_close REAL,
  volume     INTEGER,
  PRIMARY KEY (ticker, date),
  FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

CREATE TABLE IF NOT EXISTS multiples (
  ticker           TEXT NOT NULL,
  as_of_date       TEXT NOT NULL,
  mkt_cap_usd      REAL,
  ev_usd           REAL,
  fwd_pe_ntm       REAL,                        -- next 12 months consensus
  fwd_pe_fy1       REAL,
  fwd_pe_fy2       REAL,
  pe_ttm           REAL,
  ev_ebitda_ntm    REAL,
  ps_ntm           REAL,
  eps_growth_ntm   REAL,                        -- NTM vs TTM %
  eps_growth_fy1   REAL,
  eps_growth_fy2   REAL,
  rev_growth_ntm   REAL,
  rev_growth_fy1   REAL,
  rev_growth_fy2   REAL,
  peg_ntm          REAL,
  dividend_yield   REAL,
  PRIMARY KEY (ticker, as_of_date),
  FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- ---------- Consensus estimates (snapshot, one row per fiscal period per pull) ----------

CREATE TABLE IF NOT EXISTS estimates (
  ticker           TEXT NOT NULL,
  fiscal_period    TEXT NOT NULL,               -- e.g. '2026Q2', 'FY2026', 'FY2027'
  period_type      TEXT NOT NULL CHECK (period_type IN ('quarter','annual')),
  eps_mean         REAL,
  eps_low          REAL,
  eps_high         REAL,
  eps_count        INTEGER,
  revenue_mean     REAL,                        -- in reporting currency, in units of 1 (not millions)
  revenue_low      REAL,
  revenue_high     REAL,
  revenue_count    INTEGER,
  ebitda_mean      REAL,
  currency         TEXT,
  as_of_date       TEXT NOT NULL,
  source           TEXT NOT NULL,               -- 'finnhub','yfinance','manual'
  PRIMARY KEY (ticker, fiscal_period, as_of_date, source),
  FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- ---------- Earnings events (one row per reported/upcoming quarter) ----------

CREATE TABLE IF NOT EXISTS earnings_events (
  ticker            TEXT NOT NULL,
  fiscal_period     TEXT NOT NULL,              -- e.g. '2026Q1'
  report_date       TEXT,                       -- YYYY-MM-DD, may be NULL if unscheduled
  report_time       TEXT,                       -- 'bmo','amc','unknown'
  status            TEXT DEFAULT 'upcoming',    -- 'upcoming','reported','delayed','preannounced'
  eps_est           REAL,
  eps_actual        REAL,
  eps_surprise_pct  REAL,
  rev_est           REAL,
  rev_actual        REAL,
  rev_surprise_pct  REAL,
  currency          TEXT,
  press_release_url TEXT,
  transcript_url    TEXT,
  summary_md        TEXT,                       -- Claude-written earnings recap, editable
  PRIMARY KEY (ticker, fiscal_period),
  FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- ---------- Forward guidance (flexible; one row per metric per issuance) ----------

CREATE TABLE IF NOT EXISTS guidance (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker            TEXT NOT NULL,
  issued_date       TEXT NOT NULL,              -- when guidance was given
  target_period     TEXT NOT NULL,              -- '2026Q2','FY2026'
  metric            TEXT NOT NULL,              -- 'revenue','eps','gross_margin','operating_margin','capex','opex','fcf','other'
  value_low         REAL,
  value_high        REAL,
  value_point       REAL,                       -- NULL if range; filled if single point
  unit              TEXT,                       -- 'USD_millions','USD','pct','count'
  direction         TEXT,                       -- 'raise','maintain','lower','initiate','withdraw'
  vs_consensus      TEXT,                       -- 'above','inline','below', free text ok
  commentary_md     TEXT,
  source_url        TEXT,
  source_type       TEXT,                       -- 'press_release','transcript','8-K','investor_day','manual'
  FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- ---------- Themes & bullishness matrix ----------

CREATE TABLE IF NOT EXISTS themes (
  theme_id         TEXT PRIMARY KEY,            -- slug like 'gpu_vs_asic'
  name             TEXT NOT NULL,
  short_desc       TEXT,
  long_thesis_md   TEXT,
  category         TEXT,                        -- 'AI Infra','AI Apps','Macro','Structural','Consumer'
  sort_order       INTEGER DEFAULT 100,
  active           INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS theme_subsector_bullishness (
  theme_id         TEXT NOT NULL,
  subsector        TEXT NOT NULL,
  bullishness      INTEGER NOT NULL,            -- -2 dark red, -1 light red, 0 neutral/white, 1 light green, 2 dark green
  rationale_md     TEXT,
  updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (theme_id, subsector),
  FOREIGN KEY (theme_id) REFERENCES themes(theme_id)
);

CREATE TABLE IF NOT EXISTS theme_ticker_exposure (
  theme_id         TEXT NOT NULL,
  ticker           TEXT NOT NULL,
  exposure         INTEGER NOT NULL,            -- 0 none, 1 low, 2 medium, 3 high
  direction        TEXT DEFAULT 'long',         -- 'long','short','neutral'
  rationale_md     TEXT,
  updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (theme_id, ticker),
  FOREIGN KEY (theme_id) REFERENCES themes(theme_id),
  FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- ---------- Catalysts & notes (the editable-via-UI part) ----------

CREATE TABLE IF NOT EXISTS catalysts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_type       TEXT NOT NULL CHECK (scope_type IN ('ticker','theme','subsector','global')),
  scope_value      TEXT NOT NULL,               -- ticker, theme_id, subsector name, or 'ALL'
  event_date       TEXT,                        -- YYYY-MM-DD, NULL for ongoing
  title            TEXT NOT NULL,
  body_md          TEXT,
  importance       INTEGER DEFAULT 2,           -- 1 low, 2 med, 3 high
  direction        TEXT,                        -- 'bullish','bearish','neutral'
  pinned           INTEGER DEFAULT 0,
  resolved         INTEGER DEFAULT 0,           -- 1 = past event, locked
  created_by       TEXT DEFAULT 'claude',
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_type       TEXT NOT NULL,
  scope_value      TEXT NOT NULL,
  body_md          TEXT NOT NULL,
  tag              TEXT,                        -- 'thesis','risk','sentiment','model','to_watch'
  created_by       TEXT DEFAULT 'filipe',
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Business exposures (for correlation/pairs trading) ----------

CREATE TABLE IF NOT EXISTS business_exposures (
  exposure_id   TEXT PRIMARY KEY,        -- slug: 'ecommerce','cloud_iaas_paas',...
  name          TEXT NOT NULL,
  description   TEXT,
  category      TEXT,                    -- 'Consumer','Cloud/Data','Hardware/Semis','Fintech','Frontier','Other'
  sort_order    INTEGER DEFAULT 100,
  active        INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ticker_exposure (
  ticker        TEXT NOT NULL,
  exposure_id   TEXT NOT NULL,
  weight_pct    REAL NOT NULL,           -- 0-100, sum per ticker should be ~100
  source        TEXT,                    -- 'claude_reasoning','10k_segment','analyst_sotp','manual'
  rationale_md  TEXT,
  locked        INTEGER DEFAULT 0,       -- 1 = don't overwrite on re-run
  as_of_date    TEXT DEFAULT (DATE('now')),
  updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, exposure_id),
  FOREIGN KEY (ticker) REFERENCES companies(ticker),
  FOREIGN KEY (exposure_id) REFERENCES business_exposures(exposure_id)
);

-- ---------- Volatility (realized + implied, for pairs view) ----------

CREATE TABLE IF NOT EXISTS volatility (
  ticker        TEXT NOT NULL,
  as_of_date    TEXT NOT NULL,
  rv_30d        REAL,                    -- annualized realized vol, close-to-close, last 30 trading days
  rv_60d        REAL,
  rv_90d        REAL,
  iv_30d_atm    REAL,                    -- ATM IV at ~30d expiry; NULL where options chain unavailable
  iv_60d_atm    REAL,
  iv_90d_atm    REAL,
  iv_skew_25d   REAL,                    -- 25-delta put IV minus 25-delta call IV
  beta_60d      REAL,                    -- vs subsector proxy ETF (SMH for Semis, IGV for SaaS, etc)
  source        TEXT,                    -- 'yfinance','bloomberg','manual'
  locked        INTEGER DEFAULT 0,       -- 1 = auto-fetch will NOT overwrite (for Bloomberg-pasted data)
  PRIMARY KEY (ticker, as_of_date)
);

-- ---------- Pairs suggestion cache (optional, computed) ----------

CREATE TABLE IF NOT EXISTS pairs_similarity (
  ticker_a      TEXT NOT NULL,
  ticker_b      TEXT NOT NULL,
  cosine_sim    REAL NOT NULL,           -- 0-1, exposure-vector cosine similarity
  shared_exposure_top TEXT,              -- e.g. 'ecommerce: 52 vs 100'
  as_of_date    TEXT DEFAULT (DATE('now')),
  PRIMARY KEY (ticker_a, ticker_b)
);

-- ---------- ETL run log ----------

CREATE TABLE IF NOT EXISTS etl_runs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  job_name       TEXT NOT NULL,                 -- 'prices','estimates','earnings_cal',...
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  status         TEXT,                          -- 'ok','partial','failed'
  rows_upserted  INTEGER,
  message        TEXT
);

-- ---------- Indexes ----------

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date      ON prices(ticker, date DESC);
CREATE INDEX IF NOT EXISTS idx_multiples_date          ON multiples(as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_report_date    ON earnings_events(report_date);
CREATE INDEX IF NOT EXISTS idx_earnings_status         ON earnings_events(status);
CREATE INDEX IF NOT EXISTS idx_guidance_ticker         ON guidance(ticker, issued_date DESC);
CREATE INDEX IF NOT EXISTS idx_catalysts_scope         ON catalysts(scope_type, scope_value, event_date);
CREATE INDEX IF NOT EXISTS idx_notes_scope             ON notes(scope_type, scope_value, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_companies_subsector     ON companies(subsector);
CREATE INDEX IF NOT EXISTS idx_estimates_period        ON estimates(ticker, fiscal_period, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_exposure_ticker         ON ticker_exposure(ticker);
CREATE INDEX IF NOT EXISTS idx_exposure_category       ON business_exposures(category, sort_order);
CREATE INDEX IF NOT EXISTS idx_volatility_date         ON volatility(as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_pairs_cosine            ON pairs_similarity(cosine_sim DESC);
