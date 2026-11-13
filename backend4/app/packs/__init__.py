"""
Industry packs = pure configuration (no code). A pack teaches the platform
what 'revenue', 'cost', 'churn' ... look like in a given industry, which
questions matter, and which alerts to start with. Add your own by dropping
a JSON file with the same shape into app/packs/custom/.
"""
import json
from pathlib import Path

_G_HINTS = {
    "profit": ["profit", "net_profit", "gross_profit", "margin_amount", "earnings", "ebitda"],
    "revenue": ["revenue", "sales", "net_sales", "gmv", "turnover", "income", "total_sales",
                "mrr", "arr", "billing", "amount", "total"],
    "cost": ["cost", "cogs", "expense", "expenses", "spend", "total_cost", "opex"],
    "discount": ["discount", "promo", "rebate", "markdown", "coupon"],
    "returns": ["refund", "returns", "return_amount", "chargeback", "credit_note"],
    "quantity": ["quantity", "qty", "units", "volume", "orders"],
    "price": ["price", "unit_price", "rate", "asp"],
    "churn": ["churn", "churned", "cancelled", "canceled", "attrition", "lost"],
    "date": ["date", "order_date", "day", "month", "period", "timestamp", "created", "time"],
}


def _hints(**over):
    h = {k: list(v) for k, v in _G_HINTS.items()}
    for k, v in over.items():
        h[k] = list(v) + [x for x in h.get(k, []) if x not in v]
    return h


