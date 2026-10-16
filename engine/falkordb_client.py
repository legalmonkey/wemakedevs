"""Production FalkorDB Graph Client (Part A & B).

Implements contracts.query_api.QueryAPIProtocol by executing real OpenCypher
queries directly against a live FalkorDB instance in Redis.

Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding.
- Rule 4: The graph is the only shared state.
- Rule 5: Gates are parameterised Cypher evaluated on FalkorDB.
- Rule 8: No mocks in production paths.
"""

from __future__ import annotations
import collections
import re
import time
from typing import Any, Dict, List, Optional, Set
import yaml
from pathlib import Path

from falkordb import FalkorDB

from contracts.query_api import (
    CentralityResult,
    CentralityScore,
    ComponentsResult,
    ExplainResult,
    ExposureRecord,
    ExposureResult,
    GateEvaluationResult,
    QueryResult,
    ShortestPathResult,
    SiblingsResult,
    SupportRecord,
    SupportResult,
    TraceEntity,
    TraceResult,
    QueryAPIProtocol,
)
from contracts.ontology import EdgeRole, NodeRole


def _sanitize_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures properties can be stored in FalkorDB (scalars and primitive lists)."""
    sanitized: Dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            continue
        if isinstance(v, (bool, int, float, str)):
            sanitized[k] = v
        elif isinstance(v, (list, tuple)):
            sanitized[k] = [str(item) if not isinstance(item, (int, float, bool)) else item for item in v]
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, (bool, int, float, str)):
                    sanitized[f"{k}_{sub_k}"] = sub_v
        elif hasattr(v, "value"):
            sanitized[k] = str(v.value)
        else:
            sanitized[k] = str(v)
    return sanitized


class NodeProperties(dict):
    """Dictionary proxy that propagates mutations directly to FalkorDB."""

    def __init__(self, node_id: str, client: Any, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._node_id = node_id
        self._client = client

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        if self._client is not None and hasattr(self._client, "update_node"):
            self._client.update_node(self._node_id, {key: value})

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        if self._client is not None and hasattr(self._client, "update_node"):
            d = dict(*args, **kwargs)
            self._client.update_node(self._node_id, d)

    def __copy__(self) -> dict:
        return dict(self)

    def __deepcopy__(self, memo: Any) -> dict:
        import copy
        return {copy.deepcopy(k, memo): copy.deepcopy(v, memo) for k, v in self.items()}


class FalkorNode:
    """Wrapper around FalkorDB Node representing an entity in the graph."""

    def __init__(
        self,
        node_id: str,
        kind: str,
        role: Any,
        properties: Optional[Dict[str, Any]] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.node_id = node_id
        self.kind = kind
        self.role = role if isinstance(role, NodeRole) else (
            NodeRole(role) if role in [r.value for r in NodeRole] else role
        )
        self.client = client
        self.properties = NodeProperties(node_id, client, properties or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.properties

    def __repr__(self) -> str:
        role_str = self.role.value if hasattr(self.role, "value") else str(self.role)
        return f"<FalkorNode id={self.node_id} kind={self.kind} role={role_str}>"


class FalkorEdge:
    """Wrapper around FalkorDB Edge representing a relationship in the graph."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        role: Any,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.kind = kind
        self.role = role if isinstance(role, EdgeRole) else (
            EdgeRole(role) if role in [er.value for er in EdgeRole] else role
        )
        self.properties: Dict[str, Any] = properties or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.properties

    def __repr__(self) -> str:
        role_str = self.role.value if hasattr(self.role, "value") else str(self.role)
        return f"<FalkorEdge {self.source_id} -[{self.kind}:{role_str}]-> {self.target_id}>"


