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

COPY INTO ecommerce.bronze.events
FROM (
  SELECT
    event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session,
    _metadata.file_path AS source_file
  FROM '/Volumes/ecommerce/bronze/raw_files/2019-Oct/'
)
FILEFORMAT = CSV
FORMAT_OPTIONS ('header' = 'true', 'inferSchema' = 'false')
COPY_OPTIONS ('mergeSchema' = 'true');
