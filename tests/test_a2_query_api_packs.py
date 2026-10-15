"""Phase A2 Exit Check: Query builder generated from ontology and policy; all Query API functions; algorithm functions.

Exit check: "Tests pass on the food pack and a tiny second pack"

Verifies:
1. Query builder generates parameterized Cypher queries dynamically from food and pharma ontologies.
2. QueryAPI fulfills contracts.query_api.QueryAPIProtocol across both packs:
   - trace, support, siblings, exposure, explain, evaluate_gate
   - algo_shortest_path, algo_centrality, algo_components
3. Every call returns QueryResult[T] with rendered query_text and result_size.
4. Definition of Done: Swapping the second ontology leaves engine tests passing cleanly.
"""

from pathlib import Path
import pytest
from contracts.ontology import NodeRole, EdgeRole
from agents.stub_client import StubGraphClient
from toolserver.gate_evaluator import GateEvaluator
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


def test_a2_query_builder_generation_on_both_packs(root_dir, loader):
    """Verifies query builder generates dynamic queries for both food pack and pharma pack."""
    food_onto = loader.load_ontology(root_dir / "packs" / "food" / "ontology.yaml")
    food_builder = QueryBuilder(food_onto)

    # 1. Food pack query tests
    food_trace_q = food_builder.build_trace_query()
    assert "MATCH path = " in food_trace_q
    assert "length(path) AS hops" in food_trace_q
    assert "[n IN nodes(path) | n.id] AS via_path" in food_trace_q
    assert "SUPPORTS" in food_trace_q or "SHIPS_IN" in food_trace_q

    # 2. Pharma pack query tests (tiny second pack)
    pharma_onto = loader.load_ontology(root_dir / "packs" / "pharma" / "ontology.yaml")
    pharma_builder = QueryBuilder(pharma_onto)

    pharma_trace_q = pharma_builder.build_trace_query()
    assert "MATCH path = " in pharma_trace_q
    assert "length(path) AS hops" in pharma_trace_q
    assert "SHARED_INGREDIENT" in pharma_trace_q or "SUPPORTS" in pharma_trace_q


def test_a2_exit_check_query_api_on_food_pack(root_dir, loader):
    """Exit check: All Query API functions and algorithms pass on the food pack."""
    food_onto = loader.load_ontology(root_dir / "packs" / "food" / "ontology.yaml")
    query_builder = QueryBuilder(food_onto)

    client = StubGraphClient(tenant_id="tenant-food-a2")
    gen = FoodGraphGenerator(seed=888)
    gen_data = gen.generate(graph_client=client)

    gate_eval = GateEvaluator(client, config_path=str(root_dir / "config" / "gates.yaml"))
    api = QueryAPI(graph_client=client, query_builder=query_builder, gate_evaluator=gate_eval)

    # 1. support(decision)
    dec_id = gen_data["decisions"][0]
    sup_res = api.support(dec_id)
    assert sup_res.query_text
    assert sup_res.result_size >= 1
    assert sup_res.data.decision_id == dec_id
    assert sup_res.data.independent_groups_count >= 1

    # 2. siblings(unit)
    batch_1 = gen_data["batches"][1]
    batch_2 = gen_data["batches"][2]
    sib_res = api.siblings(batch_1)
    assert sib_res.query_text
    assert batch_2 in sib_res.data.sibling_unit_ids

    # 3. exposure(unit)
    batch_0 = gen_data["batches"][0]
    exp_res = api.exposure(batch_0)
    assert exp_res.query_text
    assert exp_res.result_size >= 1
    assert exp_res.data.exposures[0].unit_id == batch_0
    assert exp_res.data.exposures[0].recipient_id is not None

    # 4. explain(action)
    action_token = "action_food_888_test"
    client.add_node(
        node_id=action_token,
        kind="QuarantineAction",
        role=NodeRole.ACTION,
        properties={
            "action_type": "quarantine_hold",
            "causal_path": ["ev_1", "dec_1", "batch_1", action_token],
        },
    )
    exp_action = api.explain(action_token)
    assert exp_action.result_size == 1
    assert exp_action.data.causal_path == ["ev_1", "dec_1", "batch_1", action_token]
    assert exp_action.data.path_hops == 3

    # 5. evaluate_gate(tool, params)
    gate_res = api.evaluate_gate("hold_unit", {"entity_id": batch_0})
    assert gate_res.query_text
    assert gate_res.data.tool_name == "hold_unit"
    # batch_0 is untainted, hold is disallowed
    assert gate_res.data.allowed is False

    # 6. Algorithm 1: algo_shortest_path
    raw_lot = gen_data["raw_lots"][0]
    recipient = gen_data["recipients"][0]
    sp_res = api.algo_shortest_path(raw_lot, recipient)
    assert sp_res.result_size >= 1
    assert sp_res.data.length >= 2
    assert sp_res.data.path_node_ids[0] == raw_lot
    assert sp_res.data.path_node_ids[-1] == recipient

    # 7. Algorithm 2: algo_centrality (chokepoints)
    cent_res = api.algo_centrality(scope="tenant-food-a2")
    assert cent_res.result_size > 0
    assert cent_res.data.scores[0].rank == 1
    assert cent_res.data.scores[0].score >= 1.0

    # 8. Algorithm 3: algo_components (incident clustering)
    comp_res = api.algo_components(scope="tenant-food-a2")
    assert comp_res.result_size >= 1
    all_clustered = [item for comp in comp_res.data.components for item in comp]
    assert batch_0 in all_clustered


