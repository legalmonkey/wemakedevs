"""Agent Process Runner (Section 0 Rule 4).

Executes an agent in an independent OS process communicating exclusively
through the FalkorDB graph.
"""

from __future__ import annotations
import argparse
import sys
import time
from engine.falkordb_client import FalkorDBGraphClient
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


AGENT_CLASSES = {
    "Sentinel": SentinelAgent,
    "Tracer": TracerAgent,
    "Adjudicator": AdjudicatorAgent,
    "Dispatcher": DispatcherAgent,
}


def run_agent_loop(
    agent_name: str,
    tenant_id: str,
    poll_interval: float = 0.05,
    max_idle_count: int = 30,
) -> None:
    client = FalkorDBGraphClient(tenant_id=tenant_id, clean=False)
    agent_cls = AGENT_CLASSES[agent_name]
    agent = agent_cls(tenant_id=tenant_id, graph_client=client)

    idle_count = 0
    while idle_count < max_idle_count:
        res = agent.step()
        if res.items_processed > 0:
            idle_count = 0
        else:
            idle_count += 1
        time.sleep(poll_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=list(AGENT_CLASSES.keys()))
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    parser.add_argument("--max-idle", type=int, default=30)
    args = parser.parse_args()

    run_agent_loop(args.agent, args.tenant, args.poll_interval, args.max_idle)
