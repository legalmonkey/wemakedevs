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
from contracts.ontology import NodeRole, EdgeRole
from engine.ontology_utils import get_lateral_edge_spec


def _generate_id(seed: int, kind: str, index: int) -> str:
    """Generates an opaque, unique identifier deterministically derived from seed, kind, and index."""
    digest = hashlib.sha256(f"{seed}:{kind}:{index}".encode("utf-8")).hexdigest()[:8]
    return f"{kind.lower()}_{seed}_{digest}"


class FoodGraphGenerator:
    """Generates seeded supply chain topologies adhering to the food pack ontology."""

    def __init__(
        self,
        seed: int,
        num_units: Optional[int] = None,
        num_decisions: int = 15,
        num_product_families: int = 3,
    ) -> None:
        self.seed = seed
        # Scale: at least 30 units, dynamically varying from 30 to 35 depending on seed if not configured
        if num_units is not None:
            self.num_units = max(num_units, 30)
        else:
            self.num_units = 30 + (seed % 6)
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
        # Includes orphan-record faults (unverifiable=True, valid=False) declared in scenario fault parameters
        num_evidence = max(24, self.num_decisions * 2)
        test_ids: List[str] = []
        candidate_orphans = [idx for idx in range(num_evidence) if idx % 2 == 1]
        self.rng.shuffle(candidate_orphans)
        orphan_indices = set(candidate_orphans[:3])

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
                    # Naive-recall rule: all batches touched by temperature sensor
                    "instruments_touched": ["temperature_telemetry_sensor"] if ((i + (self.seed % 7)) % (3 + (self.seed % 3)) != 0) else ["pathogen_rapid_assay"],
                },
            )
            batch_ids.append(batch_id)

        # Link batches to raw lots (DERIVES_FROM) and establish lateral links
        lot_to_batches: Dict[str, List[str]] = {lid: [] for lid in raw_lot_ids}
        target_lateral_unit = batch_ids[7 % len(batch_ids)]
        for i, bid in enumerate(batch_ids):
            if i == 0 or i == 7:
                assigned_lots = [raw_lot_ids[0]]
            else:
                num_parents = 2 if ((self.seed + i) % 5 == 0 and len(raw_lot_ids) > 1) else 1
                assigned_lots = [raw_lot_ids[(self.seed + i + offset) % len(raw_lot_ids)] for offset in range(num_parents)]
            for assigned_lot in assigned_lots:
                lot_to_batches[assigned_lot].append(bid)
                add_edge(bid, assigned_lot, "DERIVES_FROM", EdgeRole.DERIVES_FROM)
        # Dynamic lateral edge specification from ontology.yaml
        lateral_kind, lateral_role_str = get_lateral_edge_spec()
        lateral_role = EdgeRole(lateral_role_str)

        # Direct lateral link between contaminated unit and target lateral unit
        add_edge(
            batch_ids[0],
            target_lateral_unit,
            lateral_kind,
            lateral_role,
            {"reason": "shared_ingredient_lot", "shared_lot_id": raw_lot_ids[0]},
        )

        # Batches sharing the same raw lot have lateral relationships
        # Directed acyclic order (earlier index -> later index) ensures 0 cycles!
        for lid, b_list in lot_to_batches.items():
            if len(b_list) > 1:
                for idx in range(len(b_list) - 1):
                    add_edge(
                        b_list[idx],
                        b_list[idx + 1],
                        lateral_kind,
                        lateral_role,
                        {"reason": "shared_ingredient_lot", "shared_lot_id": lid},
                    )

        # 4. Generate Quality Decisions (Decision)
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

            # Connect decision to governed unit strictly forward (Decision -> Unit)
            unit_for_decision = batch_ids[i % len(batch_ids)]
            add_edge(decision_id, unit_for_decision, "SUPPORT", EdgeRole.SUPPORT)

        # Demand 1: Wiring evidence to decisions so each seed yields >= 3 tainted, >= 3 reaffirmed, >= 1 unverifiable
        sensors = [tid for tid in test_ids if "sensorlog" in tid.lower()]
        valid_lab_tests = [tid for idx, tid in enumerate(test_ids) if idx % 2 == 1 and idx not in orphan_indices]
        orphan_tests = [test_ids[idx] for idx in sorted(orphan_indices)]

        # Decisions 0, 1, 2: Supported by drifted sensors without independent valid groups -> TAINTED (>= 3)
        for i in range(3):
            add_edge(sensors[i % len(sensors)], decision_ids[i], "SUPPORTS", EdgeRole.SUPPORT)

        # Decisions 3, 4, 5: Supported by drifted sensors AND >= 2 independent valid groups -> REAFFIRMED (>= 3)
        for i in range(3):
            d_idx = 3 + i
            add_edge(sensors[(i + 3) % len(sensors)], decision_ids[d_idx], "SUPPORTS", EdgeRole.SUPPORT)
            lab1 = valid_lab_tests[(i * 2) % len(valid_lab_tests)]
            lab2 = valid_lab_tests[(i * 2 + 1) % len(valid_lab_tests)]
            add_edge(lab1, decision_ids[d_idx], "SUPPORTS", EdgeRole.SUPPORT)
            add_edge(lab2, decision_ids[d_idx], "SUPPORTS", EdgeRole.SUPPORT)

        # Decision 6: Supported by drifted sensor AND orphan unlinked reading -> UNVERIFIABLE (>= 1)
        add_edge(sensors[0], decision_ids[6], "SUPPORTS", EdgeRole.SUPPORT)
        add_edge(orphan_tests[0], decision_ids[6], "SUPPORTS", EdgeRole.SUPPORT)

        # Decision 7 governs target_lateral_unit (batch_ids[7]). It must NOT be directly tainted by drifted sensors
        # so target_lateral_unit is ONLY contaminated laterally via declared lateral links (Demand 1 Ground Truth)
        add_edge(valid_lab_tests[0], decision_ids[7], "SUPPORTS", EdgeRole.SUPPORT)
        add_edge(valid_lab_tests[1], decision_ids[7], "SUPPORTS", EdgeRole.SUPPORT)

        # Decisions 8 to 14: Dynamic seed-dependent wiring for randomized variance across seeds
        for i in range(8, self.num_decisions):
            num_links = 1 + ((self.seed + i * 3) % 4)
            chosen_tests = [
                test_ids[(self.seed * 7 + i * 5 + g) % len(test_ids)]
                for g in range(num_links)
            ]
            for t_id in set(chosen_tests):
                add_edge(t_id, decision_ids[i], "SUPPORTS", EdgeRole.SUPPORT)

        # 5. Generate Dispatch Shipments (Shipment)
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

            # 6. Customer Recipients (Pre-created before DELIVERED_TO edge)
            recipient_id = _generate_id(self.seed, "CustomerAccount", i)
            add_node(
                node_id=recipient_id,
                kind="CustomerAccount",
                role=NodeRole.RECIPIENT,
                properties={"tier": "commercial", "account_ref": f"ACC-{self.seed}-{i}"},
            )
            recipient_ids.append(recipient_id)
            add_edge(shipment_id, recipient_id, "DELIVERED_TO", EdgeRole.DELIVERED_TO)

        # Batch write if client supports bulk ingestion; otherwise already written incrementally
        if graph_client is not None:
            if hasattr(graph_client, "batch_add_nodes") and not hasattr(graph_client, "add_node"):
                graph_client.batch_add_nodes(list(nodes.values()))
            if hasattr(graph_client, "batch_add_edges") and not hasattr(graph_client, "add_edge"):
                graph_client.batch_add_edges(edges)

        lateral_fault = {
            "source_unit_id": batch_ids[0],
            "target_lateral_unit_id": target_lateral_unit,
            "shared_lot_id": raw_lot_ids[0],
            "edge_type": lateral_kind,
        }
        if graph_client is not None:
            if not hasattr(graph_client, "recorded_faults") or graph_client.recorded_faults is None:
                graph_client.recorded_faults = {}
            graph_client.recorded_faults["lateral_fault"] = lateral_fault

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
            "recorded_lateral_fault": lateral_fault,
        }

