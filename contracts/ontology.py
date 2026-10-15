"""Ontology Contract (Section 4.1).

Node roles, edge roles, and structural schemas for ontology declarations.
Kinds only; zero domain values or hardcoded entity names.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NodeRole(str, Enum):
    """Generic node roles required by contract."""
    EVIDENCE = "Evidence"
    DECISION = "Decision"
    UNIT = "Unit"
    SHIPMENT = "Shipment"
    RECIPIENT = "Recipient"
    EVENT = "Event"
    ACTION = "Action"
    EPISODE = "Episode"
    PROCEDURE = "Procedure"


class EdgeRole(str, Enum):
    """Generic edge roles required by contract."""
    SUPPORT = "support"
    DERIVES_FROM = "derives-from"
    SHIPS_IN = "ships-in"
    DELIVERED_TO = "delivered-to"
    LATERAL_LINK = "lateral-link"
    TAINTS = "TAINTS"
    EPISODE_OUTCOME = "episode-outcome"


class TaintsEdgeProperties(BaseModel):
    """Properties required on TAINTS edges."""
    hops: int = Field(ge=0, description="Hops from retracted fact to this node")
    via_path: List[str] = Field(default_factory=list, description="Causal path of node IDs")


class NodeKindDeclaration(BaseModel):
    """Declaration of a node kind mapping to a generic role."""
    kind: str = Field(description="Domain-agnostic or pack-defined node kind")
    role: NodeRole = Field(description="Required generic role")
    properties_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema or attribute spec for this node kind"
    )


class EdgeKindDeclaration(BaseModel):
    """Declaration of an edge kind mapping to a generic role."""
    kind: str = Field(description="Domain-agnostic or pack-defined edge label")
    role: EdgeRole = Field(description="Required generic edge role")
    source_role: NodeRole = Field(description="Expected source node role")
    target_role: NodeRole = Field(description="Expected target node role")
    properties_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema or attribute spec for edge properties"
    )


class OntologyDeclaration(BaseModel):
    """Top-level ontology structure declared in config/ontology.yaml."""
    version: str = "1.0.0"
    node_kinds: List[NodeKindDeclaration] = Field(default_factory=list)
    edge_kinds: List[EdgeKindDeclaration] = Field(default_factory=list)
