# Solana Global Tech — Plano de Construção

**Versão:** 2026-04-22
**Owner:** Filipe
**Objetivo:** Dashboard interno privado de earnings/theses/catalysts para ~150 tech stocks globais, inspirado no earnings season do BTG mas mais analítico, com forward guidance destacado e heatmap editável de temas × subsetores.

---

## 1. Arquitetura

```
Solana Global Tech/
├── backend/
│   ├── db/
│   │   ├── schema.sql              ← pronto
│   │   └── dashboard.db            ← criado no 1º run
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── universe.py             ← carrega universe_draft.csv em companies
│   │   ├── prices_yf.py            ← yfinance OHLCV diário
│   │   ├── fundamentals_yf.py      ← fwd P/E, EPS growth, mkt cap via yfinance
│   │   ├── earnings_cal_fh.py      ← Finnhub earnings calendar + estimates
│   │   ├── earnings_actuals_fh.py  ← beat/miss após report
│   │   └── themes_seed.py          ← popula 23 temas + heatmap inicial
│   ├── parsers/
│   │   └── guidance_llm.py         ← Claude parseia PRs/transcripts em guidance estruturado
│   ├── api/
│   │   └── server.py               ← FastAPI: /api/heatmap, /api/earnings, /api/company/{t}...
│   └── jobs/
│       └── daily_update.py         ← chama todos ETLs em ordem
├── frontend/
│   ├── index.html                  ← heatmap + earnings week
│   ├── company.html                ← detalhe ticker (card JPM-like + fwd guidance)
│   ├── theme.html                  ← detalhe do tema com lista de stocks expostas
│   └── assets/
│       ├── app.js                  ← Alpine.js components
│       ├── styles.css              ← complementa Tailwind CDN
│       └── heatmap.js
├── notes/                          ← markdown livre, versionado em git
│   ├── companies/NVDA.md
│   └── themes/gpu_vs_asic.md
├── universe_draft.csv              ← 150 tickers rascunhados — EDITAR ANTES DE RODAR
├── requirements.txt
├── Dockerfile                      ← para deploy no servidor Solana
├── Makefile
└── .env.example                    ← FINNHUB_API_KEY, PORT
```

---

## 2. Universo (travado 2026-04-22)

Arquivo autoritativo: **`universe.csv`** (124 tickers, consolidado a partir da edição do Filipe + 4 novos nomes classificados).

| Subsetor | Qtd |
|---|---|
| Semis | 21 (inclui `688256.SS` Cambricon) |
| Internet | 21 |
| SaaS | 19 (inclui `MINIMAX_PVT` privada) |
| Robotics | 12 (inclui `UNITREE_PVT` privada) |
| OEMs | 11 |
| Networking | 10 |
| Cloud/Data | 9 (inclui `BE` Bloom Energy) |
| Financial Services | 9 |
| Cybersecurity | 7 |
| WFEs | 5 |
| **TOTAL** | **124** (122 públicas + 2 privadas em watchlist) |

**Tratamento de privadas:** `Unitree` e `MiniMax` têm `is_private=1` → entram em `companies`, `themes`, `ticker_exposure`, mas são puladas por `prices_yf`, `estimates`, `earnings`. Servem como sinal de leitura setorial.

---

## 3. Fontes de Dados

| Fonte | O que usar | Cobertura | Custo |
|---|---|---|---|
| **yfinance** (lib Python) | Preços OHLCV, fwd P/E, EPS growth estimates, mkt cap, analyst targets, earnings dates | Global (Yahoo tickers) | Grátis, sem API key |
| **Finnhub** free tier | Earnings calendar estruturado, consensus EPS/Rev por quarter, earnings surprises históricos, company profile | Boa p/ US; parcial p/ global | Grátis — 60 req/min |
| **Claude (você e eu)** | Parsing de guidance em texto livre (PRs, transcripts, 8-Ks), tagging de catalysts, bullishness scores | Qualitativo | Já pago pelo Cowork |
| **SEC EDGAR** (depois) | 8-Ks com guidance de US companies | US only | Grátis |

**Nota sobre cobertura global:** Finnhub free tier é forte em US e OK em alguns internacionais. Para tickers asiáticos (.KS, .T, .HK, .TW) e europeus fora do ADR, vamos preferir yfinance como primário e cair para parsing manual de IR pages via Claude para guidance. Isso é aceitável porque a maioria do seu book de mega-caps asiáticas tem ADR (TSM, BABA, PDD, MELI, NU, NTES).

---

## 3-bis. Business Exposures (camada nova — para pairs trading)

**Veja [BUSINESS_EXPOSURES.md](./BUSINESS_EXPOSURES.md) para a taxonomia completa (25 buckets) e workflow.**

Resumo:
- Cada ticker é decomposto em pesos % sobre 25 exposures (`ecommerce`, `cloud_iaas_paas`, `digital_ads`, `semis_ai_compute`, `humanoid_robotics`, etc.)
- Soma ≈ 100 por ticker
- Vetor de exposures → cosine similarity → sugestões de pair com overlap de negócio
- Cruzar com `volatility.iv_30d_atm` → pair trade: long IV barata / short IV rica, mesma exposição

Tabelas novas no schema: `business_exposures`, `ticker_exposure`, `volatility`, `pairs_similarity`.

