#!/usr/bin/env python3
"""Create/update the scheduled Databricks Job that refreshes the pipeline.

Until now the pipeline only ran when someone ran it by hand, which means the
dashboard is only as fresh as the last person who remembered. This wires the
same SQL files into a scheduled Workflow.

Design notes:
- Tasks are SQL-file tasks against the SQL warehouse, so the job uses the same
  compute as everything else -- no cluster to size, no idle cost.
- The dependency chain is explicit (bronze -> silver -> gold -> dq -> optimize).
  Gold reads silver; running them concurrently would read a half-built table.
- Data quality runs AFTER gold and BEFORE optimize, so a DQ regression is
  visible before the expensive layout work runs.
- The schedule is PAUSED on creation. An unpaused schedule created by a script
  starts consuming warehouse time on someone else's account without them
  agreeing to it; turning it on is a decision for whoever owns the bill.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

JOB_NAME = "ecommerce-medallion-refresh"

# Workspace path where the SQL files must live for the job to read them.
# Jobs run in the workspace, not on your laptop, so the .sql files have to be
# uploaded there -- see upload_sql_to_workspace() below.
WS_DIR = "/Shared/ecommerce/sql"

TASKS = [
    ("bronze",     "01_bronze.sql",       []),
    ("silver",     "02_silver.sql",       ["bronze"]),
    ("gold",       "03_gold.sql",         ["silver"]),
    ("dq",         "04_data_quality.sql", ["gold"]),
    ("governance", "05_governance.sql",   ["silver"]),
    ("optimize",   "06_optimize.sql",     ["dq", "governance"]),
    ("opportunities", "09_opportunities.sql", ["gold"]),
    ("deep_dive",   "10_deep_dive.sql",    ["opportunities"]),
]


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {e.read().decode()[:600]}", file=sys.stderr)
        raise


def upload_sql_to_workspace():
    """Push the local sql/ files into the workspace so the job can run them."""
    import base64
    repo_sql = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")
    api("POST", "/api/2.0/workspace/mkdirs", {"path": WS_DIR})
    for _, filename, _ in TASKS:
        with open(os.path.join(repo_sql, filename), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        api("POST", "/api/2.0/workspace/import", {
            "path": f"{WS_DIR}/{filename}",
            "format": "RAW",
            "content": content,
            "overwrite": True,
        })
        print(f"  uploaded {filename}")


def build_job_settings():
    tasks = []
    for key, filename, depends in TASKS:
        task = {
            "task_key": key,
            "sql_task": {
                "file": {"path": f"{WS_DIR}/{filename}", "source": "WORKSPACE"},
                "warehouse_id": WAREHOUSE_ID,
            },
        }
        if depends:
            task["depends_on"] = [{"task_key": d} for d in depends]
        tasks.append(task)

    return {
        "name": JOB_NAME,
        "tasks": tasks,
        "schedule": {
            # 05:00 UTC daily -- before the 06:00-11:00 UTC trading peak, so the
            # warehouse is not competing with live dashboard usage
            "quartz_cron_expression": "0 0 5 * * ?",
            "timezone_id": "UTC",
            "pause_status": "PAUSED",
        },
        "max_concurrent_runs": 1,
        "queue": {"enabled": True},
        "email_notifications": {"on_failure": []},
        "tags": {"project": "ecommerce", "layer": "pipeline"},
    }


def find_existing():
    res = api("GET", f"/api/2.2/jobs/list?name={urllib.parse.quote(JOB_NAME)}")
    for j in res.get("jobs", []):
        if j["settings"]["name"] == JOB_NAME:
            return j["job_id"]
    return None


if __name__ == "__main__":
    import urllib.parse

    print("Uploading SQL files to workspace...")
    upload_sql_to_workspace()

    settings = build_job_settings()
    existing = find_existing()
    if existing:
        api("POST", "/api/2.2/jobs/reset", {"job_id": existing, "new_settings": settings})
        job_id = existing
        print("Updated job:", job_id)
    else:
        job_id = api("POST", "/api/2.2/jobs/create", settings)["job_id"]
        print("Created job:", job_id)

    print(f"  tasks:    {' -> '.join(k for k, _, _ in TASKS)}")
    print(f"  schedule: 05:00 UTC daily (PAUSED -- enable in the UI when ready)")
    print(f"URL: {HOST}/jobs/{job_id}")
