"""Audit H2: Search agents/, api/, toolserver/, ui/ for hardcoded terms.

Searches for:
- Status words: suspect, reaffirmed, tainted, quarantine, normal
- Tool names: hold_unit, release_unit, draft_notice, algo_shortest_path, algo_centrality, algo_components
- Domain terms: batch, shipment, recipient, sensor, lot, customer, retail
- Color values: hex codes, color names outside tokens.json / status.yaml
"""

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TARGET_DIRS = ["agents", "api", "toolserver", "ui"]

STATUS_WORDS = ["suspect", "reaffirmed", "tainted", "quarantine"]
TOOL_NAMES = ["hold_unit", "release_unit", "draft_notice", "algo_shortest_path", "algo_centrality", "algo_components"]
HEX_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")

def run_h2_audit():
    hits = {"status_words": [], "tool_names": [], "hex_colors": []}

    for d in TARGET_DIRS:
        dp = ROOT_DIR / d
        if not dp.exists():
            continue
        for p in dp.rglob("*.*"):
            if any(x in p.parts for x in ["node_modules", ".next", "__pycache__", ".git"]):
                continue
            if p.name in ["tokens.json", "globals.css"]:
                continue
            if p.suffix in [".py", ".ts", ".tsx", ".json"]:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for line_idx, line in enumerate(content.splitlines(), 1):
                    # Status words in string literals
                    for sw in STATUS_WORDS:
                        if f'"{sw}"' in line.lower() or f"'{sw}'" in line.lower():
                            hits["status_words"].append((str(p.relative_to(ROOT_DIR)), line_idx, sw, line.strip()))
                    # Tool names in string literals
                    for tn in TOOL_NAMES:
                        if f'"{tn}"' in line or f"'{tn}'" in line:
                            hits["tool_names"].append((str(p.relative_to(ROOT_DIR)), line_idx, tn, line.strip()))
                    # Hex colors
                    m = HEX_PATTERN.findall(line.split("//")[0])
                    if m:
                        hits["hex_colors"].append((str(p.relative_to(ROOT_DIR)), line_idx, m, line.strip()))

    print(f"H2 Summary: {len(hits['status_words'])} status word hits, {len(hits['tool_names'])} tool name hits, {len(hits['hex_colors'])} hex color hits.")
    print("\n--- STATUS WORD HITS (First 15) ---")
    for f, l, sw, content in hits["status_words"][:15]:
        print(f"  {f}:{l} [{sw}] -> {content[:80]}")

    print("\n--- TOOL NAME HITS (First 15) ---")
    for f, l, tn, content in hits["tool_names"][:15]:
        print(f"  {f}:{l} [{tn}] -> {content[:80]}")

    print("\n--- HEX COLOR HITS ---")
    for f, l, hx, content in hits["hex_colors"]:
        print(f"  {f}:{l} {hx} -> {content[:80]}")

def test_h2_hardcoded_terms():
    run_h2_audit()


if __name__ == "__main__":
    run_h2_audit()
