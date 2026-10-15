"""Lint test ensuring compliance with Section 0 Rule 3 & syntax integrity."""

from scripts.lint import run_lint


def test_project_lint():
    exit_code = run_lint()
    assert exit_code == 0, "Lint checks failed"
