"""Ontology introspection utilities (Section 0 Rule 3 & Demand 2).

Reads ontology.yaml dynamically to extract domain edge kinds and roles,
ensuring zero hardcoding of pack-specific literals in code.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import yaml

from contracts.ontology import EdgeRole


def get_lateral_edge_spec(ontology_path: Optional[Path] = None) -> Tuple[str, str]:
    """Retrieves the lateral edge kind and role string declared in ontology.yaml.
    
    Returns:
        (kind, role_value) tuple as declared in ontology.yaml
    """
    if ontology_path is None:
        ontology_path = Path(__file__).resolve().parent.parent / "packs" / "food" / "ontology.yaml"
        if not ontology_path.exists():
            ontology_path = Path(__file__).resolve().parent.parent / "config" / "ontology.yaml"

    with open(ontology_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    for edge in data.get("edges", []):
        if edge.get("role") == "lateral-link":
            return str(edge.get("kind")), str(edge.get("role"))

    raise ValueError(f"No edge with role 'lateral-link' declared in {ontology_path}")