PACKS = {
    "general": {
        "id": "general", "name": "General business", "icon": "📊",
        "description": "Works on any tabular business data. Auto-detects revenue, cost, profit and segments.",
        "hints": _hints(), "dimensions": [], "synonyms": {},
        "kpis": [{"name": "Revenue"}, {"name": "Profit"}, {"name": "Margin %"}],
        "alert_templates": [],
        "starter_questions": [
            "Where am I losing money?", "Which segment has the weakest margin?",
            "What changed in the latest period and why?", "Give me a full dashboard",
        ],
        "drivers": ["segment losses", "margin gaps", "period-over-period decline"],
    },
    "retail": {
        "id": "retail", "name": "Retail & E-commerce", "icon": "🛒",
        "description": "Orders, SKUs, stores, channels. Finds discount leakage, returns and low-margin categories.",
        "hints": _hints(revenue=["gmv", "net_sales", "sales", "order_value", "revenue"],
                        discount=["discount", "promo", "coupon", "markdown"],
                        returns=["return", "refund", "rto"], quantity=["qty", "quantity", "units"]),
        "dimensions": ["category", "product", "sku", "store", "channel", "region", "city", "brand"],
        "synonyms": {"gmv": "revenue", "aov": "avg_order_value", "turnover": "revenue", "cogs": "cost"},
        "kpis": [{"name": "GMV"}, {"name": "Gross margin %"}, {"name": "Return rate"}, {"name": "Discount leakage"}],
        "alert_templates": [{"label": "Margin dropped below 15%", "role": "margin_pct", "operator": "<", "threshold": 15}],
        "starter_questions": [
            "Which categories lose money after discounts?", "How much revenue do we leak through discounts?",
            "Which region has the lowest margin?", "What if we cut discounts by 20%?",
        ],
        "drivers": ["discount leakage", "returns", "negative-margin SKUs", "channel mix"],
    },
    "saas": {
        "id": "saas", "name": "SaaS & Subscriptions", "icon": "☁️",
        "description": "MRR/ARR, plans, cohorts. Quantifies churn loss and expansion opportunity.",
        "hints": _hints(revenue=["mrr", "arr", "revenue", "billing", "subscription_amount"],
                        churn=["churn", "churned", "cancelled", "is_churned", "lost"]),
        "dimensions": ["plan", "tier", "segment", "country", "industry", "channel", "cohort"],
        "synonyms": {"mrr": "revenue", "arr": "revenue", "arpu": "avg_revenue_per_user"},
        "kpis": [{"name": "MRR"}, {"name": "Churn rate"}, {"name": "ARPU"}, {"name": "LTV:CAC"}],
        "alert_templates": [{"label": "Churn above 5%", "role": "churn_rate", "operator": ">", "threshold": 5}],
        "starter_questions": [
            "How much recurring revenue did churn cost us?", "Which plan churns the most?",
            "What if churn drops by 2 points?", "Which segment has the best expansion potential?",
        ],
        "drivers": ["churn", "discounting", "low-margin plans", "support cost per account"],
    },
    "fintech": {
        "id": "fintech", "name": "Fintech, Lending & Insurance", "icon": "🏦",
        "description": "Loans, claims, transactions. Surfaces default loss, fraud and underwriting margin gaps.",
        "hints": _hints(revenue=["interest_income", "premium", "fee", "revenue", "income"],
                        cost=["loss", "claim", "claims", "default_amount", "write_off", "cost", "expense"],
                        returns=["chargeback", "fraud_amount", "refund"],
                        churn=["default", "defaulted", "lapsed", "churn"]),
        "dimensions": ["product", "segment", "channel", "region", "risk_band", "agent", "branch"],
        "synonyms": {"npa": "default", "premium": "revenue", "claims": "cost"},
        "kpis": [{"name": "Net interest/premium"}, {"name": "Loss ratio"}, {"name": "Default rate"}],
        "alert_templates": [{"label": "Loss ratio above 70%", "role": "loss_ratio", "operator": ">", "threshold": 70}],
        "starter_questions": [
            "Which segment has the highest loss ratio?", "How much did defaults cost us?",
            "Where is fraud concentrated?", "What if we tighten approval for the riskiest band?",
        ],
        "drivers": ["defaults / claims", "fraud & chargebacks", "channel acquisition cost"],
    },
    "logistics": {
        "id": "logistics", "name": "Logistics & Supply Chain", "icon": "🚚",
        "description": "Shipments, routes, fleets. Finds costly lanes, delays and failed deliveries.",
        "hints": _hints(revenue=["freight_revenue", "shipping_revenue", "revenue", "billing", "amount"],
                        cost=["delivery_cost", "freight_cost", "fuel", "transport_cost", "cost"],
                        returns=["rto", "penalty", "damage_claim"], quantity=["shipments", "parcels", "weight", "units"]),
        "dimensions": ["route", "lane", "origin", "destination", "carrier", "warehouse", "vehicle", "region"],
        "synonyms": {"freight": "revenue", "fuel_cost": "cost"},
        "kpis": [{"name": "Cost per shipment"}, {"name": "On-time %"}, {"name": "Lane margin"}],
        "alert_templates": [],
        "starter_questions": [
            "Which lanes lose money?", "Where do penalties and damages cost us most?",
            "Which carrier has the worst margin?", "What if fuel cost rises 10%?",
        ],
        "drivers": ["unprofitable lanes", "penalties", "fuel & empty miles", "carrier mix"],
    },
    "manufacturing": {
        "id": "manufacturing", "name": "Manufacturing & Operations", "icon": "🏭",
        "description": "Plants, lines, batches. Finds scrap, downtime and costly product lines.",
        "hints": _hints(cost=["production_cost", "scrap_cost", "downtime_cost", "cost", "expense"],
                        returns=["scrap", "rework", "defect_cost", "warranty"], quantity=["units_produced", "output", "units", "qty"]),
        "dimensions": ["plant", "line", "machine", "shift", "product", "supplier"],
        "synonyms": {"cogs": "cost", "oee": "equipment_effectiveness"},
        "kpis": [{"name": "Unit cost"}, {"name": "Scrap cost"}, {"name": "Line margin"}],
        "alert_templates": [],
        "starter_questions": [
            "Which line has the highest scrap cost?", "Which plant has the weakest margin?",
            "What drove cost up last period?", "What if scrap drops 25%?",
        ],
        "drivers": ["scrap & rework", "downtime", "supplier cost", "low-yield lines"],
    },
    "telecom": {
        "id": "telecom", "name": "Telecom & Utilities", "icon": "📡",
        "description": "Subscribers, usage, tariffs. Quantifies churn, ARPU gaps and network cost.",
        "hints": _hints(revenue=["arpu", "revenue", "bill_amount", "recharge", "billing"],
                        churn=["churn", "churned", "port_out", "disconnected"]),
        "dimensions": ["plan", "circle", "region", "segment", "device", "tower"],
        "synonyms": {"arpu": "revenue"},
        "kpis": [{"name": "ARPU"}, {"name": "Churn rate"}, {"name": "Network cost per user"}],
        "alert_templates": [],
        "starter_questions": ["How much revenue did churned subscribers cost us?", "Which plan has the lowest ARPU?",
                              "Which circle is least profitable?"],
        "drivers": ["churn", "low-ARPU plans", "network cost"],
    },
    "adtech": {
        "id": "adtech", "name": "Marketing & Ad-tech", "icon": "📣",
        "description": "Campaigns, channels, spend. Finds wasted spend and best-return channels.",
        "hints": _hints(revenue=["conversion_value", "revenue", "sales", "attributed_revenue"],
                        cost=["spend", "ad_spend", "cost", "budget"], quantity=["clicks", "impressions", "conversions"]),
        "dimensions": ["campaign", "channel", "ad_group", "platform", "audience", "creative", "country"],
        "synonyms": {"roas": "return_on_ad_spend", "spend": "cost"},
        "kpis": [{"name": "ROAS"}, {"name": "CAC"}, {"name": "Wasted spend"}],
        "alert_templates": [],
        "starter_questions": ["Which campaigns burn money with no return?", "Which channel has the best ROAS?",
                              "How much spend is wasted?", "What if I move 20% budget to the best channel?"],
        "drivers": ["negative-ROI campaigns", "overlapping audiences", "creative fatigue"],
    },
    "healthcare": {
        "id": "healthcare", "name": "Healthcare Operations", "icon": "🏥",
        "description": "Claims, departments, visits. Finds denied claims, idle capacity and costly units.",
        "hints": _hints(revenue=["billed_amount", "claim_amount", "revenue", "collections"],
                        cost=["treatment_cost", "cost", "expense"], returns=["denied", "denial", "write_off", "rejected_amount"]),
        "dimensions": ["department", "doctor", "procedure", "payer", "branch", "insurer"],
        "synonyms": {"billed": "revenue", "denied": "returns"},
        "kpis": [{"name": "Collection rate"}, {"name": "Denial rate"}, {"name": "Cost per patient"}],
        "alert_templates": [],
        "starter_questions": ["How much revenue is lost to denied claims?", "Which department has the lowest margin?",
                              "Which payer delays collections most?"],
        "drivers": ["claim denials", "idle capacity", "high-cost procedures"],
    },
    "energy": {
        "id": "energy", "name": "Energy & Utilities Ops", "icon": "⚡",
        "description": "Generation, consumption, tariffs. Finds loss, theft and costly assets.",
        "hints": _hints(revenue=["billed", "revenue", "tariff_revenue", "sales"],
                        cost=["generation_cost", "purchase_cost", "cost", "expense"],
                        returns=["loss", "theft", "at&c", "unbilled"], quantity=["kwh", "units", "mwh", "consumption"]),
        "dimensions": ["feeder", "plant", "region", "consumer_type", "substation", "fuel"],
        "synonyms": {"kwh": "quantity"},
        "kpis": [{"name": "Cost per unit"}, {"name": "T&D loss %"}, {"name": "Collection efficiency"}],
        "alert_templates": [],
        "starter_questions": ["Which feeders lose the most money?", "Where is unbilled energy highest?",
                              "What if losses drop 3 points?"],
        "drivers": ["technical & commercial loss", "fuel cost", "unbilled units"],
    },
    "travel": {
        "id": "travel", "name": "Travel, Airlines & Hospitality", "icon": "✈️",
        "description": "Bookings, routes, occupancy. Finds empty-seat cost, cancellations and weak routes.",
        "hints": _hints(revenue=["fare", "booking_value", "room_revenue", "revenue", "sales"],
                        cost=["operating_cost", "cost", "expense"], returns=["cancellation", "refund", "no_show"]),
        "dimensions": ["route", "origin", "destination", "hotel", "channel", "cabin", "season", "property"],
        "synonyms": {"revpar": "revenue"},
        "kpis": [{"name": "Load factor"}, {"name": "RevPAR"}, {"name": "Cancellation loss"}],
        "alert_templates": [],
        "starter_questions": ["Which routes are loss-making?", "How much do cancellations cost us?",
                              "Which season has the weakest margin?"],
        "drivers": ["empty seats / rooms", "cancellations", "weak routes"],
    },
}


def _load_custom():
    d = Path(__file__).parent / "custom"
    if not d.exists():
        return
    for f in d.glob("*.json"):
        try:
            p = json.loads(f.read_text())
            base = PACKS["general"]
            merged = {**base, **p}
            merged["hints"] = {**base["hints"], **p.get("hints", {})}
            PACKS[merged["id"]] = merged
        except Exception:
            continue


_load_custom()


def get_pack(pack_id: str | None) -> dict:
    return PACKS.get(pack_id or "general", PACKS["general"])


def list_packs() -> list[dict]:
    return [
        {"id": p["id"], "name": p["name"], "icon": p.get("icon", "📦"), "description": p["description"],
         "starter_questions": p["starter_questions"], "kpis": p["kpis"], "drivers": p.get("drivers", [])}
        for p in PACKS.values()
    ]
