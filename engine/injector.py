"""Declarative Fault Injector for Tainted Scenarios (Part A, Phase A1).

Injects fault/incident events into graph state based on declarative scenario specifications:
- Picks fault targets randomly from eligible nodes matching target_role/target_kind.
- Never hardcodes IDs.
- Creates an AlertEvent node targeting the selected evidence node.
- Validates scenario expectations (used only by tests, never by agents).

Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding.
- Rule 4: Graph is the only shared state. Injector writes an Event node; agents react to it.
"""

from __future__ import annotations
import hashlib
import random
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from contracts.ontology import NodeRole


class FaultInjector:
    """Injects declarative fault events into graph state."""

    def __init__(self, scenario_config: Dict[str, Any], seed: Optional[int] = None) -> None:
        self.scenario = scenario_config
        self.seed = seed or scenario_config.get("seed", 42)
        self.rng = random.Random(self.seed)

    @classmethod
    def from_file(cls, scenario_path: str | Path, seed: Optional[int] = None) -> "FaultInjector":
        """Loads scenario configuration from YAML file."""
        with open(scenario_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data, seed=seed)

    def select_target(self, graph_client: Any) -> str:
        """Picks a fault target randomly from eligible nodes in the graph client."""
        fault_spec = self.scenario.get("fault", {})
        target_role = fault_spec.get("target_role")
        target_kind = fault_spec.get("target_kind")

        # Collect eligible nodes from client
        eligible_node_ids = []
        if hasattr(graph_client, "nodes"):
            for nid, node in graph_client.nodes.items():
                role_val = node.role.value if hasattr(node.role, "value") else str(node.role)
                if target_role and role_val.lower() != target_role.lower():
                    continue
                if target_kind and getattr(node, "kind", "").lower() != target_kind.lower():
                    continue
                eligible_node_ids.append(nid)

        if not eligible_node_ids:
            # Fallback to any Evidence node if kind-specific match is empty
            if hasattr(graph_client, "nodes"):
                for nid, node in graph_client.nodes.items():
                    role_val = node.role.value if hasattr(node.role, "value") else str(node.role)
                    if role_val.lower() == "evidence":
                        eligible_node_ids.append(nid)

        if not eligible_node_ids:
            raise ValueError(f"No eligible nodes found matching fault criteria: {fault_spec}")

        eligible_node_ids.sort()  # Ensure deterministic order before rng selection
        return self.rng.choice(eligible_node_ids)

    def inject(self, graph_client: Any) -> Dict[str, Any]:
        """Injects an AlertEvent node into the graph client targeting an eligible node."""
        target_id = self.select_target(graph_client)
        fault_spec = self.scenario.get("fault", {})

        digest = hashlib.sha256(f"{self.seed}:event:{target_id}".encode()).hexdigest()[:8]
        event_id = f"event_{self.seed}_{digest}"

        reason = fault_spec.get("reason", "Declarative fault injection")
        fault_type = fault_spec.get("fault_type", "retraction")

        properties = {
            "processed": False,
            "target_evidence_id": target_id,
            "fault_type": fault_type,
            "reason": reason,
        }

        if hasattr(graph_client, "add_node"):
            graph_client.add_node(
                node_id=event_id,
                kind="AlertEvent",
                role=NodeRole.EVENT,
                properties=properties,
            )

        return {
            "event_id": event_id,
            "target_evidence_id": target_id,
            "fault_type": fault_type,
            "reason": reason,
        }

    def verify_expectations(self, execution_results: Dict[str, Any]) -> List[str]:
        """Verifies scenario expect assertions against execution results (used by tests only)."""
        expect = self.scenario.get("expect", {})
        failures = []

        if "min_units" in expect:
            actual = execution_results.get("units_count", 0)
            if actual < expect["min_units"]:
                failures.append(f"Expected min_units >= {expect['min_units']}, got {actual}")

        if "min_tainted_decisions" in expect:
            actual = execution_results.get("tainted_decisions_count", 0)
            if actual < expect["min_tainted_decisions"]:
                failures.append(f"Expected min_tainted_decisions >= {expect['min_tainted_decisions']}, got {actual}")

        if "min_reaffirmed_decisions" in expect:
            actual = execution_results.get("reaffirmed_decisions_count", 0)
            if actual < expect["min_reaffirmed_decisions"]:
                failures.append(f"Expected min_reaffirmed_decisions >= {expect['min_reaffirmed_decisions']}, got {actual}")

        if "has_lateral_link" in expect and expect["has_lateral_link"]:
            actual = execution_results.get("has_lateral_link", False)
            if not actual:
                failures.append("Expected lateral link in graph, but none found")

        return failures
