# Tainted — Simple 3-Minute Video Demo Script

A simple, conversational, step-by-step walkthrough for your 3-minute recording. No complex jargon—just a clear story of how Tainted works and why it wins.

---

## What to Do Before Hitting Record
1. Open `http://localhost:3000/` in your browser (1440 × 900 or full screen).
2. Click **`None`** (`#btn-seed-none`) in the top bar so the canvas is in clean standby mode.
3. Keep this cheat sheet next to you on your phone or second monitor!

---

## The 5 Simple Clicks & What to Say (3:00 Total)

```
0:00 ─── [1. Show Screen] The Problem (Food Recall Chaos)
0:35 ─── [2. Click "Investigate Recall"] The 4 AI Agents & Lateral Traversal
1:15 ─── [3. Click "Reaffirmed"] Sparing Safe Food (The Reaffirmation Beat)
1:50 ─── [4. Click "Held" + Batch] The Why Drawer (Verifiable Proof)
2:25 ─── [5. Click "Needs a Person" + "Approve"] Human in the Loop & Results
3:00 ─── Finished!
```

---

### Step 1: The Problem (0:00 – 0:35)
* **What to do on screen**: 
  - Point your mouse at the screen. You're on `http://localhost:3000/`. The canvas says *"Evidence Graph Awaiting Incident Signal"* and all metric counters show **0**.
* **What to say**:
  > "Imagine you run a food manufacturing plant. Suddenly, a pasteurizer temperature sensor drifts, or a supplier calls with a contamination alert.
  > 
  > What happens today? Pure chaos. Quality teams spend days digging through messy spreadsheets. Usually, they end up doing a massive blanket recall—throwing away millions of dollars of perfectly safe food—or worse, they miss a cross-contaminated batch that already reached grocery shelves.
  > 
  > We built **Tainted** to solve this. Tainted is an autonomous forensic platform powered by **FalkorDB** that models your entire supply chain as a live property graph to isolate contamination with surgical precision."

---

### Step 2: Triggering the Incident & The AI Agents (0:35 – 1:15)
* **What to do on screen**: 
  - Click **`Seed 101`** in the top bar.
  - Click the big black button: **`INVESTIGATE RECALL`**.
  - Watch the live stream light up and the graph populate. Point your mouse at the dashed link connecting the two lines.
* **What to say**:
  > "Let's see it in action. We select Seed 101 and click **Investigate Recall**.
  > 
  > Behind the scenes, four autonomous agents immediately coordinate over FalkorDB:
  > First, our **Sentinel Agent** catches the retracted sensor reading.
  > Next, our **Tracer Agent** follows the contamination downstream—from raw ingredients, through processing decisions, to packaged products.
  > 
  > Look at this dashed link right here: Tracer uncovered **lateral cross-contamination**. Two completely separate product lines shared the same blending tank during the incident window. Traditional relational databases and ERPs miss these sideways dependencies all the time."

---

### Step 3: Sparing Safe Food (1:15 – 1:50)
* **What to do on screen**: 
  - Click the green **`REAFFIRMED (5)`** filter chip above the canvas.
  - Click on one of the green batches on the canvas.
* **What to say**:
  > "Now, here is what makes Tainted truly special: it doesn't panic and recall everything.
  > 
  > Our **Adjudicator Agent** re-evaluates every decision against safety policies. If an affected batch had independent corroborating lab tests that proved it was clean, Tainted stamps it **green**—marked **Reaffirmed**.
  > 
  > These five batches touched the suspicious window, but they are completely safe. Tainted clears them immediately, protecting safe inventory and preventing wasteful factory halts."

---

### Step 4: Quarantine Holds & The "Why Drawer" (1:50 – 2:25)
* **What to do on screen**: 
  - Click the red **`HELD (7)`** filter chip.
  - Click directly on batch **`lot-batch-301`** (or its action node).
  - The **Why Drawer** slides open from the right side! Show the breadcrumb path.
* **What to say**:
  > "For batches that genuinely lack safe evidence, our **Dispatcher Agent** issues quarantine holds on the seven compromised units.
  > 
  > But when an auditor or plant manager asks: *'Why did you hold this batch?'*, they don't get a vague AI guess. 
  > 
  > In just one click, the **Why Drawer** slides open. It reveals the exact, tamper-evident chain of custody: from the drifting sensor, through the release decision, directly to this batch—complete with the raw FalkorDB Cypher query proving the verdict. Total audit transparency in under two clicks."

---

### Step 5: Human Sign-Off & Benchmark Results (2:25 – 3:00)
* **What to do on screen**: 
  - Click the **`Needs a Person`** queue tab at the top.
  - Click the green **`Approve Notice`** button.
  - Click the **`Evaluation`** tab.
* **What to say**:
  > "Finally, when it comes to notifying customers, we never let an AI send notices unmonitored. 
  > 
  > Under our **Needs a Person** queue, Dispatcher drafts the recall notice specifically for affected customers, but waits for human approval. I click **Approve Notice**, and the sign-off is permanently committed to the graph.
  > 
  > Across 100 simulated benchmark incidents under declared blanket-recall rules, Tainted contained recalls to an average of just 32.5% of what a blunt blanket recall would take—saving over two-thirds of safe inventory, with zero false clearances.
  > 
  > That is Tainted: autonomous multi-agent precision, powered by FalkorDB."

---

## Quick Practice Tips
- **Speak naturally**: Don't memorize word-for-word; just follow the 5 story beats.
- **Pacing**: Don't rush. 3 minutes is plenty of time for these 5 simple clicks.
- **Don't read numbers from the footer**: Keep eyes on the graph, the green reaffirmations, and the Why Drawer!
