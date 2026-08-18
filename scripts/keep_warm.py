#!/usr/bin/env python3
"""Keep the SQL warehouse warm during show hours.

The warehouse auto-stops after 10 minutes idle. That is correct for normal use
and fatal at a trade show: a visitor stops at the booth, you open the dashboard,
and it spends 40 seconds cold-starting while they lose interest and walk off.

This pings the warehouse on an interval so it never goes cold. Run it in a
terminal on the booth laptop for the duration of the show and forget about it.

    python3 scripts/keep_warm.py                 # ping every 5 minutes, forever
    python3 scripts/keep_warm.py --interval 240  # tighter interval
    python3 scripts/keep_warm.py --until 18:00   # stop at end of show day

Cost is negligible -- a trivial SELECT every few minutes -- but it is not zero,
so do not leave it running after the show.
"""
import os, sys, json, time, argparse, urllib.request, urllib.error
from datetime import datetime, timedelta

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read() or b"{}")


def warehouse_state():
    return api("GET", f"/api/2.0/sql/warehouses/{WAREHOUSE_ID}").get("state")


def ping():
    """Cheap query that touches a real gold table, so the result cache and the
    cluster are both warm for the queries the demo will actually run."""
    res = api("POST", "/api/2.0/sql/statements", {
        "warehouse_id": WAREHOUSE_ID,
        "statement": "SELECT COUNT(*) FROM ecommerce.gold.funnel",
        "wait_timeout": "30s",
    })
    return res.get("status", {}).get("state")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=300,
                   help="seconds between pings (default 300; keep well under the 600s auto-stop)")
    p.add_argument("--until", type=str, default=None,
                   help="stop at this local time today, e.g. 18:00")
    args = p.parse_args()

    stop_at = None
    if args.until:
        hh, mm = (int(x) for x in args.until.split(":"))
        stop_at = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if stop_at < datetime.now():
            stop_at += timedelta(days=1)
        print(f"Will stop at {stop_at:%Y-%m-%d %H:%M}")

    if args.interval >= 600:
        print("WARNING: interval >= 600s is longer than the 10-minute auto-stop; "
              "the warehouse will go cold between pings.", file=sys.stderr)

    print(f"Keeping warehouse {WAREHOUSE_ID} warm, every {args.interval}s. Ctrl-C to stop.")
    try:
        api("POST", f"/api/2.0/sql/warehouses/{WAREHOUSE_ID}/start")
    except urllib.error.HTTPError:
        pass  # already running

    while True:
        if stop_at and datetime.now() >= stop_at:
            print("Reached --until time. Stopping (warehouse will auto-stop on its own).")
            return
        try:
            t0 = time.time()
            state = ping()
            wh = warehouse_state()
            print(f"{datetime.now():%H:%M:%S}  ping={state}  warehouse={wh}  "
                  f"({time.time()-t0:.1f}s)")
        except Exception as e:
            # never die on a transient network blip -- expo wifi is unreliable,
            # and this script silently dying is exactly what must not happen
            print(f"{datetime.now():%H:%M:%S}  ping failed: {type(e).__name__}: {e}",
                  file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
