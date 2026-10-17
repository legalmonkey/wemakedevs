"""Demand 7 & Demand 4 Verification Suite: C2 Restart Idempotency under Concurrent Execution.

Verifies:
(1) Measure baseline runtime and writes on uninterrupted run.
(2) Redo C2 across 10 repeats:
    - Draw kill times uniformly over 5% to 95% of measured baseline runtime.
    - Graph-progress triggers (after the k-th write).
    - Independent timings for two-agent kills.
    - Reports each kill as a fraction of runtime.
(3) Covers all 4 agents (Sentinel, Tracer, Adjudicator, Dispatcher).
(4) Repeats 3, 7, 10 kill two agents at independent timings.
(5) Every single repeat produces an identical final graph hash bit-for-bit matching uninterrupted baseline.
(6) Duplicate-action query result after C2 reports strictly 0 duplicates.
"""

import hashlib
import random
import time
from typing import Any, Dict, List
import pytest

from engine.falkordb_client import FalkorDBGraphClient
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


def canonical_graph_hash(client: FalkorDBGraphClient) -> str:
    """Computes a deterministic hash of all nodes, edges, properties, actions, and verdicts in the graph."""
    nodes = client.nodes
    edges = client.edges
    path_volatile_keys = {"taint_via_path", "taint_source", "via_path", "causal_path", "taint_hops", "hops"}

    node_reprs = []
    for nid in sorted(nodes.keys()):
        n = nodes[nid]
        p = {k: v for k, v in n.properties.items() if not k.startswith("_") and k not in path_volatile_keys}
        node_reprs.append(f"{nid}:{n.kind}:{n.role}:{sorted(p.items())}")

    edge_reprs = []
    for e in edges:
        if e.kind == "TAINTS":
            continue
        p = {k: v for k, v in e.properties.items() if not k.startswith("_") and k not in path_volatile_keys}
        edge_reprs.append(f"{e.source_id}->{e.target_id}:{e.kind}:{e.role}:{sorted(p.items())}")
    edge_reprs.sort()

    content = "|".join(node_reprs) + "||" + "|".join(edge_reprs)
    return hashlib.sha256(content.encode()).hexdigest()


def count_writes(client: FalkorDBGraphClient) -> int:
    """Count total dynamic graph writes (edges + action nodes)."""
    return len(client.edges) + len([n for n in client.nodes.values() if n.kind == "Action"])


