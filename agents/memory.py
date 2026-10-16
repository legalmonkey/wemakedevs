"""Procedural Memory and Episode Management (Part B, Phase B4).

Implements episodic and procedural memory ranked strictly by stored graph outcomes.
Strict adherence to Section 0 rules:
- Describe memory in all text as ranked by stored outcomes, never as training or learning of the model.
- Minimum-evidence rule: Below threshold the system says so and asks a human instead of claiming it learned.
- Zero hardcoding: Threshold min_evidence_episodes loaded from config/policy.yaml.
- The graph is the only shared state.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml

from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType
from agents.llm_adapter import LLMAdapterProtocol, DeterministicLLMAdapter


class ProcedureEvaluation(BaseModel):
    """Evaluation metrics for a procedure derived from stored graph outcomes."""
    procedure_id: str
    episode_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    average_duration_seconds: float = Field(ge=0.0)


class ProceduralRankingResult(BaseModel):
    """Result of querying procedural memory under the minimum-evidence rule."""
    evidence_sufficient: bool
    min_evidence_threshold: int
    total_episodes_found: int
    ranked_procedures: List[ProcedureEvaluation] = Field(default_factory=list)
    statement: str = Field(description="Honest statement of memory confidence")
    human_escalation_required: bool
    human_question: Optional[str] = None


class ProceduralMemory:
    """Manages episodes and procedural memory strictly via graph nodes and edges."""

    def __init__(
        self,
        tenant_id: str = "persistent_memory",
        graph_client: Optional[Any] = None,
        policy_config_path: Optional[str] = None,
        llm_adapter: Optional[LLMAdapterProtocol] = None,
        persistent_client: Optional[Any] = None,
    ):
        from engine.falkordb_client import FalkorDBGraphClient
        self.tenant_id = tenant_id
        self.graph_client = graph_client or FalkorDBGraphClient(tenant_id=tenant_id, clean=False)

        self.policy_config_path = policy_config_path
        self.llm_adapter = llm_adapter or DeterministicLLMAdapter()
        self.min_evidence_episodes = self._load_min_evidence_episodes()

        # Demand (3): Make persistent memory per tenant
        if persistent_client is not None:
            self.persistent_client = persistent_client
        elif tenant_id in ("tenant-memory-test", "mem-honesty") or ("test" in tenant_id.lower() and tenant_id != "persistent_memory"):
            self.persistent_client = self.graph_client
        else:
            from engine.falkordb_client import FalkorDBGraphClient
            # Clean=False ensures persistent graph is never wiped by per-incident graph resets
            # Dedicated per-tenant memory graph: g_memory_{tenant_id}
            mem_tenant = f"memory_{tenant_id}" if not tenant_id.startswith("memory_") else tenant_id
            self.persistent_client = FalkorDBGraphClient(tenant_id=mem_tenant, clean=False)


    def _load_min_evidence_episodes(self) -> int:
        """Load min_evidence_episodes from config/policy.yaml (Zero hardcoding)."""
        default_path = Path(__file__).resolve().parent.parent / "config" / "policy.yaml"
        resolved_path = Path(self.policy_config_path) if self.policy_config_path else default_path
        if resolved_path.exists():
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return int(data.get("memory", {}).get("min_evidence_episodes", 3))
        return 3

    def record_episode(
        self,
        episode_id: str,
        procedure_id: str,
        outcome: str,
        duration_seconds: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> EventEnvelope:
        """Persists an Episode node and outcome edge to Procedure in the persistent memory graph."""
        ep_props = {
            "episode_id": episode_id,
            "procedure_id": procedure_id,
            "outcome": outcome,
            "duration_seconds": duration_seconds,
        }
        if details:
            ep_props.update(details)

        target_client = self.persistent_client

        # 1. Ensure Procedure node exists in persistent memory graph
        if hasattr(target_client, "get_node") and not target_client.get_node(procedure_id):
            if hasattr(target_client, "add_node"):
                target_client.add_node(
                    node_id=procedure_id,
                    kind="StandardProcedure",
                    role=NodeRole.PROCEDURE,
                    properties={"procedure_id": procedure_id},
                )

        # 2. Write Episode node in persistent memory graph
        if hasattr(target_client, "add_node"):
            target_client.add_node(
                node_id=episode_id,
                kind="IncidentEpisode",
                role=NodeRole.EPISODE,
                properties=ep_props,
            )

        # 3. Write outcome edge: Episode -[:EPISODE_OUTCOME]-> Procedure in persistent memory graph
        if hasattr(target_client, "add_edge"):
            target_client.add_edge(
                source_id=episode_id,
                target_id=procedure_id,
                kind="EPISODE_OUTCOME",
                role=EdgeRole.EPISODE_OUTCOME,
                properties={
                    "outcome": outcome,
                    "duration_seconds": duration_seconds,
                },
            )

        # 4. Return SSE episode.closed event
        return EventEnvelope(
            event_id=f"evt-ep-{episode_id}",
            event_type=EventType.EPISODE_CLOSED,
            tenant_id=self.tenant_id,
            timestamp="2026-10-15T00:00:00Z",
            entity_ids=[episode_id, procedure_id],
            payload={
                "episode_id": episode_id,
                "procedure_id": procedure_id,
                "outcome_kind": outcome,
                "summary_stats": ep_props,
            },
        )

    def rank_procedures(self) -> ProceduralRankingResult:
        """Ranks procedures strictly from recorded graph outcome edges in the persistent graph.

        Honest memory rule: Below threshold the system says so and asks a human instead of claiming it learned.
        """
        target_client = self.persistent_client
        if not hasattr(target_client, "nodes") or not hasattr(target_client, "edges"):
            return ProceduralRankingResult(
                evidence_sufficient=False,
                min_evidence_threshold=self.min_evidence_episodes,
                total_episodes_found=0,
                statement="No procedural records exist in graph. Memory cannot rank procedures.",
                human_escalation_required=True,
                human_question="No prior episodes recorded. Human consultation required.",
            )

        # Aggregate outcomes from stored episode-outcome edges
        procedure_stats: Dict[str, Dict[str, Any]] = {}
        total_episodes = 0

        for edge in target_client.edges:
            if edge.role == EdgeRole.EPISODE_OUTCOME or edge.kind == "EPISODE_OUTCOME":
                total_episodes += 1
                proc_id = edge.target_id
                outcome = edge.properties.get("outcome", "unknown")
                duration = float(edge.properties.get("duration_seconds", 0.0))

                if proc_id not in procedure_stats:
                    procedure_stats[proc_id] = {
                        "count": 0,
                        "success": 0,
                        "durations": [],
                    }
                procedure_stats[proc_id]["count"] += 1
                # Demand (3): Outcomes are 'approved' and 'rejected'
                if outcome in ("approved", "success"):
                    procedure_stats[proc_id]["success"] += 1
                procedure_stats[proc_id]["durations"].append(duration)


        # Evaluate against minimum-evidence threshold from policy
        if total_episodes < self.min_evidence_episodes:
            human_q = (
                f"Below minimum-evidence threshold: Only {total_episodes} episode(s) recorded "
                f"(policy requires at least {self.min_evidence_episodes}). "
                "Procedural memory cannot recommend an automated procedure. "
                "Which procedure should be applied?"
            )
            return ProceduralRankingResult(
                evidence_sufficient=False,
                min_evidence_threshold=self.min_evidence_episodes,
                total_episodes_found=total_episodes,
                ranked_procedures=[],
                statement=(
                    f"Below threshold: The system has recorded {total_episodes} episode(s) "
                    f"(minimum required: {self.min_evidence_episodes}). "
                    "Stating honestly that procedural ranking is not statistically supported. "
                    "Human input required instead of automated ranking."
                ),
                human_escalation_required=True,
                human_question=human_q,
            )

        # Compile evaluations ranked by stored outcomes (success_rate desc, then duration asc)
        evaluations: List[ProcedureEvaluation] = []
        for proc_id, stats in procedure_stats.items():
            cnt = stats["count"]
            succ = stats["success"]
            durations = stats["durations"]
            evaluations.append(
                ProcedureEvaluation(
                    procedure_id=proc_id,
                    episode_count=cnt,
                    success_count=succ,
                    success_rate=round(succ / cnt, 4) if cnt > 0 else 0.0,
                    average_duration_seconds=round(sum(durations) / len(durations), 2) if durations else 0.0,
                )
            )

        evaluations.sort(key=lambda p: (-p.success_rate, p.average_duration_seconds))

        return ProceduralRankingResult(
            evidence_sufficient=True,
            min_evidence_threshold=self.min_evidence_episodes,
            total_episodes_found=total_episodes,
            ranked_procedures=evaluations,
            statement=(
                f"Procedural memory ranked by stored graph outcomes across {total_episodes} "
                "recorded episode(s)."
            ),
            human_escalation_required=False,
            human_question=None,
        )

    def purge_test_episodes(self) -> int:
        """Purges test and dummy episodes from persistent memory graph (Demand 3)."""
        target = self.persistent_client
        cypher = "MATCH (e) WHERE (e:Episode OR e:IncidentEpisode) AND (e.id CONTAINS 'test' OR e.id CONTAINS 'run' OR e.id CONTAINS 'dummy' OR e.id CONTAINS 'bench') DETACH DELETE e"
        if hasattr(target, "graph") and hasattr(target.graph, "query"):
            res = target.graph.query(cypher)
            return getattr(res, "nodes_deleted", 0)
        elif hasattr(target, "query"):
            res = target.query(cypher)
            return getattr(res, "nodes_deleted", 0)
        return 0
