"""Phase A3 Exit Check: Golden-file tests for templates, property test for decision reaffirmation.

Exit check: "Property test passes on random graphs"

Verifies:
1. Golden-file tests: Dynamic query builder templates match verified golden Cypher templates.
2. Property test: A decision is NEVER reaffirmed while policy-required independent support is absent.
   Verified over 100 randomized graphs with random evidence groups, random validities,
   and random policy thresholds.
3. Integration support: Multi-agent loop (B's agents) executes smoothly against Part A's QueryAPI.
"""

from pathlib import Path
import random
import pytest
from contracts.ontology import NodeRole, EdgeRole
from engine.falkordb_client import FalkorDBGraphClient
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from engine.config_loader import ConfigLoader
from engine.generator import FoodGraphGenerator
from engine.query_builder import QueryBuilder
from engine.query_api_impl import QueryAPI


@pytest.fixture
def root_dir():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def loader(root_dir):
    return ConfigLoader(root_dir)


# --- 1. Golden-File Template Tests ---


def test_golden_file_query_templates(root_dir, loader):
    """Verifies rendered Cypher queries strictly match deterministic golden file templates."""
    golden_dir = root_dir / "fixtures" / "golden"

    food_onto = loader.load_ontology(root_dir / "packs" / "food" / "ontology.yaml")
    food_builder = QueryBuilder(food_onto)

    # Food trace query
    actual_food_trace = food_builder.build_trace_query()
    expected_food_trace = (golden_dir / "food_trace_query.cyp").read_text(encoding="utf-8").strip()
    assert actual_food_trace == expected_food_trace, "Food trace query diverged from golden template!"

    # Food support query
    actual_food_support = food_builder.build_support_query()
    expected_food_support = (golden_dir / "food_support_query.cyp").read_text(encoding="utf-8").strip()
    assert actual_food_support == expected_food_support, "Food support query diverged from golden template!"

    # Food exposure query
    actual_food_exp = food_builder.build_exposure_query()
    expected_food_exp = (golden_dir / "food_exposure_query.cyp").read_text(encoding="utf-8").strip()
    assert actual_food_exp == expected_food_exp, "Food exposure query diverged from golden template!"

    # Pharma trace query
    pharma_onto = loader.load_ontology(root_dir / "packs" / "pharma" / "ontology.yaml")
    pharma_builder = QueryBuilder(pharma_onto)

    actual_pharma_trace = pharma_builder.build_trace_query()
    expected_pharma_trace = (golden_dir / "pharma_trace_query.cyp").read_text(encoding="utf-8").strip()
    assert actual_pharma_trace == expected_pharma_trace, "Pharma trace query diverged from golden template!"


# --- 2. Property-Based Test: Reaffirmation Invariant on Random Graphs ---


