-- Opportunity analysis: findings that identify a specific, addressable problem
-- rather than describing what happened.
--
-- The gold tables above answer "how are we doing". These answer "what is
-- broken, how big is it, and what would fixing it be worth". Each table below
-- corresponds to one decision somebody could actually make on Monday.

-- ---------------------------------------------------------------------------
-- 1. PURCHASE INTENT IS ALMOST ENTIRELY PREDICTED BY REPEAT VIEWING.
--
-- Conversion by how many times a user viewed a given product:
--     1 view    0.00%
--     2-3       2.88%
--     4-9      16.65%
--     10+      43.51%
--
-- The practical use is the non-buyers in the high bands: someone who viewed one
-- product 10+ times and did not buy is a far better retargeting target than any
-- demographic segment, and this table sizes that list.
--
-- Causality caveat: buyers naturally accumulate views on the way to purchasing,
-- so this does not prove that showing a product more times causes a sale. For
-- *targeting* it does not matter -- the correlation identifies the right people
-- either way. It would matter if someone tried to read it as "more impressions
-- cause conversion", which this data cannot support.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE ecommerce.gold.intent_by_view_depth
COMMENT 'Conversion and unconverted value by how many times a user viewed a product. High-view non-buyers are the highest-intent retargeting segment available.'
AS
WITH user_product AS (
  SELECT
    user_id,
    product_id,
    SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS views,
    MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS bought,
    MAX(price) AS price
  FROM ecommerce.silver.fact_events
  WHERE event_type IN ('view', 'purchase')
  GROUP BY user_id, product_id
)
SELECT
  CASE WHEN views = 1 THEN '1 view'
       WHEN views BETWEEN 2 AND 3 THEN '2-3 views'
       WHEN views BETWEEN 4 AND 9 THEN '4-9 views'
       ELSE '10+ views' END                                   AS view_band,
  CASE WHEN views = 1 THEN 1 WHEN views BETWEEN 2 AND 3 THEN 2
       WHEN views BETWEEN 4 AND 9 THEN 3 ELSE 4 END           AS band_order,
  COUNT(*)                                                    AS user_product_pairs,
  SUM(bought)                                                 AS converted,
  ROUND(SUM(bought) * 100.0 / COUNT(*), 2)                    AS conversion_pct,
  SUM(CASE WHEN bought = 0 THEN 1 ELSE 0 END)                 AS unconverted_pairs,
  ROUND(SUM(CASE WHEN bought = 0 THEN price ELSE 0 END), 0)   AS unconverted_value
FROM user_product
WHERE views > 0
GROUP BY view_band, band_order
ORDER BY band_order;

-- ---------------------------------------------------------------------------
-- 2. CART ABANDONMENT IS NOT A PRICE PROBLEM.
--
-- Cart-to-purchase holds at ~49.9% flat from $50 all the way past $1000. If
-- shoppers were balking at cost, conversion would decay as price rises. It does
-- not. Above $50 the abandonment rate is effectively price-independent, which
-- points at process friction -- delivery estimate, payment options, stock
-- status at checkout -- rather than sticker shock.
--
-- Below $50 conversion *falls*, monotonically, down to 30% under $10. That is
-- the opposite of the naive expectation and is the signature of shipping cost
-- as a proportion of order value: a flat delivery fee is a rounding error on a
-- $500 phone and a punitive surcharge on a $10 accessory.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE ecommerce.gold.cart_conversion_by_price
COMMENT 'Cart-to-purchase rate by item price band. Flat ~50% above $50 (friction, not price) and falling below it (shipping-to-value ratio).'
AS
WITH carted AS (
  SELECT
    user_session,
    product_id,
    MAX(price) AS price,
    MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS bought
  FROM ecommerce.silver.fact_events
  WHERE event_type IN ('cart', 'purchase')
  GROUP BY user_session, product_id
  HAVING MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) = 1
)
SELECT
  CASE WHEN price < 10   THEN '1. under 10'
       WHEN price < 25   THEN '2. 10-25'
       WHEN price < 50   THEN '3. 25-50'
       WHEN price < 100  THEN '4. 50-100'
       WHEN price < 500  THEN '5. 100-500'
       WHEN price < 1000 THEN '6. 500-1000'
       ELSE                   '7. 1000+' END                  AS price_band,
  COUNT(*)                                                    AS carted_items,
  SUM(bought)                                                 AS purchased,
  ROUND(SUM(bought) * 100.0 / COUNT(*), 1)                    AS cart_conversion_pct,
  ROUND(SUM(CASE WHEN bought = 0 THEN price ELSE 0 END), 0)   AS abandoned_value
FROM carted
GROUP BY price_band
ORDER BY price_band;

