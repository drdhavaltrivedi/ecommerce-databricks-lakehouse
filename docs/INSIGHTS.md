# What the data says, and what to do about it

Based on the full two months now loaded, October–November 2019: 109.9M events,
23.1M sessions, 5.32M users, $505.1M realized revenue across 61 days.

All figures come from `ecommerce.gold.*`. Read
[the data quality section](#0-read-this-first-the-numbers-have-known-holes)
before quoting any of them — and read it even if you already have, because
adding November changed the story, not just the totals.

---

## 0. Read this first: the numbers have known holes — and one hole moves month to month

`gold.data_quality` is a first-class table, not an afterthought.

| Issue | Scale | Why it matters |
|---|---|---|
| **Purchases with no cart event** | **32.97%** of purchasing sessions, combined — but **53.6% in October vs. 16.2% in November** | See below — this is not a stable defect. |
| **Missing `category_code`** | **32.2%** of rows | 10.5% of all revenue lands in an `unknown` category bucket. Stable across both months. |
| **Missing `brand`** | **13.9%** of rows | Brand ranking is biased toward well-tagged brands. Stable across both months. |
| Sessions spanning >24h | 0.17% | `user_session` ids get reused across visits. |
| Price ≤ 0 | 0.23% | Distorts AOV if not excluded from pricing analysis. |

**This correction matters, so it's stated plainly**: an earlier version of this
document, written against October alone, argued the cart-tracking gap was
*"a systematic defect... at a steady rate rather than in bursts."* That claim
was based on comparing a partial October load against the complete one — the
same month, sampled twice. It was never tested against a *different* month.
Now that November has been added, it's clear that conclusion doesn't hold:

| Month | Purchase sessions | Missing cart event | Rate |
|---|---|---|---|
| October | 629,572 | 337,699 | **53.64%** |
| November | 773,186 | 124,839 | **16.15%** |

The defect rate **more than halved** between October and November. It isn't
purchase-specific either — cart-event logging across *all* sessions (not just
ones that converted) roughly doubled, from 6.20% of October sessions to
12.66% of November sessions. Something changed operationally between the two
months: a tracking fix, an app update, a different checkout flow rolled out
for the November promotional period — the data can't say which, but it can
say the change is real, broad, and dated to around November 1st.

**The corrected view stands, with a caveat now attached to it**: `gold.funnel`
is still computed monotonically (a session that purchased is credited with
reaching the cart stage even without a logged cart event), and the raw counts
are still preserved (`sessions_cart_logged`, `purchases_missing_cart_event`).
But because the underlying defect rate is month-dependent, **any metric built
from cart events — including abandoned-cart value — should be read per month,
never pooled**, until the root cause of the October/November change is
understood. Section 3 below is a direct example of why.

**What to fix at the source**: find what changed between October and
November and ship it retroactively if possible. Whatever fixed 37 points of
missing-cart-event rate is the highest-value engineering change available —
worth more than any single feature built on top of the current data.

---

## 1. The funnel leaks at discovery, not checkout

| Stage | Sessions | Conversion |
|---|---|---|
| Viewed | 23,016,650 | — |
| Added to cart (adjusted) | 2,778,970 | **12.07%** |
| Purchased | 1,402,758 | **50.48%** of carts |
| **View → purchase** | | **6.09%** |

**The story changed from the October-only read, and it's worth saying why.**
Cart-to-purchase dropped from 69.1% (October) to 50.5% (combined) — not
because checkout got worse, but because November's better cart-event logging
means far more *genuine* adds-to-cart are now visible, including ones that
were never going to convert. October's 69.1% cart-to-purchase rate was
inflated by the same defect described in section 0: with 54% of purchases
missing their cart event, the sessions that *did* have a logged cart were a
biased sample, skewed toward ones that also converted. November's more
complete logging is the more trustworthy number.

**The view→cart step is still the largest leak** — 88% of sessions that view
a product never add anything to a cart — and that conclusion is unchanged
across both readings. **Where to spend effort**: the view→cart step still
addresses roughly 8× the population that a checkout-optimization effort would
reach (view→cart pool vs. the ~50% of carts that don't convert).

---

## 2. Revenue is dangerously concentrated in one category

| Category | Revenue | Share |
|---|---|---|
| `electronics.smartphone` | $334.9M | **66.3%** |
| `electronics.video.tv` | $20.9M | 4.1% |
| `computers.notebook` | $19.7M | 3.9% |
| *(unlabeled)* | — | 10.5% |

**Two-thirds of all revenue is smartphones** — consistent with the
October-only read (68.3%), so this finding held up unchanged when the second
month was added, which is itself useful evidence: the concentration is a
structural feature of this business, not an October artifact.

**What to do**: unchanged from before — this needs a deliberate decision, not
a dashboard. Either accept the concentration and optimize hard around
smartphone margin and attach-rate, or fund growth in the #2–#5 categories.

**Attach-rate opportunity**: headphones convert at 4.27% view→purchase,
smartphones at 4.33% — essentially tied, and still the strongest natural
smartphone attach category.

---

## 3. Abandoned cart value — read this per month, not combined

Combined across both months: 1,376,515 abandoned sessions, **$465.7M**,
against $505.1M in realized revenue — a **92.2%** ratio that on its own reads
as an almost unbelievable number. Splitting it by month explains why, and
why the combined figure shouldn't be quoted on its own:

| Month | Abandoned sessions | Abandoned value | Revenue | Ratio |
|---|---|---|---|---|
| October | 281,285 | $99.5M | $229.9M | 43.3% |
| November | 1,095,230 | $366.3M | $275.2M | **133.0%** |

November's abandoned value *exceeds* November's total revenue. Two real
effects are stacked here, and they should not be collapsed into one number:

1. **October's $99.5M was very likely an undercount.** `gold.cart_abandonment`
   only counts sessions with a *logged* cart event — the same defect from
   section 0 that hid 54% of October's purchase-side cart events almost
   certainly hid a comparable share of October's abandonment-side cart
   events too. The true October abandonment figure is unknown, but $99.5M is
   a floor, not an estimate.
2. **November genuinely has far more browsing-to-cart activity relative to
   purchases.** Total sessions rose 49% month over month (9.24M → 13.77M)
   while purchase sessions rose only 23% (629K → 773K) — consistent with a
   Black-Friday-adjacent traffic surge that brought a wave of browsers who
   added items to carts without the intent or urgency to buy.

**What to do**: don't quote "$465.7M / 92.2% of revenue" as a single
headline — it conflates a corrected floor with a real number and produces a
figure that invites (deserved) skepticism. Quote November's $366.3M as the
recovery opportunity for a Black-Friday-scale traffic month, and flag October's
$99.5M explicitly as a lower bound pending the tracking-fix investigation in
section 0. Standard abandoned-cart recovery campaigns recover 5–15% of
abandoned value; applied to November alone, that's **$18.3M–$54.9M** — still
the single largest recoverable pool in the dataset, and a more defensible
number than the pooled one.

---

## 4. High traffic ≠ high value: some categories are pure browsing

Categories with heavy traffic but near-zero conversion:

| Category | Views | Conversion | Revenue |
|---|---|---|---|
| `apparel.costume` | 328,900 | **0.42%** | $125K |
| `furniture.living_room.sofa` | 434,847 | 0.61% | $1.43M |
| `apparel.shoes.keds` | 736,199 | 0.68% | $357K |
| `apparel.shoes` | 2,054,877 | 0.70% | $1.26M |

Compare with `electronics.smartphone` at **4.33%** — roughly **6–10× the
conversion rate** of these categories.

**What to do**: unchanged from the October-only read — this is either a
sizing/returns-confidence problem, a pricing problem, or a catalog-depth
problem, worth investigating directly rather than inferring from aggregate
conversion alone.

---

## 5. Apple drives the value, Samsung drives the volume

| Brand | Purchases | Revenue | AOV |
|---|---|---|---|
| Apple | 308,922 | **$238.7M** | **$773** |
| Samsung | 372,904 | $101.3M | $272 |
| Xiaomi | 124,900 | $20.5M | $164 |

Samsung sells **21% more units** than Apple but generates **58% less
revenue** — the same ratio as the October-only read, which is a second
confirmation (alongside section 2) that this business's category and brand
structure is stable across months even though its funnel behavior isn't.

**What to do**: unchanged — Apple customers are the high-value segment;
Samsung is the volume play. These should not share a merchandising strategy.

---

## 6. Roughly 13% of users buy — repeat-buyer behavior is stable

- 5,316,649 total users
- 697,470 buyers (**13.1%**)
- 295,309 repeat buyers — **42.3% of buyers come back within the period**

Both the buyer rate and the repeat rate improved slightly versus the
October-only read (11.5% → 13.1% purchase rate, 38% → 42% repeat rate) —
consistent with November's traffic surge converting at a *lower* rate overall
(more low-intent browsers) while still adding enough real buyers to lift the
repeat-purchase base.

**What to do**: unchanged in direction — this still argues for aggressive
first-purchase incentives given the strong repeat behavior once someone
converts once.

---

## 7. Traffic peaks 06:00–11:00 UTC

Revenue peaks at hour 9 UTC ($39.7M combined), with 06:00–11:00 UTC still the
clear daily band across both months. UTC+3 puts the real peak at roughly
09:00–14:00 local time.

**What to do**: unchanged from before.

---

## Priority ranking

If only three things get done:

1. **Find out what changed between October and November's cart tracking** —
   a 37-point swing in a single defect rate, in one direction, is the highest
   information-density finding in this dataset. It should be investigated
   before any other cart-stage metric is trusted at face value.
2. **Launch abandoned-cart recovery, sized off November, not the pooled
   figure** — $366.3M pool from a Black-Friday-scale month, 5–15% typical
   recovery, no product changes needed.
3. **Attack the view→cart step** — still the largest leak in the funnel,
   88% of sessions never add to cart, unchanged in direction across both
   months.

Deliberately *not* in the top three: checkout optimization (already
converting roughly half of carts, and that number itself needs the October
data-quality caveat before further tuning) and category expansion (strategic,
slow, needs a business decision rather than a data one).
