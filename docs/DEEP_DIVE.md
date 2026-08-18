# Three follow-up investigations

Opened by the Oct+Nov rebuild in the previous update, and left as open
questions there. Each resolves — or partially resolves — something specific
rather than adding an unrelated finding. Backed by
[`sql/10_deep_dive.sql`](../sql/10_deep_dive.sql), which rebuilds every
pipeline run.

---

## 1. Does sale-day coordination explain the discount reversal?

`gold.discount_tier_analysis`

`docs/OPPORTUNITIES.md` §4 found the discounting finding **reverses sign**
between October (price cuts underperform) and November (price cuts
outperform), and recommended separating *promotional* cuts from *reactive*
ones as the next step. Same-day-cut-count — how many other products also got
a >5% price cut on the same day — is the closest available proxy for that
without a true holdout test.

The proxy validates itself immediately: the two highest-volume cut days in
the whole dataset are **November 29 and November 30, 2019** — the actual
real-world dates of Black Friday and Cyber Monday that year. No calendar
lookup was needed to find them; they simply have far more products cut
same-day (7,363 and 4,956) than anything else in the dataset (next-highest:
2,433).

| Sale-day tier | Days | Conversion |
|---|---|---|
| Mega (Black Friday / Cyber Monday) | 2 | **1.98%** |
| Elevated (top decile, not mega) | 6 | **1.51%** |
| Background / isolated | 52 | **1.71%** |

**Partial explanation, and a non-obvious shape.** Mega sale days convert
best, as expected — real demand-driven buying events. But "elevated" days
(moderate multi-product markdowns, not the two biggest calendar events)
convert **worse than isolated single-product cuts**, not better. That pattern
holds in both months:

| Month | Background | Elevated |
|---|---|---|
| October | 1.66% | 1.44% |
| November | 1.75% | 1.98% (incl. mega) / 1.58% (elevated only) |

The likely read: "elevated" days are routine, moderate-scale clearance
campaigns on slower-moving inventory — genuinely reactive, at a slightly
larger scale than a single-product cut. Isolated single-product cuts may
often be price-matching or small corrections on items already in demand,
which converts better than a clearance push.

**What this does and doesn't resolve**: coordinated sale-day timing explains
part of the October→November reversal (mega days pull November's average up),
but background/isolated cuts *themselves* improved from 1.66% to 1.75% —
smaller than the raw month-level gap, but not zero. Sale-day timing isn't the
whole story. See finding 2.

---

## 2. Is November's better conversion driven by new or returning users?

`gold.november_cohort_behavior`

**Hypothesis going in**: a Black Friday traffic surge brings a wave of
low-intent browsers who dilute conversion — the natural explanation for why
even non-sale-day metrics improved in November.

**Result: the opposite.** Restricted to November activity only:

| User cohort | Users | November conversion |
|---|---|---|
| New to November | 2,294,359 | **1.56%** |
| Returning (first seen October) | 1,401,758 | **1.37%** |

Users new to November convert *better* than the existing base returning in
November. The likely explanation: new-to-November traffic is disproportionately
Black-Friday-acquired — people searching for deals, arriving already
purchase-intent-qualified — while the October base, when it returns in
November, skews toward habitual browsing rather than urgent buying intent.

**This is the likely remainder of finding 1.** Between sale-day coordination
(mega days convert best) and traffic composition (new arrivals convert
better than the returning base), most of the October→November funnel
improvement now has a concrete, verified explanation rather than an
unexplained residual.

Session-length data doesn't show a dramatic shift either (4.59 → 4.89 events
per session, October to November) — the story is about *who* is showing up
and *when* they're cutting prices, not about people browsing more per visit.

---

## 3. RFM segmentation and buyer retention for the clickstream project

`gold.rfm_segmentation`, `gold.buyer_retention_oct_to_nov`

This project has no pre-existing customer segment label — RFM here is a
**fresh segmentation**, built directly from raw behavior rather than checked
against a given label.

| Recency quartile | Buyers | Avg. days since last event | Avg. sessions | Avg. spend |
|---|---|---|---|---|
| 1 (least recent) | 174,368 | 40.3 | 4.9 | $597 |
| 2 | 174,368 | 16.7 | 8.1 | $640 |
| 3 | 174,367 | 8.3 | 11.7 | $702 |
| 4 (most recent) | 174,367 | 2.2 | 18.1 | **$958** |

**Clean and monotonic** — recency, frequency, and spend all move together.
That's itself informative: with no pre-existing label to complicate the
picture, recency alone turns out to be a reasonable single proxy for value. The most-recently-active quartile spends
61% more on average than the least-recent, and attends 3.7× as many sessions.

**Buyer retention, October → November**: of 347,118 October buyers,
**91,286 (26.3%)** purchased again in November. With only two months loaded
this is one data point rather than a curve — worth revisiting once a third
month is added and this can be extended into a proper cohort-retention table.

---

## What to do with this

- **Sale-day timing and traffic composition together explain most of the
  discount reversal.** The `docs/OPPORTUNITIES.md` recommendation to run a
  holdout test stands — this analysis narrows *why* a naive read is
  misleading, it doesn't replace a causal test.
- **New-customer acquisition around promotional events converts well here** —
  worth protecting or growing that channel specifically, rather than treating
  "more Black Friday traffic" as an undifferentiated volume metric.
- **RFM's most-recent quartile is the highest-value, most-active segment by a
  wide margin** ($958 avg spend, 18.1 sessions) — a natural target for
  loyalty/VIP treatment, distinct from the acquisition-focused finding above.
- **Add a third month** to turn the single retention data point into an
  actual curve, and to test whether the sale-day-tier pattern (mega > isolated
  > elevated) holds outside a holiday period, or is itself a November-specific
  artifact.
