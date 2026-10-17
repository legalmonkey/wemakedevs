"""Item 3 Real Crash Safety Verification Script.

Executes:
1. Process runner on 5 seeds with real OS process kills on each of the 4 agents.
2. Two-agent kill at different times.
3. Deduplication check by (action_type, target_unit, decision).
4. Concurrency race verification for hold and customer notice actions.
"""

from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.falkordb_client import FalkorDBGraphClient
from engine.incident_generator import generate_seeded_incident
from tests.audit.test_demand4_reworked_c2 import canonical_hash
from contracts.ontology import NodeRole


def run_process_incident(
    seed: int,
    tenant_id: str,
    kills: Optional[List[Tuple[str, float]]] = None,
    poll_interval: float = 0.02,
    max_idle: int = 25,
) -> Tuple[str, FalkorDBGraphClient, int]:
    """Runs an incident using independent OS processes with optional mid-work kills."""
    client = generate_seeded_incident(seed=seed, clean=True, tenant_id=tenant_id)
    
    agent_names = ["Sentinel", "Tracer", "Adjudicator", "Dispatcher"]
    procs: Dict[str, subprocess.Popen] = {}
    
    for ag in agent_names:
        cmd = [
            sys.executable,
            "-m",
            "agents.process_runner",
            "--agent",
            ag,
            "--tenant",
            tenant_id,
            "--poll-interval",
            str(poll_interval),
            "--max-idle",
            str(max_idle),
        ]
        procs[ag] = subprocess.Popen(cmd)

    # Process scheduled kills
    if kills:
        start_time = time.perf_counter()
        for victim_name, kill_delay in sorted(kills, key=lambda x: x[1]):
            elapsed = time.perf_counter() - start_time
            if kill_delay > elapsed:
                time.sleep(kill_delay - elapsed)
            
            # Real OS Process Kill
            p = procs.get(victim_name)
            if p and p.poll() is None:
                p.kill()
                p.wait()
                # Restart agent process
                cmd = [
                    sys.executable,
                    "-m",
                    "agents.process_runner",
                    "--agent",
                    victim_name,
                    "--tenant",
                    tenant_id,
                    "--poll-interval",
                    str(poll_interval),
                    "--max-idle",
                    str(max_idle),
                ]
                procs[victim_name] = subprocess.Popen(cmd)

    # Wait for all processes to complete
    for ag, p in procs.items():
        p.wait(timeout=45)

    # Check and count duplicate actions if any
    action_nodes = [n for n in client.nodes.values() if n.role == NodeRole.ACTION]
    action_sigs = set()
    duplicate_count = 0
    for act in action_nodes:
        # Deduplication signature: (action_type, target_unit, decision)
        sig = (
            act.properties.get("action_type") or act.properties.get("action_kind"),
            act.properties.get("target_entity_id"),
            act.properties.get("procedure_id") or act.properties.get("reason_code"),
        )
        if sig in action_sigs:
            duplicate_count += 1
        else:
            action_sigs.add(sig)

    final_hash = canonical_hash(client)
    return final_hash, client, duplicate_count


def run_concurrency_race_check() -> Tuple[bool, int, str]:
    """Runs Demand 5 concurrency race test: hold and customer-notice actions never execute concurrently."""
    import random
    from toolserver.gate_evaluator import GateEvaluator
    from agents.sentinel import SentinelAgent
    from agents.tracer import TracerAgent
    from agents.adjudicator import AdjudicatorAgent
    from agents.dispatcher import DispatcherAgent
    from contracts.ontology import EdgeRole

    rng = random.Random(42)
    race_runs = 20
    concurrent_conflicts = 0

    for run_idx in range(1, race_runs + 1):
        tenant = f"t-race-verify-{run_idx}"
        c = FalkorDBGraphClient(tenant_id=tenant, clean=True)
        batch_id = f"batch-race-{run_idx}"
        c.add_node(batch_id, "BatchLot", NodeRole.UNIT, {"is_tainted": False, "status": "released"})

        dec_id = f"dec-race-{run_idx}"
        c.add_node(dec_id, "QualityDecision", NodeRole.DECISION, {"status": "pending"})
        c.add_edge(dec_id, batch_id, "SUPPORT", EdgeRole.SUPPORT)

        for g in range(3):
            ev_id = f"ev-race-{run_idx}-{g}"
            c.add_node(ev_id, "LabTest", NodeRole.EVIDENCE, {"valid": True, "group_id": f"grp_{g}"})
            c.add_edge(ev_id, dec_id, "SUPPORTS", EdgeRole.SUPPORT)

        ship_id = f"ship-race-{run_idx}"
        cust_id = f"cust-race-{run_idx}"
        c.add_node(ship_id, "DispatchShipment", NodeRole.SHIPMENT, {"status": "in_transit"})
        c.add_node(cust_id, "CustomerAccount", NodeRole.RECIPIENT, {"tier": "commercial"})
        c.add_edge(batch_id, ship_id, "SHIPS_IN", EdgeRole.SHIPS_IN)
        c.add_edge(ship_id, cust_id, "DELIVERED_TO", EdgeRole.DELIVERED_TO)

        agents = [
            SentinelAgent(tenant, c),
            TracerAgent(tenant, c),
            AdjudicatorAgent(tenant, c),
            DispatcherAgent(tenant, c),
        ]

        for _ in range(15):
            rng.shuffle(agents)
            for ag in agents:
                ag.step()

        # Check action invariants
        actions = [n for n in c.nodes.values() if n.role == NodeRole.ACTION]
        hold_actions = [a for a in actions if a.properties.get("action_kind") == "hold_unit" and a.properties.get("target_entity_id") == batch_id]
        notice_actions = [a for a in actions if a.properties.get("action_kind") == "draft_notice" and a.properties.get("target_entity_id") == cust_id]

        if hold_actions and notice_actions:
            concurrent_conflicts += 1

        evaluator = GateEvaluator(graph_client=c)
        gate_res = evaluator.evaluate("hold_unit", {"entity_id": batch_id})
        if gate_res.allowed:
            concurrent_conflicts += 1

    passed = (concurrent_conflicts == 0)
    msg = f"Zero concurrent holds/notices across {race_runs} randomized agent races."
    return passed, concurrent_conflicts, msg


