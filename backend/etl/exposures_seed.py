"""
Seed das exposições ticker × business_exposure (weight_pct).

Rascunho hardcoded — você edita pela UI depois. Weights somam ~100 por ticker.
Fonte: minha melhor estimativa por segmento de receita / biz mix conhecido.
Todos entram como source='seed', locked=0 (editável).

Uso:
    python -m backend.etl.exposures_seed
"""
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "db" / "dashboard.db"

# ticker -> [(exposure_id, weight_pct)]
# Soma deve ser ~100. Buckets válidos: veja business_exposures_seed.py
EXPOSURES: dict[str, list[tuple[str, int]]] = {

    # ============ Semis ============
    "NVDA":       [("semis_ai_compute", 70), ("semis_networking", 10), ("gaming_content", 8), ("software_ai_platform", 9), ("semis_general_compute", 3)],
    "TSM":        [("semis_foundry", 100)],
    "AVGO":       [("semis_ai_compute", 35), ("semis_networking", 30), ("semis_general_compute", 15), ("software_enterprise_saas", 20)],
    "AMD":        [("semis_ai_compute", 40), ("semis_general_compute", 45), ("gaming_content", 10), ("semis_networking", 5)],
    "QCOM":       [("mobile_ecosystem", 90), ("autonomous_vehicles", 5), ("semis_general_compute", 5)],
    "TXN":        [("semis_general_compute", 100)],
    "ARM":        [("mobile_ecosystem", 55), ("semis_general_compute", 25), ("semis_ai_compute", 20)],
    "MU":         [("semis_memory", 95), ("other", 5)],
    "INTC":       [("semis_general_compute", 50), ("semis_foundry", 30), ("semis_ai_compute", 10), ("oem_datacenter", 5), ("oem_consumer", 5)],
    "MRVL":       [("semis_networking", 50), ("semis_ai_compute", 25), ("semis_general_compute", 15), ("semis_memory", 10)],
    "NXPI":       [("semis_general_compute", 100)],
    "005930.KS":  [("semis_memory", 30), ("semis_foundry", 20), ("mobile_ecosystem", 20), ("oem_consumer", 15), ("semis_general_compute", 5), ("semis_ai_compute", 3), ("oem_datacenter", 4), ("semis_networking", 3)],
    "MPWR":       [("semis_general_compute", 100)],
    "ON":         [("semis_general_compute", 100)],
    "MCHP":       [("semis_general_compute", 100)],
    "SWKS":       [("mobile_ecosystem", 90), ("semis_general_compute", 10)],
    "GFS":        [("semis_foundry", 100)],
    "COHR":       [("semis_networking", 80), ("semis_general_compute", 15), ("semis_ai_compute", 5)],
    "UMC":        [("semis_foundry", 100)],
    "000660.KS":  [("semis_memory", 100)],
    "RMBS":       [("semis_memory", 70), ("semis_general_compute", 30)],
    "SNDK":       [("semis_memory", 100)],  # pure NAND (spun off from WDC Feb-2025)
    "WDC":        [("semis_memory", 100)],  # HDDs post-spinoff; groups with memory cycle
    "STX":        [("semis_memory", 100)],  # pure HDD; groups with memory cycle
    "688256.SS":  [("semis_ai_compute", 100)],

    # ============ WFEs ============
    "ASML":       [("wfe_equipment", 100)],
    "AMAT":       [("wfe_equipment", 100)],
    "LRCX":       [("wfe_equipment", 100)],
    "KLAC":       [("wfe_equipment", 100)],
    "TER":        [("wfe_equipment", 80), ("oem_consumer", 20)],

    # ============ SaaS ============
    "CRM":        [("software_enterprise_saas", 100)],
    "NOW":        [("software_enterprise_saas", 100)],
    "ADBE":       [("software_enterprise_saas", 85), ("software_ai_platform", 10), ("digital_ads", 5)],
    "WDAY":       [("software_enterprise_saas", 100)],
    "SNOW":       [("software_enterprise_saas", 60), ("software_dev_tools", 30), ("software_ai_platform", 10)],
    "DDOG":       [("software_dev_tools", 100)],
    "SHOP":       [("ecommerce", 90), ("payments_processing", 10)],
    "VEEV":       [("software_enterprise_saas", 100)],
    "MDB":        [("software_dev_tools", 100)],
    "HUBS":       [("software_enterprise_saas", 100)],
    "ZM":         [("software_enterprise_saas", 100)],
    "DOCU":       [("software_enterprise_saas", 100)],
    "TWLO":       [("software_dev_tools", 100)],
    "TTD":        [("digital_ads", 100)],
    "U":          [("gaming_content", 60), ("software_dev_tools", 30), ("digital_ads", 10)],
    "ESTC":       [("software_dev_tools", 100)],
    "CFLT":       [("software_dev_tools", 100)],
    "GTLB":       [("software_dev_tools", 100)],

    # ============ Internet ============
    "GOOGL":      [("digital_ads", 55), ("cloud_iaas_paas", 15), ("subscription_media", 10), ("software_ai_platform", 10), ("gaming_content", 5), ("oem_consumer", 5)],
    "META":       [("digital_ads", 95), ("software_ai_platform", 5)],
    "AMZN":       [("ecommerce", 52), ("cloud_iaas_paas", 17), ("digital_ads", 9), ("subscription_media", 7), ("other", 15)],
    "NFLX":       [("subscription_media", 100)],
    "0700.HK":    [("gaming_content", 35), ("subscription_media", 15), ("digital_ads", 15), ("fintech_consumer", 15), ("cloud_iaas_paas", 15), ("other", 5)],
    "9988.HK":    [("ecommerce", 60), ("cloud_iaas_paas", 15), ("digital_ads", 5), ("fintech_consumer", 10), ("subscription_media", 5), ("other", 5)],
    "UBER":       [("travel_booking", 100)],
    "BKNG":       [("travel_booking", 100)],
    "PDD":        [("ecommerce", 100)],
    "3690.HK":    [("travel_booking", 100)],
    "JD":         [("ecommerce", 100)],
    "ABNB":       [("travel_booking", 100)],
    "DASH":       [("travel_booking", 100)],
    "SPOT":       [("subscription_media", 100)],
    "PINS":       [("digital_ads", 100)],
    "SNAP":       [("digital_ads", 100)],
    "RDDT":       [("digital_ads", 100)],
    "BIDU":       [("digital_ads", 50), ("software_ai_platform", 25), ("autonomous_vehicles", 15), ("cloud_iaas_paas", 10)],
    "RBLX":       [("gaming_content", 100)],
    "EA":         [("gaming_content", 100)],
    "TTWO":       [("gaming_content", 100)],

    # ============ OEMs ============
    "AAPL":       [("mobile_ecosystem", 80), ("subscription_media", 10), ("oem_consumer", 5), ("payments_processing", 3), ("other", 2)],
    "2317.TW":    [("mobile_ecosystem", 30), ("oem_consumer", 25), ("oem_datacenter", 30), ("autonomous_vehicles", 5), ("other", 10)],
    "1810.HK":    [("mobile_ecosystem", 55), ("oem_consumer", 20), ("autonomous_vehicles", 15), ("other", 10)],
    "DELL":       [("oem_consumer", 40), ("oem_datacenter", 60)],
    "HPQ":        [("oem_consumer", 100)],
    "SMCI":       [("oem_datacenter", 100)],  # AI server pure-play
    "LNVGY":      [("oem_consumer", 60), ("mobile_ecosystem", 15), ("oem_datacenter", 25)],  # ADR US (renomeado de 0992.HK)
    "6758.T":     [("gaming_content", 30), ("oem_consumer", 30), ("subscription_media", 20), ("other", 20)],
    "7974.T":     [("gaming_content", 100)],
    "LOGI":       [("oem_consumer", 100)],
    "GRMN":       [("oem_consumer", 100)],

    # ============ Cloud/Data ============
    "MSFT":       [("software_enterprise_saas", 30), ("cloud_iaas_paas", 35), ("software_ai_platform", 15), ("gaming_content", 10), ("oem_consumer", 5), ("software_dev_tools", 5)],
    "ORCL":       [("software_enterprise_saas", 50), ("cloud_iaas_paas", 40), ("software_ai_platform", 10)],
    "IBM":        [("software_enterprise_saas", 50), ("cloud_iaas_paas", 15), ("software_ai_platform", 20), ("oem_datacenter", 10), ("other", 5)],
    "PLTR":       [("software_ai_platform", 80), ("software_enterprise_saas", 20)],
    "SAP":        [("software_enterprise_saas", 100)],
    "DBX":        [("software_enterprise_saas", 100)],
    "BOX":        [("software_enterprise_saas", 100)],
    "PSTG":       [("oem_datacenter", 100)],
    "BE":         [("oem_datacenter", 100)],

    # ============ Cybersecurity ============
    "CRWD":       [("cybersecurity", 100)],
    "PANW":       [("cybersecurity", 100)],
    "FTNT":       [("cybersecurity", 100)],
    "ZS":         [("cybersecurity", 100)],
    "S":          [("cybersecurity", 100)],
    "OKTA":       [("cybersecurity", 100)],
    "NET":        [("cybersecurity", 50), ("software_dev_tools", 30), ("semis_networking", 20)],

    # ============ Financial Services ============
    "V":          [("payments_processing", 100)],
    "MA":         [("payments_processing", 100)],
    "PYPL":       [("fintech_consumer", 70), ("payments_processing", 30)],
    "XYZ":        [("fintech_consumer", 50), ("payments_processing", 40), ("crypto_stablecoins", 10)],
    "COIN":       [("crypto_stablecoins", 100)],
    "HOOD":       [("fintech_consumer", 80), ("crypto_stablecoins", 20)],
    "AFRM":       [("fintech_consumer", 100)],
    "ADYEN.AS":   [("payments_processing", 100)],
    "TOST":       [("payments_processing", 100)],

    # ============ Networking ============
    "CSCO":       [("semis_networking", 60), ("cybersecurity", 30), ("software_enterprise_saas", 10)],
    "ANET":       [("semis_networking", 100)],
    "JNPR":       [("semis_networking", 90), ("cybersecurity", 10)],  # inactive (HPE acq)
    "HPE":        [("oem_datacenter", 70), ("semis_networking", 25), ("software_enterprise_saas", 5)],
    "NTAP":       [("oem_datacenter", 100)],
    "NOK":        [("semis_networking", 100)],
    "ERIC":       [("semis_networking", 100)],
    "CIEN":       [("semis_networking", 100)],
    "LITE":       [("semis_networking", 100)],
    "FFIV":       [("cybersecurity", 50), ("semis_networking", 50)],

    # ============ Robotics ============
    "ISRG":       [("robotics_industrial", 100)],  # medical
    "6954.T":     [("robotics_industrial", 100)],
    "6506.T":     [("robotics_industrial", 100)],
    "SYM":        [("robotics_industrial", 100)],
    "ABBNY":      [("robotics_industrial", 100)],
    "ROK":        [("robotics_industrial", 100)],
    "CGNX":       [("robotics_industrial", 100)],
    "ZBRA":       [("robotics_industrial", 100)],
    "TRMB":       [("robotics_industrial", 50), ("autonomous_vehicles", 30), ("other", 20)],
    "AUR":        [("autonomous_vehicles", 100)],
    "IRBT":       [("robotics_industrial", 100)],  # inactive
    "UNITREE_PVT":[("robotics_humanoid", 70), ("robotics_industrial", 30)],
    "MINIMAX_PVT":[("software_ai_platform", 100)],
}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Valida que cada ticker soma ~100 e bucket existe
    valid_buckets = {r[0] for r in cur.execute("SELECT exposure_id FROM business_exposures").fetchall()}
    assert valid_buckets, "Rode business_exposures_seed antes."

    n_tickers = 0
    n_rows = 0
    errors = []
    for ticker, buckets in EXPOSURES.items():
        total = sum(w for _, w in buckets)
        if abs(total - 100) > 2:
            errors.append(f"{ticker}: soma={total}")
        for exp_id, _ in buckets:
            if exp_id not in valid_buckets:
                errors.append(f"{ticker}: bucket inválido '{exp_id}'")

    if errors:
        print("[exposures_seed] ERROS de validação:")
        for e in errors:
            print("  " + e)
        return

    for ticker, buckets in EXPOSURES.items():
        # Remove seeds antigos deste ticker que NÃO estão no mapping atual
        # (não apaga manual/locked)
        current_ids = [exp_id for exp_id, _ in buckets]
        placeholders = ",".join("?" * len(current_ids))
        cur.execute(
            f"DELETE FROM ticker_exposure "
            f"WHERE ticker=? AND source='seed' AND COALESCE(locked,0)=0 "
            f"AND exposure_id NOT IN ({placeholders})",
            (ticker, *current_ids),
        )
        for exp_id, w in buckets:
            # Upsert: só sobrescreve se não for manual/locked
            cur.execute(
                """
                INSERT INTO ticker_exposure (ticker, exposure_id, weight_pct, source, locked, updated_at)
                VALUES (?, ?, ?, 'seed', 0, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker, exposure_id) DO UPDATE SET
                  weight_pct=excluded.weight_pct, updated_at=CURRENT_TIMESTAMP
                  WHERE COALESCE(ticker_exposure.locked,0)=0
                    AND COALESCE(ticker_exposure.source,'seed') NOT IN ('manual','claude_reasoning')
                """,
                (ticker, exp_id, w),
            )
            n_rows += 1
        n_tickers += 1

    cur.execute(
        "INSERT INTO etl_runs (job_name, started_at, finished_at, status, rows_upserted, message) "
        "VALUES (?, ?, ?, 'ok', ?, ?)",
        (
            "exposures_seed",
            datetime.now().isoformat(timespec="seconds"),
            datetime.now().isoformat(timespec="seconds"),
            n_rows,
            f"tickers={n_tickers} rows={n_rows}",
        ),
    )
    conn.commit()

    # Report
    print(f"[exposures_seed] tickers={n_tickers} rows={n_rows}")

    # Top 5 exposures por bucket (mais pesadas)
    print("\nTop ticker por bucket (peso máximo):")
    for exp_id, name in cur.execute(
        "SELECT exposure_id, name FROM business_exposures ORDER BY sort_order"
    ).fetchall():
        row = cur.execute(
            "SELECT ticker, weight_pct FROM ticker_exposure WHERE exposure_id=? ORDER BY weight_pct DESC LIMIT 1",
            (exp_id,),
        ).fetchone()
        if row:
            print(f"  {exp_id:26s} → {row[0]:12s} ({row[1]}%)")
        else:
            print(f"  {exp_id:26s} → —")

    # Tickers sem exposure
    missing = cur.execute(
        "SELECT ticker FROM companies WHERE ticker NOT IN (SELECT DISTINCT ticker FROM ticker_exposure) ORDER BY ticker"
    ).fetchall()
    if missing:
        print(f"\n[WARN] {len(missing)} tickers sem exposure: {', '.join(m[0] for m in missing)}")

    conn.close()


if __name__ == "__main__":
    main()
