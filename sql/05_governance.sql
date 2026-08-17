-- Unity Catalog governance: descriptions and informational constraints.
-- UC primary/foreign keys are declarative (RELY / NOT ENFORCED) -- they do not
-- validate data, but they document grain, drive the relationship diagram in
-- Catalog Explorer, and let the query optimizer eliminate redundant joins.

COMMENT ON CATALOG ecommerce IS
  'Multi-category e-commerce clickstream (Kaggle, Oct-Nov 2019). Medallion: bronze raw -> silver modeled -> gold business metrics.';

COMMENT ON SCHEMA ecommerce.bronze IS 'Raw ingestion, 1:1 with source files, all columns as STRING for full fidelity.';
COMMENT ON SCHEMA ecommerce.silver IS 'Typed, deduplicated, conformed. Fact + dimension model.';
COMMENT ON SCHEMA ecommerce.gold  IS 'Business-facing aggregates. Dashboard reads only from here.';

-- Grain documentation
COMMENT ON TABLE ecommerce.bronze.events IS
  'Raw event rows as loaded from CSV. Grain: one source row. Untyped by design; do not query for analytics -- use silver.fact_events.';
COMMENT ON TABLE ecommerce.silver.fact_events IS
  'Grain: one distinct (event_time, user_session, product_id, event_type). Deduplicated from bronze.';
COMMENT ON TABLE ecommerce.silver.dim_product IS
  'Grain: one row per product_id, carrying the most recent brand/category/price observed for that product.';
COMMENT ON TABLE ecommerce.silver.dim_session IS
  'Grain: one row per user_session, with funnel-stage flags. Basis for all funnel and abandonment metrics.';
COMMENT ON TABLE ecommerce.gold.funnel IS
  'Session funnel. NOTE: computed monotonically because ~54% of purchasing sessions have no logged cart event -- see gold.data_quality.';
COMMENT ON TABLE ecommerce.gold.data_quality IS
  'One row per data quality check, with affected volume and the business consequence of ignoring it. Read this before trusting any other gold table.';

-- Column-level documentation where the meaning is non-obvious
ALTER TABLE ecommerce.silver.dim_session ALTER COLUMN has_cart
  COMMENT 'TRUE only if a cart event was actually logged. Under-reported in source: many purchases have no cart event.';
ALTER TABLE ecommerce.silver.fact_events ALTER COLUMN price
  COMMENT 'Unit price at event time, in source currency. Not quantity-multiplied; a purchase row is one unit.';
ALTER TABLE ecommerce.silver.dim_product ALTER COLUMN category_l1
  COMMENT 'First segment of category_code (e.g. electronics), NULL when category_code is blank in source.';

-- Informational constraints: declare the model's grain and relationships.
ALTER TABLE ecommerce.silver.dim_product   ALTER COLUMN product_id   SET NOT NULL;
ALTER TABLE ecommerce.silver.dim_session   ALTER COLUMN user_session SET NOT NULL;

ALTER TABLE ecommerce.silver.dim_product
  ADD CONSTRAINT pk_dim_product PRIMARY KEY (product_id) RELY;
ALTER TABLE ecommerce.silver.dim_session
  ADD CONSTRAINT pk_dim_session PRIMARY KEY (user_session) RELY;

ALTER TABLE ecommerce.silver.fact_events
  ADD CONSTRAINT fk_fact_product FOREIGN KEY (product_id)   REFERENCES ecommerce.silver.dim_product   (product_id)   NOT ENFORCED RELY;
ALTER TABLE ecommerce.silver.fact_events
  ADD CONSTRAINT fk_fact_session FOREIGN KEY (user_session) REFERENCES ecommerce.silver.dim_session   (user_session) NOT ENFORCED RELY;

-- A CHECK constraint that reflects a real business rule rather than a shape rule.
ALTER TABLE ecommerce.silver.fact_events
  ADD CONSTRAINT chk_event_type CHECK (event_type IN ('view','cart','purchase','remove_from_cart'));
