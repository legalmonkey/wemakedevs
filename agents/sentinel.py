"""Sentinel Agent (Part B, Phase B1).

Detects or ingests incoming retracted facts / calibration drift / alerts in the graph.
Flags affected Evidence as suspect, marks Event as processed, and emits SSE events:
- event.received
- evidence.suspect

Strict adherence to Section 0 rules:
- Zero domain hardcoding (operates on generic NodeRole.EVENT and NodeRole.EVIDENCE).
- Graph is the only shared state.
- Idempotent and restart-safe.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from agents.base import BaseAgent, WorkItem
from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType
from contracts.query_api import QueryAPIProtocol


class SentinelAgent(BaseAgent):
    """Sentinel agent monitoring the graph for unhandled Event nodes."""

    def __init__(
        self,
        tenant_id: str,
        graph_client: Any,
        name: str = "Sentinel",
    ):
        super().__init__(name=name, tenant_id=tenant_id, graph_client=graph_client)

    def poll_work(self) -> List[WorkItem]:
        """Poll graph for unprocessed Event nodes via query."""
        work_items: List[WorkItem] = []

        if hasattr(self.graph_client, "find_nodes_by_role"):
            event_nodes = self.graph_client.find_nodes_by_role(
                NodeRole.EVENT, filters={"processed": False}
            )
            for node in event_nodes:
                work_items.append(
                    WorkItem(
                        item_id=f"work-sentinel-{node.node_id}",
                        entity_id=node.node_id,
                        role=node.role.value,
                        properties=dict(node.properties),
                    )
                )
        return work_items

    def process_item(self, item: WorkItem) -> List[EventEnvelope]:
        """Process an Event node: flag target Evidence as suspect, emit SSE events."""
        emitted_events: List[EventEnvelope] = []
        event_id = item.entity_id
        event_props = item.properties

        # Determine target evidence IDs from properties or graph edges
        target_evidence_ids: List[str] = []
        if "target_evidence_id" in event_props:
            target_evidence_ids.append(event_props["target_evidence_id"])
        elif "target_ids" in event_props and isinstance(event_props["target_ids"], list):
            target_evidence_ids.extend(event_props["target_ids"])

        # Also inspect graph edges if any already link from this event
        if hasattr(self.graph_client, "get_outgoing_edges"):
            for edge in self.graph_client.get_outgoing_edges(event_id):
                if edge.target_id not in target_evidence_ids:
                    target_evidence_ids.append(edge.target_id)

        # Emit event.received
        evt_received = self.create_event(
            event_type=EventType.EVENT_RECEIVED,
            entity_ids=[event_id] + target_evidence_ids,
            payload={
                "source_event_id": event_id,
                "event_kind": event_props.get("kind", "AlertEvent"),
                "source_node_id": target_evidence_ids[0] if target_evidence_ids else event_id,
                "details": event_props,
            },
        )
        emitted_events.append(evt_received)

        # Flag each target evidence node as suspect
        for ev_id in target_evidence_ids:
            if hasattr(self.graph_client, "update_node"):
                self.graph_client.update_node(
                    ev_id,
                    {
                        "is_suspect": True,
                        "valid": False,
                        "suspect_cause_event": event_id,
                    },
                )

            # Emit evidence.suspect
            evt_suspect = self.create_event(
                event_type=EventType.EVIDENCE_SUSPECT,
                entity_ids=[ev_id, event_id],
                payload={
                    "evidence_id": ev_id,
                    "evidence_kind": event_props.get("target_kind", "Evidence"),
                    "cause_event_id": event_id,
                    "reason": event_props.get("reason", "Retracted fact / sensor drift detected"),
                },
            )
            emitted_events.append(evt_suspect)

        # Mark event as processed in graph for idempotency
        if hasattr(self.graph_client, "update_node"):
            self.graph_client.update_node(event_id, {"processed": True})

        return emitted_events
