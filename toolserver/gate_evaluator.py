"""Gate Evaluator (Part B, Phase B2).

Evaluates parameterized Cypher gates from config/gates.yaml against graph state.
Enforces Section 0 Rule 3 & Rule 5:
- Tool names come from config/gates.yaml, never hardcoded in code.
- Gates are evaluated before the tool list is built, every time.
- The model never sees a tool the gate has not unlocked.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from contracts.gates import (
    GatesConfiguration,
    ToolGateDefinition,
    GateEvaluationResult,
    GateEvaluatorProtocol,
)
from contracts.query_api import QueryAPIProtocol


class GateEvaluator(GateEvaluatorProtocol):
    """Evaluates gates against graph state according to declared Cypher expressions."""

    def __init__(
        self,
        graph_client: QueryAPIProtocol,
        config_path: Optional[str] = None,
        gates_config: Optional[GatesConfiguration] = None,
    ):
        self.graph_client = graph_client
        if gates_config:
            self.config = gates_config
        else:
            default_path = Path(__file__).resolve().parent.parent / "config" / "gates.yaml"
            resolved_path = Path(config_path) if config_path else default_path
            self.config = self._load_config(resolved_path)

        # Register loaded gates into client for Cypher gate evaluation
        if hasattr(self.graph_client, "register_gate"):
            for gate in self.config.gates:
                self.graph_client.register_gate(
                    tool_name=gate.tool_name,
                    cypher_query=gate.cypher_query,
                    required_parameters=gate.required_parameters,
                )


    @staticmethod
    def _load_config(path: Path) -> GatesConfiguration:
        if not path.exists():
            return GatesConfiguration(version="1.0.0", gates=[])
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        return GatesConfiguration(**raw_data)

    def get_gate_definition(self, tool_name: str) -> Optional[ToolGateDefinition]:
        """Find gate definition by tool name."""
        for gate in self.config.gates:
            if gate.tool_name == tool_name:
                return gate
        return None

    def evaluate(self, tool_name: str, params: Dict[str, Any]) -> GateEvaluationResult:
        """Evaluate gate for a specific tool and parameters against graph state."""
        gate = self.get_gate_definition(tool_name)
        if not gate:
            return GateEvaluationResult(
                tool_name=tool_name,
                allowed=False,
                reason=f"Tool gate '{tool_name}' not found in configuration",
                evaluated_params=params,
            )

        # Evaluate parameterized Cypher through QueryAPI
        query_res = self.graph_client.evaluate_gate(tool_name, params)
        gate_res = query_res.data
        return GateEvaluationResult(
            tool_name=tool_name,
            allowed=gate_res.allowed,
            reason=gate_res.reason,
            evaluated_params=params,
            query_executed=query_res.query_text,
        )

    def get_unlocked_tools(self, entity_id: str, context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Evaluate all declared gates for an entity; return only unlocked tool names.

        Evaluated dynamically every time before building the tool list.
        """
        unlocked: List[str] = []
        eval_params = {"entity_id": entity_id}
        if context:
            eval_params.update(context)

        for gate in self.config.gates:
            res = self.evaluate(gate.tool_name, eval_params)
            if res.allowed:
                unlocked.append(gate.tool_name)

        return unlocked
