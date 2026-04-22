# Business Exposures — Taxonomia e Workflow

**Objetivo:** decompor cada stock em pesos % pelas linhas de negócio/value drivers, para habilitar:
1. Cálculo de similaridade estrutural entre stocks (cosine similarity)
2. Identificação de pares com overlap alto numa mesma exposição → pair trade
3. Hedge via spread de implied vol (long no de IV barata + short no de IV rica)

**Separação conceitual:**
- **Themes** (`gpu_vs_asic`, `humanoides`, ...) = narrativa direcional, heatmap editável, você emite view bull/bear por subsetor
- **Business Exposures** (`ecommerce`, `cloud_iaas_paas`, ...) = composição estrutural de receita/valor, vetor por stock, usado para correlação

---

## Taxonomia v1 (25 buckets)

### Consumer / Commerce (7)
| exposure_id | name | descrição |
|---|---|---|
| `ecommerce` | E-commerce | Retail 1P + marketplace 3P online |
| `digital_ads` | Digital Advertising | Search ads + display + social ads + CTV |
| `social_media` | Social Media | Engagement/network effects distinct de ads monetization |
| `subscription_media` | Subscription Media | Streaming vídeo/música, assinaturas recorrentes consumer |
| `gaming` | Gaming | Games publishing, plataformas, engines, esports |
| `food_delivery_rideshare` | Food/Mobility | Food delivery + rideshare + last-mile |
| `travel_booking` | Travel | OTAs, booking, travel tech |

### Cloud / Data (6)
| exposure_id | name | descrição |
|---|---|---|
| `cloud_iaas_paas` | Cloud Infra (IaaS/PaaS) | Hyperscaler compute/storage/database (AWS/Azure/GCP + pure-plays) |
| `saas_horizontal` | Horizontal SaaS | CRM, ERP, collaboration, office suites multi-indústria |
| `saas_vertical` | Vertical SaaS | Saúde, financeiro, restaurante, construção (mercados específicos) |
| `data_analytics` | Data/Analytics | Data warehouse, observability, analytics platforms |
| `security_software` | Security Software | Endpoint/network/identity/cloud security SaaS |
| `search` | Search | Motor de busca como produto core |

### Hardware / Semis (9)
| exposure_id | name | descrição |
|---|---|---|
| `semis_ai_compute` | AI Compute Silicon | GPUs, AI ASICs (TPU, Trainium), accelerators |
| `semis_general` | General Semis | Analog, MCU, power, auto, commodity logic |
| `memory` | Memory | DRAM, NAND, HBM |
| `foundry` | Foundry | TSMC-style contract manufacturing |
| `wfe` | Wafer Fab Equipment | Lithography, etch, deposition, metrology, ATE |
| `cpo_optics` | Optics / CPO | Pluggables, co-packaged optics, laser/DSP |
| `networking_hw` | Networking HW | Ethernet switches, routers, datacenter fabric, NICs |
| `consumer_hw` | Consumer HW | Phones, PCs, wearables, AR/VR, gaming consoles |
| `datacenter_power_cooling` | DC Power/Cooling | Power distribution, fuel cells, liquid cooling, thermal |

### Fintech / Payments (4)
| exposure_id | name | descrição |
|---|---|---|
| `payments_network` | Payment Networks | V, MA (4-party rails) |
| `payments_merchant` | Merchant Acquiring | Block, Toast, Stone, Adyen (acquirers/PSPs) |
| `crypto_exchange` | Crypto | Exchanges, custody, staking, stablecoins |
| `neo_bank_bnpl` | Digital Banking + BNPL | Neobanks, BNPL, consumer fintech |

### Frontier (6)
| exposure_id | name | descrição |
|---|---|---|
| `autonomous_driving` | Autonomous Driving | AV tech, robotaxi, autonomous trucking |
| `humanoid_robotics` | Humanoid Robotics | General-purpose humanoids |
| `industrial_automation` | Industrial Automation | Factory automation, warehouse robots, PLCs |
| `medical_robotics` | Medical Robotics | Surgical robots, medical devices with robotics |
| `enterprise_ai_apps` | Enterprise AI Apps | Copilots, agents, AI features embedded in SaaS |
| `foundation_models` | Foundation Models | Core LLM labs monetizing via APIs/assistants |

