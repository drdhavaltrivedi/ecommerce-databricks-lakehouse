#!/usr/bin/env python3
"""Create SQL alerts that fire when the data stops being trustworthy.

gold.data_quality records defects, but a table nobody opens is not monitoring.
These alerts turn the two failure modes that would silently corrupt every
downstream number into notifications:

  1. The cart-tracking gap gets worse. The funnel already compensates for a
     ~54% gap. If that climbs, the correction is carrying more and more weight
     and the funnel becomes mostly inference.

  2. The pipeline silently stops. Stale gold tables look identical to fresh
     ones on a dashboard -- the numbers are simply yesterday's. This catches
     the case where nobody notices for a week.

Alerts are created WITHOUT a schedule and without notification destinations.
Both are deliberate: a schedule spends warehouse time, and adding an email
destination sends mail on someone's behalf. Both are one click in the UI.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

ALERTS = [
    {
        "name": "[ecommerce] Cart tracking gap exceeded 60%",
        "query_name": "[ecommerce] cart tracking gap",
        "sql": """
SELECT pct_affected
FROM ecommerce.gold.data_quality
WHERE check_name = 'purchase_without_cart'
""".strip(),
        "column": "pct_affected",
        "op": "GREATER_THAN",
        "threshold": 60.0,
        "why": (
            "Baseline is ~54%. Above 60% the funnel's cart stage is majority "
            "inferred rather than measured, and view-to-cart conversion should "
            "not be quoted to stakeholders without a caveat."
        ),
    },
    {
        "name": "[ecommerce] Gold tables are stale (>36h)",
        "query_name": "[ecommerce] gold freshness",
        "sql": """
SELECT DATEDIFF(HOUR, MAX(event_date), CURRENT_DATE()) AS hours_since_latest_data
FROM ecommerce.gold.daily_metrics
""".strip(),
        "column": "hours_since_latest_data",
        "op": "GREATER_THAN",
        "threshold": 36.0,
        "why": (
            "The job runs daily at 05:00 UTC. A 36h window tolerates one missed "
            "run without crying wolf, but catches a pipeline that has genuinely "
            "stopped."
        ),
    },
    {
        "name": "[ecommerce] Unlabeled category share exceeded 40%",
        "query_name": "[ecommerce] category labeling",
        "sql": """
SELECT pct_affected
FROM ecommerce.gold.data_quality
WHERE check_name = 'missing_category_code'
""".strip(),
        "column": "pct_affected",
        "op": "GREATER_THAN",
        "threshold": 40.0,
        "why": (
            "Baseline is ~32%. Above 40%, category revenue rankings exclude so "
            "much of the catalog that merchandising decisions based on them "
            "become unsafe."
        ),
    },
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
        print(f"[{e.code}] {e.read().decode()[:500]}", file=sys.stderr)
        raise


def upsert_query(name, sql):
    existing = api("GET", "/api/2.0/sql/queries?page_size=100").get("results", [])
    for q in existing:
        if q.get("display_name") == name:
            api("PATCH", f"/api/2.0/sql/queries/{q['id']}",
                {"query": {"query_text": sql}, "update_mask": "query_text"})
            return q["id"]
    created = api("POST", "/api/2.0/sql/queries", {
        "query": {
            "display_name": name,
            "query_text": sql,
            "warehouse_id": WAREHOUSE_ID,
        }
    })
    return created["id"]


def upsert_alert(spec, query_id):
    condition = {
        "op": spec["op"],
        "operand": {"column": {"name": spec["column"]}},
        "threshold": {"value": {"double_value": spec["threshold"]}},
    }
    payload = {
        "display_name": spec["name"],
        "query_id": query_id,
        "condition": condition,
        "custom_body": spec["why"],
    }
    existing = api("GET", "/api/2.0/sql/alerts?page_size=100").get("results", [])
    for a in existing:
        if a.get("display_name") == spec["name"]:
            api("PATCH", f"/api/2.0/sql/alerts/{a['id']}",
                {"alert": payload,
                 "update_mask": "condition,custom_body,query_id"})
            return a["id"], "updated"
    created = api("POST", "/api/2.0/sql/alerts", {"alert": payload})
    return created["id"], "created"


if __name__ == "__main__":
    for spec in ALERTS:
        qid = upsert_query(spec["query_name"], spec["sql"])
        aid, action = upsert_alert(spec, qid)
        print(f"{action}: {spec['name']}")
        print(f"   {spec['column']} > {spec['threshold']}  ->  {HOST}/sql/alerts/{aid}")
    print("\nAlerts have no schedule and no notification destination by design.")
    print("Add both in the UI: open each alert -> set refresh schedule -> add recipients.")
