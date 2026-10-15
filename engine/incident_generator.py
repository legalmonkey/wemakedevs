"""Seeded Incident Topology Generator (Part A).

Generates unique randomized incident graphs from seeds for testing and live execution.
Ensures strict Section 0 Rule 3 compliance: zero hardcoding.
"""

from __future__ import annotations
import random
from contracts.ontology import EdgeRole, NodeRole
from agents.stub_client import StubGraphClient


def generate_seeded_incident(seed: int) -> StubGraphClient:
    """Generates a unique randomized incident graph using a fresh seed.

    Topology guarantees:
    - 1 Reaffirmation beat (decision with >= min_independent independent valid support groups)
    - 1 Tainted decision (decision whose sole support was retracted)
    - 1 Lateral link (shared lot/line connecting to an unplanned batch)
    - 1 Outbound shipment and recipient exposed to tainted batch
    """
    rng = random.Random(seed)
    tenant_id = f"tenant-seed-{seed}-{rng.randint(100, 999)}"
    client = StubGraphClient(tenant_id=tenant_id)

    # Generate random ID tokens for this seed
    tok_ev1 = f"ev-{rng.randint(10000, 99999)}"
    tok_ev2 = f"ev-indepA-{rng.randint(10000, 99999)}"
    tok_ev3 = f"ev-indepB-{rng.randint(10000, 99999)}"

    tok_dec_reaff = f"dec-reaff-{rng.randint(10000, 99999)}"
    tok_dec_taint = f"dec-taint-{rng.randint(10000, 99999)}"

    tok_unit_clean = f"unit-{rng.randint(10000, 99999)}"
    tok_unit_taint = f"unit-{rng.randint(10000, 99999)}"
    tok_unit_lateral = f"unit-lateral-{rng.randint(10000, 99999)}"

    tok_ship = f"ship-{rng.randint(10000, 99999)}"
    tok_rec = f"rec-{rng.randint(10000, 99999)}"
    tok_evt = f"evt-alert-{rng.randint(10000, 99999)}"

    # 1. Evidence nodes
    client.add_node(tok_ev1, "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": f"grp-{rng.randint(1, 99)}"})
    client.add_node(tok_ev2, "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": f"grp-indep-{rng.randint(100, 199)}"})
    client.add_node(tok_ev3, "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": f"grp-indep-{rng.randint(200, 299)}"})

    # 2. Decision 1: Reaffirmation beat (has 2 independent valid groups + retracted evidence)
    client.add_node(tok_dec_reaff, "Disposition", NodeRole.DECISION, {"status": "pending"})
    client.add_edge(tok_ev1, tok_dec_reaff, "SUPPORT", EdgeRole.SUPPORT)
    client.add_edge(tok_ev2, tok_dec_reaff, "SUPPORT", EdgeRole.SUPPORT)
    client.add_edge(tok_ev3, tok_dec_reaff, "SUPPORT", EdgeRole.SUPPORT)

    # 3. Decision 2: Tainted beat (only supported by retracted evidence)
    client.add_node(tok_dec_taint, "Disposition", NodeRole.DECISION, {"status": "pending"})
    client.add_edge(tok_ev1, tok_dec_taint, "SUPPORT", EdgeRole.SUPPORT)

    # 4. Units
    client.add_node(tok_unit_clean, "Batch", NodeRole.UNIT, {})
    client.add_edge(tok_dec_reaff, tok_unit_clean, "SUPPORT", EdgeRole.SUPPORT)

    client.add_node(tok_unit_taint, "Batch", NodeRole.UNIT, {})
    client.add_edge(tok_dec_taint, tok_unit_taint, "SUPPORT", EdgeRole.SUPPORT)

    # Lateral link: Unplanned batch contaminated via shared equipment/lot
    client.add_node(tok_unit_lateral, "Batch", NodeRole.UNIT, {})
    client.add_edge(tok_unit_taint, tok_unit_lateral, "LATERAL_LINK", EdgeRole.LATERAL_LINK)

    # 5. Outbound shipment and recipient
    client.add_node(tok_ship, "Shipment", NodeRole.SHIPMENT, {"status": "in_transit"})
    client.add_edge(tok_unit_taint, tok_ship, "SHIPS_IN", EdgeRole.SHIPS_IN)

    client.add_node(tok_rec, "Recipient", NodeRole.RECIPIENT, {})
    client.add_edge(tok_ship, tok_rec, "DELIVERED_TO", EdgeRole.DELIVERED_TO)

    # 6. Trigger Event targeting tok_ev1
    client.add_node(tok_evt, "AlertEvent", NodeRole.EVENT, {
        "processed": False,
        "target_evidence_id": tok_ev1,
        "reason": f"Randomized calibration drift alert (seed {seed})",
    })

    return client
