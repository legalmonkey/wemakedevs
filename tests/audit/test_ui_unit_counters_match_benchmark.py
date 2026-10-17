"""Test Requirement 1 & 4: Cypher Parity Checks for Unit Tiles on FalkorDB.

Verifies:
1. Executes hand-written OpenCypher queries directly on FalkorDB for seeds 101, 202, 303, and 4812.
2. Escalated tile counts Units that have a decision with verdict unverifiable or an escalation action, not u.verdict.
3. Suspect tile counts Units flagged suspect or connected via lateral links.
4. Asserts strict parity between FalkorDB Cypher queries and UI tiles.
5. Asserts that escalated is at least 1 across all verified seeds.
"""

from __future__ import annotations
import pytest
from api.incident_service import IncidentService


CYPHER_TOTAL_HELD_REAFFIRMED_QUERY = """
MATCH (u:Unit)
RETURN
  count(u) AS total_units,
  count(CASE WHEN u.verdict = 'tainted' OR u.status IN ['tainted', 'quarantined'] THEN 1 END) AS held_units,
  count(CASE WHEN u.verdict = 'reaffirmed' OR u.status = 'reaffirmed' THEN 1 END) AS reaffirmed_units
"""

CYPHER_ESCALATED_UNITS_QUERY = """
MATCH (u:Unit)
OPTIONAL MATCH (d:Decision)-[:SUPPORT|TAINTS]->(u)
OPTIONAL MATCH (a:Action) WHERE (a.target_entity_id = u.id OR (a)-[:APPLIES_TO]->(u)) AND a.action_kind = 'escalate_human'
WITH u, d, a
WHERE d.verdict = 'unverifiable' OR a IS NOT NULL
RETURN count(DISTINCT u) AS escalated_units
"""

CYPHER_SUSPECT_UNITS_QUERY = """
MATCH (u:Unit)
WHERE u.is_suspect = true OR (u)<-[:SHARED_LOT]-() OR (u)<-[:LATERAL_LINK]-()
RETURN count(DISTINCT u) AS suspect_units
"""


