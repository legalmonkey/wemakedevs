"""Demand 5 Verification Suite: Race Conditions & Customer Path Verification for draft_notice.

Verifies:
(1) Race test: A reaffirmed unit can NEVER be held or noticed under ANY agent interleaving
    (tested across 30 randomized agent execution permutations).
(2) draft_notice Cypher gate strictly verifies the DELIVERED_TO path for the given customer:
    - Allowed for tainted batch delivered to customer A.
    - Refused for tainted batch when queried for customer B (no delivery path to customer B).
    - Refused for clean batch delivered to customer A.
    - Refused for unshipped batch.
"""

import random
import pytest
from contracts.ontology import NodeRole, EdgeRole
from engine.falkordb_client import FalkorDBGraphClient
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from toolserver.gate_evaluator import GateEvaluator


def test_race_reaffirmed_unit_never_held_or_noticed_under_any_interleaving():
    """Verify that a reaffirmed unit can never receive hold or notice actions under any agent interleaving."""
    rng = random.Random(9999)
    print(f"\n{'='*95}")
    print("DEMAND 5.1: RACE TEST - REAFFIRMED UNIT CAN NEVER BE HELD OR NOTICED")
    print(f"{'='*95}")

    # Test 30 randomized agent interleavings
    for run_idx in range(1, 31):
        client = FalkorDBGraphClient(tenant_id=f"test-race-reaffirm-{run_idx}", clean=True)

        # 1. Setup Unit, Decision, Evidence, Shipment, Customer
        batch_id = f"batch-race-{run_idx}"
        client.add_node(batch_id, "BatchLot", NodeRole.UNIT, {"is_tainted": False, "status": "released"})

        # Decision with 3 independent valid groups (reaffirmed under min_independent=2)
        dec_id = f"dec-race-{run_idx}"
        client.add_node(dec_id, "QualityDecision", NodeRole.DECISION, {"status": "pending"})
        client.add_edge(dec_id, batch_id, "SUPPORT", EdgeRole.SUPPORT)

        for g in range(3):
            ev_id = f"ev-race-{run_idx}-{g}"
            client.add_node(ev_id, "LabTest", NodeRole.EVIDENCE, {"valid": True, "group_id": f"grp_{g}"})
            client.add_edge(ev_id, dec_id, "SUPPORTS", EdgeRole.SUPPORT)

        # Shipment and Customer
        ship_id = f"ship-race-{run_idx}"
        cust_id = f"cust-race-{run_idx}"
        client.add_node(ship_id, "DispatchShipment", NodeRole.SHIPMENT, {"status": "in_transit"})
        client.add_node(cust_id, "CustomerAccount", NodeRole.RECIPIENT, {"tier": "commercial"})
        client.add_edge(batch_id, ship_id, "SHIPS_IN", EdgeRole.SHIPS_IN)
        client.add_edge(ship_id, cust_id, "DELIVERED_TO", EdgeRole.DELIVERED_TO)

        # Setup agents
        sentinel = SentinelAgent(client.tenant_id, client)
        tracer = TracerAgent(client.tenant_id, client)
        adjudicator = AdjudicatorAgent(client.tenant_id, client)
        dispatcher = DispatcherAgent(client.tenant_id, client)

        agents = [sentinel, tracer, adjudicator, dispatcher]

        # Shuffle execution order for 20 ticks to simulate arbitrary OS thread / process scheduling
        for _ in range(15):
            rng.shuffle(agents)
            for ag in agents:
                ag.step()

        # Late taint attempt: inject alert targeting unit
        alert_id = f"alert-race-{run_idx}"
        client.add_node(alert_id, "AlertEvent", NodeRole.EVENT, {"processed": False, "target_evidence_id": f"ev-race-{run_idx}-0"})
        for _ in range(15):
            rng.shuffle(agents)
            for ag in agents:
                ag.step()

        # Strict safety assertions across graph actions and unit state
        actions = [n for n in client.nodes.values() if n.role == NodeRole.ACTION]
        hold_actions = [a for a in actions if a.properties.get("action_kind") == "hold_unit" and a.properties.get("target_entity_id") == batch_id]
        notice_actions = [a for a in actions if a.properties.get("action_kind") == "draft_notice" and a.properties.get("target_entity_id") == cust_id]

        unit_node = client.nodes[batch_id]
        unit_status = unit_node.properties.get("status")

        assert len(hold_actions) == 0, f"Interleaving {run_idx} violated invariant: Hold action placed on reaffirmed unit!"
        assert len(notice_actions) == 0, f"Interleaving {run_idx} violated invariant: Draft notice action created for reaffirmed unit!"
        assert unit_status in ("released", "reaffirmed"), f"Interleaving {run_idx} corrupted unit status: {unit_status}"

    print(f"PASSED: 30/30 randomized agent interleavings verified. Reaffirmed unit was NEVER held or noticed.")