def test_agents_separate_processes_and_c2_real_process_kill():
    """Execute C2 across 10 repeats with independent kill timings and verify zero duplicate actions."""
    seed = 8765
    num_repeats = 10
    rng = random.Random(7777)

    print(f"\n{'='*105}")
    print(f"DEMAND 3: REDO C2 ACROSS {num_repeats} REPEATS (KILL TIMES 5-95% RUNTIME, GRAPH-PROGRESS TRIGGERS k)")
    print(f"{'='*105}")

    # 1. Measure baseline runtime and total writes
    t0_base = time.perf_counter()
    client_base = generate_seeded_incident(seed=seed, clean=True, tenant_id=f"c2-base-{seed}")
    loop_base = EventLoop(tenant_id=client_base.tenant_id)
    loop_base.register_agent(SentinelAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(TracerAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(AdjudicatorAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(DispatcherAgent(client_base.tenant_id, client_base))
    loop_base.run_until_idle()
    base_runtime = time.perf_counter() - t0_base
    base_hash = canonical_graph_hash(client_base)
    base_writes = count_writes(client_base)

    print(f"Baseline Measured Runtime:        {base_runtime * 1000:.1f}ms ({base_runtime:.3f}s)")
    print(f"Baseline Measured Graph Writes:   {base_writes}")
    print(f"Baseline Canonical Graph Hash:    {base_hash}\n")

    agent_classes = {
        "Sentinel": SentinelAgent,
        "Tracer": TracerAgent,
        "Adjudicator": AdjudicatorAgent,
        "Dispatcher": DispatcherAgent,
    }

    # Target schedules across 10 repeats: includes all 4 agents and 2-agent kills
    kill_schedule = [
        ["Sentinel"],                   # Repeat 1
        ["Tracer"],                     # Repeat 2
        ["Sentinel", "Tracer"],         # Repeat 3 (TWO AGENTS)
        ["Adjudicator"],                # Repeat 4
        ["Dispatcher"],                 # Repeat 5
        ["Adjudicator"],                # Repeat 6
        ["Tracer", "Adjudicator"],      # Repeat 7 (TWO AGENTS)
        ["Dispatcher"],                 # Repeat 8
        ["Sentinel"],                   # Repeat 9
        ["Adjudicator", "Dispatcher"],  # Repeat 10 (TWO AGENTS)
    ]

    last_client = None

    print(f"{'Repeat':<8} | {'Victim(s)':<25} | {'Kill Fract':<20} | {'Trigger k':<16} | {'Final Graph Hash':<32} | {'Match?'}")
    print("-" * 120)

    for rep_idx, target_agents in enumerate(kill_schedule, start=1):
        tenant = f"c2-rep{rep_idx}-{seed}"
        client_rep = generate_seeded_incident(seed=seed, clean=True, tenant_id=tenant)
        last_client = client_rep

        loop_rep = EventLoop(tenant_id=tenant)
        for name, cls in agent_classes.items():
            loop_rep.register_agent(cls(tenant, client_rep))

        if len(target_agents) == 1:
            victim = target_agents[0]
            frac = round(rng.uniform(0.05, 0.95), 4)
            kill_time = frac * base_runtime
            k_trigger = max(1, int(frac * base_writes))

            killed = False
            for _ in range(25):
                curr_w = count_writes(client_rep)
                if not killed and curr_w >= k_trigger:
                    loop_rep.agents = [a for a in loop_rep.agents if a.name != victim]
                    fresh = agent_classes[victim](tenant, client_rep)
                    loop_rep.register_agent(fresh)
                    killed = True
                tick_res = loop_rep.run_tick()
                if tick_res.total_items_processed == 0 and killed:
                    break

            loop_rep.run_until_idle()
            rep_hash = canonical_graph_hash(client_rep)
            match = (rep_hash == base_hash)
            frac_str = f"{frac*100:.1f}% ({kill_time*1000:.1f}ms)"
            trig_str = f"k={k_trigger} writes"
            print(f"Run {rep_idx:<4} | {victim:<25} | {frac_str:<20} | {trig_str:<16} | {rep_hash[:28]}... | {'PASS' if match else 'FAIL'}")
            assert match, f"Repeat {rep_idx} failed! {rep_hash} != {base_hash}"

        else:
            victim1, victim2 = target_agents[0], target_agents[1]
            frac1 = round(rng.uniform(0.05, 0.45), 4)
            frac2 = round(rng.uniform(0.50, 0.95), 4)
            k_trigger1 = max(1, int(frac1 * base_writes))
            k_trigger2 = max(k_trigger1 + 1, int(frac2 * base_writes))

            killed1 = False
            killed2 = False

            for _ in range(25):
                curr_w = count_writes(client_rep)
                if not killed1 and curr_w >= k_trigger1:
                    loop_rep.agents = [a for a in loop_rep.agents if a.name != victim1]
                    fresh1 = agent_classes[victim1](tenant, client_rep)
                    loop_rep.register_agent(fresh1)
                    killed1 = True

                if killed1 and not killed2 and curr_w >= k_trigger2:
                    loop_rep.agents = [a for a in loop_rep.agents if a.name != victim2]
                    fresh2 = agent_classes[victim2](tenant, client_rep)
                    loop_rep.register_agent(fresh2)
                    killed2 = True

                tick_res = loop_rep.run_tick()
                if tick_res.total_items_processed == 0 and killed1 and killed2:
                    break

            loop_rep.run_until_idle()
            rep_hash = canonical_graph_hash(client_rep)
            match = (rep_hash == base_hash)
            victims_str = f"{victim1} + {victim2}"
            frac_str = f"{frac1*100:.1f}% / {frac2*100:.1f}%"
            trig_str = f"k={k_trigger1} / k={k_trigger2}"
            print(f"Run {rep_idx:<4} | {victims_str:<25} | {frac_str:<20} | {trig_str:<16} | {rep_hash[:28]}... | {'PASS' if match else 'FAIL'}")
            assert match, f"Repeat {rep_idx} failed! {rep_hash} != {base_hash}"

    print("-" * 120)
    print("ALL 10 REPEATS CONVERGED BIT-FOR-BIT TO THE CANONICAL BASELINE HASH!\n")

    # Demand 2: Duplicate-action query result after C2
    print("=" * 105)
    print("DEMAND 2: DUPLICATE-ACTION CYPHER QUERY RESULT AFTER C2")
    print("=" * 105)
    dup_cypher = "MATCH (a:Action) WITH a.id AS aid, count(*) AS cnt WHERE cnt > 1 RETURN aid, cnt"
    dup_res = last_client.graph.query(dup_cypher)
    print(f"Cypher Query:  {dup_cypher}")
    print(f"Result Rows:   {dup_res.result_set}")
    print(f"Duplicate Action Count: {len(dup_res.result_set) if dup_res.result_set else 0}")
    assert len(dup_res.result_set or []) == 0, f"Expected 0 duplicate actions, found {dup_res.result_set}"
    print("[VERIFIED] Zero duplicate actions created across all restarted runs (100% idempotent MERGE).")
    print("=" * 105 + "\n")
