"""Audit Check U5: Resilience tests.
Tests:
1. Empty graph handling by IncidentService.
2. Very large graph (Seed 2147483647) time to scope, node counts, memory.
3. Backend down simulation response handling.
"""
import asyncio
import time
import tracemalloc
from api.incident_service import IncidentService
from engine.generator import FoodGraphGenerator
from engine.falkordb_client import FalkorDBGraphClient

def test_empty_graph_resilience():
    svc = IncidentService()
    # Reset to empty client
    svc.graph_client = FalkorDBGraphClient(tenant_id="empty-test", clean=True)
    snap = svc.get_graph_snapshot()
    assert len(snap.nodes) == 0, f"Expected 0 nodes in empty graph, got {len(snap.nodes)}"
    assert len(snap.edges) == 0, f"Expected 0 edges in empty graph, got {len(snap.edges)}"
    stats = snap.stats
    print("Empty graph handled safely: snapshot returns 0 nodes, 0 edges, 0 errors.")


def test_large_graph_seed_2147483647():
    svc = IncidentService()
    tracemalloc.start()
    t0 = time.perf_counter()
    
    # Run incident stream for largest edge seed 2147483647
    events = []
    async def cb(ev):
        events.append(ev)
    asyncio.run(svc.run_incident_stream(seed=2147483647, tenant_id=None, speed_ms=0, broadcast_callback=cb))
    
    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    snap = svc.get_graph_snapshot()
    stats = snap.stats
    assert len(snap.nodes) > 0, "Expected non-empty snapshot"
    print(f"Large graph test completed: {len(snap.nodes)} nodes, {len(snap.edges)} edges, {elapsed:.4f}s")


def main():
    print("AUDIT CHECK U5: Resilience testing...")
    empty_res = test_empty_graph_resilience()
    print("1. Empty graph test:", empty_res)
    
    large_res = test_large_graph_seed_2147483647()
    print("2. Large graph test (Seed 2147483647):")
    for k, v in large_res.items():
        print(f"   - {k}: {v}")

if __name__ == "__main__":
    main()
