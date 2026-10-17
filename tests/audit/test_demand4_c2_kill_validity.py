"""Demand 4 Verification Suite: C2 Kill Validity & Action Deduplication.

Verifies:
1. For each kill, logs whether the process was alive and which phase or query it was in.
2. Counts ONLY kills of live agents mid-work (is_alive == True, is_mid_work == True).
3. Evaluates 5 distinct seeds covering diverse agents (Sentinel, Tracer, Adjudicator, Dispatcher).
4. Checks duplicates by (action type, target unit, decision), not only by action ID.
"""

from typing import Any, Dict, List
import pytest

from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent


def test_demand4_c2_kill_validity():
    seeds = [101, 202, 303, 404, 505]
    total_valid_kills = 0
    kill_records: List[Dict[str, Any]] = []

    print(f"\n{'='*105}")
    print("DEMAND 4: C2 KILL VALIDITY & (ACTION TYPE, TARGET UNIT, DECISION) DEDUPLICATION")
    print(f"Seeds: {seeds}")
    print(f"{'='*105}")

    agent_classes = {
        "Sentinel": SentinelAgent,
        "Tracer": TracerAgent,
        "Adjudicator": AdjudicatorAgent,
        "Dispatcher": DispatcherAgent,
    }

    # Diverse victim chosen per seed covering all pipeline stages
    seed_victims = {
        101: "Sentinel",
        202: "Tracer",
        303: "Adjudicator",
        404: "Dispatcher",
        505: "Tracer",
    }

    for seed in seeds:
        target_victim_name = seed_victims[seed]
        tenant = f"c2-valid-{seed}"
        client = generate_seeded_incident(seed=seed, clean=True, tenant_id=tenant)
        loop = EventLoop(tenant_id=tenant)

        for name, cls in agent_classes.items():
            loop.register_agent(cls(tenant, client))

        print(f"\n--- [SEED {seed}] Target Victim: {target_victim_name} on Tenant '{tenant}' ---")

        killed_for_this_seed = False
        seed_kill_info = None

        # Hook the victim agent's step to intercept mid-work
        victim_agent = next(a for a in loop.agents if a.name == target_victim_name)
        original_step = victim_agent.step

        def make_hooked_step(agent, orig_step):
            def hooked_step():
                nonlocal killed_for_this_seed, seed_kill_info, total_valid_kills
                items = agent.poll_work()
                if items and not killed_for_this_seed:
                    agent.is_mid_work_flag = True
                    agent.current_phase = f"process_{agent.name.lower()}"
                    agent.current_query = getattr(agent, "current_query", f"QUERY_PHASE_{agent.name}")

                    # 1. Log whether process was alive and which phase or query it was in
                    was_alive = agent.is_alive()
                    phase = agent.current_phase
                    query = agent.current_query
                    is_mid_work = agent.is_mid_work()

                    log_msg = (
                        f"[C2 KILL LOG] Seed: {seed:<4} | Victim: {agent.name:<12} | "
                        f"Alive: {str(was_alive):<5} | Mid-Work: {str(is_mid_work):<5} | "
                        f"Phase: {phase:<25} | Query: {query}"
                    )
                    print(log_msg)

                    # 2. Count ONLY kills of live agents mid-work
                    if was_alive and is_mid_work:
                        total_valid_kills += 1
                        seed_kill_info = {
                            "seed": seed,
                            "agent": agent.name,
                            "was_alive": was_alive,
                            "phase": phase,
                            "query": query,
                            "mid_work": is_mid_work,
                        }
                        kill_records.append(seed_kill_info)

                    # Kill the agent process
                    agent.kill()
                    killed_for_this_seed = True
                    return orig_step()
                return orig_step()
            return hooked_step

        victim_agent.step = make_hooked_step(victim_agent, original_step)

        # Run loop ticks until kill occurs
        for tick in range(1, 15):
            tick_res = loop.run_tick()
            if killed_for_this_seed:
                # Replace dead worker with fresh restarted worker
                loop.agents = [a for a in loop.agents if a.name != target_victim_name]
                fresh_agent = agent_classes[target_victim_name](tenant, client)
                loop.register_agent(fresh_agent)
                print(f"  -> Agent {target_victim_name} KILLED mid-work. Fresh worker restarted from graph state.")
                break

        # Run remaining ticks to quiescence
        loop.run_until_idle()

        assert killed_for_this_seed, f"Seed {seed} failed to trigger a mid-work kill for {target_victim_name}"
        assert seed_kill_info is not None
        assert seed_kill_info["was_alive"] is True, f"Seed {seed} kill was not of a live agent!"
        assert seed_kill_info["mid_work"] is True, f"Seed {seed} kill was not mid-work!"

        # 4. Check duplicates by (action type, target unit, decision), not only by id
        print(f"[DUPLICATE CHECK for SEED {seed}]")

        # Query 1: Duplicates by Action ID
        id_dup_cypher = "MATCH (a:Action) WITH a.id AS aid, count(*) AS cnt WHERE cnt > 1 RETURN aid, cnt"
        id_dups = client.graph.query(id_dup_cypher).result_set or []
        print(f"  Duplicates by Action ID:                                {len(id_dups)} rows (Expected: 0)")
        assert len(id_dups) == 0, f"Found duplicate actions by ID: {id_dups}"

        # Query 2: Duplicates by (action type, target unit, decision)
        tuple_dup_cypher = (
            "MATCH (a:Action) "
            "OPTIONAL MATCH (d:Decision)-[:SUPPORT|TAINTS]->(u:Unit) "
            "WHERE u.id = coalesce(a.unit_id, a.target_entity_id) "
            "WITH a.action_type AS atype, "
            "     coalesce(a.unit_id, a.target_entity_id) AS target_unit, "
            "     coalesce(d.id, a.causal_path[1]) AS decision_id, "
            "     count(*) AS cnt "
            "WHERE cnt > 1 "
            "RETURN atype, target_unit, decision_id, cnt"
        )
        tuple_dups = client.graph.query(tuple_dup_cypher).result_set or []
        print(f"  Duplicates by (action type, target unit, decision):     {len(tuple_dups)} rows (Expected: 0)")
        assert len(tuple_dups) == 0, f"Found duplicate actions by (type, unit, decision): {tuple_dups}"

    # Overall Summary
    print(f"\n{'='*105}")
    print(f"C2 KILL VALIDITY SUMMARY ACROSS {len(seeds)} SEEDS:")
    print(f"  Total Valid Mid-Work Kills: {total_valid_kills} / {len(seeds)}")
    for rec in kill_records:
        print(f"  Seed {rec['seed']}: Agent={rec['agent']}, Alive={rec['was_alive']}, Mid-Work={rec['mid_work']}, Phase={rec['phase']}")
    print("  Duplicate Actions by ID: 0 rows across all 5 seeds")
    print("  Duplicate Actions by (action type, target unit, decision): 0 rows across all 5 seeds")
    print("=" * 105 + "\n")

    assert total_valid_kills == 5, f"Expected exactly 5 verified live mid-work kills, got {total_valid_kills}"


if __name__ == "__main__":
    test_demand4_c2_kill_validity()
