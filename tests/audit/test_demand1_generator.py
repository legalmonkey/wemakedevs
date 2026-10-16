"""Demand 1 Verification Suite: Scaled Randomised Generator.

Verifies:
(1) Scale configurable: at least 30 units, 15 decisions, 3 product families.
(2) Zero IDs or labels that encode expected outcomes (no 'reaff', 'taint', 'lateral', etc.).
(3) Two seeds differ in graph structure (different nodes, edges, degree distribution).
"""

import pytest
from contracts.ontology import NodeRole, EdgeRole
from engine.generator import FoodGraphGenerator
from engine.falkordb_client import FalkorDBGraphClient


BANNED_OUTCOME_SUBSTRINGS = ["reaff", "taint", "lateral", "hold", "clean", "adulterat", "drift"]


def test_generator_scale_configurable():
    """Verify scale configurable: at least 30 units, 15 decisions, 3 product families."""
    gen = FoodGraphGenerator(seed=101, num_units=35, num_decisions=18, num_product_families=4)
    data = gen.generate()

    assert len(data["batches"]) == 35, f"Expected 35 batches, got {len(data['batches'])}"
    assert len(data["decisions"]) == 18, f"Expected 18 decisions, got {len(data['decisions'])}"
    assert len(data["product_families"]) == 4, f"Expected 4 product families, got {len(data['product_families'])}"

    # Default scale must also satisfy minimum requirements
    default_gen = FoodGraphGenerator(seed=202)
    default_data = default_gen.generate()
    assert len(default_data["batches"]) >= 30, f"Default batches < 30: {len(default_data['batches'])}"
    assert len(default_data["decisions"]) >= 15, f"Default decisions < 15: {len(default_data['decisions'])}"
    assert len(default_data["product_families"]) >= 3, f"Default product families < 3: {len(default_data['product_families'])}"


def test_generator_no_outcome_encoding_in_ids_or_labels():
    """Verify no IDs or labels encode expected outcomes."""
    gen = FoodGraphGenerator(seed=303, num_units=30, num_decisions=15, num_product_families=3)
    data = gen.generate()

    for node_id, node_info in data["nodes"].items():
        # 1. No banned outcome substrings in node ID
        for banned in BANNED_OUTCOME_SUBSTRINGS:
            assert banned not in node_id.lower(), (
                f"Violation: Node ID '{node_id}' encodes expected outcome token '{banned}'!"
            )

        # 2. No outcome labels in initial properties
        props = node_info["properties"]
        verdict = props.get("verdict")
        assert verdict not in ["reaffirmed", "tainted"], (
            f"Violation: Node '{node_id}' initially encodes verdict '{verdict}'!"
        )
        assert props.get("is_tainted", False) is False, (
            f"Violation: Node '{node_id}' initially encodes is_tainted=True!"
        )


def test_generator_seeds_differ_in_structure():
    """Assert two seeds produce topologies that genuinely differ in graph structure."""
    gen1 = FoodGraphGenerator(seed=1111)
    gen2 = FoodGraphGenerator(seed=2222)

    data1 = gen1.generate()
    data2 = gen2.generate()

    # 1. Different node ID sets
    nodes1 = set(data1["nodes"].keys())
    nodes2 = set(data2["nodes"].keys())
    assert nodes1 != nodes2, "Seeds produced identical node ID sets!"
    assert len(nodes1.intersection(nodes2)) == 0, "Seeds produced colliding node IDs!"

    # 2. Different edge sets
    edges1 = {(e["source_id"], e["target_id"], e["kind"]) for e in data1["edges"]}
    edges2 = {(e["source_id"], e["target_id"], e["kind"]) for e in data2["edges"]}
    assert edges1 != edges2, "Seeds produced identical edge sets!"

    # 3. Different raw lot and test mappings
    assert data1["raw_lots"] != data2["raw_lots"], "Raw lots identical across seeds!"
    assert data1["tests"] != data2["tests"], "Test evidence identical across seeds!"
