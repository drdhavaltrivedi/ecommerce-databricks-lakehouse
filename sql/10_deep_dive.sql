-- Deep dive: three follow-up investigations opened by the Oct+Nov rebuild.
-- Each resolves (or partially resolves) an open question from docs/INSIGHTS.md
-- and docs/OPPORTUNITIES.md rather than introducing a new unrelated finding.

-- ---------------------------------------------------------------------------
-- 1. DOES SALE-DAY COORDINATION EXPLAIN THE DISCOUNT REVERSAL?
--
-- opportunities #4 found that price-cut conversion flips sign between October
-- (cuts underperform) and November (cuts outperform). Hypothesis: November's
-- cuts are disproportionately coordinated, calendar-driven promotions (Black
-- Friday/Cyber Monday) rather than October's more likely reactive markdowns.
--
-- Tests it using same-day-cut-count as a proxy for "planned sale" vs
-- "isolated markdown" -- the closest read to causal available without a true
-- experiment. Nov 29 2019 (the real Black Friday date) and Nov 30 (Cyber
-- Monday) surface automatically as the two highest-volume cut days with no
-- calendar lookup required, which is itself a sanity check that the proxy is
-- measuring something real.
--
-- RESULT: partial explanation. Mega sale days (Black Friday/Cyber Monday)
-- convert best (1.98%) of any tier, and "elevated" multi-product sale days
-- (moderate coordinated markdowns, not the two biggest) convert WORST
-- (1.51%) -- worse than isolated single-product cuts (1.71%). That pattern
-- holds in both months. But isolated/background cuts *themselves* still
-- improved from October to November (1.66% -> 1.75%), a smaller gap than the
-- raw month-level reversal but not zero -- so coordinated-sale-day timing
-- explains part of the reversal, not all of it. See finding 2 below for the
-- likely remainder.
CREATE OR REPLACE TABLE ecommerce.gold.discount_tier_analysis
COMMENT 'Price-cut conversion by same-day-cut-count tier (mega/elevated/background), the proxy used to test whether the Oct-to-Nov discount reversal is explained by coordinated sale-day timing. Partial explanation -- see table comment in sql/10_deep_dive.sql.'
AS
WITH product_day AS (
  SELECT product_id, event_date,
         SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchases,
         SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS views,
         ROUND(AVG(price), 2) AS avg_price
  FROM ecommerce.silver.fact_events
  GROUP BY product_id, event_date
),
with_prev AS (
  SELECT *,
    LAG(avg_price) OVER (PARTITION BY product_id ORDER BY event_date) AS prev_price
  FROM product_day
),
cuts AS (
  SELECT event_date, product_id, views, purchases
  FROM with_prev
  WHERE prev_price IS NOT NULL AND prev_price > 0 AND avg_price < prev_price * 0.95
),
daily_cut_count AS (
  SELECT event_date, COUNT(DISTINCT product_id) AS products_cut_that_day
  FROM cuts GROUP BY event_date
)
SELECT
  DATE_TRUNC('MONTH', c.event_date) AS month,
  CASE WHEN d.products_cut_that_day >= 3000 THEN '1. mega sale day (Black Friday / Cyber Monday)'
       WHEN d.products_cut_that_day >= 2118 THEN '2. elevated (top decile, not mega)'
       ELSE '3. background / isolated' END AS sale_day_tier,
  COUNT(DISTINCT c.event_date) AS days,
  SUM(c.purchases) AS purchases,
  SUM(c.views) AS views,
  ROUND(SUM(c.purchases) * 100.0 / NULLIF(SUM(c.views), 0), 2) AS conversion_pct
FROM cuts c
JOIN daily_cut_count d ON c.event_date = d.event_date
GROUP BY 1, 2
ORDER BY 1, 2;

