#!/usr/bin/env python3
"""Create a Databricks Lakeview dashboard on top of the ecommerce.gold tables."""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

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
        print(e.read().decode(), file=sys.stderr)
        raise


def dataset(name, query):
    return {"name": name, "displayName": name, "queryLines": [query]}


def counter_widget(name, dataset_name, field, title, fmt="number"):
    return {
        "widget": {
            "name": name,
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": dataset_name,
                    "fields": [{"name": field, "expression": f"`{field}`"}],
                    "disaggregated": False,
                },
            }],
            "spec": {
                "version": 2,
                "widgetType": "counter",
                "encodings": {"value": {"fieldName": field, "displayName": title}},
                "frame": {"title": title, "showTitle": True},
            },
        },
    }


def chart_widget(name, dataset_name, x, y, title, widget_type="bar", scale_x="categorical"):
    return {
        "widget": {
            "name": name,
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": dataset_name,
                    "fields": [
                        {"name": x, "expression": f"`{x}`"},
                        {"name": y, "expression": f"`{y}`"},
                    ],
                    "disaggregated": True,
                },
            }],
            "spec": {
                "version": 3,
                "widgetType": widget_type,
                "encodings": {
                    "x": {"fieldName": x, "scale": {"type": scale_x}, "displayName": x},
                    "y": {"fieldName": y, "scale": {"type": "quantitative"}, "displayName": y},
                },
                "frame": {"title": title, "showTitle": True},
            },
        },
    }


def table_widget(name, dataset_name, columns, title):
    return {
        "widget": {
            "name": name,
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": dataset_name,
                    "fields": [{"name": c, "expression": f"`{c}`"} for c in columns],
                    "disaggregated": True,
                },
            }],
            "spec": {
                "version": 1,
                "widgetType": "table",
                "encodings": {
                    "columns": [{"fieldName": c, "displayName": c} for c in columns]
                },
                "frame": {"title": title, "showTitle": True},
            },
        },
    }


def pos(w, x, y, width, height):
    w["position"] = {"x": x, "y": y, "width": width, "height": height}
    return w


datasets = [
    dataset("funnel", "SELECT * FROM ecommerce.gold.funnel"),
    dataset("daily", "SELECT * FROM ecommerce.gold.daily_metrics ORDER BY event_date"),
    dataset("funnel_stages", """
        SELECT '1. Viewed' AS stage, sessions_with_view AS sessions FROM ecommerce.gold.funnel
        UNION ALL SELECT '2. Added to cart', sessions_with_cart FROM ecommerce.gold.funnel
        UNION ALL SELECT '3. Purchased', sessions_with_purchase FROM ecommerce.gold.funnel
        ORDER BY stage
    """),
    dataset("data_quality", "SELECT check_name, description, affected_rows, pct_affected, business_impact FROM ecommerce.gold.data_quality ORDER BY pct_affected DESC"),
    dataset("intent", "SELECT CONCAT(band_order, '. ', view_band) AS view_band, conversion_pct, unconverted_value, unconverted_pairs FROM ecommerce.gold.intent_by_view_depth ORDER BY band_order"),
    dataset("price_bands", "SELECT price_band, cart_conversion_pct, carted_items, abandoned_value FROM ecommerce.gold.cart_conversion_by_price ORDER BY price_band"),
    dataset("attach", "SELECT attached_category, sessions, pct_of_phone_buyers, revenue FROM ecommerce.gold.attach_opportunity ORDER BY sessions DESC LIMIT 8"),
    dataset("repeat_buyers", """
        SELECT
          CASE WHEN purchase_count = 0 THEN '0 - browsed only'
               WHEN purchase_count = 1 THEN '1 purchase'
               WHEN purchase_count BETWEEN 2 AND 5 THEN '2-5 purchases'
               ELSE '6+ purchases' END AS buyer_segment,
          COUNT(*) AS users,
          ROUND(SUM(total_spend), 0) AS total_spend
        FROM ecommerce.gold.user_summary
        GROUP BY 1 ORDER BY 1
    """),
    dataset("abandonment", "SELECT * FROM ecommerce.gold.cart_abandonment ORDER BY event_date"),
    dataset("categories", "SELECT * FROM ecommerce.gold.category_performance WHERE category_code != 'unknown' ORDER BY revenue DESC LIMIT 15"),
    dataset("brands", "SELECT * FROM ecommerce.gold.brand_performance ORDER BY revenue DESC LIMIT 15"),
    dataset("hourly", "SELECT * FROM ecommerce.gold.hourly_pattern ORDER BY hour_of_day"),
    dataset("top_products", "SELECT product_id, category_code, brand, views, purchases, revenue FROM ecommerce.gold.top_products ORDER BY revenue DESC LIMIT 25"),
    dataset("totals", """
        SELECT
          SUM(revenue) AS total_revenue,
          SUM(sessions) AS total_sessions,
          SUM(unique_users) AS total_users,
          ROUND(AVG(conversion_rate_pct), 2) AS avg_conversion_pct
        FROM ecommerce.gold.daily_metrics
    """),
    dataset("abandoned_total", "SELECT SUM(abandoned_cart_value) AS abandoned_value FROM ecommerce.gold.cart_abandonment"),
]

