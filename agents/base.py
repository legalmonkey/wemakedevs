"""Agent Base Class (Part B, Phase B0).

Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding of domain values, ids, thresholds, or tool names.
- Rule 4: The graph is the only shared state. Agents never call each other.
- Rule 5: The LLM never issues a verdict.
- Idempotent and restart-safe because work queue is derived from graph queries.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from contracts.query_api import QueryAPIProtocol
from contracts.events import EventEnvelope, EventType
from agents.llm_adapter import LLMAdapterProtocol


class WorkItem(BaseModel):
    """A unit of work discovered by querying graph state."""
    item_id: str = Field(description="Unique identifier of the work item")
    entity_id: str = Field(description="Graph entity id requiring attention")
    role: str = Field(description="Generic role of entity (e.g. Event, Decision, Action)")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Entity attributes from query")


class AgentStepResult(BaseModel):
    """Telemetry and outcome of a single agent step."""
    agent_name: str
    tenant_id: str
    items_polled: int = 0
    items_processed: int = 0
    events_emitted: List[EventEnvelope] = Field(default_factory=list)
    queries_run: List[str] = Field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base class for all Tainted agents."""

    def __init__(
        self,
        name: str,
        tenant_id: str,
        graph_client: QueryAPIProtocol,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
    ):
        self.name = name
        self.tenant_id = tenant_id
        self.graph_client = graph_client
        self.llm_adapter = llm_adapter
        self.is_active = True
        self.is_alive_flag: bool = True
        self.current_phase: str = "idle"
        self.current_query: str = "MATCH (n) RETURN count(n);"
        self.is_mid_work_flag: bool = False

    def is_alive(self) -> bool:
        """Returns True if agent process/worker is alive and active."""
        return self.is_alive_flag and self.is_active

    def is_mid_work(self) -> bool:
        """Returns True if agent is actively executing mid-work."""
        return self.is_mid_work_flag

    def kill(self) -> None:
        """Terminates agent worker process mid-execution."""
        self.is_alive_flag = False
        self.is_active = False
        self.is_mid_work_flag = False

    def create_event(
        self,
        event_type: EventType,
        entity_ids: List[str],
        payload: Dict[str, Any],
    ) -> EventEnvelope:
        """Helper to create SSE event envelope satisfying the Event Contract."""
        return EventEnvelope(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            tenant_id=self.tenant_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            entity_ids=entity_ids,
            payload=payload,
        )

    @abstractmethod
    def poll_work(self) -> List[WorkItem]:
        """Poll the graph for pending work items via query. Must be idempotent."""
        pass

    @abstractmethod
    def process_item(self, item: WorkItem) -> List[EventEnvelope]:
        """Process a single work item strictly via graph operations and policy."""
        pass

    def step(self) -> AgentStepResult:
        """Perform one execution step: poll, process, and return result."""
        result = AgentStepResult(
            agent_name=self.name,
            tenant_id=self.tenant_id,
        )

        self.current_phase = f"poll_work_{self.name.lower()}"
        items = self.poll_work()
        result.items_polled = len(items)

        if items:
            self.is_mid_work_flag = True
            self.current_phase = f"process_items_{self.name.lower()}"

        for item in items:
            if not self.is_active or not self.is_alive_flag:
                break
            emitted = self.process_item(item)
            result.events_emitted.extend(emitted)
            result.items_processed += 1

        self.is_mid_work_flag = False
        self.current_phase = "idle"

        # Emit agent status event
        status_event = self.create_event(
            event_type=EventType.AGENT_STATUS,
            entity_ids=[item.entity_id for item in items],
            payload={
                "agent_name": self.name,
                "status": "idle" if result.items_processed == 0 else "active",
                "entities_processed": result.items_processed,
            },
        )
        result.events_emitted.append(status_event)

        return result
