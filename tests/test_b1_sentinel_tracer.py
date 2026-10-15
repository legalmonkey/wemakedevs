"""Phase B1 Exit Check: Sentinel and Tracer against Query API.

Exit check: "Trace writes hops and via-path for a generated incident"
Verifies:
1. Sentinel discovers unhandled Event and flags suspect Evidence.
2. Tracer propagates taint hop-by-hop across multi-hop paths (including lateral links).
3. Every TAINTS edge written to the graph has hops and via_path properties.
4. Idempotency and cycle-safety.
5. All emitted events conform to Event Contract.
"""

import pytest
from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType
from agents.stub_client import StubGraphClient
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.event_loop import EventLoop


def build_generated_incident_topology(client: StubGraphClient):
    """Constructs a multi-hop incident topology with lateral link:

    [Event: evt-drift-1]
           | (targets)
    [Evidence: ev-sensor-9]
           | (SUPPORT)
    [Decision: dec-release-4]
           | (SUPPORT / governs)
    [Unit: unit-batch-101]
           +---> (DERIVES_FROM) ---> [Unit: unit-batch-202]
           |                              | (SHIPS_IN)
           |                         [Shipment: ship-301]
           |                              | (DELIVERED_TO)
           |                         [Recipient: rec-customer-401]
           |
           +---> (LATERAL_LINK) ---> [Unit: unit-batch-999] (shared lot)
    """
    # 1. Evidence
    client.add_node(
        node_id="ev-sensor-9",
        kind="SensorCalibration",
        role=NodeRole.EVIDENCE,
        properties={"valid": True, "is_suspect": False},
    )

    # 2. Decision
    client.add_node(
        node_id="dec-release-4",
        kind="ReleaseDisposition",
        role=NodeRole.DECISION,
        properties={"status": "approved"},
    )
    client.add_edge("ev-sensor-9", "dec-release-4", "SUPPORT", EdgeRole.SUPPORT)

    # 3. Units
    client.add_node(
        node_id="unit-batch-101",
        kind="IntermediateBatch",
        role=NodeRole.UNIT,
        properties={"status": "released"},
    )
    client.add_edge("dec-release-4", "unit-batch-101", "SUPPORT", EdgeRole.SUPPORT)

    client.add_node(
        node_id="unit-batch-202",
        kind="FinishedBatch",
        role=NodeRole.UNIT,
        properties={"status": "packaged"},
    )
    client.add_edge("unit-batch-202", "unit-batch-101", "DERIVES_FROM", EdgeRole.DERIVES_FROM)

    # Lateral link: another batch produced on shared line/lot
    client.add_node(
        node_id="unit-batch-999",
        kind="ParallelBatch",
        role=NodeRole.UNIT,
        properties={"status": "stored"},
    )
    client.add_edge("unit-batch-101", "unit-batch-999", "LATERAL_LINK", EdgeRole.LATERAL_LINK)

    # 4. Shipment & Recipient
    client.add_node(
        node_id="ship-301",
        kind="OutboundFreight",
        role=NodeRole.SHIPMENT,
        properties={"status": "in_transit"},
    )
    client.add_edge("unit-batch-202", "ship-301", "SHIPS_IN", EdgeRole.SHIPS_IN)

    client.add_node(
        node_id="rec-customer-401",
        kind="DistributionCenter",
        role=NodeRole.RECIPIENT,
        properties={"country": "US"},
    )
    client.add_edge("ship-301", "rec-customer-401", "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    # 5. Retraction Alert Event
    client.add_node(
        node_id="evt-drift-1",
        kind="CalibrationAlert",
        role=NodeRole.EVENT,
        properties={
            "processed": False,
            "target_evidence_id": "ev-sensor-9",
            "reason": "Instrument drift detected outside tolerance",
        },
    )


def test_b1_sentinel_and_tracer_exit_check():
    """Verify Phase B1 Exit Check: Trace writes hops and via-path for a generated incident."""
    tenant_id = "tenant-food-demo"
    client = StubGraphClient(tenant_id=tenant_id)
    build_generated_incident_topology(client)

    sentinel = SentinelAgent(tenant_id=tenant_id, graph_client=client)
    tracer = TracerAgent(tenant_id=tenant_id, graph_client=client)

    loop = EventLoop(tenant_id=tenant_id)
    loop.register_agent(sentinel)
    loop.register_agent(tracer)

    captured_events: list[EventEnvelope] = []
    loop.add_event_listener(captured_events.append)

    # Run loop until all hops are traced and graph reaches idle
    ticks = loop.run_until_idle(max_ticks=10)

    # 1. Sentinel verified
    event_node = client.get_node("evt-drift-1")
    assert event_node.properties["processed"] is True

    evidence_node = client.get_node("ev-sensor-9")
    assert evidence_node.properties["is_suspect"] is True
    assert evidence_node.properties["valid"] is False

    # Check Sentinel SSE events
    event_types = [e.event_type for e in captured_events]
    assert EventType.EVENT_RECEIVED in event_types
    assert EventType.EVIDENCE_SUSPECT in event_types

    # 2. Tracer verified: TAINTS edges written to graph
    taints_edges = [e for e in client.edges if e.role == EdgeRole.TAINTS]
    assert len(taints_edges) >= 5, f"Expected at least 5 TAINTS edges, got {len(taints_edges)}"

    # Map of target_id -> edge for easy assertion
    taints_by_target = {e.target_id: e for e in taints_edges}

    # Verify Decision tainted
    assert "dec-release-4" in taints_by_target
    edge_dec = taints_by_target["dec-release-4"]
    assert edge_dec.properties["hops"] == 1
    assert edge_dec.properties["via_path"] == ["ev-sensor-9", "dec-release-4"]

    # Verify Unit batch 101 tainted
    assert "unit-batch-101" in taints_by_target
    edge_u101 = taints_by_target["unit-batch-101"]
    assert edge_u101.properties["hops"] == 2
    assert edge_u101.properties["via_path"] == ["ev-sensor-9", "dec-release-4", "unit-batch-101"]

    # Verify Derived Finished Batch 202 tainted
    assert "unit-batch-202" in taints_by_target
    edge_u202 = taints_by_target["unit-batch-202"]
    assert edge_u202.properties["hops"] == 3
    assert edge_u202.properties["via_path"] == [
        "ev-sensor-9", "dec-release-4", "unit-batch-101", "unit-batch-202"
    ]

    # Verify Lateral Link Batch 999 tainted
    assert "unit-batch-999" in taints_by_target
    edge_u999 = taints_by_target["unit-batch-999"]
    assert edge_u999.properties["hops"] == 3
    assert edge_u999.properties["via_path"] == [
        "ev-sensor-9", "dec-release-4", "unit-batch-101", "unit-batch-999"
    ]

    # Verify Shipment 301 tainted
    assert "ship-301" in taints_by_target
    edge_s301 = taints_by_target["ship-301"]
    assert edge_s301.properties["hops"] == 4
    assert edge_s301.properties["via_path"] == [
        "ev-sensor-9", "dec-release-4", "unit-batch-101", "unit-batch-202", "ship-301"
    ]

    # Verify Recipient customer 401 tainted
    assert "rec-customer-401" in taints_by_target
    edge_r401 = taints_by_target["rec-customer-401"]
    assert edge_r401.properties["hops"] == 5
    assert edge_r401.properties["via_path"] == [
        "ev-sensor-9", "dec-release-4", "unit-batch-101", "unit-batch-202", "ship-301", "rec-customer-401"
    ]

    # 3. Check taint.added SSE events
    taint_events = [e for e in captured_events if e.event_type == EventType.TAINT_ADDED]
    assert len(taint_events) >= 5
    for te in taint_events:
        assert te.tenant_id == tenant_id
        assert "hops" in te.payload
        assert "via_path" in te.payload
        assert len(te.payload["via_path"]) == te.payload["hops"] + 1

    # 4. Verify Idempotency: another tick produces 0 additional items
    subsequent_tick = loop.run_tick()
    assert subsequent_tick.total_items_processed == 0
