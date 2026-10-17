"""Verification Test for Item 1: 100% Explanation Coverage across 100 Seeds.

Runs 100 distinct incident seeds on live FalkorDB, calls explain on every action,
verifies that MATCH (a:Action) WHERE a.causal_path IS NULL RETURN a.action_type, count(*)
returns 0 rows, and reports counts per action kind with and without causal_path.
"""

from collections import defaultdict
import time
import pytest
from engine.falkordb_client import FalkorDBGraphClient
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


def test_100_percent_explanation_coverage_100_seeds():
    num_seeds = 100
    base_seed = 4000
    
    with_path_by_kind = defaultdict(int)
    without_path_by_kind = defaultdict(int)
    total_actions_inspected = 0
    total_null_actions = 0

    print("\n" + "=" * 90)
    print(f"ITEM 1: EXPLANATION COVERAGE OVER {num_seeds} SEEDS ON LIVE FALKORDB")
    print("=" * 90)

    last_client = None

    t0_all = time.perf_counter()
    for i in range(num_seeds):
        seed = base_seed + i * 17
        tenant = f"t-exp-cov-{seed}"
        client = generate_seeded_incident(seed=seed, clean=True, tenant_id=tenant)
        last_client = client

        loop = EventLoop(tenant_id=tenant)
        loop.register_agent(SentinelAgent(tenant, client))
        loop.register_agent(TracerAgent(tenant, client))
        loop.register_agent(AdjudicatorAgent(tenant, client))
        loop.register_agent(DispatcherAgent(tenant, client))
        loop.run_until_idle(max_ticks=25)

        # Inspect all Action nodes via Cypher in FalkorDB
        act_query = "MATCH (a:Action) RETURN a.id, coalesce(a.action_type, a.action_kind), a.causal_path"
        res = client.graph.query(act_query)
        rows = res.result_set or []

        for aid, akind, cpath in rows:
            kind_str = str(akind or "unknown")
            total_actions_inspected += 1

            # Test calling explain() on every action via QueryAPIProtocol
            exp_res = client.explain(aid)
            assert exp_res.data is not None, f"Explain failed on action {aid}"
            assert exp_res.data.action_id == aid

            if cpath and len(cpath) > 0 and len(exp_res.data.causal_path) > 0:
                with_path_by_kind[kind_str] += 1
            else:
                without_path_by_kind[kind_str] += 1
                total_null_actions += 1

        # Check for null causal_path directly in Cypher
        null_query = "MATCH (a:Action) WHERE a.causal_path IS NULL RETURN a.action_type, count(*)"
        null_res = client.graph.query(null_query)
        null_rows = null_res.result_set or []
        assert len(null_rows) == 0, f"Seed {seed} has actions with NULL causal_path: {null_rows}"

    total_time = time.perf_counter() - t0_all

    print(f"\nCompleted evaluation of {num_seeds} seeds in {total_time:.2f}s ({total_actions_inspected} total actions inspected).\n")
    print(f"{'Action Kind':<25} | {'With Causal Path':<18} | {'Without Causal Path':<20} | {'Coverage %'}")
    print("-" * 80)

    all_kinds = sorted(list(set(list(with_path_by_kind.keys()) + list(without_path_by_kind.keys()))))
    total_with = sum(with_path_by_kind.values())
    total_without = sum(without_path_by_kind.values())

    for k in all_kinds:
        w = with_path_by_kind[k]
        wo = without_path_by_kind[k]
        pct = (w / (w + wo) * 100.0) if (w + wo) > 0 else 0.0
        print(f"{k:<25} | {w:<18} | {wo:<20} | {pct:>8.2f}%")

    print("-" * 80)
    total_pct = (total_with / total_actions_inspected * 100.0) if total_actions_inspected > 0 else 0.0
    print(f"{'TOTAL ACTIONS':<25} | {total_with:<18} | {total_without:<20} | {total_pct:>8.2f}%")
    print("=" * 80)

    # Cypher query validation on last incident
    dup_query = "MATCH (a:Action) WHERE a.causal_path IS NULL RETURN a.action_type, count(*)"
    null_rows = last_client.graph.query(dup_query).result_set or []
    print(f"\nCypher Validation Query: {dup_query}")
    print(f"Result Rows: {null_rows}")
    print(f"Total Rows with causal_path IS NULL: {len(null_rows)}")
    assert len(null_rows) == 0
    assert total_without == 0
    assert total_pct == 100.0
    print("\n[VERIFIED] Explanation coverage is 100.0% (measured result across 100 seeds).\n")


if __name__ == "__main__":
    test_100_percent_explanation_coverage_100_seeds()
