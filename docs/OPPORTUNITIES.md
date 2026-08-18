# Five problems in this data, and what to do about them

[`INSIGHTS.md`](INSIGHTS.md) describes what the numbers say. This document is
narrower: five findings where the data identifies a **specific broken thing**,
sizes it, and points at a decision.

Each is backed by a table in `ecommerce.gold.*` that rebuilds every pipeline
run, so none of this goes stale — see [`sql/09_opportunities.sql`](../sql/09_opportunities.sql).

Full month of October 2019: 42.4M events, 9.2M sessions, $229.9M revenue.

---

## 1. Cart abandonment is not a price problem — and everyone will assume it is

`gold.cart_conversion_by_price`

| Item price | Carted | Cart → purchase |
|---|---|---|
| under $10 | 4,767 | **30.0%** |
| $10–25 | 20,147 | 35.7% |
| $25–50 | 43,883 | 39.6% |
| $50–100 | 57,270 | 42.7% |
| $100–500 | — | ~50% |
| $500–1000 | 81,611 | 49.9% |
| **$1000+** | 48,130 | **49.6%** |

**Two things here, and both are counterintuitive.**

**Above $50, conversion is flat at ~50%.** A $1,000 phone converts as well as a
$60 accessory. If shoppers were balking at cost, conversion would decay as price
climbs — it doesn't, at all, across a 20× price range. That rules out sticker
shock as the driver of abandonment for the overwhelming bulk of revenue.

Whatever is stopping half of all carts is **price-independent**, which means it
is process: delivery estimate revealed late, payment method missing, stock
status changing at checkout, forced account creation. Those are testable in an
afternoon and none of them are a pricing decision.

**Below $50, conversion falls — monotonically, to 30% under $10.** This is the
opposite of naive intuition, and it is the classic signature of **shipping cost
as a proportion of order value**. A flat delivery fee is a rounding error on a
$500 phone and a punitive surcharge on a $9 cable.

**What to do**
- Stop treating abandonment as a discounting problem. The price data says it
  isn't one.
- Instrument the checkout steps. The funnel currently ends at "cart" — there is
  no visibility into *where* inside checkout the 50% leave. That is the single
  highest-value tracking addition after the cart-event fix.
- Test a free-shipping threshold or bundle-to-qualify prompt on the sub-$50
  bands. The gradient is steep enough that even a partial fix is measurable.

---

## 2. The attach-rate engine is switched off

`gold.attach_opportunity`

285,252 sessions bought a smartphone. **6,041 of them bought anything else at
all — an attach rate of 2.12%.**

| Attached category | Sessions | % of phone buyers |
|---|---|---|
| `electronics.audio.headphone` | 1,158 | 0.41% |
| `electronics.video.tv` | 813 | 0.29% |
| `electronics.clocks` | 790 | 0.28% |
| `computers.notebook` | 579 | 0.20% |
| `appliances.kitchen.washer` | 373 | 0.13% |

Phone retail runs on accessories — cases, headphones, chargers, screen
protection, warranties. That is where the margin is, because the handset itself
is close to a commodity. **A 2% attach rate means that engine is not running.**
Industry norms for electronics attach sit in the 15–30% range.

**Sizing it.** Headphone AOV is $116. Moving attach from 2.1% to a conservative
10% is ~22,500 additional attach sessions:

> 22,500 × $116 ≈ **$2.6M/month in incremental revenue**, at accessory margins
> rather than handset margins.

And that is headphones alone, at a target well below industry norm.

**What to do**
- This is a merchandising and UX fix, not a data fix: cart-page accessory
  recommendations, bundle pricing, post-purchase upsell.
- It needs no new traffic. These are people who have **already bought** — the
  expensive part is done.
- The top-5 attach list above is the starting recommendation set, derived from
  what these customers actually already do together.

⚠️ One caveat worth stating: this measures *same-session* attach. A customer who
buys a case three days later is not counted, so 2.12% is a floor. The gap to
15–30% is far too large for that to explain it away, but the number to quote
externally is "same-session attach", not "attach".

---

## 3. Repeat viewing predicts purchase almost perfectly — and we're not using it

`gold.intent_by_view_depth`

