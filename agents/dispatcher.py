"""Dispatcher Agent (Part B, Phase B3).

Creates Action nodes in the graph based on adjudicated decisions.
Strict adherence to Section 0 rules:
- Rule 7: Every action has a stored path. Every hold, release, notice and escalation
  must be retrievable with its causal path from the graph. Never generate afterwards.
- Draft notice requires human approval (requires_approval = True).
- Idempotent and restart-safe: Work queue is a query for undispatched adjudicated decisions.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from agents.base import BaseAgent, WorkItem
from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType
from agents.llm_adapter import LLMAdapterProtocol, StubLLMAdapter


class DispatcherAgent(BaseAgent):
    """Dispatcher agent creating Action nodes with stored causal paths."""

    def __init__(
        self,
        tenant_id: str,
        graph_client: Any,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        name: str = "Dispatcher",
    ):
        super().__init__(
            name=name,
            tenant_id=tenant_id,
            graph_client=graph_client,
            llm_adapter=llm_adapter or StubLLMAdapter(),
        )

    def poll_work(self) -> List[WorkItem]:
        """Poll graph for adjudicated Decision nodes that have not yet had actions dispatched."""
        work_items: List[WorkItem] = []
        if not hasattr(self.graph_client, "nodes"):
            return work_items

        for node in self.graph_client.nodes.values():
            if node.role == NodeRole.DECISION:
                verdict_set = node.properties.get("verdict_set", False)
                action_dispatched = node.properties.get("action_dispatched", False)
                if verdict_set and not action_dispatched:
                    work_items.append(
                        WorkItem(
                            item_id=f"work-disp-{node.node_id}",
                            entity_id=node.node_id,
                            role=node.role.value,
                            properties=dict(node.properties),
                        )
                    )
        return work_items

    def process_item(self, item: WorkItem) -> List[EventEnvelope]:
        """Create Action nodes in graph with stored causal paths and emit SSE events."""
        emitted_events: List[EventEnvelope] = []
        decision_id = item.entity_id
        decision_props = item.properties
        verdict = decision_props.get("verdict", "tainted")

        # Causal path of decision
        causal_path = decision_props.get("taint_via_path", [decision_id])

        # Identify governed units (outgoing/incoming edges), deduplicated
        governed_units: List[str] = []
        if hasattr(self.graph_client, "get_outgoing_edges"):
            for edge in self.graph_client.get_outgoing_edges(decision_id):
                target = self.graph_client.get_node(edge.target_id)
                if target and target.role == NodeRole.UNIT and edge.target_id not in governed_units:
                    governed_units.append(edge.target_id)
        if hasattr(self.graph_client, "get_incoming_edges"):
            for edge in self.graph_client.get_incoming_edges(decision_id):
                source = self.graph_client.get_node(edge.source_id)
                if source and source.role == NodeRole.UNIT and edge.source_id not in governed_units:
                    governed_units.append(edge.source_id)


        target_entities = governed_units if governed_units else [decision_id]

        for target_id in target_entities:
            if target_id == decision_id or (causal_path and causal_path[-1] == target_id):
                unit_path = list(causal_path)
            else:
                unit_path = list(causal_path) + [target_id]


            if verdict == "reaffirmed":
                # Release action
                action_id = f"act-release-{target_id}"
                self._persist_action(
                    action_id=action_id,
                    action_kind="release_unit",
                    target_id=target_id,
                    causal_path=unit_path,
                    requires_approval=False,
                    reason_code="INDEPENDENT_SUPPORT_VERIFIED",
                    details={"independent_groups": decision_props.get("independent_groups_count")},
                )
                emitted_events.append(
                    self._create_action_event(
                        action_id=action_id,
                        action_kind="release_unit",
                        target_id=target_id,
                        causal_path=unit_path,
                        requires_approval=False,
                    )
                )

            elif verdict == "unverifiable":
                # Escalation action (requires human input)
                action_id = f"act-escalate-{target_id}"
                human_q = decision_props.get("human_question", "Missing verifiable records")
                self._persist_action(
                    action_id=action_id,
                    action_kind="escalate_human",
                    target_id=target_id,
                    causal_path=unit_path,
                    requires_approval=True,
                    reason_code="UNVERIFIABLE_EVIDENCE",
                    details={"human_question": human_q},
                )
                emitted_events.append(
                    self._create_action_event(
                        action_id=action_id,
                        action_kind="escalate_human",
                        target_id=target_id,
                        causal_path=unit_path,
                        requires_approval=True,
                        draft_content=human_q,
                    )
                )

            else:
                # Tainted: Hold action
                action_id = f"act-hold-{target_id}"
                self._persist_action(
                    action_id=action_id,
                    action_kind="hold_unit",
                    target_id=target_id,
                    causal_path=unit_path,
                    requires_approval=False,
                    reason_code="TAINT_CONFIRMED",
                    details={},
                )
                emitted_events.append(
                    self._create_action_event(
                        action_id=action_id,
                        action_kind="hold_unit",
                        target_id=target_id,
                        causal_path=unit_path,
                        requires_approval=False,
                    )
                )

                # Check exposure for outbound shipments/recipients
                if hasattr(self.graph_client, "exposure"):
                    exp_res = self.graph_client.exposure(target_id)
                    for exp in exp_res.data.exposures:
                        if exp.recipient_id:
                            # Notice action: Rule: Draft notice REQUIRES human approval
                            notice_id = f"act-notice-{exp.recipient_id}-{target_id}"
                            notice_path = unit_path + [exp.shipment_id or "", exp.recipient_id]
                            causal_summary = " -> ".join([str(p) for p in notice_path if p])

                            draft_copy = ""
                            if self.llm_adapter:
                                draft_copy = self.llm_adapter.draft_notice_text(
                                    target_role=NodeRole.RECIPIENT.value,
                                    target_id=exp.recipient_id,
                                    causal_summary=causal_summary,
                                )

                            self._persist_action(
                                action_id=notice_id,
                                action_kind="draft_notice",
                                target_id=exp.recipient_id,
                                causal_path=notice_path,
                                requires_approval=True,  # STRICT REQUIREMENT
                                reason_code="EXPOSURE_DETECTED",
                                details={
                                    "unit_id": target_id,
                                    "shipment_id": exp.shipment_id,
                                    "draft_content": draft_copy,
                                    "status": "pending_approval",
                                },
                            )
                            emitted_events.append(
                                self._create_action_event(
                                    action_id=notice_id,
                                    action_kind="draft_notice",
                                    target_id=exp.recipient_id,
                                    causal_path=notice_path,
                                    requires_approval=True,
                                    draft_content=draft_copy,
                                )
                            )

        # Mark decision as dispatched in graph for idempotency
        if hasattr(self.graph_client, "update_node"):
            self.graph_client.update_node(decision_id, {"action_dispatched": True})

        return emitted_events

    def _persist_action(
        self,
        action_id: str,
        action_kind: str,
        target_id: str,
        causal_path: List[str],
        requires_approval: bool,
        reason_code: str,
        details: Dict[str, Any],
    ) -> None:
        """Persists Action node in graph with causal path (Rule 7)."""
        if not hasattr(self.graph_client, "add_node"):
            return

        props = {
            "action_kind": action_kind,
            "target_entity_id": target_id,
            "causal_path": causal_path,
            "path_hops": max(0, len(causal_path) - 1),
            "requires_approval": requires_approval,
            "reason_code": reason_code,
            "approved": False if requires_approval else True,
        }
        props.update(details)

        self.graph_client.add_node(
            node_id=action_id,
            kind=action_kind,
            role=NodeRole.ACTION,
            properties=props,
        )
        # Avoid duplicate APPLIES_TO edges
        has_edge = any(
            e.source_id == action_id and e.target_id == target_id and e.role == EdgeRole.SUPPORT
            for e in self.graph_client.edges
        )
        if not has_edge:
            self.graph_client.add_edge(
                source_id=action_id,
                target_id=target_id,
                kind="APPLIES_TO",
                role=EdgeRole.SUPPORT,
            )


    def _create_action_event(
        self,
        action_id: str,
        action_kind: str,
        target_id: str,
        causal_path: List[str],
        requires_approval: bool,
        draft_content: Optional[str] = None,
    ) -> EventEnvelope:
        return self.create_event(
            event_type=EventType.ACTION_CREATED,
            entity_ids=[action_id, target_id],
            payload={
                "action_id": action_id,
                "action_kind": action_kind,
                "target_entity_id": target_id,
                "causal_path": causal_path,
                "requires_approval": requires_approval,
                "draft_content": draft_content,
            },
        )
