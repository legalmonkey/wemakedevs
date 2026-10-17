"""Event Loop Skeleton (Part B, Phase B0).

Coordinates agents by polling graph queries in cycle.
Strict adherence to Section 0 Rule 4:
- The graph is the only shared state.
- Agents never call each other. They write nodes and edges; others react to graph state.
"""

from __future__ import annotations
import logging
from typing import Callable, List, Optional
from pydantic import BaseModel, Field

from agents.base import BaseAgent, AgentStepResult
from contracts.events import EventEnvelope

logger = logging.getLogger(__name__)


class LoopTickResult(BaseModel):
    """Telemetry for a single tick of the event loop."""
    tick_number: int
    total_items_processed: int
    agent_results: List[AgentStepResult] = Field(default_factory=list)
    events_emitted: List[EventEnvelope] = Field(default_factory=list)


class EventLoop:
    """Agent event loop that iterates over agents and processes graph-driven work."""

    def __init__(self, tenant_id: str = "tenant-default"):
        self.tenant_id = tenant_id
        self.agents: List[BaseAgent] = []
        self.event_listeners: List[Callable[[EventEnvelope], None]] = []
        self.running: bool = False
        self.tick_count: int = 0

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent into the loop in canonical pipeline execution order."""
        self.agents.append(agent)
        order = {"Sentinel": 1, "Tracer": 2, "Adjudicator": 3, "Dispatcher": 4}
        self.agents.sort(key=lambda a: order.get(a.name, 99))

    def add_event_listener(self, listener: Callable[[EventEnvelope], None]) -> None:
        """Add an event listener (e.g., SSE publisher or test collector)."""
        self.event_listeners.append(listener)

    def dispatch_event(self, event: EventEnvelope) -> None:
        """Dispatch event to registered listeners."""
        for listener in self.event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error("Error in event listener: %s", e)

    def run_tick(self) -> LoopTickResult:
        """Run one complete cycle through all registered agents.

        Each agent polls the graph independently. Agents never call each other.
        """
        self.tick_count += 1
        tick_result = LoopTickResult(
            tick_number=self.tick_count,
            total_items_processed=0,
        )

        for agent in self.agents:
            if not agent.is_active:
                continue
            step_result = agent.step()
            tick_result.agent_results.append(step_result)
            tick_result.total_items_processed += step_result.items_processed

            for event in step_result.events_emitted:
                tick_result.events_emitted.append(event)
                self.dispatch_event(event)

        return tick_result

    def run_until_idle(self, max_ticks: int = 10) -> List[LoopTickResult]:
        """Run the loop until no agent finds any pending work items or max_ticks reached."""
        self.running = True
        tick_results: List[LoopTickResult] = []

        for _ in range(max_ticks):
            tick_res = self.run_tick()
            tick_results.append(tick_res)
            # If no items were processed by any agent, system is idle
            if tick_res.total_items_processed == 0:
                break

        self.running = False
        return tick_results

    def stop(self) -> None:
        """Signal the loop to stop."""
        self.running = False
