-- Physical optimization. Nothing here changes a number; it changes how fast
-- and how cheaply the numbers come back.

-- Liquid clustering on the fact table.
--
-- Chosen over partitioning by event_date: at ~30M rows/month, date partitions
-- would be small enough to cause the small-file problem, and partitioning is a
-- one-way door (changing the key means rewriting the table). Liquid clustering
-- keeps the layout adjustable and handles skew, which matters here because
-- event volume is far from uniform across days and products.
--
-- Keys chosen from actual filter/group patterns in the gold layer:
--   event_date  -- every daily aggregate and any date-range dashboard filter
--   product_id  -- top_products, and the join to dim_product
ALTER TABLE ecommerce.silver.fact_events
  CLUSTER BY (event_date, product_id);

-- Let Databricks maintain file sizes and clustering automatically rather than
-- scheduling manual OPTIMIZE. Predictive optimization is already inherited as
-- ENABLED from the metastore; these properties cover writes made outside it.
ALTER TABLE ecommerce.silver.fact_events SET TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact'   = 'true'
);

ALTER TABLE ecommerce.bronze.events SET TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact'   = 'true',
  -- bronze is a reproducible reload from the volume, so a long time-travel
  -- window buys little and costs storage
  'delta.deletedFileRetentionDuration' = 'interval 7 days'
);

-- Gold tables are small and fully rebuilt each run. Keep a short history:
-- enough to diff yesterday's numbers against today's when a figure looks odd,
-- not enough to accumulate cost.
ALTER TABLE ecommerce.gold.daily_metrics        SET TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 30 days');
ALTER TABLE ecommerce.gold.funnel               SET TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 30 days');
ALTER TABLE ecommerce.gold.data_quality         SET TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 90 days');

-- Compact and cluster now, so the first dashboard load after a pipeline run is
-- not the query that pays for layout.
OPTIMIZE ecommerce.silver.fact_events;
OPTIMIZE ecommerce.silver.dim_session;
OPTIMIZE ecommerce.bronze.events;

-- Statistics for the cost-based optimizer. Without these the planner guesses
-- cardinality, and guesses badly on a 30M-row fact joined to two dimensions.
ANALYZE TABLE ecommerce.silver.fact_events COMPUTE STATISTICS FOR COLUMNS
  event_date, event_type, product_id, user_id, user_session, brand;
ANALYZE TABLE ecommerce.silver.dim_session COMPUTE STATISTICS FOR COLUMNS
  user_session, has_view, has_cart, has_purchase;
ANALYZE TABLE ecommerce.silver.dim_product COMPUTE STATISTICS FOR COLUMNS
  product_id, category_code, brand_clean;
