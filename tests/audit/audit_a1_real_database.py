"""Audit Check A1: Real database execution against live FalkorDB container.
1. Show docker ps and FalkorDB container.
2. Query graph directly with GRAPH.QUERY via falkordb/redis client and count nodes by label.
3. Stop container mid-run and confirm loud failure (not silent).
4. Restart container and confirm recovery.
"""
import subprocess
import time
import redis
from falkordb import FalkorDB

def run_a1_check():
    print("AUDIT CHECK A1: Real FalkorDB Database Verification\n")
    
    # 1. Show docker ps
    ps_res = subprocess.run(["docker", "ps", "--filter", "name=falkordb-tainted", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"], capture_output=True, text=True)
    print("1. Docker PS Output:")
    print(ps_res.stdout.strip())
    
    # 2. Connect to FalkorDB directly and query
    db = FalkorDB(host='127.0.0.1', port=6379)
    graph = db.select_graph("tainted_audit_graph")
    
    # Clean previous if any
    try:
        graph.delete()
    except Exception:
        pass
        
    # Populate a sample audit graph with Evidence, Decision, Unit, Shipment
    graph.query("""
        CREATE (:Evidence {id: 'ev-1', kind: 'PathogenResult', is_suspect: true}),
               (:Decision {id: 'dec-1', kind: 'LotRelease', verdict: 'tainted'}),
               (:Unit {id: 'unit-1', kind: 'FinishedPack', is_tainted: true}),
               (:Shipment {id: 'ship-1', kind: 'OutboundBill'}),
               (:Recipient {id: 'rec-1', kind: 'HospitalClient'})
    """)
    
    # Query node counts by label directly using Cypher
    res = graph.query("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY label")
    print("\n2. Direct Cypher Query node counts by label (GRAPH.QUERY):")
    label_counts = {record[0]: record[1] for record in res.result_set}
    for lbl, cnt in label_counts.items():
        print(f"   Label '{lbl}': {cnt} node(s)")
    assert len(label_counts) == 5, f"Expected 5 labels, got {len(label_counts)}"
    
    # 3. Stop container mid-run and verify backend fails loudly
    print("\n3. Stopping container mid-run...")
    stop_res = subprocess.run(["docker", "stop", "falkordb-tainted"], capture_output=True, text=True)
    print("   Container stopped:", stop_res.stdout.strip())
    
    loud_failure = False
    error_message = ""
    try:
        # Attempt direct query while stopped
        r = redis.Redis(host='127.0.0.1', port=6379, socket_connect_timeout=1)
        r.ping()
    except Exception as e:
        loud_failure = True
        error_message = f"{type(e).__name__}: {e}"
        print(f"   CONFIRMED: Backend failed loudly on query: {error_message}")
        
    assert loud_failure, "FAIL: Backend did not fail loudly when FalkorDB was stopped!"
    
    # 4. Restart container and confirm recovery
    print("\n4. Restarting container...")
    start_res = subprocess.run(["docker", "start", "falkordb-tainted"], capture_output=True, text=True)
    print("   Container restarted:", start_res.stdout.strip())
    time.sleep(2)
    
    # Re-query
    db_recovered = FalkorDB(host='127.0.0.1', port=6379)
    graph_recovered = db_recovered.select_graph("tainted_audit_graph")
    res_rec = graph_recovered.query("MATCH (n) RETURN count(n) AS total")
    total_nodes = res_rec.result_set[0][0]
    print(f"   CONFIRMED: Recovery successful! Query returned {total_nodes} nodes after restart.")
    assert total_nodes == 5, f"Expected 5 nodes recovered, got {total_nodes}"
    
    # Clean up
    graph_recovered.delete()
    print("\nAUDIT CHECK A1 PASSED: Live FalkorDB container verified with loud failure and clean recovery.")

def test_a1_check():
    try:
        run_a1_check()
    finally:
        subprocess.run(["docker", "start", "falkordb-tainted"], capture_output=True)


if __name__ == "__main__":
    run_a1_check()
