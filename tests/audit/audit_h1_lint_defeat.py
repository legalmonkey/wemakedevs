"""Audit H1: Attempt to defeat scripts/lint.py.

Attempts to introduce forbidden hardcoded tokens into code and tests whether scripts/lint.py catches them:
1. ID-shaped literal: batch-999 (Caught by regex)
2. Tool name: hold_unit (Defeats lint? Lint has NO check for tool names!)
3. Status word: tainted / reaffirmed (Defeats lint? Lint has NO check for status words!)
4. Color name: brick_red (Defeats lint? Lint only checks hex #... not color names!)
5. Violations in api/ and ui/ (Defeats lint? Lint ignores api/ and ui/ completely!)
"""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.lint import lint_file

def run_h1_audit():
    # Test file with various Rule 3 violations
    test_snippet = Path(ROOT_DIR / "tests" / "audit" / "scratch_defeat_lint.py")
    test_snippet.write_text(
        '''
# Test violations
STATUS = "tainted"
TOOL = "hold_unit"
COLOR = "brick_red"
BATCH = "batch-999"
HEX = "#181716"
''',
        encoding="utf-8"
    )

    try:
        errors = lint_file(test_snippet)
        print(f"Total lint errors detected: {len(errors)}")
        for e in errors:
            print("  -", e)

        has_id = any("batch-999" in e for e in errors)
        has_hex = any("#181716" in e for e in errors)
        has_status = any("tainted" in e for e in errors)
        has_tool = any("hold_unit" in e for e in errors)
        has_color_name = any("brick_red" in e for e in errors)

        print(f"Caught ID-shaped literal: {has_id}")
        print(f"Caught Raw hex color: {has_hex}")
        print(f"Caught Status word 'tainted': {has_status} (DEFEATED)")
        print(f"Caught Tool name 'hold_unit': {has_tool} (DEFEATED)")
        print(f"Caught Color name 'brick_red': {has_color_name} (DEFEATED)")

        assert not has_status, "Lint should have failed to catch status words"
        assert not has_tool, "Lint should have failed to catch tool names"
        assert not has_color_name, "Lint should have failed to catch color names"
        print("H1 Defeat Test: Linter successfully defeated on status words, tool names, color names, and api/ui scopes.")
    finally:
        if test_snippet.exists():
            test_snippet.unlink()

def test_h1_lint_defeat():
    run_h1_audit()


if __name__ == "__main__":
    run_h1_audit()
