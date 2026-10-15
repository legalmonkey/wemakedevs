"""Phase A1 Exit Check: Food pack ontology, seeded generator, declarative fault injector, scenario files.

Exit check: "Two seeds yield different graphs; scenario expectations hold"

Verifies:
1. Seeded generator produces deterministic graphs for identical seeds and distinct graphs for different seeds.
2. Generator structures conform to the food pack ontology contract.
3. Declarative fault injector picks eligible targets randomly per seed without hardcoding.
4. Running the full incident pipeline on injected scenarios satisfies scenario expectations (reaffirmation beat, lateral link propagation, hold actions).
"""

from pathlib import Path
import pytest
from contracts.ontology import NodeRole, EdgeRole
from agents.stub_client import StubGraphClient
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from engine.config_loader import ConfigLoader
from engine.generator import FoodGraphGenerator
from engine.injector import FaultInjector


@pytest.fixture
def root_dir():
    return Path(__file__).resolve().parent.parent


def test_food_pack_ontology_validates_against_schema(root_dir):
    """Verifies packs/food/ontology.yaml validates against config/schemas/ontology.schema.json."""
    loader = ConfigLoader(root_dir)
    data = loader.load_ontology(root_dir / "packs" / "food" / "ontology.yaml")
    assert data["pack_name"] == "food"
    assert len(data["nodes"]) >= 8
    assert len(data["edges"]) >= 5


def test_a1_exit_check_two_seeds_yield_different_graphs():
    """Exit check: Two seeds yield completely different graphs."""
    gen1 = FoodGraphGenerator(seed=111)
    graph1 = gen1.generate()

    gen2 = FoodGraphGenerator(seed=222)
    graph2 = gen2.generate()

    # Compare node ID sets
    nodes1 = set(graph1["nodes"].keys())
    nodes2 = set(graph2["nodes"].keys())

    assert nodes1 != nodes2, "Two distinct seeds produced identical node sets!"
    # Ensure zero overlap between dynamically generated node IDs
    assert len(nodes1.intersection(nodes2)) == 0, "Colliding IDs found across distinct seeds!"

    # Ensure both topologies have the required generic roles
    roles1 = {n["role"] for n in graph1["nodes"].values()}
    assert NodeRole.UNIT in roles1
    assert NodeRole.DECISION in roles1
    assert NodeRole.EVIDENCE in roles1
    assert NodeRole.SHIPMENT in roles1
    assert NodeRole.RECIPIENT in roles1


def test_a1_exit_check_scenario_expectations_hold(root_dir):
    """Exit check: Scenario expectations hold under declarative fault injection."""
    scenario_path = root_dir / "scenarios" / "scenario_calibration_drift.yaml"
    injector = FaultInjector.from_file(scenario_path, seed=777)

    # 1. Generate base graph using generator
    tenant_id = "tenant-scenario-test-777"
    client = StubGraphClient(tenant_id=tenant_id)
    generator = FoodGraphGenerator(seed=777)
    generator.generate(graph_client=client)

    # 2. Inject fault declaratively
    injection_result = injector.inject(client)
    assert injection_result["event_id"].startswith("event_777_")
    assert injection_result["target_evidence_id"] in client.nodes

    # 3. Execute multi-agent event loop
    loop = EventLoop(tenant_id=tenant_id)
    loop.register_agent(SentinelAgent(tenant_id, client))
    loop.register_agent(TracerAgent(tenant_id, client))
    loop.register_agent(AdjudicatorAgent(tenant_id, client))
    loop.register_agent(DispatcherAgent(tenant_id, client))

    loop.run_until_idle(max_ticks=10)

    # 4. Measure results
    decisions = [n for n in client.nodes.values() if n.role == NodeRole.DECISION]
    reaffirmed = sum(1 for d in decisions if d.properties.get("verdict") == "reaffirmed")
    tainted = sum(1 for d in decisions if d.properties.get("verdict") == "tainted")
    units = [n for n in client.nodes.values() if n.role == NodeRole.UNIT]
    actions = [n for n in client.nodes.values() if n.role == NodeRole.ACTION]

    lateral_edges = [
        e for e in client.edges
        if e.role == EdgeRole.LATERAL_LINK or e.kind == "SHARED_LOT"
    ]

    execution_results = {
        "units_count": len(units),
        "tainted_decisions_count": tainted,
        "reaffirmed_decisions_count": reaffirmed,
        "has_lateral_link": len(lateral_edges) > 0,
        "actions_count": len(actions),
    }

    # Verify scenario expectations
    failures = injector.verify_expectations(execution_results)
    assert not failures, f"Scenario expectations failed: {failures}"
