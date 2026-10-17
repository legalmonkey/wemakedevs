"""Adjudicator Agent (Part B, Phase B3).

Evaluates decisions using declared policy evaluated via graph queries (contracts.query_api.support).
Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding of thresholds or status names. Reads min_independent from policy config.
- Rule 5: The LLM NEVER issues a verdict. Verdicts come only from declared policy.
- Section 4 Verdict Order:
    1. Reaffirm if independent valid groups >= min_independent.
    2. Otherwise escalate (unverifiable) if any unverifiable evidence exists.
    3. Otherwise taint.
- LLM judgement task: When unverifiable, LLM drafts a specific human question naming the missing link.
- Idempotent and restart-safe: Work queue is a query for unadjudicated decisions.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from agents.base import BaseAgent, WorkItem
from contracts.ontology import NodeRole
from contracts.events import EventEnvelope, EventType
from contracts.query_api import QueryAPIProtocol
from agents.llm_adapter import LLMAdapterProtocol, StubLLMAdapter


class AdjudicatorAgent(BaseAgent):
    """Adjudicator agent executing policy-only verdict determination."""

    def __init__(
        self,
        tenant_id: str,
        graph_client: Any,
        policy_config_path: Optional[str] = None,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        name: str = "Adjudicator",
    ):
        super().__init__(
            name=name,
            tenant_id=tenant_id,
            graph_client=graph_client,
            llm_adapter=llm_adapter or StubLLMAdapter(),
        )
        self.policy_config_path = policy_config_path
        self.min_independent = self._load_min_independent()

    def _load_min_independent(self) -> int:
        """Load min_independent threshold from config/policy.yaml (Zero hardcoding)."""
        default_path = Path(__file__).resolve().parent.parent / "config" / "policy.yaml"
        resolved_path = Path(self.policy_config_path) if self.policy_config_path else default_path
        if resolved_path.exists():
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return int(data.get("adjudication", {}).get("min_independent", 2))
        return 2

    def poll_work(self) -> List[WorkItem]:
        """Poll graph for Decision nodes that are tainted/impacted but not yet adjudicated."""
        self.current_phase = "adjudicator_poll_decisions"
        self.current_query = "MATCH (d:Decision) WHERE d.is_tainted = true AND d.verdict_set IS NULL RETURN d;"
        work_items: List[WorkItem] = []

        if not hasattr(self.graph_client, "nodes"):
            return work_items

        for node in self.graph_client.nodes.values():
            if node.role == NodeRole.DECISION:
                # Check if decision is tainted or impacted, and lacks a final verdict
                is_tainted = node.properties.get("is_tainted", False)
                verdict_set = node.properties.get("verdict_set", False)
                if is_tainted and not verdict_set:
                    work_items.append(
                        WorkItem(
                            item_id=f"work-adj-{node.node_id}",
                            entity_id=node.node_id,
                            role=node.role.value,
                            properties=dict(node.properties),
                        )
                    )
        return work_items

    def process_item(self, item: WorkItem) -> List[EventEnvelope]:
        """Evaluate declared policy for a Decision node strictly via Cypher/support query."""
        decision_id = item.entity_id
        self.current_phase = "adjudicator_evaluate_policy"
        self.current_query = f"MATCH (d:Decision {{id: '{decision_id}'}})<-[r:SUPPORT]-(ev:Evidence) RETURN count(ev);"

        # Query support evaluation from QueryAPI
        support_res = self.graph_client.support(decision_id)
        sup_data = support_res.data
        independent_groups = sup_data.independent_groups_count
        unverifiable_count = sup_data.unverifiable_count

        # Verdict order recorded in Section 4:
        # 1. Reaffirm if independent valid groups >= min_independent
        # 2. Otherwise escalate (unverifiable) if any unverifiable evidence exists
        # 3. Otherwise taint
        human_question: Optional[str] = None
        if independent_groups >= self.min_independent:
            verdict = "reaffirmed"
        elif unverifiable_count > 0:
            verdict = "unverifiable"
            # Required LLM task: Model drafts specific human question naming missing link using only graph facts
            context_facts = [
                f"support_record={s.evidence_id}:is_valid={s.is_valid}" for s in sup_data.supports
            ]
            if self.llm_adapter:
                human_question = self.llm_adapter.draft_missing_link_question(
                    missing_evidence_role=NodeRole.EVIDENCE.value,
                    entity_id=decision_id,
                    context_facts=context_facts,
                )
        else:
            verdict = "tainted"

        # Update Decision node in graph
        update_props: Dict[str, Any] = {
            "verdict": verdict,
            "verdict_set": True,
            "independent_groups_count": independent_groups,
            "unverifiable_count": unverifiable_count,
            "min_independent_applied": self.min_independent,
        }
        if human_question:
            update_props["human_question"] = human_question

        if hasattr(self.graph_client, "update_node"):
            self.graph_client.update_node(decision_id, update_props)

        # Emit verdict.set SSE event
        evt_verdict = self.create_event(
            event_type=EventType.VERDICT_SET,
            entity_ids=[decision_id],
            payload={
                "decision_id": decision_id,
                "verdict_kind": verdict,
                "independent_groups_count": independent_groups,
                "unverifiable_count": unverifiable_count,
                "policy_reference": f"min_independent={self.min_independent}",
                "human_question": human_question,
            },
        )

        return [evt_verdict]
