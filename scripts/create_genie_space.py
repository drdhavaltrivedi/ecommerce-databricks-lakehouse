#!/usr/bin/env python3
"""Create/update an AI/BI Genie space over the gold layer.

Genie lets non-technical users ask questions in natural language. That is only
useful if it is pointed at the right tables AND told about the data's defects --
otherwise it will confidently report the broken raw funnel (110% cart-to-purchase)
to a business user who has no way to know better.

The instructions therefore do three jobs:
  1. Scope Genie to gold (small, business-named, pre-aggregated)
  2. Warn it about the cart-logging gap and say which columns to trust
  3. Encode grain rules so it does not join or group tables incorrectly

Schema note: the `serialized_space` payload shape is not publicly documented.
It was determined empirically against this workspace's API:
    {"version": 2,
     "data_sources": {"tables": [{"identifier": "cat.schema.table"}]},
     "instructions": {"text_instructions": [{"content": ["..."]}]}}
`content` is an array of plain strings.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

TITLE = "Ecommerce Analytics Genie"
DESCRIPTION = (
    "Ask questions in plain English about store performance: funnel, cart "
    "abandonment, category and brand revenue, buyer behaviour. Corrects for "
    "the known cart-tracking gap."
)

TABLES = [
    "ecommerce.gold.daily_metrics",
    "ecommerce.gold.funnel",
    "ecommerce.gold.cart_abandonment",
    "ecommerce.gold.category_performance",
    "ecommerce.gold.brand_performance",
    "ecommerce.gold.top_products",
    "ecommerce.gold.user_summary",
    "ecommerce.gold.hourly_pattern",
    "ecommerce.gold.data_quality",
    "ecommerce.gold.intent_by_view_depth",
    "ecommerce.gold.cart_conversion_by_price",
    "ecommerce.gold.attach_opportunity",
    "ecommerce.gold.price_change_effect",
]

INSTRUCTIONS = [
    # --- the critical one: stop Genie reporting a broken funnel ---
    "CRITICAL DATA CAVEAT. The source tracking fails to log a cart event for "
    "about 54% of purchasing sessions. Always use ecommerce.gold.funnel, which "
    "is already corrected: it is computed monotonically, so a session that "
    "purchased is credited with reaching the cart stage. NEVER compute a "
    "cart-to-purchase rate by dividing raw purchase sessions by raw cart "
    "sessions -- that yields an impossible rate above 100%. The column "
    "sessions_cart_logged holds the RAW uncorrected count and "
    "purchases_missing_cart_event holds the size of the gap; use those only "
    "when the user asks about data quality or tracking coverage. When you "
    "report funnel numbers, briefly note that the cart stage is partly "
    "inferred because of this tracking gap.",

    # --- other data caveats ---
    "About 32% of source rows have no category_code and 14% have no brand; "
    "these appear as 'unknown'. When ranking categories or brands, say that "
    "unlabeled rows are bucketed as unknown, so labeled totals undercount. "
    "A 'purchase' event is treated as a completed sale -- there is no payment, "
    "refund or fulfilment status in this data. There is no quantity column: "
    "one purchase row is one unit at that price. Currency is the source "
    "currency, unconverted, so report plain numbers without a currency symbol.",

    # --- grain and join rules ---
    "GRAIN RULES. ecommerce.gold.funnel has exactly ONE row covering the whole "
    "period -- never GROUP BY it. ecommerce.gold.daily_metrics is one row per "
    "day; use it for any trend over time and for revenue totals. "
    "ecommerce.gold.hourly_pattern is one row per hour-of-day (0-23) aggregated "
    "across all days -- it is a daily profile, NOT a time series. "
    "ecommerce.gold.user_summary is one row per user; use it for buyer counts "
    "and spend distribution, never for revenue totals. Do NOT join gold tables "
    "to each other: each is independently aggregated and joining them double "
    "counts.",

    # --- business context so answers are useful, not just correct ---
    "BUSINESS CONTEXT. Revenue is heavily concentrated in "
    "electronics.smartphone (about 68% of total) -- flag this as a "
    "concentration risk when relevant. Checkout converts well (about 69% of "
    "carts complete), so the weak step is view-to-cart (about 10%). If asked "
    "where to improve conversion, the upstream discovery step is the larger "
    "opportunity, not checkout. Timestamps are UTC and the store serves a "
    "UTC+3 market, so peak trading at 06:00-11:00 UTC is roughly 09:00-14:00 "
    "local time -- mention local time when discussing time of day.",

    # --- the opportunity tables, and how to talk about them honestly ---
    "OPPORTUNITY TABLES. Four tables identify specific fixable problems, and "
    "each carries a caveat you must repeat when you cite it. "
    "gold.cart_conversion_by_price shows cart-to-purchase is FLAT at about 50% "
    "from $50 to over $1000, so abandonment is NOT driven by price above $50 -- "
    "it is process friction. Below $50 conversion falls to 30%, consistent with "
    "shipping cost as a share of order value. "
    "gold.attach_opportunity shows only 2.12% of smartphone buyers buy anything "
    "else in the same session, against a 15-30% industry norm; note this "
    "measures SAME-SESSION attach only, so it is a floor. "
    "gold.intent_by_view_depth shows users who viewed a product 10+ times "
    "convert at 43.5% versus 0% for a single view, and about $41.6M of value "
    "sits with high-view non-buyers -- an excellent retargeting segment. But "
    "NEVER claim more impressions CAUSE sales: buyers accumulate views on the "
    "way to buying, so this is correlation and is valid for targeting, not for "
    "justifying ad spend. "
    "gold.price_change_effect shows product-days after a >5% price cut convert "
    "at 1.62% versus 1.85% when stable. Always state the confound: prices get "
    "cut BECAUSE items are not selling, so this is not evidence that discounts "
    "suppress demand -- only that discounting is not visibly rescuing those "
    "products. A holdout test is needed for a causal answer.",

    # --- worked examples ---
    "USEFUL QUERIES. Funnel: SELECT sessions_with_view, sessions_with_cart, "
    "sessions_with_purchase, view_to_cart_pct, cart_to_purchase_pct, "
    "view_to_purchase_pct FROM ecommerce.gold.funnel. "
    "Browsed-but-not-bought categories: SELECT category_code, views, purchases, "
    "revenue, view_to_purchase_pct FROM ecommerce.gold.category_performance "
    "WHERE category_code != 'unknown' AND views > 100000 ORDER BY "
    "view_to_purchase_pct ASC. "
    "Abandonment: SELECT SUM(abandoned_sessions), SUM(abandoned_cart_value) "
    "FROM ecommerce.gold.cart_abandonment. "
    "Repeat buyers: SELECT COUNT(*) AS users, SUM(CASE WHEN purchase_count > 0 "
    "THEN 1 ELSE 0 END) AS buyers, SUM(CASE WHEN purchase_count > 1 THEN 1 "
    "ELSE 0 END) AS repeat_buyers FROM ecommerce.gold.user_summary.",
]


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {e.read().decode()[:600]}", file=sys.stderr)
        raise


def build_space():
    return {
        "version": 2,
        # the API rejects an unsorted table list, so sort defensively rather
        # than relying on TABLES being maintained in order
        "data_sources": {"tables": [{"identifier": t} for t in sorted(TABLES)]},
        # exactly one text_instruction is permitted; the separate paragraphs go
        # into its `content` array
        "instructions": {"text_instructions": [{"content": INSTRUCTIONS}]},
    }


def find_existing():
    for s in api("GET", "/api/2.0/genie/spaces").get("spaces", []):
        if s.get("title") == TITLE:
            return s["space_id"]
    return None


if __name__ == "__main__":
    body = {
        "title": TITLE,
        "description": DESCRIPTION,
        "warehouse_id": WAREHOUSE_ID,
        "serialized_space": json.dumps(build_space()),
    }
    existing = find_existing()
    if existing:
        api("PATCH", f"/api/2.0/genie/spaces/{existing}", body)
        space_id = existing
        print("Updated Genie space:", space_id)
    else:
        space_id = api("POST", "/api/2.0/genie/spaces", body)["space_id"]
        print("Created Genie space:", space_id)

    print(f"  tables:       {len(TABLES)}")
    print(f"  instructions: {len(INSTRUCTIONS)}")
    print(f"URL: {HOST}/genie/rooms/{space_id}")
