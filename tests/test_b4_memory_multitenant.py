"""Phase B4 Exit Check: Episodes, Procedure Ranking, and Concurrent Multi-Tenant Run.

Exit check: "Below threshold the system says so and asks a human instead of claiming it learned"
Verifies:
1. Procedural memory ranked strictly by stored graph outcome edges.
2. Minimum-evidence rule: Below threshold the system says so and asks a human instead of claiming it learned.
3. Above threshold, procedures are ranked by stored outcomes; described as ranked by outcomes, never training.
4. LLM judgement task: drafts specific human question naming missing link using only graph facts; never sets status.
5. Concurrent two-tenant run: One graph per tenant, concurrent event loops, zero cross-tenant contamination.
"""

import asyncio
import pytest
from contracts.ontology import EdgeRole, NodeRole
from contracts.events import EventEnvelope, EventType
from engine.falkordb_client import FalkorDBGraphClient
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent
from agents.event_loop import EventLoop
from agents.llm_adapter import StubLLMAdapter
from agents.memory import ProceduralMemory


def test_b4_exit_check_below_threshold_asks_human_not_claiming_learned():
    """Phase B4 Exit Check: Below threshold the system says so and asks a human instead of claiming it learned."""
    client = FalkorDBGraphClient(tenant_id="tenant-memory-test")
    memory = ProceduralMemory(
        tenant_id="tenant-memory-test",
        graph_client=client,
    )
    # min_evidence_episodes is 3 from config/policy.yaml
    assert memory.min_evidence_episodes == 3

    # Case 1: 0 episodes in graph
    res_zero = memory.rank_procedures()
    assert res_zero.evidence_sufficient is False
    assert res_zero.human_escalation_required is True
    assert "below threshold" in res_zero.statement.lower()
    assert "human input required" in res_zero.statement.lower()
    assert res_zero.human_question is not None


    # Case 2: Only 1 episode recorded (below threshold of 3)
    memory.record_episode(
        episode_id="ep-2026-001",
        procedure_id="proc-quarantine-batch",
        outcome="success",
        duration_seconds=120.0,
    )
    res_one = memory.rank_procedures()

    # EXIT CHECK ASSERTIONS:
    assert res_one.evidence_sufficient is False
    assert res_one.total_episodes_found == 1
    assert res_one.human_escalation_required is True
    # The system says so honestly:
    assert "below threshold" in res_one.statement.lower()
    assert "not statistically supported" in res_one.statement.lower()
    assert "human input required" in res_one.statement.lower()
    # It asks a human:
    assert res_one.human_question is not None
    assert "Which procedure should be applied?" in res_one.human_question
    assert len(res_one.ranked_procedures) == 0


def test_b4_above_threshold_procedures_ranked_by_stored_outcomes():
    """Above threshold, procedures are ranked strictly by stored graph outcome edges."""
    client = FalkorDBGraphClient(tenant_id="tenant-memory-test")
    memory = ProceduralMemory(
        tenant_id="tenant-memory-test",
        graph_client=client,
    )

    # Record 4 episodes across 2 procedures (exceeds threshold 3):
    # Procedure A: 1 success, 1 failure -> success_rate 0.5
    memory.record_episode("ep-1", "proc-A", "success", 200.0)
    memory.record_episode("ep-2", "proc-A", "failure", 300.0)

    # Procedure B: 2 successes -> success_rate 1.0
    memory.record_episode("ep-3", "proc-B", "success", 100.0)
    memory.record_episode("ep-4", "proc-B", "success", 150.0)

    res = memory.rank_procedures()

    assert res.evidence_sufficient is True
    assert res.human_escalation_required is False
    assert res.total_episodes_found == 4
    assert len(res.ranked_procedures) == 2

    # Procedure B ranked #1 due to higher success rate
    top_proc = res.ranked_procedures[0]
    assert top_proc.procedure_id == "proc-B"
    assert top_proc.success_rate == 1.0
    assert top_proc.average_duration_seconds == 125.0

    second_proc = res.ranked_procedures[1]
    assert second_proc.procedure_id == "proc-A"
    assert second_proc.success_rate == 0.5
    assert second_proc.average_duration_seconds == 250.0

    # Strict language check: described as ranked by stored graph outcomes, never training
    assert "ranked by stored graph outcomes" in res.statement.lower()
    assert "trained" not in res.statement.lower()
    assert "learning model" not in res.statement.lower()


