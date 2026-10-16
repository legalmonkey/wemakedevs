"""Demand 3 Verification Suite: Realistic Naive Rule & Share Recalled Metric.

Verifies:
(1) Scenario declares realistic naive rule:
    'all batches touched by the affected instrument type in the window'.
(2) Precision metric is renamed to 'share recalled' across data contracts and evaluation reports.
(3) Benchmark metrics recomputed using the realistic scenario rule.
"""

from pathlib import Path
import pytest
import yaml
from engine.evaluation import EvaluationHarness, EvaluationReport, IncidentMetric


def test_scenario_declares_realistic_naive_recall_rule():
    """Verify scenarios declare realistic naive recall based on instrument type and time window."""
    scenario_paths = [
        Path("scenarios/scenario_calibration_drift.yaml"),
        Path("scenarios/scenario_pathogen_adulteration.yaml"),
    ]

    for p in scenario_paths:
        assert p.exists(), f"Scenario file not found: {p}"
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        naive_spec = data.get("naive_recall", {})
        rule = naive_spec.get("rule", "")
        inst_type = naive_spec.get("instrument_type")
        window = naive_spec.get("time_window_hours")

        assert "instrument type" in rule.lower() and "window" in rule.lower(), (
            f"Scenario {p.name} naive_recall rule must be 'all batches touched by the affected instrument type in the window', got '{rule}'"
        )
        assert inst_type is not None, f"Scenario {p.name} must declare instrument_type"
        assert window is not None and window > 0, f"Scenario {p.name} must declare time_window_hours"

        print(f"Verified scenario '{p.name}': rule = '{rule}' (instrument='{inst_type}', window={window}h)")


def test_share_recalled_metric_and_recomputed_benchmarks():
    """Verify precision metric renamed to share recalled and recompute metrics on real FalkorDB."""
    harness = EvaluationHarness(base_seed=7000)
    report = harness.run_benchmark(num_incidents=3)

    # Verify model fields
    assert hasattr(report, "share_recalled"), "EvaluationReport must have 'share_recalled' field"
    assert report.share_recalled > 0.0, f"Expected positive share_recalled, got {report.share_recalled}"
    assert report.precision_vs_naive_recall == report.share_recalled, "precision_vs_naive_recall must mirror share_recalled for compatibility"

    for inc in report.incidents:
        assert hasattr(inc, "share_recalled"), "IncidentMetric must have 'share_recalled' field"
        assert 0.0 <= inc.share_recalled <= 1.0, f"Invalid share_recalled: {inc.share_recalled}"
        assert inc.naive_recall_units <= inc.total_units, "Naive recall scope must be realistic subset of total units"

    print(f"\n{'='*90}")
    print("DEMAND 3: RECOMPUTED BENCHMARK WITH REALISTIC NAIVE RECALL ('share recalled')")
    print(f"{'='*90}")
    print(f"Incidents Evaluated:       {report.num_incidents}")
    print(f"Share Recalled:            {report.share_recalled * 100:.2f}% (Tainted / Naive Scope)")
    print(f"Safe Release Rate:         {report.safe_release_rate * 100:.2f}% (Reaffirmed / Total)")
    print(f"False Reaffirm Count:      {report.false_reaffirm_count} (Ground Truth Guarantee)")
    print(f"Avg Time to Scope:         {report.avg_time_to_scope_ms:.2f} ms")
    print(f"Explanation Coverage:      {report.explanation_coverage_pct:.1f}%")
    print(f"Total Unverifiable Units:  {report.unverifiable_units_count}")
    print(f"Total Escalated Actions:   {report.escalated_count}")
    print("-" * 90)
    print(f"{'Incident ID':<22} | {'Total':<6} | {'Naive':<6} | {'Tainted':<8} | {'Share Recalled':<16} | {'Duration'}")
    print("-" * 90)
    for m in report.incidents:
        print(f"{m.incident_id:<22} | {m.total_units:<6} | {m.naive_recall_units:<6} | {m.tainted_units:<8} | {m.share_recalled*100:>12.2f}% | {m.duration_ms:.2f} ms")
    print(f"{'='*90}\n")
