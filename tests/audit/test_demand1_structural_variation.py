"""Demand 1 Verification Suite: Non-Cyclic Topologies, Dynamic Counts, and Structural Comparison.

Verifies:
(1) Topologies are strictly acyclic DAGs (cycle count == 0).
(2) Graph structure diverges across seeds based on fault injection and process branching,
    tested by comparing graph topological structure (degree distribution / role connectivity)
    without comparing node IDs or labels.
(3) Counts of tainted, reaffirmed, and unverifiable units all vary across seeds.
"""

from collections import defaultdict, deque
import pytest
from contracts.ontology import NodeRole, EdgeRole
from engine.falkordb_client import FalkorDBGraphClient
from engine.generator import FoodGraphGenerator
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from engine.incident_generator import generate_seeded_incident


def _detect_cycles(nodes: dict, edges: list) -> list:
    """Detects cycles in a directed graph using Kahn's algorithm / in-degree topological sort."""
    adj = defaultdict(list)
    in_degree = defaultdict(int)
    all_node_ids = set(nodes.keys())

    for n in all_node_ids:
        in_degree[n] = 0

    for e in edges:
        src = e["source_id"] if isinstance(e, dict) else e.source_id
        tgt = e["target_id"] if isinstance(e, dict) else e.target_id
        adj[src].append(tgt)
        in_degree[tgt] += 1

    queue = deque([n for n in all_node_ids if in_degree[n] == 0])
    visited_count = 0

    while queue:
        curr = queue.popleft()
        visited_count += 1
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If visited_count != len(all_node_ids), there is at least one cycle
    return len(all_node_ids) - visited_count


def _get_structural_fingerprint(nodes: dict, edges: list) -> tuple:
    """Extracts topological structural invariant independent of node IDs or labels.
    
    Computes sorted multiset of (node_role, in_degree, out_degree, incoming_edge_roles, outgoing_edge_roles).
    """
    in_deg = defaultdict(int)
    out_deg = defaultdict(int)
    in_roles = defaultdict(list)
    out_roles = defaultdict(list)

    for e in edges:
        src = e["source_id"] if isinstance(e, dict) else e.source_id
        tgt = e["target_id"] if isinstance(e, dict) else e.target_id
        role = e["role"] if isinstance(e, dict) else e.role
        role_val = role.value if hasattr(role, "value") else str(role)

        out_deg[src] += 1
        in_deg[tgt] += 1
        out_roles[src].append(role_val)
        in_roles[tgt].append(role_val)

    signatures = []
    for nid, node in nodes.items():
        role = node["role"] if isinstance(node, dict) else node.role
        role_val = role.value if hasattr(role, "value") else str(role)
        sig = (
            role_val,
            in_deg[nid],
            out_deg[nid],
            tuple(sorted(in_roles[nid])),
            tuple(sorted(out_roles[nid])),
        )
        signatures.append(sig)

    return tuple(sorted(signatures))


def test_generator_topologies_are_strictly_acyclic_dags():
    """Verify that generated graphs have zero cycles across multiple seeds."""
    for seed in [101, 202, 303, 404, 505]:
        gen = FoodGraphGenerator(seed=seed, num_units=30, num_decisions=15)
        data = gen.generate()
        cycle_nodes = _detect_cycles(data["nodes"], data["edges"])
        assert cycle_nodes == 0, f"Seed {seed} generated graph with {cycle_nodes} nodes trapped in cycles!"
    print("DEMAND 1.1: Verified that all generated supply chain topologies are strict acyclic DAGs (0 cycles).")


def test_generator_structural_comparison_without_ids():
    """Verify structural divergence between two seeds comparing pure topological invariants, NOT IDs."""
    gen_a = FoodGraphGenerator(seed=1337, num_units=30, num_decisions=15)
    gen_b = FoodGraphGenerator(seed=7331, num_units=30, num_decisions=15)

    data_a = gen_a.generate()
    data_b = gen_b.generate()

    struct_a = _get_structural_fingerprint(data_a["nodes"], data_a["edges"])
    struct_b = _get_structural_fingerprint(data_b["nodes"], data_b["edges"])

    assert struct_a != struct_b, "Topological signatures must differ between seeds (isomorphic graph failure)!"
    print("DEMAND 1.2: Confirmed topological structural divergence between Seed 1337 and Seed 7331 without using node IDs.")


def test_generator_dynamic_counts_of_tainted_reaffirmed_unverifiable():
    """Verify that counts of tainted, reaffirmed, and unverifiable units all vary across seeds."""
    tainted_counts = []
    reaffirmed_counts = []
    unverifiable_counts = []

    print("\nDEMAND 1.3: Evaluating outcome variance across 10 distinct seeds on FalkorDB:")
    print(f"{'Seed':<8} | {'Tainted':<8} | {'Reaffirmed':<12} | {'Unverifiable':<14} | {'Total Decisions'}")
    print("-" * 65)

    seeds = [1000 + i * 43 for i in range(10)]
    for s in seeds:
        client = generate_seeded_incident(s, clean=True)
        loop = EventLoop(tenant_id=client.tenant_id)
        loop.register_agent(SentinelAgent(client.tenant_id, client))
        loop.register_agent(TracerAgent(client.tenant_id, client))
        loop.register_agent(AdjudicatorAgent(client.tenant_id, client))
        loop.register_agent(DispatcherAgent(client.tenant_id, client))
        loop.run_until_idle()

        decisions = [n for n in client.nodes.values() if n.role == NodeRole.DECISION]
        t_count = sum(1 for d in decisions if d.properties.get("verdict") == "tainted")
        r_count = sum(1 for d in decisions if d.properties.get("verdict") == "reaffirmed")
        u_count = sum(1 for d in decisions if d.properties.get("verdict") == "unverifiable")

        tainted_counts.append(t_count)
        reaffirmed_counts.append(r_count)
        unverifiable_counts.append(u_count)

        print(f"{s:<8} | {t_count:<8} | {r_count:<12} | {u_count:<14} | {len(decisions)}")

    print("-" * 65)
    print(f"Tainted Count Range:      [{min(tainted_counts)}, {max(tainted_counts)}] (unique values: {len(set(tainted_counts))})")
    print(f"Reaffirmed Count Range:   [{min(reaffirmed_counts)}, {max(reaffirmed_counts)}] (unique values: {len(set(reaffirmed_counts))})")
    print(f"Unverifiable Count Range: [{min(unverifiable_counts)}, {max(unverifiable_counts)}] (unique values: {len(set(unverifiable_counts))})")

    assert len(set(tainted_counts)) > 1, f"Tainted count must vary across seeds! Got {tainted_counts}"
    assert len(set(reaffirmed_counts)) > 1, f"Reaffirmed count must vary across seeds! Got {reaffirmed_counts}"
    assert len(set(unverifiable_counts)) > 1, f"Unverifiable count must vary across seeds! Got {unverifiable_counts}"
    assert max(unverifiable_counts) > 0, "Unverifiable decisions must appear due to orphan-result fault injection!"