layout = [
    pos(counter_widget("kpi_revenue", "totals", "total_revenue", "Total Revenue"), 0, 0, 1, 3),
    pos(counter_widget("kpi_sessions", "totals", "total_sessions", "Sessions"), 1, 0, 1, 3),
    pos(counter_widget("kpi_users", "totals", "total_users", "Unique Users"), 2, 0, 1, 3),
    pos(counter_widget("kpi_conv", "totals", "avg_conversion_pct", "Avg Conversion %"), 3, 0, 1, 3),
    pos(counter_widget("kpi_abandoned", "abandoned_total", "abandoned_value", "Abandoned Cart Value"), 4, 0, 2, 3),

    pos(chart_widget("funnel_chart", "funnel_stages", "stage", "sessions", "Purchase Funnel (sessions)"), 0, 3, 3, 6),
    pos(chart_widget("daily_revenue", "daily", "event_date", "revenue", "Daily Revenue", widget_type="line", scale_x="temporal"), 3, 3, 3, 6),

    pos(chart_widget("daily_conv", "daily", "event_date", "conversion_rate_pct", "Daily Conversion Rate %", widget_type="line", scale_x="temporal"), 0, 9, 3, 6),
    pos(chart_widget("abandon_trend", "abandonment", "event_date", "abandoned_cart_value", "Abandoned Cart Value by Day", widget_type="line", scale_x="temporal"), 3, 9, 3, 6),

    pos(chart_widget("cat_revenue", "categories", "category_code", "revenue", "Top Categories by Revenue"), 0, 15, 3, 7),
    pos(chart_widget("brand_revenue", "brands", "brand", "revenue", "Top Brands by Revenue"), 3, 15, 3, 7),

    pos(chart_widget("hourly_rev", "hourly", "hour_of_day", "revenue", "Revenue by Hour of Day"), 0, 22, 3, 6),
    pos(chart_widget("cat_conv", "categories", "category_code", "view_to_purchase_pct", "Category View-to-Purchase %"), 3, 22, 3, 6),

    pos(chart_widget("buyer_segments", "repeat_buyers", "buyer_segment", "users", "Users by Purchase Frequency"), 0, 28, 3, 6),
    pos(chart_widget("buyer_spend", "repeat_buyers", "buyer_segment", "total_spend", "Revenue by Buyer Segment"), 3, 28, 3, 6),

    pos(chart_widget("products_chart", "top_products", "product_id", "revenue",
                     "Top Products by Revenue"), 0, 34, 6, 8),

    # --- opportunity analysis: the actionable findings ---
    pos(chart_widget("intent_conv", "intent", "view_band", "conversion_pct",
                     "Conversion by Repeat Views (1 view = 0%, 10+ views = 43%)"), 0, 42, 3, 6),
    pos(chart_widget("intent_value", "intent", "view_band", "unconverted_value",
                     "Unconverted Value by Intent Band (retargeting pool)"), 3, 42, 3, 6),

    pos(chart_widget("price_conv", "price_bands", "price_band", "cart_conversion_pct",
                     "Cart Conversion by Price - flat above $50, so not a price problem"), 0, 48, 3, 6),
    pos(chart_widget("attach_chart", "attach", "attached_category", "sessions",
                     "What Phone Buyers Also Buy (attach rate only 2.1%)"), 3, 48, 3, 6),

    pos(chart_widget("dq_chart", "data_quality", "check_name", "pct_affected",
                     "Data Quality - read before trusting the numbers above"), 0, 54, 6, 7),
]

serialized = {
    "datasets": datasets,
    "pages": [{
        "name": "overview",
        "displayName": "Ecommerce Overview",
        "layout": layout,
    }],
}

DISPLAY_NAME = "Ecommerce Behavior Analytics"


def find_existing():
    """Return the id of an existing dashboard with our display name, if any,
    so repeated runs update in place instead of piling up duplicates."""
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
        result = api("PATCH", f"/api/2.0/lakeview/dashboards/{existing}", body)
        dashboard_id = result["dashboard_id"]
        print("Updated dashboard:", dashboard_id)
    else:
        result = api("POST", "/api/2.0/lakeview/dashboards", body)
        dashboard_id = result["dashboard_id"]
        print("Created dashboard:", dashboard_id)
    api("POST", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
        {"embed_credentials": True, "warehouse_id": WAREHOUSE_ID})
    print("Published.")
    print(f"URL: {HOST}/dashboardsv3/{dashboard_id}/published")