-- ---------------------------------------------------------------------------
-- 2. IS NOVEMBER'S BETTER CONVERSION DRIVEN BY NEW OR RETURNING USERS?
--
-- Hypothesis going in: a Black-Friday traffic surge brings low-intent
-- browsers who dilute conversion. RESULT: the opposite. Within November,
-- users NEW to November convert at 1.56%, while users RETURNING from October
-- convert at only 1.37% during that same month. New-to-November traffic is
-- plausibly Black-Friday-acquired (paid/organic search for deals) and arrives
-- already purchase-intent-qualified; the existing October base returning in
-- November skews toward habitual, lower-intent browsing. This is the likely
-- remainder of the discount-reversal and funnel-improvement story that
-- sale-day timing alone (finding 1) doesn't fully explain.
CREATE OR REPLACE TABLE ecommerce.gold.november_cohort_behavior
COMMENT 'November-only conversion split by whether the user is new to November or returning from October. New-to-November users convert BETTER (1.56% vs 1.37%), the opposite of the low-intent-dilution hypothesis -- likely explained by Black-Friday-acquired traffic arriving pre-qualified.'
AS
WITH first_seen AS (
  SELECT user_id, MIN(event_date) AS first_date
  FROM ecommerce.silver.fact_events
  WHERE user_id IS NOT NULL
  GROUP BY user_id
)
SELECT
  CASE WHEN fs.first_date < '2019-11-01' THEN 'returning (first seen October)'
       ELSE 'new to November' END AS user_cohort,
  COUNT(DISTINCT f.user_id) AS users,
  SUM(CASE WHEN f.event_type = 'view' THEN 1 ELSE 0 END) AS views,
  SUM(CASE WHEN f.event_type = 'purchase' THEN 1 ELSE 0 END) AS purchases,
  ROUND(SUM(CASE WHEN f.event_type = 'purchase' THEN 1 ELSE 0 END) * 100.0
        / NULLIF(SUM(CASE WHEN f.event_type = 'view' THEN 1 ELSE 0 END), 0), 2) AS november_conversion_pct
FROM ecommerce.silver.fact_events f
JOIN first_seen fs ON f.user_id = fs.user_id
WHERE f.event_date >= '2019-11-01'
GROUP BY 1;

-- ---------------------------------------------------------------------------
-- 3. RFM SCORING FOR THE CLICKSTREAM PROJECT (never built before -- only the
-- Indian e-commerce project had this).
--
-- Unlike the Indian project, there is no pre-existing segment label here to
-- validate RFM against -- this is a fresh segmentation, not a check on a
-- given one. Result is clean and monotonic: recency, frequency, and monetary
-- value all move together (no anomaly like the Indian dataset's flat-recency
-- finding), which is itself informative -- it means recency alone is a
-- reasonable single proxy for value in this business, unlike the Indian
-- dataset where a customer's stated segment failed to predict recency.
CREATE OR REPLACE TABLE ecommerce.gold.rfm_segmentation
COMMENT 'RFM quartile scoring for buyers (recency = days since last event, frequency = distinct sessions, monetary = total purchase value). Clean monotonic relationship across all three dimensions -- no pre-existing segment label to compare against, unlike the Indian e-commerce project.'
AS
WITH rfm_base AS (
  SELECT user_id,
    DATEDIFF('2019-12-01', MAX(event_date)) AS recency_days,
    COUNT(DISTINCT user_session) AS frequency,
    SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS monetary
  FROM ecommerce.silver.fact_events
  WHERE user_id IS NOT NULL
  GROUP BY user_id
  HAVING monetary > 0
),
scored AS (
  SELECT user_id, recency_days, frequency, monetary,
    NTILE(4) OVER (ORDER BY recency_days DESC) AS recency_score
  FROM rfm_base
)
SELECT
  recency_score,
  COUNT(*) AS buyers,
  ROUND(AVG(recency_days), 1) AS avg_recency_days,
  ROUND(AVG(frequency), 1) AS avg_sessions,
  ROUND(AVG(monetary), 0) AS avg_spend
FROM scored
GROUP BY recency_score
ORDER BY recency_score;

-- ---------------------------------------------------------------------------
-- Companion to #3: month-over-month buyer retention. With only two months
-- loaded, this measures exactly one transition -- October buyers who bought
-- again in November.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE ecommerce.gold.buyer_retention_oct_to_nov
COMMENT 'October buyers who purchased again in November. One data point (26.3%) -- more months of data would turn this into a real retention curve the way the Indian e-commerce project has.'
AS
WITH oct_buyers AS (
  SELECT DISTINCT user_id FROM ecommerce.silver.fact_events
  WHERE event_type = 'purchase' AND event_date < '2019-11-01'
),
nov_buyers AS (
  SELECT DISTINCT user_id FROM ecommerce.silver.fact_events
  WHERE event_type = 'purchase' AND event_date >= '2019-11-01'
)
SELECT
  (SELECT COUNT(*) FROM oct_buyers) AS october_buyers,
  (SELECT COUNT(*) FROM oct_buyers o JOIN nov_buyers n ON o.user_id = n.user_id) AS returned_in_november,
  ROUND((SELECT COUNT(*) FROM oct_buyers o JOIN nov_buyers n ON o.user_id = n.user_id) * 100.0
        / (SELECT COUNT(*) FROM oct_buyers), 2) AS pct_returned;
