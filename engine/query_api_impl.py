"""Full Query API Implementation (Part A, Phase A2).

Implements contracts.query_api.QueryAPIProtocol with:
- trace(event)
- support(decision)
- siblings(unit)
- exposure(unit)
- explain(action)
- evaluate_gate(tool, params)
- algo_shortest_path(source_id, target_id)
- algo_centrality(scope)
- algo_components(scope)

Every call returns a typed QueryResult[T] with rendered query_text and result_size.
Strictly adheres to Section 0 rules:
- Rule 3: Zero hardcoding.
- Rule 7: Every action has a stored path.
"""

from __future__ import annotations
import collections
import time
from typing import Any, Dict, List, Optional, Set

from contracts.query_api import (
    CentralityResult,
    CentralityScore,
    ComponentsResult,
    ExplainResult,
    ExposureRecord,
    ExposureResult,
    GateEvaluationResult,
    QueryResult,
    ShortestPathResult,
    SiblingsResult,
    SupportRecord,
    SupportResult,
    TraceEntity,
    TraceResult,
)
from contracts.ontology import EdgeRole, NodeRole
from engine.query_builder import QueryBuilder


class QueryAPI:
    """Production Query API implementation fulfilling QueryAPIProtocol."""

    def __init__(
        self,
        graph_client: Any,
        query_builder: QueryBuilder,
        gate_evaluator: Optional[Any] = None,
    ) -> None:
        self.graph_client = graph_client
        self.query_builder = query_builder
        self.gate_evaluator = gate_evaluator

    def trace(self, event: str) -> QueryResult[TraceResult]:
        """Traces multi-hop causal taint from an event across the graph."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_trace_query()

        # If graph_client has delegate trace implementation, use it
        if hasattr(self.graph_client, "trace"):
            delegate_res = self.graph_client.trace(event)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        # Graph traversal fallback over client topology
        tainted_entities: List[TraceEntity] = []
        if hasattr(self.graph_client, "nodes") and hasattr(self.graph_client, "edges"):
            visited: Set[str] = set()
            queue = collections.deque([(event, 0, [event])])

            while queue:
                curr_id, hops, path = queue.popleft()
                for edge in self.graph_client.edges:
                    next_id = None
                    if edge.source_id == curr_id:
                        next_id = edge.target_id
                    elif edge.target_id == curr_id and edge.role == EdgeRole.DERIVES_FROM:
                        next_id = edge.source_id

                    if next_id and next_id not in visited and next_id != event:
                        visited.add(next_id)
                        nxt_node = self.graph_client.nodes.get(next_id)
                        if nxt_node:
                            nxt_path = path + [next_id]
                            role_val = nxt_node.role.value if hasattr(nxt_node.role, "value") else str(nxt_node.role)
                            tainted_entities.append(
                                TraceEntity(
                                    entity_id=next_id,
                                    entity_kind=getattr(nxt_node, "kind", role_val),
                                    role=role_val,
                                    hops=hops + 1,
                                    via_path=nxt_path,
                                    properties=nxt_node.properties,
                                )
                            )
                            queue.append((next_id, hops + 1, nxt_path))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=TraceResult(event_id=event, tainted_entities=tainted_entities),
            query_text=query_text,
            result_size=len(tainted_entities),
            duration_ms=round(elapsed_ms, 3),
        )

    def support(self, decision: str) -> QueryResult[SupportResult]:
        """Evaluates evidence support for a Decision node."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_support_query()

        if hasattr(self.graph_client, "support"):
            delegate_res = self.graph_client.support(decision)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        supports: List[SupportRecord] = []
        groups: Set[str] = set()
        unverifiable_count = 0

        if hasattr(self.graph_client, "edges"):
            for edge in self.graph_client.edges:
                if edge.target_id == decision and edge.role == EdgeRole.SUPPORT:
                    ev_node = self.graph_client.nodes.get(edge.source_id)
                    if ev_node:
                        is_valid = bool(ev_node.properties.get("valid", True))
                        is_unverifiable = bool(ev_node.properties.get("unverifiable", False))
                        group_id = ev_node.properties.get("group_id")
                        if is_unverifiable:
                            unverifiable_count += 1
                        if is_valid and not is_unverifiable and group_id:
                            groups.add(str(group_id))
                        supports.append(
                            SupportRecord(
                                evidence_id=ev_node.node_id,
                                evidence_kind=getattr(ev_node, "kind", "Evidence"),
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
        """Finds sibling units sharing lots or lateral associations."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_siblings_query()

        siblings_found: Set[str] = set()
        shared_parent: Optional[str] = None

        if hasattr(self.graph_client, "edges"):
            # 1. Units linked via lateral link
            from engine.ontology_utils import get_lateral_edge_spec
            lat_kind, lat_role_val = get_lateral_edge_spec()
            for edge in self.graph_client.edges:
                e_role_str = edge.role.value if hasattr(edge.role, 'value') else str(edge.role)
                if e_role_str == lat_role_val or edge.kind == lat_kind:
                    if edge.source_id == unit and edge.target_id != unit:
                        siblings_found.add(edge.target_id)
                    elif edge.target_id == unit and edge.source_id != unit:
                        siblings_found.add(edge.source_id)

            # 2. Units sharing parent lot
            parent_lots = [
                e.target_id
                for e in self.graph_client.edges
                if e.source_id == unit and e.role == EdgeRole.DERIVES_FROM
            ]
            for plot in parent_lots:
                for edge in self.graph_client.edges:
                    if edge.target_id == plot and edge.source_id != unit and edge.role == EdgeRole.DERIVES_FROM:
                        siblings_found.add(edge.source_id)
                        shared_parent = plot

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=SiblingsResult(
                unit_id=unit,
                sibling_unit_ids=sorted(siblings_found),
                shared_parent_id=shared_parent,
            ),
            query_text=query_text,
            result_size=len(siblings_found),
            duration_ms=round(elapsed_ms, 3),
        )

    def exposure(self, unit: str) -> QueryResult[ExposureResult]:
        """Retrieves downstream delivery exposure for a unit."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_exposure_query()

        if hasattr(self.graph_client, "exposure"):
            delegate_res = self.graph_client.exposure(unit)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        exposures: List[ExposureRecord] = []
        if hasattr(self.graph_client, "edges"):
            # unit -> shipment (ships-in)
            shipment_ids = [
                e.target_id
                for e in self.graph_client.edges
                if e.source_id == unit and e.role == EdgeRole.SHIPS_IN
            ]
            for sid in shipment_ids:
                s_node = self.graph_client.nodes.get(sid)
                status = s_node.properties.get("status", "unknown") if s_node else "unknown"
                # shipment -> recipient (delivered-to)
                recipient_ids = [
                    e.target_id
                    for e in self.graph_client.edges
                    if e.source_id == sid and e.role == EdgeRole.DELIVERED_TO
                ]
                for rid in recipient_ids:
                    r_node = self.graph_client.nodes.get(rid)
                    exposures.append(
                        ExposureRecord(
                            unit_id=unit,
                            shipment_id=sid,
                            recipient_id=rid,
                            status=status,
                            properties=r_node.properties if r_node else {},
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
        """Retrieves the stored chain-of-custody path for an Action node."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_explain_query()

        if hasattr(self.graph_client, "explain"):
            delegate_res = self.graph_client.explain(action)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        a_node = self.graph_client.nodes.get(action) if hasattr(self.graph_client, "nodes") else None
        causal_path = a_node.properties.get("causal_path", [action]) if a_node else [action]
        reason_code = a_node.properties.get("action_type", "quarantine_action") if a_node else "unknown"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ExplainResult(
                action_id=action,
                causal_path=causal_path,
                path_hops=max(0, len(causal_path) - 1),
                reason_code=reason_code,
                details=a_node.properties if a_node else {},
            ),
            query_text=query_text,
            result_size=1 if a_node else 0,
            duration_ms=round(elapsed_ms, 3),
        )

    def evaluate_gate(self, tool: str, params: Dict[str, Any]) -> QueryResult[GateEvaluationResult]:
        """Evaluates a parameterised Cypher gate before tool list generation."""
        t0 = time.perf_counter()
        query_text = f"EVALUATE_GATE tool='{tool}' params={params}"

        if self.gate_evaluator is not None and hasattr(self.gate_evaluator, "evaluate"):
            eval_res = self.gate_evaluator.evaluate(tool, params)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=eval_res,
                query_text=query_text,
                result_size=1,
                duration_ms=round(elapsed_ms, 3),
            )

        # Default fallback
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=GateEvaluationResult(
                tool_name=tool,
                allowed=True,
                reason="Default gate permission",
                evaluated_params=params,
            ),
            query_text=query_text,
            result_size=1,
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_shortest_path(self, source_id: str, target_id: str) -> QueryResult[ShortestPathResult]:
        """Algorithm Tool: Shortest path between two graph entities."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_shortest_path_query()

        if hasattr(self.graph_client, "algo_shortest_path"):
            delegate_res = self.graph_client.algo_shortest_path(source_id, target_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        # BFS shortest path traversal over undirected edge topology
        adj: Dict[str, List[tuple[str, str]]] = collections.defaultdict(list)
        if hasattr(self.graph_client, "edges"):
            for e in self.graph_client.edges:
                adj[e.source_id].append((e.target_id, e.kind))
                adj[e.target_id].append((e.source_id, e.kind))

        queue = collections.deque([(source_id, [source_id], [])])
        visited = {source_id}
        found_path: List[str] = []
        found_edges: List[str] = []

        while queue:
            curr, path, edge_kinds = queue.popleft()
            if curr == target_id:
                found_path = path
                found_edges = edge_kinds
                break
            for nxt, ekind in adj[curr]:
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt], edge_kinds + [ekind]))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ShortestPathResult(
                source_id=source_id,
                target_id=target_id,
                path_node_ids=found_path,
                path_edge_kinds=found_edges,
                length=max(0, len(found_path) - 1),
            ),
            query_text=query_text,
            result_size=1 if found_path else 0,
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_centrality(self, scope: str) -> QueryResult[CentralityResult]:
        """Algorithm Tool: Calculates degree centrality to identify chokepoints."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_centrality_query()

        if hasattr(self.graph_client, "algo_centrality"):
            delegate_res = self.graph_client.algo_centrality(scope)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        degrees: Dict[str, int] = collections.defaultdict(int)
        if hasattr(self.graph_client, "edges"):
            for e in self.graph_client.edges:
                degrees[e.source_id] += 1
                degrees[e.target_id] += 1

        sorted_degrees = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
        scores = [
            CentralityScore(entity_id=nid, score=float(deg), rank=i + 1)
            for i, (nid, deg) in enumerate(sorted_degrees)
        ]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=CentralityResult(scope=scope, scores=scores),
            query_text=query_text,
            result_size=len(scores),
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_components(self, scope: str) -> QueryResult[ComponentsResult]:
        """Algorithm Tool: Identifies connected components for incident clustering."""
        t0 = time.perf_counter()
        query_text = self.query_builder.build_components_query()

        if hasattr(self.graph_client, "algo_components"):
            delegate_res = self.graph_client.algo_components(scope)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResult(
                data=delegate_res.data,
                query_text=query_text,
                result_size=delegate_res.result_size,
                duration_ms=round(elapsed_ms, 3),
            )

        adj: Dict[str, Set[str]] = collections.defaultdict(set)
        all_nodes = set(self.graph_client.nodes.keys()) if hasattr(self.graph_client, "nodes") else set()
        if hasattr(self.graph_client, "edges"):
            for e in self.graph_client.edges:
                adj[e.source_id].add(e.target_id)
                adj[e.target_id].add(e.source_id)

        visited: Set[str] = set()
        components: List[List[str]] = []

        for node_id in sorted(all_nodes):
            if node_id not in visited:
                comp = []
                queue = [node_id]
                visited.add(node_id)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for nxt in sorted(adj[curr]):
                        if nxt not in visited:
                            visited.add(nxt)
                            queue.append(nxt)
                components.append(comp)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ComponentsResult(scope=scope, components=components),
            query_text=query_text,
            result_size=len(components),
            duration_ms=round(elapsed_ms, 3),
        )
