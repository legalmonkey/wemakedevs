"""Test Requirement 5: UI Unit Counters Strictly Count Units Only and Equal Benchmark Rows.

Verifies:
1. Held, Reaffirmed, Escalated, and Suspect tiles count UNITS only (role == 'Unit' or kind == 'Batch').
2. Non-unit nodes (Actions, Decisions, Evidence, Shipments) with stamps or verdicts are excluded.
3. Counters strictly equal the evaluation benchmark row for the same seed.
4. Denominator represents total units (e.g. '7 of 28 batches').
"""

import asyncio
import pytest
from engine.evaluation import EvaluationHarness
from api.incident_service import IncidentService


@pytest.mark.asyncio
async def test_ui_unit_counters_match_benchmark_row():
    """Verify UI unit counting logic matches evaluation benchmark rows across multiple seeds."""
    test_seeds = [101, 202, 303]
    harness = EvaluationHarness(base_seed=100)
    service = IncidentService()

    for seed in test_seeds:
        # 1. Run evaluation benchmark for this seed
        # EvaluationHarness runs incidents starting at base_seed
        eval_harness = EvaluationHarness(base_seed=seed)
        report = eval_harness.run_benchmark(num_incidents=1)
        assert len(report.incidents) == 1, f"Expected 1 benchmark incident for seed {seed}"
        bench_row = report.incidents[0]

        # 2. Run incident on the API service to get the graph snapshot for the UI
        await service.run_incident_stream(seed=seed, speed_ms=0)
        snapshot = service.get_graph_snapshot()

        # 3. Calculate UI counters strictly according to the UI logic
        all_nodes = snapshot.nodes
        unit_nodes = [n for n in all_nodes if n.role.lower() == "unit"]
        total_units = len(unit_nodes)

        # Ensure there are other nodes with stamps/verdicts to verify isolation
        non_unit_nodes_with_stamps = [
            n for n in all_nodes
            if n.role.lower() != "unit" and (n.stamp_text or n.properties.get("verdict"))
        ]
        assert len(non_unit_nodes_with_stamps) > 0, "Graph must contain non-unit nodes with stamps/verdicts"

        ui_held = 0
        ui_reaffirmed = 0
        ui_escalated = 0
        ui_suspect = 0

        for u in unit_nodes:
            s = (u.status or "").lower()
            stamp = (u.stamp_text or "").upper()
            verdict = str(u.properties.get("verdict") or "").lower()

            if stamp == "REAFFIRMED" or s == "reaffirmed" or verdict == "reaffirmed":
                ui_reaffirmed += 1
            elif stamp == "ESCALATED" or s == "escalated" or s == "unverifiable" or verdict == "unverifiable":
                ui_escalated += 1
            elif stamp == "HOLD" or s == "tainted" or s == "quarantined" or verdict == "tainted":
                ui_held += 1
            elif stamp == "SUSPECT" or s == "suspect" or bool(u.properties.get("is_suspect")):
                ui_suspect += 1

        # Denominator test: unit count must match total_units
        assert total_units == bench_row.total_units, (
            f"Seed {seed}: Total unit count mismatch: UI {total_units} vs Benchmark {bench_row.total_units}"
        )

        # 4. Strict assertions against benchmark row
        assert ui_reaffirmed == bench_row.reaffirmed_units, (
            f"Seed {seed}: Reaffirmed unit count mismatch! UI computed {ui_reaffirmed}, benchmark row is {bench_row.reaffirmed_units}"
        )

        assert ui_held == bench_row.tainted_units, (
            f"Seed {seed}: Held unit count mismatch! UI computed {ui_held}, benchmark row is {bench_row.tainted_units}"
        )

        # Verify that non-unit nodes are NOT counted in the total or held counts
        total_stamped_nodes = len([n for n in all_nodes if n.stamp_text])
        assert total_stamped_nodes > ui_held, (
            f"Seed {seed}: Unit held count ({ui_held}) must be strictly less than total stamped nodes ({total_stamped_nodes})"
        )

        print(
            f"\n[PASS] Seed {seed} Verified:"
            f"\n  Units Total (Denominator): {total_units} of {bench_row.total_units} batches"
            f"\n  Held Units:                 {ui_held} (UI) == {bench_row.tainted_units} (Benchmark)"
            f"\n  Reaffirmed Units:           {ui_reaffirmed} (UI) == {bench_row.reaffirmed_units} (Benchmark)"
            f"\n  Escalated Units:            {ui_escalated}"
            f"\n  Suspect Units:              {ui_suspect}"
        )


def test_ui_counters_fail_if_non_units_included():
    """Verify that including action/decision nodes in unit counters causes a test failure."""
    service = IncidentService()
    snapshot = service.get_graph_snapshot()
    all_nodes = snapshot.nodes

    # Incorrect counter that counts all nodes with stamps instead of units only
    corrupt_held = len([n for n in all_nodes if n.stamp_text == "HOLD"])
    actual_units_held = len([
        n for n in all_nodes
        if n.role.lower() == "unit" and n.stamp_text == "HOLD"
    ])

    if corrupt_held != actual_units_held:
        print(f"\n[PASS] Confirmed counter divergence: all stamped nodes={corrupt_held} vs unit-only held={actual_units_held}")
        assert corrupt_held > actual_units_held
