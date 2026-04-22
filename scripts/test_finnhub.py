"""
Testa conexão com Finnhub (depois que FINNHUB_API_KEY estiver em .env).
Puxa: company profile, earnings calendar da semana, último consensus EPS p/ NVDA.
"""
import os
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

import finnhub

ROOT = Path(__file__).resolve().parent.parent

def main() -> None:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise SystemExit(
            "FINNHUB_API_KEY não configurada. Edita .env com a chave do https://finnhub.io/dashboard"
        )

    client = finnhub.Client(api_key=api_key)

    # 1. Company profile NVDA
    print("[1] Company profile — NVDA")
    prof = client.company_profile2(symbol="NVDA")
    print(f"    name={prof.get('name')}, mktcap={prof.get('marketCapitalization')}M, exch={prof.get('exchange')}")

    # 2. Earnings calendar próximos 14 dias
    today = date.today()
    to = today + timedelta(days=14)
    print(f"\n[2] Earnings calendar {today} → {to}")
    cal = client.earnings_calendar(_from=today.isoformat(), to=to.isoformat(), symbol="", international=False)
    events = cal.get("earningsCalendar", [])
    print(f"    {len(events)} eventos nos próximos 14 dias")
    for ev in events[:10]:
        print(f"    - {ev.get('date')} {ev.get('hour','?'):4s} | {ev.get('symbol'):8s} | EPS est {ev.get('epsEstimate')} | Rev est {ev.get('revenueEstimate')}")

    # 3. EPS estimates NVDA quarterly
    print("\n[3] NVDA quarterly EPS estimates (próximos)")
    ests = client.company_eps_estimates(symbol="NVDA", freq="quarterly")
    for row in (ests.get("data") or [])[:4]:
        print(f"    - {row.get('period')} | mean={row.get('epsAvg')} | n={row.get('numberAnalysts')}")

    print("\n[ok] Finnhub conectado.")

if __name__ == "__main__":
    main()
