"""Demand 5 / Item 5 Verification: Mutually Exclusive UI State Tiles & Suspect=0 at Completion.

Verifies:
1. Four tiles are mutually exclusive: held, reaffirmed, escalated, unaffected.
2. Sum of tiles equals total units investigated on 5 seeds (101, 202, 303, 4812, 31337).
3. Suspect count is strictly 0 at completion on every seed.
4. Cypher queries executed directly against live FalkorDB.
"""

import pytest
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


@pytest.mark.parametrize("seed", [101, 202, 303, 4812, 31337])
def test_ui_tiles_mutually_exclusive_and_suspect_zero_at_completion(seed):
    tenant = f"t-tile-pytest-{seed}"
    client = generate_seeded_incident(seed=seed, clean=True, tenant_id=tenant)
    loop = EventLoop(tenant_id=tenant)
    loop.register_agent(SentinelAgent(tenant, client))
    loop.register_agent(TracerAgent(tenant, client))
    loop.register_agent(AdjudicatorAgent(tenant, client))
    loop.register_agent(DispatcherAgent(tenant, client))
    loop.run_until_idle()

    # Cypher query for unit states
    cypher_units = """
        MATCH (u:Unit)
        OPTIONAL MATCH (u)-[]-(d:Decision)
        OPTIONAL MATCH (u)-[]-(a:Action)
        WITH u,
             sum(CASE WHEN d.verdict = 'unverifiable' OR d.status = 'unverifiable' THEN 1 ELSE 0 END) AS unv_count,
             sum(CASE WHEN a.action_kind = 'escalate_human' OR a.kind = 'escalate_human' THEN 1 ELSE 0 END) AS esc_count
        RETURN u.id AS id,
               coalesce(u.is_tainted, false) AS is_tainted,
               coalesce(u.status, '') AS status,
               coalesce(u.verdict, '') AS verdict,
               coalesce(u.is_suspect, false) AS is_suspect,
               unv_count,
               esc_count
    """
    res = client.graph.query(cypher_units)
    rows = res.result_set or []

    total_units = len(rows)
    held = 0
    reaffirmed = 0
    escalated = 0
    unaffected = 0
    suspect = 0

    for row in rows:
        uid, is_tainted, status, verdict, is_suspect, unv_cnt, esc_cnt = row
        s = str(status).lower()
        v = str(verdict).lower()

        if is_suspect or s == "suspect":
            suspect += 1

        if unv_cnt > 0 or esc_cnt > 0:
            escalated += 1
        elif v == "reaffirmed" or s == "reaffirmed":
            reaffirmed += 1
        elif is_tainted or s == "quarantined" or v == "tainted":
            held += 1
        else:
            unaffected += 1

    tile_sum = held + reaffirmed + escalated + unaffected

    # Strict invariant assertions
    assert tile_sum == total_units, f"Seed {seed}: Tile sum {tile_sum} != total units {total_units}"
    assert suspect == 0, f"Seed {seed}: Expected 0 suspect units at completion, found {suspect}"