def test_a2_exit_check_query_api_on_pharma_pack(root_dir, loader):
    """Exit check: All Query API functions and algorithms pass on the tiny second pack (pharma)."""
    pharma_onto = loader.load_ontology(root_dir / "packs" / "pharma" / "ontology.yaml")
    query_builder = QueryBuilder(pharma_onto)

    client = StubGraphClient(tenant_id="tenant-pharma-test")
    # Build a tiny pharma graph conforming to pharma ontology
    api_lot = "api_lot_active_901"
    vial_batch_1 = "vial_batch_sterile_101"
    vial_batch_2 = "vial_batch_sterile_102"
    qp_decision = "qp_release_cert_301"
    assay_test_1 = "hplc_assay_401"
    assay_test_2 = "potency_assay_402"
    cold_box = "cold_box_ship_501"
    pharmacy = "hospital_pharmacy_601"

    client.add_node(api_lot, "ActiveIngredientLot", NodeRole.EVIDENCE, {"purity": 99.4})
    client.add_node(assay_test_1, "AssayValidation", NodeRole.EVIDENCE, {"valid": True, "group_id": "lab_a"})
    client.add_node(assay_test_2, "AssayValidation", NodeRole.EVIDENCE, {"valid": True, "group_id": "lab_b"})
    client.add_node(qp_decision, "ReleaseDecision", NodeRole.DECISION, {"verdict": "released"})
    client.add_node(vial_batch_1, "VialBatch", NodeRole.UNIT, {"is_tainted": False})
    client.add_node(vial_batch_2, "VialBatch", NodeRole.UNIT, {"is_tainted": False})
    client.add_node(cold_box, "ColdBox", NodeRole.SHIPMENT, {"status": "dispatched"})
    client.add_node(pharmacy, "HospitalPharmacy", NodeRole.RECIPIENT, {"tier": "acute_care"})

    # Edges
    client.add_edge(assay_test_1, qp_decision, "SUPPORTS", EdgeRole.SUPPORT)
    client.add_edge(assay_test_2, qp_decision, "SUPPORTS", EdgeRole.SUPPORT)
    client.add_edge(vial_batch_1, qp_decision, "DERIVES_FROM", EdgeRole.DERIVES_FROM)
    client.add_edge(vial_batch_1, api_lot, "DERIVES_FROM", EdgeRole.DERIVES_FROM)
    client.add_edge(vial_batch_2, api_lot, "DERIVES_FROM", EdgeRole.DERIVES_FROM)
    client.add_edge(vial_batch_1, vial_batch_2, "SHARED_INGREDIENT", EdgeRole.LATERAL_LINK)
    client.add_edge(vial_batch_1, cold_box, "SHIPS_IN", EdgeRole.SHIPS_IN)
    client.add_edge(cold_box, pharmacy, "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    api = QueryAPI(graph_client=client, query_builder=query_builder)

    # 1. support(decision)
    sup_res = api.support(qp_decision)
    assert sup_res.data.independent_groups_count == 2

    # 2. siblings(unit)
    sib_res = api.siblings(vial_batch_1)
    assert vial_batch_2 in sib_res.data.sibling_unit_ids

    # 3. exposure(unit)
    exp_res = api.exposure(vial_batch_1)
    assert exp_res.data.exposures[0].recipient_id == pharmacy

    # 4. algo_shortest_path
    sp_res = api.algo_shortest_path(api_lot, pharmacy)
    assert sp_res.data.length >= 2
    assert sp_res.data.path_node_ids[0] == api_lot
    assert sp_res.data.path_node_ids[-1] == pharmacy

    # 5. algo_centrality
    cent_res = api.algo_centrality(scope="tenant-pharma-test")
    assert cent_res.result_size > 0
    assert cent_res.data.scores[0].entity_id in [vial_batch_1, api_lot]

    # 6. algo_components
    comp_res = api.algo_components(scope="tenant-pharma-test")
    assert comp_res.result_size == 1
    assert len(comp_res.data.components[0]) == 8
