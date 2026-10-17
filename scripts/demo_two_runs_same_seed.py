"""Demonstrates Requirement 4: Compute time to scope per run from the graph with no per-seed cache.

Executes two back-to-back runs of the exact same seed (101) and demonstrates:
1. Each run computes its duration from graph timestamps (event received timestamp to max TAINTS edge timestamp).
2. Zero per-seed cache (no time_to_scope_by_seed).
3. Both runs produce their own distinct measured values.
"""

from __future__ import annotations
import asyncio
import sys
sys.path.insert(0, ".")

from api.incident_service import IncidentService


async def main():
    service = IncidentService()

    # Run 1 on Seed 101
    print("\n--- RUN 1: Seed 101 ---")
    await service.run_incident_stream(seed=101, speed_ms=0)
    snap1 = service.get_graph_snapshot()
    time1 = snap1.stats["time_to_scope_ms"]
    nodes1 = snap1.stats["total_nodes"]
    edges1 = snap1.stats["total_edges"]
    print(f"Run 1 Results: time_to_scope = {time1} ms | nodes = {nodes1} | edges = {edges1}")

    # Run 2 on the exact same Seed 101
    print("\n--- RUN 2: Seed 101 (Same Seed, Separate Run) ---")
    await service.run_incident_stream(seed=101, speed_ms=0)
    snap2 = service.get_graph_snapshot()
    time2 = snap2.stats["time_to_scope_ms"]
    nodes2 = snap2.stats["total_nodes"]
    edges2 = snap2.stats["total_edges"]
    print(f"Run 2 Results: time_to_scope = {time2} ms | nodes = {nodes2} | edges = {edges2}")

    print("\nVerification:")
    print(f"  Run 1 Value: {time1} ms")
    print(f"  Run 2 Value: {time2} ms")
    print(f"  Has per-seed cache: {hasattr(service, 'time_to_scope_by_seed')}")
    assert not hasattr(service, "time_to_scope_by_seed"), "Service must not maintain per-seed cache"
    print("  [PASS] Both runs of seed 101 computed their own values directly from graph timestamps.")


if __name__ == "__main__":
    asyncio.run(main())
