# FalkorDB Hackathon Submission Form — Tainted

### Project Title [<= 80 chars]
Tainted: Autonomous Forensic Recall Tracer and Containment Agent System

---

### Description: Problem, Who It Is For, How It Works [200-250 words]
When a trusted fact turns out to be wrong, such as a drifting sensor or a supplier alert, manufacturers struggle to say which release decisions depended on it. The usual result is days of spreadsheet work, then either an over-broad recall or a missed batch.

Tainted is a prototype that models evidence, decisions, batches, shipments and customers as a graph in FalkorDB, with four agents working on top of it. When a fact is retracted, the Tracer follows every dependency, including sideways links through shared lots. The Adjudicator then re-judges each decision under a declared policy: if independent valid support remains, the batch is reaffirmed; if not, it is held; if a link cannot be verified, it is escalated to a person. The Dispatcher places holds and drafts customer notices only for customers who received a held batch, and a human approves each notice.

Verdicts come from policy evaluated in Cypher, never from a language model, and tools are offered to agents only when the graph state allows them. Every action stores the graph path that caused it, so any hold or release can be explained from the graph.

It is built for quality and compliance teams in food manufacturing. On 100 generated incidents, under a declared blanket-recall rule, it held a mean of 32.5% of the batches a blanket recall would, with no false reaffirmations against generated ground truth. It runs on generated data and is not a compliance product.

---

### Track(s)
Track 1: Agents That Act on Connected Data

---

### Repository URL
[Repository URL placeholder]

---

### Demo Video
[Demo video placeholder]

---

### Live Demo or Deployment
Tested locally from a clean clone. Requires Docker Desktop running FalkorDB (`docker compose up -d` or `docker run -p 6379:6379 -d --name falkordb-tainted falkordb/falkordb:latest`), Python 3.11+ for FastAPI backend on port 8001 (`python -m uvicorn api.main:app --port 8001 --host 127.0.0.1`), and Node.js 18+ for the Next.js evidence dossier UI on port 3000 (`cd ui && npm run build && npm start`). Open http://localhost:3000, select Seed 101, and click INVESTIGATE RECALL.

---

### How Did You Use FalkorDB [250-350 words]
We utilized FalkorDB as the single source of truth, coordination plane, and policy execution engine across six core technical challenges:

- **Multi-Hop Causal Propagation:** To trace contamination across supplier lots, blending tanks, and distribution shipments, TracerAgent executes recursive variable-length path traversal using `MATCH path = (e:Event {id: $event})-[:TAINTS*]->(target) RETURN target, length(path) AS hops, [n in nodes(path) | n.id] AS via_path`, capturing full provenance.
- **Lateral Co-Contamination Discovery:** When batches share physical tanks or equipment, TracerAgent uncovers hidden cross-contamination paths via lateral Cypher queries: `MATCH (u {id: $u})-[r]-(s) WHERE (r.role = 'lateral-link' OR type(r) = $lat_kind) AND s.id <> $u RETURN collect(DISTINCT s.id)`, achieving 100% hidden-link recall on benchmark faults.
- **Independent Evidence Reaffirmation:** To prevent blanket recalls, AdjudicatorAgent checks independent corroboration in FalkorDB via `MATCH (d {id: $dec})<-[r]-(ev) WHERE r.role = 'support' RETURN ev.id, ev.kind, properties(ev)`. Batches backed by at least the configured minimum (default two) independent evidence groups are reaffirmed, halting taint spread.
- **Policy Enforcement via Cypher Tool Gates:** Actions are governed by parameterised Cypher gates evaluated directly on the graph. For instance, `hold_unit` executes `MATCH (u:Unit {id: $entity_id}) WHERE u.is_tainted = true AND coalesce(u.status, '') <> 'reaffirmed' RETURN count(u) > 0 AS allowed`. If an entity is clean or reaffirmed, the tool is locked. Local deterministic formatting adapters handle natural language text, ensuring LLMs never decide verdicts.
- **Atomic Quarantine and Notice Dispatch:** DispatcherAgent executes atomic holds and recipient exposure notices via a single Cypher query: `MATCH (u {id: $unit_id}) ... SET u.status = 'quarantined' MERGE (h:Action {id: $hold_id}) ... WITH u, h OPTIONAL MATCH (u)-[:SHIPS_IN]->(s)-[:DELIVERED_TO]->(r) FOREACH ... MERGE (n:Action ...)` to maintain transactional graph consistency.
- **Crash Safety, Persistent Memory, and Tool APIs:** Crash recovery was tested on a seed (seed 404) with a mid-work OS-process kill on TracerAgent, matching the baseline graph hash with zero duplicate actions. Permanent outcomes are recorded to `g_memory_{tenant}` via `MERGE (e:Episode)-[:EPISODE_OUTCOME]->(p:Procedure)`. Graph algorithm tools (`algo_shortest_path`, `algo_centrality`, `algo_components`) are exposed over MCP; not used in the demo run.

---

### What I Liked About FalkorDB [80-120 words]
FalkorDB delivered in-memory graph execution on top of Redis, making it an ideal substrate for real-time multi-agent systems where agents coordinate purely through graph state. Running OpenCypher directly in memory eliminated ORM impedance mismatch and allowed us to express complex multi-hop causal tracing, variable-length path expansions, and policy gate invariants as single parameterised queries. The native support for Cypher UNWIND batching enabled rapid ingestion of dozens of nodes and edges in a single network round-trip. Crucially, per-tenant graph namespacing (`GRAPH.LIST`) allowed instant multi-tenant isolation and clean deterministic graph teardown between automated benchmark runs without restarting the server.

---

### Improvements I'd Like to See [80-120 words]
First, Cypher queries pairing `MATCH` and `CREATE` succeed with zero creations when any match pattern binds zero nodes without raising an error; an optional strict mode that warns or errors on missing endpoints would prevent accidental silent no-ops. Second, relationship types and labels containing hyphens require backtick escaping (such as ``-[:`derives-from`]->``) or query syntax errors occur; native support for hyphenated kebab-case identifiers would streamline domain ontology mapping. Third, per-query network round-trip latency over Redis becomes noticeable when issuing hundreds of single node/edge writes sequentially, making `UNWIND` batching mandatory for write throughput.

---

### Blog Link
[Leave blank]
