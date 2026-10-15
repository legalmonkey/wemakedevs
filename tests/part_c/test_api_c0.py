import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["part"] == "C"

def test_registry_endpoint_contract():
    res = client.get("/api/registry")
    assert res.status_code == 200
    data = res.json()
    assert "theme_tokens" in data
    assert "statuses" in data
    assert "vocabulary" in data
    assert "node_presentation" in data
    
    # Check theme tokens
    tokens = data["theme_tokens"]
    assert "paper_base" in tokens
    assert "signal_inks" in tokens
    assert "tainted" in tokens["signal_inks"]
    assert "reaffirmed" in tokens["signal_inks"]
    assert "suspect" in tokens["signal_inks"]

    # Check status format
    for status in data["statuses"]:
        assert "id" in status
        assert "label" in status
        assert "stamp_text" in status
        assert "ink_token" in status

def test_event_publish_and_schema():
    payload = {
        "event_id": "test-evt-001",
        "event_type": "event.received",
        "tenant_id": "tenant-alpha",
        "timestamp": "2026-10-15T20:00:00Z",
        "entity_ids": ["node-1", "node-2"],
        "payload": {"kind": "unit_test"}
    }
    res = client.post("/api/events/publish", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "published"
