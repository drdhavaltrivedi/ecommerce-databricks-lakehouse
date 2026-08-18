#!/usr/bin/env python3
"""Run the full medallion pipeline end to end against the SQL warehouse.

Idempotent: bronze uses COPY INTO (already-loaded files are skipped), silver
and gold are CREATE OR REPLACE, governance uses IF NOT EXISTS semantics where
the API allows it. Safe to re-run after new files land in the volume.

Usage:
    python3 scripts/run_pipeline.py            # all layers
    python3 scripts/run_pipeline.py bronze     # a single layer
"""
import os, sys, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SQL_DIR = os.path.join(REPO, "sql")

LAYERS = [
    ("bronze",        "01_bronze.sql"),
    ("silver",        "02_silver.sql"),
    ("gold",          "03_gold.sql"),
    ("dq",            "04_data_quality.sql"),
    ("governance",    "05_governance.sql"),
    ("optimize",      "06_optimize.sql"),
    ("security",      "07_security.sql"),
    ("observability", "08_observability.sql"),
    ("opportunities", "09_opportunities.sql"),
]

REQUIRED_ENV = ["DATABRICKS_HOST", "DATABRICKS_TOKEN", "DBX_WAREHOUSE_ID"]


def main():
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing required env var(s): {', '.join(missing)}")

    only = sys.argv[1] if len(sys.argv) > 1 else None
    layers = [l for l in LAYERS if only is None or l[0] == only]
    if not layers:
        sys.exit(f"Unknown layer '{only}'. Choose from: {', '.join(n for n, _ in LAYERS)}")

    t_start = time.time()
    for name, filename in layers:
        path = os.path.join(SQL_DIR, filename)
        print(f"\n{'='*60}\n{name.upper()}  ({filename})\n{'='*60}")
        t0 = time.time()
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "run_sql_file.py"), path]
        )
        if result.returncode != 0:
            sys.exit(f"\n{name} failed after {time.time()-t0:.1f}s -- stopping.")
        print(f"{name} completed in {time.time()-t0:.1f}s")

    print(f"\nPipeline finished in {time.time()-t_start:.1f}s")
    print("Refresh the dashboard with: python3 scripts/create_dashboard.py")


if __name__ == "__main__":
    main()
