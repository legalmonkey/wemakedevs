"""Dynamic Cypher Query Builder derived from Ontology and Policy (Part A, Phase A2).

Generates parameterized Cypher queries dynamically from declared ontology definitions
and policy contracts without hardcoded domain values or specific node IDs.

Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding in code. Query patterns derived dynamically from ontology kinds and roles.
- Rule 4: Graph is the only shared state.
- Rule 7: Every action has a stored path.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


class QueryBuilder:
    """Constructs parameterized Cypher queries dynamically from an ontology definition."""

    def __init__(self, ontology: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> None:
        self.ontology = ontology
        self.policy = policy or {}
        self.pack_name = ontology.get("pack_name", "generic")

        # Map generic roles to domain edge kinds
        self._role_to_edge_kinds: Dict[str, List[str]] = {}
        for edge in ontology.get("edges", []):
            role = edge.get("role")
            kind = edge.get("kind")
            if role and kind:
                self._role_to_edge_kinds.setdefault(role, []).append(kind)

        # Map generic roles to domain node kinds
        self._role_to_node_kinds: Dict[str, List[str]] = {}
        for node in ontology.get("nodes", []):
            role = node.get("role")
            kind = node.get("kind")
            if role and kind:
                self._role_to_node_kinds.setdefault(role, []).append(kind)

    def _get_edge_pattern(self, *roles: str) -> str:
        """Returns Cypher relationship kind alternation string for given roles."""
        kinds = []
        for r in roles:
            kinds.extend(self._role_to_edge_kinds.get(r, []))
        if not kinds:
            # Fallback to standard generic edge roles if no specific kinds mapped
            kinds = list(roles)
        return "|".join(sorted(set(kinds)))

    def build_trace_query(self, max_hops: int = 10) -> str:
        """Builds variable-depth trace Cypher query with path variable, hops, and via_path."""
        edge_pattern = self._get_edge_pattern("support", "derives-from", "ships-in", "delivered-to", "lateral-link")
        return (
            f"MATCH path = (start {{id: $event_id}})-[:{edge_pattern}*1..{max_hops}]->(target) "
            "RETURN target.id AS entity_id, labels(target)[0] AS entity_kind, "
            "length(path) AS hops, [n IN nodes(path) | n.id] AS via_path, properties(target) AS properties"
        )

    def build_support_query(self) -> str:
        """Builds support query evaluating evidence nodes supporting a decision."""
        support_edges = self._get_edge_pattern("support")
        return (
            f"MATCH (d {{id: $decision_id}})<-[:{support_edges}]-(ev) "
            "RETURN ev.id AS evidence_id, labels(ev)[0] AS evidence_kind, "
            "ev.valid AS is_valid, ev.unverifiable AS is_unverifiable, "
            "ev.group_id AS group_id, properties(ev) AS properties"
        )

    def build_siblings_query(self) -> str:
        """Builds siblings query identifying co-derived units sharing lots or lateral links."""
        derives_edges = self._get_edge_pattern("derives-from")
        lateral_edges = self._get_edge_pattern("lateral-link")
        return (
            f"MATCH (u {{id: $unit_id}})-[:{derives_edges}]->(lot)<-[:{derives_edges}]-(sib) "
            f"WHERE sib.id <> u.id "
            f"UNION "
            f"MATCH (u {{id: $unit_id}})-[:{lateral_edges}]-(sib) "
            f"RETURN sib.id AS sibling_id, lot.id AS shared_parent_id"
        )

    def build_exposure_query(self) -> str:
        """Builds supply chain exposure query: Unit -> Shipment -> Recipient."""
        ships_edges = self._get_edge_pattern("ships-in")
        delivered_edges = self._get_edge_pattern("delivered-to")
        return (
            f"MATCH (u {{id: $unit_id}})-[:{ships_edges}]->(s)-[:{delivered_edges}]->(r) "
            "RETURN u.id AS unit_id, s.id AS shipment_id, r.id AS recipient_id, "
            "s.status AS status, properties(r) AS recipient_properties"
        )

    def build_explain_query(self) -> str:
        """Builds explain query retrieving the stored chain-of-custody path for an action."""
        return (
            "MATCH (a {id: $action_id}) "
            "RETURN a.id AS action_id, a.causal_path AS causal_path, "
            "size(a.causal_path) - 1 AS path_hops, a.reason AS reason_code, "
            "properties(a) AS details"
        )

    def build_shortest_path_query(self) -> str:
        """Builds algorithm shortest-path query between two nodes."""
        return (
            "MATCH (src {id: $source_id}), (tgt {id: $target_id}), "
            "p = shortestPath((src)-[*..15]-(tgt)) "
            "RETURN [n IN nodes(p) | n.id] AS path_node_ids, "
            "[r IN relationships(p) | type(r)] AS path_edge_kinds, "
            "length(p) AS length"
        )

    def build_centrality_query(self) -> str:
        """Builds degree centrality query to identify chokepoint lots."""
        return (
            "MATCH (n)-[r]-() "
            "RETURN n.id AS entity_id, count(r) AS degree_score "
            "ORDER BY degree_score DESC"
        )

    def build_components_query(self) -> str:
        """Builds connected components query for incident clustering."""
        return (
            "MATCH (n)-[r]-(neighbor) "
            "RETURN n.id AS entity_id, collect(DISTINCT neighbor.id) AS neighbors"
        )
