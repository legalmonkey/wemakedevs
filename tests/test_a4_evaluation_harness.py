"""Phase A4 Exit Check: Evaluation harness and metric report generation.

Exit check: "Report generated end to end"

Verifies:
1. Evaluation harness executes across N randomised incidents on fresh seeds.
2. Computes the 6 core metrics:
   - precision versus naive recall (tainted batches over batches a naive recall would hit)
   - safe-release rate
   - false-reaffirm count (must be strictly 0 on generated ground truth)
   - hidden-link recall (target 100%)
   - time to scope (ms)
   - explanation coverage (target 100%)
3. Generates and exports standardized JSON report to fixtures/evaluation_report.json for Part C's UI evidence board.
"""

import json
from pathlib import Path
import pytest
from engine.evaluation import EvaluationHarness, EvaluationReport


@pytest.fixture
def root_dir():
    return Path(__file__).resolve().parent.parent


def test_a4_exit_check_report_generated_end_to_end(root_dir):
    """Exit check: Evaluation report generated end to end across N randomised incidents."""
    report_path = root_dir / "fixtures" / "evaluation_report.json"

    harness = EvaluationHarness(base_seed=5000)
    report = harness.generate_and_save_report(output_path=report_path, num_incidents=10)

    # 1. Verify report structure
    assert isinstance(report, EvaluationReport)
    assert report.num_incidents == 10
    assert len(report.incidents) == 10
    assert report_path.exists(), "Report JSON file was not saved to disk!"

    # 2. Verify exported JSON content
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["title"] == "Tainted Evaluation Benchmark Report"
    assert "timestamp" in data
    assert data["num_incidents"] == 10

    # 3. Acceptance criteria & metric assertions
    # False-reaffirm count MUST be strictly 0
    assert report.false_reaffirm_count == 0, f"VIOLATION: False reaffirm count is {report.false_reaffirm_count} (must be 0)!"
    assert data["false_reaffirm_count"] == 0

    # Precision vs naive recall: Tainted batches are a subset of blanket recall
    assert 0.0 < report.precision_vs_naive_recall <= 1.0
    assert report.precision_vs_naive_recall < 1.0, "Tainted system failed to demonstrate precision advantage over blanket recall!"

    # Safe release rate > 0 (reaffirmation demo beat verified)
    assert report.safe_release_rate > 0.0

    # Hidden-link recall target: 100%
    assert report.hidden_link_recall_pct == 100.0

    # Explanation coverage: 100% of dispatched actions have a stored causal path
    assert report.explanation_coverage_pct == 100.0

    # Time to scope: Measured honestly
    assert report.avg_time_to_scope_ms > 0.0
    for inc in report.incidents:
        assert inc.duration_ms > 0.0
        assert inc.total_units >= 3
        assert inc.explained_actions_count == inc.actions_count