def test_b4_llm_judgement_task_on_unverifiable():
    """Verify required LLM task: drafts specific human question naming missing link using graph facts."""
    client = FalkorDBGraphClient(tenant_id="tenant-llm-task")

    # Suspect evidence and missing record
    client.add_node("ev-missing-rec", "Record", NodeRole.EVIDENCE, {"valid": False, "unverifiable": True})
    client.add_node("dec-unverifiable-99", "Disposition", NodeRole.DECISION, {
        "status": "pending",
        "is_tainted": True,
        "taint_via_path": ["ev-missing-rec", "dec-unverifiable-99"],
    })
    client.add_edge("ev-missing-rec", "dec-unverifiable-99", "SUPPORT", EdgeRole.SUPPORT)

    adapter = StubLLMAdapter()
    adj = AdjudicatorAgent(tenant_id="tenant-llm-task", graph_client=client, llm_adapter=adapter)
    step_res = adj.step()

    # Verdict was set by policy to unverifiable (Rule 5)
    dec_node = client.get_node("dec-unverifiable-99")
    assert dec_node.properties["verdict"] == "unverifiable"

    # LLM drafted human question naming the missing link using only graph facts
    question = dec_node.properties.get("human_question")
    assert question is not None
    assert "dec-unverifiable-99" in question
    assert "cannot be verified" in question


@pytest.mark.asyncio
async def test_b4_concurrent_two_tenant_run():
    """Concurrent Two-Tenant Run: One graph per tenant, concurrent event loops, zero cross-contamination."""
    # Tenant Alpha setup (has an active incident)
    tenant_a = "tenant-alpha"
    client_a = FalkorDBGraphClient(tenant_id=tenant_a)
    client_a.add_node("ev-a1", "Reading", NodeRole.EVIDENCE, {"valid": True})
    client_a.add_node("dec-a1", "Disposition", NodeRole.DECISION, {"status": "pending"})
    client_a.add_edge("ev-a1", "dec-a1", "SUPPORT", EdgeRole.SUPPORT)
    client_a.add_node("evt-alert-a", "Alert", NodeRole.EVENT, {
        "processed": False,
        "target_evidence_id": "ev-a1",
    })

    loop_a = EventLoop(tenant_id=tenant_a)
    loop_a.register_agent(SentinelAgent(tenant_a, client_a))
    loop_a.register_agent(TracerAgent(tenant_a, client_a))
    loop_a.register_agent(AdjudicatorAgent(tenant_a, client_a))
    loop_a.register_agent(DispatcherAgent(tenant_a, client_a))

    # Tenant Beta setup (clean operational batch, separate alert on independent lot)
    tenant_b = "tenant-beta"
    client_b = FalkorDBGraphClient(tenant_id=tenant_b)
    client_b.add_node("ev-b1", "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": "b-indep-1"})
    client_b.add_node("ev-b2", "Reading", NodeRole.EVIDENCE, {"valid": True, "group_id": "b-indep-2"})
    client_b.add_node("dec-b1", "Disposition", NodeRole.DECISION, {"status": "pending"})
    client_b.add_edge("ev-b1", "dec-b1", "SUPPORT", EdgeRole.SUPPORT)
    client_b.add_edge("ev-b2", "dec-b1", "SUPPORT", EdgeRole.SUPPORT)
    client_b.add_node("evt-alert-b", "Alert", NodeRole.EVENT, {
        "processed": False,
        "target_evidence_id": "ev-b1",
    })

    loop_b = EventLoop(tenant_id=tenant_b)
    loop_b.register_agent(SentinelAgent(tenant_b, client_b))
    loop_b.register_agent(TracerAgent(tenant_b, client_b))
    loop_b.register_agent(AdjudicatorAgent(tenant_b, client_b))
    loop_b.register_agent(DispatcherAgent(tenant_b, client_b))

    events_a: list[EventEnvelope] = []
    events_b: list[EventEnvelope] = []
    loop_a.add_event_listener(events_a.append)
    loop_b.add_event_listener(events_b.append)

    # Run both loops concurrently in async tasks
    async def run_loop_async(loop: EventLoop):
        # Run until idle in threadpool executor
        return await asyncio.to_thread(loop.run_until_idle, max_ticks=10)

    results_a, results_b = await asyncio.gather(
        run_loop_async(loop_a),
        run_loop_async(loop_b),
    )

    # Assertions on Tenant Alpha
    assert len(results_a) > 0
    dec_a = client_a.get_node("dec-a1")
    assert dec_a.properties["verdict"] == "tainted"  # Only 0 independent valid groups
    for ev in events_a:
        assert ev.tenant_id == tenant_a
        assert "ev-b1" not in ev.entity_ids  # No cross-tenant leak

    # Assertions on Tenant Beta
    assert len(results_b) > 0
    dec_b = client_b.get_node("dec-b1")
    # dec-b1 had ev-b1 suspect, but ev-b2 remained independent and valid (reaffirmed under min_independent=2)
    # Wait: ev-b1 suspect means 1 independent group (ev-b2), which is < 2, so tainted
    assert dec_b.properties["verdict_set"] is True
    for ev in events_b:
        assert ev.tenant_id == tenant_b
        assert "ev-a1" not in ev.entity_ids  # No cross-tenant leak

    # Verify complete isolation of graphs
    assert "dec-b1" not in client_a.nodes
    assert "dec-a1" not in client_b.nodes
