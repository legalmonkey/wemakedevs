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
    ):
        super().__init__(name=name, tenant_id=tenant_id, graph_client=graph_client)

    def _is_already_tainted(self, node_id: str) -> bool:
        """Check if a node has already been tainted or is suspect evidence."""
        node = self.graph_client.get_node(node_id)
        if node and node.properties.get("is_tainted", False):
            return True
        for edge in self.graph_client.edges:
            if edge.target_id == node_id and edge.role == EdgeRole.TAINTS:
                return True
        return False

    def poll_work(self) -> List[WorkItem]:
        """Poll graph for nodes that are suspect or tainted and have untainted downstream neighbors."""
        work_items: List[WorkItem] = []
        if not hasattr(self.graph_client, "nodes") or not hasattr(self.graph_client, "edges"):
            return work_items

        # Nodes that are suspect or tainted can propagate downstream
        active_nodes = [
            n for n in self.graph_client.nodes.values()
            if n.properties.get("is_suspect", False) or n.properties.get("is_tainted", False)
        ]

        for node in active_nodes:
            curr_id = node.node_id
            out_edges = self.graph_client.get_outgoing_edges(curr_id)
            in_edges = self.graph_client.get_incoming_edges(curr_id)

            untraced_targets: List[str] = []

            # 1. Forward domain edges:
            # - SUPPORT: Evidence -> Decision, or Decision -> Unit
            # - SHIPS_IN: Unit -> Shipment
            # - DELIVERED_TO: Shipment -> Recipient
            # - LATERAL_LINK: Unit -> Unit
            for edge in out_edges:
                if edge.role in (EdgeRole.SUPPORT, EdgeRole.SHIPS_IN, EdgeRole.DELIVERED_TO, EdgeRole.LATERAL_LINK):
                    if not self._is_already_tainted(edge.target_id):
                        if edge.target_id not in untraced_targets:
                            untraced_targets.append(edge.target_id)

            # 2. Inward DERIVES_FROM edges:
            # (derived_unit)-[:derives-from]->(source_lot)
            # If curr_id is the source_lot (target of DERIVES_FROM), taint flows forward to derived_unit (source of edge)
            for edge in in_edges:
                if edge.role == EdgeRole.DERIVES_FROM:
                    derived_unit_id = edge.source_id
                    if not self._is_already_tainted(derived_unit_id):
                        if derived_unit_id not in untraced_targets:
                            untraced_targets.append(derived_unit_id)
                elif edge.role == EdgeRole.LATERAL_LINK:
                    lateral_unit_id = edge.source_id
                    if not self._is_already_tainted(lateral_unit_id):
                        if lateral_unit_id not in untraced_targets:
                            untraced_targets.append(lateral_unit_id)

            if untraced_targets:
                current_path = node.properties.get("taint_via_path")
                if not current_path:
                    current_path = [curr_id]

                work_items.append(
                    WorkItem(
                        item_id=f"work-trace-{curr_id}",
                        entity_id=curr_id,
                        role=node.role.value,
                        properties={
                            "source_node_id": curr_id,
                            "untraced_targets": untraced_targets,
                            "hops": node.properties.get("taint_hops", 0),
                            "via_path": current_path,
                        },
                    )
                )

        return work_items

    def process_item(self, item: WorkItem) -> List[EventEnvelope]:
        """Advance taint by one hop to untraced targets, writing TAINTS edges."""
        emitted_events: List[EventEnvelope] = []
        source_id = item.entity_id
        current_hops = item.properties.get("hops", 0)
        current_path = item.properties.get("via_path", [source_id])
        untraced_targets = item.properties.get("untraced_targets", [])

        for target_id in untraced_targets:
            # Double check to prevent race conditions or duplicate hops
            if self._is_already_tainted(target_id):
                continue

            target_node = self.graph_client.get_node(target_id)
            if not target_node:
                continue

            new_hops = current_hops + 1
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

            # Check if this hop crossed a lateral link edge
            is_lateral = False
            if hasattr(self.graph_client, "edges"):
                for e in self.graph_client.edges:
                    if e.role == EdgeRole.LATERAL_LINK:
                        if (e.source_id == source_id and e.target_id == target_id) or (e.source_id == target_id and e.target_id == source_id):
                            is_lateral = True
                            break

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
