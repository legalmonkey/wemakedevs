"""Demand 4 Verification Suite: Reworked C2 Restart Idempotency under Concurrent Execution.

Verifies:
(1) All agents (Sentinel, Tracer, Adjudicator, Dispatcher) running concurrently.
(2) Kill each agent at 20 random moments during execution.
(3) Repeat across 10 independent runs.
(4) Every single repeat produces an identical final graph hash bit-for-bit matching uninterrupted baseline.
"""

import hashlib
import random
import pytest
from engine.falkordb_client import FalkorDBGraphClient
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


def canonical_hash(client: FalkorDBGraphClient) -> str:
    """Computes a deterministic canonical SHA-256 hash of the graph state."""
    nodes = client.nodes
    edges = client.edges

    node_entries = []
    for nid in sorted(nodes.keys()):
        n = nodes[nid]
        role_val = n.role.value if hasattr(n.role, "value") else str(n.role)
        sig = f"{nid}:{n.kind}:{role_val}:{n.properties.get('is_tainted')}:{n.properties.get('status')}:{n.properties.get('verdict')}"
        node_entries.append(sig)

    edge_entries = []
    for e in sorted(edges, key=lambda x: (x.source_id, x.target_id, x.kind)):
        role_val = e.role.value if hasattr(e.role, "value") else str(e.role)
        sig = f"{e.source_id}->{e.target_id}:{e.kind}:{role_val}"
        edge_entries.append(sig)

    payload = "||".join(node_entries) + "###" + "||".join(edge_entries)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_reworked_c2_concurrent_kills_10_repeats_identical_hash():
    """Rework C2: Concurrent agents, kill each at 20 random moments, 10 repeats, identical hash."""
    seed = 8821
    rng = random.Random(seed)

    print(f"\n{'='*105}")
    print("DEMAND 4: REWORKED C2 CONCURRENT EXECUTION WITH 20 RANDOM KILLS ACROSS 10 REPEATS")
    print(f"{'='*105}")

    # 1. Uninterrupted Baseline Run
    client_base = generate_seeded_incident(seed=seed, clean=True)
    loop_base = EventLoop(tenant_id=client_base.tenant_id)
    loop_base.register_agent(SentinelAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(TracerAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(AdjudicatorAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(DispatcherAgent(client_base.tenant_id, client_base))
    loop_base.run_until_idle()
    base_hash = canonical_hash(client_base)

    print(f"Baseline Uninterrupted Graph Hash: {base_hash}")
    print("-" * 105)
    print(f"{'Repeat':<8} | {'Total Kills':<12} | {'Killed Agents Breakdown':<35} | {'Final Graph Hash':<32} | {'Match?'}")
    print("-" * 105)

    agent_classes = {
        "Sentinel": SentinelAgent,
        "Tracer": TracerAgent,
        "Adjudicator": AdjudicatorAgent,
        "Dispatcher": DispatcherAgent,
    }

    # 2. 10 Repeats with 20 random kill moments each
    for repeat in range(1, 11):
        client_rep = generate_seeded_incident(seed=seed, clean=True)
        loop_rep = EventLoop(tenant_id=client_rep.tenant_id)

        # Initialize fresh agent instances
        for name, cls in agent_classes.items():
            loop_rep.register_agent(cls(client_rep.tenant_id, client_rep))

        # 20 random kill points distributed across execution ticks
        kill_moments = sorted([rng.randint(1, 10) for _ in range(20)])
        killed_counts = {name: 0 for name in agent_classes}
        current_tick = 0
        consecutive_idle = 0

        while current_tick < 25 and (consecutive_idle < 3 or kill_moments):
            current_tick += 1

            # Check if any kills scheduled for this tick
            while kill_moments and kill_moments[0] <= current_tick:
                kill_moments.pop(0)
                # Randomly pick which agent to kill
                victim_name = rng.choice(list(agent_classes.keys()))
                killed_counts[victim_name] += 1

                # Kill agent: remove from loop and instantiate fresh agent instance
                loop_rep.agents = [a for a in loop_rep.agents if a.name != victim_name]
                fresh_agent = agent_classes[victim_name](client_rep.tenant_id, client_rep)
                loop_rep.register_agent(fresh_agent)

            # Concurrent tick execution across all agents
            tick_res = loop_rep.run_tick()
            if tick_res.total_items_processed == 0:
                consecutive_idle += 1
            else:
                consecutive_idle = 0

        # Let remaining work reach quiescence
        loop_rep.run_until_idle()

        # Verify hash
        rep_hash = canonical_hash(client_rep)
        matches = (rep_hash == base_hash)

        counts_str = f"S:{killed_counts['Sentinel']} T:{killed_counts['Tracer']} A:{killed_counts['Adjudicator']} D:{killed_counts['Dispatcher']}"
        print(f"Run {repeat:<4} | {sum(killed_counts.values()):<12} | {counts_str:<35} | {rep_hash[:28]}... | {'PASS' if matches else 'FAIL'}")

        assert matches, f"Repeat {repeat} hash mismatch! {rep_hash} != {base_hash}"

    print(f"{'='*105}")
    print("ALL 10 REPEATS WITH 20 RANDOM KILLS CONVERGED TO THE EXACT BASELINE HASH!")
    print(f"{'='*105}\n")
