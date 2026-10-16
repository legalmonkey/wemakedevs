"""True Production Mutation Testing Pipeline (Demand 4).

Executes the strict protocol required by Demand (4):
For each bug:
1. Actually patches the production file on disk.
2. Runs the existing production test suite via pytest.
3. Asserts and shows that the exact test FAILS loudly.
4. Restores the production file cleanly using git checkout.
5. Verifies that the test PASSES cleanly on restored production code.
"""

import subprocess
import sys
import os
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent


def run_cmd(cmd_list):
    res = subprocess.run(
        cmd_list,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
    )
    return res.returncode, res.stdout + res.stderr


def git_checkout(file_rel_path):
    subprocess.run(["git", "checkout", "--", file_rel_path], cwd=str(WORKSPACE), check=True)


def patch_file(file_rel_path, old_text, new_text):
    full_path = WORKSPACE / file_rel_path
    content = full_path.read_text(encoding="utf-8")
    assert old_text in content, f"Target text not found in {file_rel_path}: {old_text[:50]}..."
    patched = content.replace(old_text, new_text, 1)
    full_path.write_text(patched, encoding="utf-8")


def main():
    print("=" * 105)
    print("DEMAND 4: TRUE PRODUCTION MUTATION TESTING (PATCH -> RUN TEST -> PROVE FAILURE -> RESTORE -> PROVE PASS)")
    print("=" * 105)

    mutations = [
        {
            "id": "MUT-1",
            "name": "Outcome Token Leakage in ID Generator",
            "file": "engine/generator.py",
            "target": 'return f"{kind.lower()}_{seed}_{digest}"',
            "patch": 'return f"{kind.lower()}_{seed}_reaff_{digest}"',
            "test_cmd": [sys.executable, "-m", "pytest", "tests/audit/test_adversarial_audit.py", "-k", "test_a4_variety_distinct_signatures", "-v", "--no-cov"],
            "expected_fail_str": "AssertionError",
        },
        {
            "id": "MUT-2",
            "name": "Sabotaged S3 Adjudicator Policy (Inverted Rule)",
            "file": "agents/adjudicator.py",
            "target": 'verdict = "reaffirmed"\n        elif unverifiable_count > 0:',
            "patch": 'verdict = "tainted"\n        elif unverifiable_count > 0:',
            "test_cmd": [sys.executable, "-m", "pytest", "tests/audit/test_demand2_s3_scaled.py", "-v", "--no-cov"],
            "expected_fail_str": "AssertionError",
        },
        {
            "id": "MUT-3",
            "name": "Inconsistent Relationship Name ('ships-in' vs 'SHIPS_IN')",
            "file": "engine/generator.py",
            "target": 'add_edge(shipped_batch, shipment_id, "SHIPS_IN", EdgeRole.SHIPS_IN)',
            "patch": 'add_edge(shipped_batch, shipment_id, "ships-in", EdgeRole.SHIPS_IN)',
            "test_cmd": [sys.executable, "-m", "pytest", "tests/audit/test_demand3_gates_consistent.py", "-v", "--no-cov"],
            "expected_fail_str": "AssertionError",
        },
        {
            "id": "MUT-4",
            "name": "Suppress ValueError on Zero-Node MATCH Edge Creation",
            "file": "engine/falkordb_client.py",
            "target": 'if not res.relationships_created or res.relationships_created == 0:\n            raise ValueError(',
            "patch": 'if False and (not res.relationships_created or res.relationships_created == 0):\n            raise ValueError(',
            "test_cmd": [sys.executable, "-m", "pytest", "tests/audit/test_demand4_match_zero_nodes.py", "-k", "test_edge_creation_fails_if_match_matches_zero_nodes", "-v", "--no-cov"],
            "expected_fail_str": "Failed: DID NOT RAISE <class 'ValueError'>",
        },
        {
            "id": "MUT-5",
            "name": "Bypass Gate Race Invariant in hold_unit Cypher Query",
            "file": "config/gates.yaml",
            "target": "WHERE u.is_tainted = true AND coalesce(u.status, '') <> 'reaffirmed' AND coalesce(u.verdict, '') <> 'reaffirmed'",
            "patch": "WHERE u.is_tainted = true",
            "test_cmd": [sys.executable, "-m", "pytest", "tests/audit/test_demand5_race_and_notice_gate.py", "-k", "test_race_reaffirmed_unit_never_held_or_noticed_under_any_interleaving", "-v", "--no-cov"],
            "expected_fail_str": "AssertionError",
        },
        {
            "id": "MUT-6",
            "name": "Bypass Recipient Path Verification in draft_notice Gate",
            "file": "config/gates.yaml",
            "target": "MATCH (u:Unit {id: $entity_id})-[:SHIPS_IN]->(s:Shipment)-[:DELIVERED_TO]->(r:Recipient {id: $recipient_id})",
            "patch": "MATCH (u:Unit {id: $entity_id})-[:SHIPS_IN]->(s:Shipment)",
            "test_cmd": [sys.executable, "-m", "pytest", "tests/audit/test_demand5_race_and_notice_gate.py", "-k", "test_draft_notice_verifies_delivered_to_path_for_customer", "-v", "--no-cov"],
            "expected_fail_str": "AssertionError",
        },
    ]

    all_passed = True
    for mut in mutations:
        m_id = mut["id"]
        m_name = mut["name"]
        m_file = mut["file"]
        print(f"\n{'='*105}")
        print(f"[{m_id}] {m_name}")
        print(f"Target Production File: {m_file}")
        print(f"{'='*105}")

        # Step A: Patch production file
        print(f"Step 1: Applying bug mutation to production code {m_file}...")
        try:
            patch_file(m_file, mut["target"], mut["patch"])
            print("  Mutation applied successfully.")

            # Step B: Run existing test suite on mutated code
            print(f"Step 2: Running matching test: {' '.join(mut['test_cmd'][-4:])}...")
            code_mut, out_mut = run_cmd(mut["test_cmd"])

            print(f"Step 3: Evaluating test result on mutated code (Exit Code: {code_mut}):")
            if code_mut != 0 and (mut["expected_fail_str"] in out_mut or "FAILED" in out_mut):
                print(f"  >>> SUCCESS: Existing test FAILED as expected on mutated production code! <<<")
                # Print relevant failure line
                for line in out_mut.splitlines():
                    if "FAILED" in line or "AssertionError" in line or "DID NOT RAISE" in line or "Error:" in line:
                        print(f"      [Failure Output]: {line.strip()}")
            else:
                print(f"  >>> CRITICAL FAILURE: Test unexpectedly PASSED on mutated code! <<<")
                all_passed = False
        finally:
            # Step C: Restore production file cleanly via git checkout
            print(f"Step 4: Restoring clean production file via git checkout -- {m_file}...")
            git_checkout(m_file)
            print("  Clean production file restored.")

        # Step D: Confirm test passes on restored production code
        print(f"Step 5: Verifying test PASSES on clean production code...")
        code_clean, out_clean = run_cmd(mut["test_cmd"])
        if code_clean == 0:
            print(f"  >>> SUCCESS: Test PASSED on restored clean production code! <<<")
        else:
            print(f"  >>> ERROR: Test failed on clean code! Exit code: {code_clean} <<<")
            all_passed = False

    print(f"\n{'='*105}")
    if all_passed:
        print("ALL 6 PRODUCTION MUTATION CHECKS COMPLETED AND VERIFIED: EVERY MUTATION FAILED LOUDLY & PASSED CLEANLY!")
    else:
        print("ONE OR MORE MUTATION CHECKS FAILED VERIFICATION!")
    print(f"{'='*105}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