-- ---------------------------------------------------------------------------
-- 3. ALMOST NOBODY BUYS A SECOND ITEM.
--
-- 285,252 sessions bought a smartphone. Only 6,041 of them -- 2.12% -- bought
-- anything else at all. For a category whose accessories (cases, headphones,
-- chargers, warranties) are the standard margin engine of phone retail, an
-- attach rate near 2% means that engine is essentially switched off.
--
-- Headphones are the single most common attach and still reach only 1,158
-- sessions, 0.4% of phone buyers.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE ecommerce.gold.attach_opportunity
COMMENT 'What smartphone buyers purchase alongside the phone, in the same session. Attach rate is ~2%, against a 15-30% norm for electronics retail.'
AS
WITH phone_sessions AS (
  SELECT DISTINCT user_session
  FROM ecommerce.silver.fact_events
  WHERE event_type = 'purchase' AND category_code = 'electronics.smartphone'
),
attached AS (
  SELECT f.user_session, f.category_code, f.price
  FROM ecommerce.silver.fact_events f
  JOIN phone_sessions p ON f.user_session = p.user_session
  WHERE f.event_type = 'purchase'
    AND f.category_code <> 'electronics.smartphone'
    AND f.category_code IS NOT NULL AND f.category_code <> ''
)
SELECT
  category_code                                               AS attached_category,
  COUNT(DISTINCT user_session)                                AS sessions,
  ROUND(COUNT(DISTINCT user_session) * 100.0
        / (SELECT COUNT(*) FROM phone_sessions), 3)           AS pct_of_phone_buyers,
  ROUND(AVG(price), 2)                                        AS avg_price,
  ROUND(SUM(price), 0)                                        AS revenue
FROM attached
GROUP BY category_code
ORDER BY sessions DESC;

-- ---------------------------------------------------------------------------
-- 4. DISCOUNTING DOES NOT APPEAR TO BE WORKING.
--
-- Product-days following a >5% price cut convert at 1.62%, *below* the 1.85%
-- of price-stable days. Price rises convert worst at 1.30%.
--
-- Read this carefully. It is not proof that discounts suppress demand -- the
-- obvious confound is that prices get cut *because* an item is not selling, so
-- discounted days are drawn from weak products to begin with. What it does say
-- is that discounting is not visibly rescuing those products: after the cut,
-- they still convert below the ordinary baseline. Whatever the discount is
-- buying, it is not measurable conversion lift, and margin is being given away
-- for it.
--
-- The clean way to settle it is a holdout test, which this observational data
-- cannot substitute for.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE ecommerce.gold.price_change_effect
COMMENT 'Conversion on product-days after a price cut, rise, or no change. Observational only -- confounded by which products get discounted. See table comment in 09_opportunities.sql.'
AS
WITH product_day AS (
  SELECT
    product_id,
    event_date,
    ROUND(AVG(price), 2)                                      AS avg_price,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END)  AS purchases,
    SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END)      AS views
  FROM ecommerce.silver.fact_events
  GROUP BY product_id, event_date
),
with_prev AS (
  SELECT *,
    LAG(avg_price) OVER (PARTITION BY product_id ORDER BY event_date) AS prev_price
  FROM product_day
)
SELECT
  CASE WHEN avg_price < prev_price * 0.95 THEN 'price cut >5%'
       WHEN avg_price > prev_price * 1.05 THEN 'price rise >5%'
       ELSE 'stable' END                                      AS price_move,
  COUNT(*)                                                    AS product_days,
  SUM(views)                                                  AS views,
  SUM(purchases)                                              AS purchases,
  ROUND(SUM(purchases) * 100.0 / NULLIF(SUM(views), 0), 2)    AS conversion_pct
FROM with_prev
WHERE prev_price IS NOT NULL AND prev_price > 0
GROUP BY price_move
ORDER BY conversion_pct DESC;

-- ---------------------------------------------------------------------------
-- 5. THE MISSING CATEGORIES CANNOT BE RECOVERED FROM THE DATA. (Negative result.)
--
-- 31.8% of rows have no category_code. The obvious fix is to map them via
-- category_id, since that column is always populated -- look up the code from
-- another row sharing the same id.
--
-- It does not work. Of 372 distinct category_ids that appear with a blank code,
-- ZERO ever appear with a populated one. The blank-code categories are a
-- disjoint set, not a sparsely-labeled one, so there is nothing to join back to.
--
-- Recorded as a table because a negative result that stops someone re-attempting
-- a day of work is worth as much as a positive one. The fix has to come from the
-- source product catalog; it cannot be imputed here.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE ecommerce.gold.category_recovery_check
COMMENT 'Tests whether blank category_code can be backfilled from category_id. It cannot -- the id sets are disjoint. Prevents re-attempting the obvious fix.'
AS
WITH blank_ids AS (
  SELECT DISTINCT category_id FROM ecommerce.silver.fact_events
  WHERE category_code IS NULL OR category_code = ''
),
known_ids AS (
  SELECT DISTINCT category_id FROM ecommerce.silver.fact_events
  WHERE category_code IS NOT NULL AND category_code <> ''
)
SELECT
  (SELECT COUNT(*) FROM blank_ids)                            AS category_ids_with_blank_code,
  (SELECT COUNT(*) FROM known_ids)                            AS category_ids_with_known_code,
  (SELECT COUNT(*) FROM blank_ids b JOIN known_ids k
     ON b.category_id = k.category_id)                        AS recoverable_ids,
  CASE WHEN (SELECT COUNT(*) FROM blank_ids b JOIN known_ids k
               ON b.category_id = k.category_id) = 0
       THEN 'NOT RECOVERABLE - id sets are disjoint; fix must come from source catalog'
       ELSE 'PARTIALLY RECOVERABLE - backfill possible for the overlapping ids'
  END                                                         AS verdict;