**Implied vol: de onde vem:**
- Primária: `yfinance` option chains (US stocks + ADRs) → calcula ATM IV 30/60/90d e 25-delta skew
- Fallback: realized vol (RV 30/60/90d) computada do histórico de preços — sempre disponível
- Para não-US nativos (.HK, .SS, .TW, .KS, .T, .AS, .DE): campo fica NULL, espera import
- **Integração Bloomberg:** campo `volatility.source='bloomberg'` + `locked=1`. Você exporta do BLP, manda via `/api/volatility/import` (CSV bulk) ou cola célula por célula na UI. O auto-fetch do yfinance respeita `locked=1` e não sobrescreve.

## 4. Temas (23 da sua matriz)

Mapeamento inicial de `theme_id` para categorias:

**AI Infra:** `gpu_vs_asic`, `memory_wall`, `capex_hyperscalers`, `mega_dc_deals`, `cloud_dominance`, `roi_ai_capex`, `cpo_optics`, `cpu_demand`
**AI Apps:** `basket_openai`, `chip_to_app`, `vibe_coding`, `llm_leaderboard`, `agentic_inference`, `chinese_llms`
**Structural:** `saas_is_dead`, `oems_margin`, `humanoides`, `autonomous_vehicles`
**Consumer:** `gaming`
**Macro/Financial:** `liquidez_ipos`, `prediction_markets`, `stablecoins`, `private_credit`

Vou gerar um `themes_seed.sql` pré-populando a matriz `theme_subsector_bullishness` lendo as cores da sua imagem (verde escuro = 2, verde claro = 1, branco = 0). Você revisa e ajusta pela UI depois.

---

## 5. Roadmap de Implementação (faseado)

**Fase 0 — Setup (hoje):**
- [ ] Setup do ambiente: venv, dependências, API keys
- [ ] Criar SQLite + schema
- [ ] Carregar universo em `companies`
- [ ] Testar yfinance e Finnhub com 5 tickers

**Fase 1 — ETL core (2 dias):**
- [ ] `universe.py` carrega `universe.csv` em `companies`
- [ ] `prices_yf.py` + `fundamentals_yf.py`
- [ ] `earnings_cal_fh.py` + `earnings_actuals_fh.py`
- [ ] `themes_seed.py` (23 temas + matriz bullishness)
- [ ] `vol_yf.py` — RV 30/60/90d + IV ATM onde disponível
- [ ] `exposures_seed.py` — Claude reasoning batch para os 124 tickers
- [ ] `pairs_compute.py` — popula `pairs_similarity`
- [ ] `jobs/daily_update.py` encadeia tudo

**Fase 2 — Frontend MVP (2 dias):**
- [ ] FastAPI + endpoints `/api/heatmap`, `/api/earnings/week`, `/api/company/{t}`, `/api/pairs/{t}`
- [ ] `index.html` — heatmap temas × subsetores
- [ ] `company.html` — card JPM-like + consensus + fwd guidance + **pie de business exposures + tabela de pairs sugeridos com spread de IV**
- [ ] `theme.html` — lista de tickers expostos ao tema

**Fase 3 — Qualitativo editável (1–2 dias):**
- [ ] UI edita inline: `catalysts`, `notes`, `theme_ticker_exposure`, **`ticker_exposure` (pesos), `volatility` (colar IV do BBG)**
- [ ] Endpoint POST/PUT salva no SQLite
- [ ] Campo "locked" na UI (cadeado) — marca que é Bloomberg / manual e auto-fetch não sobrescreve
- [ ] Markdown rendering nos campos de notes

**Fase 4 — Parser de guidance (1–2 dias):**
- [ ] Script que pega últimos PRs + transcripts de empresas com earnings na semana
- [ ] Claude extrai guidance estruturado → `guidance` table
- [ ] Frontend mostra guidance do próximo quarter no card (destaque)

**Fase 5 — Deploy Solana (1 dia):**
- [ ] Dockerfile + docker-compose
- [ ] Tailscale ou VPN interna p/ acesso da equipe

**Fase 6 — Refinamento contínuo:**
- [ ] Endpoint `/api/volatility/import` para bulk upload de Bloomberg CSV
- [ ] Alertas quando guidance muda materialmente vs consensus
- [ ] Histórico de revisões de consensus
- [ ] Export de tear sheets PDF

---

## 6. Decisões travadas (2026-04-22)

| Decisão | Escolha |
|---|---|
| Consensus source | yfinance + Finnhub free + Claude parsing |
| Frontend stack | HTML + Alpine.js + Tailwind (CDN) |
| Hosting | localhost + Dockerfile p/ servidor interno Solana |
| Universo | 124 tickers (`universe.csv`), 2 privados em watchlist |
| DB | SQLite único arquivo |
| Linguagem ETL | Python 3.11+ |
| API server | FastAPI + uvicorn |
| Business exposures | 25 buckets, Claude reasoning initial, editável via UI |
| Implied vol | yfinance options (US/ADRs) + fallback RV; integração Bloomberg via CSV import + UI paste com `locked=1` |
| Granularidade exposures | 25 buckets (v1) |

---

## 7. O que falta decidir / perguntar (futuro)

- Nível de automação: scheduler diário (cron? APScheduler?) ou rodar manual com `make update`?
- Histórico de estimativas revisadas (snapshot diário vs só último)? → Schema já suporta via PK (ticker, period, as_of_date, source), decisão é só do cron.
- Como entra Bloomberg/FactSet se você tiver acesso no futuro? → schema já tem coluna `source` em `estimates`, plugar é trivial.
- Moeda: tudo em USD com conversion daily? ou manter reporting currency e converter só no frontend? → **Proposta:** guardar em reporting currency, converter p/ USD no frontend usando FX diário também do yfinance.
