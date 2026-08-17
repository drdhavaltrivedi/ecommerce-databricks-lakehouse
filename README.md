# E-commerce Behavior Analytics on Databricks

A complete lakehouse implementation over the Kaggle
[eCommerce behavior data from a multi category store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)
dataset: ~30M raw clickstream events → Unity Catalog governed medallion data
model → Lakeview dashboard → a documented set of business findings.

This README is the single source of truth for **what was built, why each
decision was made, and how to run or extend it**. Anyone picking this up
should not need to ask.

---

## Table of contents

1. [Business context — why this exists](#1-business-context--why-this-exists)
2. [The dataset](#2-the-dataset)
3. [Architecture and why it looks like this](#3-architecture-and-why-it-looks-like-this)
4. [Ingestion: the hard part, and how it was solved](#4-ingestion-the-hard-part-and-how-it-was-solved)
5. [The data model, layer by layer](#5-the-data-model-layer-by-layer)
6. [Data quality: the issues found and how they were handled](#6-data-quality-the-issues-found-and-how-they-were-handled)
7. [The dashboard](#7-the-dashboard)
8. [Business findings](#8-business-findings)
9. [Repo layout](#9-repo-layout)
10. [How to run it](#10-how-to-run-it)
11. [Design decisions and trade-offs](#11-design-decisions-and-trade-offs)
12. [Extending this](#12-extending-this)

---

## 1. Business context — why this exists

Raw clickstream logs are not an asset. A 5.7GB CSV of `view`/`cart`/`purchase`
rows cannot be queried by a merchandiser, cannot be joined to anything, has no
governance, and answers no question on its own.

The goal is to turn that file into a **governed, queryable, trustworthy model**
that answers the questions a retail business actually asks:

| Question | Where it's answered |
|---|---|
| Where do shoppers drop out between browsing and buying? | `gold.funnel` |
| How much revenue is stuck in abandoned carts? | `gold.cart_abandonment` |
| Which categories earn their shelf space, and which just get browsed? | `gold.category_performance` |
| Which brands drive volume vs. value? | `gold.brand_performance` |
| When are we busiest (staffing, promo timing, deploy windows)? | `gold.hourly_pattern` |
| Do buyers come back? | `gold.user_summary` |
| **Can I trust any of the above?** | `gold.data_quality` |

That last row is deliberate and is covered in
[section 6](#6-data-quality-the-issues-found-and-how-they-were-handled). A model
that reports numbers without reporting its own defects is worse than no model,
because it converts a known unknown into an unknown unknown.

---

## 2. The dataset

Real behavioral data from a large multi-category online store, October–November
2019. One row per user interaction event.

| Column | Meaning |
|---|---|
| `event_time` | UTC timestamp of the event |
| `event_type` | `view`, `cart`, or `purchase` |
| `product_id` | Product identifier |
| `category_id` | Numeric category identifier |
| `category_code` | Dotted taxonomy, e.g. `electronics.smartphone` (often blank) |
| `brand` | Brand name (often blank) |
| `price` | Unit price at event time |
| `user_id` | Persistent user identifier |
| `user_session` | Session identifier |

**Scale**: 5.7GB / ~42M rows for October alone; 9GB for November.
**Currently loaded**: October 2019 (see [section 12](#12-extending-this) for
adding November).

The dataset documents `remove_from_cart` as a possible `event_type`, but it does
**not appear** in the October file — only three event types are present. The
silver-layer filter still accepts it so that adding a month containing it
requires no code change.

---

## 3. Architecture and why it looks like this

```mermaid
flowchart TD
    K["Kaggle API<br/>2019-Oct.csv.zip - 1.7GB"]
    L["Local disk<br/>one ~1GB part at a time"]
    V["UC Volume<br/>ecommerce.bronze.raw_files"]
    B["bronze.events<br/>raw, all STRING"]
    S1["silver.fact_events"]
    S2["silver.dim_product"]
    S3["silver.dim_session"]
    G["gold.* - 9 tables"]
    D["Lakeview Dashboard"]
    Q["gold.data_quality"]

    K -->|"kaggle CLI"| L
    L -->|"split + stream,<br/>never fully unzipped"| V
    V -->|"COPY INTO<br/>(idempotent)"| B
    B -->|"type, dedupe, conform"| S1
    B --> S2
    S1 -->|"session aggregation"| S3
    S1 --> G
    S3 --> G
    B -.->|"profiling"| Q
    S3 -.-> Q
    Q --> D
    G --> D
```

### Why medallion (bronze / silver / gold)?

Each layer has exactly one job, which makes failures diagnosable:

- **Bronze** — *fidelity*. Every column is `STRING`. Nothing is cast, nothing is
  dropped, nothing is cleaned. If a downstream number looks wrong, bronze is the
  reference to check against. Casting at ingest would destroy the evidence
  needed to debug it.
- **Silver** — *correctness*. Types, deduplication, conformed dimensions,
  derived attributes. This is where business rules about *what the data means*
  live.
- **Gold** — *consumption*. Pre-aggregated, denormalized, named for the business
  question they answer. The dashboard reads **only** from gold, so a dashboard
  query never scans 30M rows.

The alternative — one big transformation from CSV to dashboard — is faster to
write once and impossible to debug or extend afterwards.

### Why Unity Catalog?

- **Three-level namespace** (`ecommerce.silver.fact_events`) — layer membership
  is visible in every reference; no naming conventions to enforce by hand.
- **Volumes** — governed file storage for the raw CSVs. This workspace has the
  legacy DBFS root disabled (a good security posture), so Volumes are the
  supported ingestion path, not just the preferred one.
- **Lineage** — UC tracks table-to-table lineage automatically, so the
  bronze→silver→gold flow is visible in Catalog Explorer without maintaining a
  diagram that goes stale.
- **Informational constraints** — declared PK/FK relationships make the model
  self-describing and let the optimizer eliminate provably redundant joins.

### Why a serverless SQL warehouse and not a Spark cluster?

This workload is pure SQL: `COPY INTO` plus a set of `CREATE TABLE AS SELECT`
statements. A SQL warehouse needs no cluster configuration, no node-type
decision, auto-starts on first query, and auto-stops after 10 minutes idle. A
general-purpose cluster would add operational surface area and cost for zero
capability gain. If this later needs Python UDFs, ML, or streaming, that's the
point at which a cluster earns its place.

All orchestration runs through the **Statement Execution API** over plain
HTTPS — no notebooks, no cluster attach, no local Spark install. The pipeline is
therefore runnable from any machine or CI runner with an environment variable
set.

---

## 4. Ingestion: the hard part, and how it was solved

This was the least obvious part of the build, and three separate approaches
failed before one worked. Documented here so nobody retries a dead end.

### The constraints

| Constraint | Value |
|---|---|
| Uncompressed CSV | 5.67 GB |
| Free local disk | ~13 GB |
| Files API single-`PUT` limit | 5 GiB |
| Legacy DBFS root | **disabled** in this workspace |

### What was tried

| # | Approach | Result |
|---|---|---|
| 1 | Buffer whole CSV in memory, one `PUT` | Would need ~6GB RAM. Rejected before running. |
| 2 | Chunked `PUT` of the full 5.67GB file | **`BrokenPipeError`** — exceeds the 5 GiB per-request limit. |
| 3 | DBFS block API (`create`/`add-block`/`close`) | **`PERMISSION_DENIED`** — public DBFS root disabled under UC. Correct security posture; wrong tool. |
| 4 | **Split into ~1GB parts, stream each to a UC Volume** | **Works.** |

### The working approach — [`scripts/split_upload.py`](scripts/split_upload.py)

```
zip member ──read line by line──> ~1GB part on local disk
                                       │
                                       ├─ PUT to UC Volume
                                       └─ delete local part, reuse the space
```

Key properties, and why each matters:

- **The 5.67GB CSV is never fully written to disk.** Only one ~1GB part exists
  at a time. Peak local usage is ~1GB against 13GB free, instead of 5.7GB
  against 13GB.
- **Splitting happens on line boundaries, and every part carries the header
  row.** A byte-offset split would tear a row in half and silently corrupt
  whichever record straddled the boundary. Every part is independently valid CSV.
- **Each part is under the 5 GiB Files API limit**, so a plain `PUT` works with
  no multipart-session complexity.
- **Multiple files in a directory are a feature, not a workaround.** Spark reads
  a directory of CSVs as one logical table, and it parallelizes better than one
  large file would.

### Why `COPY INTO` rather than `CREATE TABLE ... USING CSV`

`COPY INTO` keeps a **per-file load ledger**. Re-running it skips files already
ingested and loads only new ones. Two direct consequences:

1. **Ingestion could start before the upload finished.** Bronze was loaded from
   4 of 6 parts while parts 5 and 6 were still uploading, and the remaining
   parts were picked up by simply re-running the same statement. No coordination
   logic, no "is the upload done yet" polling in the pipeline.
2. **Adding November is one re-run.** Drop the files in the volume, re-run the
   pipeline; October is not re-read.

`_metadata.file_path` is captured into `source_file` so every bronze row can be
traced back to the exact file it came from.

---

## 5. The data model, layer by layer

```mermaid
erDiagram
    dim_product ||--o{ fact_events : "product_id"
    dim_session ||--o{ fact_events : "user_session"

    dim_product {
        bigint product_id PK
        decimal category_id
        string category_code
        string category_l1
        string category_l2
        string brand_clean
        double price
    }
    dim_session {
        string user_session PK
        bigint user_id
        timestamp session_start
        timestamp session_end
        boolean has_view
        boolean has_cart
        boolean has_purchase
        double session_revenue
    }
    fact_events {
        timestamp event_time
        date event_date
        string event_type
        bigint product_id FK
        string user_session FK
        string brand
        double price
        bigint user_id
    }
```

### Bronze — `ecommerce.bronze.events`

**Grain**: one row per source CSV row.
**Types**: every column `STRING`, deliberately.

Casting at ingest means a single malformed value fails the load of an entire
file, and the offending value is gone by the time anyone investigates. Keeping
bronze untyped means ingestion essentially cannot fail on data content, and
bronze remains a faithful, queryable copy of the source for debugging.

Adds one column not present in the source: `source_file`, for lineage.

### Silver — typed, deduplicated, conformed

**`silver.fact_events`** — grain: one distinct
`(event_time, user_session, product_id, event_type)`.

- Casts to real types (`TIMESTAMP`, `BIGINT`, `DOUBLE`)
- `SELECT DISTINCT` removes exact duplicate events — these exist in the source,
  typically from client-side retry or double-firing analytics tags
- Derives `event_date` once, so daily aggregates never re-cast at query time
- Blank `brand` becomes `'unknown'` rather than `NULL` — `NULL` silently
  disappears from `GROUP BY` output, whereas `'unknown'` shows up as a visible
  row and makes the gap impossible to overlook
- Filters to known `event_type` values, keeping `remove_from_cart` accepted for
  forward compatibility

**`silver.dim_product`** — grain: one row per `product_id`.

Products change brand/category/price over time in this data. The dimension keeps
the **most recent** observation per product, via
`ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY event_time DESC)`. This is
a Type-1 slowly-changing dimension: current state only, no history.

That is the right call *here* because the analytical questions are about current
catalog performance. It would be the wrong call for questions like "what was the
price when this order was placed" — but the fact table already stores `price` at
event time, so point-in-time price is preserved where it matters.

Also splits `category_code` into `category_l1` / `category_l2` so the taxonomy
can be rolled up without string manipulation in every downstream query.

**`silver.dim_session`** — grain: one row per `user_session`.

This is the most important table in the model. It collapses the event stream
into one row per session carrying `has_view` / `has_cart` / `has_purchase`
flags.

**Why session-level and not event-level for the funnel**: a shopper who views
the same phone eleven times has not moved through eleven funnels. Counting raw
events measures *engagement*; counting sessions measures *shoppers making
progress*. Every funnel, conversion, and abandonment metric downstream is
session-based for this reason.

### Gold — nine business-facing tables

| Table | Grain | Business question |
|---|---|---|
| `daily_metrics` | one row per day | Traffic, revenue, conversion trend |
| `funnel` | one row (whole period) | Where do sessions drop out? |
| `cart_abandonment` | one row per day | How much money is stuck in carts? |
| `category_performance` | one row per category | Which categories earn their space? |
| `brand_performance` | one row per brand | Volume vs. value by brand |
| `top_products` | top 100 by revenue | What actually sells? |
| `user_summary` | one row per user | Buyer frequency, spend, recency |
| `hourly_pattern` | one row per hour-of-day | When are we busiest? |
| `data_quality` | one row per check | **Can these numbers be trusted?** |

Gold tables are materialized rather than views. The dashboard has ~14 widgets;
as views, each widget refresh would re-scan the 30M-row fact table. Materialized,
the dashboard queries touch tables of a few hundred rows. Cost of the trade:
gold is stale until the pipeline re-runs — acceptable for a daily-refresh
analytics use case, and `CREATE OR REPLACE` makes the refresh a single re-run.

### Governance — [`sql/05_governance.sql`](sql/05_governance.sql)

- **Comments** on catalog, schemas, every table, and any column whose meaning is
  not self-evident. Every table's **grain is documented in its comment** — the
  single most common source of misuse in an analytics model is someone assuming
  the wrong grain and double-counting.
- **`PRIMARY KEY` / `FOREIGN KEY` constraints** declared `RELY NOT ENFORCED`.
  Databricks does not enforce these — they are *informational*. They earn their
  place by (a) rendering the ER diagram in Catalog Explorer, (b) documenting the
  intended grain in a machine-readable way, and (c) allowing the optimizer to
  eliminate joins it can prove are redundant.
- **`CHECK` constraint** on `event_type`, which *is* enforced. This one encodes
  a real business rule: if a new event type ever appears in source data, the
  pipeline should fail loudly rather than silently drop it from the funnel.

---

## 6. Data quality: the issues found and how they were handled

Profiling ran before any business metric was trusted. It found one issue serious
enough to invalidate the headline metric.

### The blocking issue: cart events are systematically under-logged

The first funnel build produced this:

```
cart_to_purchase_pct = 110.16%
```

More sessions contained a purchase (450,901) than contained a cart (409,308).
Arithmetically impossible in a funnel where cart precedes purchase.

**Root cause**: **53.9% of purchasing sessions have no cart event at all.** The
source tracking drops the cart step for over half of completed purchases.

**How it was handled** — the funnel is computed **monotonically**: a session
that purchased is credited with having reached the cart stage, and any session
that carted or purchased is credited with having reached the view stage.

**Crucially, the raw numbers are retained alongside the adjusted ones**:

| Column | Meaning |
|---|---|
| `sessions_with_cart` | Adjusted — includes purchases with no logged cart |
| `sessions_cart_logged` | Raw — cart events actually present in source |
| `purchases_missing_cart_event` | The size of the gap |

This is the important part of the approach. Silently patching the number would
produce a plausible dashboard built on an invisible assumption. Publishing both
means a reader can see exactly how much of the funnel is measured and how much
is inferred.

Result after the fix — and note the *direction* of the correction:

| | Before (raw) | After (monotonic) |
|---|---|---|
| view → cart | 6.30% | **10.04%** |
| cart → purchase | **110.16%** (impossible) | **69.10%** |
| view → purchase | 6.94% | 6.94% |

The naive version did not just look silly — it **understated cart adds by 37%**
and would have sent the team optimizing checkout, which is the part that already
works.

### All checks — `gold.data_quality`

| Check | Affected | % | Business consequence |
|---|---|---|---|
| `purchase_without_cart` | 243,245 sessions | **53.9%** of purchases | Funnel invalid unless computed monotonically |
| `missing_category_code` | 9,610,028 rows | **32.1%** | 10.1% of revenue sits in an `unknown` bucket |
| `missing_brand` | 4,211,149 rows | **14.1%** | Brand ranking biased toward well-tagged brands |
| `multiday_sessions` | 11,631 sessions | 0.18% | Session ids reused across visits; inflates duration |
| `zero_or_negative_price` | 49,322 rows | 0.16% | Distorts AOV if not excluded |
| `purchase_without_view` | 560 sessions | 0.12% | Sessions starting mid-journey (deep links) |

**Why this is a table and not a footnote**: it's queryable, it's on the
dashboard, and it re-computes every pipeline run. If a future month arrives with
worse tracking, the number moves and somebody sees it. A README caveat would go
stale the day it was written.

**The principle applied throughout**: bad data is surfaced, never silently
dropped. Blank brands become a visible `'unknown'` row rather than vanishing
from a `GROUP BY`. The cart gap is published next to the corrected figure. The
reader can always see the shape of what is missing.

---

## 7. The dashboard

Built via [`scripts/create_dashboard.py`](scripts/create_dashboard.py) against
the Lakeview API. Re-running **updates in place** (it looks up the dashboard by
display name and `PATCH`es it) rather than creating duplicates.

Layout, top to bottom — deliberately ordered as *headline → diagnosis → detail →
caveats*:

1. **KPI row** — revenue, sessions, users, conversion %, abandoned cart value
2. **Funnel + daily revenue** — the headline story and its trend
3. **Daily conversion % + abandoned value over time** — is it getting better?
4. **Category and brand revenue** — where the money comes from
5. **Revenue by hour + category conversion** — operational timing, and which
   categories convert rather than merely attract traffic
6. **Buyer segments** — users and revenue by purchase frequency
7. **Top products table**
8. **Data quality table** — titled *"read before trusting the numbers above"*

The data-quality panel is placed last on purpose: a reader who scrolls the whole
dashboard ends on the caveats, rather than bouncing off them at the top before
seeing anything useful.

Defining the dashboard **as code** rather than clicking it together in the UI
means it is reviewable in a pull request, reproducible in another workspace, and
diffable when it changes.

---

### AI/BI Genie — natural language access

[`scripts/create_genie_space.py`](scripts/create_genie_space.py) provisions a
Genie space so non-technical users can ask questions in plain English rather
than filing a request for a SQL query.

Genie is scoped to the **gold layer only** — those tables are small,
business-named, and pre-aggregated, which is exactly what a text-to-SQL system
needs. Pointing it at bronze would invite 30M-row scans and meaningless
column names.

**The instructions matter more than the table list.** Without them Genie would
happily compute `purchases / carts` from raw counts and report a **110%
cart-to-purchase rate** to a business user with no way to know it was wrong.
The space is therefore given five instruction blocks:

1. **The cart-tracking caveat** — always use `gold.funnel`, never divide raw
   counts, and disclose that the cart stage is partly inferred
2. **Other data caveats** — unknown-bucketing, purchase = completed sale, no
   quantity column
3. **Grain rules** — `gold.funnel` is one row (never `GROUP BY` it),
   `hourly_pattern` is a daily profile not a time series, and gold tables must
   never be joined to each other because each is independently aggregated
4. **Business context** — revenue concentration, where the funnel actually
   leaks, UTC→local time conversion
5. **Worked SQL examples** for the most common questions

Verified working. Asked *"What is our purchase funnel and where are we losing
the most people?"*, Genie selected `gold.funnel`, returned the correct figures,
identified view→cart as the drop-off — and **volunteered the caveat unprompted**:
*"The cart stage is partly inferred due to tracking gaps."*

Schema note: the `serialized_space` payload shape is not publicly documented
and was determined empirically. Three constraints are easy to trip over and are
handled in the script: `data_sources.tables` **must be sorted** by identifier,
`instructions.text_instructions` accepts **at most one item** (separate
paragraphs go in its `content` array), and `content` entries must be plain
strings.

## 8. Business findings

Full write-up with reasoning and recommendations:
**[`docs/INSIGHTS.md`](docs/INSIGHTS.md)**. Headlines from Oct 1–22 2019
(~30M events, 6.5M sessions, 2.36M users, $164M revenue):

**The funnel leaks at discovery, not checkout.** 69% of carts convert — checkout
is healthy. But only 10% of viewing sessions ever cart. The addressable
population upstream is roughly 3× the one at checkout, so that is where effort
belongs.

**$71.8M sits in abandoned carts** — 43.6% of realized revenue, 201,693
sessions. Standard recovery campaigns recover 5–15%, implying $3.6M–$10.8M in a
single month with no product or pricing change.

**68% of revenue is smartphones.** A concentration risk that needs an explicit
strategic decision rather than a dashboard. Headphones (4.65% conversion, a
natural attach) look like the most obvious adjacent opportunity.

**Apple drives value, Samsung drives volume.** Samsung sells 21% more units;
Apple earns 58% more revenue at a 2.9× AOV ($777 vs $268). These should not
share a merchandising strategy.

**Some categories are pure browsing.** `apparel.shoes` takes 431K views and
returns $247K — a 0.66% conversion rate against smartphones' 4.85%. It consumes
traffic and merchandising space disproportionate to its return.

**11% of users buy, but 36% of buyers repeat within the month.** Weak
acquisition conversion, strong retention. That combination is a strong argument
for aggressive first-purchase incentives, because the payback is unusually good.

**Peak trading is 06:00–11:00 UTC** (≈09:00–14:00 local for this
Russian-market store) — a workday-morning pattern. Promo sends should land just
before it; deploy freezes and support staffing should respect it.

---

## 9. Repo layout

```
sql/
  01_bronze.sql        Raw table DDL + idempotent COPY INTO from the UC volume
  02_silver.sql        Typed fact + dimensions, session derivation
  03_gold.sql          Nine business aggregate tables
  04_data_quality.sql  One row per DQ check, with business impact
  05_governance.sql    Comments, PK/FK constraints, CHECK constraint

scripts/
  split_upload.py      Streams a CSV out of the Kaggle zip into <5GiB parts and
                       uploads each to a UC Volume. Never fully unzips locally.
  dbx_sql.py           Thin client for the SQL Statement Execution API
  run_sql_file.py      Runs a .sql file statement by statement. The splitter is
                       quote-aware: a naive split on ';' breaks on semicolons
                       inside string literals, which this codebase has.
  run_pipeline.py      Orchestrates all five SQL layers in order. Idempotent.
  create_dashboard.py  Creates or updates the Lakeview dashboard
  create_genie_space.py  Creates or updates the AI/BI Genie space, including
                       the instructions that stop it reporting the broken
                       raw funnel to business users

docs/
  INSIGHTS.md          Business findings, reasoning, and recommendations
```

---

## 10. How to run it

### Prerequisites

```bash
export DATABRICKS_HOST="https://<workspace>.cloud.databricks.com"
export DATABRICKS_TOKEN="<personal access token>"
export DBX_WAREHOUSE_ID="<sql warehouse id>"
```

Kaggle credentials at `~/.kaggle/access_token` (newer `KGAT_…` token format) or
`~/.kaggle/kaggle.json` (legacy). Install the CLI with `uv tool install kaggle`.

### One-time: catalog structure

```bash
python3 scripts/dbx_sql.py "CREATE CATALOG IF NOT EXISTS ecommerce"
python3 scripts/dbx_sql.py "CREATE SCHEMA IF NOT EXISTS ecommerce.bronze"
python3 scripts/dbx_sql.py "CREATE SCHEMA IF NOT EXISTS ecommerce.silver"
python3 scripts/dbx_sql.py "CREATE SCHEMA IF NOT EXISTS ecommerce.gold"
python3 scripts/dbx_sql.py "CREATE VOLUME IF NOT EXISTS ecommerce.bronze.raw_files"
```

### Ingest a month

```bash
kaggle datasets download -d mkechinov/ecommerce-behavior-data-from-multi-category-store -f 2019-Oct.csv
python3 scripts/split_upload.py 2019-Oct.csv.zip 2019-Oct.csv \
    /Volumes/ecommerce/bronze/raw_files/2019-Oct ./tmp_parts
```

Upload throughput is bounded by local upstream bandwidth — budget roughly 10
minutes per GB on a typical office connection.

### Run the pipeline

```bash
python3 scripts/run_pipeline.py
```

Or a single layer: `python3 scripts/run_pipeline.py silver`.
Layer names: `bronze`, `silver`, `gold`, `dq`, `governance`.

### Refresh the dashboard and Genie space

```bash
python3 scripts/create_dashboard.py
python3 scripts/create_genie_space.py
```

Both look up the existing object by name and update it in place, so re-running
does not create duplicates.

**The whole pipeline is idempotent.** Re-running is always safe: `COPY INTO`
skips files it has already loaded, and silver/gold are `CREATE OR REPLACE`.

---

## 11. Design decisions and trade-offs

Recorded with reasoning so they can be revisited deliberately rather than
rediscovered by accident.

| Decision | Why | Trade-off accepted |
|---|---|---|
| Bronze columns all `STRING` | Ingest can't fail on bad values; source stays debuggable | Every downstream query casts; bronze is not directly analyzable |
| Session-grain funnel, not event-grain | Eleven views of one phone is one shopper, not eleven funnels | Sessions spanning days are slightly miscounted (0.18%, surfaced in DQ) |
| Monotonic funnel | Raw data yields an impossible 110% cart→purchase | Cart stage is partly inferred — disclosed via `sessions_cart_logged` |
| Blank → `'unknown'`, not `NULL` | `NULL` vanishes from `GROUP BY`; `'unknown'` is a visible row | Slightly noisier output, which is the point |
| Gold materialized, not views | 14 widgets × 30M-row scans is unnecessary cost and latency | Gold is stale until the pipeline re-runs |
| Type-1 dimension (current state only) | Questions asked are about current catalog performance | No historical attribute tracking; point-in-time price preserved in the fact table |
| Serverless SQL warehouse, no cluster | Workload is pure SQL; no cluster config or idle cost | Would need a cluster for Python UDFs, ML, or streaming |
| Statement Execution API, not notebooks | Runs from any machine or CI runner; reviewable as code | No interactive exploration in the pipeline itself |
| Split upload into ~1GB parts | Only path that satisfies both the 5 GiB API limit and 13GB free disk | Slower than one large upload would be; more moving parts |
| `COPY INTO`, not `CREATE TABLE USING CSV` | Per-file ledger makes re-runs incremental and safe | Slightly more verbose DDL |
| DQ as a table, not documentation | Recomputes every run; a README caveat goes stale immediately | One more table to maintain |
| Dashboard as code | Reviewable, reproducible, diffable | Slower to iterate than clicking in the UI |

---

## 12. Extending this

### Add November 2019 (recommended next step)

November contains Black Friday and Cyber Monday — the highest-signal period in
the dataset, and the obvious test of whether the funnel behaves differently
under promotional traffic.

```bash
kaggle datasets download -d mkechinov/ecommerce-behavior-data-from-multi-category-store -f 2019-Nov.csv
python3 scripts/split_upload.py 2019-Nov.csv.zip 2019-Nov.csv \
    /Volumes/ecommerce/bronze/raw_files/2019-Nov ./tmp_parts
```

Then widen the `COPY INTO` source path in
[`sql/01_bronze.sql`](sql/01_bronze.sql) from `.../2019-Oct/` to
`.../` and re-run `python3 scripts/run_pipeline.py`. October is not re-read —
the `COPY INTO` ledger skips it.

### Other worthwhile extensions

- **Incremental gold.** Gold is currently a full rebuild. At two months this is
  fine (seconds); at a year it warrants `MERGE` on a date key.
- **Scheduled refresh.** Wrap `run_pipeline.py` in a Databricks Job on a daily
  schedule.
- **Cohort retention.** `gold.user_summary` has the raw material; a first-purchase
  cohort table would answer whether the 36% repeat rate holds beyond one month.
- **Liquid clustering** on `fact_events` by `event_date` once multiple months are
  loaded, to speed up date-filtered queries.
- **Alerting on `gold.data_quality`.** A Databricks SQL alert when
  `purchase_without_cart` exceeds a threshold would catch tracking regressions
  automatically.

### Known limitations

- **Purchase = completed sale.** The dataset has no payment or fulfilment status,
  so a `purchase` event is treated as revenue. Refunds and failed payments are
  invisible.
- **No quantity column.** A `purchase` row is one unit at `price`. Multi-unit
  orders cannot be distinguished from repeated single purchases.
- **Anonymized.** No geography, channel, or campaign attribution, so acquisition
  analysis is out of scope.
- **October only, partial** at time of writing (Oct 1–22, ~30M of ~42M rows).
