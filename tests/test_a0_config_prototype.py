"""Phase A0 Exit Check: Config loader with JSON Schema and prototype queries.

Exit check: "Invalid config is rejected with a clear message; prototype queries run"

Verifies:
1. Valid configuration files (gates.yaml, policy.yaml) pass JSON Schema validation cleanly.
2. Invalid configurations (missing required fields, negative values, type mismatches) are rejected
   with descriptive ConfigValidationError messages naming the failed fields.
3. Prototype gate Cypher query runs with parameters and evaluates permission.
4. Prototype variable-depth trace Cypher query runs with path assignment, length(path),
   and via_path list comprehension [n IN nodes(path) | n.id].
5. Dialect constraints on FalkorDB / OpenCypher are verified.
"""

import pytest
from pathlib import Path
from engine.config_loader import ConfigLoader, ConfigValidationError
from engine.prototype_queries import (
    GATE_PROTOTYPE_CYPHER,
    TRACE_PROTOTYPE_CYPHER,
    PrototypeQueryRunner,
)


@pytest.fixture
def loader():
    return ConfigLoader()


@pytest.fixture
def query_runner():
    return PrototypeQueryRunner()


# --- 1. Config Loader & JSON Schema Validation Tests ---


def test_valid_gates_config_passes_validation(loader):
    """Verifies that config/gates.yaml strictly matches gates.schema.json."""
    data = loader.load_gates()
    assert "version" in data
    assert "gates" in data
    assert len(data["gates"]) >= 3
    for gate in data["gates"]:
        assert "tool_name" in gate
        assert "cypher_query" in gate
        assert "required_parameters" in gate
        assert "target_role" in gate


def test_valid_policy_config_passes_validation(loader):
    """Verifies that config/policy.yaml strictly matches policy.schema.json."""
    data = loader.load_policy()
    assert data["version"] == "1.0.0"
    assert data["adjudication"]["min_independent"] >= 1
    assert data["memory"]["min_evidence_episodes"] >= 1


def test_invalid_config_rejected_with_clear_message(loader, tmp_path):
    """Exit check: Invalid config is rejected with a clear message."""
    invalid_policy_file = tmp_path / "invalid_policy.yaml"

    # Case A: Missing required section 'memory'
    invalid_policy_file.write_text(
        """
version: "1.0.0"
adjudication:
  min_independent: 2
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError) as exc_info:
        loader.load_policy(invalid_policy_file)
    err_msg = str(exc_info.value)
    assert "policy.schema.json" in err_msg
    assert "'memory' is a required property" in err_msg

    # Case B: Negative value violating minimum constraint
    invalid_policy_file.write_text(
        """
version: "1.0.0"
adjudication:
  min_independent: -5
memory:
  min_evidence_episodes: 3
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError) as exc_info:
        loader.load_policy(invalid_policy_file)
    err_msg = str(exc_info.value)
    assert "adjudication -> min_independent" in err_msg
    assert "less than the minimum of 1" in err_msg

    # Case C: Malformed gates config missing required property 'cypher_query'
    invalid_gates_file = tmp_path / "invalid_gates.yaml"
    invalid_gates_file.write_text(
        """
version: "1.0.0"
gates:
  - tool_name: "hold_unit"
    description: "Missing cypher query"
    required_parameters: ["entity_id"]
    target_role: "Unit"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError) as exc_info:
        loader.load_gates(invalid_gates_file)
    err_msg = str(exc_info.value)
    assert "gates.schema.json" in err_msg
    assert "'cypher_query' is a required property" in err_msg


# --- 2. Prototype Queries & Dialect Verification Tests ---


def test_prototype_gate_query_runs(query_runner):
    """Exit check: Prototype gate query runs and returns valid gate evaluation."""
    entity_token = "entity_test_token"
    result = query_runner.run_gate_query(entity_id=entity_token)

    assert result["params"]["entity_id"] == entity_token
    assert "MATCH (u:Unit {id: $entity_id})" in result["query"]
    assert "RETURN count(u) > 0 AS allowed" in result["query"]
    assert isinstance(result["allowed"], bool)
    assert result["result_size"] >= 1


def test_prototype_variable_depth_trace_runs(query_runner):
    """Exit check: Prototype variable-depth trace runs with hops and via_path."""
    source_node = "source_evidence_node"
    hop1_node = "intermediate_batch_node"
    hop2_node = "destination_shipment_node"

    # Multi-hop test topology
    mock_topology = {
        "edges": {
            source_node: [hop1_node],
            hop1_node: [hop2_node],
        }
    }

    traces = query_runner.run_trace_query(start_id=source_node, mock_graph=mock_topology)

    assert len(traces) == 2
    # First hop
    assert traces[0]["target_id"] == hop1_node
    assert traces[0]["hops"] == 1
    assert traces[0]["via_path"] == [source_node, hop1_node]

    # Second hop (depth = 2)
    assert traces[1]["target_id"] == hop2_node
    assert traces[1]["hops"] == 2
    assert traces[1]["via_path"] == [source_node, hop1_node, hop2_node]


def test_prototype_cypher_dialect_conformance():
    """Validates that prototype queries conform to FalkorDB OpenCypher dialect requirements."""
    # Gate query structure
    assert "WHERE u.is_tainted = true" in GATE_PROTOTYPE_CYPHER
    assert "$entity_id" in GATE_PROTOTYPE_CYPHER

    # Variable-depth trace query structure
    assert "MATCH path = (start {id: $start_id})-[:SUPPORT|DERIVES_FROM|SHIPS_IN|DELIVERED_TO|LATERAL_LINK*1..10]->(target)" in TRACE_PROTOTYPE_CYPHER
    assert "length(path) AS hops" in TRACE_PROTOTYPE_CYPHER
    assert "[n IN nodes(path) | n.id] AS via_path" in TRACE_PROTOTYPE_CYPHER
