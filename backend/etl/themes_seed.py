"""
Seed dos 23 temas + matriz inicial de bullishness (tema × subsector).

Rode UMA vez (idempotente). Valores iniciais são um rascunho — você edita pela UI depois.

Escala:
   2 = dark green (muito bullish)
   1 = light green (bullish)
   0 = neutro / sem exposição
  -1 = light red (bearish)
  -2 = dark red (muito bearish)
"""
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

SUBSECTORS = [
    "Semis", "SaaS", "Internet", "OEMs", "WFEs", "Cloud/Data",
    "Cybersecurity", "Financial Services", "Networking", "Robotics",
    "Space",  # added 2026-07-23 (SPCX)
]

# (theme_id, name, short_desc, category, sort_order)
THEMES = [
    # AI Infra
    ("gpu_vs_asic",       "GPU vs ASIC",                    "Custom silicon eats merchant GPU share",  "AI Infra", 10),
    ("memory_wall",        "Memory Wall",                    "HBM/CXL/DRAM supply tightness in AI",     "AI Infra", 15),
    ("capex_hyperscalers", "Capex Hyperscalers",             "AWS/Azure/GCP/Meta capex trajectory",     "AI Infra", 20),
    ("mega_dc_deals",      "Mega Datacenter Deals",          "Multi-GW deals (Stargate, Oracle DC)",    "AI Infra", 25),
    ("cloud_dominance",    "Cloud Dominance",                "Share shifts AWS/Azure/GCP/Oracle",       "AI Infra", 30),
    ("roi_ai_capex",       "ROI on AI Capex",                "Will hyperscaler AI capex pay back?",     "AI Infra", 35),
    ("cpo_optics",         "CPO & Optics",                   "Co-packaged optics, 1.6T+ transceivers",  "AI Infra", 40),
    ("cpu_demand",         "CPU Demand",                     "Server CPU refresh + share x86 vs Arm",   "AI Infra", 45),
    # AI Apps
    ("basket_openai",      "Basket OpenAI",                  "Names with deepest OpenAI exposure",      "AI Apps",  50),
    ("chip_to_app",        "Chip → App",                     "Value migration downstream from silicon",  "AI Apps",  55),
    ("vibe_coding",        "Vibe Coding",                    "AI coding copilots / IDE disruption",      "AI Apps",  60),
    ("llm_leaderboard",    "LLM Leaderboard",                "Frontier model ranking shifts",           "AI Apps",  65),
    ("agentic_inference",  "Agentic Inference",              "Long-context agents driving token vol",   "AI Apps",  70),
    ("chinese_llms",       "Chinese LLMs",                   "DeepSeek/Qwen/Kimi ecosystem strength",   "AI Apps",  75),
    # Structural
    ("saas_is_dead",       "SaaS is Dead",                   "AI-native replaces seat-based SaaS",      "Structural", 80),
    ("oems_margin",        "OEMs Margin Squeeze",            "PC/server OEMs margin under AI boom",     "Structural", 85),
    ("humanoides",         "Humanoides",                     "Humanoid robot supply chain",             "Structural", 90),
    ("autonomous_vehicles","Autonomous Vehicles",            "Robotaxi/AV stack progress",              "Structural", 95),
    # Consumer
    ("gaming",             "Gaming",                         "Console cycle + gaming engagement",       "Consumer",   100),
    # Macro / Financial
    ("liquidez_ipos",      "Liquidez / IPOs",                "IPO window + secondary issuance",         "Macro",      110),
    ("prediction_markets", "Prediction Markets",             "Polymarket/Kalshi + adjacencies",         "Macro",      115),
    ("stablecoins",        "Stablecoins",                    "USDC/USDT/Tether rails, payments",         "Macro",      120),
    ("private_credit",     "Private Credit Bubble",          "Risk of direct lending unwind",           "Macro",      125),
]

