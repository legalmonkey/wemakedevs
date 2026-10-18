import sys
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.falkordb_client import FalkorDBGraphClient

API_BASE = "http://127.0.0.1:8001"

def measure_fresh_seeds(seeds=[5000, 5111, 5296]):
    print("=" * 105)
    print("STEP 1i: MEASURED NUMBERS ON THREE FRESH SEEDS")
    print(f"Seeds: {seeds}")
    print("=" * 105)

    results = []

    for seed in seeds:
        print(f"\n--- Triggering Seed {seed} via Incident API (speed_ms=0) ---")
        t0 = time.perf_counter()
        r = requests.post(
            f"{API_BASE}/api/incident/run",
            json={"seed": seed, "speed_ms": 0},
            timeout=10,
        )
        assert r.status_code == 200, f"Trigger failed: {r.status_code} {r.text}"
        tenant = r.json().get("tenant_id", f"tenant-seed-{seed}")

        # Poll until complete
        while True:
            time.sleep(0.1)
            st_r = requests.get(f"{API_BASE}/api/incident/status", timeout=5)
            if st_r.ok and not st_r.json().get("is_running"):
                break

        paced_duration_s = round(time.perf_counter() - t0, 3)

        # Fetch graph snapshot
        snap_r = requests.get(f"{API_BASE}/api/incident/graph", timeout=10)
        assert snap_r.status_code == 200, "Graph fetch failed"
        snap = snap_r.json()
        stats = snap.get("stats", {})
        time_to_scope_ms = stats.get("time_to_scope_ms", 0.0)

        # Directly query FalkorDB for the tenant graph
        client = FalkorDBGraphClient(tenant_id=tenant, clean=False)
        cypher_units = """
            MATCH (u:Unit)
            OPTIONAL MATCH (u)-[]-(d:Decision)
            OPTIONAL MATCH (u)-[]-(a:Action)
            WITH u,
                 sum(CASE WHEN d.verdict = 'unverifiable' OR d.status = 'unverifiable' THEN 1 ELSE 0 END) AS unv_count,
                 sum(CASE WHEN a.action_kind = 'escalate_human' OR a.kind = 'escalate_human' THEN 1 ELSE 0 END) AS esc_count
            RETURN u.id AS id,
                   coalesce(u.is_tainted, false) AS is_tainted,
                   coalesce(u.status, '') AS status,
                   coalesce(u.verdict, '') AS verdict,
                   unv_count,
                   esc_count
        """
        res = client.graph.query(cypher_units)
        rows = res.result_set or []
        total_units = len(rows)
        held = 0
        reaffirmed = 0
        escalated = 0
        unaffected = 0

        for row in rows:
            uid, is_tainted, status, verdict, unv_cnt, esc_cnt = row
            s = str(status).lower()
            v = str(verdict).lower()
            if unv_cnt > 0 or esc_cnt > 0:
                escalated += 1
            elif v == "reaffirmed" or s == "reaffirmed":
                reaffirmed += 1
            elif is_tainted or s == "quarantined" or v == "tainted":
                held += 1
            else:
                unaffected += 1

        tile_sum = held + reaffirmed + escalated + unaffected
        sum_matches = (tile_sum == total_units)

        # Lateral links
        cypher_lat = "MATCH (src:Unit)-[r:TAINTS]->(tgt:Unit) RETURN count(tgt)"
        lat_count = client.graph.query(cypher_lat).result_set[0][0]

        res_dict = {
            "seed": seed,
            "tenant": tenant,
            "total_units": total_units,
            "held": held,
            "reaffirmed": reaffirmed,
            "escalated": escalated,
            "unaffected": unaffected,
            "tile_sum": tile_sum,
            "sum_matches_total": sum_matches,
            "time_to_scope_ms": time_to_scope_ms,
            "paced_duration_s": paced_duration_s,
            "lateral_links": lat_count,
        }
        results.append(res_dict)

        print(f"Seed {seed}: Total={total_units} | Held={held} | Reaffirmed={reaffirmed} | Escalated={escalated} | Unaffected={unaffected}")
        print(f"Tile Sum: {tile_sum} == Total Units: {sum_matches}")
        print(f"Time to Scope (UI footer graph op): {time_to_scope_ms:.2f} ms (Wall-clock run duration: {paced_duration_s:.3f} s)")
        print(f"Lateral links count: {lat_count}")

    print("\n" + "=" * 105)
    print(f"{'Seed':<8} | {'Total':<6} | {'Held':<6} | {'Reaff':<6} | {'Escal':<6} | {'Unaff':<6} | {'Tile Sum':<9} | {'Sum==Tot':<9} | {'Scope Op ms':<12} | {'Wall-clock s':<13} | {'Lat Links'}")
    print("-" * 105)
    for r in results:
        print(f"{r['seed']:<8} | {r['total_units']:<6} | {r['held']:<6} | {r['reaffirmed']:<6} | {r['escalated']:<6} | {r['unaffected']:<6} | {r['tile_sum']:<9} | {str(r['sum_matches_total']):<9} | {r['time_to_scope_ms']:>10.2f}ms | {r['paced_duration_s']:>11.3f}s | {r['lateral_links']}")
    print("=" * 105)

if __name__ == "__main__":
    measure_fresh_seeds()
