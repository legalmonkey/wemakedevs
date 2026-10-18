import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
import time
from engine.falkordb_client import FalkorDBGraphClient

API = "http://127.0.0.1:8001"

def check_seed(seed=101):
    for run in [1, 2]:
        r = requests.post(f"{API}/api/incident/run", json={"seed": seed, "speed_ms": 0})
        while True:
            time.sleep(0.1)
            st = requests.get(f"{API}/api/incident/status").json()
            if not st.get("is_running"):
                break

        client = FalkorDBGraphClient(tenant_id=f"tenant-seed-{seed}", clean=False)
        q = """
            MATCH (u:Unit)
            OPTIONAL MATCH (u)-[]-(d:Decision)
            OPTIONAL MATCH (u)-[]-(a:Action)
            WITH u,
                 sum(CASE WHEN d.verdict = 'unverifiable' OR d.status = 'unverifiable' THEN 1 ELSE 0 END) AS unv_count,
                 sum(CASE WHEN a.action_kind = 'escalate_human' OR a.kind = 'escalate_human' THEN 1 ELSE 0 END) AS esc_count
            RETURN u.id, coalesce(u.is_tainted, false), coalesce(u.status, ''), coalesce(u.verdict, ''), unv_count, esc_count
        """
        rows = client.graph.query(q).result_set or []
        held, reaff, esc, unaff = 0, 0, 0, 0
        for r_row in rows:
            uid, is_t, status, verd, unv_cnt, esc_cnt = r_row
            s, v = str(status).lower(), str(verd).lower()
            if unv_cnt > 0 or esc_cnt > 0:
                esc += 1
            elif v == "reaffirmed" or s == "reaffirmed":
                reaff += 1
            elif s == "quarantined" or v == "tainted":
                held += 1
            else:
                unaff += 1

        actions_q = "MATCH (a:Action) RETURN a.action_type, count(*)"
        acts = client.graph.query(actions_q).result_set

        # Lateral links
        cypher_lat = "MATCH (src:Unit)-[r:TAINTS]->(tgt:Unit) RETURN count(tgt)"
        lat_count = client.graph.query(cypher_lat).result_set[0][0]

        print(f"Run {run} on Seed {seed}: Total={len(rows)} | Held={held} | Reaffirmed={reaff} | Escalated={esc} | Unaffected={unaff} | Lateral={lat_count} | Actions={acts}")

if __name__ == "__main__":
    check_seed(101)
