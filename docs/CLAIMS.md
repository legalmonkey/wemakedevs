# Tainted — Verified Claims & Empirical Metrics

This document formalizes all empirical claims for the **Tainted** forensic recall tracer. Every claim herein is backed by automated tests, Cypher graph query verification, and reproducible benchmarks recorded in `docs/AUDIT.md`.

---

## 1. Scope & Methodology

Tainted models food supply chains and manufacturing batch topologies as a directed property graph in **FalkorDB**. Contamination propagation, evidence evaluation, and recall containment are executed by multi-agent workflows bounded by parameterized Cypher tool gates.

Decisions are classified into four mutually exclusive states:
- **Held**: Units on verified contamination trajectories or suspect paths awaiting adjudication.
- **Reaffirmed**: Units cleared of contamination via verified independent testing meeting policy thresholds.
- **Escalated**: Units with ambiguous or unverifiable chain of custody escalated for human review.
- **Unaffected**: Units outside the exposure perimeter.

---

## 2. 100-Seed Benchmark Results

Across a 100-seed benchmark executed against live FalkorDB (`tests/audit/test_demand2_100_seed_benchmark.py`), Tainted demonstrated the following metrics:

| Metric | Measured Value | Benchmark Description |
| :--- | :--- | :--- |
| **Share Recalled (Mean)** | **32.47%** | Mean fraction of units identified for hold/recall within the naive exposure scope (Min: 21.43%, Max: 45.00%). |
| **Safe Release Rate (Mean)** | **12.16%** | Mean fraction of units safely reaffirmed through verified independent multi-lab evidence. |
| **False Reaffirmations** | **0** | Zero units reaffirmed when contamination was physically present on the graph trajectory. |
| **Lateral Link Recall** | **100.0%** | Injected multi-hop cross-contamination hops through shared lots were identified across 100/100 seeds. |
| **Explanation Coverage** | **100.0%** | 100% of generated actions and decisions possess a verified stored causal trajectory (`causal_path`). |

---

## 3. Real Crash Safety & Invariance

Crash safety was tested under ungraceful operating system process kills (`os.kill` / `proc.kill`) during active graph state transitions (`tests/audit/test_demand1_crash_safety.py`):

1. **Hash Invariance**: 100% bit-for-bit SHA-256 hash invariance between uninterrupted graph state and post-recovery graph state across both single and dual process crash injections.
2. **Action Idempotency**: Zero duplicate actions created across recovery runs.
3. **Concurrency Isolation**: Zero race conflicts or deadlocks detected under concurrent agent execution.

---

## 4. Cypher Tool Gate Governance

In accordance with Section 0 Rule 5:
- **LLMs Never Decide Privileged Actions**: Tools modifying entity status (`quarantine_hold`, `release_unit`, `dispatch_notice`) are guarded by parameterized Cypher queries executed directly in FalkorDB.
- **Zero Gate Bypasses**: Automated tests verify that tools are strictly inaccessible until graph preconditions (such as independent test count $\ge \text{threshold}$) are mathematically satisfied.

---

## 5. Human-in-the-Loop Governance

- **Drafted Notices**: External customer or logistics notifications are generated as drafts and placed in a dedicated review queue.
- **Operator Adjudication**: Dispatched notices require explicit human operator sign-off before transmission.
- **Why Drawer**: Every decision and action can be inspected in $\le 2$ interactions, displaying the complete forensic chain-of-custody path with step-by-step entity and role details.

---

## 6. Explicit Boundaries & Limitations

To maintain absolute scientific and engineering honesty:
- **Model Boundaries**: Tainted traces contamination across known, modeled graph relationships. Unmodeled external variables or unrecorded batch movements fall outside graph reach.
- **No Regulatory Endorsement**: Tainted is an algorithmic decision-support tool. It does not replace statutory recall protocols or human safety officers.
- **No Absolute Probabilistic Absolutes**: Contamination paths reflect graph reachability and recorded test evidence; no statistical claims of total real-world certainty are made.
