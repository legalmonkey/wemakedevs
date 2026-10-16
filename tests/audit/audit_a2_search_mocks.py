"""Audit A2: Search production paths for mocks, stubs, fakes, dummies, etc.

Target dirs: engine/, agents/, toolserver/, api/, ui/ (excluding ui/node_modules, ui/.next)
Target keywords: mock, stub, fake, dummy, sample, lorem, TODO, skip, xfail, hardcoded arrays of events, setTimeout
Classifies every hit as test-only or production.
"""

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TARGET_DIRS = ["engine", "agents", "toolserver", "api", "ui"]
KEYWORDS = ["mock", "stub", "fake", "dummy", "sample", "lorem", "TODO", "skip", "xfail", "setTimeout"]

def scan_file(file_path: Path):
    hits = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return hits

    lines = content.splitlines()
    for line_idx, line in enumerate(lines, 1):
        for kw in KEYWORDS:
            # case insensitive search with word boundary or substring
            pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            if pattern.search(line):
                # Classify
                classification = "TEST-ONLY" if "test" in str(file_path).lower() or file_path.name.startswith("test_") else "PRODUCTION"
                hits.append({
                    "file": str(file_path.relative_to(ROOT_DIR)),
                    "line": line_idx,
                    "keyword": kw,
                    "content": line.strip(),
                    "classification": classification,
                })
    return hits

def run_a2_audit():
    all_hits = []
    for d in TARGET_DIRS:
        dp = ROOT_DIR / d
        if not dp.exists():
            continue
        for p in dp.rglob("*.*"):
            if any(x in p.parts for x in ["node_modules", ".next", "__pycache__", ".git"]):
                continue
            if p.suffix in [".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml"]:
                all_hits.extend(scan_file(p))

    print(f"Total keyword hits found in production directories: {len(all_hits)}")
    prod_hits = [h for h in all_hits if h["classification"] == "PRODUCTION"]
    test_hits = [h for h in all_hits if h["classification"] == "TEST-ONLY"]
    print(f"Production path hits: {len(prod_hits)}")
    print(f"Test-only path hits: {len(test_hits)}")
    print("\n--- SAMPLE PRODUCTION HITS ---")
    for h in prod_hits[:30]:
        print(f"[{h['keyword'].upper()}] {h['file']}:{h['line']} -> {h['content'][:100]}")

    return all_hits


def test_a2_search_mocks():
    all_hits = run_a2_audit()
    code_mocks = [
        h for h in all_hits
        if h["classification"] == "PRODUCTION"
        and h["file"].endswith(".py")
        and not h["content"].startswith("#")
        and not h["content"].startswith("-")
    ]
    assert len(code_mocks) == 0, f"Found mock in production Python code: {code_mocks}"


if __name__ == "__main__":
    run_a2_audit()
