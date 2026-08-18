#!/usr/bin/env python3
"""Build the booth/demo dashboard.

This is NOT the analysis dashboard. The main one has ~18 widgets and is built
for someone sitting down with it. A trade-show visitor gives you seconds while
walking past, from about three feet away, over someone else's shoulder.

So this one is deliberately sparse:
  - Four big numbers, each one a headline a retailer cares about
  - One chart, chosen because it is instantly surprising: cart conversion is
    FLAT across a 20x price range, which kills the "abandonment is a pricing
    problem" assumption everyone walks up with
  - One attach chart, because it is the clearest money-on-the-table story

Nothing else. Every widget removed is a widget not competing for attention.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

DISPLAY_NAME = "Ecommerce Analytics - Booth Demo"


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


def dataset(name, query):
    return {"name": name, "displayName": name, "queryLines": [query]}


def counter(name, ds, field, title):
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds,
            "fields": [{"name": field, "expression": f"`{field}`"}],
            "disaggregated": False}}],
        "spec": {"version": 2, "widgetType": "counter",
                 "encodings": {"value": {"fieldName": field, "displayName": title}},
                 "frame": {"title": title, "showTitle": True}},
    }}


def chart(name, ds, x, y, title, widget_type="bar"):
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds,
            "fields": [{"name": x, "expression": f"`{x}`"},
                       {"name": y, "expression": f"`{y}`"}],
            "disaggregated": True}}],
        "spec": {"version": 3, "widgetType": widget_type,
                 "encodings": {
                     "x": {"fieldName": x, "scale": {"type": "categorical"}, "displayName": x},
                     "y": {"fieldName": y, "scale": {"type": "quantitative"}, "displayName": y}},
                 "frame": {"title": title, "showTitle": True}},
    }}


def markdown(name, text):
    return {"widget": {"name": name, "textbox_spec": text}}


def pos(w, x, y, width, height):
    w["position"] = {"x": x, "y": y, "width": width, "height": height}
    return w


datasets = [
    dataset("headline", """
        SELECT
          (SELECT ROUND(SUM(revenue)/1e6,1) FROM ecommerce.gold.daily_metrics)            AS revenue_m,
          (SELECT ROUND(SUM(abandoned_cart_value)/1e6,1)
             FROM ecommerce.gold.cart_abandonment)                                        AS abandoned_m,
          (SELECT ROUND(SUM(unconverted_value)/1e6,1)
             FROM ecommerce.gold.intent_by_view_depth WHERE view_band = '10+ views')      AS intent_pool_m,
          -- NB: must count DISTINCT sessions. Summing the per-category counts in
          -- gold.attach_opportunity double-counts any session that bought two
          -- different attach categories, which inflates 2.12% to 2.30%.
          (SELECT ROUND(COUNT(DISTINCT a.user_session)*100.0
                        / COUNT(DISTINCT p.user_session), 2)
             FROM (SELECT DISTINCT user_session FROM ecommerce.silver.fact_events
                    WHERE event_type='purchase'
                      AND category_code='electronics.smartphone') p
             LEFT JOIN (SELECT DISTINCT user_session FROM ecommerce.silver.fact_events
                         WHERE event_type='purchase'
                           AND category_code<>'electronics.smartphone'
                           AND category_code IS NOT NULL AND category_code<>'') a
               ON p.user_session=a.user_session)                                          AS attach_pct
    """),
    dataset("price_bands", """
        SELECT price_band, cart_conversion_pct
        FROM ecommerce.gold.cart_conversion_by_price ORDER BY price_band
    """),
    dataset("attach", """
        SELECT attached_category, sessions
        FROM ecommerce.gold.attach_opportunity ORDER BY sessions DESC LIMIT 6
    """),
    dataset("intent", """
        SELECT view_band, conversion_pct
        FROM ecommerce.gold.intent_by_view_depth ORDER BY band_order
    """),
]

widgets = [
    pos(markdown("title",
        "# 42,448,764 real shopping events, analysed\n"
        "### Three things this store did not know it was losing money on"), 0, 0, 6, 2),

    pos(counter("c_rev",    "headline", "revenue_m",     "Revenue analysed ($M)"),        0, 2, 3, 3),
    pos(counter("c_aband",  "headline", "abandoned_m",   "Left in abandoned carts ($M)"), 3, 2, 3, 3),
    pos(counter("c_intent", "headline", "intent_pool_m", "Ready-to-buy, never asked ($M)"), 0, 5, 3, 3),
    pos(counter("c_attach", "headline", "attach_pct",    "Phone buyers sold an accessory (%)"), 3, 5, 3, 3),

    pos(markdown("hook",
        "## Everyone assumes cart abandonment is about price.\n"
        "### It isn't. Conversion is flat from \\$50 to \\$1,000+ "
        "— so it's checkout friction, not cost."), 0, 8, 6, 2),

    pos(chart("price_chart", "price_bands", "price_band", "cart_conversion_pct",
              "Cart conversion by price - flat above $50"), 0, 10, 6, 7),

    pos(chart("intent_chart", "intent", "view_band", "conversion_pct",
              "Viewed it 10+ times? 43% buy. Viewed once? Nobody."), 0, 17, 3, 6),
    pos(chart("attach_chart", "attach", "attached_category", "sessions",
              "What phone buyers also buy - only 2.1% buy anything"), 3, 17, 3, 6),
]

serialized = {
    "datasets": datasets,
    "pages": [{"name": "booth", "displayName": "Booth Demo", "layout": widgets}],
}


def find_existing():
    res = api("GET", "/api/2.0/lakeview/dashboards?page_size=100")
    for d in res.get("dashboards", []):
        if d.get("display_name") == DISPLAY_NAME and d.get("lifecycle_state") != "TRASHED":
            return d["dashboard_id"]
    return None


if __name__ == "__main__":
    body = {
        "display_name": DISPLAY_NAME,
        "warehouse_id": WAREHOUSE_ID,
        "serialized_dashboard": json.dumps(serialized),
    }
    existing = find_existing()
    if existing:
        api("PATCH", f"/api/2.0/lakeview/dashboards/{existing}", body)
        did = existing
        print("Updated booth dashboard:", did)
    else:
        did = api("POST", "/api/2.0/lakeview/dashboards", body)["dashboard_id"]
        print("Created booth dashboard:", did)

    api("POST", f"/api/2.0/lakeview/dashboards/{did}/published",
        {"embed_credentials": True, "warehouse_id": WAREHOUSE_ID})
    print("Published.")
    print(f"URL: {HOST}/dashboardsv3/{did}/published")
