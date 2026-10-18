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
https://github.com/legalmonkey/wemakedevs

---

### Demo Video
[Demo video placeholder]

---

### Live Demo or Deployment
Tested locally from a clean clone. Requires Docker Desktop running FalkorDB (`docker compose up -d` or `docker run -p 6379:6379 -d --name falkordb-tainted falkordb/falkordb:latest`), Python 3.11+ for FastAPI backend on port 8001 (`python -m uvicorn api.main:app --port 8001 --host 127.0.0.1`), and Node.js 18+ for the Next.js evidence dossier UI on port 3000 (`cd ui && npm run build && npm start`). Open http://localhost:3000, select Seed 101, and click INVESTIGATE RECALL.

---

### How Did You Use FalkorDB [250-350 words]
We used FalkorDB as the shared state, coordination layer and policy engine for four agents (Sentinel, Tracer, Adjudicator, Dispatcher). The agents never call each other; they only read and write the graph. It solved six problems. (1) Multi-hop tracing: the Tracer follows a variable-length path from a retracted event through decisions, batches and shipments to customers, and stores the hop count and path on each TAINTS edge. (2) Lateral links: batches that share a lot or equipment are found by a Cypher traversal over lateral-link relationships; on 100 generated incidents, every injected lateral link was recalled. (3) Reaffirmation: a Cypher support check counts independent evidence groups per decision, and a decision with at least the configured minimum (default two) is reaffirmed instead of recalled. (4) Tool gates: an agent is offered the hold tool only when a parameterised Cypher gate confirms the batch is tainted and not reaffirmed; no language model decides verdicts, and notice text comes from a deterministic formatter. (5) Atomic dispatch: the Dispatcher places a hold and drafts customer notices for exposed recipients in one idempotent query, which avoids duplicate actions after a restart. (6) Crash safety, memory and tools: in a test on seed 404, killing the Tracer process mid-work and restarting it produced a final graph identical to an uninterrupted run, with no duplicate actions. Human approvals and rejections are stored as episodes linked to procedures in a per-tenant graph. Shortest-path, centrality and connected-components tools are exposed over MCP but are not used in the demo run. The exact Cypher queries are listed in the repository README.

---

### What I Liked About FalkorDB [80-120 words]
FalkorDB delivered in-memory graph execution on top of Redis, making it an ideal substrate for real-time multi-agent systems where agents coordinate purely through graph state. Running OpenCypher directly in memory eliminated ORM impedance mismatch and allowed us to express complex multi-hop causal tracing, variable-length path expansions, and policy gate invariants as single parameterised queries. The native support for Cypher UNWIND batching enabled rapid ingestion of dozens of nodes and edges in a single network round-trip. Crucially, per-tenant graph namespacing (`GRAPH.LIST`) allowed instant multi-tenant isolation and clean deterministic graph teardown between automated benchmark runs without restarting the server.

---

### Improvements I'd Like to See [80-120 words]
First, Cypher queries pairing `MATCH` and `CREATE` succeed with zero creations when any match pattern binds zero nodes without raising an error; an optional strict mode that warns or errors on missing endpoints would prevent accidental silent no-ops. Second, relationship types and labels containing hyphens require backtick escaping (such as ``-[:`derives-from`]->``) or query syntax errors occur; native support for hyphenated kebab-case identifiers would streamline domain ontology mapping. Third, per-query network round-trip latency over Redis becomes noticeable when issuing hundreds of single node/edge writes sequentially, making `UNWIND` batching mandatory for write throughput.

---

### Blog Link
[Leave blank]
