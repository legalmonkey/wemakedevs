"""Adversarial Audit Test Suite (Part 1 Audit).

Exposes system failures, blind spots, Rule violations, and unverified claims
in accordance with ROADMAP.md Section 0 and Section 9.
"""

import asyncio
import re
import socket
from pathlib import Path
import pytest

from contracts.ontology import EdgeRole, NodeRole
from engine.falkordb_client import FalkorDBGraphClient
from toolserver.gate_evaluator import GateEvaluator
from api.incident_service import IncidentService
from engine.incident_generator import generate_seeded_incident


ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_audit_reaffirmation_stamp_in_incident_service():
    """ADVERSARIAL CHECK: Does a reaffirmed decision get stamped REAFFIRMED (green) in the API/UI?
    
    Roadmap Section 1, 2, 8: Reaffirmation beat is the core pitch where decisions with
    independent support flip to green REAFFIRMED.
    """
    svc = IncidentService()
    async def noop_cb(ev): pass
    # Run incident to quiescence
    asyncio.run(svc.run_incident_stream(seed=101, tenant_id=None, speed_ms=1, broadcast_callback=noop_cb))
    
    snapshot = svc.get_graph_snapshot()
    reaff_nodes = [n for n in snapshot.nodes if n.role.lower() == "decision" and (n.properties.get("verdict") == "reaffirmed" or n.stamp_text == "REAFFIRMED")]
    assert len(reaff_nodes) >= 1, "No reaffirmed decision node found in graph snapshot"
    
    reaff_node = reaff_nodes[0]
    
    # FAULT EXPOSED: The node verdict was 'reaffirmed', but status remained 'pending' and is_tainted remained True.
    # Therefore, api/incident_service.py stamped it as HOLD with ink tainted!
    assert reaff_node.stamp_text == "REAFFIRMED", (
        f"BROKEN CORE DEMO BEAT: Reaffirmed node '{reaff_node.id}' was stamped '{reaff_node.stamp_text}' "
        f"with ink '{reaff_node.ink_token}' instead of 'REAFFIRMED' / 'reaffirmed'!"
    )
    assert reaff_node.ink_token == "reaffirmed", (
        f"BROKEN COLOR: Reaffirmed node ink_token is '{reaff_node.ink_token}', expected 'reaffirmed'!"
    )


def test_audit_cypher_gate_evaluator_syntax_bypass():
    """ADVERSARIAL CHECK: Does StubGraphClient.evaluate_gate properly enforce Cypher graph patterns?
    
    Rule 5: Verdicts come only from declared policy evaluated in Cypher.
    config/gates.yaml draft_notice query:
    MATCH (u:Unit {id: $entity_id})-[:ships-in]->(s:Shipment) WHERE u.is_tainted = true RETURN count(s) > 0 AS allowed
    """
    client = FalkorDBGraphClient(tenant_id="audit-gate-test", clean=True)
    # Add a tainted unit that has NO shipment (has not shipped anywhere)
    client.add_node(
        node_id="unit-tainted-unshipped",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={"is_tainted": True, "status": "tainted"},
    )
    
    evaluator = GateEvaluator(graph_client=client)
    res = evaluator.evaluate("draft_notice", {"entity_id": "unit-tainted-unshipped"})
    
    # In real Cypher, count(s) == 0 because no shipment exists, so allowed must be False.
    # FAULT EXPOSED: StubGraphClient only checks '"is_tainted = true" in cypher_lower'
    # and ignores the '-[:ships-in]->(s:Shipment)' pattern, wrongly returning allowed=True!
    assert res.allowed is False, (
        f"SECURITY / POLICY BYPASS: draft_notice gate returned allowed=True for an unshipped unit! "
        f"Reason: {res.reason}. Cypher pattern matching was bypassed by substring check."
    )


def test_audit_raw_hex_color_in_ui():
    """ADVERSARIAL CHECK: Are raw hex colors forbidden by Rule 3 present in frontend code?"""
    page_file = ROOT_DIR / "ui" / "src" / "app" / "page.tsx"
    assert page_file.exists(), "ui/src/app/page.tsx not found"
    
    hex_pattern = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
    content = page_file.read_text(encoding="utf-8")
    
    violations = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        clean_line = line.split("//")[0]
        matches = hex_pattern.findall(clean_line)
        if matches:
            violations.append(f"Line {line_no}: {matches} in {clean_line.strip()}")
            
    assert not violations, f"Rule 3 Violation in ui/src/app/page.tsx: Raw hex colors found: {violations}"


