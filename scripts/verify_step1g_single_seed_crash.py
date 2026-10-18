import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.verify_item3_real_crash_safety import run_process_incident

def verify_single_seed_crash_safety(seed: int = 404):
    print("=" * 80)
    print(f"STEP 1g: OS-PROCESS KILL TEST (SEED {seed})")
    print("=" * 80)

    # 1. Baseline uninterrupted run
    t_base = f"t-step1g-base-{seed}"
    print(f"Running baseline uninterrupted run on tenant: {t_base}...")
    t0 = time.perf_counter()
    hash_base, client_base, dupes_base = run_process_incident(seed=seed, tenant_id=t_base)
    t_base_elapsed = time.perf_counter() - t0
    print(f"Baseline completed in {t_base_elapsed:.2f}s")
    print(f"Baseline Canonical Graph Hash: {hash_base}")
    print(f"Baseline Duplicate Actions:     {dupes_base}")

    # 2. Mid-work kill on TracerAgent (kill after 0.08s, restarted immediately)
    t_kill = f"t-step1g-kill-{seed}"
    print(f"\nRunning mid-work OS-process kill on tenant: {t_kill} (Victim: TracerAgent killed at t=0.08s)...")
    t0_k = time.perf_counter()
    hash_kill, client_kill, dupes_kill = run_process_incident(
        seed=seed,
        tenant_id=t_kill,
        kills=[("Tracer", 0.08)],
    )
    t_kill_elapsed = time.perf_counter() - t0_k
    print(f"Kill run completed in {t_kill_elapsed:.2f}s")
    print(f"Kill Run Canonical Graph Hash: {hash_kill}")
    print(f"Kill Run Duplicate Actions:     {dupes_kill}")

    # 3. Compare hashes bit-for-bit
    match = (hash_kill == hash_base)
    print("\n" + "-" * 80)
    print(f"Hash Match: {match}")
    print(f"Baseline Hash: {hash_base}")
    print(f"Kill Run Hash: {hash_kill}")
    print(f"Duplicate Actions: {dupes_kill}")
    print("-" * 80)

    if match and dupes_kill == 0:
        print("\nRESULT: PASS")
    else:
        print("\nRESULT: FAIL")
        sys.exit(1)

if __name__ == "__main__":
    verify_single_seed_crash_safety()
