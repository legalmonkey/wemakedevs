# Tainted — 3-Minute Live Demo Script

This script provides an exact, time-stamped presenter walkthrough for demonstrating the **Tainted** forensic recall tracer.

---

## Pre-Demo Checklist

1. **FalkorDB**: Running on port `6379` (`docker compose up -d`).
2. **FastAPI Backend**: Running on port `8001` (`python -m uvicorn api.main:app --port 8001`).
3. **Next.js Frontend**: Running on port `3000` (`npm run dev` in `ui/`).
4. **Browser**: Open [http://localhost:3000](http://localhost:3000) at 100% zoom (1440x900 recommended).

---

## The 3-Minute Narrative Flow

### [0:00 - 0:30] Scene Setting: The Crisis & Calm Paper Aesthetic

- **Action**: Display the clean, high-contrast tactile paper dashboard before triggering the incident. Point out the initial topology showing raw lots, blending operations, and finished retail packs.
- **Narrative**:
  > *"Every product recall begins in panic. A sensor flags a temperature violation, a supplier tests positive for an adulterant, and management's instinctive reaction is a blanket recall. They shut down distribution, hold every truck, draft frantic customer alerts, and incinerate millions of dollars in good inventory.*
  >
  > *Tainted replaces panic with graph-theoretic rigor. We run on FalkorDB to trace verified contamination chains of custody, pinpoint the exact affected perimeter, and prove which batches are safe to release."*

---

### [0:30 - 1:15] Incident Trigger: Multi-Hop Lateral Spread

- **Action**: Select Seed `9011` (or click **Trigger Incident Run**). Observe the live event stream and forensic canvas updating.
- **Narrative**:
  > *"When an alert triggers, our Sentinel agent flags the initial sensor reading in FalkorDB. Immediately, the Tracer agent begins traversing upstream supplier links and downstream processing tanks.*
  >
  > *Notice this lateral link: batchlot `3e59e543` was blended into another production line. Most relational databases miss lateral tank sharing without expensive recursive joins. FalkorDB navigates the multi-hop trajectory in milliseconds, stamping affected units with bold red **`HOLD`** stamps."*

---

### [1:15 - 1:45] The Core Pitch: The Reaffirmation Beat

- **Action**: Highlight the green **`REAFFIRMED`** nodes on the canvas and point to the metric tile showing Reaffirmed units.
- **Narrative**:
  > *"Here is the breakthrough. Look at these finished units downstream. Under a naive blanket recall, they would be destroyed.*
  >
  > *Our Adjudicator agent evaluates graph evidence against our independent evidence policy. It discovers that this lot received testing from two separate accredited laboratories with zero negative findings. Because the independent evidence threshold is satisfied, the agent draws back taint and stamps the batch with serene green **`REAFFIRMED`** ink.*
  >
  > *The result? Up to 15% to 30% of inventory is safely spared from destruction with verifiable mathematical proof."*

---

### [1:45 - 2:20] Cypher Tool Gate Invariance & MCP

- **Action**: Switch to the **Cypher Audit Log** or trigger the Tool Gate inspection.
- **Narrative**:
  > *"How do we know the agents don't hallucinate a release? In Tainted, the LLM never decides.*
  >
  > *Every privileged tool execution is guarded by a Cypher gate executed directly in FalkorDB. If a batch does not meet the graph policy query—such as minimum independent test count—the tool is mathematically withheld. The agent cannot call what the graph does not unlock."*

---

### [2:20 - 3:00] Human Governance: Why Drawer & Action Approval

- **Action**: Click on the **Review Queue** tab. Click **Inspect Causal Trajectory** on the pending customer notice. Show the **Why Drawer** sliding open with the complete step-by-step chain of custody. Then click **APPROVE ACTION**.
- **Narrative**:
  > *"Finally, human governance is non-negotiable. Critical external actions—such as customer exposure advisories—are placed in our Review Queue as drafts.*
  >
  > *In one click, an operator opens the Why Drawer to view the complete chain of custody from the origin sensor through every intermediary tank to the retail pack.*
  >
  > *Satisfied with the forensic path, the operator clicks **APPROVE ACTION**. The action is signed off, the audit ledger commits the event, and the incident reaches full quiescence."*

---

## Key Metrics to Emphasize

- **Graph Traversal Speed**: < 200 ms graph operation time.
- **Reaffirmation Yield**: Spares 10–30% of inventory from unnecessary blanket destruction.
- **False Reaffirmations**: 0 across all benchmarked runs.
- **Why Drawer Access**: $\le 2$ interactions from anywhere on the canvas.
