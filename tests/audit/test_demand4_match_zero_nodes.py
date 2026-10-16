"""Demand 4 Verification Suite: Recipient Ordering & Zero-Node MATCH Failure.

Verifies:
(1) Recipient nodes are created before any DELIVERED_TO edge is created.
(2) FalkorDB add_edge fails loudly with ValueError if an edge-creating MATCH matches zero nodes.
"""

import pytest
from contracts.ontology import NodeRole, EdgeRole
from engine.falkordb_client import FalkorDBGraphClient
from engine.generator import FoodGraphGenerator


def test_edge_creation_fails_if_match_matches_zero_nodes():
    """Verify that add_edge fails loudly with ValueError when source or target does not exist."""
    client = FalkorDBGraphClient(tenant_id="test-demand4-match-zero", clean=True)

    # 1. Existing source node only
    client.add_node(
        node_id="node-existing-source",
        kind="BatchLot",
        role=NodeRole.UNIT,
        properties={"status": "active"},
    )

    # 2. Attempt edge creation to non-existent target -> MUST RAISE ValueError
    with pytest.raises(ValueError) as excinfo:
        client.add_edge(
            source_id="node-existing-source",
            target_id="node-ghost-target-404",
            kind="DELIVERED_TO",
            role=EdgeRole.DELIVERED_TO,
        )

    print("\n1. Caught Expected Zero-Node Edge Error (Missing Target):")
    print("   ", excinfo.value)
    assert "MATCH matched zero nodes" in str(excinfo.value)
    assert "node-ghost-target-404" in str(excinfo.value)

    # 3. Attempt edge creation from non-existent source -> MUST RAISE ValueError
    with pytest.raises(ValueError) as excinfo_src:
        client.add_edge(
            source_id="node-ghost-source-404",
            target_id="node-existing-source",
            kind="DELIVERED_TO",
            role=EdgeRole.DELIVERED_TO,
        )

    print("2. Caught Expected Zero-Node Edge Error (Missing Source):")
    print("   ", excinfo_src.value)
    assert "MATCH matched zero nodes" in str(excinfo_src.value)
    assert "node-ghost-source-404" in str(excinfo_src.value)

    # 4. Create target node and verify edge creation succeeds
    client.add_node(
        node_id="node-existing-target",
        kind="CustomerAccount",
        role=NodeRole.RECIPIENT,
        properties={"tier": "commercial"},
    )
    edge = client.add_edge(
        source_id="node-existing-source",
        target_id="node-existing-target",
        kind="DELIVERED_TO",
        role=EdgeRole.DELIVERED_TO,
    )
    print("3. Valid Edge Creation (Both Nodes Exist):", edge)
    assert edge.source_id == "node-existing-source"
    assert edge.target_id == "node-existing-target"


def test_generator_creates_recipients_before_delivered_to_edge():
    """Verify that FoodGraphGenerator creates Recipient nodes before any DELIVERED_TO edge."""
    client = FalkorDBGraphClient(tenant_id="test-demand4-gen-recip", clean=True)
    gen = FoodGraphGenerator(seed=9999)

    # If recipients were not created before DELIVERED_TO, add_edge would raise ValueError immediately
    data = gen.generate(graph_client=client)

    # Verify all recipients exist in graph client
    recipients = data["recipients"]
    assert len(recipients) > 0, "Generator must produce customer recipients"
    for r_id in recipients:
        node = client.get_node(r_id)
        assert node is not None, f"Recipient node '{r_id}' missing from FalkorDB graph!"
        assert node.role == NodeRole.RECIPIENT

    # Verify DELIVERED_TO edges exist in FalkorDB
    delivered_edges = [e for e in client.edges if e.role == EdgeRole.DELIVERED_TO or e.kind == "DELIVERED_TO"]
    assert len(delivered_edges) == len(recipients), (
        f"Expected {len(recipients)} DELIVERED_TO edges, found {len(delivered_edges)}"
    )
