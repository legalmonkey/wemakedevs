import sys
sys.path.insert(0, ".")
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent

for seed in [101, 202, 303, 4812]:
    gc = generate_seeded_incident(seed, clean=True, tenant_id=f"tenant-{seed}")
    loop = EventLoop(tenant_id=f"tenant-{seed}")
    loop.register_agent(SentinelAgent(f"tenant-{seed}", gc))
    loop.register_agent(TracerAgent(f"tenant-{seed}", gc))
    loop.register_agent(AdjudicatorAgent(f"tenant-{seed}", gc))
    loop.register_agent(DispatcherAgent(f"tenant-{seed}", gc))
    for _ in range(10):
        res = loop.run_tick()
        if res.total_items_processed == 0:
            break

    q_tot = "MATCH (u:Unit) RETURN count(u)"
    tot = gc.graph.query(q_tot).result_set[0][0]

    q_held = """
    MATCH (u:Unit)
    WHERE u.verdict = 'tainted' OR u.status IN ['tainted', 'quarantined']
    RETURN count(u)
    """
    held = gc.graph.query(q_held).result_set[0][0]

    q_reaff = """
    MATCH (u:Unit)
    WHERE u.verdict = 'reaffirmed' OR u.status = 'reaffirmed'
    RETURN count(u)
    """
    reaff = gc.graph.query(q_reaff).result_set[0][0]

    q_esc = """
    MATCH (u:Unit)
    OPTIONAL MATCH (d:Decision)-[:SUPPORT|TAINTS]->(u)
    OPTIONAL MATCH (a:Action) WHERE (a.target_entity_id = u.id OR (a)-[:APPLIES_TO]->(u)) AND a.action_kind = 'escalate_human'
    WITH u, d, a
    WHERE d.verdict = 'unverifiable' OR a IS NOT NULL
    RETURN count(DISTINCT u)
    """
    esc = gc.graph.query(q_esc).result_set[0][0]

    q_sus = """
    MATCH (u:Unit)
    WHERE u.is_suspect = true OR (u)<-[:SHARED_LOT]-() OR (u)<-[:LATERAL_LINK]-()
    RETURN count(DISTINCT u)
    """
    sus = gc.graph.query(q_sus).result_set[0][0]

    print(f"Seed {seed}: tot={tot}, held={held}, reaff={reaff}, esc={esc}, sus={sus}")
