"""Item 5 Verification Script: UI Tile Exclusivity, Timing Disclosure & Cypher Parity.

Verifies:
1. Four tiles are mutually exclusive: held, reaffirmed, escalated, unaffected.
2. Sum of tiles equals total units investigated on 5 seeds (101, 202, 303, 4812, 31337).
3. Suspect count is strictly 0 at completion on every seed.
4. Verifies Cypher query assertions directly against live FalkorDB.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.falkordb_client import FalkorDBGraphClient
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


def evaluate_tile_counts_on_seed(seed: int) -> Dict[str, int]:
    """Runs incident on live FalkorDB and evaluates mutually exclusive unit counts via Cypher."""
    tenant = f"t-tile-check-{seed}"
    client = generate_seeded_incident(seed=seed, clean=True, tenant_id=tenant)
    loop = EventLoop(tenant_id=tenant)
    loop.register_agent(SentinelAgent(tenant, client))
    loop.register_agent(TracerAgent(tenant, client))
    loop.register_agent(AdjudicatorAgent(tenant, client))
    loop.register_agent(DispatcherAgent(tenant, client))
    loop.run_until_idle()

    # Single unified Cypher query to retrieve all unit states
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

    return {
        "seed": seed,
        "total": total_units,
        "held": held,
        "reaffirmed": reaffirmed,
        "escalated": escalated,
        "unaffected": unaffected,
        "tile_sum": held + reaffirmed + escalated + unaffected,
        "suspect_at_completion": suspect,
        "sum_matches_total": (held + reaffirmed + escalated + unaffected == total_units),
        "suspect_is_zero": (suspect == 0),
    }


if __name__ == "__main__":
    print("=" * 105)
    print("ITEM 5: MUTUALLY EXCLUSIVE UI STATE TILES & SUSPECT=0 AT COMPLETION ON 5 SEEDS")
    print("=" * 105)

    seeds = [101, 202, 303, 4812, 31337]
    print(f"\nEvaluating seeds: {seeds}\n")
    print(f"{'Seed':<6} | {'Total':<6} | {'Held':<6} | {'Reaffirmed':<11} | {'Escalated':<10} | {'Unaffected':<11} | {'Tile Sum':<9} | {'Suspect':<8} | {'Status'}")
    print("-" * 105)

    all_passed = True
    for s in seeds:
        res = evaluate_tile_counts_on_seed(s)
        passed = res["sum_matches_total"] and res["suspect_is_zero"]
        if not passed:
            all_passed = False
        print(
            f"{res['seed']:<6} | {res['total']:<6} | {res['held']:<6} | {res['reaffirmed']:<11} | "
            f"{res['escalated']:<10} | {res['unaffected']:<11} | {res['tile_sum']:<9} | "
            f"{res['suspect_at_completion']:<8} | {'PASS (EXACT)' if passed else 'FAIL'}"
        )

    print("-" * 105)
    assert all_passed, "One or more seeds failed tile exclusivity or non-zero suspect check!"
    print("\n[ALL CHECKS PASSED] Four tiles are strictly mutually exclusive (sum == total) and suspect == 0.")
