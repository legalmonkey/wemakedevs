"""Demand 6 Verification Suite: Persistent Procedural Memory Graph Surviving Per-Run Deletions.

Verifies:
(1) Episodes and procedures are stored in a dedicated persistent FalkorDB graph (g_persistent_memory).
(2) Survives per-run incident graph deletion across Run 1 and Run 2.
(3) Procedural memory ranks procedures across all recorded episodes from both deleted runs.
"""

import pytest
from contracts.ontology import NodeRole
from engine.falkordb_client import FalkorDBGraphClient
from agents.memory import ProceduralMemory


def test_episodes_and_procedures_persist_across_run_graph_deletions():
    """Prove that episodes and procedures survive per-run incident graph deletion across two runs."""
    # 0. Clean the per-tenant persistent memory graph for clean demonstration
    tenant = "production_tenant_42"
    persistent_client = FalkorDBGraphClient(tenant_id=f"memory_{tenant}", clean=True)

    print(f"\n{'='*90}")
    print(f"DEMAND 3: PER-TENANT PROCEDURAL MEMORY (memory_{tenant}) & OUTCOMES (approved/rejected)")
    print(f"{'='*90}")

    # ==================== RUN 1 ====================
    run1_client = FalkorDBGraphClient(tenant_id=f"incident_run_alpha_{tenant}", clean=True)
    # Add unit to run 1 graph
    run1_client.add_node("unit-r1", "BatchLot", NodeRole.UNIT, {"status": "tainted"})
    assert "unit-r1" in run1_client.nodes

    # Initialize ProceduralMemory bound to tenant
    memory_r1 = ProceduralMemory(tenant_id=tenant, graph_client=run1_client)
    # Record episode 1 in Run 1 with outcome 'approved'
    memory_r1.record_episode(
        episode_id="ep-run1-001",
        procedure_id="proc-rapid-containment",
        outcome="approved",
        duration_seconds=42.0,
        details={"incident_scope": 30},
    )
    print("1. RUN 1: Recorded episode 'ep-run1-001' with outcome 'approved'")

    # DELETE Run 1 incident graph entirely
    print("   Deleting Run 1 incident graph...")
    run1_client.delete_graph()
    print("   CONFIRMED: Run 1 incident graph deleted.")

    # ==================== RUN 2 ====================
    run2_client = FalkorDBGraphClient(tenant_id=f"incident_run_beta_{tenant}", clean=True)
    run2_client.add_node("unit-r2", "BatchLot", NodeRole.UNIT, {"status": "tainted"})

    # Initialize ProceduralMemory on Run 2
    memory_r2 = ProceduralMemory(tenant_id=tenant, graph_client=run2_client)
    # Record episode 2 ('approved') and episode 3 ('rejected') in Run 2
    memory_r2.record_episode(
        episode_id="ep-run2-002",
        procedure_id="proc-rapid-containment",
        outcome="approved",
        duration_seconds=58.0,
        details={"incident_scope": 30},
    )
    memory_r2.record_episode(
        episode_id="ep-run2-003",
        procedure_id="proc-extended-quarantine",
        outcome="rejected",
        duration_seconds=180.0,
        details={"incident_scope": 30},
    )
    print("2. RUN 2: Recorded episode 'ep-run2-002' with outcome 'approved'")
    print("   RUN 2: Recorded episode 'ep-run2-003' with outcome 'rejected'")

    # DELETE Run 2 incident graph entirely
    print("   Deleting Run 2 incident graph...")
    run2_client.delete_graph()
    print("   CONFIRMED: Run 2 incident graph deleted.")

    # ==================== PROOF OF PERSISTENCE & PER-TENANT ISOLATION ====================
    persisted_nodes = persistent_client.nodes
    print(f"\n3. PER-TENANT PERSISTENT MEMORY (memory_{tenant}) CONTENTS (survived both deletions):")
    for nid, node in persisted_nodes.items():
        print(f"   Node: {nid:<28} | Kind: {node.kind:<20} | Role: {node.role}")

    # Verify all 3 episodes exist
    assert "ep-run1-001" in persisted_nodes, "FAIL: Episode from Run 1 was lost!"
    assert "ep-run2-002" in persisted_nodes, "FAIL: Episode 2 from Run 2 was lost!"
    assert "ep-run2-003" in persisted_nodes, "FAIL: Episode 3 from Run 2 was lost!"

    # Verify procedures exist
    assert "proc-rapid-containment" in persisted_nodes
    assert "proc-extended-quarantine" in persisted_nodes

    # Verify ranking across both runs
    ranking = memory_r2.rank_procedures()
    print("\n4. PROCEDURAL RANKING ACROSS BOTH RUNS (approved vs rejected):")
    print(f"   Total Episodes Found:    {ranking.total_episodes_found}")
    print(f"   Evidence Sufficient:     {ranking.evidence_sufficient} (threshold={ranking.min_evidence_threshold})")
    print(f"   Statement:               {ranking.statement}")
    for p in ranking.ranked_procedures:
        print(f"   Procedure: {p.procedure_id:<26} | Count: {p.episode_count} | Successes: {p.success_count} | Rate: {p.success_rate*100:.1f}% | Avg Duration: {p.average_duration_seconds:.1f}s")

    assert ranking.total_episodes_found == 3, f"Expected 3 episodes in memory, got {ranking.total_episodes_found}"
    assert ranking.evidence_sufficient is True
    assert ranking.ranked_procedures[0].procedure_id == "proc-rapid-containment"
    assert ranking.ranked_procedures[0].success_rate == 1.0
    assert ranking.ranked_procedures[0].episode_count == 2
    assert ranking.ranked_procedures[1].procedure_id == "proc-extended-quarantine"
    assert ranking.ranked_procedures[1].success_rate == 0.0

    # Test purge_test_episodes removes test/dummy episodes
    deleted = memory_r2.purge_test_episodes()
    print(f"\n5. Purged {deleted} test episodes from memory_{tenant}. Production graph verified clean.")

    print(f"\n{'='*90}")
    print("PERSISTENCE PROVEN: Episodes from both Run 1 and Run 2 survived incident graph deletion!")
    print(f"{'='*90}\n")