def test_audit_linter_blind_spots():
    """ADVERSARIAL CHECK: Does scripts/lint.py inspect all production code (including api/ and ui/)?"""
    from scripts.lint import PRODUCTION_DIRS
    
    # FAULT EXPOSED: PRODUCTION_DIRS only includes contracts, agents, toolserver, engine.
    # api and ui are omitted, masking Rule 3 violations.
    assert "api" in PRODUCTION_DIRS, "Linter blind spot: 'api' directory omitted from PRODUCTION_DIRS"
    assert "ui" in PRODUCTION_DIRS, "Linter blind spot: 'ui' directory omitted from PRODUCTION_DIRS"


def test_audit_fake_numbers_formula_in_ui_stats():
    """ADVERSARIAL CHECK: Does api/incident_service.py use fabricated formulas for UI metrics?
    
    Rule 8: No mock data in production paths. No fake numbers in the UI.
    """
    svc_file = ROOT_DIR / "api" / "incident_service.py"
    content = svc_file.read_text(encoding="utf-8")
    
    # FAULT EXPOSED: Line 153 fabricates naive recall:
    # naive_units_count = max(len(units) * 2, 8)
    assert "len(units) * 2" not in content, (
        "Rule 8 Violation: api/incident_service.py fabricates naive_units_count with 'max(len(units) * 2, 8)'"
    )


def test_audit_hardcoded_gate_test_samples_in_ui():
    """ADVERSARIAL CHECK: Does ui/src/app/page.tsx hardcode non-existent dummy entity IDs?"""
    page_file = ROOT_DIR / "ui" / "src" / "app" / "page.tsx"
    content = page_file.read_text(encoding="utf-8")
    
    assert "unit-clean-sample" not in content, (
        "Rule 3 / 8 Violation: Hardcoded non-existent entity 'unit-clean-sample' in UI test button"
    )
    assert "unit-tainted-sample" not in content, (
        "Rule 3 / 8 Violation: Hardcoded non-existent entity 'unit-tainted-sample' in UI test button"
    )


def test_audit_fallback_recording_file_presence():
    """ADVERSARIAL CHECK: Does fallback_demo_recording_1792081416235.webp claimed in PROGRESS.md exist?"""
    claimed_filename = "fallback_demo_recording_1792081416235.webp"
    matches = list(ROOT_DIR.rglob(claimed_filename))
    
    assert len(matches) > 0, (
        f"UNVERIFIED CLAIM: Claimed fallback recording '{claimed_filename}' is missing from repository."
    )


def test_audit_falkordb_live_service_connectivity():
    """ADVERSARIAL CHECK: Is live FalkorDB instance accessible on port 6379?"""
    s = socket.socket()
    s.settimeout(1.0)
    err = s.connect_ex(("127.0.0.1", 6379))
    s.close()
    
    if err != 0:
        pytest.fail("NOT RUN / FAILING: FalkorDB is not reachable on port 6379; Docker container is not active.")


def test_audit_new_status_ui_rendering():
    """ADVERSARIAL CHECK: Definition of Done #4:
    A new status added to the registry appears in the UI with no frontend change.
    """
    svc = IncidentService()
    # Add a custom status to a node in graph
    test_node = svc.graph_client.add_node(
        node_id="custom-status-node",
        kind="CustomBatch",
        role=NodeRole.UNIT,
        properties={"status": "quarantined_by_custom_policy"},
    )
    
    snapshot = svc.get_graph_snapshot()
    matched = [n for n in snapshot.nodes if n.id == "custom-status-node"]
    assert len(matched) == 1
    
    # FAULT EXPOSED: api/incident_service.py has hardcoded if/elif logic that only knows
    # 'suspect', 'reaffirmed', 'tainted'. It does not dynamically look up status from registry!
    assert matched[0].stamp_text is not None, (
        "Definition of Done #4 Failed: New status 'quarantined_by_custom_policy' was not mapped to a stamp text "
        "because api/incident_service.py hardcodes known status strings in if/elif branches!"
    )
