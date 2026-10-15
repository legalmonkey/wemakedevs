"""Tool Gate Contract (Section 4.5).

Gate expressions declared in config/gates.yaml, each a parameterised Cypher returning boolean.
Tool names come from this configuration, NEVER hardcoded in Python code.
Evaluated dynamically before offering tools to LLM or executing actions.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field


class ToolGateDefinition(BaseModel):
    """Schema for each gate declared in config/gates.yaml."""
    tool_name: str = Field(description="Dynamic tool identifier defined in config")
    description: str = Field(description="Purpose of tool and when unlocked")
    cypher_query: str = Field(description="Parameterised Cypher returning boolean (e.g. allowed: bool)")
    required_parameters: List[str] = Field(default_factory=list, description="Parameters required by query")
    target_role: Optional[str] = Field(default=None, description="Generic role on which this tool operates")


class GatesConfiguration(BaseModel):
    """Top-level structure of config/gates.yaml."""
    version: str = "1.0.0"
    gates: List[ToolGateDefinition] = Field(default_factory=list)


class GateEvaluationResult(BaseModel):
    """Result of evaluating a gate query against the graph."""
    tool_name: str
    allowed: bool
    reason: str
    evaluated_params: Dict[str, Any] = Field(default_factory=dict)
    query_executed: Optional[str] = None


class GateEvaluatorProtocol(Protocol):
    """Protocol for evaluating tool gates against graph state."""

    def evaluate(self, tool_name: str, params: Dict[str, Any]) -> GateEvaluationResult:
        """Evaluate whether a tool is unlocked for given parameters."""
        ...

    def get_unlocked_tools(self, entity_id: str, context: Dict[str, Any]) -> List[str]:
        """Return list of tool names currently unlocked for an entity."""
        ...
