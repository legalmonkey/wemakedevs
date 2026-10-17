"""Demand 5 Verification Suite: Scenario-Declared Naive Recall Rule & Recomputed Metrics.

Verifies:
(1) Zero regulatory citations in docs/AUDIT.md.
(2) Naive recall baseline is declared strictly by scenario rule ('all_facility_units').
(3) Evaluation metrics are recomputed across incidents and printed with raw metrics.
"""

from pathlib import Path
import re
import pytest
import yaml
from engine.evaluation import EvaluationHarness


ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_no_regulatory_citations_in_audit_doc():
    """Verify that regulatory citations (FDA 21 CFR, FSMA, cGMP) have been removed from AUDIT.md."""
    audit_file = ROOT_DIR / "docs" / "AUDIT.md"
    assert audit_file.exists()
    content = audit_file.read_text(encoding="utf-8")

    # Search for regulatory references in the audit doc
    banned_citations = ["21 CFR", "FSMA", "cGMP"]
    for citation in banned_citations:
        assert citation not in content, (
            f"Regulatory citation '{citation}' found in docs/AUDIT.md! Must define via scenario rule."
        )
    print("\n1. Confirmed: docs/AUDIT.md contains zero regulatory citations.")


def test_naive_recall_declared_in_scenarios():
    """Verify naive recall is defined strictly by declarative rule in scenario files."""
    scenario_dir = ROOT_DIR / "scenarios"
    scenario_files = list(scenario_dir.glob("scenario_*.yaml"))
    assert len(scenario_files) >= 2, "Expected at least 2 scenario files"

    for s_path in scenario_files:
        with open(s_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "naive_recall" in data, f"Scenario '{s_path.name}' lacks naive_recall block!"
        rule = data["naive_recall"].get("rule")
        assert rule in [
            "all_facility_units",
            "all batches touched by the affected instrument type in the window",
        ], f"Scenario '{s_path.name}' rule is '{rule}', expected valid declared scenario rule"
        print(f"2. Verified scenario '{s_path.name}': naive_recall.rule = '{rule}'")


def test_recompute_evaluation_metrics_via_scenario_rule():
    """Recompute evaluation metrics against live FalkorDB using declared scenario rule."""
    harness = EvaluationHarness(base_seed=5000)
    report = harness.run_benchmark(num_incidents=3)

    print(f"\n{'='*80}")
    print("DEMAND 5: RECOMPUTED FORENSIC BENCHMARK METRICS (SCENARIO-DECLARED RULE)")
    print(f"{'='*80}")
    print(f"Timestamp:                 {report.timestamp}")
    print(f"Number of Incidents:       {report.num_incidents}")
    print(f"Precision vs Naive Recall: {report.precision_vs_naive_recall * 100:.2f}% (Tainted / Naive Scope)")
    print(f"Safe Release Rate:         {report.safe_release_rate * 100:.2f}% (Reaffirmed / Total)")
    print(f"False Reaffirm Count:      {report.false_reaffirm_count} (Must be exactly 0)")
    print(f"Avg Time to Scope:         {report.avg_time_to_scope_ms:.2f} ms")
    print(f"Explanation Coverage:      {report.explanation_coverage_pct:.1f}%")
    print("-" * 80)
    print(f"{'Incident ID':<20} | {'Seed':<6} | {'Total':<6} | {'Naive':<6} | {'Tainted':<8} | {'Reaffirmed':<10} | {'Duration'}")
    print("-" * 80)
    for inc in report.incidents:
        print(f"{inc.incident_id:<20} | {inc.seed:<6} | {inc.total_units:<6} | {inc.naive_recall_units:<6} | {inc.tainted_units:<8} | {inc.reaffirmed_units:<10} | {inc.duration_ms:.2f} ms")
    print(f"{'='*80}\n")

    # Assertions
    assert report.false_reaffirm_count == 0, "Safety violation: false reaffirmations detected!"
    assert report.precision_vs_naive_recall > 0.0, "Invalid precision metric"
    assert report.explanation_coverage_pct == 100.0, "All containment actions must have full explanations"
