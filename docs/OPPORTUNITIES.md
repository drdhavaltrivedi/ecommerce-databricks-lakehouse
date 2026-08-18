# Five problems in this data, and what to do about them

[`INSIGHTS.md`](INSIGHTS.md) describes what the numbers say. This document is
narrower: five findings where the data identifies a **specific broken thing**,
sizes it, and points at a decision.

Each is backed by a table in `ecommerce.gold.*` that rebuilds every pipeline
run, so none of this goes stale — see [`sql/09_opportunities.sql`](../sql/09_opportunities.sql).

October–November 2019, combined: 109.9M events, 23.1M sessions, $505.1M
revenue. **Two of the five findings below changed meaningfully when November
was added** — not just in magnitude, but in what they mean. That's flagged
explicitly in each section rather than smoothed over, because it's the most
important thing this update has to say: a finding built on one month of data
is a hypothesis, not a conclusion, until a second month either confirms or
breaks it.

---

## 1. Cart abandonment is not a price problem — and everyone will assume it is

`gold.cart_conversion_by_price`

| Item price | Carted | Cart → purchase |
|---|---|---|
| under $10 | 50,210 | **23.6%** |
| $10–25 | 105,185 | 29.5% |
| $25–50 | 302,286 | 32.2% |
| $50–100 | 330,256 | 33.6% |
| $100–500 | 1,413,481 | 40.8% |
| $500–1000 | 335,656 | 39.1% |
| **$1000+** | 144,901 | **41.2%** |

**The shape held; the level shifted.** Conversion is still roughly flat
(33–41%) above $50 and still falls below it — the same pattern as the
October-only read. What changed is the overall level: every band converts
lower than before, because November's more complete cart-event logging (see
[`INSIGHTS.md` §0](INSIGHTS.md#0-read-this-first-the-numbers-have-known-holes))
surfaces genuine low-intent carts that October's tracking gap was hiding. The
*conclusion* is unchanged and, if anything, more trustworthy now that it's
built on better-logged data: whatever stops roughly 60% of carts above $50 is
still price-independent.

**What to do** — unchanged from the original read:
- Stop treating abandonment as a discounting problem. The price data still
  says it isn't one.
- Instrument the checkout steps — still the highest-value tracking gap after
  the cart-event fix itself.
- Test a free-shipping threshold on the sub-$50 bands, where the gradient is
  steep enough that even a partial fix is measurable.

---

## 2. The attach-rate engine is switched off

`gold.attach_opportunity`

609,168 sessions bought a smartphone. **15,352 of them bought anything else
at all — an attach rate of 2.52%** (up slightly from 2.12% in the
October-only read; same order of magnitude, same conclusion).

| Attached category | Sessions | % of phone buyers |
|---|---|---|
| `electronics.audio.headphone` | 3,118 | 0.51% |
| `electronics.video.tv` | 2,090 | 0.34% |
| `electronics.clocks` | 2,084 | 0.34% |
| `computers.notebook` | 1,460 | 0.24% |
| `appliances.kitchen.washer` | 957 | 0.16% |

Industry norms for electronics attach sit in the 15–30% range. **A ~2.5%
attach rate means the engine is not running**, and that conclusion is now
confirmed across two months of independent traffic rather than resting on
one.

**Sizing it.** Headphone AOV is now $129 (was $116). Moving attach from 2.5%
to a conservative 10% is roughly the same order of magnitude as before:

> ~45,700 additional attach sessions × $129 ≈ **$5.9M over two months**
> (~$2.9M/month), at accessory margins rather than handset margins.

**What to do** — unchanged: cart-page accessory recommendations, bundle
pricing, post-purchase upsell. Needs no new traffic — these customers have
already bought.

⚠️ Same caveat as before: this measures same-session attach only, so the true
figure is a floor, not a ceiling.

---

## 3. Repeat viewing predicts purchase almost perfectly — and we're not using it

`gold.intent_by_view_depth`

| Views of a product by one user | Pairs | Conversion | Unconverted value |
|---|---|---|---|
| 1 view | 35.9M | **0.39%** | $10.18B |
| 2–3 views | 15.5M | 2.83% | $4.41B |
| 4–9 views | 4.3M | 10.86% | $1.10B |
| **10+ views** | 726K | **29.23%** | **$166.3M** |

**Direction unchanged, magnitude changed a lot.** The monotonic
view-depth-predicts-purchase pattern held exactly — more views still means
much higher conversion, at every band. But the absolute conversion rates at
each band came down (10+ views: 43.5% → 29.2%), and the unconverted-value
pool grew roughly 4×. Both are explained by the same traffic surge described
in `INSIGHTS.md`: November brought a wave of new, lower-intent browsers, which
dilutes conversion within every view-count band while dramatically growing
the number of people sitting in each one.

**What to do** — unchanged in kind, larger in scale: the non-buyers in the
10+ view band remain a far better-qualified retargeting segment than any
demographic split, and the addressable pool is now bigger, not smaller.

⚠️ Same caveat as before: this is correlation, valid for targeting, not for
justifying ad spend as a causal driver of sales.

---

## 4. Discounting: the finding reversed between months — read this one carefully

`gold.price_change_effect`

**Combined, two months:**

| Price move (vs prior day) | Product-days | Conversion |
|---|---|---|
| Price cut >5% | 108,874 | **1.74%** |
| Stable | 4,683,784 | 1.60% |
| Price rise >5% | 113,593 | 1.56% |

Read on its own, this table says the *opposite* of what the October-only
version said: price cuts now convert **best**, not worst.

**Split by month, and the real story appears:**

| Month | Cut | Stable | Rise |
|---|---|---|---|
| October | 1.62% | **1.85%** (best) | 1.30% |
| November | **1.80%** (best) | 1.44% (worst) | 1.67% |

**Neither single-month reading nor the pooled figure should be trusted as a
causal claim, and this is exactly why.** October's price-stable products
converted best — consistent with the original read that discounting doesn't
help. November's price-*cut* products converted best — the opposite pattern,
plausibly because November's price cuts are disproportionately
*promotional* (Black-Friday-period markdowns on products people already
intend to buy) rather than October's more likely *reactive* cuts (marking
down items that were already underperforming). Those are two different
mechanisms wearing the same label of "price cut," and pooling them, or
trusting either month in isolation, produces a confident-sounding number that
means something different each time.

