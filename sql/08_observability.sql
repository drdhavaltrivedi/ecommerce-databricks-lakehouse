-- Platform observability from Unity Catalog system tables.
--
-- The gold layer answers "how is the business doing". These views answer
-- "how is the platform doing, and what is it costing" -- the questions that
-- decide whether this pipeline is still affordable and still being used.
--
-- Views, not tables: system tables are already maintained by Databricks, and
-- materializing a copy would mean paying to duplicate data that is free to
-- query and always current.

CREATE SCHEMA IF NOT EXISTS ecommerce.ops
  COMMENT 'Platform observability: cost, query performance, and access, sourced from system tables.';

-- ---------------------------------------------------------------------------
-- Cost. Priced in DBUs; multiply by your contracted rate for currency.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW ecommerce.ops.daily_dbu_cost
COMMENT 'DBU consumption per day by SKU. The first place to look when the bill moves.'
AS
SELECT
  usage_date,
  sku_name,
  usage_unit,
  ROUND(SUM(usage_quantity), 2) AS dbus,
  COUNT(DISTINCT usage_metadata.warehouse_id) AS warehouses
FROM system.billing.usage
WHERE usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY usage_date, sku_name, usage_unit
ORDER BY usage_date DESC, dbus DESC;

-- ---------------------------------------------------------------------------
-- Query performance. Surfaces the queries worth optimizing, ranked by the
-- only thing that matters: total time burned, not worst single run.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW ecommerce.ops.expensive_queries
COMMENT 'Heaviest queries over the last 7 days by cumulative duration. Optimize from the top of this list.'
AS
SELECT
  LEFT(REGEXP_REPLACE(statement_text, '\\s+', ' '), 160) AS statement_preview,
  COUNT(*)                                    AS executions,
  ROUND(SUM(total_duration_ms) / 1000.0, 1)   AS total_seconds,
  ROUND(AVG(total_duration_ms) / 1000.0, 2)   AS avg_seconds,
  ROUND(SUM(read_bytes) / 1e9, 2)             AS total_gb_read,
  ROUND(AVG(read_rows))                       AS avg_rows_read
FROM system.query.history
WHERE start_time >= CURRENT_TIMESTAMP() - INTERVAL 7 DAYS
  AND statement_type = 'SELECT'
GROUP BY statement_preview
HAVING SUM(total_duration_ms) > 5000
ORDER BY total_seconds DESC
LIMIT 50;

-- ---------------------------------------------------------------------------
-- Pipeline health. Did the scheduled refresh actually run, and did it work?
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW ecommerce.ops.pipeline_runs
COMMENT 'Recent runs of the ecommerce refresh job, newest first. Check here before trusting a dashboard number.'
AS
SELECT
  r.run_id,
  r.period_start_time    AS started_at,
  r.period_end_time      AS ended_at,
  ROUND((UNIX_TIMESTAMP(r.period_end_time) - UNIX_TIMESTAMP(r.period_start_time)) / 60.0, 1) AS duration_min,
  r.result_state,
  r.termination_code
FROM system.lakeflow.job_run_timeline r
JOIN system.lakeflow.jobs j
  ON r.job_id = j.job_id AND r.workspace_id = j.workspace_id
WHERE j.name = 'ecommerce-medallion-refresh'
ORDER BY r.period_start_time DESC
LIMIT 50;

-- ---------------------------------------------------------------------------
-- Usage. Which tables are actually being read? Unread gold tables are
-- maintenance burden with no return -- this is the evidence for deleting them.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW ecommerce.ops.table_usage
COMMENT 'Read activity per ecommerce table over 30 days. Tables with no reads are candidates for removal.'
AS
SELECT
  source_table_full_name AS table_name,
  COUNT(*)               AS read_events,
  COUNT(DISTINCT created_by) AS distinct_users,
  MAX(event_time)        AS last_read
FROM system.access.table_lineage
WHERE source_table_catalog = 'ecommerce'
  AND event_time >= CURRENT_TIMESTAMP() - INTERVAL 30 DAYS
GROUP BY source_table_full_name
ORDER BY read_events DESC;

-- ---------------------------------------------------------------------------
-- Where does personal data live? Answerable in SQL because 07_security.sql
-- tagged it, rather than depending on somebody remembering.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW ecommerce.ops.pii_inventory
COMMENT 'Every column tagged as personal data, for audit and access review.'
AS
SELECT
  catalog_name, schema_name, table_name, column_name,
  MAX(CASE WHEN tag_name = 'pii'         THEN tag_value END) AS pii_class,
  MAX(CASE WHEN tag_name = 'sensitivity' THEN tag_value END) AS sensitivity
FROM system.information_schema.column_tags
WHERE catalog_name = 'ecommerce'
GROUP BY catalog_name, schema_name, table_name, column_name
HAVING pii_class IS NOT NULL
ORDER BY schema_name, table_name, column_name;
