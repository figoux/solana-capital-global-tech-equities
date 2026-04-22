"""
Seed do mapping theme × business_exposure (weight 0..1).

Uso no v_ticker_theme_score:
    score = SUM(ticker_exposure.weight_pct * mapping.weight) / 100

Interpretação:
    weight 1.0 = bucket é O proxy do tema (100% relevante)
    weight 0.5 = bucket é secundário
    weight 0.2 = bucket toca o tema tangencialmente

A direção (bullish/bearish) NÃO vem daqui — ela vem de:
    1. theme_subsector_bullishness (default por subsetor)
    2. theme_ticker_exposure.direction_override (override manual por ticker)

Uso:
    python -m backend.etl.theme_mapping_seed
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

# theme_id -> [(exposure_id, weight)]
# Weights são positivos — representam MAGNITUDE de exposição ao tema.
MAPPING: dict[str, list[tuple[str, float]]] = {

    # ---- AI Infra ----
    "gpu_vs_asic": [
        ("semis_ai_compute", 1.0),
        ("semis_networking", 0.3),       # ASIC switches (TH5, Jericho) crossover
        ("semis_foundry", 0.4),          # TSMC fabrica todos os GPUs/ASICs
    ],
    "memory_wall": [
        ("semis_memory", 1.0),
        ("wfe_equipment", 0.4),          # HBM capex = WFE demand
        ("semis_ai_compute", 0.3),       # GPU/ASIC consumem HBM
        ("semis_foundry", 0.3),          # packaging HBM via foundry (CoWoS)
    ],
    "capex_hyperscalers": [
        ("semis_ai_compute", 1.0),
        ("semis_networking", 0.8),
        ("oem_datacenter", 0.8),
        ("wfe_equipment", 0.6),
        ("cloud_iaas_paas", 0.5),
        ("semis_memory", 0.5),
        ("semis_foundry", 0.6),          # foundry absorve capex de hyperscale
    ],
    "mega_dc_deals": [
        ("semis_ai_compute", 1.0),
        ("oem_datacenter", 0.9),
        ("semis_networking", 0.8),
        ("cloud_iaas_paas", 0.5),
        ("wfe_equipment", 0.3),
        ("semis_foundry", 0.5),
    ],
    "cloud_dominance": [
        ("cloud_iaas_paas", 1.0),
        ("software_enterprise_saas", 0.3),
        ("software_ai_platform", 0.3),
    ],
    "roi_ai_capex": [
        # Proxy para "quem está comprado em AI capex"
        ("semis_ai_compute", 1.0),
        ("oem_datacenter", 0.7),
        ("semis_networking", 0.7),
        ("cloud_iaas_paas", 0.5),
        ("software_ai_platform", 0.5),
        ("semis_memory", 0.5),
        ("wfe_equipment", 0.3),
        ("semis_foundry", 0.6),
    ],
    "cpo_optics": [
        ("semis_networking", 1.0),       # CIEN/LITE/COHR/ANET
    ],
    "cpu_demand": [
        ("semis_general_compute", 1.0),  # INTC/AMD/ARM
        ("oem_datacenter", 0.4),
        ("cloud_iaas_paas", 0.2),
    ],

    # ---- AI Apps ----
    "basket_openai": [
        ("software_ai_platform", 1.0),
        ("cloud_iaas_paas", 0.6),        # Azure é OpenAI
        ("semis_ai_compute", 0.4),
        ("oem_datacenter", 0.3),
    ],
    "chip_to_app": [
        ("software_ai_platform", 1.0),
        ("software_enterprise_saas", 0.5),
        ("software_dev_tools", 0.5),
    ],
    "vibe_coding": [
        ("software_dev_tools", 1.0),
        ("software_ai_platform", 0.5),
    ],
    "llm_leaderboard": [
        ("software_ai_platform", 1.0),
    ],
    "agentic_inference": [
        ("software_ai_platform", 1.0),
        ("cloud_iaas_paas", 0.8),
        ("semis_ai_compute", 0.7),
        ("semis_networking", 0.3),
    ],
    "chinese_llms": [
        # Filtro geográfico fica no app layer (só tickers CN)
        ("software_ai_platform", 1.0),
        ("cloud_iaas_paas", 0.5),
        ("semis_ai_compute", 0.5),
    ],

    # ---- Structural ----
    "saas_is_dead": [
        ("software_enterprise_saas", 1.0),
    ],
    "oems_margin": [
        ("oem_consumer", 1.0),
        ("oem_datacenter", 0.8),
        ("mobile_ecosystem", 1.0),   # AAPL/Samsung/Xiaomi/Foxconn/Lenovo captam margin cycle OEM
    ],
    "humanoides": [
        ("robotics_humanoid", 1.0),
        ("robotics_industrial", 0.3),
    ],
    "autonomous_vehicles": [
        ("autonomous_vehicles", 1.0),
    ],

    # ---- Consumer ----
    "gaming": [
        ("gaming_content", 1.0),
    ],

    # ---- Macro / Financial ----
    "liquidez_ipos": [
        ("financial_infra", 1.0),
        ("fintech_consumer", 0.6),
        ("payments_processing", 0.2),
    ],
    "prediction_markets": [
        ("financial_infra", 1.0),
        ("fintech_consumer", 0.5),
        ("crypto_stablecoins", 0.3),
    ],
    "stablecoins": [
        ("crypto_stablecoins", 1.0),
        ("payments_processing", 0.5),
        ("fintech_consumer", 0.3),
        ("financial_infra", 0.3),
    ],
    "private_credit": [
        ("financial_infra", 0.6),
        ("fintech_consumer", 0.5),
        ("payments_processing", 0.2),
    ],
}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    valid_themes = {r[0] for r in cur.execute("SELECT theme_id FROM themes").fetchall()}
    valid_buckets = {r[0] for r in cur.execute("SELECT exposure_id FROM business_exposures").fetchall()}
    assert valid_themes, "Rode themes_seed antes."
    assert valid_buckets, "Rode business_exposures_seed antes."

    errors = []
    for t_id, rows in MAPPING.items():
        if t_id not in valid_themes:
            errors.append(f"theme inválido: {t_id}")
        for exp_id, w in rows:
            if exp_id not in valid_buckets:
                errors.append(f"{t_id}: bucket inválido '{exp_id}'")
            if not (0 <= w <= 1.5):
                errors.append(f"{t_id}/{exp_id}: weight {w} fora do range")

    if errors:
        print("[theme_mapping_seed] ERROS:")
        for e in errors:
            print("  " + e)
        return

    # Reset idempotente por tema mapeado (não apaga temas não presentes aqui)
    n_rows = 0
    for t_id, rows in MAPPING.items():
        cur.execute("DELETE FROM theme_exposure_mapping WHERE theme_id=?", (t_id,))
        for exp_id, w in rows:
            cur.execute(
                "INSERT INTO theme_exposure_mapping (theme_id, exposure_id, weight, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (t_id, exp_id, w),
            )
            n_rows += 1
    conn.commit()

    # Report
    print(f"[theme_mapping_seed] themes={len(MAPPING)} rows={n_rows}")

    # Temas sem mapping
    missing = [t for t in valid_themes if t not in MAPPING]
    if missing:
        print(f"[WARN] {len(missing)} temas sem mapping: {', '.join(missing)}")

    # Sanity: top 3 tickers por tema via v_ticker_theme_score (scale 0-100)
    print("\nTop 3 tickers por tema (score 0-100 via mapping):")
    for t_id, _ in cur.execute(
        "SELECT theme_id, name FROM themes ORDER BY sort_order"
    ).fetchall():
        rows = cur.execute(
            "SELECT ticker, score FROM v_ticker_theme_score "
            "WHERE theme_id=? AND score > 0 ORDER BY score DESC LIMIT 3",
            (t_id,),
        ).fetchall()
        if rows:
            top = ", ".join(f"{t}:{s:.0f}" for t, s in rows)
            print(f"  {t_id:22s} {top}")
        else:
            print(f"  {t_id:22s} (nenhum ticker exposto)")

    conn.close()


if __name__ == "__main__":
    main()
