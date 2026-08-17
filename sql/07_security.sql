-- Data classification and access control.
--
-- This dataset is anonymized -- user_id is a surrogate, not a name or email.
-- It is still a persistent identifier tied to an individual's browsing and
-- purchase history, which makes it personal data under GDPR-style regimes
-- (pseudonymized, not anonymized). Tagging it now means that when this pattern
-- is applied to production data with real identifiers, the classification and
-- the masking policy already exist rather than being retrofitted after an audit.

-- ---------------------------------------------------------------------------
-- Classification tags. These are queryable from
-- system.information_schema.column_tags, so "where does personal data live"
-- becomes a SQL question instead of a tribal-knowledge question.
-- ---------------------------------------------------------------------------
ALTER TABLE ecommerce.silver.fact_events
  ALTER COLUMN user_id SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'confidential');
ALTER TABLE ecommerce.silver.fact_events
  ALTER COLUMN user_session SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'internal');

ALTER TABLE ecommerce.silver.dim_session
  ALTER COLUMN user_id SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'confidential');

ALTER TABLE ecommerce.gold.user_summary
  ALTER COLUMN user_id SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'confidential');
ALTER TABLE ecommerce.gold.user_summary
  ALTER COLUMN total_spend SET TAGS ('sensitivity' = 'confidential');

ALTER TABLE ecommerce.bronze.events
  ALTER COLUMN user_id SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'confidential');

-- Table-level tags for discovery and cost attribution
ALTER TABLE ecommerce.silver.fact_events SET TAGS ('layer' = 'silver', 'domain' = 'clickstream', 'contains_pii' = 'true');
ALTER TABLE ecommerce.gold.user_summary  SET TAGS ('layer' = 'gold',   'domain' = 'customer',    'contains_pii' = 'true');
ALTER TABLE ecommerce.gold.funnel        SET TAGS ('layer' = 'gold',   'domain' = 'conversion',  'contains_pii' = 'false');
ALTER TABLE ecommerce.gold.data_quality  SET TAGS ('layer' = 'gold',   'domain' = 'observability');

-- ---------------------------------------------------------------------------
-- Column mask for user_id.
--
-- Analysts need to COUNT DISTINCT users and segment by behaviour; they do not
-- need to single out an individual. The mask hashes user_id for everyone
-- outside `ecommerce_pii_readers`, which preserves grouping and distinct counts
-- (the hash is deterministic) while removing the ability to join back to a
-- person. This is the data-minimisation principle expressed as code.
--
-- Deliberately NOT applied by default -- applying a mask to a group that does
-- not exist yet would break every existing query. Create the group first, then
-- uncomment the ALTER statements.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ecommerce.silver.mask_user_id(user_id BIGINT)
RETURNS BIGINT
COMMENT 'Returns user_id unchanged for members of ecommerce_pii_readers; a deterministic hash otherwise. Deterministic so COUNT(DISTINCT) and GROUP BY still work on masked values.'
RETURN CASE
         WHEN is_account_group_member('ecommerce_pii_readers') THEN user_id
         ELSE xxhash64(CAST(user_id AS STRING))
       END;

-- To activate (after creating the ecommerce_pii_readers group):
-- ALTER TABLE ecommerce.silver.fact_events ALTER COLUMN user_id SET MASK ecommerce.silver.mask_user_id;
-- ALTER TABLE ecommerce.gold.user_summary  ALTER COLUMN user_id SET MASK ecommerce.silver.mask_user_id;
