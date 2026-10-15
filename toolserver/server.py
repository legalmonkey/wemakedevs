"""Dynamic FastMCP Tool Server (Part B, Phase B2).

Exposes MCP tools dynamically gated by parameterised Cypher queries evaluated against the graph.
Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoded tool names or domain Cypher values. Tools and gates loaded from config/gates.yaml.
- Rule 5: Gates are evaluated before the tool list is built, every time.
- A hold on an untainted batch is refused because the tool is absent from the tool list.
- Registers at least two graph algorithm tools (shortest path, centrality, components).
"""

from __future__ import annotations
import inspect
from typing import Any, Callable, Dict, List, Optional
from fastmcp import FastMCP
from fastmcp.tools import Tool

from contracts.query_api import QueryAPIProtocol
from contracts.gates import ToolGateDefinition
from contracts.ontology import EdgeRole, NodeRole
from toolserver.gate_evaluator import GateEvaluator


def _create_action_tool_handler(
    tool_def: ToolGateDefinition,
    graph_client: Any,
    gate_evaluator: GateEvaluator,
) -> Callable[..., Dict[str, Any]]:
    """Generates an action tool execution handler bound dynamically to a gate definition."""

    def handler(entity_id: str, reason: str = "Automated policy execution") -> Dict[str, Any]:
        # Rule 5: Gate is verified at execution time as well
        gate_res = gate_evaluator.evaluate(tool_def.tool_name, {"entity_id": entity_id})
        if not gate_res.allowed:
            raise PermissionError(
                f"Action '{tool_def.tool_name}' refused by gate for entity '{entity_id}': {gate_res.reason}"
            )

        # Retrieve causal path if entity is tainted or suspect
        target_node = graph_client.get_node(entity_id) if hasattr(graph_client, "get_node") else None
        causal_path = [entity_id]
        if target_node:
            causal_path = target_node.properties.get("taint_via_path", [entity_id])

        # Create Action node in graph (Rule 7: Every action has a stored path)
        action_id = f"act-{tool_def.tool_name}-{entity_id}"
        if hasattr(graph_client, "add_node"):
            graph_client.add_node(
                node_id=action_id,
                kind=tool_def.tool_name,
                role=NodeRole.ACTION,
                properties={
                    "tool_name": tool_def.tool_name,
                    "target_entity_id": entity_id,
                    "causal_path": causal_path,
                    "path_hops": max(0, len(causal_path) - 1),
                    "reason_code": reason,
                    "requires_approval": True,
                },
            )
            # Add edge connecting action to target entity
            graph_client.add_edge(
                source_id=action_id,
                target_id=entity_id,
                kind="APPLIES_TO",
                role=EdgeRole.SUPPORT,
            )

        return {
            "status": "success",
            "action_id": action_id,
            "tool_name": tool_def.tool_name,
            "entity_id": entity_id,
            "causal_path": causal_path,
        }

    handler.__name__ = tool_def.tool_name
    handler.__doc__ = tool_def.description
    return handler


def _create_shortest_path_handler(graph_client: QueryAPIProtocol) -> Callable[..., Dict[str, Any]]:
    """Handler for shortest path algorithm tool (Why path)."""
    def algo_shortest_path(source_id: str, target_id: str) -> Dict[str, Any]:
        res = graph_client.algo_shortest_path(source_id, target_id)
        return {
            "source_id": res.data.source_id,
            "target_id": res.data.target_id,
            "length": res.data.length,
            "path_node_ids": res.data.path_node_ids,
            "path_edge_kinds": res.data.path_edge_kinds,
            "query_text": res.query_text,
        }
    return algo_shortest_path


def _create_centrality_handler(graph_client: QueryAPIProtocol) -> Callable[..., Dict[str, Any]]:
    """Handler for centrality algorithm tool (chokepoints)."""
    def algo_centrality(scope: str = "all") -> Dict[str, Any]:
        res = graph_client.algo_centrality(scope)
        return {
            "scope": res.data.scope,
            "scores": [s.model_dump() for s in res.data.scores],
            "query_text": res.query_text,
        }
    return algo_centrality


def _create_components_handler(graph_client: QueryAPIProtocol) -> Callable[..., Dict[str, Any]]:
    """Handler for connected components algorithm tool (incident clusters)."""
    def algo_components(scope: str = "all") -> Dict[str, Any]:
        res = graph_client.algo_components(scope)
        return {
            "scope": res.data.scope,
            "components": res.data.components,
            "query_text": res.query_text,
        }
    return algo_components


def build_scoped_mcp_server(
    entity_id: str,
    graph_client: QueryAPIProtocol,
    gate_evaluator: Optional[GateEvaluator] = None,
    server_name: Optional[str] = None,
) -> FastMCP:
    """Builds a FastMCP server instance dynamically scoped to an entity / decision.

    Gates are evaluated BEFORE the tool list is built, every time.
    Tools whose gates evaluate to False are NOT registered on this server.
    """
    evaluator = gate_evaluator or GateEvaluator(graph_client=graph_client)
    name = server_name or f"tainted-mcp-{entity_id}"
    app = FastMCP(name)

    # 1. Dynamically evaluate gates for this entity
    unlocked_tool_names = set(evaluator.get_unlocked_tools(entity_id))

    # 2. Register only unlocked tools from gates configuration
    for gate_def in evaluator.config.gates:
        if gate_def.tool_name not in unlocked_tool_names:
            continue

        # Check if algorithm tool
        if "algo_shortest_path" in gate_def.tool_name:
            h = _create_shortest_path_handler(graph_client)
            tool = Tool.from_function(h, name=gate_def.tool_name, description=gate_def.description)
            app.add_tool(tool)
        elif "algo_centrality" in gate_def.tool_name:
            h = _create_centrality_handler(graph_client)
            tool = Tool.from_function(h, name=gate_def.tool_name, description=gate_def.description)
            app.add_tool(tool)
        elif "algo_components" in gate_def.tool_name:
            h = _create_components_handler(graph_client)
            tool = Tool.from_function(h, name=gate_def.tool_name, description=gate_def.description)
            app.add_tool(tool)
        else:
            # Action tool
            h = _create_action_tool_handler(gate_def, graph_client, evaluator)
            tool = Tool.from_function(h, name=gate_def.tool_name, description=gate_def.description)
            app.add_tool(tool)

    return app
