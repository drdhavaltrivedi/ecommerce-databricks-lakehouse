#!/usr/bin/env python3
"""Create SQL alerts that fire when the data stops being trustworthy, on the
Alerts V2 API.

gold.data_quality records defects, but a table nobody opens is not monitoring.
These alerts turn the two failure modes that would silently corrupt every
downstream number into notifications:

  1. The cart-tracking gap gets worse. The funnel already compensates for a
     ~54% gap. If that climbs, the correction is carrying more and more weight
     and the funnel becomes mostly inference.

  2. The pipeline silently stops. Stale gold tables look identical to fresh
     ones on a dashboard -- the numbers are simply yesterday's. This catches
     the case where nobody notices for a week.

Each alert is self-contained (query text inline) and runs on a daily
schedule, notifying a shared email notification destination -- so a breach
actually reaches someone instead of sitting silent in the Alerts tab.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

NOTIFICATION_DESTINATION_NAME = "Dashboard alert email"
NOTIFICATION_EMAIL = "dhaval.m@brilworks.com"

ALERTS = [
    {
        "name": "[ecommerce] Cart tracking gap exceeded 60%",
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


def upsert_notification_destination():
    existing = api("GET", "/api/2.0/notification-destinations").get("results", [])
    for d in existing:
        if d.get("display_name") == NOTIFICATION_DESTINATION_NAME:
            return d["id"]
    created = api("POST", "/api/2.0/notification-destinations", {
        "display_name": NOTIFICATION_DESTINATION_NAME,
        "config": {"email": {"addresses": [NOTIFICATION_EMAIL]}},
    })
    return created["id"]


def upsert_alert(spec, destination_id):
    payload = {
        "display_name": spec["name"],
        "query_text": spec["sql"],
        "warehouse_id": WAREHOUSE_ID,
        "custom_body": spec["why"],
        "evaluation": {
            "source": {"name": spec["column"]},
            "comparison_operator": spec["op"],
            "threshold": {"value": {"double_value": spec["threshold"]}},
            "notification": {
                "notify_on_ok": True,
                "subscriptions": [{"destination_id": destination_id}],
            },
        },
        "schedule": {
            "quartz_cron_schedule": "0 0 6 * * ?",  # daily 06:00 UTC
            "timezone_id": "UTC",
            "pause_status": "UNPAUSED",
        },
    }
    existing = api("GET", "/api/2.0/alerts?page_size=100").get("results", [])
    for a in existing:
        if a.get("display_name") == spec["name"]:
            api("PATCH", f"/api/2.0/alerts/{a['id']}",
                {"alert": payload, "update_mask": "display_name,query_text,warehouse_id,custom_body,evaluation,schedule"})
            return a["id"], "updated"
    created = api("POST", "/api/2.0/alerts", payload)
    return created["id"], "created"


if __name__ == "__main__":
    destination_id = upsert_notification_destination()
    print(f"Notification destination: {NOTIFICATION_DESTINATION_NAME} ({NOTIFICATION_EMAIL}) -> {destination_id}\n")
    for spec in ALERTS:
        aid, action = upsert_alert(spec, destination_id)
        print(f"{action}: {spec['name']}")
        print(f"   {spec['column']} > {spec['threshold']}  ->  {HOST}/sql/alerts/{aid}")
    print(f"\nAlerts run daily (06:00 UTC) and notify {NOTIFICATION_EMAIL} on breach and on recovery.")
