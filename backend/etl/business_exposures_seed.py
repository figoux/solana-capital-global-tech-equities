"""
Seed dos 25 business exposure buckets (taxonomia para pairs trading).
Idempotente.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

# (exposure_id, name, description, category, sort_order)
BUCKETS = [
    # Consumer / Commerce (5)
    ("ecommerce",             "E-commerce",             "Marketplaces, DTC platforms, 1P+3P retail",         "Consumer",      10),
    ("digital_ads",           "Digital Ads",            "Search, social, display, video, CTV ad revenue",    "Consumer",      15),
    ("subscription_media",    "Subscription Media",     "Streaming, music, subs consumer services",          "Consumer",      20),
    ("travel_booking",        "Travel & Mobility",      "OTA, hospitality platforms, ride-hailing",          "Consumer",      25),
    ("gaming_content",        "Gaming Content",         "Game publishers, platforms, engines, esports",       "Consumer",      30),
    # Cloud / Software (5)
    ("cloud_iaas_paas",       "Cloud IaaS/PaaS",        "Public cloud infra (AWS, Azure, GCP, OCI, Alicloud)","Cloud/Data",    40),
    ("software_enterprise_saas","Enterprise SaaS",      "CRM, ERP, HCM, collaboration, vertical SaaS",       "Cloud/Data",    45),
    ("software_dev_tools",    "Developer Tools",        "IDEs, CI/CD, databases, devops, observability",     "Cloud/Data",    50),
    ("cybersecurity",         "Cybersecurity",          "Network, endpoint, identity, cloud security, SIEM",  "Cloud/Data",    55),
    ("software_ai_platform",  "AI Platform / Apps",     "ML platforms, agents, AI-native apps, LLM APIs",    "Cloud/Data",    60),
    # Hardware / Semis (9)
    ("semis_ai_compute",      "Semis — AI Compute",     "GPUs, AI ASICs, NPUs, accelerators",                "Hardware/Semis",70),
    ("semis_foundry",         "Semis — Foundry",        "Pure-play foundries (TSMC, UMC, GFS) + foundry arms (Intel IFS, Samsung Foundry)","Hardware/Semis",72),
    ("semis_general_compute", "Semis — General Compute","CPUs, MCUs, analog, power, RF, automotive SoCs",    "Hardware/Semis",75),
    ("semis_memory",          "Semis — Memory",         "DRAM, NAND, HBM, memory IP",                         "Hardware/Semis",80),
    ("semis_networking",      "Semis — Networking",     "Switches, DPUs, PHYs, optical components, CPO",      "Hardware/Semis",85),
    ("wfe_equipment",         "WFE Equipment",          "Litho, etch, dep, metrology, test equipment",        "Hardware/Semis",90),
    ("mobile_ecosystem",      "Mobile Ecosystem",       "Smartphone devices + mobile-specific SoCs/modems/RF/power — cross-market bucket (iPhone, Galaxy, Snapdragon, RF front-end)", "Hardware/Semis", 93),
    ("oem_consumer",          "OEM — Consumer (non-mobile)", "PCs, wearables, peripherals, AR/VR, TVs, home (smartphones vivem em mobile_ecosystem)", "Hardware/Semis", 95),
    ("oem_datacenter",        "OEM — Datacenter",       "Server OEMs, storage arrays, DC networking HW",      "Hardware/Semis",100),
    # Fintech / Payments (3)
    ("payments_processing",   "Payments Processing",    "Card networks, acquirers, PSPs",                     "Fintech",       110),
    ("fintech_consumer",      "Fintech Consumer",       "Neobanks, wealth, BNPL, P2P wallets",                "Fintech",       115),
    ("financial_infra",       "Financial Infra",        "Exchanges, custody, market data, clearing",          "Fintech",       120),
    # Frontier (4)
    ("robotics_industrial",   "Robotics — Industrial",  "Factory automation, cobots, medical robotics, AGV",  "Frontier",      130),
    ("robotics_humanoid",     "Robotics — Humanoid",    "Bipedal/quadruped general-purpose robots",           "Frontier",      135),
    ("autonomous_vehicles",   "Autonomous Vehicles",    "AV stack, robotaxi, trucking AV, EV SDV",            "Frontier",      140),
    ("crypto_stablecoins",    "Crypto & Stablecoins",   "Stablecoin infra, exchanges, on-chain rails",        "Frontier",      145),
    # Other (1)
    ("other",                 "Other / Residual",       "Catch-all residual (services, legacy, etc)",         "Other",         200),
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for exp_id, name, desc, cat, sort_order in BUCKETS:
        cur.execute(
            """
            INSERT INTO business_exposures (exposure_id, name, description, category, sort_order, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(exposure_id) DO UPDATE SET
              name=excluded.name, description=excluded.description,
              category=excluded.category, sort_order=excluded.sort_order
            """,
            (exp_id, name, desc, cat, sort_order),
        )
    conn.commit()

    # Report
    n = cur.execute("SELECT COUNT(*) FROM business_exposures").fetchone()[0]
    print(f"[business_exposures] {n} buckets")
    for cat, c in cur.execute(
        "SELECT category, COUNT(*) FROM business_exposures GROUP BY category ORDER BY MIN(sort_order)"
    ).fetchall():
        print(f"  {cat:16s} {c}")
    conn.close()


if __name__ == "__main__":
    main()
