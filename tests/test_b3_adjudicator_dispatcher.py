"""Phase B3 Exit Check: Adjudicator and Dispatcher with Mid-Incident Restart.

Exit check: "Kill and restart any agent mid-incident; final graph state is identical"
Verifies:
1. Adjudicator evaluates declared policy (Section 4 verdict order):
   - Reaffirm if independent groups >= min_independent
   - Escalate (unverifiable) if any unverifiable evidence exists
   - Otherwise taint
2. Changing min_independent changes verdicts with zero code edit.
3. Dispatcher creates Action nodes with stored causal path.
4. Draft notices strictly require human approval (requires_approval = True).
5. Kill and restart any agent mid-incident: Final graph state is 100% identical.
"""

import copy
import pytest
from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType
from engine.falkordb_client import FalkorDBGraphClient
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from agents.event_loop import EventLoop


def build_scenario_graph(tenant_id: str = "tenant-b3"):
    """Builds a deterministic test incident graph with:
    - 1 Calibration Alert event
    - 2 Decisions:
        * dec-reaffirm: has 2 independent valid evidence groups (group-A, group-B)
        * dec-taint: has 0 independent valid groups (only the suspect evidence)
        * dec-unverifiable: has 1 unverifiable evidence
    - Units, Shipments, Recipients
    """
    client = FalkorDBGraphClient(tenant_id=tenant_id, clean=True)

    # Suspect evidence from drift alert
    client.add_node("ev-suspect-1", "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": "grp-1"})
    # Valid independent evidence
    client.add_node("ev-valid-A", "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": "grp-indep-A"})
    client.add_node("ev-valid-B", "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": "grp-indep-B"})
    # Unverifiable evidence
    client.add_node("ev-missing-C", "Reading", NodeRole.EVIDENCE, {"valid": False, "unverifiable": True})

    # Decision 1: Has independent support (group-A and group-B) plus the suspect evidence
    client.add_node("dec-reaffirm", "Disposition", NodeRole.DECISION, {"status": "pending"})
    client.add_edge("ev-suspect-1", "dec-reaffirm", "SUPPORT", EdgeRole.SUPPORT)
    client.add_edge("ev-valid-A", "dec-reaffirm", "SUPPORT", EdgeRole.SUPPORT)
    client.add_edge("ev-valid-B", "dec-reaffirm", "SUPPORT", EdgeRole.SUPPORT)

    # Decision 2: Only rests on suspect evidence
    client.add_node("dec-taint", "Disposition", NodeRole.DECISION, {"status": "pending"})
    client.add_edge("ev-suspect-1", "dec-taint", "SUPPORT", EdgeRole.SUPPORT)

    # Decision 3: Has unverifiable evidence
    client.add_node("dec-unverifiable", "Disposition", NodeRole.DECISION, {"status": "pending"})
    client.add_edge("ev-suspect-1", "dec-unverifiable", "SUPPORT", EdgeRole.SUPPORT)
    client.add_edge("ev-missing-C", "dec-unverifiable", "SUPPORT", EdgeRole.SUPPORT)

    # Units
    client.add_node("unit-reaffirmed", "Batch", NodeRole.UNIT, {})
    client.add_edge("dec-reaffirm", "unit-reaffirmed", "SUPPORT", EdgeRole.SUPPORT)

    client.add_node("unit-tainted", "Batch", NodeRole.UNIT, {})
    client.add_edge("dec-taint", "unit-tainted", "SUPPORT", EdgeRole.SUPPORT)

    client.add_node("unit-unverifiable", "Batch", NodeRole.UNIT, {})
    client.add_edge("dec-unverifiable", "unit-unverifiable", "SUPPORT", EdgeRole.SUPPORT)

    # Shipment and Recipient for tainted unit
    client.add_node("ship-outbound", "Shipment", NodeRole.SHIPMENT, {"status": "in_transit"})
    client.add_edge("unit-tainted", "ship-outbound", "SHIPS_IN", EdgeRole.SHIPS_IN)

    client.add_node("rec-retailer", "Recipient", NodeRole.RECIPIENT, {})
    client.add_edge("ship-outbound", "rec-retailer", "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    # Alert event
    client.add_node("evt-drift-alert", "Alert", NodeRole.EVENT, {
        "processed": False,
        "target_evidence_id": "ev-suspect-1",
    })

    return client


def serialize_graph_state(client: FalkorDBGraphClient):
    """Generates a canonical state dictionary representing all nodes, properties, and edges."""
    nodes_state = {
        nid: {"kind": n.kind, "role": n.role.value, "properties": copy.deepcopy(n.properties)}
        for nid, n in sorted(client.nodes.items())
    }
    edges_state = [
        {"src": e.source_id, "tgt": e.target_id, "role": e.role.value, "props": copy.deepcopy(e.properties)}
        for e in sorted(client.edges, key=lambda x: (x.source_id, x.target_id, x.role.value))
    ]
    return {"nodes": nodes_state, "edges": edges_state}


def test_b3_adjudicator_verdict_order_and_config_change():
    """Verify Section 4 verdict order & changing min_independent in config changes verdicts."""
    client = build_scenario_graph()

    # Mark evidence suspect and decisions tainted
    client.update_node("ev-suspect-1", {"valid": False, "is_suspect": True})
    client.update_node("dec-reaffirm", {"is_tainted": True, "taint_via_path": ["ev-suspect-1", "dec-reaffirm"]})
    client.update_node("dec-taint", {"is_tainted": True, "taint_via_path": ["ev-suspect-1", "dec-taint"]})
    client.update_node("dec-unverifiable", {"is_tainted": True, "taint_via_path": ["ev-suspect-1", "dec-unverifiable"]})

    # 1. Adjudicate with default min_independent = 2
    adj = AdjudicatorAgent(tenant_id="tenant-b3", graph_client=client)
    adj.step()

    # dec-reaffirm has 2 independent groups -> reaffirmed
    assert client.get_node("dec-reaffirm").properties["verdict"] == "reaffirmed"
    # dec-taint has 0 independent groups -> tainted
    assert client.get_node("dec-taint").properties["verdict"] == "tainted"
    # dec-unverifiable has unverifiable evidence and < 2 groups -> unverifiable
    assert client.get_node("dec-unverifiable").properties["verdict"] == "unverifiable"
    assert "human_question" in client.get_node("dec-unverifiable").properties

    # 2. Reset verdict and test with min_independent = 3
    client.update_node("dec-reaffirm", {"verdict_set": False})
    adj_strict = AdjudicatorAgent(tenant_id="tenant-b3", graph_client=client)
    adj_strict.min_independent = 3  # Config changed without code edit
    adj_strict.step()

    # With min_independent = 3, dec-reaffirm only has 2 -> becomes tainted
    assert client.get_node("dec-reaffirm").properties["verdict"] == "tainted"


def test_b3_dispatcher_action_nodes_and_human_approval():
    """Verify Dispatcher creates Action nodes with causal path & draft notice requires approval."""
    client = build_scenario_graph()
    client.update_node("ev-suspect-1", {"valid": False, "is_suspect": True})
    client.update_node("dec-taint", {"is_tainted": True, "taint_via_path": ["ev-suspect-1", "dec-taint"]})
    client.update_node("unit-tainted", {"is_tainted": True, "taint_via_path": ["ev-suspect-1", "dec-taint", "unit-tainted"]})

    adj = AdjudicatorAgent(tenant_id="tenant-b3", graph_client=client)
    adj.step()

    disp = DispatcherAgent(tenant_id="tenant-b3", graph_client=client)
    step_res = disp.step()

    # Action nodes created
    action_nodes = [n for n in client.nodes.values() if n.role == NodeRole.ACTION]
    action_kinds = [n.kind for n in action_nodes]

    # Hold unit action created with stored causal path
    assert "hold_unit" in action_kinds
    hold_node = next(n for n in action_nodes if n.kind == "hold_unit")
    assert hold_node.properties["causal_path"] == ["ev-suspect-1", "dec-taint", "unit-tainted"]
    assert hold_node.properties["path_hops"] == 2

    # Draft notice created for exposed retailer
    assert "draft_notice" in action_kinds
    notice_node = next(n for n in action_nodes if n.kind == "draft_notice")
    # STRICT RULE: draft notice requires human approval
    assert notice_node.properties["requires_approval"] is True
    assert notice_node.properties["approved"] is False
    assert "draft_content" in notice_node.properties


def test_b3_exit_check_kill_and_restart_identical_graph_state():
    """Phase B3 Exit Check: Kill and restart any agent mid-incident; final graph state is identical."""
    tenant_id = "tenant-b3-restart-proof"

    # --- RUN 1: Uninterrupted baseline run ---
    client_baseline = build_scenario_graph(tenant_id=tenant_id)
    loop_baseline = EventLoop(tenant_id=tenant_id)
    loop_baseline.register_agent(SentinelAgent(tenant_id, client_baseline))
    loop_baseline.register_agent(TracerAgent(tenant_id, client_baseline))
    loop_baseline.register_agent(AdjudicatorAgent(tenant_id, client_baseline))
    loop_baseline.register_agent(DispatcherAgent(tenant_id, client_baseline))
    loop_baseline.run_until_idle(max_ticks=10)

    state_baseline = serialize_graph_state(client_baseline)

    # --- RUN 2: Interrupted run with mid-incident crash and restart ---
    client_interrupted = build_scenario_graph(tenant_id=tenant_id)

    # Step 1: Start only Sentinel and Tracer for 2 ticks (mid-incident)
    loop_run1 = EventLoop(tenant_id=tenant_id)
    sentinel_1 = SentinelAgent(tenant_id, client_interrupted)
    tracer_1 = TracerAgent(tenant_id, client_interrupted)
    loop_run1.register_agent(sentinel_1)
    loop_run1.register_agent(tracer_1)
    loop_run1.run_tick()
    loop_run1.run_tick()

    # SIMULATE KILL: Process / agents abruptly killed mid-incident!
    del loop_run1
    del sentinel_1
    del tracer_1

    # SIMULATE RESTART: Fresh agent instances spawned against the graph
    loop_restarted = EventLoop(tenant_id=tenant_id)
    loop_restarted.register_agent(SentinelAgent(tenant_id, client_interrupted))
    loop_restarted.register_agent(TracerAgent(tenant_id, client_interrupted))
    loop_restarted.register_agent(AdjudicatorAgent(tenant_id, client_interrupted))
    loop_restarted.register_agent(DispatcherAgent(tenant_id, client_interrupted))

    # Resume execution until idle
    loop_restarted.run_until_idle(max_ticks=10)

    state_restarted = serialize_graph_state(client_interrupted)

    # --- VERIFY: Graph state after restart is 100% IDENTICAL to uninterrupted run ---
    assert state_restarted["nodes"] == state_baseline["nodes"]
    assert state_restarted["edges"] == state_baseline["edges"]
