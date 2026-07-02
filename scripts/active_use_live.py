#!/usr/bin/env python3
#
# Author: Ryan Duffy <ryanduffy.uk@gmail.com>
# ORCID: 0009-0009-6464-0617
# Generated with: Claude Code
#
"""Active-use eval against a running qwen-memory-agent server.

LIVE tool - drives /chat against a real deployment and spends Qwen credits
(~25 calls for the 10-scenario set). Point it at a server you own:

    ACTIVE_USE_BASE_URL=http://<host>:8000 python3 scripts/active_use_live.py

Run against a FRESH store (restart with the persist snapshot removed) so store
checks are not polluted by prior facts. Scoring lives in benchmark/active_use.py
(offline-importable, unit-tested); this script only supplies HTTP transport and
writes the artifacts:

    benchmark/results/active_use.json        summary + per-scenario rows
    active_use_rows.jsonl                    streaming per-scenario evidence

Oracle = store state via /memory/export + tool_calls_made of the decision turn,
never the model's prose alone.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmark.active_use import SCENARIOS, aggregate, run_scenario, score_scenario  # noqa: E402

BASE = os.getenv("ACTIVE_USE_BASE_URL", os.getenv("FUZZ_BASE_URL", "http://localhost:8000"))
ROWS_OUT = os.getenv("ACTIVE_USE_ROWS", "active_use_rows.jsonl")
SUMMARY_OUT = os.getenv(
    "ACTIVE_USE_SUMMARY",
    str(Path(__file__).resolve().parent.parent / "benchmark" / "results" / "active_use.json"),
)


def api(path, payload=None, timeout=90):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"content-type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat(message, session_id):
    r = api("/chat", {"message": message, "session_id": session_id})
    return r["answer"], r["tool_calls_made"]


def records():
    return [e["record"] for e in api("/memory/export")["json"]["records"]]


def run():
    t0 = time.time()
    start_count = len(records())
    print(f"base={BASE} start_records={start_count}", flush=True)
    if start_count:
        print(
            f"WARNING: store is not fresh ({start_count} records) - "
            "keyword store checks may be polluted",
            flush=True,
        )

    rows = []
    for scenario in SCENARIOS:
        try:
            answer, tool_calls = run_scenario(chat, scenario, session_prefix="active-")
            time.sleep(0.5)  # let the persist snapshot settle before the store read
            row = score_scenario(
                answer=answer,
                tool_calls=tool_calls,
                records=records(),
                scenario=scenario,
            )
        except Exception as exc:  # noqa: BLE001 - live harness must survive one bad scenario
            row = {
                "id": scenario["id"],
                "depth": scenario["depth"],
                "outcome_pass": False,
                "store_pass": False,
                "process_pass": False,
                "task_success": False,
                "violations": [],
                "error": str(exc)[:200],
            }
        rows.append(row)
        with open(ROWS_OUT, "a") as f:
            f.write(json.dumps(row) + "\n")
        verdict = "PASS" if row["task_success"] else "FAIL"
        print(
            f"[{verdict}] {row['id']} depth={row['depth']} "
            f"outcome={row.get('outcome_pass')} store={row.get('store_pass')} "
            f"process={row.get('process_pass')} violations={row.get('violations')}",
            flush=True,
        )

    summary = {
        "provenance": f"live-{urlparse(BASE).hostname}-{datetime.now(timezone.utc).date().isoformat()}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url_host": urlparse(BASE).hostname,
        "scenario_count": len(SCENARIOS),
        "aggregate": aggregate(rows),
        "rows": rows,
    }
    Path(SUMMARY_OUT).parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_OUT, "w") as f:
        json.dump(summary, f, indent=2)

    agg = summary["aggregate"]
    print(
        f"\n==== DONE in {time.time() - t0:.0f}s: "
        f"task_success={agg['task_success_rate']:.2f} "
        f"outcome={agg['outcome_pass_rate']:.2f} store={agg['store_pass_rate']:.2f} "
        f"process={agg['process_pass_rate']:.2f} "
        f"violations={agg['constraint_violation_rate']:.2f} ====",
        flush=True,
    )
    for depth, stats in agg["by_depth"].items():
        print(
            f"  depth {depth}: n={stats['n']} task_success={stats['task_success']:.2f}", flush=True
        )
    print(f"summary -> {SUMMARY_OUT}", flush=True)


if __name__ == "__main__":
    run()
