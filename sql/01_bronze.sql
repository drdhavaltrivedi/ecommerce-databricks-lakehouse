-- Bronze layer: raw ingestion, minimal transformation, full fidelity
CREATE TABLE IF NOT EXISTS ecommerce.bronze.events (
  event_time    STRING,
  event_type    STRING,
  product_id    STRING,
  category_id   STRING,
  category_code STRING,
  brand         STRING,
  price         STRING,
  user_id       STRING,
  user_session  STRING,
  source_file   STRING
) USING DELTA;

-- Points at the raw_files root, not a single month's subfolder, so adding a
-- new month is just uploading its parts to a new subfolder here and re-running
-- this file -- COPY INTO's per-file ledger means already-loaded months are not
-- re-read.
--
-- PATTERN is required: COPY INTO does not recurse into subdirectories on its
-- own. Pointing FROM at the root with no PATTERN finds zero files (each
-- month's CSVs live one level down, in a 2019-Oct/ or 2019-Nov/ subfolder)
-- and fails with COPY_INTO_SOURCE_SCHEMA_INFERENCE_FAILED. '*/*.csv' matches
-- exactly one level of subdirectory, which is this layout.
COPY INTO ecommerce.bronze.events
FROM (
  SELECT
    event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session,
    _metadata.file_path AS source_file
  FROM '/Volumes/ecommerce/bronze/raw_files/'
)
FILEFORMAT = CSV
PATTERN = '*/*.csv'
FORMAT_OPTIONS ('header' = 'true', 'inferSchema' = 'false')
COPY_OPTIONS ('mergeSchema' = 'true');
