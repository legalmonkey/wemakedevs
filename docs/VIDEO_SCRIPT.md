# Tainted — 3-Minute Video Demonstration Script

Screen recording script and spoken narration for the production build demonstration (`npm run build && npm start`).

---

## Pre-Recording Checklist
- [ ] FalkorDB container running: `docker ps` confirms `falkordb-tainted` on port `6379`.
- [ ] Backend running: `python -m uvicorn api.main:app --port 8001 --host 127.0.0.1`.
- [ ] Frontend running in production mode: `cd ui && npm run build && npm start` on port `3000`.
- [ ] Next.js development badge is absent from bottom-left corner.
- [ ] Browser window width set to exactly `1440px` (height `900px`).
- [ ] Demo Seed selected: **Seed 101** (empirically verified in two consecutive runs: 35 total units, 7 held, 5 reaffirmed, 0 escalated, 23 unaffected).
- [ ] Primary button verified: **INVESTIGATE RECALL** (`#btn-investigate`).
- [ ] Narration rule: Do not cite unmeasured speed numbers or read out the footer duration aloud.

---

## Timed Shot List & Spoken Narration (180 Seconds Total)

### Beat 1: The Problem & The Baseline Canvas (0:00 – 0:30)
- **Visual:** Browser opens to `http://localhost:3000`. Calm paper background shows the food supply chain topology before incident trigger on Seed 101. Node counters show 0 held.
- **Action:** Mouse hovers over clean batch nodes and supplier lots.
- **Spoken Narration (0:00 – 0:30):**
  > "When a trusted fact turns out to be wrong—like a drifting sensor or a supplier alert—manufacturers struggle to know which release decisions depended on it. The usual result is days of spreadsheet tracing, followed by either an over-broad recall or a missed contaminated batch.
  > 
  > Tainted models evidence, decisions, batches, shipments, and customer accounts as a property graph in FalkorDB, with four autonomous agents coordinating on top of it. Let's see what happens when a contamination alert strikes."

---

### Beat 2: Triggering the Incident & Sentinel Alert (0:30 – 0:55)
- **Visual:** Operator confirms Seed 101 in the header and clicks the primary action button: **"INVESTIGATE RECALL"**.
- **Action:** Click `INVESTIGATE RECALL`. Live event stream ticker begins updating. Sentinel Agent flags drifted sensor evidence.
- **Spoken Narration (0:30 – 0:55):**
  > "We select Seed 101 and click Investigate Recall. The Sentinel Agent immediately detects a calibration drift on an upstream sensor log.
  > 
  > Instead of halting the entire facility, Sentinel writes the retracted evidence directly into FalkorDB and activates the multi-agent dependency trace."

---

### Beat 3: Multi-Hop Propagation & Lateral Links (0:55 – 1:25)
- **Visual:** The Tracer Agent propagates `TAINTS` edges across the graph canvas. Amber warning stamps appear on affected batch lots. A lateral link flashes connecting a shared lot to an otherwise separate line.
- **Action:** Zoom in on the canvas to highlight the lateral connection (`SHARED_LOT` / `TAINTS` hop).
- **Spoken Narration (0:55 – 1:25):**
  > "The Tracer Agent follows causal dependencies through processing decisions and blending tanks. Crucially, it uncovers sideways links through shared equipment that contaminated an adjacent product line.
  > 
  > Traditional batch tracking easily misses these sideways dependencies, leaving contaminated products in circulation."

---

### Beat 4: The Reaffirmation Beat (1:25 – 1:55)
- **Visual:** The Adjudicator Agent evaluates Decision nodes. Clean batches with independent valid support are stamped with tranquil green **`REAFFIRMED`** ink. Tile counters update: 5 units reaffirmed.
- **Action:** Click on one of the green `REAFFIRMED` batch nodes on the canvas.
- **Spoken Narration (1:25 – 1:55):**
  > "Now the Adjudicator Agent re-evaluates each decision under a declared policy. Where independent valid evidence remains, the batch is reaffirmed.
  > 
  > Here, five batches that touched the suspect window had independent corroborating tests. Adjudicator halts taint propagation and marks these batches reaffirmed, protecting clean inventory from unnecessary recall."

---

### Beat 5: Quarantine Hold & Why Drawer Provenance (1:55 – 2:25)
- **Visual:** The Dispatcher Agent places holds on compromised batches. Red `HOLD` stamps appear on 7 units. Operator clicks an Action node; the **Why Drawer** slides out from the right showing the full causal trajectory.
- **Action:** Click on a quarantine Action node (`act-hold-...`). Show the causal path breadcrumb in the Why Drawer (`sensorlog -> qualitydecision -> batchlot`).
- **Spoken Narration (1:55 – 2:25):**
  > "For batches lacking independent support, the Dispatcher Agent evaluates parameterized Cypher gates and places quarantine holds on the seven affected units.
  > 
  > Clicking any hold opens the Why Drawer. Every action stores the exact graph path that caused it, allowing quality teams to verify the chain of custody from the faulty sensor to the quarantined batch."

---

### Beat 6: Customer Notice & Human Sign-off (2:25 – 2:45)
- **Visual:** An outbound shipment was delivered to a customer. An advisory notice action appears under `Pending Approval`. Operator clicks **"Approve Notice"**.
- **Action:** Click the green **"Approve Notice"** button in the pending queue. Notice changes status to approved; badge updates.
- **Spoken Narration (2:25 – 2:45):**
  > "For downstream shipments, Dispatcher drafts customer advisory notices only for recipients who received a held batch.
  > 
  > Sensitive customer communications require human oversight. The operator reviews the drafted text and approves the notice, recording the human sign-off into FalkorDB."

---

### Beat 7: Cypher Query Log & Closing (2:45 – 3:00)
- **Visual:** Press `L` or click **"Cypher Log"** in the footer to reveal the live FalkorDB query stream.
- **Action:** Scroll through the query log showing `MATCH`, `MERGE`, and gate evaluations. (Do not read out timing numbers).
- **Spoken Narration (2:45 – 3:00):**
  > "Pressing 'L' reveals our raw FalkorDB query log: every trace, gate evaluation, and episodic outcome runs directly on the graph.
  > 
  > On 100 generated incidents, under a declared blanket-recall rule, Tainted held a mean of 32.5% of the batches a blanket recall would, with no false reaffirmations against generated ground truth. Tainted demonstrates how graph-connected data turns crisis response into verifiable forensic precision."
