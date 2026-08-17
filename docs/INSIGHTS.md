# What the data says, and what to do about it

Based on October 2019 (partial month at time of writing: Oct 1–22, ~30M
events, 6.5M sessions, 2.36M users, $164M realized revenue).

All figures come from `ecommerce.gold.*`. Read
[the data quality section](#0-read-this-first-the-numbers-have-known-holes)
before quoting any of them.

---

## 0. Read this first: the numbers have known holes

`gold.data_quality` is a first-class table, not an afterthought, because three
issues materially change how every other number should be read.

| Issue | Scale | Why it matters |
|---|---|---|
| **Purchases with no cart event** | **53.9%** of purchasing sessions | The raw funnel produces a **110% cart→purchase rate** — arithmetically impossible. Cart events are systematically under-logged. |
| **Missing `category_code`** | **32.1%** of rows | 10.1% of all revenue lands in an `unknown` category bucket. Category strategy built on the labeled 90% is skewed. |
| **Missing `brand`** | **14.1%** of rows | Brand ranking is biased toward well-tagged brands. |
| Sessions spanning >24h | 0.18% | `user_session` ids get reused across visits, slightly depressing per-session conversion. |
| Price ≤ 0 | 0.16% | Distorts AOV if not excluded from pricing analysis. |

**The fix applied**: `gold.funnel` is computed **monotonically** — a session
that purchased is credited with reaching the cart stage even when no cart
event was logged. The raw count is preserved alongside it
(`sessions_cart_logged`, `purchases_missing_cart_event`) so the gap stays
visible rather than being silently smoothed over.

**What to fix at the source**: the cart-event tracking is the highest-value
engineering fix available. Over half of all purchases are missing their cart
step, which means no reliable measurement of cart-stage friction, cart
value, or time-in-cart. Everything downstream of "did they add to cart" is
currently guesswork.

---

## 1. The funnel leaks at discovery, not checkout

| Stage | Sessions | Conversion |
|---|---|---|
| Viewed | 6,501,390 | — |
| Added to cart (adjusted) | 652,553 | **10.0%** |
| Purchased | 450,901 | **69.1%** of carts |
| **View → purchase** | | **6.94%** |

**The story**: checkout works. Once a shopper puts something in the cart,
69% of the time they buy it — that's a healthy rate, and it means payment
flow, shipping options, and checkout UX are not the bottleneck.

**The problem is upstream**: 90% of sessions that view a product never add
anything to a cart. That's a product-discovery, pricing, or
merchandising problem, not a checkout problem.

**Where to spend effort**: optimizing checkout would fight over the 31% who
abandon a cart. Optimizing the view→cart step addresses 90% of sessions.
That's roughly a 3× larger pool.

---

## 2. Revenue is dangerously concentrated in one category

| Category | Revenue | Share |
|---|---|---|
| `electronics.smartphone` | $112.2M | **68.2%** |
| `computers.notebook` | $6.5M | 4.0% |
| `electronics.video.tv` | $5.9M | 3.6% |
| *(unlabeled)* | $16.6M | 10.1% |

**Two-thirds of all revenue is smartphones.** This is a concentration risk:
one supply disruption, one competitor price war, or one seasonal shift in
handset launch cycles moves the entire business.

**What to do**: this needs a deliberate decision, not a dashboard. Either
(a) accept the concentration and optimize hard around smartphone margin,
inventory, and attach-rate, or (b) fund growth in the #2–#5 categories.
Right now the data suggests the business is a smartphone retailer that also
sells other things.

**Attach-rate opportunity**: headphones convert at 4.65% view→purchase —
the second-best rate of any major category, and a natural smartphone
attach. There is likely untapped bundling revenue here.

---

## 3. There is $71.8M sitting in abandoned carts

201,693 sessions added something to a cart and never bought.
**That's $71.8M — equal to 43.6% of realized revenue.**

Even with the tracking caveat above (real abandonment is likely *higher*,
since half of cart events go unlogged), this is the single largest
recoverable revenue pool in the dataset.

**What to do**: abandoned-cart email/push recovery campaigns typically
recover 5–15% of abandoned value. Applied here, that's a **$3.6M–$10.8M**
opportunity in a single month, and it requires no change to the product or
pricing — only to the messaging pipeline.

---

## 4. High traffic ≠ high value: some categories are pure browsing

Categories with heavy traffic but near-zero conversion:

| Category | Views | Conversion | Revenue |
|---|---|---|---|
| `apparel.shoes` | 430,943 | **0.66%** | $247K |
| `apparel.shoes.keds` | 248,504 | 0.77% | $136K |
| `furniture.living_room.cabinet` | 122,044 | 0.81% | $246K |
| `computers.desktop` | 186,905 | 1.19% | $787K |

Compare with `electronics.smartphone` at **4.85%** — roughly **7× the
conversion rate of shoes**.

**The story**: apparel.shoes pulls 431K views and returns $247K. It consumes
significant merchandising real estate and traffic acquisition budget while
generating 0.15% of revenue.

**What to do**: this is either a sizing/returns-confidence problem (typical
for footwear sold online without fit tooling), a pricing problem, or a
catalog-depth problem. Worth a targeted investigation — but if the answer
is "we can't win in footwear", that traffic and shelf space is better
redirected to electronics attach categories.

---

## 5. Apple drives the value, Samsung drives the volume

| Brand | Purchases | Revenue | AOV |
|---|---|---|---|
| Apple | 102,349 | **$79.6M** | **$777** |
| Samsung | 123,473 | $33.1M | $268 |
| Xiaomi | 40,305 | $6.5M | $161 |

Samsung sells **21% more units** than Apple but generates **58% less
revenue**. Apple's AOV is 2.9× Samsung's.

**What to do**: Apple customers are the high-value segment — they warrant
differentiated treatment (premium support, trade-in offers, accessory
bundling at higher price points). Samsung is the volume/margin play. These
should not share a merchandising strategy.

---

## 6. Only 11% of users ever buy — but repeat buyers are real

- 2,360,159 total users
- 262,286 buyers (**11.1%**)
- 95,142 repeat buyers — **36% of buyers come back within the month**

**The story**: the 11% purchase rate is the headline weakness, but the 36%
repeat rate among buyers is genuinely strong. The business converts poorly
but retains well.

**What to do**: this argues for aggressive first-purchase incentives. The
data says that if you can get someone over the line once, there's a better
than one-in-three chance they buy again within the same month. First-purchase
discounting has a much better payback profile here than it would at a
business with weak retention.

---

## 7. Traffic peaks 06:00–11:00 UTC

Revenue peaks at hour 9 UTC ($13.2M), with 06:00–11:00 UTC forming the
clear daily band. The source store is Russian-market, so UTC+3 puts the
real peak at **roughly 09:00–14:00 local time** — a workday-morning
shopping pattern, not an evening one.

**What to do**: schedule promotional sends, flash sales, and inventory
updates to land just before 06:00 UTC. Ensure support staffing and any
deploy freezes respect the 06:00–11:00 UTC window.

---

## Priority ranking

If only three things get done:

1. **Fix cart-event tracking** — 54% of purchases have no cart event. This
   blinds every funnel decision until fixed. Engineering, not analytics.
2. **Launch abandoned-cart recovery** — $71.8M pool, well-understood
   playbook, 5–15% typical recovery, no product changes needed.
3. **Attack the view→cart step** — 90% of sessions leak here versus 31% at
   checkout. Three times the addressable population.

Deliberately *not* in the top three: checkout optimization (already at 69%,
limited headroom) and category expansion (strategic, slow, and needs a
business decision rather than a data one).