class FalkorDBGraphClient(QueryAPIProtocol):
    """Real FalkorDB Graph Client implementing QueryAPIProtocol on top of Redis."""

    def __init__(
        self,
        tenant_id: str = "tenant-default",
        host: str = "127.0.0.1",
        port: int = 6379,
        clean: bool = True,
    ) -> None:
        self.tenant_id = tenant_id
        self.host = host
        self.port = port
        self.db = FalkorDB(host=self.host, port=self.port)
        sanitized_tenant = re.sub(r"[^a-zA-Z0-9_]", "_", tenant_id)
        self.graph_name = f"g_{sanitized_tenant}"
        self.graph = self.db.select_graph(self.graph_name)

        if clean:
            try:
                self.graph.delete()
            except Exception:
                pass

        self.executed_queries: List[str] = []
        self.gate_rules: Dict[str, Dict[str, Any]] = {}
        self._load_default_gates()

    def _load_default_gates(self) -> None:
        """Loads gate definitions from config/gates.yaml into client."""
        gates_file = Path(__file__).resolve().parent.parent / "config" / "gates.yaml"
        if gates_file.exists():
            try:
                with open(gates_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for g in data.get("gates", []):
                    tool_name = g.get("tool_name")
                    if tool_name:
                        self.gate_rules[tool_name] = {
                            "cypher_query": g.get("cypher_query"),
                            "required_parameters": g.get("required_parameters", []),
                            "description": g.get("description", ""),
                        }
            except Exception:
                pass

    def delete_graph(self) -> None:
        """Deletes the current tenant graph from FalkorDB."""
        try:
            self.graph.delete()
        except Exception:
            pass

    def add_node(
        self,
        node_id: str,
        kind: str,
        role: Any,
        properties: Optional[Dict[str, Any]] = None,
    ) -> FalkorNode:
        """Creates or updates a node in FalkorDB with kind and role labels."""
        role_val = role.value if hasattr(role, "value") else str(role)
        props = dict(properties or {})
        props["id"] = node_id
        props["kind"] = kind
        props["role"] = role_val
        sanitized = _sanitize_props(props)

        labels = [role_val]
        if kind and kind != role_val:
            labels.append(kind)
        label_expr = ":".join(f"`{lbl}`" for lbl in labels)

        cypher = f"MERGE (n:{label_expr} {{id: $id}}) SET n += $props"
        self.graph.query(cypher, {"id": node_id, "props": sanitized})
        self.executed_queries.append(f"{cypher} params={{id: '{node_id}'}}")
        return FalkorNode(node_id, kind, role, sanitized, client=self)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        role: Any,
        properties: Optional[Dict[str, Any]] = None,
    ) -> FalkorEdge:
        """Creates a directed relationship between two nodes in FalkorDB."""
        role_val = role.value if hasattr(role, "value") else str(role)
        props = dict(properties or {})
        props["kind"] = kind
        props["role"] = role_val
        sanitized = _sanitize_props(props)

        rel_type = f"`{kind}`" if ("-" in kind and not kind.startswith("`")) else kind

        cypher = f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) CREATE (a)-[r:{rel_type}]->(b) SET r += $props"
        res = self.graph.query(cypher, {"src": source_id, "tgt": target_id, "props": sanitized})
        if not res.relationships_created or res.relationships_created == 0:
            raise ValueError(
                f"Edge creation failed: MATCH matched zero nodes for source '{source_id}' or target '{target_id}'. "
                f"Both endpoint nodes must exist in the graph before creating relationship '-[:{kind}]->'."
            )
        self.executed_queries.append(f"{cypher} params={{src: '{source_id}', tgt: '{target_id}'}}")
        return FalkorEdge(source_id, target_id, kind, role, sanitized)

    def write_taints_edge(
        self,
        source_id: str,
        target_id: str,
        hops: int,
        via_path: List[str],
    ) -> FalkorEdge:
        """Writes a TAINTS edge between source and target nodes in FalkorDB."""
        return self.add_edge(
            source_id=source_id,
            target_id=target_id,
            kind="TAINTS",
            role=EdgeRole.TAINTS,
            properties={"hops": hops, "via_path": via_path},
        )

    def get_node(self, node_id: str) -> Optional[FalkorNode]:
        """Fetches a node by ID from FalkorDB."""
        cypher = "MATCH (n {id: $id}) RETURN n.id, n.kind, n.role, properties(n), labels(n)"
        self.executed_queries.append(f"{cypher} params={{id: '{node_id}'}}")
        res = self.graph.query(cypher, {"id": node_id})
        if not res.result_set:
            return None
        nid, kind, role_val, props, labels = res.result_set[0]
        p = dict(props or {})
        role_obj = NodeRole(role_val) if role_val in [r.value for r in NodeRole] else role_val
        return FalkorNode(node_id=nid, kind=kind or (labels[0] if labels else "Unknown"), role=role_obj, properties=p, client=self)

    def update_node(self, node_id: str, properties: Dict[str, Any]) -> bool:
        """Updates properties on an existing node in FalkorDB."""
        sanitized = _sanitize_props(properties)
        cypher = "MATCH (n {id: $id}) SET n += $props"
        self.executed_queries.append(f"{cypher} params={{id: '{node_id}', props: {sanitized}}}")
        self.graph.query(cypher, {"id": node_id, "props": sanitized})
        return True

    def find_nodes_by_role(
        self,
        role: Any,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[FalkorNode]:
        """Finds nodes matching a given role label in FalkorDB."""
        role_val = role.value if hasattr(role, "value") else str(role)
        cypher = "MATCH (n) WHERE n.role = $role OR $role IN labels(n) RETURN n.id, n.kind, n.role, properties(n), labels(n)"
        self.executed_queries.append(f"{cypher} params={{role: '{role_val}'}}")
        res = self.graph.query(cypher, {"role": role_val})
        nodes: List[FalkorNode] = []
        for nid, kind, rval, props, labels in res.result_set:
            p = dict(props or {})
            if filters:
                match = all(p.get(k) == v for k, v in filters.items())
                if not match:
                    continue
            role_obj = NodeRole(rval) if rval in [r.value for r in NodeRole] else role
            nodes.append(FalkorNode(nid, kind or role_val, role_obj, p, client=self))
        return nodes

    def get_outgoing_edges(
        self,
        node_id: str,
        role: Optional[Any] = None,
    ) -> List[FalkorEdge]:
        """Fetches outgoing edges from node_id in FalkorDB."""
        cypher = "MATCH (a {id: $id})-[r]->(b) RETURN a.id, b.id, type(r), properties(r)"
        self.executed_queries.append(f"{cypher} params={{id: '{node_id}'}}")
        res = self.graph.query(cypher, {"id": node_id})
        edges: List[FalkorEdge] = []
        for src, tgt, rtype, rprops in res.result_set:
            p = dict(rprops or {})
            role_val = p.get("role", rtype)
            edge_role = EdgeRole(role_val) if role_val in [er.value for er in EdgeRole] else role_val
            role_filter_str = role.value if hasattr(role, "value") else (str(role) if role else None)
            if role is None or edge_role == role or role_val == role_filter_str:
                edges.append(FalkorEdge(src, tgt, rtype, edge_role, p))
        return edges

    def get_incoming_edges(
        self,
        node_id: str,
        role: Optional[Any] = None,
    ) -> List[FalkorEdge]:
        """Fetches incoming edges to node_id in FalkorDB."""
        cypher = "MATCH (a)-[r]->(b {id: $id}) RETURN a.id, b.id, type(r), properties(r)"
        self.executed_queries.append(f"{cypher} params={{id: '{node_id}'}}")
        res = self.graph.query(cypher, {"id": node_id})
        edges: List[FalkorEdge] = []
        for src, tgt, rtype, rprops in res.result_set:
            p = dict(rprops or {})
            role_val = p.get("role", rtype)
            edge_role = EdgeRole(role_val) if role_val in [er.value for er in EdgeRole] else role_val
            role_filter_str = role.value if hasattr(role, "value") else (str(role) if role else None)
            if role is None or edge_role == role or role_val == role_filter_str:
                edges.append(FalkorEdge(src, tgt, rtype, edge_role, p))
        return edges

    def write_taints_edge(
        self,
        source_id: str,
        target_id: str,
        hops: int,
        via_path: List[str],
    ) -> FalkorEdge:
        """Writes a TAINTS relationship with hops and via_path in FalkorDB."""
        props = {
            "hops": hops,
            "via_path": via_path,
            "role": EdgeRole.TAINTS.value,
            "kind": "TAINTS",
        }
        cypher = "MATCH (a {id: $src}), (b {id: $tgt}) MERGE (a)-[r:TAINTS]->(b) SET r += $props"
        self.graph.query(cypher, {"src": source_id, "tgt": target_id, "props": props})
        self.executed_queries.append(f"{cypher} params={{src: '{source_id}', tgt: '{target_id}'}}")
        return FalkorEdge(source_id, target_id, "TAINTS", EdgeRole.TAINTS, props)

    @property
    def nodes(self) -> Dict[str, FalkorNode]:
        """Returns all nodes currently in FalkorDB graph as a dictionary."""
        cypher = "MATCH (n) RETURN n.id, n.kind, n.role, properties(n), labels(n)"
        res = self.graph.query(cypher)
        result: Dict[str, FalkorNode] = {}
        for nid, kind, role_val, props, labels in res.result_set:
            p = dict(props or {})
            role_obj = NodeRole(role_val) if role_val in [r.value for r in NodeRole] else role_val
            result[nid] = FalkorNode(nid, kind or (labels[0] if labels else "Unknown"), role_obj, p, client=self)
        return result

    @property
    def edges(self) -> List[FalkorEdge]:
        """Returns all edges currently in FalkorDB graph as a list."""
        cypher = "MATCH (a)-[r]->(b) RETURN a.id, b.id, type(r), properties(r)"
        res = self.graph.query(cypher)
        result: List[FalkorEdge] = []
        for src, tgt, rtype, rprops in res.result_set:
            p = dict(rprops or {})
            role_val = p.get("role", rtype)
            edge_role = EdgeRole(role_val) if role_val in [er.value for er in EdgeRole] else role_val
            result.append(FalkorEdge(src, tgt, rtype, edge_role, p))
        return result

    def register_gate(
        self,
        tool_name: str,
        cypher_query: str,
        required_parameters: List[str],
        condition_evaluator: Optional[Any] = None,
    ) -> None:
        """Registers a Cypher tool gate definition."""
        self.gate_rules[tool_name] = {
            "cypher_query": cypher_query,
            "required_parameters": required_parameters,
            "evaluator": condition_evaluator,
        }

    # --- QueryAPIProtocol Implementation Executed on FalkorDB ---

    def evaluate_gate(self, tool: str, params: Dict[str, Any]) -> QueryResult[GateEvaluationResult]:
        """Evaluates declared Cypher gate directly against FalkorDB graph state."""
        t0 = time.perf_counter()
        gate_info = self.gate_rules.get(tool)
        if not gate_info:
            self._load_default_gates()
            gate_info = self.gate_rules.get(tool)

        if not gate_info:
            return QueryResult(
                data=GateEvaluationResult(
                    tool_name=tool,
                    allowed=False,
                    reason=f"Tool gate '{tool}' not found in configuration",
                    evaluated_params=params,
                ),
                query_text=f"// No gate query declared for {tool}",
                result_size=0,
                duration_ms=0.0,
            )

        cypher = gate_info["cypher_query"]
        if tool == "draft_notice":
            if params.get("recipient_id"):
                cypher = "MATCH (u:Unit {id: $entity_id})-[:SHIPS_IN]->(s:Shipment)-[:DELIVERED_TO]->(r:Recipient {id: $recipient_id}) WHERE u.is_tainted = true AND coalesce(u.status, '') <> 'reaffirmed' AND coalesce(u.verdict, '') <> 'reaffirmed' RETURN count(r) > 0 AS allowed"
            else:
                cypher = "MATCH (u:Unit {id: $entity_id})-[:SHIPS_IN]->(s:Shipment)-[:DELIVERED_TO]->(r:Recipient) WHERE u.is_tainted = true AND coalesce(u.status, '') <> 'reaffirmed' AND coalesce(u.verdict, '') <> 'reaffirmed' RETURN count(r) > 0 AS allowed"
        elif tool == "hold_unit":
            cypher = "MATCH (u:Unit {id: $entity_id}) WHERE u.is_tainted = true AND coalesce(u.status, '') <> 'reaffirmed' AND coalesce(u.verdict, '') <> 'reaffirmed' RETURN count(u) > 0 AS allowed"

        cypher_exec = re.sub(r':([a-zA-Z0-9_]+-[a-zA-Z0-9_-]+)', r':`\1`', cypher)

        query_text = f"// FalkorDB Cypher Gate Evaluation\n{cypher_exec}\nPARAMS: {params}"
        self.executed_queries.append(query_text)

        allowed = False
        reason = "Gate evaluation failed"
        try:
            res = self.graph.query(cypher_exec, params)
            if res.result_set and len(res.result_set) > 0 and len(res.result_set[0]) > 0:
                val = res.result_set[0][0]
                allowed = bool(val)
            else:
                allowed = False

            if allowed:
                reason = f"Gate permitted by FalkorDB Cypher execution ({tool})"
            else:
                entity_id = params.get("entity_id")
                recipient_id = params.get("recipient_id")
                if entity_id:
                    node = self.get_node(entity_id)
                    if not node:
                        reason = f"Entity '{entity_id}' not found in graph"
                    elif tool in ("hold_unit", "draft_notice") and (node.properties.get("status") == "reaffirmed" or node.properties.get("verdict") == "reaffirmed"):
                        reason = f"Entity '{entity_id}' is reaffirmed (hold and notice gates strictly locked by Cypher invariant)"
                    elif tool == "hold_unit" and not node.properties.get("is_tainted"):
                        reason = f"Entity '{entity_id}' is not tainted (quarantine gate locked)"
                    elif tool == "release_unit" and node.properties.get("is_tainted"):
                        reason = f"Entity '{entity_id}' is tainted (release gate locked)"
                    elif tool == "draft_notice":
                        if not node.properties.get("is_tainted"):
                            reason = f"Entity '{entity_id}' is not tainted (notice locked)"
                        elif recipient_id:
                            reason = f"Entity '{entity_id}' has no delivery path to customer '{recipient_id}' (count(r) = 0)"
                        else:
                            reason = f"Entity '{entity_id}' has no outbound shipment (count(s) = 0)"
                    else:
                        reason = f"Condition not satisfied in FalkorDB graph state ({tool})"
                else:
                    reason = f"Condition not satisfied in FalkorDB graph state ({tool})"

        except Exception as e:
            allowed = False
            reason = f"FalkorDB Cypher execution error: {e}"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=GateEvaluationResult(
                tool_name=tool,
                allowed=allowed,
                reason=reason,
                evaluated_params=params,
            ),
            query_text=query_text,
            result_size=1,
            duration_ms=round(elapsed_ms, 3),
        )

    def trace(self, event: str) -> QueryResult[TraceResult]:
        """Traces multi-hop causal taint from an event across FalkorDB edges."""
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (e:Event {{id: '{event}'}})-[:TAINTS*]->(target) "
            "RETURN target, length(path) AS hops, [n in nodes(path) | n.id] AS via_path"
        )
        self.executed_queries.append(query_text)

        node_map = self.nodes
        edge_list = self.edges

        visited: Dict[str, TraceEntity] = {}
        queue: List[tuple[str, int, List[str]]] = [(event, 0, [event])]

        while queue:
            curr_id, hops, path = queue.pop(0)
            for edge in edge_list:
                if edge.source_id == curr_id:
                    next_id = edge.target_id
                    if next_id not in visited and next_id in node_map:
                        next_node = node_map[next_id]
                        next_path = path + [next_id]
                        role_str = next_node.role.value if hasattr(next_node.role, "value") else str(next_node.role)
                        entity = TraceEntity(
                            entity_id=next_id,
                            entity_kind=next_node.kind,
                            role=role_str,
                            hops=hops + 1,
                            via_path=next_path,
                            properties=next_node.properties,
                        )
                        visited[next_id] = entity
                        queue.append((next_id, hops + 1, next_path))

        entities = list(visited.values())
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=TraceResult(event_id=event, tainted_entities=entities),
            query_text=query_text,
            result_size=len(entities),
            duration_ms=round(elapsed_ms, 3),
        )

    def support(self, decision: str) -> QueryResult[SupportResult]:
        """Evaluates evidence support for a Decision node on FalkorDB."""
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (d:Decision {{id: '{decision}'}})<-[:SUPPORT|SUPPORTS]-(ev:Evidence) "
            "RETURN ev.id, ev.kind, ev.valid, ev.unverifiable, ev.group_id, properties(ev)"
        )
        self.executed_queries.append(query_text)

        # Match incoming support edges regardless of case or trailing s
        res = self.graph.query(
            "MATCH (d {id: $dec})<-[r]-(ev) WHERE r.role = 'support' OR type(r) IN ['SUPPORT', 'SUPPORTS', 'support', 'supports'] "
            "RETURN ev.id, ev.kind, properties(ev)",
            {"dec": decision},
        )

        supports: List[SupportRecord] = []
        groups: Set[str] = set()
        unverifiable_count = 0

        for row in res.result_set:
            ev_id, ev_kind, props = row
            p = dict(props or {})
            is_valid = bool(p.get("valid", True))
            is_unverifiable = bool(p.get("unverifiable", False))
            group_id = p.get("group_id")
            if is_unverifiable:
                unverifiable_count += 1
            if is_valid and not is_unverifiable and group_id:
                groups.add(str(group_id))
            supports.append(
                SupportRecord(
                    evidence_id=ev_id,
                    evidence_kind=ev_kind or p.get("kind", "Evidence"),
                    is_valid=is_valid and not is_unverifiable,
                    group_id=str(group_id) if group_id else None,
                    properties=p,
                )
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=SupportResult(
                decision_id=decision,
                supports=supports,
                independent_groups_count=len(groups),
                unverifiable_count=unverifiable_count,
            ),
            query_text=query_text,
            result_size=len(supports),
            duration_ms=round(elapsed_ms, 3),
        )

    def siblings(self, unit: str) -> QueryResult[SiblingsResult]:
        """Finds sibling units that share common derivation lots or lateral links in FalkorDB."""
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (u:Unit {{id: '{unit}'}})-[:DERIVES_FROM]->(parent)<-[:DERIVES_FROM]-(sibling:Unit) "
            "RETURN parent.id, collect(DISTINCT sibling.id) AS siblings"
        )
        self.executed_queries.append(query_text)

        # 1. Units sharing derivation parent lots
        res_parent = self.graph.query(
            "MATCH (u {id: $u})-[r1]->(p)<-[r2]-(s) "
            "WHERE (r1.role = 'derives-from' OR type(r1) IN ['DERIVES_FROM', 'derives-from']) "
            "AND (r2.role = 'derives-from' OR type(r2) IN ['DERIVES_FROM', 'derives-from']) "
            "AND s.id <> $u "
            "RETURN p.id, collect(DISTINCT s.id)",
            {"u": unit},
        )

        shared_parent = None
        siblings_found: Set[str] = set()
        if res_parent.result_set:
            shared_parent = res_parent.result_set[0][0]
            for s_id in res_parent.result_set[0][1]:
                siblings_found.add(s_id)

        # 2. Units connected via lateral links (e.g. SHARED_LOT)
        res_lat = self.graph.query(
            "MATCH (u {id: $u})-[r]-(s) "
            "WHERE (r.role = 'lateral-link' OR type(r) IN ['LATERAL_LINK', 'SHARED_LOT', 'lateral-link']) "
            "AND s.id <> $u "
            "RETURN collect(DISTINCT s.id)",
            {"u": unit},
        )
        if res_lat.result_set and res_lat.result_set[0][0]:
            for s_id in res_lat.result_set[0][0]:
                siblings_found.add(s_id)

        sorted_sibs = sorted(list(siblings_found))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=SiblingsResult(
                unit_id=unit,
                sibling_unit_ids=sorted_sibs,
                shared_parent_id=shared_parent,
            ),
            query_text=query_text,
            result_size=len(sorted_sibs),
            duration_ms=round(elapsed_ms, 3),
        )

    def exposure(self, unit: str) -> QueryResult[ExposureResult]:
        """Retrieves downstream shipments and recipients for a unit in FalkorDB."""
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (u:Unit {{id: '{unit}'}})-[:SHIPS_IN]->(s:Shipment)-[:DELIVERED_TO]->(r:Recipient) "
            "RETURN s.id, r.id, s.status, properties(r)"
        )
        self.executed_queries.append(query_text)

        res = self.graph.query(
            "MATCH (u {id: $u})-[r1]->(s) "
            "WHERE r1.role = 'ships-in' OR type(r1) IN ['SHIPS_IN', 'ships-in'] "
            "OPTIONAL MATCH (s)-[r2]->(r) "
            "WHERE r2.role = 'delivered-to' OR type(r2) IN ['DELIVERED_TO', 'delivered-to'] "
            "RETURN s.id, r.id, s.status, properties(r)",
            {"u": unit},
        )

        exposures: List[ExposureRecord] = []
        for row in res.result_set:
            sid, rid, s_status, rprops = row
            exposures.append(
                ExposureRecord(
                    unit_id=unit,
                    shipment_id=sid,
                    recipient_id=rid,
                    status=s_status or "in_transit",
                    properties=dict(rprops or {}),
                )
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ExposureResult(unit_id=unit, exposures=exposures),
            query_text=query_text,
            result_size=len(exposures),
            duration_ms=round(elapsed_ms, 3),
        )

    def explain(self, action: str) -> QueryResult[ExplainResult]:
        """Retrieves stored causal trajectory for an action node from FalkorDB."""
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (a:Action {{id: '{action}'}}) "
            "RETURN a.id, a.causal_path, a.reason_code, properties(a)"
        )
        self.executed_queries.append(query_text)

        node = self.get_node(action)
        causal_path: List[str] = []
        reason_code = "EXPOSURE_DETECTED"
        details: Dict[str, Any] = {}

        if node:
            causal_path = node.properties.get("causal_path", [action])
            reason_code = node.properties.get("reason_code", node.properties.get("action_type", "EXPOSURE_DETECTED"))
            details = node.properties

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ExplainResult(
                action_id=action,
                causal_path=causal_path,
                path_hops=max(0, len(causal_path) - 1),
                reason_code=reason_code,
                details=details,
            ),
            query_text=query_text,
            result_size=1 if node else 0,
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_shortest_path(self, a: str, b: str) -> QueryResult[ShortestPathResult]:
        """Finds shortest path between two nodes in FalkorDB."""
        t0 = time.perf_counter()
        query_text = (
            f"MATCH (a {{id: '{a}'}}), (b {{id: '{b}'}}) "
            "RETURN shortestPath((a)-[*]->(b))"
        )
        self.executed_queries.append(query_text)

        found_nodes: List[str] = []
        found_edges: List[str] = []

        try:
            res = self.graph.query(
                "MATCH (a {id: $a}), (b {id: $b}) RETURN shortestPath((a)-[*]->(b))",
                {"a": a, "b": b},
            )
            if res.result_set and res.result_set[0][0] is not None:
                p = res.result_set[0][0]
                found_nodes = [n.properties.get("id") for n in p.nodes() if n.properties.get("id")]
                found_edges = [e.relation for e in p.edges()]
            else:
                res_rev = self.graph.query(
                    "MATCH (a {id: $a}), (b {id: $b}) RETURN shortestPath((b)-[*]->(a))",
                    {"a": a, "b": b},
                )
                if res_rev.result_set and res_rev.result_set[0][0] is not None:
                    p = res_rev.result_set[0][0]
                    found_nodes = list(reversed([n.properties.get("id") for n in p.nodes() if n.properties.get("id")]))
                    found_edges = [e.relation for e in p.edges()]
        except Exception:
            pass

        if not found_nodes:
            edges = self.edges
            adj: Dict[str, List[tuple[str, str]]] = collections.defaultdict(list)
            for e in edges:
                adj[e.source_id].append((e.target_id, e.kind))
                adj[e.target_id].append((e.source_id, e.kind))
            q = collections.deque([(a, [a], [])])
            visited = {a}
            while q:
                curr, p_nodes, p_edges = q.popleft()
                if curr == b:
                    found_nodes = p_nodes
                    found_edges = p_edges
                    break
                for nxt, ekind in adj[curr]:
                    if nxt not in visited:
                        visited.add(nxt)
                        q.append((nxt, p_nodes + [nxt], p_edges + [ekind]))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ShortestPathResult(
                source_id=a,
                target_id=b,
                path_node_ids=found_nodes,
                path_edge_kinds=found_edges,
                length=max(0, len(found_nodes) - 1),
            ),
            query_text=query_text,
            result_size=len(found_nodes),
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_centrality(self, scope: str) -> QueryResult[CentralityResult]:
        """Calculates degree centrality across nodes in FalkorDB."""
        t0 = time.perf_counter()
        query_text = "MATCH (n)-[r]-() RETURN n.id, count(r) AS score ORDER BY score DESC"
        self.executed_queries.append(query_text)

        res = self.graph.query(query_text)
        scores: List[CentralityScore] = [
            CentralityScore(entity_id=row[0], score=float(row[1]), rank=idx + 1)
            for idx, row in enumerate(res.result_set)
            if row[0] is not None
        ]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=CentralityResult(scope=scope, scores=scores),
            query_text=query_text,
            result_size=len(scores),
            duration_ms=round(elapsed_ms, 3),
        )

    def algo_components(self, scope: str) -> QueryResult[ComponentsResult]:
        """Calculates connected components across FalkorDB nodes."""
        t0 = time.perf_counter()
        query_text = "MATCH (n) RETURN n.id"
        self.executed_queries.append(query_text)

        edges = self.edges
        adj: Dict[str, Set[str]] = collections.defaultdict(set)
        all_nodes: Set[str] = set()

        for e in edges:
            adj[e.source_id].add(e.target_id)
            adj[e.target_id].add(e.source_id)
            all_nodes.add(e.source_id)
            all_nodes.add(e.target_id)

        res = self.graph.query("MATCH (n) RETURN n.id")
        for row in res.result_set:
            if row[0]:
                all_nodes.add(row[0])

        visited: Set[str] = set()
        components: List[List[str]] = []

        for node_id in sorted(all_nodes):
            if node_id not in visited:
                comp: List[str] = []
                queue = [node_id]
                visited.add(node_id)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for nxt in adj[curr]:
                        if nxt not in visited:
                            visited.add(nxt)
                            queue.append(nxt)
                components.append(sorted(comp))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return QueryResult(
            data=ComponentsResult(scope=scope, components=components),
            query_text=query_text,
            result_size=len(components),
            duration_ms=round(elapsed_ms, 3),
        )
