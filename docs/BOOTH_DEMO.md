# Booth demo runbook — Seamless Middle East 2026

Everything needed to run this at the stand: the 90-second script, the setup
checklist, what to do when it breaks, and the answers to questions you will
definitely be asked.

---

## The one thing to get right

A visitor gives you **seconds**, from three feet away, while deciding whether to
keep walking. They do not care about the architecture yet. They care whether you
can tell them something about their own business they didn't know.

So: **lead with the finding, not the pipeline.** The architecture is the second
conversation, and only with the people who ask for it.

---

## The 90-second script

### 0:00 — The hook (say this before showing anything)

> "Everyone in this hall thinks cart abandonment is a pricing problem.
> We analysed 110 million real shopping events across two months and it
> isn't. Want to see?"

That challenges a belief they already hold. It works because it is specific,
falsifiable, and about *their* problem. Do not open with "we built a lakehouse".

**If they stop, keep going. If they don't, you lost nothing.**

### 0:15 — The surprise (open the booth dashboard)

Point at the **cart conversion by price** chart.

> "Cart-to-purchase is flat — about 50% — from a $50 item all the way past
> $1,000. Twenty times the price, same conversion. If people were walking away
> because things cost too much, that line would fall. It doesn't.
>
> So whatever loses half of all carts isn't price. It's friction in checkout —
> delivery estimates, payment options, stock changing at the last step.
> That's a completely different fix, and it's cheaper."

**Why this lands**: it takes something they were about to spend money on
(discounting) and tells them it's aimed at the wrong target.

### 0:45 — The money on the table

Point at the two counters.

> "Two more. Only about 2.5% of people buying a phone here bought anything
> with it — no case, no headphones, nothing. In phone retail that's where the
> margin lives, and it's switched off. That's about $2.9M a month.
>
> And $166 million sits with people who looked at the same product ten or
> more times and never got asked to buy. Those customers convert at 29% when
> they do buy. They're already interested. Nobody followed up."

### 1:10 — Hand them the keyboard (Genie)

> "You don't need me to run this. Ask it yourself — plain English."

Let them type. Suggested prompts if they hesitate:
- *"Which categories get lots of views but few sales?"*
- *"How much revenue is stuck in abandoned carts?"*
- *"Should we discount more to boost conversion?"*

**That last one is the best demo in the whole stand.** It answers with the
numbers *and* explains that the result is confounded and needs a holdout test —
i.e. it refuses to give a confident wrong answer. That is the thing serious
buyers are worried about with AI, and you get to show it handling that
correctly, unprompted.

### 1:30 — Hand off

> "It's all open — architecture, SQL, the lot."

Give them the QR code / one-pager.

---

## Only if they ask: the technical story

For the data engineers and CTOs who want the build, not the findings:

- **Medallion on Databricks**: bronze (raw, untyped, 42.4M rows) → silver
  (typed star schema: fact + 2 conformed dimensions) → gold (14 tables — 9
  descriptive, 5 diagnostic)
- **Unity Catalog throughout** — PK/FK constraints, grain documented per table,
  PII classification tags, a column-mask function ready to activate
- **Liquid clustering** over date partitioning (0.93 clustering quality)
- **Everything is code** — SQL files plus API scripts, no clicked-together
  notebooks. Whole pipeline rebuilds in ~280s.
- **The interesting engineering problem**: the source CSV is 5.67GB, the Files
  API caps a single PUT at 5GiB, and this workspace has legacy DBFS disabled.
  Solution streams the file out of the zip in ~1GB line-aligned parts, each
  verified by size after upload.

### The honest bit — say this unprompted

> "One thing worth flagging: half the purchases in this data have no cart event
> logged at all. The tracking is broken. So the naive funnel returns a 110%
> cart-to-purchase rate, which is impossible.
>
> We didn't quietly patch it — the corrected number sits next to the raw one, so
> you can always see how much is measured and how much is inferred."

