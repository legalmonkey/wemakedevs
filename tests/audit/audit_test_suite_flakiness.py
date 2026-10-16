"""Audit Check 2.7: Run test suite three times in random order and report flakiness."""
import random
import sys
import subprocess
from pathlib import Path

def get_test_files():
    files = sorted(list(Path("tests").glob("test_*.py")) + list(Path("tests/part_c").glob("test_*.py")))
    return [str(f) for f in files]

def main():
    print("AUDIT CHECK 2.7: Running test suite 3 times in random order...")
    test_files = get_test_files()
    print(f"Discovered {len(test_files)} test files.")
    
    seeds = [104729, 224737, 350377]
    run_results = []
    
    for i, s in enumerate(seeds, 1):
        shuffled = list(test_files)
        random.seed(s)
        random.shuffle(shuffled)
        print(f"\n--- RUN {i} (Seed: {s}) ---")
        cmd = [sys.executable, "-m", "pytest"] + shuffled + ["-q"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout.strip()
        last_line = out.splitlines()[-1] if out.splitlines() else "NO OUTPUT"
        print(f"Exit code: {res.returncode}")
        print(f"Summary: {last_line}")
        run_results.append((i, s, res.returncode, last_line))
        
    print("\n--- FLAKINESS REPORT ---")
    all_passed = all(r[2] == 0 for r in run_results)
    for r in run_results:
        print(f"Run {r[0]} (seed {r[1]}): exit {r[2]} -> {r[3]}")
    if all_passed:
        print("Flakiness detected: 0 tests flaky across 3 randomized runs (100% stable).")
    else:
        print("Flakiness detected! Some runs had non-zero exit codes.")

if __name__ == "__main__":
    main()
