"""Query API Contract (Section 4.2).

Python functions returning typed results for Part A, B, and C integration.
Every call returns rendered query text and result size for UI query log.
Kinds only; zero domain values or hardcoded entity names.
"""

from __future__ import annotations
from typing import Any, Dict, Generic, List, Optional, Protocol, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class QueryResult(BaseModel, Generic[T]):
    """Wrapper returned by every query API call with telemetry."""
    data: T
    query_text: str = Field(description="Rendered Cypher query string")
    result_size: int = Field(ge=0, description="Number of records returned")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Query execution duration")


# --- Trace ---
class TraceEntity(BaseModel):
    entity_id: str
    entity_kind: str
    role: str
    hops: int = Field(ge=0)
    via_path: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class TraceResult(BaseModel):
    event_id: str
    tainted_entities: List[TraceEntity] = Field(default_factory=list)


# --- Support ---
class SupportRecord(BaseModel):
    evidence_id: str
    evidence_kind: str
    is_valid: bool
    group_id: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class SupportResult(BaseModel):
    decision_id: str
    supports: List[SupportRecord] = Field(default_factory=list)
    independent_groups_count: int = Field(ge=0)
    unverifiable_count: int = Field(ge=0)


# --- Siblings ---
class SiblingsResult(BaseModel):
    unit_id: str
    sibling_unit_ids: List[str] = Field(default_factory=list)
    shared_parent_id: Optional[str] = None


# --- Exposure ---
class ExposureRecord(BaseModel):
    unit_id: str
    shipment_id: Optional[str] = None
    recipient_id: Optional[str] = None
    status: str = Field(description="Current exposure/delivery status")
    properties: Dict[str, Any] = Field(default_factory=dict)


class ExposureResult(BaseModel):
    unit_id: str
    exposures: List[ExposureRecord] = Field(default_factory=list)


# --- Explain ---
class ExplainResult(BaseModel):
    action_id: str
    causal_path: List[str] = Field(default_factory=list)
    path_hops: int = Field(ge=0)
    reason_code: str
    details: Dict[str, Any] = Field(default_factory=dict)


# --- Gate Evaluation ---
class GateEvaluationResult(BaseModel):
    tool_name: str
    allowed: bool
    reason: str
    evaluated_params: Dict[str, Any] = Field(default_factory=dict)


# --- Algorithm: Shortest Path ---
class ShortestPathResult(BaseModel):
    source_id: str
    target_id: str
    path_node_ids: List[str] = Field(default_factory=list)
    path_edge_kinds: List[str] = Field(default_factory=list)
    length: int = Field(ge=0)


# --- Algorithm: Centrality ---
class CentralityScore(BaseModel):
    entity_id: str
    score: float
    rank: int = Field(ge=1)


class CentralityResult(BaseModel):
    scope: str
    scores: List[CentralityScore] = Field(default_factory=list)


# --- Algorithm: Connected Components ---
class ComponentsResult(BaseModel):
    scope: str
    components: List[List[str]] = Field(default_factory=list)


class QueryAPIProtocol(Protocol):
    """Protocol for the Query API service provided by Part A."""

    def trace(self, event: str) -> QueryResult[TraceResult]:
        """Trace from retracted fact/event through graph."""
        ...

    def support(self, decision: str) -> QueryResult[SupportResult]:
        """Evaluate evidence groups supporting a decision."""
        ...

    def siblings(self, unit: str) -> QueryResult[SiblingsResult]:
        """Find units that share common derivation lots."""
        ...

    def exposure(self, unit: str) -> QueryResult[ExposureResult]:
        """Find shipments and recipients exposed to a tainted unit."""
        ...

    def explain(self, action: str) -> QueryResult[ExplainResult]:
        """Retrieve stored causal path behind an action."""
        ...

    def evaluate_gate(self, tool: str, params: Dict[str, Any]) -> QueryResult[GateEvaluationResult]:
        """Evaluate parameterised Cypher gate for tool availability."""
        ...

    def algo_shortest_path(self, a: str, b: str) -> QueryResult[ShortestPathResult]:
        """Find shortest path between two nodes for chain-of-custody."""
        ...

    def algo_centrality(self, scope: str) -> QueryResult[CentralityResult]:
        """Compute centrality scores for chokepoint identification."""
        ...

    def algo_components(self, scope: str) -> QueryResult[ComponentsResult]:
        """Compute connected components for incident clusters."""
        ...