**This is your strongest credibility moment.** Anyone who has run a data team
has been burned by a dashboard that looked confident and was wrong. Showing that
you surface your own data's defects is worth more than any architecture diagram.

---

## Setup checklist — morning of each show day

```bash
export DATABRICKS_HOST="https://<workspace>.cloud.databricks.com"
export DATABRICKS_TOKEN="<fresh PAT>"
export DBX_WAREHOUSE_ID="<warehouse id>"

# 1. start the keep-warm loop and LEAVE IT RUNNING all day
python3 scripts/keep_warm.py --until 18:00
```

Then, in the browser, before the doors open:

- [ ] Booth dashboard open in tab 1, **already loaded** (not a cold page)
- [ ] Genie open in tab 2, with one question already asked and answered
      (proves it works, and warms the cache)
- [ ] GitHub repo in tab 3
- [ ] Fallback screen-recording saved **locally**, not in cloud storage
      (shot list: [`DEMO_VIDEO.md`](DEMO_VIDEO.md))
- [ ] Laptop sleep/screensaver **disabled**
- [ ] Browser zoom at ~125% — booth screens are viewed from further away than desks

### Why the keep-warm script matters

The warehouse auto-stops after 10 minutes idle. Without the script, the first
visitor after a quiet spell waits 30–60 seconds staring at a spinner. That is
the demo dying. Run it, and forget it.

**Stop it at the end of the show** — it costs a little, and there is no reason
to keep paying after the stand closes.

---

## When it breaks

| What happens | Do this |
|---|---|
| Dashboard spinning >10s | Keep talking, switch to the recording. Never narrate a loading screen. |
| Expo wifi drops | Switch to the recording ([`DEMO_VIDEO.md`](DEMO_VIDEO.md)) and keep talking. It covers the same beats in the same order, so your script still lines up. |
| Genie gives an odd answer | *"Good — that's why the caveats are built in, not bolted on."* Then re-ask more specifically. |
| Someone asks something the data can't answer | *"This dataset can't tell you that — there's no payment or refund status in it."* Say so. Guessing in front of a technical audience is fatal. |
| Token expires | Have a spare PAT written down offline. |

---

## Questions you will be asked

**"Is this your client's data?"**
No — and be precise here. It's a **public Kaggle dataset from a real
multi-category retailer, October–November 2019**. Someone in this audience may well
recognise it. Presenting it as a client engagement would be dishonest and is the
one thing that could actually damage you at this show. The work is the model and
the analysis, and that stands on its own.

**"Does this work on our data?"**
Yes — the shape is standard clickstream (user, session, product, event type,
price, timestamp). The medallion structure and every gold table transfers. What
changes is the category taxonomy and whatever their tracking gaps turn out to be.

**"How long did this take?"**
Be honest. It's a strong answer, not a weak one — the pipeline rebuilds in under
ten minutes and the whole two-month build cost under 10 DBUs of serverless
> compute.

**"What would you do first for us?"**
Data quality audit. Every finding here came *after* discovering the tracking gap.
If we'd trusted the raw funnel we'd have sent them optimising checkout — the one
part that already works.

**"Why Databricks and not Snowflake/BigQuery?"**
Don't oversell. Unity Catalog governance, Delta, and Genie in one place suited
this. The model itself is portable; the medallion pattern isn't vendor-specific.

---

## What NOT to do

- **Don't open with the architecture diagram.** It's the second conversation.
- **Don't say "AI-powered"** to this audience without immediately showing what it
  actually does. Seamless is saturated with that phrase.
- **Don't hide the data quality problem.** It's your best credibility asset.
- **Don't claim causality on the discount finding.** If someone pushes, the
  correct answer is *"it's confounded — you'd need a holdout test."* Getting
  that right in front of an analytics buyer is worth more than the finding.
- **Don't demo the 18-widget analysis dashboard.** Use the booth one. The big
  one is for the follow-up meeting.
