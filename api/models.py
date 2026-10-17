"""Data models for Tainted Part C API.

Adheres strictly to Section 0 rules:
- Rule 2: Contract adherence.
- Rule 3: Zero hardcoding.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ThemeTokens(BaseModel):
    model_config = {"extra": "allow"}
    paper_base: str
    paper_sunken: str
    paper_elevated: str
    ink_primary: str
    ink_secondary: str
    ink_muted: str
    ink_border: str
    border_width: Optional[str] = None
    border_neo: Optional[str] = None
    shadow_offset: Optional[str] = None
    signal_inks: Dict[str, str]


class StatusDefinition(BaseModel):
    id: str
    label: str
    stamp_text: str
    ink_token: str
    description: Optional[str] = None


class NodePresentation(BaseModel):
    label: str
    badge: str
    shape: str


class RegistryResponse(BaseModel):
    version: str = "1.0.0"
    theme_tokens: ThemeTokens
    statuses: List[StatusDefinition]
    vocabulary: Dict[str, str]
    node_presentation: Dict[str, NodePresentation]
    role_order: Optional[List[str]] = None


class EventContractPayload(BaseModel):
    event_id: str
    event_type: str
    tenant_id: str
    timestamp: str
    entity_ids: List[str] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)


class IncidentRunRequest(BaseModel):
    seed: Optional[int] = 101
    tenant_id: Optional[str] = "tenant-alpha"
    speed_ms: Optional[int] = 350


class GraphNode(BaseModel):
    id: str
    kind: str
    role: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None
    stamp_text: Optional[str] = None
    ink_token: Optional[str] = None
    badge: Optional[str] = None


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    kind: str
    role: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    is_taint: bool = False
    hops: Optional[int] = None
    is_lateral: bool = False


class GraphSnapshotResponse(BaseModel):
    tenant_id: str
    seed: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    stats: Dict[str, Any] = Field(default_factory=dict)


class WhyStep(BaseModel):
    step_number: int
    entity_id: str
    kind: str
    role: str
    description: str
    status: Optional[str] = None
    stamp_text: Optional[str] = None


class WhyPathResponse(BaseModel):
    action_id: str
    target_entity_id: str
    action_kind: str
    causal_path: List[str]
    steps: List[WhyStep]
    requires_approval: bool
    approved: bool
    draft_content: Optional[str] = None
    stored_path_verified: bool = True


class ActionApprovalRequest(BaseModel):
    action_id: str
    operator_notes: Optional[str] = None


class GateCheckRequest(BaseModel):
    tool_name: str
    entity_id: str


class GateCheckResponse(BaseModel):
    tool_name: str
    entity_id: str
    permitted: bool
    reason: str
    gate_query: str