def test_a3_exit_check_property_never_reaffirm_without_independent_support():
    """Exit check: A decision is NEVER reaffirmed while policy-required independent support is absent.
    
    Property Invariant:
    For any graph G, for any Decision D, with policy min_independent = K:
    - If valid independent groups count < K, verdict is NEVER 'reaffirmed' (must be 'tainted' or 'unverifiable').
    - If and only if valid independent groups count >= K, verdict is 'reaffirmed'.
    """
    rng = random.Random(9999)

    for iteration in range(100):
        tenant_id = f"tenant-prop-{iteration}"
        client = FalkorDBGraphClient(tenant_id=tenant_id)

        min_independent = rng.randint(1, 4)
        decision_id = f"dec_{iteration}_{rng.randint(100, 999)}"

        # Create Decision node initially tainted
        client.add_node(
            node_id=decision_id,
            kind="QualityDecision",
            role=NodeRole.DECISION,
            properties={"is_tainted": True, "verdict": "initial"},
        )

        evidence_count = rng.randint(0, 8)
        evidence_nodes = []
        valid_groups = set()
        has_unverifiable = False

        for i in range(evidence_count):
            ev_id = f"ev_{iteration}_{i}"
            is_unverifiable = rng.choice([False, False, False, True])  # 25% chance
            is_valid = False if is_unverifiable else rng.choice([True, False])
            group_id = f"grp_{rng.randint(1, max(1, evidence_count // 2 + 1))}"

            if is_unverifiable:
                has_unverifiable = True
            elif is_valid:
                valid_groups.add(group_id)

            client.add_node(
                node_id=ev_id,
                kind="LabTest",
                role=NodeRole.EVIDENCE,
                properties={
                    "valid": is_valid,
                    "unverifiable": is_unverifiable,
                    "group_id": group_id,
                },
            )
            client.add_edge(ev_id, decision_id, "SUPPORTS", EdgeRole.SUPPORT)
            evidence_nodes.append(ev_id)

        # Instantiate Adjudicator with dynamic min_independent
        adjudicator = AdjudicatorAgent(tenant_id=tenant_id, graph_client=client)
        adjudicator.min_independent = min_independent

        work_items = adjudicator.poll_work()
        assert len(work_items) == 1

        adjudicator.process_item(work_items[0])

        dec_node = client.nodes[decision_id]
        verdict = dec_node.properties.get("verdict")
        actual_valid_groups = len(valid_groups)

        # STRICT PROPERTY INVARIANT ASSERTIONS:
        if actual_valid_groups < min_independent:
            assert verdict != "reaffirmed", (
                f"VIOLATION: Decision was reaffirmed with only {actual_valid_groups} valid groups "
                f"when min_independent={min_independent} in iteration {iteration}!"
            )
            if has_unverifiable:
                assert verdict == "unverifiable", (
                    f"Expected unverifiable, got {verdict} with unverifiable evidence present."
                )
            else:
                assert verdict == "tainted", (
                    f"Expected tainted, got {verdict} when valid groups {actual_valid_groups} < {min_independent}."
                )
        else:
            assert verdict == "reaffirmed", (
                f"Expected reaffirmed with {actual_valid_groups} valid groups >= {min_independent}, got {verdict}."
            )


# --- 3. Integration with Part B's Agents ---


def test_a3_part_b_multi_agent_integration(root_dir, loader):
    """Verifies Part B's agents run smoothly against Part A's QueryAPI on generated incident."""
    food_onto = loader.load_ontology(root_dir / "packs" / "food" / "ontology.yaml")
    query_builder = QueryBuilder(food_onto)

    tenant_id = "tenant-a3-integration"
    client = FalkorDBGraphClient(tenant_id=tenant_id)
    gen = FoodGraphGenerator(seed=303)
    gen.generate(graph_client=client)

    api = QueryAPI(graph_client=client, query_builder=query_builder)

    # Trigger incident on lab/sensor evidence node
    suspect_candidates = [
        n for n in client.nodes.values()
        if n.kind in ("SensorLog", "LabTest")
    ]
    suspect_ev = suspect_candidates[0].node_id

    client.add_node(
        node_id="event_a3_integration",
        kind="AlertEvent",
        role=NodeRole.EVENT,
        properties={"processed": False, "target_evidence_id": suspect_ev},
    )

    loop = EventLoop(tenant_id=tenant_id)
    loop.register_agent(SentinelAgent(tenant_id, client))
    loop.register_agent(TracerAgent(tenant_id, client))
    loop.register_agent(AdjudicatorAgent(tenant_id, client))
    loop.register_agent(DispatcherAgent(tenant_id, client))

    ticks = loop.run_until_idle(max_ticks=10)
    assert len(ticks) >= 1

    # Verify QueryAPI can query the resulting graph state seamlessly
    trace_res = api.trace(suspect_ev)
    assert trace_res.result_size >= 1

    # Check that actions have retrievable explanation paths via QueryAPI
    actions = [n for n in client.nodes.values() if n.role == NodeRole.ACTION]
    assert len(actions) >= 1
    explain_res = api.explain(actions[0].node_id)
    assert explain_res.data.causal_path
    assert explain_res.data.path_hops >= 0
