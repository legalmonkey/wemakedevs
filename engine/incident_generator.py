"""Seeded Incident Topology Generator (Part A).

Generates unique randomized incident graphs from seeds for testing and live execution.
Ensures strict Section 0 Rule 3 compliance:
- Zero hardcoding and no IDs or labels encoding expected outcomes.
- Configurable scale: >= 30 units, >= 15 decisions, >= 3 product families.
- Emergent outcomes derived strictly from declarative fault injection.
"""

from __future__ import annotations
import random
from contracts.ontology import EdgeRole, NodeRole
from engine.falkordb_client import FalkorDBGraphClient
from engine.generator import FoodGraphGenerator, _generate_id


def generate_seeded_incident(
    seed: int,
    num_units: int = 30,
    num_decisions: int = 15,
    num_product_families: int = 3,
    clean: bool = True,
    tenant_id: Optional[str] = None,
) -> FalkorDBGraphClient:
    """Generates a randomized incident graph using a fresh seed on FalkorDB.

    Scale configurable:
    - num_units >= 30 finished product units
    - num_decisions >= 15 quality release decisions
    - num_product_families >= 3 product families
    - Topology outcomes (tainted, reaffirmed, lateral spread) emerge purely from
      fault injection and graph traversal, not hardcoded identifiers or outcome tags.
    """
    if not tenant_id:
        rng = random.Random(seed)
        tenant_id = f"tenant-seed-{seed}-{rng.randint(100, 999)}"
    client = FalkorDBGraphClient(tenant_id=tenant_id, clean=clean)

    # 1. Generate multi-family supply chain graph topology
    generator = FoodGraphGenerator(
        seed=seed,
        num_units=num_units,
        num_decisions=num_decisions,
        num_product_families=num_product_families,
    )
    gen_data = generator.generate(graph_client=client)

    # 2. Inject declarative fault using scenario fault parameters
    from pathlib import Path
    from engine.injector import FaultInjector
    scenario_path = Path(__file__).resolve().parent.parent / "scenarios" / "scenario_calibration_drift.yaml"
    injector = FaultInjector.from_file(scenario_path, seed=seed)
    injector.inject(client)

    return client


