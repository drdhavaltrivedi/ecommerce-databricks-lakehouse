-- Data quality: surface the issues that would otherwise silently corrupt the
-- business metrics. Each row is one check, with a verdict and the impact.

CREATE OR REPLACE TABLE ecommerce.gold.data_quality AS
WITH src AS (SELECT * FROM ecommerce.bronze.events),
     sess AS (SELECT * FROM ecommerce.silver.dim_session)
SELECT * FROM (
  SELECT
    'missing_category_code' AS check_name,
    'Rows with no category_code' AS description,
    (SELECT COUNT(*) FROM src WHERE category_code IS NULL OR category_code = '') AS affected_rows,
    ROUND((SELECT COUNT(*) FROM src WHERE category_code IS NULL OR category_code = '') * 100.0
          / (SELECT COUNT(*) FROM src), 2) AS pct_affected,
    'Category-level revenue and conversion undercount; unlabeled products are bucketed as unknown' AS business_impact

  UNION ALL SELECT
    'missing_brand',
    'Rows with no brand',
    (SELECT COUNT(*) FROM src WHERE brand IS NULL OR brand = ''),
    ROUND((SELECT COUNT(*) FROM src WHERE brand IS NULL OR brand = '') * 100.0
          / (SELECT COUNT(*) FROM src), 2),
    'Brand performance excludes these rows entirely; brand ranking is biased toward well-tagged brands'

  UNION ALL SELECT
    'purchase_without_cart',
    'Sessions with a purchase but no cart event',
    (SELECT COUNT(*) FROM sess WHERE has_purchase AND NOT has_cart),
    ROUND((SELECT COUNT(*) FROM sess WHERE has_purchase AND NOT has_cart) * 100.0
          / NULLIF((SELECT COUNT(*) FROM sess WHERE has_purchase), 0), 2),
    'Cart step is under-logged. A naive view>cart>purchase funnel yields >100% cart-to-purchase and understates cart adds. Funnel must be computed monotonically'

  UNION ALL SELECT
    'purchase_without_view',
    'Sessions with a purchase but no view event',
    (SELECT COUNT(*) FROM sess WHERE has_purchase AND NOT has_view),
    ROUND((SELECT COUNT(*) FROM sess WHERE has_purchase AND NOT has_view) * 100.0
          / NULLIF((SELECT COUNT(*) FROM sess WHERE has_purchase), 0), 2),
    'Small volume, but indicates sessions starting mid-journey (deep link, resumed session) - top of funnel is slightly understated'

  UNION ALL SELECT
    'zero_or_negative_price',
    'Event rows with price <= 0',
    (SELECT COUNT(*) FROM ecommerce.silver.fact_events WHERE price <= 0),
    ROUND((SELECT COUNT(*) FROM ecommerce.silver.fact_events WHERE price <= 0) * 100.0
          / (SELECT COUNT(*) FROM ecommerce.silver.fact_events), 2),
    'Free or mispriced items distort AOV and revenue if not excluded from pricing analysis'

  UNION ALL SELECT
    'multiday_sessions',
    'Sessions spanning more than 24 hours',
    (SELECT COUNT(*) FROM sess WHERE session_end > session_start + INTERVAL 24 HOURS),
    ROUND((SELECT COUNT(*) FROM sess WHERE session_end > session_start + INTERVAL 24 HOURS) * 100.0
          / (SELECT COUNT(*) FROM sess), 2),
    'user_session ids are reused across visits, inflating session duration and depressing per-session conversion'
) ORDER BY pct_affected DESC;
