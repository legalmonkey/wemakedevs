"""Event Contract (Section 4.3).

SSE event specifications emitted by Part B (agents) and consumed by Part C (API/UI).
Every event carries tenant_id, timestamp, and entity_ids.
No domain words in event type names. Kinds only.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Declared SSE event types from Section 4.3."""
    EVENT_RECEIVED = "event.received"
    EVIDENCE_SUSPECT = "evidence.suspect"
    TAINT_ADDED = "taint.added"
    VERDICT_SET = "verdict.set"
    ACTION_CREATED = "action.created"
    EPISODE_CLOSED = "episode.closed"
    QUERY_RUN = "query.run"
    AGENT_STATUS = "agent.status"


class EventEnvelope(BaseModel):
    """Common envelope for all SSE events."""
    event_id: str = Field(description="Unique event notification ID")
    event_type: EventType = Field(description="One of the declared SSE event types")
    tenant_id: str = Field(description="Tenant scope for multi-tenant isolation")
    timestamp: str = Field(description="ISO-8601 UTC timestamp")
    entity_ids: List[str] = Field(default_factory=list, description="IDs of graph entities involved")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event-specific typed data")


# Specific payload structures for consistency

class EventReceivedPayload(BaseModel):
    source_event_id: str
    event_kind: str
    source_node_id: str
    details: Dict[str, Any] = Field(default_factory=dict)


class EvidenceSuspectPayload(BaseModel):
    evidence_id: str
    evidence_kind: str
    cause_event_id: str
    reason: str


class TaintAddedPayload(BaseModel):
    source_id: str
    target_id: str
    target_kind: str
    target_role: str
    hops: int = Field(ge=0)
    via_path: List[str] = Field(default_factory=list)


class VerdictSetPayload(BaseModel):
    decision_id: str
    verdict_kind: str
    independent_groups_count: int = Field(ge=0)
    unverifiable_count: int = Field(ge=0)
    policy_reference: Optional[str] = None


class ActionCreatedPayload(BaseModel):
    action_id: str
    action_kind: str
    target_entity_id: str
    causal_path: List[str] = Field(default_factory=list)
    requires_approval: bool = True
    draft_content: Optional[str] = None


class EpisodeClosedPayload(BaseModel):
    episode_id: str
    procedure_id: Optional[str] = None
    outcome_kind: str
    summary_stats: Dict[str, Any] = Field(default_factory=dict)


class QueryRunPayload(BaseModel):
    query_name: str
    query_text: str
    result_size: int = Field(ge=0)
    duration_ms: float = Field(ge=0.0)


class AgentStatusPayload(BaseModel):
    agent_name: str
    status: str
    current_task: Optional[str] = None
    entities_processed: int = Field(default=0, ge=0)