def test_draft_notice_verifies_delivered_to_path_for_customer():
    """Verify that draft_notice Cypher gate verifies the DELIVERED_TO path for the given customer."""
    client = FalkorDBGraphClient(tenant_id="test-draft-notice-customer-path", clean=True)
    evaluator = GateEvaluator(graph_client=client)

    print(f"\n{'='*95}")
    print("DEMAND 5.2: FALKORDB GATE TEST - draft_notice CUSTOMER PATH VERIFICATION")
    print(f"{'='*95}")

    # 1. Tainted Batch delivered to Customer A
    client.add_node("batch-tainted-A", "BatchLot", NodeRole.UNIT, {"is_tainted": True, "status": "tainted"})
    client.add_node("ship-outbound-A", "DispatchShipment", NodeRole.SHIPMENT, {"status": "delivered"})
    client.add_node("cust-A", "CustomerAccount", NodeRole.RECIPIENT, {"tier": "enterprise"})
    client.add_edge("batch-tainted-A", "ship-outbound-A", "SHIPS_IN", EdgeRole.SHIPS_IN)
    client.add_edge("ship-outbound-A", "cust-A", "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    # 2. Customer B (does NOT receive batch-tainted-A)
    client.add_node("cust-B", "CustomerAccount", NodeRole.RECIPIENT, {"tier": "retail"})

    # 3. Clean Batch delivered to Customer B
    client.add_node("batch-clean-B", "BatchLot", NodeRole.UNIT, {"is_tainted": False, "status": "released"})
    client.add_node("ship-outbound-B", "DispatchShipment", NodeRole.SHIPMENT, {"status": "delivered"})
    client.add_edge("batch-clean-B", "ship-outbound-B", "SHIPS_IN", EdgeRole.SHIPS_IN)
    client.add_edge("ship-outbound-B", "cust-B", "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    # 4. Tainted Batch that is UNSHIPPED
    client.add_node("batch-tainted-unshipped", "BatchLot", NodeRole.UNIT, {"is_tainted": True, "status": "tainted"})

    # CASE 1: Tainted batch + delivered customer A -> ALLOWED
    res1 = evaluator.evaluate("draft_notice", {"entity_id": "batch-tainted-A", "recipient_id": "cust-A"})
    print(f"1. Tainted Batch -> Customer A (Delivered):    allowed={res1.allowed} | reason='{res1.reason}'")
    assert res1.allowed is True, f"Expected allowed for customer A, got {res1}"

    # CASE 2: Tainted batch + wrong customer B (no delivery path) -> REFUSED
    res2 = evaluator.evaluate("draft_notice", {"entity_id": "batch-tainted-A", "recipient_id": "cust-B"})
    print(f"2. Tainted Batch -> Customer B (NO Path):       allowed={res2.allowed} | reason='{res2.reason}'")
    assert res2.allowed is False, f"Expected refused for customer B without delivery path, got {res2}"
    assert "no delivery path" in res2.reason.lower() or "count(r) = 0" in res2.reason.lower()

    # CASE 3: Clean batch + delivered customer B -> REFUSED (not tainted)
    res3 = evaluator.evaluate("draft_notice", {"entity_id": "batch-clean-B", "recipient_id": "cust-B"})
    print(f"3. Clean Batch   -> Customer B (Untainted):     allowed={res3.allowed} | reason='{res3.reason}'")
    assert res3.allowed is False, f"Expected refused for clean batch, got {res3}"
    assert "not tainted" in res3.reason.lower()

    # CASE 4: Tainted batch + unshipped -> REFUSED
    res4 = evaluator.evaluate("draft_notice", {"entity_id": "batch-tainted-unshipped", "recipient_id": "cust-A"})
    print(f"4. Tainted Batch -> Unshipped:                  allowed={res4.allowed} | reason='{res4.reason}'")
    assert res4.allowed is False, f"Expected refused for unshipped batch, got {res4}"

    print(f"{'='*95}\n")
