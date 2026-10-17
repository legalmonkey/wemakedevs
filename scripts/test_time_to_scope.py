import sys
sys.path.insert(0, ".")
import time
from engine.incident_generator import generate_seeded_incident
from agents.event_loop import EventLoop
from agents.sentinel import SentinelAgent
from agents.tracer import TracerAgent
from agents.adjudicator import AdjudicatorAgent
from agents.dispatcher import DispatcherAgent

for run_i in [1, 2]:
    gc = generate_seeded_incident(101, clean=True, tenant_id=f"tenant-101-run{run_i}")
    t_ev = time.time()
    gc.graph.query("MATCH (e:Event) SET e.timestamp = $ts", {"ts": t_ev})
    
    loop = EventLoop(tenant_id=f"tenant-101-run{run_i}")
    loop.register_agent(SentinelAgent(f"tenant-101-run{run_i}", gc))
    loop.register_agent(TracerAgent(f"tenant-101-run{run_i}", gc))
    loop.register_agent(AdjudicatorAgent(f"tenant-101-run{run_i}", gc))
    loop.register_agent(DispatcherAgent(f"tenant-101-run{run_i}", gc))
    for _ in range(10):
        res = loop.run_tick()
        for ev in res.events_emitted:
            ev_type_str = str(ev.event_type.value if hasattr(ev.event_type, "value") else ev.event_type)
            if "taint" in ev_type_str.lower() and len(ev.entity_ids) >= 2:
                t_now = time.time()
                gc.graph.query(
                    "MATCH (a {id: $src})-[r:TAINTS]->(b {id: $tgt}) SET r.timestamp = $ts",
                    {"src": ev.entity_ids[0], "tgt": ev.entity_ids[1], "ts": t_now}
                )
        if res.total_items_processed == 0:
            break
            
    q_scope = """
    MATCH (e:Event)
    MATCH ()-[r:TAINTS]->()
    WHERE e.timestamp IS NOT NULL AND r.timestamp IS NOT NULL
    RETURN (max(r.timestamp) - min(e.timestamp)) * 1000.0
    """
    raw_val = gc.graph.query(q_scope).result_set[0][0]
    val = round(raw_val, 2)
    print(f"Seed 101 Run {run_i}: time_to_scope = {val} ms")
