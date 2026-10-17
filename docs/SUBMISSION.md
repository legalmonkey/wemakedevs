# Tainted — FalkorDB Hackathon Submission (Track 1)

**Tainted** is a forensic recall tracer and decision-support system that replaces the panic of blanket recalls with the mathematical precision of **FalkorDB** graph algorithms and Cypher tool gates.

---

## 1. Project Information

- **Project Name**: Tainted
- **Hackathon Track**: Track 1 — Core Graph & Multi-Agent Workflows
- **Target Domain**: Food & Beverage, Pharma, and Cold-Chain Manufacturing Supply Chains
- **Primary Database**: FalkorDB (Redis-based Graph Database)

---

## 2. FalkorDB Graph Capabilities Showcased

Tainted is built entirely around native FalkorDB capabilities, treating the graph as the single source of shared state across all agents (Section 0 Rule 4):

1. **Graph-As-Shared-State Multi-Agent Loop**:
   - Four specialized agents (`Sentinel`, `Tracer`, `Adjudicator`, `Dispatcher`) coordinate asynchronously without direct inter-agent messaging.
   - All state transitions, taint propagation, evidence evaluations, and incident events are committed as graph nodes and edges.

2. **Cypher Tool Gates (Section 0 Rule 5)**:
   - Tool execution is strictly governed by parameterized Cypher gate expressions evaluated directly in FalkorDB.
   - LLMs are never granted execution access to privileged tools (such as releasing units or drafting exposure notices) until the graph state mathematically satisfies policy queries.

3. **Multi-Hop Lateral Traversal & Hidden-Link Detection**:
   - Traces complex cross-contamination paths across shared tanks, blending stages, and supplier split-lots (`SHARED_LOT`, `BLENDED_INTO`, `TAINTS`).
   - Achieves 100% recall on injected lateral contamination links across 100 benchmark seeds.

4. **Episodic & Procedural Memory**:
   - Past incident trajectories and outcomes are committed to graph memory (`Episode`, `Procedure`).
   - Enables procedural comparison across containment workflows while maintaining strict boundary integrity.

5. **Stored Causal Chain of Custody (Why Drawer)**:
   - Every action and decision stores its full causal trajectory (`causal_path`) in graph properties, retrievable in $\le 2$ clicks from the canvas.

---

## 3. Technology Stack

- **Graph Database**: FalkorDB (via `falkordb-py`)
- **Backend**: Python 3.11, FastAPI, Uvicorn, Pydantic v2
- **Frontend**: Next.js 14 (App Router), TypeScript, Vanilla CSS design tokens, SVG Forensic Canvas
- **Design System**: Neo-brutalist paper aesthetic with distinct physical ink stamps (`HOLD`, `REAFFIRMED`, `ESCALATED`, `SUSPECT`)
- **Test Infrastructure**: Pytest (126 tests, 0 failures, 0 skips), Playwright (multi-viewport UI testing)

---

## 4. Empirical Performance & Verification

All metrics are verified through automated test suites documented in `docs/AUDIT.md` and `docs/CLAIMS.md`:

| Benchmark Area | Metric | Result |
| :--- | :--- | :--- |
| **Test Suite** | Green suite pass rate | **126 passed, 0 failures, 0 skips** |
| **Crash Safety** | Process kill recovery invariance | **100% bit-for-bit hash match; 0 duplicate actions** |
| **Recall Precision** | False Reaffirmations | **0 across 100 seeds** |
| **Hidden-Link Recall** | Lateral contamination detection | **100.0% (100/100 seeds)** |
| **Explanation Coverage** | Stored causal path completeness | **100.0% (0 null paths)** |
| **Graph Query Latency** | Full incident scoping latency | **< 200 ms graph operation time** |
| **Demo Run Reliability** | 3 clean keyboard demo runs | **Completed in < 12s each (Target: < 180s)** |

---

## 5. Reviewer Quickstart

### Automated Launch

```bash
# 1. Start FalkorDB in Docker
docker compose up -d

# 2. Launch FastAPI Backend (Port 8001)
pip install -r requirements.txt
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001 &

# 3. Launch Next.js UI (Port 3000)
cd ui && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Key Verification Commands

```bash
# Run full standard test suite
python -m pytest tests/test_*.py tests/part_c/test_*.py -v

# Run crash safety and property audit
python -m pytest tests/audit/test_demand1_crash_safety.py -v

# Run 3 clean keyboard demo runs on fresh seeds
python scripts/verify_item7_demo_runs.py

# Run static linting
python scripts/lint.py
```

---

## 6. Documentation Index

- `README.md` — Project overview and getting started guide
- `docs/CLAIMS.md` — Complete empirical metrics, benchmark tables, and verified boundaries
- `docs/DEMO_SCRIPT.md` — 3-minute presenter guide with narrative beats and timecodes
- `docs/AUDIT.md` — Master forensic audit log with verbatim command outputs from all testing rounds
- `docs/screens/` — Visual proof: 1440px desktop, 390px mobile, Why Drawer, and 3 demo run captures