# Matriz inicial (theme_id, subsector) -> bullishness (-2..2)
# Rascunho: positivo onde o subsector ganha com o tema, negativo onde perde, 0 onde é neutro.
BULL = {
    "gpu_vs_asic": {
        "Semis": 1, "SaaS": 0, "Internet": 1, "OEMs": -1, "WFEs": 1,
        "Cloud/Data": 1, "Cybersecurity": 0, "Financial Services": 0, "Networking": 1, "Robotics": 0,
    },
    "memory_wall": {
        "Semis": 2, "WFEs": 2, "Cloud/Data": 1, "OEMs": -1, "Networking": 1,
        "SaaS": 0, "Internet": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "capex_hyperscalers": {
        "Semis": 2, "WFEs": 2, "Networking": 2, "Cloud/Data": 2, "OEMs": 1,
        "Robotics": 1, "SaaS": 0, "Internet": 1, "Cybersecurity": 1, "Financial Services": 0,
    },
    "mega_dc_deals": {
        "Semis": 2, "Networking": 2, "Cloud/Data": 2, "WFEs": 1, "OEMs": 1,
        "SaaS": 0, "Internet": 1, "Cybersecurity": 1, "Financial Services": 0, "Robotics": 0,
    },
    "cloud_dominance": {
        "Cloud/Data": 2, "SaaS": 1, "Internet": 1, "Networking": 1, "Cybersecurity": 1,
        "Semis": 1, "WFEs": 0, "OEMs": -1, "Financial Services": 0, "Robotics": 0,
    },
    "roi_ai_capex": {
        "Semis": -1, "Networking": -1, "Cloud/Data": -1, "WFEs": -1, "OEMs": 0,
        "SaaS": 0, "Internet": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "cpo_optics": {
        "Networking": 2, "Semis": 1, "Cloud/Data": 1, "WFEs": 0, "OEMs": 0,
        "SaaS": 0, "Internet": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "cpu_demand": {
        "Semis": 1, "OEMs": 1, "Cloud/Data": 1, "WFEs": 0, "Networking": 0,
        "SaaS": 0, "Internet": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "basket_openai": {
        "Semis": 2, "Cloud/Data": 2, "SaaS": 1, "OEMs": 1, "Internet": 1,
        "Networking": 1, "WFEs": 1, "Cybersecurity": 0, "Financial Services": 1, "Robotics": 0,
    },
    "chip_to_app": {
        "SaaS": 1, "Internet": 1, "Cloud/Data": 1, "Semis": -1, "OEMs": -1,
        "Networking": 0, "WFEs": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "vibe_coding": {
        "SaaS": 2, "Internet": 1, "Cloud/Data": 1, "Cybersecurity": 0, "OEMs": 0,
        "Semis": 0, "WFEs": 0, "Networking": 0, "Financial Services": 0, "Robotics": 0,
    },
    "llm_leaderboard": {
        "SaaS": 1, "Internet": 1, "Cloud/Data": 1, "Semis": 1, "Cybersecurity": 0,
        "OEMs": 0, "WFEs": 0, "Networking": 0, "Financial Services": 0, "Robotics": 0,
    },
    "agentic_inference": {
        "Semis": 2, "Cloud/Data": 2, "Networking": 1, "SaaS": 1, "Internet": 1,
        "OEMs": 0, "WFEs": 1, "Cybersecurity": 1, "Financial Services": 0, "Robotics": 0,
    },
    "chinese_llms": {
        "Internet": 2, "SaaS": 1, "Semis": 1, "Cloud/Data": 1, "OEMs": 0,
        "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 1,
    },
    "saas_is_dead": {
        "SaaS": -2, "Internet": 1, "Cloud/Data": 1, "Semis": 0, "OEMs": 0,
        "WFEs": 0, "Networking": 0, "Cybersecurity": -1, "Financial Services": 0, "Robotics": 0,
    },
    "oems_margin": {
        "OEMs": -2, "Semis": 0, "Cloud/Data": 0, "SaaS": 0, "Internet": 0,
        "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "humanoides": {
        "Robotics": 2, "Semis": 1, "OEMs": 0, "Cloud/Data": 0, "SaaS": 0,
        "Internet": 0, "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Financial Services": 0,
    },
    "autonomous_vehicles": {
        "Robotics": 2, "Semis": 1, "Internet": 1, "OEMs": -1, "SaaS": 0,
        "Cloud/Data": 0, "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Financial Services": 0,
    },
    "gaming": {
        "Internet": 1, "Semis": 1, "OEMs": 0, "SaaS": 0, "Cloud/Data": 0,
        "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Financial Services": 0, "Robotics": 0,
    },
    "liquidez_ipos": {
        "Financial Services": 2, "Internet": 1, "SaaS": 1, "Semis": 0, "OEMs": 0,
        "Cloud/Data": 0, "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Robotics": 0,
    },
    "prediction_markets": {
        "Financial Services": 1, "Internet": 1, "SaaS": 0, "Cloud/Data": 0, "OEMs": 0,
        "Semis": 0, "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Robotics": 0,
    },
    "stablecoins": {
        "Financial Services": 2, "Internet": 1, "SaaS": 0, "Cloud/Data": 0, "Cybersecurity": 1,
        "OEMs": 0, "Semis": 0, "WFEs": 0, "Networking": 0, "Robotics": 0,
    },
    "private_credit": {
        "Financial Services": -1, "Internet": 0, "SaaS": 0, "Cloud/Data": 0, "OEMs": 0,
        "Semis": 0, "WFEs": 0, "Networking": 0, "Cybersecurity": 0, "Robotics": 0,
    },
}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Insert themes
    for t_id, name, short_desc, category, sort_order in THEMES:
        cur.execute(
            """
            INSERT INTO themes (theme_id, name, short_desc, category, sort_order, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(theme_id) DO UPDATE SET
              name=excluded.name, short_desc=excluded.short_desc,
              category=excluded.category, sort_order=excluded.sort_order
            """,
            (t_id, name, short_desc, category, sort_order),
        )

    # 2. Bullishness matrix
    n_cells = 0
    for t_id, row in BULL.items():
        for sub, b in row.items():
            assert sub in SUBSECTORS, f"subsector inválido: {sub}"
            cur.execute(
                """
                INSERT INTO theme_subsector_bullishness (theme_id, subsector, bullishness, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(theme_id, subsector) DO UPDATE SET
                  bullishness=excluded.bullishness, updated_at=CURRENT_TIMESTAMP
                """,
                (t_id, sub, b),
            )
            n_cells += 1

    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, finished_at, status, rows_upserted, message) "
        "VALUES (?, ?, ?, 'ok', ?, ?)",
        (
            "themes_seed",
            datetime.now().isoformat(timespec="seconds"),
            datetime.now().isoformat(timespec="seconds"),
            len(THEMES) + n_cells,
            f"themes={len(THEMES)} bullishness_cells={n_cells}",
        ),
    )
    conn.commit()

    # Report
    n_themes = cur.execute("SELECT COUNT(*) FROM themes").fetchone()[0]
    print(f"[themes_seed] themes={n_themes} | bullishness_cells={n_cells}")
    print("\nResumo por categoria:")
    for cat, c in cur.execute(
        "SELECT category, COUNT(*) FROM themes GROUP BY category ORDER BY MIN(sort_order)"
    ).fetchall():
        print(f"  {cat:12s} {c}")

    # Top 5 mais positivos por tema (linha mais verde)
    print("\nTop green rows (max bullishness por tema, amostra 5):")
    for t_id, maxb in cur.execute(
        "SELECT theme_id, MAX(bullishness) FROM theme_subsector_bullishness GROUP BY theme_id ORDER BY MAX(bullishness) DESC LIMIT 5"
    ).fetchall():
        subs = cur.execute(
            "SELECT subsector FROM theme_subsector_bullishness WHERE theme_id=? AND bullishness=?",
            (t_id, maxb),
        ).fetchall()
        print(f"  {t_id:22s} (+{maxb}) → {', '.join(s[0] for s in subs)}")

    conn.close()


if __name__ == "__main__":
    main()
