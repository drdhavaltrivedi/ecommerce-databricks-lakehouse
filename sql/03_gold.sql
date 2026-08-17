-- Gold layer: business-facing aggregates for the dashboard

-- Daily overview: traffic, conversion, revenue
CREATE OR REPLACE TABLE ecommerce.gold.daily_metrics AS
SELECT
  event_date,
  COUNT(DISTINCT user_id) AS unique_users,
  COUNT(DISTINCT user_session) AS sessions,
  COUNT(DISTINCT CASE WHEN event_type = 'view' THEN CONCAT(user_session,'-',product_id) END) AS product_views,
  COUNT(DISTINCT CASE WHEN event_type = 'cart' THEN user_session END) AS sessions_with_cart,
  COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_session END) AS sessions_with_purchase,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS revenue,
  COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchase_events,
  ROUND(COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_session END) * 100.0
        / NULLIF(COUNT(DISTINCT user_session), 0), 2) AS conversion_rate_pct
FROM ecommerce.silver.fact_events
GROUP BY event_date
ORDER BY event_date;

-- Purchase funnel: view -> cart -> purchase, at session level.
--
-- IMPORTANT: the source data under-logs cart events -- ~54% of purchasing
-- sessions have no cart event at all. Counting raw flags yields a nonsensical
-- >100% cart-to-purchase rate. The funnel is therefore computed MONOTONICALLY:
-- a session that purchased is counted as having reached the cart stage, and any
-- session that carted or purchased is counted as having reached the view stage.
-- `sessions_cart_logged` retains the raw (unadjusted) count so the size of the
-- logging gap stays visible rather than being silently smoothed away.
CREATE OR REPLACE TABLE ecommerce.gold.funnel AS
SELECT
  COUNT(*) AS total_sessions,
  SUM(CASE WHEN has_view OR has_cart OR has_purchase THEN 1 ELSE 0 END) AS sessions_with_view,
  SUM(CASE WHEN has_cart OR has_purchase THEN 1 ELSE 0 END) AS sessions_with_cart,
  SUM(CASE WHEN has_purchase THEN 1 ELSE 0 END) AS sessions_with_purchase,
  SUM(CASE WHEN has_cart THEN 1 ELSE 0 END) AS sessions_cart_logged,
  SUM(CASE WHEN has_purchase AND NOT has_cart THEN 1 ELSE 0 END) AS purchases_missing_cart_event,
  ROUND(SUM(CASE WHEN has_cart OR has_purchase THEN 1 ELSE 0 END) * 100.0
        / NULLIF(SUM(CASE WHEN has_view OR has_cart OR has_purchase THEN 1 ELSE 0 END),0), 2) AS view_to_cart_pct,
  ROUND(SUM(CASE WHEN has_purchase THEN 1 ELSE 0 END) * 100.0
        / NULLIF(SUM(CASE WHEN has_cart OR has_purchase THEN 1 ELSE 0 END),0), 2) AS cart_to_purchase_pct,
  ROUND(SUM(CASE WHEN has_purchase THEN 1 ELSE 0 END) * 100.0
        / NULLIF(SUM(CASE WHEN has_view OR has_cart OR has_purchase THEN 1 ELSE 0 END),0), 2) AS view_to_purchase_pct
FROM ecommerce.silver.dim_session;

-- Cart abandonment detail: sessions that added to cart but never purchased
CREATE OR REPLACE TABLE ecommerce.gold.cart_abandonment AS
SELECT
  event_date,
  COUNT(DISTINCT user_session) AS abandoned_sessions,
  COUNT(DISTINCT user_id) AS affected_users,
  SUM(price) AS abandoned_cart_value
FROM (
  SELECT DISTINCT
    f.event_date, f.user_session, f.user_id, f.product_id, f.price
  FROM ecommerce.silver.fact_events f
  JOIN ecommerce.silver.dim_session s ON f.user_session = s.user_session
  WHERE f.event_type = 'cart' AND s.has_purchase = false
)
GROUP BY event_date
ORDER BY event_date;

-- Category performance
CREATE OR REPLACE TABLE ecommerce.gold.category_performance AS
SELECT
  COALESCE(NULLIF(category_code, ''), 'unknown') AS category_code,
  COUNT(DISTINCT CASE WHEN event_type = 'view' THEN CONCAT(user_session,'-',product_id) END) AS views,
  COUNT(DISTINCT CASE WHEN event_type = 'cart' THEN CONCAT(user_session,'-',product_id) END) AS carts,
  COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchases,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS revenue,
  ROUND(COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) * 100.0
        / NULLIF(COUNT(DISTINCT CASE WHEN event_type = 'view' THEN CONCAT(user_session,'-',product_id) END), 0), 2) AS view_to_purchase_pct
FROM ecommerce.silver.fact_events
GROUP BY COALESCE(NULLIF(category_code, ''), 'unknown')
ORDER BY revenue DESC;

-- Brand performance
CREATE OR REPLACE TABLE ecommerce.gold.brand_performance AS
SELECT
  brand,
  COUNT(DISTINCT CASE WHEN event_type = 'view' THEN CONCAT(user_session,'-',product_id) END) AS views,
  COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchases,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS revenue,
  ROUND(AVG(CASE WHEN event_type = 'purchase' THEN price END), 2) AS avg_order_value
FROM ecommerce.silver.fact_events
WHERE brand != 'unknown'
GROUP BY brand
ORDER BY revenue DESC;

-- Top products by revenue
CREATE OR REPLACE TABLE ecommerce.gold.top_products AS
SELECT
  product_id,
  ANY_VALUE(category_code) AS category_code,
  ANY_VALUE(brand) AS brand,
  COUNT(CASE WHEN event_type = 'view' THEN 1 END) AS views,
  COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchases,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS revenue
FROM ecommerce.silver.fact_events
GROUP BY product_id
ORDER BY revenue DESC
LIMIT 100;

-- User-level RFM-style summary (within available date range)
CREATE OR REPLACE TABLE ecommerce.gold.user_summary AS
SELECT
  user_id,
  COUNT(DISTINCT user_session) AS total_sessions,
  MAX(event_date) AS last_active_date,
  DATEDIFF(MAX(event_date), MIN(event_date)) AS active_span_days,
  COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchase_count,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS total_spend
FROM ecommerce.silver.fact_events
GROUP BY user_id;

-- Hourly traffic pattern (for staffing / ad-timing insights)
CREATE OR REPLACE TABLE ecommerce.gold.hourly_pattern AS
SELECT
  HOUR(event_time) AS hour_of_day,
  COUNT(DISTINCT user_session) AS sessions,
  COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchases,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS revenue
FROM ecommerce.silver.fact_events
GROUP BY HOUR(event_time)
ORDER BY hour_of_day;