@pytest.mark.asyncio
async def test_ui_unit_counters_match_falkordb_cypher_query():
    """Verify UI unit tiles match hand-written Cypher queries on FalkorDB for seeds 101, 202, 303, and 4812."""
    test_seeds = [101, 202, 303, 4812]
    service = IncidentService()

    for seed in test_seeds:
        # 1. Run multi-agent incident on this seed
        await service.run_incident_stream(seed=seed, speed_ms=0)
        client = service.graph_client

        # 2. Execute hand-written Cypher queries directly on FalkorDB
        cypher_base_res = client.graph.query(CYPHER_TOTAL_HELD_REAFFIRMED_QUERY)
        assert cypher_base_res.result_set, f"Seed {seed}: Cypher base query returned no results"
        base_row = cypher_base_res.result_set[0]
        cypher_total = base_row[0]
        cypher_held = base_row[1]
        cypher_reaffirmed = base_row[2]

        cypher_esc_res = client.graph.query(CYPHER_ESCALATED_UNITS_QUERY)
        assert cypher_esc_res.result_set, f"Seed {seed}: Cypher escalated query returned no results"
        cypher_escalated = cypher_esc_res.result_set[0][0]

        cypher_sus_res = client.graph.query(CYPHER_SUSPECT_UNITS_QUERY)
        assert cypher_sus_res.result_set, f"Seed {seed}: Cypher suspect query returned no results"
        cypher_suspect = cypher_sus_res.result_set[0][0]

        # 3. Assert on Requirement 1: Show a seed where escalated is at least 1
        assert cypher_escalated >= 1, (
            f"Seed {seed}: Expected escalated units >= 1, got {cypher_escalated}"
        )

        # 4. Obtain UI graph snapshot as consumed by the Evidence Canvas
        snapshot = service.get_graph_snapshot()
        all_nodes = snapshot.nodes
        unit_nodes = [n for n in all_nodes if n.role.lower() == "unit"]
        unit_ids = {u.id for u in unit_nodes}
        total_units = len(unit_nodes)

        # 5. Compute UI tile counter numbers exactly as page.tsx computes them
        # (A) Escalated: Units with unverifiable decisions (via edges) or escalation actions
        unv_dec_ids = {
            n.id for n in all_nodes
            if n.role.lower() == "decision" and (n.properties.get("verdict") == "unverifiable" or n.status == "unverifiable")
        }
        esc_action_targets = {
            str(n.properties.get("target_entity_id"))
            for n in all_nodes
            if n.role.lower() == "action" and n.properties.get("action_kind") == "escalate_human"
        }
        # Also include registry actions
        for act in service.actions_registry.values():
            if act.get("action_kind") == "escalate_human" and act.get("target_entity_id"):
                esc_action_targets.add(act["target_entity_id"])

        units_with_unv_decision = set()
        for e in snapshot.edges:
            if e.source_id in unv_dec_ids and e.target_id in unit_ids:
                units_with_unv_decision.add(e.target_id)
            if e.target_id in unv_dec_ids and e.source_id in unit_ids:
                units_with_unv_decision.add(e.source_id)

        escalated_unit_ids = {
            u.id for u in unit_nodes
            if u.id in units_with_unv_decision or u.id in esc_action_targets
        }
        ui_escalated = len(escalated_unit_ids)

        # (B) Suspect: units flagged suspect or connected via lateral links
        lateral_unit_ids = set()
        for e in snapshot.edges:
            if e.is_lateral or e.kind in ("SHARED_LOT", "LATERAL_LINK"):
                if e.target_id in unit_ids:
                    lateral_unit_ids.add(e.target_id)

        ui_held = 0
        ui_reaffirmed = 0
        ui_suspect = 0

        for u in unit_nodes:
            s = (u.status or "").lower()
            stamp = (u.stamp_text or "").upper()
            verdict = str(u.properties.get("verdict") or "").lower()

            if verdict == "reaffirmed" or s == "reaffirmed" or stamp == "REAFFIRMED":
                ui_reaffirmed += 1
            if verdict == "tainted" or s == "tainted" or s == "quarantined" or stamp == "HOLD":
                ui_held += 1
            if (
                u.properties.get("is_suspect")
                or u.properties.get("suspect")
                or s == "suspect"
                or stamp == "SUSPECT"
                or u.id in lateral_unit_ids
            ):
                ui_suspect += 1

        # 6. Strict Cypher Parity Assertions
        assert total_units == cypher_total, (
            f"Seed {seed}: Total unit count mismatch: UI {total_units} vs Cypher {cypher_total}"
        )
        assert ui_held == cypher_held, (
            f"Seed {seed}: Held unit count mismatch: UI {ui_held} vs Cypher {cypher_held}"
        )
        assert ui_reaffirmed == cypher_reaffirmed, (
            f"Seed {seed}: Reaffirmed unit count mismatch: UI {ui_reaffirmed} vs Cypher {cypher_reaffirmed}"
        )
        assert ui_escalated == cypher_escalated, (
            f"Seed {seed}: Escalated unit count mismatch: UI {ui_escalated} vs Cypher {cypher_escalated}"
        )
        assert ui_suspect == cypher_suspect, (
            f"Seed {seed}: Suspect unit count mismatch: UI {ui_suspect} vs Cypher {cypher_suspect}"
        )

        print(
            f"\n[PASS] Seed {seed} Cypher vs UI Tiles Parity Verified:"
            f"\n  Total Units (Denominator): UI={total_units} == Cypher={cypher_total}"
            f"\n  Held Units:                 UI={ui_held} == Cypher={cypher_held}"
            f"\n  Reaffirmed Units:           UI={ui_reaffirmed} == Cypher={cypher_reaffirmed}"
            f"\n  Escalated Units:            UI={ui_escalated} == Cypher={cypher_escalated} (asserted >= 1)"
            f"\n  Suspect Units:              UI={ui_suspect} == Cypher={cypher_suspect}"
        )
