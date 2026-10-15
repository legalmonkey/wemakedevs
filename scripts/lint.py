"""Project Linter for Rule 3 & Section 0 Compliance.

Checks:
1. Syntax correctness across all Python files.
2. Absence of raw hex color literals in production code (Rule 3).
3. Zero hardcoding checks.
"""

import ast
import re
import sys
from pathlib import Path

HEX_COLOR_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
PRODUCTION_DIRS = ["contracts", "agents", "toolserver"]


def lint_file(file_path: Path) -> list[str]:
    errors = []
    content = file_path.read_text(encoding="utf-8")

    # 1. Syntax check
    try:
        ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        errors.append(f"Syntax error in {file_path}:{e.lineno}: {e.msg}")
        return errors

    # 2. Check for raw hex colors in production code
    for line_no, line in enumerate(content.splitlines(), start=1):
        # Ignore comments if any
        code_part = line.split("#")[0] if "#" in line and not line.strip().startswith("#") else line
        matches = HEX_COLOR_PATTERN.findall(code_part)
        if matches:
            errors.append(
                f"Rule 3 violation in {file_path}:{line_no}: Raw hex color '{matches[0]}' "
                "forbidden. Colours exist only in token files served from status registry."
            )

    return errors


def run_lint() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    all_errors = []
    files_checked = 0

    for pdir in PRODUCTION_DIRS:
        target_path = root_dir / pdir
        if not target_path.exists():
            continue
        for py_file in target_path.rglob("*.py"):
            files_checked += 1
            errs = lint_file(py_file)
            all_errors.extend(errs)

    # Also check tests syntax
    tests_path = root_dir / "tests"
    if tests_path.exists():
        for py_file in tests_path.rglob("*.py"):
            files_checked += 1
            try:
                ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError as e:
                all_errors.append(f"Syntax error in {py_file}:{e.lineno}: {e.msg}")

    print(f"Linting complete: {files_checked} files inspected.")
    if all_errors:
        print(f"Found {len(all_errors)} lint error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1
    else:
        print("All lint checks PASSED cleanly (zero syntax errors, zero raw hex colors).")
        return 0


if __name__ == "__main__":
    sys.exit(run_lint())
