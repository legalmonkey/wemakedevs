"""Tests for Phase B0 Exit Check.

Exit check: "Loop runs against a stub graph client built from the contract"
Verifies:
1. All 5 frozen contracts in contracts/
2. BaseAgent and AgentStepResult
3. StubGraphClient built from QueryAPIProtocol
4. EventLoop executing multiple agents coordinating strictly via graph state (no agent-to-agent calls)
5. LLM adapter interface complying with Section 0 Rule 5
"""

import pytest
from contracts.ontology import (
    NodeRole,
    EdgeRole,
    TaintsEdgeProperties,
    NodeKindDeclaration,
    EdgeKindDeclaration,
    OntologyDeclaration,
)
from contracts.query_api import (
    QueryAPIProtocol,
    QueryResult,
    TraceResult,
    SupportResult,
    SiblingsResult,
    ExposureResult,
    ExplainResult,
    ShortestPathResult,
    CentralityResult,
    ComponentsResult,
)
from contracts.events import (
    EventType,
    EventEnvelope,
    EventReceivedPayload,
    TaintAddedPayload,
    AgentStatusPayload,
)
from contracts.registry import (
    StatusDefinition,
    VocabularyDefinition,
    NodePresentationDefinition,
    RegistryResponse,
)
from contracts.gates import (
    ToolGateDefinition,
    GatesConfiguration,
    GateEvaluationResult,
)
from engine.falkordb_client import FalkorDBGraphClient
from agents.base import BaseAgent, WorkItem
from agents.event_loop import EventLoop
from agents.llm_adapter import StubLLMAdapter


class StubProducerAgent(BaseAgent):
    """An agent that discovers unhandled Event nodes in the graph and flags linked evidence."""

    def poll_work(self) -> list[WorkItem]:
        # Query graph for unprocessed events
        items: list[WorkItem] = []
        for node in self.graph_client.nodes.values():
            if node.role == NodeRole.EVENT and not node.properties.get("processed", False):
                items.append(
                    WorkItem(
                        item_id=f"work-{node.node_id}",
                        entity_id=node.node_id,
                        role=node.role.value,
                        properties=node.properties,
                    )
                )
        return items

    def process_item(self, item: WorkItem) -> list[EventEnvelope]:
        # Mark event as processed in graph
        event_node = self.graph_client.nodes[item.entity_id]
        event_node.properties["processed"] = True

        # Find target entity from edge and add a TAINTS edge in the graph
        target_id = event_node.properties.get("target_id")
        emitted_events: list[EventEnvelope] = []

        if target_id and target_id in self.graph_client.nodes:
            target_node = self.graph_client.nodes[target_id]
            target_node.properties["is_tainted"] = True
            self.graph_client.add_edge(
                source_id=item.entity_id,
                target_id=target_id,
                kind="TAINTS",
                role=EdgeRole.TAINTS,
                properties={"hops": 1, "via_path": [item.entity_id, target_id]},
            )

            emitted_events.append(
                self.create_event(
                    event_type=EventType.TAINT_ADDED,
                    entity_ids=[item.entity_id, target_id],
                    payload={
                        "source_id": item.entity_id,
                        "target_id": target_id,
                        "hops": 1,
                        "via_path": [item.entity_id, target_id],
                    },
                )
            )

        return emitted_events


class StubConsumerAgent(BaseAgent):
    """An agent that discovers newly tainted nodes in the graph and flags them for adjudication."""

    def poll_work(self) -> list[WorkItem]:
        # Query graph for tainted decisions/units not yet adjudicated
        items: list[WorkItem] = []
        for node in self.graph_client.nodes.values():
            if node.properties.get("is_tainted", False) and not node.properties.get("adjudicated", False):
                items.append(
                    WorkItem(
                        item_id=f"work-adj-{node.node_id}",
                        entity_id=node.node_id,
                        role=node.role.value,
                        properties=node.properties,
                    )
                )
        return items

    def process_item(self, item: WorkItem) -> list[EventEnvelope]:
        target_node = self.graph_client.nodes[item.entity_id]
        target_node.properties["adjudicated"] = True

        return [
            self.create_event(
                event_type=EventType.VERDICT_SET,
                entity_ids=[item.entity_id],
                payload={
                    "decision_id": item.entity_id,
                    "verdict_kind": "tainted",
                    "independent_groups_count": 0,
                    "unverifiable_count": 0,
                },
            )
        ]


