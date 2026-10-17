"""Tainted Forensic API (Part C, FastAPI Backend).

Provides endpoints for:
- /api/registry: Statuses, design tokens, vocabulary, and node presentation
- /api/events: Real-time Server-Sent Events (SSE) stream
- /api/incident/run: Seeded multi-agent incident execution with live SSE dispatch
- /api/incident/graph: Current graph canvas snapshot
- /api/incident/query-log: Real-time Cypher audit query log
- /api/actions/{action_id}/why: Chain-of-custody explanation for Why drawer
- /api/actions/{action_id}/approve: Human approval of drafted actions
- /api/tools/gate-check: Cypher tool gate evaluator check
- /api/evaluation: Forensic evaluation benchmark metrics report
- /api/tenants: Multi-tenant scope index

Strictly adheres to Section 0 rules:
- Rule 3: Zero hardcoding.
- Rule 4: Graph is the only shared state.
- Rule 5: Verdicts come only from declared policy evaluated in Cypher.
- Rule 7: Every action has a stored path.
"""

from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from api.models import (
    RegistryResponse,
    EventContractPayload,
    IncidentRunRequest,
    GraphSnapshotResponse,
    WhyPathResponse,
    ActionApprovalRequest,
    GateCheckRequest,
    GateCheckResponse,
)
from api.incident_service import INCIDENT_SERVICE

app = FastAPI(title="Tainted Forensic Audit API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EVENT_SUBSCRIBERS: list[asyncio.Queue] = []


def load_registry_data() -> dict:
    tokens_path = Path(__file__).parent / "tokens.json"
    with open(tokens_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "part": "C",
        "service": "api",
        "active_tenant": INCIDENT_SERVICE.current_tenant_id,
        "active_seed": INCIDENT_SERVICE.current_seed,
    }


@app.get("/api/registry", response_model=RegistryResponse)
async def get_registry():
    data = load_registry_data()
    return RegistryResponse(**data)


@app.get("/api/events")
async def event_stream(request: Request):
    """Server-Sent Events endpoint streaming real-time event contract envelopes."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    EVENT_SUBSCRIBERS.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Initial connection handshake
            yield f": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep SSE alive
                    yield f": heartbeat\n\n"
        finally:
            if queue in EVENT_SUBSCRIBERS:
                EVENT_SUBSCRIBERS.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def broadcast_event(event_dict: Dict[str, Any]) -> None:
    """Broadcasts an event envelope to all connected SSE clients."""
    payload_str = f"data: {json.dumps(event_dict)}\n\n"
    for queue in list(EVENT_SUBSCRIBERS):
        try:
            await queue.put(payload_str)
        except Exception:
            pass


@app.post("/api/events/publish")
async def publish_event(event: EventContractPayload):
    event_dict = event.model_dump()
    await broadcast_event(event_dict)
    return {"status": "published", "event_id": event.event_id}


@app.post("/api/incident/run")
async def trigger_incident_run(
    req: IncidentRunRequest,
    background_tasks: BackgroundTasks,
):
    """Triggers an asynchronous multi-agent incident run on a seeded graph."""
    seed = req.seed or 101
    speed_ms = req.speed_ms or 350
    tenant_id = req.tenant_id or f"tenant-seed-{seed}"

    # Run execution in background task so endpoint returns immediately
    background_tasks.add_task(
        INCIDENT_SERVICE.run_incident_stream,
        seed=seed,
        tenant_id=tenant_id,
        speed_ms=speed_ms,
        broadcast_callback=broadcast_event,
    )

    return {
        "status": "started",
        "seed": seed,
        "tenant_id": tenant_id,
        "speed_ms": speed_ms,
        "message": f"Multi-agent incident run started on seed {seed}",
    }


@app.get("/api/incident/graph", response_model=GraphSnapshotResponse)
async def get_graph_snapshot():
    """Returns serialized graph snapshot for the canvas."""
    return INCIDENT_SERVICE.get_graph_snapshot()


@app.get("/api/incident/query-log")
async def get_query_log():
    """Returns real-time Cypher audit query log."""
    return {
        "queries": INCIDENT_SERVICE.query_log,
        "count": len(INCIDENT_SERVICE.query_log),
    }


@app.get("/api/actions/pending")
async def get_pending_actions():
    """Returns list of actions awaiting human operator adjudication."""
    return {"pending_actions": INCIDENT_SERVICE.get_pending_actions()}


@app.get("/api/actions/{action_id}/why", response_model=WhyPathResponse)
async def get_action_why(action_id: str):
    """Retrieves the stored causal chain of custody for Why drawer (Rule 7)."""
    return INCIDENT_SERVICE.explain_action(action_id)


@app.post("/api/actions/{action_id}/approve")
async def approve_action(action_id: str, req: ActionApprovalRequest = None):
    """Approves a human-gated action."""
    notes = req.operator_notes if req else None
    result = INCIDENT_SERVICE.approve_action(action_id, notes)
    
    # Broadcast approval event over SSE
    await broadcast_event({
        "event_id": f"evt-approved-{action_id}",
        "event_type": "action.created",
        "tenant_id": INCIDENT_SERVICE.current_tenant_id,
        "timestamp": result["timestamp"],
        "entity_ids": [action_id],
        "payload": {
            "action_id": action_id,
            "status": "APPROVED",
            "approved": True,
            "operator_notes": result["operator_notes"],
        },
    })
    return result


@app.post("/api/tools/gate-check", response_model=GateCheckResponse)
async def check_tool_gate(req: GateCheckRequest):
    """Evaluates whether a tool is unlocked by graph state in Cypher (Rule 5)."""
    return INCIDENT_SERVICE.evaluate_gate(req.tool_name, req.entity_id)


@app.get("/api/evaluation")
async def get_evaluation_benchmark(
    num_incidents: int = Query(default=5, ge=1, le=20)
):
    """Runs the forensic evaluation benchmark harness."""
    report = INCIDENT_SERVICE.run_benchmark(num_incidents=num_incidents)
    return report.model_dump()


@app.get("/api/tenants")
async def list_tenants():
    """Lists available tenants for multi-tenant isolation demonstration."""
    return {
        "tenants": [
            {
                "id": "tenant-alpha",
                "label": "Tenant Alpha (Food Distribution)",
                "ontology": "packs/food/ontology.yaml",
                "policy": "Standard Containment (min_independent=2)",
            },
            {
                "id": "tenant-beta",
                "label": "Tenant Beta (Cold-Chain Logistics)",
                "ontology": "packs/food/ontology.yaml",
                "policy": "Strict Containment (min_independent=3)",
            },
            {
                "id": INCIDENT_SERVICE.current_tenant_id,
                "label": f"Current Active Tenant ({INCIDENT_SERVICE.current_tenant_id})",
                "ontology": "packs/food/ontology.yaml",
                "policy": "Dynamic Seeded Isolation",
            },
        ],
        "current_tenant": INCIDENT_SERVICE.current_tenant_id,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
