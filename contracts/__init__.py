"""Frozen Contracts Module (Section 4).

All inter-part contracts between Part A, Part B, and Part C.
Frozen after Hour 3. Modifications require an approved change note in docs/CONTRACT_CHANGES.md.
"""

from contracts.ontology import (
    NodeRole,
    EdgeRole,
    TaintsEdgeProperties,
    NodeKindDeclaration,
    EdgeKindDeclaration,
    OntologyDeclaration,
)

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
    GateEvaluationResult as QueryGateResult,
    ShortestPathResult,
    CentralityScore,
    CentralityResult,
    ComponentsResult,
    QueryAPIProtocol,
)

from contracts.events import (
    EventType,
    EventEnvelope,
    EventReceivedPayload,
    EvidenceSuspectPayload,
    TaintAddedPayload,
    VerdictSetPayload,
    ActionCreatedPayload,
    EpisodeClosedPayload,
    QueryRunPayload,
    AgentStatusPayload,
)

from contracts.registry import (
    StatusDefinition,
    VocabularyDefinition,
    NodePresentationDefinition,
    RegistryResponse,
)

from contracts.gates import (
    ToolGateDefinition,
    GatesConfiguration,
    GateEvaluationResult,
    GateEvaluatorProtocol,
)

__all__ = [
    # Ontology
    "NodeRole",
    "EdgeRole",
    "TaintsEdgeProperties",
    "NodeKindDeclaration",
    "EdgeKindDeclaration",
    "OntologyDeclaration",
    # Query API
    "QueryResult",
    "TraceEntity",
    "TraceResult",
    "SupportRecord",
    "SupportResult",
    "SiblingsResult",
    "ExposureRecord",
    "ExposureResult",
    "ExplainResult",
    "QueryGateResult",
    "ShortestPathResult",
    "CentralityScore",
    "CentralityResult",
    "ComponentsResult",
    "QueryAPIProtocol",
    # Events
    "EventType",
    "EventEnvelope",
    "EventReceivedPayload",
    "EvidenceSuspectPayload",
    "TaintAddedPayload",
    "VerdictSetPayload",
    "ActionCreatedPayload",
    "EpisodeClosedPayload",
    "QueryRunPayload",
    "AgentStatusPayload",
    # Registry
    "StatusDefinition",
    "VocabularyDefinition",
    "NodePresentationDefinition",
    "RegistryResponse",
    # Gates
    "ToolGateDefinition",
    "GatesConfiguration",
    "GateEvaluationResult",
    "GateEvaluatorProtocol",
]
