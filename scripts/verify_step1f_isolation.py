import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import redis
from engine.falkordb_client import FalkorDBGraphClient

# 1. Create two isolated tenants
client_a = FalkorDBGraphClient(tenant_id="tenant-isolation-alpha", clean=True)
client_b = FalkorDBGraphClient(tenant_id="tenant-isolation-beta", clean=True)

print(f"Tenant A graph name: {client_a.graph_name}")
print(f"Tenant B graph name: {client_b.graph_name}")

# 2. Add distinct nodes
client_a.add_node("secret-asset-A", "Unit", "Unit", {"secret": "alpha-payload"})
client_b.add_node("secret-asset-B", "Unit", "Unit", {"secret": "beta-payload"})

# 3. List graphs in Redis
r = redis.Redis(host="127.0.0.1", port=6379)
graph_list = [g.decode("utf-8") if isinstance(g, bytes) else str(g) for g in r.execute_command("GRAPH.LIST")]
print("\nFalkorDB GRAPH.LIST (showing isolation graphs):")
print([g for g in graph_list if "isolation" in g])

# 4. Cross-tenant queries
query_a_for_b = client_a.graph.query("MATCH (n {id: 'secret-asset-B'}) RETURN count(n)").result_set[0][0]
query_b_for_a = client_b.graph.query("MATCH (n {id: 'secret-asset-A'}) RETURN count(n)").result_set[0][0]

print(f"\nQuerying Tenant A for secret-asset-B: found {query_a_for_b} node(s) (Expected: 0)")
print(f"Querying Tenant B for secret-asset-A: found {query_b_for_a} node(s) (Expected: 0)")

assert query_a_for_b == 0
assert query_b_for_a == 0
print("\n[VERIFIED] Per-tenant isolation 100% confirmed.")
