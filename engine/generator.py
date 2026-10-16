"""Seeded Graph Topology Generator for Food Pack (Part A, Phase A1).

Generates realistic food supply chain and quality control graphs:
- Suppliers & Raw Material Lots (Evidence)
- Lab Tests & Sensor Logs (Evidence)
- Finished Product Batches (Unit)
- Quality Adjudication Decisions (Decision)
- Lateral links between batches via shared lots
- Dispatch Shipments (Shipment)
- Customer Accounts (Recipient)

Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding. All IDs generated dynamically from seed and kind hash.
- Rule 8: No mock data in production paths. Generated data conforms strictly to ontology contracts.
- Exit Check: Two seeds yield completely different graphs.
"""

from __future__ import annotations
import random
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from contracts.ontology import NodeRole, EdgeRole


def _generate_id(seed: int, kind: str, index: int) -> str:
    """Generates an opaque, unique identifier deterministically derived from seed, kind, and index."""
    digest = hashlib.sha256(f"{seed}:{kind}:{index}".encode("utf-8")).hexdigest()[:8]
    return f"{kind.lower()}_{seed}_{digest}"


class FoodGraphGenerator:
    """Generates seeded supply chain topologies adhering to the food pack ontology."""

    def __init__(
        self,
        seed: int,
        num_units: int = 30,
        num_decisions: int = 15,
        num_product_families: int = 3,
    ) -> None:
        self.seed = seed
        # Scale: at least 30 units, dynamically varying from 30 to 35 depending on seed
        base_units = max(num_units, 30)
        self.num_units = base_units + (seed % 6)
        self.num_decisions = max(num_decisions, 15)
        self.num_product_families = max(num_product_families, 3)
        self.rng = random.Random(seed)

    def generate(self, graph_client: Optional[Any] = None) -> Dict[str, Any]:
        """Generates graph topology and populates graph_client if provided.
        
        Returns a dictionary containing graph nodes, edges, and index mappings.
        """
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []

        def add_node(node_id: str, kind: str, role: NodeRole, properties: Dict[str, Any]) -> None:
            node_data = {
                "id": node_id,
                "kind": kind,
                "role": role,
                "properties": properties,
            }
            nodes[node_id] = node_data
            if graph_client is not None and hasattr(graph_client, "add_node"):
                graph_client.add_node(node_id, kind, role, properties)

        def add_edge(source_id: str, target_id: str, kind: str, role: EdgeRole, properties: Optional[Dict[str, Any]] = None) -> None:
            props = properties or {}
            edge_data = {
                "source_id": source_id,
                "target_id": target_id,
                "kind": kind,
                "role": role,
                "properties": props,
            }
            edges.append(edge_data)
            if graph_client is not None and hasattr(graph_client, "add_edge"):
                graph_client.add_edge(source_id, target_id, kind, role, props)

        # 0. Product Families
        family_names = [f"ProductFamily_{chr(65 + i)}" for i in range(self.num_product_families)]

        # 1. Generate Suppliers and Raw Lots (Evidence) - Dynamic count per seed
        raw_lot_count = 6 + (self.seed % 5)
        raw_lot_ids: List[str] = []
        for i in range(raw_lot_count):
            lot_id = _generate_id(self.seed, "SupplierLot", i)
            add_node(
                node_id=lot_id,
                kind="SupplierLot",
                role=NodeRole.EVIDENCE,
                properties={
                    "origin_hash": hashlib.md5(f"facility_{self.seed}_{i}".encode()).hexdigest()[:6],
                    "status": "received",
                },
            )
            raw_lot_ids.append(lot_id)

        # 2. Generate Evidence Readings / Lab Tests (Evidence)
        # Includes orphan-result faults (unverifiable=True, valid=False) to trigger unverifiable status
        num_evidence = max(24, self.num_decisions * 2)
        test_ids: List[str] = []
        orphan_indices = set(self.rng.sample(range(num_evidence), k=min(3, max(1, num_evidence // 10))))

        for i in range(num_evidence):
            kind = "SensorLog" if (i % 2 == 0) else "LabTest"
            inst_type = "temperature_telemetry_sensor" if (i % 2 == 0) else "pathogen_rapid_assay"
            test_id = _generate_id(self.seed, kind, i)
            group_idx = (self.seed + i) % 7
            is_orphan = i in orphan_indices

            add_node(
                node_id=test_id,
                kind=kind,
                role=NodeRole.EVIDENCE,
                properties={
                    "assay_hash": hashlib.md5(f"assay_{self.seed}_{i}".encode()).hexdigest()[:6],
                    "valid": not is_orphan,
                    "unverifiable": is_orphan,
                    "reason": "orphan_result_unlinked_chain" if is_orphan else "normal_telemetry",
                    "group_id": f"group_{self.seed}_{group_idx}",
                    "instrument_type": inst_type,
                    "facility_id": "FAC-01",
                },
            )
            test_ids.append(test_id)

        # 3. Generate Finished Product Batches (Unit)
        batch_ids: List[str] = []
        for i in range(self.num_units):
            batch_id = _generate_id(self.seed, "BatchLot", i)
            family = family_names[i % len(family_names)]
            add_node(
                node_id=batch_id,
                kind="BatchLot",
                role=NodeRole.UNIT,
                properties={
                    "is_tainted": False,
                    "status": "released",
                    "product_family": family,
                    "batch_number": 1000 + i,
                    # Demand (2): Naive-recall rule selects a strict subset on seeds
                    # Stride and offset based on seed ensures count of batches touching sensor varies per seed
                    "instruments_touched": ["temperature_telemetry_sensor"] if ((i + (self.seed % 7)) % (3 + (self.seed % 3)) != 0) else ["pathogen_rapid_assay"],
                },
            )
            batch_ids.append(batch_id)

        # Link batches to raw lots (DERIVES_FROM) and establish lateral links
        # Derivation branching varies by seed: each batch derives from 1 or 2 raw lots
        lot_to_batches: Dict[str, List[str]] = {lid: [] for lid in raw_lot_ids}
        for i, bid in enumerate(batch_ids):
            num_parents = 2 if ((self.seed + i) % 5 == 0 and len(raw_lot_ids) > 1) else 1
            assigned_lots = [raw_lot_ids[(self.seed + i + offset) % len(raw_lot_ids)] for offset in range(num_parents)]
            for assigned_lot in assigned_lots:
                lot_to_batches[assigned_lot].append(bid)
                add_edge(bid, assigned_lot, "DERIVES_FROM", EdgeRole.DERIVES_FROM)

        # Batches sharing the same raw lot have SHARED_LOT (LATERAL_LINK) relationships
        # Directed acyclic order (earlier index -> later index) ensures 0 cycles!
        for lid, b_list in lot_to_batches.items():
            if len(b_list) > 1:
                for idx in range(len(b_list) - 1):
                    add_edge(
                        b_list[idx],
                        b_list[idx + 1],
                        "SHARED_LOT",
                        EdgeRole.LATERAL_LINK,
                        {"reason": "shared_ingredient_lot", "shared_lot_id": lid},
                    )

        # 4. Generate Quality Decisions (Decision)
        # Pure DAG: (Evidence) -[:SUPPORTS]-> (Decision) -[:SUPPORT]-> (Unit)
        # ZERO cyclic edges!
        decision_ids: List[str] = []
        for i in range(self.num_decisions):
            decision_id = _generate_id(self.seed, "QualityDecision", i)
            add_node(
                node_id=decision_id,
                kind="QualityDecision",
                role=NodeRole.DECISION,
                properties={
                    "status": "pending",
                    "decision_index": i,
                },
            )
            decision_ids.append(decision_id)

            # Connect decision to governed unit(s) - strictly forward (Decision -> Unit)
            unit_for_decision = batch_ids[i % len(batch_ids)]
            add_edge(decision_id, unit_for_decision, "SUPPORT", EdgeRole.SUPPORT)

            # Assign evidence support edges from test_ids with variable group counts per seed:
            num_evidence_links = 1 + ((self.seed + i * 3) % 4) # 1 to 4 supports
            chosen_tests = [
                test_ids[(self.seed * 7 + i * 5 + g) % len(test_ids)]
                for g in range(num_evidence_links)
            ]
            for t_id in set(chosen_tests):
                add_edge(t_id, decision_id, "SUPPORTS", EdgeRole.SUPPORT)

        # 5. Generate Dispatch Shipments (Shipment) for a subset of units (~60% shipped, ~40% unshipped)
        shipment_ids: List[str] = []
        recipient_ids: List[str] = []
        num_shipments = max(10, (self.num_units * 3) // 5)

        for i in range(num_shipments):
            shipped_batch = batch_ids[i]
            shipment_id = _generate_id(self.seed, "DispatchShipment", i)
            add_node(
                node_id=shipment_id,
                kind="DispatchShipment",
                role=NodeRole.SHIPMENT,
                properties={"status": "in_transit", "tracking_code": f"TRK-{self.seed}-{i}"},
            )
            shipment_ids.append(shipment_id)
            add_edge(shipped_batch, shipment_id, "SHIPS_IN", EdgeRole.SHIPS_IN)

            # 6. Generate Customer Recipients (Recipient)
            # Pre-create Recipient node BEFORE any DELIVERED_TO edge
            recipient_id = _generate_id(self.seed, "CustomerAccount", i)
            add_node(
                node_id=recipient_id,
                kind="CustomerAccount",
                role=NodeRole.RECIPIENT,
                properties={"tier": "commercial", "account_ref": f"ACC-{self.seed}-{i}"},
            )
            recipient_ids.append(recipient_id)

            # Add DELIVERED_TO edge
            add_edge(shipment_id, recipient_id, "DELIVERED_TO", EdgeRole.DELIVERED_TO)

        return {
            "seed": self.seed,
            "nodes": nodes,
            "edges": edges,
            "batches": batch_ids,
            "decisions": decision_ids,
            "tests": test_ids,
            "raw_lots": raw_lot_ids,
            "shipments": shipment_ids,
            "recipients": recipient_ids,
            "product_families": family_names,
        }
