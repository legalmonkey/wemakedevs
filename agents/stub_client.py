"""Stub Graph Client built from Query API Contract (contracts.query_api).

Provides an in-memory graph client implementing QueryAPIProtocol for Phase B0 exit check
and offline testing without requiring an external FalkorDB instance.
Follows zero domain hardcoding rule: operates purely on graph roles, kinds, and edges.
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Set
from contracts.query_api import (
    QueryResult,
    TraceEntity,
    TraceResult,
    SupportRecord,
    SupportResult,
    SiblingsResult,
    ExposureRecord,
    ExposureResult,
    ExplainResult,
    GateEvaluationResult,
    ShortestPathResult,
    CentralityScore,
    CentralityResult,
    ComponentsResult,
    QueryAPIProtocol,
)
from contracts.ontology import EdgeRole, NodeRole


class InMemoryNode:
    def __init__(
        self,
        node_id: str,
        kind: str,
        role: NodeRole,
        properties: Optional[Dict[str, Any]] = None,
    ):
        self.node_id = node_id
        self.kind = kind
        self.role = role
        self.properties: Dict[str, Any] = properties or {}


class InMemoryEdge:
    def __init__(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        role: EdgeRole,
        properties: Optional[Dict[str, Any]] = None,
    ):
        self.source_id = source_id
        self.target_id = target_id
        self.kind = kind
        self.role = role
        self.properties: Dict[str, Any] = properties or {}


class StubGraphClient(QueryAPIProtocol):
    """Stub graph client implementing QueryAPIProtocol."""

    def __init__(self, tenant_id: str = "tenant-default"):
        self.tenant_id = tenant_id
        self.nodes: Dict[str, InMemoryNode] = {}
        self.edges: List[InMemoryEdge] = []
        self.gate_rules: Dict[str, Dict[str, Any]] = {}
        self.executed_queries: List[str] = []

    def add_node(
        self,
        node_id: str,
        kind: str,
        role: NodeRole,
        properties: Optional[Dict[str, Any]] = None,
    ) -> InMemoryNode:
        node = InMemoryNode(node_id, kind, role, properties)
        self.nodes[node_id] = node
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        role: EdgeRole,
        properties: Optional[Dict[str, Any]] = None,
    ) -> InMemoryEdge:
        edge = InMemoryEdge(source_id, target_id, kind, role, properties)
        self.edges.append(edge)
        return edge

    def get_node(self, node_id: str) -> Optional[InMemoryNode]:
        return self.nodes.get(node_id)

    def update_node(self, node_id: str, properties: Dict[str, Any]) -> bool:
        node = self.nodes.get(node_id)
        if node:
            node.properties.update(properties)
            self.executed_queries.append(f"MATCH (n {{id: '{node_id}'}}) SET n += {properties}")
            return True
        return False

    def find_nodes_by_role(
        self,
        role: NodeRole,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[InMemoryNode]:
        query_text = f"MATCH (n:{role.value}) RETURN n"
        self.executed_queries.append(query_text)
        results = [n for n in self.nodes.values() if n.role == role]
        if filters:
            for k, v in filters.items():
                results = [n for n in results if n.properties.get(k) == v]
        return results

    def get_outgoing_edges(
        self,
        node_id: str,
        role: Optional[EdgeRole] = None,
    ) -> List[InMemoryEdge]:
        edges = [e for e in self.edges if e.source_id == node_id]
        if role:
            edges = [e for e in edges if e.role == role]
        return edges

    def get_incoming_edges(
        self,
        node_id: str,
        role: Optional[EdgeRole] = None,
    ) -> List[InMemoryEdge]:
        edges = [e for e in self.edges if e.target_id == node_id]
        if role:
            edges = [e for e in edges if e.role == role]
        return edges

    def write_taints_edge(
        self,
        source_id: str,
        target_id: str,
        hops: int,
        via_path: List[str],
    ) -> InMemoryEdge:
        cypher = (
            f"MATCH (s {{id: '{source_id}'}}), (t {{id: '{target_id}'}}) "
            f"CREATE (s)-[:TAINTS {{hops: {hops}, via_path: {via_path}}}]->(t)"
        )
        self.executed_queries.append(cypher)
        return self.add_edge(
            source_id=source_id,
            target_id=target_id,
            kind="TAINTS",
            role=EdgeRole.TAINTS,
            properties={"hops": hops, "via_path": via_path},
        )


    def register_gate(
        self,
        tool_name: str,
        cypher_query: str,
        required_parameters: List[str],
        condition_evaluator: Optional[Any] = None,
    ) -> None:
        self.gate_rules[tool_name] = {
            "cypher": cypher_query,
            "params": required_parameters,
            "evaluator": condition_evaluator,
        }

    # --- QueryAPIProtocol Implementation ---

    def trace(self, event: str) -> QueryResult[TraceResult]:
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (e:{NodeRole.EVENT.value} {{id: '{event}'}})-[:{EdgeRole.TAINTS.value}*]->(target) "
            "RETURN target, length(path) AS hops, [n in nodes(path) | n.id] AS via_path"
        )
        self.executed_queries.append(query_text)

        # In-memory BFS trace following TAINTS or causal edges
        visited: Dict[str, TraceEntity] = {}
        queue: List[tuple[str, int, List[str]]] = [(event, 0, [event])]

        while queue:
            curr_id, hops, path = queue.pop(0)
            # Find outgoing edges
            for edge in self.edges:
                if edge.source_id == curr_id:
                    next_id = edge.target_id
                    if next_id not in visited and next_id in self.nodes:
                        next_node = self.nodes[next_id]
                        next_path = path + [next_id]
                        entity = TraceEntity(
                            entity_id=next_id,
                            entity_kind=next_node.kind,
                            role=next_node.role.value,
                            hops=hops + 1,
                            via_path=next_path,
                            properties=next_node.properties,
                        )
                        visited[next_id] = entity
                        queue.append((next_id, hops + 1, next_path))

        entities = list(visited.values())
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=TraceResult(event_id=event, tainted_entities=entities),
            query_text=query_text,
            result_size=len(entities),
            duration_ms=round(elapsed_ms, 3),
        )

    def support(self, decision: str) -> QueryResult[SupportResult]:
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (d:{NodeRole.DECISION.value} {{id: '{decision}'}})<-[:{EdgeRole.SUPPORT.value}]-(ev:{NodeRole.EVIDENCE.value}) "
            "RETURN ev, ev.valid AS is_valid, ev.group_id AS group_id"
        )
        self.executed_queries.append(query_text)

        supports: List[SupportRecord] = []
        groups: Set[str] = set()
        unverifiable_count = 0

        for edge in self.edges:
            if edge.target_id == decision and edge.role == EdgeRole.SUPPORT:
                ev_node = self.nodes.get(edge.source_id)
                if ev_node:
                    is_valid = bool(ev_node.properties.get("valid", True))
                    is_unverifiable = bool(ev_node.properties.get("unverifiable", False))
                    group_id = ev_node.properties.get("group_id")
                    if is_unverifiable:
                        unverifiable_count += 1
                    if is_valid and group_id:
                        groups.add(str(group_id))
                    supports.append(
                        SupportRecord(
                            evidence_id=ev_node.node_id,
                            evidence_kind=ev_node.kind,
                            is_valid=is_valid and not is_unverifiable,
                            group_id=str(group_id) if group_id else None,
                            properties=ev_node.properties,
                        )
                    )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=SupportResult(
                decision_id=decision,
                supports=supports,
                independent_groups_count=len(groups),
                unverifiable_count=unverifiable_count,
            ),
            query_text=query_text,
            result_size=len(supports),
            duration_ms=round(elapsed_ms, 3),
        )

    def siblings(self, unit: str) -> QueryResult[SiblingsResult]:
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (u:{NodeRole.UNIT.value} {{id: '{unit}'}})-[:{EdgeRole.DERIVES_FROM.value}]->(parent) "
            f"<-[:{EdgeRole.DERIVES_FROM.value}]-(sibling:{NodeRole.UNIT.value}) "
            "RETURN parent.id, collect(DISTINCT sibling.id) AS siblings"
        )
        self.executed_queries.append(query_text)

        parents: List[str] = [
            edge.target_id
            for edge in self.edges
            if edge.source_id == unit and edge.role == EdgeRole.DERIVES_FROM
        ]
        shared_parent = parents[0] if parents else None
        siblings: Set[str] = set()
        if shared_parent:
            for edge in self.edges:
                if (
                    edge.target_id == shared_parent
                    and edge.role == EdgeRole.DERIVES_FROM
                    and edge.source_id != unit
                ):
                    siblings.add(edge.source_id)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=SiblingsResult(
                unit_id=unit,
                sibling_unit_ids=sorted(list(siblings)),
                shared_parent_id=shared_parent,
            ),
            query_text=query_text,
            result_size=len(siblings),
            duration_ms=round(elapsed_ms, 3),
        )

    def exposure(self, unit: str) -> QueryResult[ExposureResult]:
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (u:{NodeRole.UNIT.value} {{id: '{unit}'}})-[:{EdgeRole.SHIPS_IN.value}]->(s:{NodeRole.SHIPMENT.value}) "
            f"-[:{EdgeRole.DELIVERED_TO.value}]->(r:{NodeRole.RECIPIENT.value}) "
            "RETURN s.id, r.id, s.status"
        )
        self.executed_queries.append(query_text)

        exposures: List[ExposureRecord] = []
        for edge in self.edges:
            if edge.source_id == unit and edge.role == EdgeRole.SHIPS_IN:
                shipment_id = edge.target_id
                shipment_node = self.nodes.get(shipment_id)
                recipient_id = None
                for edge2 in self.edges:
                    if edge2.source_id == shipment_id and edge2.role == EdgeRole.DELIVERED_TO:
                        recipient_id = edge2.target_id
                        break
                status = (
                    shipment_node.properties.get("status", "unknown")
                    if shipment_node
                    else "unknown"
                )
                exposures.append(
                    ExposureRecord(
                        unit_id=unit,
                        shipment_id=shipment_id,
                        recipient_id=recipient_id,
                        status=status,
                    )
                )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ExposureResult(unit_id=unit, exposures=exposures),
            query_text=query_text,
            result_size=len(exposures),
            duration_ms=round(elapsed_ms, 3),
        )

    def explain(self, action: str) -> QueryResult[ExplainResult]:
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (a:{NodeRole.ACTION.value} {{id: '{action}'}})-[:{EdgeRole.TAINTS.value}*]->(origin) "
            "RETURN a, origin, a.causal_path, a.reason_code"
        )
        self.executed_queries.append(query_text)

        action_node = self.nodes.get(action)
        causal_path: List[str] = []
        reason_code = "UNSPECIFIED"
        details: Dict[str, Any] = {}

        if action_node:
            causal_path = action_node.properties.get("causal_path", [action])
            reason_code = action_node.properties.get("reason_code", "EXPOSURE_DETECTED")
            details = action_node.properties

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ExplainResult(
                action_id=action,
                causal_path=causal_path,
                path_hops=max(0, len(causal_path) - 1),
                reason_code=reason_code,
                details=details,
            ),
            query_text=query_text,
            result_size=1 if action_node else 0,
            duration_ms=round(elapsed_ms, 3),
        )

    def evaluate_gate(self, tool: str, params: Dict[str, Any]) -> QueryResult[GateEvaluationResult]:
        t0 = time.perf_counter()
        gate_info = self.gate_rules.get(tool)
        cypher = gate_info["cypher"] if gate_info else f"MATCH (n {{id: '{params.get('entity_id')}'}}) RETURN true"
        query_text = f"// Gate check for {tool}\n{cypher}\nPARAMS: {params}"
        self.executed_queries.append(query_text)

        allowed = False
        reason = "Gate rule not defined"
        if gate_info:
            evaluator = gate_info.get("evaluator")
            if callable(evaluator):
                allowed, reason = evaluator(params, self)
            else:
                # Default evaluation based on target node status
                entity_id = params.get("entity_id")
                target = self.nodes.get(entity_id) if entity_id else None
                if target:
                    # Example check: is entity tainted?
                    is_tainted = bool(target.properties.get("is_tainted", False))
                    allowed = is_tainted
                    reason = "Entity is tainted" if allowed else "Entity is not tainted"
                else:
                    allowed = False
                    reason = "Target entity not found in graph"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=GateEvaluationResult(
                tool_name=tool,
                allowed=allowed,
                reason=reason,
                evaluated_params=params,
            ),
            query_text=query_text,
            result_size=1,
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_shortest_path(self, a: str, b: str) -> QueryResult[ShortestPathResult]:
        t0 = time.perf_counter()
        query_text = (
            f"MATCH p = shortestPath((a {{id: '{a}'}})-[*]-(b {{id: '{b}'}})) "
            "RETURN [n in nodes(p) | n.id] AS node_ids, [r in relationships(p) | type(r)] AS edge_kinds"
        )
        self.executed_queries.append(query_text)

        # BFS shortest path
        queue: List[tuple[str, List[str], List[str]]] = [(a, [a], [])]
        visited: Set[str] = {a}
        found_nodes: List[str] = []
        found_edges: List[str] = []

        while queue:
            curr_id, path_nodes, path_edges = queue.pop(0)
            if curr_id == b:
                found_nodes = path_nodes
                found_edges = path_edges
                break
            for edge in self.edges:
                neighbor = None
                if edge.source_id == curr_id:
                    neighbor = edge.target_id
                elif edge.target_id == curr_id:
                    neighbor = edge.source_id
                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path_nodes + [neighbor], path_edges + [edge.kind]))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ShortestPathResult(
                source_id=a,
                target_id=b,
                path_node_ids=found_nodes,
                path_edge_kinds=found_edges,
                length=max(0, len(found_nodes) - 1),
            ),
            query_text=query_text,
            result_size=len(found_nodes),
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_centrality(self, scope: str) -> QueryResult[CentralityResult]:
        t0 = time.perf_counter()
        query_text = (
            f"CALL gds.betweenness.stream('{scope}') "
            "YIELD nodeId, score RETURN gds.util.asNode(nodeId).id AS entity_id, score ORDER BY score DESC"
        )
        self.executed_queries.append(query_text)

        # Degree centrality approximation over current edges
        degrees: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        for edge in self.edges:
            degrees[edge.source_id] = degrees.get(edge.source_id, 0) + 1
            degrees[edge.target_id] = degrees.get(edge.target_id, 0) + 1

        sorted_nodes = sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)
        scores: List[CentralityScore] = [
            CentralityScore(entity_id=k, score=float(v), rank=idx + 1)
            for idx, (k, v) in enumerate(sorted_nodes)
        ]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=CentralityResult(scope=scope, scores=scores),
            query_text=query_text,
            result_size=len(scores),
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_components(self, scope: str) -> QueryResult[ComponentsResult]:
        t0 = time.perf_counter()
        query_text = (
            f"CALL gds.wcc.stream('{scope}') "
            "YIELD componentId, nodeId RETURN componentId, collect(gds.util.asNode(nodeId).id) AS component"
        )
        self.executed_queries.append(query_text)

        visited: Set[str] = set()
        components: List[List[str]] = []

        for node_id in self.nodes:
            if node_id not in visited:
                comp: List[str] = []
                queue = [node_id]
                visited.add(node_id)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for edge in self.edges:
                        neighbor = None
                        if edge.source_id == curr:
                            neighbor = edge.target_id
                        elif edge.target_id == curr:
                            neighbor = edge.source_id
                        if neighbor and neighbor not in visited and neighbor in self.nodes:
                            visited.add(neighbor)
                            queue.append(neighbor)
                components.append(sorted(comp))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ComponentsResult(scope=scope, components=components),
            query_text=query_text,
            result_size=len(components),
            duration_ms=round(elapsed_ms, 3),
        )
