"""Registry Contract (Section 4.4).

Contract between Part A (registry source) and Part C (UI consumer).
Returns statuses, domain vocabulary, and ontology-derived node presentation.
Colours exist ONLY in the token file referenced by ink_token.
Kinds only; zero domain values or hardcoded entity names.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StatusDefinition(BaseModel):
    """Status definition served to UI for dynamic rendering."""
    id: str = Field(description="Internal status identifier")
    label: str = Field(description="Human readable status label")
    stamp_text: str = Field(description="Forensic stamp text (e.g. REAFFIRMED, TAINTED)")
    ink_token: str = Field(description="Design system token name, NEVER raw hex colour")


class VocabularyDefinition(BaseModel):
    """Vocabulary mapping generic ontology roles to domain pack terminology."""
    role: str = Field(description="Generic ontology role name (e.g. Unit, Evidence)")
    domain_term: str = Field(description="Pack domain singular term")
    plural_term: str = Field(description="Pack domain plural term")
    description: Optional[str] = Field(default=None, description="Domain context explanation")


class NodePresentationDefinition(BaseModel):
    """Dynamic presentation metadata for node kinds in the UI canvas."""
    kind: str = Field(description="Node kind identifier")
    role: str = Field(description="Generic node role")
    label_property: str = Field(description="Node property to display as primary label")
    sub_label_property: Optional[str] = Field(default=None, description="Optional property for secondary label")
    badge_token: Optional[str] = Field(default=None, description="Visual badge token name")


class RegistryResponse(BaseModel):
    """Response returned by GET /api/registry."""
    statuses: List[StatusDefinition] = Field(default_factory=list)
    vocabulary: Dict[str, VocabularyDefinition] = Field(default_factory=dict)
    node_presentations: Dict[str, NodePresentationDefinition] = Field(default_factory=dict)
