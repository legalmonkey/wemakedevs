"""Demand 2 Verification Suite: S3 Rerun on Scaled Topology (min_independent 0 to 4).

Verifies:
(1) Rerun S3 for min_independent 0 to 4 on the scaled topology.
(2) Prints each decision's valid independent groups and verdict in a clean formatted table.
(3) Asserts that Adjudicator verdicts equal the hand-computed policy:
    If valid_independent_groups >= min_independent -> reaffirmed
    Else -> tainted
"""

import pytest
from contracts.ontology import NodeRole
from engine.falkordb_client import FalkorDBGraphClient
from engine.generator import FoodGraphGenerator
from agents.adjudicator import AdjudicatorAgent


def test_s3_scaled_topology_min_independent_0_to_4():
    """Rerun S3 for min_independent 0 to 4 on scaled topology, asserting verdicts equal hand policy."""
    seed = 4242
    
    # 1. Generate scaled topology (30 units, 15 decisions, 3 product families)
    client = FalkorDBGraphClient(tenant_id=f"test-s3-scaled-{seed}", clean=True)
    generator = FoodGraphGenerator(seed=seed, num_units=30, num_decisions=15, num_product_families=3)
    gen_data = generator.generate(graph_client=client)

    decisions = gen_data["decisions"]
    assert len(decisions) >= 15, f"Scaled topology must have >= 15 decisions, got {len(decisions)}"

    # 2. Simulate fault injection: test 0 drifts (invalidated)
    drifted_test_id = gen_data["tests"][0]
    client.update_node(drifted_test_id, {"valid": False, "status": "drifted"})

    print(f"\n{'='*105}")
    print(f"DEMAND 2: S3 POLICY RERUN ON SCALED TOPOLOGY (SEED {seed}, 15 DECISIONS, 30 UNITS)")
    print(f"Fault injected on Evidence: {drifted_test_id} (valid=False)")
    print(f"{'='*105}")

    # 3. Evaluate for min_independent 0, 1, 2, 3, 4
    for min_indep in [0, 1, 2, 3, 4]:
        # Reset decisions to unadjudicated state
        for dec_id in decisions:
            client.update_node(dec_id, {"verdict_set": False, "verdict": "pending", "status": "pending"})

        # Run Adjudicator with current min_independent threshold
        adj = AdjudicatorAgent(tenant_id=client.tenant_id, graph_client=client)
        adj.min_independent = min_indep
        adj.step()

        print(f"\n--- THRESHOLD: min_independent = {min_indep} ---")
        print(f"{'Decision ID':<30} | {'Groups':<8} | {'Valid':<6} | {'min_indep':<9} | {'Adj Verdict':<12} | {'Hand Policy':<12} | {'Match?'}")
        print("-" * 105)

        for dec_id in decisions:
            # Query support to determine valid independent groups
            sup_res = client.support(dec_id)
            valid_groups_count = sup_res.data.independent_groups_count
            total_supports = len(sup_res.data.supports)

            # Hand-computed policy (Section 4: Reaffirm >= min_indep, elif unverifiable > 0 -> unverifiable, else tainted)
            unverifiable_count = sup_res.data.unverifiable_count
            if valid_groups_count >= min_indep:
                hand_verdict = "reaffirmed"
            elif unverifiable_count > 0:
                hand_verdict = "unverifiable"
            else:
                hand_verdict = "tainted"

            # Adjudicator verdict recorded in FalkorDB
            dec_node = client.nodes[dec_id]
            adj_verdict = dec_node.properties.get("verdict")
            matches = (adj_verdict == hand_verdict)

            print(f"{dec_id:<30} | {total_supports:<8} | {valid_groups_count:<6} | {min_indep:<9} | {adj_verdict:<12} | {hand_verdict:<12} | {'PASS' if matches else 'FAIL'}")

            # Strict assertion
            assert adj_verdict == hand_verdict, (
                f"Policy mismatch for decision '{dec_id}' under min_independent={min_indep}! "
                f"Valid groups: {valid_groups_count}, Adjudicator: {adj_verdict}, Hand policy: {hand_verdict}"
            )

    print(f"\n{'='*105}")
    print("ALL 75 DECISION ADJUDICATIONS (15 decisions x 5 thresholds) MATCH HAND-COMPUTED POLICY EXACTLY!")
    print(f"{'='*105}\n")