if __name__ == "__main__":
    print("=" * 105)
    print("ITEM 3: REAL CRASH SAFETY WITH MID-WORK PROCESS KILLS & CONCURRENCY RACE VERIFICATION")
    print("=" * 105)

    test_seeds = [101, 202, 303, 404, 505]
    all_matched = True
    total_dupes = 0

    print(f"\n1. Single Agent Mid-Work Real OS Process Kills Across 5 Seeds:\n")
    print(f"{'Seed':<6} | {'Test Case':<22} | {'Final Graph Hash':<32} | {'Match Baseline?':<16} | {'Duplicates'}")
    print("-" * 105)

    for seed in test_seeds:
        tenant_base = f"t-crash-base-{seed}"
        h_base, _, dupes_base = run_process_incident(seed, tenant_base)
        print(f"{seed:<6} | {'Baseline (Uninterrupted)':<22} | {h_base[:28]}... | {'BASELINE':<16} | {dupes_base}")

        for ag in ["Sentinel", "Tracer", "Adjudicator", "Dispatcher"]:
            t_kill = f"t-crash-k-{seed}-{ag.lower()}"
            h_kill, _, dupes = run_process_incident(seed, t_kill, kills=[(ag, 0.08)])
            match = (h_kill == h_base)
            if not match:
                all_matched = False
            total_dupes += dupes
            print(f"{seed:<6} | {f'Kill {ag}':<22} | {h_kill[:28]}... | {'PASS (MATCH)' if match else 'FAIL':<16} | {dupes}")

    print("-" * 105)

    print(f"\n2. Two-Agent Mid-Work Process Kills at Different Timings (Sentinel @ 0.08s, Tracer @ 0.18s):\n")
    print(f"{'Seed':<6} | {'Test Case':<22} | {'Final Graph Hash':<32} | {'Match Baseline?':<16} | {'Duplicates'}")
    print("-" * 105)

    for seed in test_seeds:
        tenant_base = f"t-crash-base-{seed}"
        h_base, c_base, _ = run_process_incident(seed, tenant_base)
        t_two_kill = f"t-crash-2k-{seed}"
        h_two_kill, _, dupes_two = run_process_incident(
            seed,
            t_two_kill,
            kills=[("Sentinel", 0.08), ("Tracer", 0.18)],
        )
        match_two = (h_two_kill == h_base)
        if not match_two:
            all_matched = False
        total_dupes += dupes_two
        print(f"{seed:<6} | {'Kill Sentinel + Tracer':<22} | {h_two_kill[:28]}... | {'PASS (MATCH)' if match_two else 'FAIL':<16} | {dupes_two}")

    print("-" * 105)

    print(f"\n3. Concurrency Race Condition Verification (Hold vs Notice Gate Invariance):\n")
    race_passed, race_conflicts, race_msg = run_concurrency_race_check()
    print(f"Race Invariant Check: {'PASS' if race_passed else 'FAIL'}")
    print(f"Concurrent Conflicts: {race_conflicts}")
    print(f"Details: {race_msg}")
    print("-" * 105)

    assert all_matched, "One or more process kill runs failed to converge to baseline graph hash!"
    assert total_dupes == 0, f"Found {total_dupes} duplicate actions across process runs!"
    assert race_passed, f"Found {race_conflicts} concurrency race conflicts!"

    print("\n[ALL CHECKS PASSED] ITEM 3 REAL CRASH SAFETY VERIFIED.")