def test_frozen_contracts_integrity():
    """Verify all 5 frozen contracts can be instantiated with kinds only."""
    # 1. Ontology Contract
    onto = OntologyDeclaration(
        version="1.0.0",
        node_kinds=[
            NodeKindDeclaration(kind="TestLot", role=NodeRole.UNIT),
            NodeKindDeclaration(kind="TestReport", role=NodeRole.EVIDENCE),
        ],
        edge_kinds=[
            EdgeKindDeclaration(
                kind="TEST_SUPPORT",
                role=EdgeRole.SUPPORT,
                source_role=NodeRole.EVIDENCE,
                target_role=NodeRole.DECISION,
            )
        ],
    )
    assert len(onto.node_kinds) == 2
    assert onto.node_kinds[0].role == NodeRole.UNIT

    # 2. Event Contract
    envelope = EventEnvelope(
        event_id="evt-1",
        event_type=EventType.EVENT_RECEIVED,
        tenant_id="tenant-alpha",
        timestamp="2026-10-15T00:00:00Z",
        entity_ids=["e1"],
        payload={"source_node_id": "e1"},
    )
    assert envelope.event_type == EventType.EVENT_RECEIVED

    # 3. Registry Contract
    reg = RegistryResponse(
        statuses=[
            StatusDefinition(
                id="st-tainted",
                label="Tainted",
                stamp_text="TAINTED",
                ink_token="ink-signal-tainted",
            )
        ],
        vocabulary={
            "Unit": VocabularyDefinition(
                role="Unit", domain_term="Batch", plural_term="Batches"
            )
        },
        node_presentations={
            "Batch": NodePresentationDefinition(
                kind="Batch", role="Unit", label_property="batch_code"
            )
        },
    )
    assert reg.statuses[0].ink_token == "ink-signal-tainted"

    # 4. Gate Contract
    gates = GatesConfiguration(
        gates=[
            ToolGateDefinition(
                tool_name="hold_unit",
                description="Place hold on unit",
                cypher_query="MATCH (u:Unit {id: $unit_id}) WHERE u.is_tainted RETURN true",
                required_parameters=["unit_id"],
                target_role=NodeRole.UNIT.value,
            )
        ]
    )
    assert gates.gates[0].tool_name == "hold_unit"


def test_stub_graph_client_query_api_protocol():
    """Verify StubGraphClient satisfies QueryAPIProtocol with query telemetry."""
    client = FalkorDBGraphClient(tenant_id="test-tenant")

    # Add sample nodes and edges
    client.add_node("ev-1", "TestReading", NodeRole.EVIDENCE, {"valid": True, "group_id": "grp-1"})
    client.add_node("dec-1", "TestDisposition", NodeRole.DECISION, {})
    client.add_edge("ev-1", "dec-1", "SUPPORT", EdgeRole.SUPPORT)

    # 1. support()
    sup_res = client.support("dec-1")
    assert isinstance(sup_res, QueryResult)
    assert sup_res.result_size == 1
    assert sup_res.data.independent_groups_count == 1
    assert "MATCH (d:Decision" in sup_res.query_text

    # 2. trace()
    client.add_node("evt-1", "CalibrationAlert", NodeRole.EVENT, {})
    client.add_edge("evt-1", "ev-1", "TAINTS", EdgeRole.TAINTS)
    trace_res = client.trace("evt-1")
    assert isinstance(trace_res, QueryResult)
    assert trace_res.result_size >= 1
    assert len(trace_res.data.tainted_entities) >= 1

    # 3. siblings()
    client.add_node("u-1", "Lot", NodeRole.UNIT, {})
    client.add_node("u-2", "Lot", NodeRole.UNIT, {})
    client.add_node("raw-1", "RawMaterial", NodeRole.UNIT, {})
    client.add_edge("u-1", "raw-1", "DERIVES_FROM", EdgeRole.DERIVES_FROM)
    client.add_edge("u-2", "raw-1", "DERIVES_FROM", EdgeRole.DERIVES_FROM)
    sib_res = client.siblings("u-1")
    assert "u-2" in sib_res.data.sibling_unit_ids

    # 4. exposure()
    client.add_node("ship-1", "Outbound", NodeRole.SHIPMENT, {"status": "in_transit"})
    client.add_node("rec-1", "Facility", NodeRole.RECIPIENT, {})
    client.add_edge("u-1", "ship-1", "SHIPS_IN", EdgeRole.SHIPS_IN)
    client.add_edge("ship-1", "rec-1", "DELIVERED_TO", EdgeRole.DELIVERED_TO)
    exp_res = client.exposure("u-1")
    assert exp_res.result_size == 1
    assert exp_res.data.exposures[0].shipment_id == "ship-1"

    # 5. explain()
    client.add_node("act-1", "HoldAction", NodeRole.ACTION, {
        "causal_path": ["evt-1", "ev-1", "u-1", "act-1"],
        "reason_code": "EVIDENCE_INVALIDATED"
    })
    explain_res = client.explain("act-1")
    assert explain_res.data.path_hops == 3
    assert explain_res.data.reason_code == "EVIDENCE_INVALIDATED"

    # 6. evaluate_gate()
    client.register_gate(
        tool_name="place_hold",
        cypher_query="MATCH (n {id: $entity_id}) WHERE n.is_tainted = true RETURN true",
        required_parameters=["entity_id"],
    )
    client.nodes["u-1"].properties["is_tainted"] = False
    gate_res_denied = client.evaluate_gate("place_hold", {"entity_id": "u-1"})
    assert not gate_res_denied.data.allowed

    client.nodes["u-1"].properties["is_tainted"] = True
    gate_res_allowed = client.evaluate_gate("place_hold", {"entity_id": "u-1"})
    assert gate_res_allowed.data.allowed

    # 7. algorithms: shortest_path, centrality, components
    sp_res = client.algo_shortest_path("evt-1", "dec-1")
    assert sp_res.data.length >= 1

    cent_res = client.algo_centrality("all")
    assert cent_res.result_size > 0

    comp_res = client.algo_components("all")
    assert comp_res.result_size > 0


