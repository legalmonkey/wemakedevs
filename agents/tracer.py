"""Tracer Agent (Part B, Phase B1).

Advances hop-by-hop across graph relationships from suspect evidence to downstream decisions,
units, shipments, and recipients, writing TAINTS edges with hops and via_path properties.

Strict adherence to Section 0 rules:
- Zero domain hardcoding (traverses generic edge roles and node roles).
- Graph is the only shared state; agents never call each other.
- Every action has a stored path: TAINTS edges persist hops and via_path in the graph.
- Idempotent and cycle-safe.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from agents.base import BaseAgent, WorkItem
from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType


class TracerAgent(BaseAgent):
    """Tracer agent that propagates taints hop-by-hop and writes TAINTS edges."""

    def __init__(
        self,
        tenant_id: str,
        graph_client: Any,
        name: str = "Tracer",
        allow_lateral: bool = True,
    ):
        super().__init__(name=name, tenant_id=tenant_id, graph_client=graph_client)
        self.allow_lateral = allow_lateral

    def _is_already_tainted(self, node_id: str) -> bool:
        """Check if a node has already been traversed by tracer (has incoming TAINTS edge or is suspect)."""
        if hasattr(self.graph_client, "get_incoming_edges"):
            in_edges = self.graph_client.get_incoming_edges(node_id, role=EdgeRole.TAINTS)
            if in_edges:
                return True
        elif hasattr(self.graph_client, "edges"):
            for edge in self.graph_client.edges:
                edge_role = edge.role.value if hasattr(edge.role, "value") else str(edge.role)
                if edge.target_id == node_id and (edge_role == EdgeRole.TAINTS.value or edge.kind == "TAINTS"):
                    return True
        node = self.graph_client.get_node(node_id)
        if node and node.properties.get("is_suspect", False):
            return True
        return False

    def poll_work(self) -> List[WorkItem]:
        """Poll graph for nodes that are suspect or tainted and have untainted downstream neighbors."""
        self.current_phase = "tracer_taint_poll"
        self.current_query = "MATCH (n) WHERE n.is_suspect = true OR n.is_tainted = true RETURN n;"
        work_items: List[WorkItem] = []
        if not hasattr(self.graph_client, "nodes") or not hasattr(self.graph_client, "edges"):
            return work_items

        # Nodes that are suspect or tainted can propagate downstream
        # Decision nodes:
        # - If pending adjudication (status == 'pending' and verdict is not 'tainted'), wait for Adjudicator.
        # - If reaffirmed or unverifiable, halt taint propagation downstream.
        def _can_decision_propagate(dec_node: Any) -> bool:
            props = dec_node.properties
            verdict = props.get("verdict")
            status = props.get("status")
            if verdict in ("reaffirmed", "unverifiable") or status in ("reaffirmed", "unverifiable"):
                return False
            if status == "pending" and verdict != "tainted":
                return False
            return True

        active_nodes = [
            n for n in self.graph_client.nodes.values()
            if (n.properties.get("is_suspect", False) or n.properties.get("is_tainted", False))
            and (n.role != NodeRole.DECISION or _can_decision_propagate(n))
        ]
        # Strict BFS ordering: lowest hops first, then deterministic node_id tie-breaker
        active_nodes.sort(key=lambda n: (n.properties.get("taint_hops", 0), n.node_id))

        target_hop: Optional[int] = None
        for node in active_nodes:
            curr_id = node.node_id
            curr_hops = node.properties.get("taint_hops", 0)
            if target_hop is not None and curr_hops > target_hop:
                break
            curr_path = node.properties.get("taint_via_path") or [curr_id]
            out_edges = self.graph_client.get_outgoing_edges(curr_id)
            in_edges = self.graph_client.get_incoming_edges(curr_id)

            # Deterministic edge sorting
            out_edges.sort(key=lambda e: (e.role.value if hasattr(e.role, 'value') else str(e.role), e.target_id))
            in_edges.sort(key=lambda e: (e.role.value if hasattr(e.role, 'value') else str(e.role), e.source_id))

            # Prioritize direct forward supply chain edges before lateral links
            prio = {EdgeRole.SUPPORT: 1, EdgeRole.SHIPS_IN: 2, EdgeRole.DELIVERED_TO: 3}
            out_edges.sort(key=lambda e: (prio.get(e.role, 9), e.target_id))
            in_edges.sort(key=lambda e: (1 if e.role == EdgeRole.DERIVES_FROM else 2, e.source_id))

            untraced_targets: List[str] = []

            # 1. Primary forward supply-chain edges (Evidence->Decision, Decision->Unit, Unit->Shipment, Shipment->Recipient)
            for edge in out_edges:
                if edge.role in (EdgeRole.SUPPORT, EdgeRole.SHIPS_IN, EdgeRole.DELIVERED_TO):
                    if not self._is_already_tainted(edge.target_id):
                        if edge.target_id not in untraced_targets:
                            untraced_targets.append(edge.target_id)

            # 2. Primary inward edges (DERIVES_FROM)
            for edge in in_edges:
                if edge.role == EdgeRole.DERIVES_FROM:
                    derived_unit_id = edge.source_id
                    if not self._is_already_tainted(derived_unit_id):
                        if derived_unit_id not in untraced_targets:
                            untraced_targets.append(derived_unit_id)

            # 3. Secondary lateral crossover links (Unit<->Unit) resolved dynamically from ontology
            if self.allow_lateral:
                from engine.ontology_utils import get_lateral_edge_spec
                lat_kind, lat_role_val = get_lateral_edge_spec()
                for edge in out_edges:
                    e_role_str = edge.role.value if hasattr(edge.role, 'value') else str(edge.role)
                    if e_role_str == lat_role_val or edge.kind == lat_kind:
                        if not self._is_already_tainted(edge.target_id):
                            if edge.target_id not in untraced_targets:
                                untraced_targets.append(edge.target_id)
                for edge in in_edges:
                    e_role_str = edge.role.value if hasattr(edge.role, 'value') else str(edge.role)
                    if e_role_str == lat_role_val or edge.kind == lat_kind:
                        lateral_unit_id = edge.source_id
                        if not self._is_already_tainted(lateral_unit_id):
                            if lateral_unit_id not in untraced_targets:
                                untraced_targets.append(lateral_unit_id)

            if untraced_targets:
                if target_hop is None:
                    target_hop = curr_hops
                work_items.append(
                    WorkItem(
                        item_id=f"work-trace-{curr_id}",
                        entity_id=curr_id,
                        role=node.role.value,
                        properties={
                            "source_node_id": curr_id,
                            "untraced_targets": untraced_targets,
                            "hops": curr_hops,
                            "via_path": curr_path,
                        },
                    )
                )

        return work_items

    def process_item(self, item: WorkItem) -> List[EventEnvelope]:
        """Advance taint by one hop to untraced targets, writing TAINTS edges."""
        self.current_phase = "tracer_propagate_taint"
        emitted_events: List[EventEnvelope] = []
        source_id = item.entity_id
        current_hops = item.properties.get("hops", 0)
        current_path = item.properties.get("via_path", [source_id])
        untraced_targets = item.properties.get("untraced_targets", [])

        for target_id in untraced_targets:
            self.current_query = f"MATCH (a {{id: '{source_id}'}}), (b {{id: '{target_id}'}}) MERGE (a)-[r:TAINTS]->(b);"
            # Double check to prevent race conditions or duplicate hops
            if self._is_already_tainted(target_id):
                continue

            target_node = self.graph_client.get_node(target_id)
            if not target_node:
                continue

            from engine.ontology_utils import get_lateral_edge_spec
            lat_kind, lat_role_val = get_lateral_edge_spec()
            is_lateral = False
            if hasattr(self.graph_client, "get_outgoing_edges"):
                for e in self.graph_client.get_outgoing_edges(source_id):
                    e_role_str = e.role.value if hasattr(e.role, 'value') else str(e.role)
                    if (e_role_str == lat_role_val or e.kind == lat_kind) and e.target_id == target_id:
                        is_lateral = True
                        break
            if not is_lateral and hasattr(self.graph_client, "get_incoming_edges"):
                for e in self.graph_client.get_incoming_edges(source_id):
                    e_role_str = e.role.value if hasattr(e.role, 'value') else str(e.role)
                    if (e_role_str == lat_role_val or e.kind == lat_kind) and e.source_id == target_id:
                        is_lateral = True
                        break

            new_hops = current_hops + 1
            # Demand 2: Build via_path from the actual traversal result
            new_path = list(current_path) + [target_id]

            # Write TAINTS edge to graph with required hops and via_path properties
            if hasattr(self.graph_client, "write_taints_edge"):
                self.graph_client.write_taints_edge(
                    source_id=source_id,
                    target_id=target_id,
                    hops=new_hops,
                    via_path=new_path,
                )
            else:
                self.graph_client.add_edge(
                    source_id=source_id,
                    target_id=target_id,
                    kind="TAINTS",
                    role=EdgeRole.TAINTS,
                    properties={"hops": new_hops, "via_path": new_path},
                )

            # Update target node in graph
            if hasattr(self.graph_client, "update_node"):
                self.graph_client.update_node(
                    target_id,
                    {
                        "is_tainted": True,
                        "taint_hops": new_hops,
                        "taint_via_path": new_path,
                        "taint_source": source_id,
                    },
                )

            # Emit taint.added event
            evt_taint = self.create_event(
                event_type=EventType.TAINT_ADDED,
                entity_ids=[source_id, target_id],
                payload={
                    "source_id": source_id,
                    "target_id": target_id,
                    "target_kind": target_node.kind,
                    "target_role": target_node.role.value,
                    "hops": new_hops,
                    "via_path": new_path,
                    "is_lateral": is_lateral,
                },
            )
            emitted_events.append(evt_taint)

        return emitted_events