| Views of a product by one user | Pairs | Conversion | Unconverted value |
|---|---|---|---|
| 1 view | 15.2M | **0.00%** | $4.46B |
| 2–3 views | 6.2M | 2.88% | $1.76B |
| 4–9 views | 1.6M | 16.65% | $377M |
| **10+ views** | 252K | **43.51%** | **$41.6M** |

A user who has looked at the same product ten or more times converts at **43.5%**.
A user who looked once converts at **effectively zero**.

The actionable part is the **non-buyers in the top bands**: ~142,000 user-product
pairs where someone viewed an item 10+ times and still didn't buy, representing
**$41.6M of unconverted intent**. That is a retargeting list that is better
qualified than any demographic segment, and it is sitting unused in the
clickstream.

**What to do**
- Build the high-intent segment (4+ views, no purchase) and route it to
  retargeting / email / on-site prompts. This is a query, not a project.
- Use view depth as a live intent score on-site — the 4–9 band at 16.7% is
  already 2.4× the site-wide 6.8% conversion rate.

⚠️ **Do not read this as "more impressions cause sales."** Buyers accumulate
views on the way to purchasing, so cause and effect are entangled. For
*targeting* the direction doesn't matter — the correlation finds the right
people regardless. For *ad spend justification* it matters a great deal, and
this data cannot support that claim.

---

## 4. Discounting isn't visibly working

`gold.price_change_effect`

| Price move (vs prior day) | Product-days | Conversion |
|---|---|---|
| Stable | 2,050,054 | **1.85%** |
| Price cut >5% | 31,459 | **1.62%** |
| Price rise >5% | 34,266 | 1.30% |

Days following a price cut convert **below** price-stable days.

**Be careful with this one.** It is *not* evidence that discounts suppress
demand. The obvious confound: prices get cut **because** an item isn't selling,
so discounted product-days are drawn from a weak population to start with.

What it does say is narrower and still uncomfortable: **after the discount,
those products still convert below the ordinary baseline.** The markdown is not
visibly rescuing them. Margin is being given away and no conversion lift is
showing up for it.

**What to do**
- Don't cancel discounting off the back of an observational result. Run a
  **holdout test** — same product, matched period, discount withheld from a
  random slice. That is the only way to get a causal answer, and it is cheap
  relative to the margin at stake.
- Meanwhile, treat "we discounted it" as an unproven intervention rather than a
  known lever.

---

## 5. The 32% missing categories cannot be recovered — don't try

`gold.category_recovery_check`

31.8% of rows have no `category_code`, and 10.1% of revenue lands in an
`unknown` bucket. The obvious fix is to backfill from `category_id`, which is
always populated: find another row with the same id and copy its code across.

**It does not work.** Of the **372** distinct `category_id` values that appear
with a blank code, **zero** ever appear with a populated one. The blank-code
categories are a **disjoint set**, not a sparsely-labeled one. There is nothing
to join back to.

This is recorded as a table on purpose. A negative result that stops the next
engineer spending a day on the obvious fix is worth as much as a positive one —
and this is exactly the kind of thing that gets re-attempted every six months by
someone who wasn't there.

**What to do**
- The fix has to come from the **source product catalog**. It cannot be imputed
  from this dataset at any level of effort.
- Until then, keep reporting `unknown` as a visible row rather than dropping it,
  so every category ranking carries its own caveat.

---

## Ranked by value, net of effort

| # | Action | Size | Effort | Type |
|---|---|---|---|---|
| 1 | **Accessory attach on phone purchases** | ~$2.6M/mo | Medium | Merchandising |
| 2 | **Retarget high-intent non-buyers** | $41.6M pool | **Low** | Query + campaign |
| 3 | **Instrument checkout steps** | Unblocks the ~50% | Low | Engineering |
| 4 | **Free-shipping threshold under $50** | Sub-band lift | Low | Pricing |
| 5 | **Holdout-test discounting** | Protects margin | Medium | Experiment |
| — | ~~Backfill missing categories~~ | **Impossible** | — | Don't |

**If one thing gets done: #2.** The high-intent segment is a single query
against an existing gold table, the audience is already qualified, and no
product, pricing, or catalog change is required to act on it.

**The one prerequisite behind several of these**: the cart-event tracking gap
(54% of purchases have no cart event, see [`INSIGHTS.md`](INSIGHTS.md)). Until
that is fixed, checkout-stage measurement stays partly inferred.
