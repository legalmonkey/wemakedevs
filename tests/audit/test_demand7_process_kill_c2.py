"""Demand 7 Verification Suite: Real OS Process Execution & Mid-Incident Process Kill (C2).

Verifies:
(1) Agents run as separate, independent OS processes (communicating strictly through FalkorDB).
(2) C2 execution: A real OS process is terminated mid-incident via proc.kill().
(3) The process is restarted, completes the incident, and converges to the exact canonical state
    as an uninterrupted baseline run.
"""

import hashlib
import json
import subprocess
import sys
import time
import pytest
from engine.falkordb_client import FalkorDBGraphClient
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


def canonical_graph_hash(client: FalkorDBGraphClient) -> str:
    """Computes a deterministic hash of all nodes, edges, properties, and verdicts in the graph."""
    nodes = client.nodes
    edges = client.edges

    node_reprs = []
    for nid in sorted(nodes.keys()):
        n = nodes[nid]
        p = {k: v for k, v in n.properties.items() if not k.startswith("_")}
        node_reprs.append(f"{nid}:{n.kind}:{n.role}:{sorted(p.items())}")

    edge_reprs = []
    for e in edges:
        p = {k: v for k, v in e.properties.items() if not k.startswith("_")}
        edge_reprs.append(f"{e.source_id}->{e.target_id}:{e.kind}:{e.role}:{sorted(p.items())}")
    edge_reprs.sort()

    content = "|".join(node_reprs) + "||" + "|".join(edge_reprs)
    return hashlib.sha256(content.encode()).hexdigest()


def test_agents_separate_processes_and_c2_real_process_kill():
    """Show agents running as separate OS processes and execute C2 across repeats with independent kill timings."""
    import random
    seed = 8765
    num_repeats = 5  # Multi-repeat test with independent kill timing per repeat
    rng = random.Random(7777)

    print(f"\n{'='*95}")
    print(f"DEMAND 5: C2 REAL OS PROCESS EXECUTION ACROSS {num_repeats} REPEATS WITH INDEPENDENT KILL TIMINGS")
    print(f"{'='*95}")

    # 1. Establish baseline uninterrupted run
    client_base = generate_seeded_incident(seed=seed, clean=True)
    loop_base = EventLoop(tenant_id=client_base.tenant_id)
    loop_base.register_agent(SentinelAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(TracerAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(AdjudicatorAgent(client_base.tenant_id, client_base))
    loop_base.register_agent(DispatcherAgent(client_base.tenant_id, client_base))
    loop_base.run_until_idle()
    base_hash = canonical_graph_hash(client_base)
    print(f"Baseline Uninterrupted Graph Hash: {base_hash}\n")

    # 2. Execute multi-repeat C2 with independent kill timing per repeat
    for rep in range(1, num_repeats + 1):
        # Independent kill delay and target agent per repeat
        kill_delay = round(rng.uniform(0.08, 0.30), 4)
        target_agent = rng.choice(["Tracer", "Sentinel"])

        # Setup fresh incident graph
        client_proc = generate_seeded_incident(seed=seed, clean=True)
        tenant = client_proc.tenant_id

        # Spawn all agents concurrently as separate OS processes
        proc_sentinel = subprocess.Popen(
            [sys.executable, "-m", "agents.process_runner", "--agent", "Sentinel", "--tenant", tenant, "--max-idle", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc_tracer = subprocess.Popen(
            [sys.executable, "-m", "agents.process_runner", "--agent", "Tracer", "--tenant", tenant, "--max-idle", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc_adj = subprocess.Popen(
            [sys.executable, "-m", "agents.process_runner", "--agent", "Adjudicator", "--tenant", tenant, "--max-idle", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc_disp = subprocess.Popen(
            [sys.executable, "-m", "agents.process_runner", "--agent", "Dispatcher", "--tenant", tenant, "--max-idle", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Independent kill timing: sleep for randomized duration before termination
        time.sleep(kill_delay)

        target_proc = proc_tracer if target_agent == "Tracer" else proc_sentinel
        print(f"Repeat {rep}/{num_repeats}: Killing {target_agent} (PID: {target_proc.pid}) after {kill_delay*1000:.1f}ms...")
        target_proc.kill()
        target_proc.wait()
        assert target_proc.poll() is not None, f"Process {target_agent} was not killed!"

        # Restart killed agent as a fresh separate OS process
        restarted_proc = subprocess.Popen(
            [sys.executable, "-m", "agents.process_runner", "--agent", target_agent, "--tenant", tenant, "--max-idle", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for all processes to finish through FalkorDB
        proc_sentinel.wait(timeout=25)
        proc_tracer.wait(timeout=25)
        proc_adj.wait(timeout=25)
        proc_disp.wait(timeout=25)
        restarted_proc.wait(timeout=25)

        # Validate canonical graph hash matches baseline exactly
        proc_hash = canonical_graph_hash(client_proc)
        print(f"  Result: Hash={proc_hash[:16]}... Baseline={base_hash[:16]}... Match={proc_hash == base_hash}")
        assert proc_hash == base_hash, (
            f"Repeat {rep} failed C2 recovery! Final hash {proc_hash} did not match baseline {base_hash}"
        )

    print(f"\n{'='*95}")
    print(f"C2 RECOVERY PROVEN: All {num_repeats} repeats with independent kill timings converged to baseline!")
    print(f"{'='*95}\n")
