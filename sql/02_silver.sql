-- Silver layer: typed, cleaned, deduplicated, with derived dimensions

-- Dimension: products (latest known brand/category per product_id)
CREATE OR REPLACE TABLE ecommerce.silver.dim_product AS
SELECT
  product_id,
  category_id,
  category_code,
  COALESCE(NULLIF(category_code, ''), 'unknown') AS category_code_clean,
  SPLIT(category_code, '\\.')[0] AS category_l1,
  SPLIT(category_code, '\\.')[1] AS category_l2,
  brand,
  COALESCE(NULLIF(brand, ''), 'unknown') AS brand_clean,
  price
FROM (
  SELECT
    CAST(product_id AS BIGINT) AS product_id,
    CAST(category_id AS DECIMAL(30,0)) AS category_id,
    category_code,
    brand,
    CAST(price AS DOUBLE) AS price,
    ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY event_time DESC) AS rn
  FROM ecommerce.bronze.events
  WHERE product_id IS NOT NULL
)
WHERE rn = 1;

-- Fact: cleaned, typed, deduplicated event stream
CREATE OR REPLACE TABLE ecommerce.silver.fact_events AS
SELECT DISTINCT
  CAST(event_time AS TIMESTAMP) AS event_time,
  CAST(event_time AS DATE) AS event_date,
  event_type,
  CAST(product_id AS BIGINT) AS product_id,
  CAST(category_id AS DECIMAL(30,0)) AS category_id,
  category_code,
  COALESCE(NULLIF(brand, ''), 'unknown') AS brand,
  CAST(price AS DOUBLE) AS price,
  CAST(user_id AS BIGINT) AS user_id,
  user_session
FROM ecommerce.bronze.events
WHERE event_time IS NOT NULL
  AND user_session IS NOT NULL
  AND event_type IN ('view','cart','purchase','remove_from_cart');

-- Dimension: sessions with funnel-stage flags
CREATE OR REPLACE TABLE ecommerce.silver.dim_session AS
SELECT
  user_session,
  MIN(user_id) AS user_id,
  MIN(event_time) AS session_start,
  MAX(event_time) AS session_end,
  COUNT(*) AS event_count,
  COUNT(DISTINCT product_id) AS distinct_products,
  MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) = 1 AS has_view,
  MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) = 1 AS has_cart,
  MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) = 1 AS has_purchase,
  SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS session_revenue
FROM ecommerce.silver.fact_events
GROUP BY user_session;
