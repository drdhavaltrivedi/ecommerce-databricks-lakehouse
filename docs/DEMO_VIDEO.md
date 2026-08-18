# Demo video — shot list and captions

Two jobs, one recording:

1. **Attract loop** — plays on the booth screen when nobody is standing there,
   and has to stop someone mid-walk.
2. **Fallback** — when the wifi dies or the warehouse is cold, you switch to
   this and keep talking over it without missing a beat.

## The constraint that shapes everything

**A trade show hall is loud, and nobody will hear your audio.** Seamless is a
big, noisy room. So:

- **Record silent.** No voiceover. Do not rely on sound for anything.
- **Every point must be an on-screen caption**, large enough to read from
  2–3 metres.
- **It must loop cleanly** — no fade to black, no end card that sits there dead.
- Target **60–75 seconds**. Longer and the loop feels slow when someone catches
  it mid-way.

Record at **1920×1080**, browser zoom **150%** (booth screens are viewed from
much further than a desk), cursor visible, everything else on screen hidden —
no bookmarks bar, no notifications, no other tabs.

---

## Shot list

Timings are targets, not exact. Total 68s.

| # | Time | On screen | Caption (burned in) |
|---|---|---|---|
| 1 | 0:00–0:05 | Booth dashboard, top KPI row, still | **42,448,764 real shopping events** |
| 2 | 0:05–0:12 | Slow pan across the four counters | **Three things this store was losing money on** |
| 3 | 0:12–0:20 | Hold on the $99.5M counter | **$99.5M left in abandoned carts — 43% of what it earned** |
| 4 | 0:20–0:28 | Scroll to the price-band chart, hold | **Everyone assumes that's a pricing problem** |
| 5 | 0:28–0:38 | Hold on chart, cursor traces the flat bars left→right | **It isn't. Conversion is flat from $50 to $1,000+** |
| 6 | 0:38–0:44 | Same chart, cursor rests on the low bars | **So it's checkout friction, not cost** |
| 7 | 0:44–0:52 | Cut to Genie. Type the question live | *(no caption — let the typing read)* |
| 8 | 0:52–1:02 | Genie's answer appears, hold on it | **Ask it anything. In plain English.** |
| 9 | 1:02–1:08 | Hold on the caveat sentence in the answer | **It tells you when the data can't prove it** |

Then cut straight back to shot 1. No end card, no logo sting — it loops.

### The Genie question to type in shot 7

Type this one, character by character, at readable speed:

> **Should we discount more to boost conversion?**

**This is the most important shot in the video.** The answer comes back with the
numbers *and* the sentence about the result being confounded and needing a
holdout test. Shot 9 exists purely to hold on that sentence.

Anyone in that hall who has been sold an AI tool is quietly worried about it
producing confident nonsense. Ten seconds of it visibly refusing to overclaim
does more than any feature list.

---

## Recording it

```bash
# 1. warm the warehouse first, or the recording captures a spinner
python3 scripts/keep_warm.py
```

Wait for two clean pings, then:

- macOS: **⌘⇧5** → Record Selected Portion → crop to the browser window
- Pre-load the booth dashboard **before** hitting record, so nothing loads on camera
- Pre-run the Genie question once before recording, so shot 7's answer is
  cache-warm and comes back fast
- Do the whole thing in **one take** if you can — cuts between tools look
  stitched, and a continuous take reads as "this is just working"

### Then

- Add captions in any editor (or Canva / CapCut). White text, dark scrim behind
  it, bottom third, large.
- Export **MP4, H.264, 1080p**.
- Save it **locally on the booth laptop.** Not Drive, not Dropbox. The entire
  point is that it survives the wifi dying.
- Also put a copy on a phone, in case the laptop is the thing that fails.

---

## Using it at the stand

**As the attract loop**: muted, looping, fullscreen on the booth screen whenever
nobody is mid-conversation.

**As the fallback**: the moment something hangs for more than a few seconds,
switch to it and keep talking. Do not narrate a loading spinner and do not
apologise for it — most visitors will not register that anything went wrong.

> "Here — this is it running on the full 42 million rows."

Then carry on with the same script from [`BOOTH_DEMO.md`](BOOTH_DEMO.md). The
video covers the same beats in the same order, so your words still line up.

---

## What not to put in it

- **No voiceover.** Nobody will hear it.
- **No architecture diagram.** That is the second conversation, and it is not
  what stops someone walking past.
- **No stock footage of shoppers or warehouses.** It signals marketing, and the
  credibility here comes from the numbers being real.
- **No claim this is client data.** It's public Kaggle data from a real
  retailer — the provenance line is already on the one-pager and should stay
  visible in shot 1 if it happens to be in frame.
