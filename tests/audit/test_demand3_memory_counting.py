"""Demand 3 Verification Suite: Memory Counting & Procedural Ranking.

Verifies:
1. Episode IDs include the incident ID (e.g., ep_{tenant}_{incident_id}_{action_id}).
2. Running three incidents on different seeds under one stable tenant shows
   the episode count rises by exactly one per approval or rejection.
3. Ranking must compare at least two procedures for the same situation, or print that
   comparison is not possible.
4. Never count one episode twice (idempotent replay and Cypher deduplication).
"""

import asyncio
import pytest
from contracts.ontology import NodeRole
from api.incident_service import IncidentService
from agents.memory import ProceduralMemory
from engine.falkordb_client import FalkorDBGraphClient


def test_demand3_memory_counting_and_ranking():
    stable_tenant = "tenant-memory-counting-stable"
    print(f"\n{'='*100}")
    print("DEMAND 3: MEMORY COUNTING & PROCEDURAL RANKING VERIFICATION")
    print(f"Stable Tenant: {stable_tenant}")
    print(f"{'='*100}")

    # 0. Clean persistent memory graph for this stable tenant
    FalkorDBGraphClient(tenant_id=f"memory_{stable_tenant}", clean=True)
    mem = ProceduralMemory(tenant_id=stable_tenant)
    initial_ranking = mem.rank_procedures()
    assert initial_ranking.total_episodes_found == 0, "Initial episode count must be 0"
    print("\n[STEP 0] Memory cleanly initialized. Initial episode count: 0")

    svc = IncidentService(stable_tenant_id=stable_tenant)

    # =========================================================================
    # INCIDENT 1: Seed 1101 (Recorded Human Approval)
    # =========================================================================
    seed_1 = 1101
    print(f"\n--- [INCIDENT 1] Running Seed {seed_1} on {stable_tenant} ---")
    svc.load_seed(seed_1)
    assert svc.current_incident_id == f"inc_{seed_1}", f"Expected inc_{seed_1}, got {svc.current_incident_id}"

    asyncio.run(svc.run_incident_stream(seed=seed_1, speed_ms=0))

    actions_1 = [n for n in svc.graph_client.nodes.values() if n.role == NodeRole.ACTION]
    pending_1 = [a for a in actions_1 if a.properties.get("requires_approval")]
    assert len(pending_1) > 0, "Seed 1101 must produce at least one action requiring approval"
    act_1 = pending_1[0].node_id

    appr_1 = svc.approve_action(act_1, operator_notes="Scope confirmed; notice approved.")
    ep_id_1 = appr_1["persistent_episode_recorded"]
    print(f"Action:     {act_1}")
    print(f"Episode ID: {ep_id_1}")
    print(f"Outcome:    {appr_1['outcome']}")
    print(f"Procedure:  {appr_1['procedure_id']}")

    assert f"inc_{seed_1}" in ep_id_1, f"Episode ID must contain incident ID 'inc_{seed_1}', got {ep_id_1}"
    assert appr_1["outcome"] == "approved"

    rank_1 = mem.rank_procedures(situation="containment")
    print(f"Episode Count after Incident 1: {rank_1.total_episodes_found} (Expected: 1)")
    assert rank_1.total_episodes_found == 1, f"Episode count must rise by exactly 1 to 1, got {rank_1.total_episodes_found}"
    assert "Comparison is not possible" in rank_1.statement, "With only 1 procedure, comparison must be stated as not possible"

    # =========================================================================
    # INCIDENT 2: Seed 2202 (Recorded Human Rejection)
    # =========================================================================
    seed_2 = 2202
    print(f"\n--- [INCIDENT 2] Running Seed {seed_2} on {stable_tenant} ---")
    svc.load_seed(seed_2)
    assert svc.current_incident_id == f"inc_{seed_2}", f"Expected inc_{seed_2}, got {svc.current_incident_id}"

    asyncio.run(svc.run_incident_stream(seed=seed_2, speed_ms=0))

    actions_2 = [n for n in svc.graph_client.nodes.values() if n.role == NodeRole.ACTION]
    pending_2 = [a for a in actions_2 if a.properties.get("requires_approval")]
    assert len(pending_2) > 0, "Seed 2202 must produce at least one action requiring approval"
    act_2 = pending_2[0].node_id

    rej_2 = svc.reject_action(act_2, operator_notes="Notice rejected pending QA audit.")
    ep_id_2 = rej_2["persistent_episode_recorded"]
    print(f"Action:     {act_2}")
    print(f"Episode ID: {ep_id_2}")
    print(f"Outcome:    {rej_2['outcome']}")
    print(f"Procedure:  {rej_2['procedure_id']}")

    assert f"inc_{seed_2}" in ep_id_2, f"Episode ID must contain incident ID 'inc_{seed_2}', got {ep_id_2}"
    assert rej_2["outcome"] == "rejected"

    rank_2 = mem.rank_procedures(situation="containment")
    print(f"Episode Count after Incident 2: {rank_2.total_episodes_found} (Expected: 2)")
    assert rank_2.total_episodes_found == 2, f"Episode count must rise by exactly 1 to 2, got {rank_2.total_episodes_found}"

    # =========================================================================
    # INCIDENT 3: Seed 3303 (Approval with distinct procedure to compare procedures)
    # =========================================================================
    seed_3 = 3303
    print(f"\n--- [INCIDENT 3] Running Seed {seed_3} on {stable_tenant} ---")
    svc.load_seed(seed_3)
    assert svc.current_incident_id == f"inc_{seed_3}", f"Expected inc_{seed_3}, got {svc.current_incident_id}"

    asyncio.run(svc.run_incident_stream(seed=seed_3, speed_ms=0))

    # Add an action for a distinct procedure (e.g. proc-quarantine-hold or proc-escalate-human)
    act_3 = "act-escalate-human-seed3303"
    svc.graph_client.add_node(
        act_3,
        "escalate_human",
        NodeRole.ACTION,
        {
            "action_id": act_3,
            "action_kind": "escalate_human",
            "kind": "escalate_human",
            "procedure_id": "proc-escalate-human",
            "requires_approval": True,
        },
    )

    appr_3 = svc.approve_action(act_3, operator_notes="Manual escalation procedure authorized.")
    ep_id_3 = appr_3["persistent_episode_recorded"]
    print(f"Action:     {act_3}")
    print(f"Episode ID: {ep_id_3}")
    print(f"Outcome:    {appr_3['outcome']}")
    print(f"Procedure:  {appr_3['procedure_id']}")

    assert f"inc_{seed_3}" in ep_id_3, f"Episode ID must contain incident ID 'inc_{seed_3}', got {ep_id_3}"
    assert appr_3["outcome"] == "approved"
    assert appr_3["procedure_id"] == "proc-escalate-human"

    rank_3 = mem.rank_procedures(situation="containment")
    print(f"Episode Count after Incident 3: {rank_3.total_episodes_found} (Expected: 3)")
    assert rank_3.total_episodes_found == 3, f"Episode count must rise by exactly 1 to 3, got {rank_3.total_episodes_found}"
    assert len(rank_3.ranked_procedures) >= 2, f"Must have at least 2 procedures to compare, got {len(rank_3.ranked_procedures)}"
    assert "Comparing" in rank_3.statement, f"Statement must compare procedures when >= 2 exist: {rank_3.statement}"
    print(f"\n[RANKING STATEMENT]:\n{rank_3.statement}")
    for p in rank_3.ranked_procedures:
        print(f"  -> Procedure: {p.procedure_id} | Episodes: {p.episode_count} | Success Rate: {p.success_rate*100:.1f}%")

    # =========================================================================
    # DEDUPLICATION CHECK: Never count one episode twice
    # =========================================================================
    print(f"\n--- [DEDUPLICATION CHECK] Re-approving exact same action in Seed 3303 ---")
    re_appr = svc.approve_action(act_3, operator_notes="Duplicate replay test")
    assert re_appr["persistent_episode_recorded"] == ep_id_3, "Replay must use identical episode ID"

    rank_after_replay = mem.rank_procedures(situation="containment")
    print(f"Episode Count after duplicate replay: {rank_after_replay.total_episodes_found} (Expected: 3)")
    assert rank_after_replay.total_episodes_found == 3, "Episode count must NEVER rise when replaying existing episode"

    print(f"\n{'='*100}")
    print("ALL DEMAND 3 INVARIANTS VERIFIED:")
    print("  1. Episode IDs include incident IDs (inc_1101, inc_2202, inc_3303)")
    print("  2. Episode count rises by exactly +1 per approval or rejection (0 -> 1 -> 2 -> 3)")
    print("  3. Ranking prints 'Comparison is not possible' when <2 procedures, and compares top procedures when >=2")
    print("  4. Never counts an episode twice on duplicate replay (3 remains 3)")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    test_demand3_memory_counting_and_ranking()
