"""Demand 2 Verification Suite: 100+ Seed Benchmark with Comprehensive Metrics.

Verifies:
(1) Runs benchmark across 100+ seeds on FalkorDB.
(2) Reports Mean, Min, and Max of every metric:
    - Share Recalled
    - Safe Release Rate
    - Tainted Units Count
    - Reaffirmed Units Count
    - Unverifiable Units Count (emerging from orphan-result faults)
    - Escalated Actions Count
    - Hidden-Link Recall
    - Time to Scope (ms)
    - Explanation Coverage (%)
    - False Reaffirm Count (Ground Truth Invariant: 0)
"""

import time
import pytest
from engine.evaluation import EvaluationHarness, LargeBenchmarkSummary


def test_100_seed_benchmark_with_mean_min_max_metrics():
    """Run benchmark on 100+ seeds and report mean, min, and max of all metrics."""
    num_seeds = 100
    base_seed = 5000
    harness = EvaluationHarness(base_seed=base_seed)

    print(f"\n{'='*105}")
    print(f"DEMAND 2: EXECUTING 100+ SEED FORENSIC BENCHMARK ON FALKORDB ({num_seeds} SEEDS)")
    print(f"{'='*105}")
    t0_start = time.perf_counter()

    report = harness.run_100_seed_benchmark(num_seeds=num_seeds)
    elapsed_total = time.perf_counter() - t0_start
    summary: LargeBenchmarkSummary = report.large_summary

    print(f"\nExecution Time: {elapsed_total:.2f}s ({elapsed_total/num_seeds*1000:.1f}ms per incident)")
    print(f"{'='*105}")
    print(f"BENCHMARK RESULTS ACROSS {num_seeds} DISTINCT SEEDS (Mean, Min, Max)")
    print(f"{'='*105}")
    print(f"{'Metric':<35} | {'Mean':<18} | {'Min':<18} | {'Max':<18}")
    print("-" * 105)
    print(f"{'Share Recalled (Tainted / Naive)':<35} | {summary.share_recalled.mean * 100:>16.2f}% | {summary.share_recalled.min * 100:>16.2f}% | {summary.share_recalled.max * 100:>16.2f}%")
    print(f"{'Safe Release Rate (Reaffirmed/Total)':<35} | {summary.safe_release_rate.mean * 100:>16.2f}% | {summary.safe_release_rate.min * 100:>16.2f}% | {summary.safe_release_rate.max * 100:>16.2f}%")
    print(f"{'Tainted Units Count':<35} | {summary.tainted_units.mean:>17.2f} | {summary.tainted_units.min:>17.0f} | {summary.tainted_units.max:>17.0f}")
    print(f"{'Reaffirmed Units Count':<35} | {summary.reaffirmed_units.mean:>17.2f} | {summary.reaffirmed_units.min:>17.0f} | {summary.reaffirmed_units.max:>17.0f}")
    print(f"{'Unverifiable Units Count':<35} | {summary.unverifiable_units.mean:>17.2f} | {summary.unverifiable_units.min:>17.0f} | {summary.unverifiable_units.max:>17.0f}")
    print(f"{'Escalated Actions Count':<35} | {summary.escalated_count.mean:>17.2f} | {summary.escalated_count.min:>17.0f} | {summary.escalated_count.max:>17.0f}")
    print(f"{'Hidden-Link Recall':<35} | {summary.hidden_link_recall.mean:>16.1f}% | {summary.hidden_link_recall.min:>16.1f}% | {summary.hidden_link_recall.max:>16.1f}%")
    print(f"{'Time to Scope (ms)':<35} | {summary.time_to_scope_ms.mean:>15.2f}ms | {summary.time_to_scope_ms.min:>15.2f}ms | {summary.time_to_scope_ms.max:>15.2f}ms")
    print(f"{'Explanation Coverage':<35} | {summary.explanation_coverage_pct.mean:>16.1f}% | {summary.explanation_coverage_pct.min:>16.1f}% | {summary.explanation_coverage_pct.max:>16.1f}%")
    print(f"{'Total False Reaffirms':<35} | {summary.total_false_reaffirms:>17d} | {'0':>17} | {'0':>17}")
    print(f"{'='*105}\n")

    print(f"\n--- DEMAND 1: LATERAL LINK (HIDDEN-LINK) RECALL BREAKDOWN ACROSS {num_seeds} SEEDS ---")
    print(f"Seeds with Lateral Link Injected:     {summary.lateral_injected_count}")
    print(f"Seeds with Lateral Link Recalled:     {summary.lateral_recalled_count}")
    print(f"Seeds with Lateral Link Missed:       {summary.lateral_missed_count}")
    print(f"Seeds without Lateral Link Injected:  {summary.lateral_not_injected_count}")
    print(f"Hidden-Link Recall on Injected Seeds: {summary.hidden_link_recall_on_injected_pct:.1f}%\n")

    print(f"\n--- DEMAND 2: NAIVE SCOPE VARIATION & SCALE (SAMPLE OF FIRST 10 SEEDS) ---")
    print(f"{'Seed':<8} | {'Total Units (>=30)':<20} | {'Naive Scope (< Total)':<22} | {'Tainted Units':<15} | {'Share Recalled'}")
    print("-" * 85)
    for inc in report.incidents[:10]:
        print(f"{inc.seed:<8} | {inc.total_units:<20} | {inc.naive_recall_units:<22} | {inc.tainted_units:<15} | {inc.share_recalled*100:>12.2f}%")
    print("-" * 85 + "\n")

    # DEMAND 1: Check demo-viability minimums from scenario expect block (read only by tests)
    import yaml
    from pathlib import Path
    scenario_path = Path(__file__).resolve().parent.parent.parent / "scenarios" / "scenario_calibration_drift.yaml"
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario_yaml = yaml.safe_load(f)
    expect_block = scenario_yaml.get("expect", {})
    min_tainted = expect_block.get("min_tainted_units", 3)
    min_reaffirmed = expect_block.get("min_reaffirmed_units", 3)
    min_unverifiable = expect_block.get("min_unverifiable_units", 1)

    demo_viable_seeds = [
        inc for inc in report.incidents
        if inc.tainted_units >= min_tainted
        and inc.reaffirmed_units >= min_reaffirmed
        and inc.unverifiable_units >= min_unverifiable
    ]
    viable_pct = (len(demo_viable_seeds) / num_seeds) * 100.0

    print(f"\n--- DEMAND 1: DEMO-VIABILITY COMPLIANCE ACROSS {num_seeds} SEEDS ---")
    print(f"Scenario Expect Contract (Read ONLY by tests):")
    print(f"  - min_tainted_units:      >= {min_tainted}")
    print(f"  - min_reaffirmed_units:   >= {min_reaffirmed}")
    print(f"  - min_unverifiable_units: >= {min_unverifiable}")
    print(f"Results Across {num_seeds} Seeds:")
    print(f"  - Seeds meeting all minimums: {len(demo_viable_seeds)} / {num_seeds}")
    print(f"  - Fraction meeting minimums:  {viable_pct:.1f}% (Target: 100%)\n")

    print(f"\n--- DEMAND 2: HIDDEN-LINK RECALL DEFINED AS 'THE LATERAL UNIT RECEIVED A TAINTS EDGE' ---")
    print("Graph Query on 5 Seeds:")
    print("MATCH (lateral:Unit)<-[r:TAINTS]-(src)")
    print("WHERE (lateral)-[:SHARED_LOT|LATERAL_LINK]-() RETURN lateral.id, type(r), src.id, r.hops, r.via_path\n")

    from engine.falkordb_client import FalkorDBGraphClient
    sample_seeds = [inc.seed for inc in report.incidents[:5]]
    for s_seed in sample_seeds:
        c_sample = FalkorDBGraphClient(tenant_id=f"tenant-bench-{s_seed}", clean=False)
        cypher_check = (
            "MATCH (lateral:Unit)<-[r:TAINTS]-(src) "
            "WHERE (lateral)-[:SHARED_LOT|LATERAL_LINK]-() "
            "RETURN lateral.id AS lateral_unit, type(r) AS edge_type, src.id AS source_id, r.hops AS hops, r.via_path AS via_path"
        )
        res_sample = c_sample.graph.query(cypher_check)
        print(f"Seed {s_seed}:")
        if res_sample.result_set:
            for row in res_sample.result_set[:2]:
                print(f"  -> Lateral Unit: {row[0]} | Received: {row[1]} edge from {row[2]} | Hops: {row[3]} | Via: {row[4]}")
        else:
            print(f"  -> No lateral link row found")


    print(f"{'='*105}\n")

    # Strict Assertions
    assert len(demo_viable_seeds) == num_seeds, (
        f"Target 100% demo-viable seeds failed! Got {len(demo_viable_seeds)}/{num_seeds} ({viable_pct:.1f}%)"
    )
    naive_counts = [inc.naive_recall_units for inc in report.incidents]
    assert len(set(naive_counts)) > 1, f"Naive count must vary across seeds! Got {set(naive_counts)}"
    assert all(inc.total_units >= 30 for inc in report.incidents), "Scale must be at least 30 units across all seeds"
    assert any(inc.naive_recall_units < inc.total_units for inc in report.incidents), "Naive recall must select a strict subset on some seeds"
    assert summary.total_false_reaffirms == 0, f"False reaffirms must be strictly 0, got {summary.total_false_reaffirms}"
    assert summary.unverifiable_units.min >= 1, f"Unverifiable min must be >= 1, got {summary.unverifiable_units.min}"
    assert summary.tainted_units.min >= 3, f"Tainted min must be >= 3, got {summary.tainted_units.min}"
    assert summary.reaffirmed_units.min >= 3, f"Reaffirmed min must be >= 3, got {summary.reaffirmed_units.min}"
    assert summary.escalated_count.max > 0, "Escalated actions must appear for unverifiable units"
    assert summary.lateral_missed_count == 0, f"Lateral links missed must be strictly 0, got {summary.lateral_missed_count}"
    assert summary.hidden_link_recall_on_injected_pct == 100.0, f"Hidden-link recall on injected seeds must be strictly 100.0%, got {summary.hidden_link_recall_on_injected_pct}%"
    assert summary.share_recalled.min >= 0.0, "Share recalled min must be non-negative"
    assert summary.share_recalled.max > 0.0, "Share recalled max must be positive"
    assert summary.share_recalled.max <= 1.0, "Share recalled max must be <= 1.0"

