"""Phase B2 Exit Check: MCP server with gate evaluator and algorithm tools.

Exit check: "A hold on an untainted batch is refused because the tool is absent"
Verifies:
1. Tool list is computed per entity/decision from graph state.
2. For an untainted batch, hold tool is absent and calling it is refused.
3. For a tainted batch, hold tool is present, can be executed, and writes Action with causal path.
4. Tool list visibly changes when graph state changes.
5. At least two algorithm tools (shortest path, centrality, components) registered and callable.
"""

import pytest
from fastmcp.exceptions import NotFoundError
from contracts.ontology import EdgeRole, NodeRole
from agents.stub_client import StubGraphClient
from toolserver.gate_evaluator import GateEvaluator
from toolserver.server import build_scoped_mcp_server


@pytest.fixture
def graph_setup():
    client = StubGraphClient(tenant_id="tenant-mcp-test")

    # Untainted unit
    client.add_node(
        node_id="unit-clean-01",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={"is_tainted": False, "status": "approved"},
    )

    # Tainted unit
    client.add_node(
        node_id="unit-tainted-02",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={
            "is_tainted": True,
            "status": "under_investigation",
            "taint_via_path": ["evt-drift-1", "ev-sensor-1", "unit-tainted-02"],
        },
    )

    # Connecting nodes for algorithm tools testing
    client.add_node("node-a", "Unit", NodeRole.UNIT, {})
    client.add_node("node-b", "Unit", NodeRole.UNIT, {})
    client.add_edge("node-a", "node-b", "DERIVES_FROM", EdgeRole.DERIVES_FROM)

    evaluator = GateEvaluator(graph_client=client)
    return client, evaluator


@pytest.mark.asyncio
async def test_b2_untainted_batch_hold_refused_because_absent(graph_setup):
    """Exit Check: A hold on an untainted batch is refused because the tool is absent."""
    client, evaluator = graph_setup

    # Build server scoped to untainted batch
    server = build_scoped_mcp_server("unit-clean-01", client, evaluator)
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    # Hold tool MUST BE ABSENT
    assert "hold_unit" not in tool_names, (
        f"Security violation: 'hold_unit' was offered for untainted unit! Tools: {tool_names}"
    )

    # Calling hold_unit must be refused because the tool does not exist on this server
    with pytest.raises(NotFoundError):
        await server.call_tool("hold_unit", {"entity_id": "unit-clean-01"})


@pytest.mark.asyncio
async def test_b2_tainted_batch_hold_present_and_executable(graph_setup):
    """For a tainted batch, hold tool is unlocked, callable, and persists causal path."""
    client, evaluator = graph_setup

    # Build server scoped to tainted batch
    server = build_scoped_mcp_server("unit-tainted-02", client, evaluator)
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    # Hold tool MUST BE PRESENT
    assert "hold_unit" in tool_names

    # Calling hold_unit must succeed
    result = await server.call_tool("hold_unit", {"entity_id": "unit-tainted-02", "reason": "Incident investigation"})
    assert result is not None

    # Verify Action node was written to graph with causal path (Rule 7)
    action_nodes = [n for n in client.nodes.values() if n.role == NodeRole.ACTION]
    assert len(action_nodes) >= 1
    act_node = action_nodes[0]
    assert act_node.properties["target_entity_id"] == "unit-tainted-02"
    assert act_node.properties["causal_path"] == ["evt-drift-1", "ev-sensor-1", "unit-tainted-02"]


@pytest.mark.asyncio
async def test_b2_tool_list_visibly_changes_with_graph_state(graph_setup):
    """Winning Criterion: Tool list visibly changes when graph state changes."""
    client, evaluator = graph_setup

    # Initially untainted
    server_before = build_scoped_mcp_server("unit-clean-01", client, evaluator)
    tools_before = [t.name for t in await server_before.list_tools()]
    assert "hold_unit" not in tools_before
    assert "release_unit" in tools_before

    # Graph state changes: unit becomes tainted
    client.update_node("unit-clean-01", {"is_tainted": True, "taint_via_path": ["evt-1", "unit-clean-01"]})

    # Tool list re-evaluated
    server_after = build_scoped_mcp_server("unit-clean-01", client, evaluator)
    tools_after = [t.name for t in await server_after.list_tools()]
    assert "hold_unit" in tools_after
    assert "release_unit" not in tools_after


@pytest.mark.asyncio
async def test_b2_algorithm_tools_exposed_and_callable_over_mcp(graph_setup):
    """Winning Criterion: Algorithm tools exposed over MCP."""
    client, evaluator = graph_setup
    server = build_scoped_mcp_server("unit-clean-01", client, evaluator)
    tools = [t.name for t in await server.list_tools()]

    # At least two algorithm tools
    assert "algo_shortest_path" in tools
    assert "algo_centrality" in tools
    assert "algo_components" in tools

    # Call shortest path over MCP
    sp_res = await server.call_tool("algo_shortest_path", {"source_id": "node-a", "target_id": "node-b"})
    assert sp_res is not None

    # Call centrality over MCP
    cent_res = await server.call_tool("algo_centrality", {"scope": "all"})
    assert cent_res is not None

    # Call components over MCP
    comp_res = await server.call_tool("algo_components", {"scope": "all"})
    assert comp_res is not None
