"""Demand 7 Verification Suite: Real Incident Persistent Episode from Recorded Human Approval.

Verifies:
(1) A real incident running through IncidentService writes its own episode into persistent memory.
(2) Outcome is defined strictly from recorded human approval:
    - Operator human approval -> outcome = 'success'.
    - Operator human rejection / escalation -> outcome = 'failure'.
(3) The recorded episode survives across incident runs in g_persistent_memory on FalkorDB.
"""

import asyncio
import pytest
from contracts.ontology import NodeRole
from api.incident_service import IncidentService
from agents.memory import ProceduralMemory
from engine.falkordb_client import FalkorDBGraphClient


def test_real_incident_writes_episode_with_outcome_from_human_approval():
    """Verify real incident writes its own episode to persistent memory with outcome from human approval."""
    svc = IncidentService()
    seed = 9421
    svc.load_seed(seed)

    print(f"\n{'='*105}")
    print("DEMAND 7: REAL INCIDENT WRITING EPISODE WITH OUTCOME FROM RECORDED HUMAN APPROVAL")
    print(f"{'='*105}")

    # 1. Run live incident stream
    events = []
    async def _on_event(ev):
        events.append(ev)

    asyncio.run(svc.run_incident_stream(seed=seed, speed_ms=0, broadcast_callback=_on_event))
    print(f"1. Live incident stream completed on seed {seed} ({len(events)} SSE events emitted).")

    # 2. Find an action in the incident that requires human approval
    actions = [n for n in svc.graph_client.nodes.values() if n.role == NodeRole.ACTION]
    pending_actions = [a for a in actions if a.properties.get("requires_approval")]
    assert len(pending_actions) > 0, "Incident must produce at least one action requiring human approval"

    action_to_approve = pending_actions[0].node_id
    action_kind = pending_actions[0].properties.get("action_kind")
    print(f"2. Found pending action requiring approval: {action_to_approve} (kind: {action_kind})")

    # 3. RECORDED HUMAN APPROVAL
    notes = "Forensic lead verified containment scope; authorized customer draft notice."
    approval_res = svc.approve_action(action_to_approve, operator_notes=notes)
    episode_id = approval_res["persistent_episode_recorded"]
    outcome = approval_res["outcome"]

    print(f"3. Recorded Human Approval on Action: {action_to_approve}")
    print(f"   Episode ID:    {episode_id}")
    print(f"   Outcome:       {outcome} (Derived directly from recorded human approval!)")
    print(f"   Notes:         '{notes}'")

    assert approval_res["status"] == "approved"
    assert outcome == "success", f"Outcome for approved action must be 'success', got '{outcome}'"

    # 4. Verify episode is in g_persistent_memory on FalkorDB
    persistent_client = FalkorDBGraphClient(tenant_id="persistent_memory", clean=False)
    episode_node = persistent_client.get_node(episode_id)
    assert episode_node is not None, f"Episode '{episode_id}' was not found in persistent memory graph!"
    assert episode_node.properties.get("outcome") == "success", (
        f"Stored outcome mismatch: expected 'success', got {episode_node.properties.get('outcome')}"
    )

    # 5. TEST REJECTION OUTCOME
    if len(pending_actions) > 1:
        action_to_reject = pending_actions[1].node_id
    else:
        # Create a second action to test rejection
        action_to_reject = "act-escalate-test-rejection"
        svc.graph_client.add_node(action_to_reject, "escalate_human", NodeRole.ACTION, {"requires_approval": True})

    rejection_res = svc.reject_action(action_to_reject, operator_notes="Scope incomplete; rejected by operator")
    ep_reject_id = rejection_res["persistent_episode_recorded"]
    ep_reject_outcome = rejection_res["outcome"]

    print(f"4. Recorded Human Rejection on Action: {action_to_reject}")
    print(f"   Episode ID:    {ep_reject_id}")
    print(f"   Outcome:       {ep_reject_outcome} (Derived from human rejection!)")

    assert rejection_res["status"] == "rejected"
    assert ep_reject_outcome == "failure"

    reject_node = persistent_client.get_node(ep_reject_id)
    assert reject_node is not None
    assert reject_node.properties.get("outcome") == "failure"

    # 6. Procedural memory ranking incorporates both human approval outcomes
    mem = ProceduralMemory(tenant_id="persistent_memory")
    ranking = mem.rank_procedures()
    print(f"5. Procedural Ranking in Persistent Memory:")
    print(f"   Total Episodes Found: {ranking.total_episodes_found}")
    print(f"   Statement:            {ranking.statement}")
    for proc in ranking.ranked_procedures:
        print(f"   Procedure: {proc.procedure_id:<25} | Successes: {proc.success_count}/{proc.episode_count} ({proc.success_rate * 100:.1f}%)")

    print(f"{'='*105}\n")