### Other (1)
| exposure_id | name | descrição |
|---|---|---|
| `it_services_legacy` | IT Services / Legacy | Consulting, outsourcing, legacy infra services |

---

## Exemplos (para calibração)

```
AMZN:  ecommerce 52, cloud_iaas_paas 17, digital_ads 9, subscription_media 7,
       industrial_automation 4, consumer_hw 3, other 8
GOOGL: search 55, digital_ads 12, cloud_iaas_paas 13, autonomous_driving 3,
       foundation_models 5, consumer_hw 2, social_media 2, other 8
MSFT:  cloud_iaas_paas 38, saas_horizontal 32, gaming 9, enterprise_ai_apps 6,
       consumer_hw 5, foundation_models 4, security_software 6
META:  digital_ads 95, enterprise_ai_apps 1, consumer_hw (Quest) 2, other 2
AAPL:  consumer_hw 78, subscription_media 14, saas_horizontal 5, other 3
NVDA:  semis_ai_compute 88, networking_hw 5, semis_general 5, other 2
TSM:   foundry 98, other 2
NFLX:  subscription_media 97, digital_ads 3
V:     payments_network 100
NU:    neo_bank_bnpl 92, payments_merchant 5, crypto_exchange 3
COIN:  crypto_exchange 88, payments_network 5, neo_bank_bnpl 7
BE:    datacenter_power_cooling 90, other 10
ISRG:  medical_robotics 100
SYM:   industrial_automation 100
688256.SS: semis_ai_compute 95, other 5
Unitree: humanoid_robotics 80, industrial_automation 20
MiniMax: foundation_models 90, enterprise_ai_apps 10
```

---

## Workflow para popular

**Fase 1 — batch inicial (Claude reasoning):**
- Script `backend/etl/exposures_seed.py` itera os 124 tickers
- Para cada: chama Claude com prompt estruturado contendo `name`, `subsector`, `country`, pede JSON `{exposure_id: weight_pct}` que some 100
- Valida (sum entre 95-105, todos exposure_id são válidos, não mais que 6 exposures > 5%)
- Insere na `ticker_exposure` com `source='claude_reasoning'`

**Fase 2 — refino top 30 (10-K segment):**
- Para as 30 maiores (AMZN, GOOGL, MSFT, META, AAPL, TSM, NVDA, etc), pegar segment reporting do último 10-K via EDGAR (US) ou relatório anual
- Substituir manualmente os pesos da Fase 1 com precisão de filings
- `source='10k_segment'`, `locked=1`

**Fase 3 — UI para edição contínua:**
- Company page mostra pie chart de exposures + lista editável
- Cada linha tem input numérico + campo de rationale
- Salva com `source='manual'`, `locked=1`

---

## Como a cosine similarity vira pair trade

```python
import numpy as np

def cosine(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    va = np.array([a.get(k, 0.0) for k in keys])
    vb = np.array([b.get(k, 0.0) for k in keys])
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(va @ vb / denom) if denom else 0.0

# Exemplo: AMZN vs PDD
amzn = {"ecommerce": 52, "cloud_iaas_paas": 17, "digital_ads": 9, ...}
pdd  = {"ecommerce": 100}
# cosine(amzn, pdd) ≈ 0.58 — overlap dominante em ecommerce
```

**Algo de sugestão de pairs na UI:**
1. Para ticker A, computa `cosine_sim(A, X)` para todos X do universo
2. Filtra X com `cosine_sim > 0.4` AND mesmo subsetor OR mesma top-exposure
3. Para cada candidato, pega `iv_30d_atm` de A e de X (se disponível)
4. Rankeia por `abs(iv_A - iv_X)` → pares com maior spread de IV primeiro
5. UI mostra sugestão: "Long A / Short X — overlap 62% em `ecommerce`, spread IV30 = +8pp"
