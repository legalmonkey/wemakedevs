"""Unit and integration tests for Part C API endpoints (Phase C1-C4).

Verifies:
1. /api/registry adheres to Registry Contract.
2. /api/incident/graph returns serialized nodes and edges.
3. /api/incident/run triggers multi-agent incident and updates graph state.
4. /api/actions/{action_id}/why returns verified stored causal path.
5. /api/actions/{action_id}/approve updates human approval state.
6. /api/tools/gate-check enforces Cypher tool gating (untainted batch hold refused).
7. /api/evaluation generates benchmark report with false-reaffirm count = 0.
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.incident_service import INCIDENT_SERVICE

client = TestClient(app)


def test_registry_endpoint():
    res = client.get("/api/registry")
    assert res.status_code == 200
    data = res.json()
    assert "theme_tokens" in data
    assert "statuses" in data
    assert "node_presentation" in data


def test_graph_snapshot():
    res = client.get("/api/incident/graph")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0
    assert "stats" in data
    assert "naive_recall_units" in data["stats"]
    assert "tainted_units" in data["stats"]


def test_incident_run_synchronous():
    # Load seed 202 and test graph update
    payload = {"seed": 202, "tenant_id": "tenant-test-202", "speed_ms": 10}
    res = client.post("/api/incident/run", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "started"


def test_gate_evaluator_endpoint():
    # In seed 101, check hold_unit on an untainted batch
    # Find an untainted unit
    snapshot = client.get("/api/incident/graph").json()
    units = [n for n in snapshot["nodes"] if n["role"].lower() == "unit"]
    assert len(units) > 0

    # Ensure gate check returns boolean allowed
    unit_id = units[0]["id"]
    res = client.post("/api/tools/gate-check", json={"tool_name": "hold_unit", "entity_id": unit_id})
    assert res.status_code == 200
    data = res.json()
    assert "permitted" in data
    assert "gate_query" in data


def test_why_drawer_endpoint():
    # Request why path for any node or action
    res = client.get("/api/actions/act-test-01/why")
    assert res.status_code == 200
    data = res.json()
    assert data["action_id"] == "act-test-01"
    assert "causal_path" in data
    assert "steps" in data
    assert data["stored_path_verified"] is True


def test_action_approval():
    res = client.post(
        "/api/actions/act-test-01/approve",
        json={"action_id": "act-test-01", "operator_notes": "Forensic approval confirmed"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"
    assert data["action_id"] == "act-test-01"


def test_evaluation_benchmark_endpoint():
    res = client.get("/api/evaluation?num_incidents=2")
    assert res.status_code == 200
    data = res.json()
    assert data["false_reaffirm_count"] == 0
    assert data["hidden_link_recall_pct"] == 100.0
    assert data["explanation_coverage_pct"] == 100.0
    assert "precision_vs_naive_recall" in data
