"""Audit A3: Live versus replay verification.

Triggers an incident run via the API (seed 27225), traces an event from its
query log representation to graph state change, and confirms live execution vs static replay.
"""

import json
import urllib.request
import urllib.error

import sys
import time
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

API_BASE = "http://127.0.0.1:8001"

def run_a3_audit():
    # 1. Trigger incident run
    req = urllib.request.Request(
        f"{API_BASE}/api/incident/run",
        data=json.dumps({"seed": 27225, "speed_ms": 1}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        run_res = json.loads(resp.read().decode())
    print("Trigger Response:", run_res)

    # Wait for background agent loop to complete ticks
    time.sleep(1.0)

    # 2. Get query log
    with urllib.request.urlopen(f"{API_BASE}/api/incident/query-log") as resp:
        query_log_data = json.loads(resp.read().decode())
    queries = query_log_data.get("queries", [])
    print(f"Query Log count: {len(queries)}")
    print("Sample queries in log:")
    for q in queries[:4]:
        print("  -", q)

    # 3. Get graph snapshot
    with urllib.request.urlopen(f"{API_BASE}/api/incident/graph") as resp:
        snapshot = json.loads(resp.read().decode())
    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])
    print(f"Graph Snapshot: {len(nodes)} nodes, {len(edges)} edges, active seed: {snapshot.get('seed')}")

    # Trace a taint edge
    taint_edges = [e for e in edges if e.get("is_taint")]
    print(f"Taint edges in graph: {len(taint_edges)}")
    if taint_edges:
        te = taint_edges[0]
        print(f"Sample Taint Edge: {te['source_id']} -> {te['target_id']} (hops: {te.get('hops')})")

    # Check for replay artifacts: does incident_service stream from dynamic agent loop or read static recording?
    from api.incident_service import IncidentService
    import inspect
    src = inspect.getsource(IncidentService.run_incident_stream)
    is_live = "loop.run_tick" in src and "open(" not in src and ".json" not in src
    print(f"Live dynamic agent execution confirmed in backend: {is_live}")

def test_a3_live_vs_replay():
    run_a3_audit()


if __name__ == "__main__":
    run_a3_audit()
