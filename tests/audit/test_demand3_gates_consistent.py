"""Demand 3 Verification Suite: Consistent Relationship Names & Real Cypher Gate Evaluation.

Verifies:
(1) Relationship type names are strictly consistent between generator and gates (:SHIPS_IN, :DELIVERED_TO).
(2) On real FalkorDB:
    - draft_notice is ALLOWED for a tainted, shipped batch.
    - draft_notice is REFUSED for a tainted, unshipped batch.
    - draft_notice is REFUSED for an untainted, shipped batch.
"""

import pytest
from contracts.ontology import NodeRole, EdgeRole
from engine.falkordb_client import FalkorDBGraphClient
from toolserver.gate_evaluator import GateEvaluator


def test_consistent_relationship_types_and_draft_notice_gate_on_falkordb():
    """Verify consistent relationship names and draft_notice gate behavior on FalkorDB."""
    client = FalkorDBGraphClient(tenant_id="test-demand3-gate", clean=True)
    evaluator = GateEvaluator(graph_client=client)

    # 1. Setup entities in FalkorDB
    # Tainted + Shipped Batch
    client.add_node(
        node_id="batch-tainted-shipped",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={"is_tainted": True, "status": "tainted"},
    )
    client.add_node(
        node_id="shipment-outbound-1",
        kind="DispatchShipment",
        role=NodeRole.SHIPMENT,
        properties={"status": "in_transit"},
    )
    client.add_node(
        node_id="recipient-customer-1",
        kind="CustomerAccount",
        role=NodeRole.RECIPIENT,
        properties={"tier": "commercial"},
    )
    # Generator uses SHIPS_IN and DELIVERED_TO
    client.add_edge("batch-tainted-shipped", "shipment-outbound-1", "SHIPS_IN", EdgeRole.SHIPS_IN)
    client.add_edge("shipment-outbound-1", "recipient-customer-1", "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    # Tainted + UNSHIPPED Batch
    client.add_node(
        node_id="batch-tainted-unshipped",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={"is_tainted": True, "status": "tainted"},
    )

    # Untainted + Shipped Batch
    client.add_node(
        node_id="batch-clean-shipped",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={"is_tainted": False, "status": "released"},
    )
    client.add_node(
        node_id="shipment-outbound-2",
        kind="DispatchShipment",
        role=NodeRole.SHIPMENT,
        properties={"status": "delivered"},
    )
    client.add_edge("batch-clean-shipped", "shipment-outbound-2", "SHIPS_IN", EdgeRole.SHIPS_IN)

    # 2. Evaluate draft_notice for tainted, shipped batch -> MUST BE ALLOWED
    res_shipped = evaluator.evaluate("draft_notice", {"entity_id": "batch-tainted-shipped"})
    print("\n1. Draft Notice (Tainted + Shipped):", res_shipped)
    assert res_shipped.allowed is True, (
        f"Expected draft_notice to be ALLOWED for tainted+shipped batch, got: {res_shipped}"
    )

    # 3. Evaluate draft_notice for tainted, UNSHIPPED batch -> MUST BE REFUSED
    res_unshipped = evaluator.evaluate("draft_notice", {"entity_id": "batch-tainted-unshipped"})
    print("2. Draft Notice (Tainted + Unshipped):", res_unshipped)
    assert res_unshipped.allowed is False, (
        f"Expected draft_notice to be REFUSED for tainted+unshipped batch, got: {res_unshipped}"
    )

    # 4. Evaluate draft_notice for untainted, shipped batch -> MUST BE REFUSED
    res_clean = evaluator.evaluate("draft_notice", {"entity_id": "batch-clean-shipped"})
    print("3. Draft Notice (Untainted + Shipped):", res_clean)
    assert res_clean.allowed is False, (
        f"Expected draft_notice to be REFUSED for untainted+shipped batch, got: {res_clean}"
    )