**What to do**
- This is no longer just "run a holdout test to be safe" — it's now
  demonstrated that the observational answer flips sign depending on which
  month you happen to look at. A holdout test isn't optional caution anymore;
  it's the only way this question gets a real answer.
- If a holdout test isn't feasible immediately, at minimum separate
  *promotional* price cuts (planned, calendar-driven, e.g. Black Friday) from
  *reactive* ones (triggered by low sales velocity) as a modeling variable
  before drawing any conclusion from historical price-change data.

---

## 5. The missing categories still cannot be recovered — don't try

`gold.category_recovery_check`

32.2% of rows have no `category_code` (was 31.8% in October alone — stable).
The obvious fix is still to backfill from `category_id`.

**Still does not work, and the gap widened slightly.** Of the **414** distinct
`category_id` values that now appear with a blank code (was 372), **zero**
ever appear with a populated one. The blank-code categories remain a
**disjoint set**. Adding a second month strengthens rather than weakens this
conclusion — more data, same zero overlap.

**What to do** — unchanged: the fix has to come from the source product
catalog. It cannot be imputed from this dataset at any level of effort.

---

## Ranked by value, net of effort

| # | Action | Size | Effort | Type |
|---|---|---|---|---|
| 1 | **Accessory attach on phone purchases** | ~$2.9M/mo | Medium | Merchandising |
| 2 | **Retarget high-intent non-buyers** | $166.3M pool (10+ view band) | **Low** | Query + campaign |
| 3 | **Instrument checkout steps** | Unblocks the ~60% leak above $50 | Low | Engineering |
| 4 | **Free-shipping threshold under $50** | Sub-band lift | Low | Pricing |
| 5 | **Holdout-test discounting** | Now demonstrated sign-unstable across months — no longer optional | Medium | Experiment |
| — | ~~Backfill missing categories~~ | **Impossible**, confirmed on more data | — | Don't |

**If one thing gets done: #2.** Unchanged from before — single query, already
qualified audience, no product or pricing change needed, and the pool got
bigger with more data rather than shrinking.

**The one prerequisite behind several of these**: the cart-event tracking gap
now understood to be *month-dependent* (53.6% in October, 16.2% in November —
see [`INSIGHTS.md`](INSIGHTS.md)), not a stable defect. Until the root cause
of that swing is found, treat any cart-stage metric — including the flat
prices in finding #1 — as more solid in November than in October.
