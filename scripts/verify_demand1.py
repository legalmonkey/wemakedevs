"""Verification Script for Demand 1: Hidden-Link Recall, Ground Truth, and S2 Traversal."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import yaml

from engine.generator import FoodGraphGenerator
from engine.injector import FaultInjector
from engine.falkordb_client import FalkorDBGraphClient
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from engine.evaluation import EvaluationHarness


def run_demand1_verification():
    print("=" * 105)
    print("DEMAND 1: HIDDEN-LINK RECALL DEFINITION, 5-SEED PATHS, S2 LATERAL DISABLED, & 100-SEED BENCHMARK")
    print("=" * 105)
    print("FORMAL DEFINITION:")
    print("  Hidden-link recall is defined strictly as:")
    print("  'The injector's recorded lateral target received a TAINTS edge whose via_path contains")
    print("   the lateral edge or shared-lot node.'")
    print("  Ground truth is taken directly from the injector's recorded faults (injector.recorded_faults['lateral_fault']),")
    print("  NOT from arbitrary graph edges or post-hoc graph inspection.\n")

    # Step 1: Run 5 seeds and print the paths
    print("--- 1. 5 SEEDS' PATHS WITH GROUND TRUTH FROM INJECTOR RECORDED FAULTS ---")
    scenario_s1 = Path("scenarios/scenario_calibration_drift.yaml")
    sample_seeds = [1000, 1037, 1074, 1111, 1148]

    for seed in sample_seeds:
        client = FalkorDBGraphClient(tenant_id=f"tenant-d1-seed-{seed}", clean=True)
        gen = FoodGraphGenerator(seed=seed)
        gen.generate(graph_client=client)

        injector = FaultInjector.from_file(scenario_s1, seed=seed)
        fault_res = injector.inject(client)

        # Ground truth taken directly from injector's recorded fault dictionary
        lat_fault = injector.recorded_faults.get("lateral_fault", {})
        target_lat_unit = lat_fault.get("target_lateral_unit_id")
        shared_lot = lat_fault.get("shared_lot_id")
        source_unit = lat_fault.get("source_unit_id")

        loop = EventLoop(tenant_id=client.tenant_id)
        loop.register_agent(SentinelAgent(client.tenant_id, client))
        loop.register_agent(TracerAgent(client.tenant_id, client, allow_lateral=True))
        loop.register_agent(AdjudicatorAgent(client.tenant_id, client))
        loop.register_agent(DispatcherAgent(client.tenant_id, client))
        loop.run_until_idle(max_ticks=25)

        # OpenCypher query checking incoming TAINTS edge on the recorded lateral target unit
        q = (
            "MATCH (src)-[r:TAINTS]->(u:Unit {id: $target_id}) "
            "RETURN src.id AS source_id, type(r) AS rel_type, r.hops AS hops, r.via_path AS via_path"
        )
        res = client.graph.query(q, {"target_id": target_lat_unit})

        print(f"\nSeed: {seed}")
        print(f"  Injector Ground Truth Record (Fault Source -> Target):")
        print(f"    - Source Unit:             {source_unit}")
        print(f"    - Recorded Lateral Target: {target_lat_unit}")
        print(f"    - Shared Lot Ref:          {shared_lot}")
        print(f"  Cypher Query Result on FalkorDB:")
        matched = False
        if res.result_set:
            for row in res.result_set:
                src_id, rel_type, hops, via_path = row[0], row[1], row[2], row[3]
                has_lot = (shared_lot in via_path) or ("SHARED_LOT" in via_path)
                print(f"    -> Edge: ({src_id}) -[:{rel_type}]-> ({target_lat_unit})")
                print(f"       Hops:     {hops}")
                print(f"       via_path: {via_path}")
                print(f"       via_path contains lateral edge / shared-lot: {has_lot}")
                if has_lot:
                    matched = True
        print(f"  Recall Status for Seed {seed}: {'RECALLED (100%)' if matched else 'MISSED (0%)'}")
        assert matched, f"Seed {seed} failed to recall recorded lateral target with shared lot in via_path!"

    # Step 2: Rerun S2 (scenario_pathogen_adulteration.yaml) with lateral traversal disabled vs enabled
    print("\n" + "=" * 105)
    print("--- 2. RERUN S2 WITH LATERAL TRAVERSAL DISABLED AND SHOW RECALL DROPPING ---")
    scenario_s2 = Path("scenarios/scenario_pathogen_adulteration.yaml")

    for allow_lat in [True, False]:
        client = FalkorDBGraphClient(tenant_id=f"tenant-d1-s2-lat-{allow_lat}", clean=True)
        gen = FoodGraphGenerator(seed=2026)
        gen.generate(graph_client=client)

        injector = FaultInjector.from_file(scenario_s2, seed=2026)
        injector.inject(client)
        lat_fault = injector.recorded_faults.get("lateral_fault", {})
        target_lat = lat_fault.get("target_lateral_unit_id")
        shared_lot = lat_fault.get("shared_lot_id")

        loop = EventLoop(tenant_id=client.tenant_id)
        loop.register_agent(SentinelAgent(client.tenant_id, client))
        loop.register_agent(TracerAgent(client.tenant_id, client, allow_lateral=allow_lat))
        loop.register_agent(AdjudicatorAgent(client.tenant_id, client))
        loop.register_agent(DispatcherAgent(client.tenant_id, client))
        loop.run_until_idle(max_ticks=25)

        q = (
            "MATCH (src)-[r:TAINTS]->(u:Unit {id: $target_id}) "
            "RETURN src.id AS source_id, type(r) AS rel_type, r.hops AS hops, r.via_path AS via_path"
        )
        res = client.graph.query(q, {"target_id": target_lat})
        taints_received = len(res.result_set) if res.result_set else 0
        status_str = "ENABLED (allow_lateral=True)" if allow_lat else "DISABLED (allow_lateral=False)"
        print(f"\nScenario S2 Run [allow_lateral={allow_lat}]:")
        print(f"  Configuration:                {status_str}")
        print(f"  Recorded Lateral Target:      {target_lat}")
        print(f"  Shared Lot Node:              {shared_lot}")
        print(f"  Incoming TAINTS edges count:  {taints_received}")
        if taints_received > 0:
            print(f"  Retrieved via_path:           {res.result_set[0][3]}")
            print(f"  Hidden-Link Recall:           100.0% (RECALLED)")
        else:
            print(f"  Incoming TAINTS edge found:   NONE (Taint propagation blocked at lateral boundary)")
            print(f"  Hidden-Link Recall:           0.0% (DROPPED TO ZERO AS REQUIRED)")

    # Step 3: Run 100 seeds and report counts
    print("\n" + "=" * 105)
    print("--- 3. 100-SEED BENCHMARK: INJECTED, NOT-INJECTED, RECALLED, AND MISSED COUNTS ---")
    harness = EvaluationHarness(base_seed=7000)
    report = harness.run_100_seed_benchmark(num_seeds=100)
    s = report.large_summary

    print(f"Total Seeds Evaluated:                        {s.num_seeds}")
    print(f"Lateral Faults Injected (Ground Truth):       {s.lateral_injected_count}")
    print(f"Lateral Faults Recalled:                      {s.lateral_recalled_count}")
    print(f"Lateral Faults Missed:                        {s.lateral_missed_count}")
    print(f"Lateral Faults Not-Injected:                  {s.lateral_not_injected_count}")
    print(f"Hidden-Link Recall on Injected Seeds:         {s.hidden_link_recall_on_injected_pct:.1f}%")
    print(f"Mean Safe Release Rate:                       {s.safe_release_rate.mean * 100:.2f}%")
    print(f"Mean Share Recalled (Precision vs Naive):     {s.share_recalled.mean * 100:.2f}%")
    print(f"Total False Reaffirms:                        {s.total_false_reaffirms} (Strict Invariant: 0)")
    print("=" * 105 + "\n")


if __name__ == "__main__":
    run_demand1_verification()