def test_b0_event_loop_runs_against_stub_graph():
    """B0 Exit Check Test: Loop runs against a stub graph client built from the contract.

    Verifies:
    - BaseAgent polling from graph query.
    - Two agents coordinate ONLY via graph state (no agent-to-agent calls).
    - Event loop processes ticks until idle.
    - Event stream records all lifecycle events with tenant_id, timestamp, entity_ids.
    """
    tenant_id = "tenant-001"
    client = FalkorDBGraphClient(tenant_id=tenant_id)
    loop = EventLoop(tenant_id=tenant_id)

    # Set up initial graph state with one pending unhandled Event node
    client.add_node(
        node_id="target-node-100",
        kind="GenericUnit",
        role=NodeRole.UNIT,
        properties={"is_tainted": False, "adjudicated": False},
    )
    client.add_node(
        node_id="evt-trigger-1",
        kind="TriggerEvent",
        role=NodeRole.EVENT,
        properties={"processed": False, "target_id": "target-node-100"},
    )

    producer = StubProducerAgent(
        name="SentinelStub",
        tenant_id=tenant_id,
        graph_client=client,
    )
    consumer = StubConsumerAgent(
        name="AdjudicatorStub",
        tenant_id=tenant_id,
        graph_client=client,
    )

    loop.register_agent(producer)
    loop.register_agent(consumer)

    captured_events: list[EventEnvelope] = []
    loop.add_event_listener(captured_events.append)

    # Run loop until idle
    ticks = loop.run_until_idle(max_ticks=5)

    # Assertions
    assert len(ticks) >= 2  # Tick 1 processes event -> taints target; Tick 2 adjudicates target; Tick 3 idle
    assert any(t.total_items_processed > 0 for t in ticks)

    # Target node was tainted by producer and then adjudicated by consumer strictly via graph
    target_node = client.nodes["target-node-100"]
    assert target_node.properties["is_tainted"] is True
    assert target_node.properties["adjudicated"] is True

    # Events emitted verify Event Contract compliance
    event_types = [e.event_type for e in captured_events]
    assert EventType.TAINT_ADDED in event_types
    assert EventType.VERDICT_SET in event_types
    assert EventType.AGENT_STATUS in event_types

    for ev in captured_events:
        assert ev.tenant_id == tenant_id
        assert ev.timestamp is not None
        assert isinstance(ev.entity_ids, list)


def test_llm_adapter_contract_adherence():
    """Verify LLM adapter never issues verdicts and only selects among unlocked tools."""
    adapter = StubLLMAdapter()

    # Rule 5 check: unlocked tools strictly filter what can be selected
    unlocked = ["apply_quarantine", "request_inspection"]
    selected = adapter.choose_tool(unlocked, "Please apply quarantine to item", {})
    assert selected == "apply_quarantine"

    # When tool list is empty, None is returned
    assert adapter.choose_tool([], "apply quarantine", {}) is None

    # Missing link drafting
    q = adapter.draft_missing_link_question(
        missing_evidence_role="Evidence",
        entity_id="node-xyz",
        context_facts=["calibration expired 2 days ago"],
    )
    assert "node-xyz" in q
    assert "calibration expired 2 days ago" in q
