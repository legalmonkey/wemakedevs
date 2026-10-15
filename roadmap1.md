# Tainted: Antigravity Build Roadmap

Team build plan for the Agent Context-Layer Hackathon, FalkorDB track. Give this whole file to Antigravity as the first instruction in every session.

## 0. How Antigravity must use this document

You are a coding agent working inside a three-person team. Each person owns one Part (A, B or C). Read sections 1 to 4 fully, then work ONLY on the Part you are assigned.

**Strict rules. Violating any of them is a failure, not a style issue.**

1. **Stay in your lane.** Edit only the directories your Part owns (section 5). Never modify another Part's files. If you need a change there, write it to `docs/REQUESTS.md` and stop on that item.
2. **Contracts are frozen after Hour 3.** Files in `contracts/` change only through a change note in `docs/CONTRACT_CHANGES.md` approved by all three members. Never edit them silently.
3. **Zero hardcoding.** No batch ids, instrument names, customer names, thresholds, status names, status colours, tool names or domain Cypher values in code. Code handles kinds; `config/` and `packs/` supply instances. Colours exist only in the token file served from the status registry.
4. **The graph is the only shared state.** Agents never call each other. They write nodes and edges; others react to graph state.
5. **The LLM never issues a verdict.** Verdicts come only from declared policy evaluated in Cypher. The model chooses among tools offered to it and drafts text. It never sees a tool the gate has not unlocked.
6. **Unknown is a first-class outcome.** A missing link yields `unverifiable` plus a specific human question. Never guess, never default to safe.
7. **Every action has a stored path.** Every hold, release, notice and escalation must be retrievable with its causal path from the graph. Never generate the explanation afterwards.
8. **No mock data in production paths.** Fixtures live only under `fixtures/` and `tests/`. No placeholder copy, no lorem text, no fake numbers in the UI.
9. **Never invent facts.** Do not make up FalkorDB features, library APIs or dataset fields. Check the docs in the repo or ask. If unsure, write the question to `docs/BLOCKERS.md` and continue with the next unblocked task.
10. **Exit checks gate progress.** At the end of each phase, run the listed exit check, paste the result into `docs/PROGRESS.md`, and stop for human review. Do not start the next phase until a human writes `APPROVED` under that phase.
11. **Run lint and tests before every commit.** Commits are small, one concern each, message format `part-X: phase-N: what changed`.
12. **Do not add dependencies** beyond section 3 without a note in `docs/REQUESTS.md`.
13. **Report honestly.** If a check fails, say so with the output. Never mark a task done on a failing or skipped check.

## 1. The project in brief

When a trusted fact is retracted (an instrument drifted, a supplier issued an alert), Tainted traces every decision, batch, shipment and customer that rested on it, then re-judges each decision. It holds what truly lost support, reaffirms what still stands, flags what cannot be verified, and shows the exact graph path behind every action.

The memorable moment is the demo beat where red spreads through the graph and then parts of it turn green again, because the system can prove those decisions still have independent support.

## 2. Winning criteria and how the build proves each one

Nothing can guarantee a win. The way to maximise the chance is to meet every item below with a visible, testable proof. Treat each row as an acceptance requirement.

| Judging expectation (from the brief) | Proof we must ship | Owner |
| --- | --- | --- |
| Graph shapes what the agent does, not beside it | Tool gates evaluated in Cypher; a hold on an untainted batch is impossible because the tool is absent | B |
| Multi-hop reasoning | Trace of unknown depth from retracted fact to customer, plus lateral hops | A |
| Graph algorithms as agent tools | At least two algorithm tools (shortest path for the Why path; centrality or connected components for chokepoint lots and incident clusters) exposed over MCP | A + B |
| Tool selection through MCP | FastMCP server; tool list visibly changes with graph state | B |
| Explainable results | Why drawer shows a stored chain-of-custody path for every action | A + C |
| Remembers what it learns | Episodes, procedures ranked by recorded outcomes, minimum-evidence rule stated honestly | B |
| Shared state and per-tenant memory | One FalkorDB graph per tenant; agents coordinate only via edges; concurrent tenant run | A + B |
| Works, not mockware | Live SSE from real graph state; fresh seed every run | C |
| Measured, not narrated | Evaluation report: precision vs blanket recall over N random incidents, false-reaffirm count 0 | A |
| Distinctive presentation | Evidence-board UI that passes the banned-list review | C |

**Lead track:** Track 1 (Agents That Act on Connected Data). Memory and coordination are the second act. Do not claim full Track 2 coverage; claim episodic and procedural memory only.

## 3. Stack and repository layout

- FalkorDB in Docker; Python 3.11+; FastMCP for the tool server; FastAPI with Server-Sent Events; Next.js for the UI; any tool-calling LLM behind one adapter interface.
- Config as YAML validated by JSON Schema.

```
contracts/        FROZEN interfaces (all parts read, nobody edits alone)
config/           ontology, gates, status, tenants (A owns schema, all edit instances via PR)
packs/food/       ontology, policies, vocabulary (A)
scenarios/        fault-injection files (A)
engine/           graph client, query builder, generator, injector, evaluation (A)
agents/           sentinel, tracer, adjudicator, dispatcher, event loop, memory (B)
toolserver/       MCP server, gate evaluator, algorithm tools (B)
api/              FastAPI, SSE, registry endpoint (C)
ui/               Next.js evidence board (C)
tests/            per-part subfolders
fixtures/         generated data only
docs/             PROGRESS.md, BLOCKERS.md, REQUESTS.md, CONTRACT_CHANGES.md
```

## 4. The frozen contracts (written by all three together in Hours 0 to 3)

These live in `contracts/` and are the only coupling between Parts. Write them as JSON Schema or Python protocols, with kinds only, never domain values.

1. **Ontology contract.** Node kinds and edge kinds are declared in `config/ontology.yaml`. Required generic roles: `Evidence`, `Decision`, `Unit` (what ships), `Shipment`, `Recipient`, `Event`, `Action`, `Episode`, `Procedure`. Required edge roles: support, derives-from, ships-in, delivered-to, lateral link (declared in config), `TAINTS` with properties `hops` and `via_path`, and outcome edges from `Episode`.
2. **Query API contract (A to B and C).** Python functions that return typed results: `trace(event)`, `support(decision)`, `siblings(unit)`, `exposure(unit)`, `explain(action)`, `evaluate_gate(tool, params)`, `algo_shortest_path(a, b)`, `algo_centrality(scope)`, `algo_components(scope)`. Every call returns the rendered query text and result size so the UI can show it in the query log.
3. **Event contract (B to C).** SSE event types: `event.received`, `evidence.suspect`, `taint.added`, `verdict.set`, `action.created`, `episode.closed`, `query.run`, `agent.status`. Each carries tenant id, timestamp and entity ids. No domain words in event type names.
4. **Registry contract (A and C).** `/api/registry` returns statuses (id, label, stamp text, ink token), vocabulary, and node presentation derived from the ontology. The UI must render a newly added status with no frontend change.
5. **Tool gate contract (A and B).** Gate expressions in `config/gates.yaml`, each a parameterised Cypher returning a boolean. Tool names come from this file, never from code.

**Decision recorded now: verdict order.** The original policy escalated whenever any unverifiable evidence existed, even when ample independent support remained. Replace with: reaffirm if independent valid groups are at least the minimum; otherwise escalate if any unverifiable evidence exists; otherwise taint. This avoids over-escalation and protects the reaffirmation demo beat.

## 5. Division of work

### PART A: Graph, data and proof (Member 1)

**Owns:** `engine/`, `config/` schemas, `packs/`, `scenarios/`, `contracts/` drafting, evaluation.

**Mission:** Make the graph correct, realistic and measurable. Everyone else depends on this Part, so it must ship the Query API early.

**Phases**

| Phase | Hours | Deliverable | Exit check |
| --- | --- | --- | --- |
| A0 | 0 to 3 | Repo, FalkorDB in Docker, config loader with JSON Schema, lint for id-shaped literals and raw hex colours. Prototype one gate query and one variable-depth trace with `via_path` on real FalkorDB to expose dialect limits early. | Invalid config is rejected with a clear message; prototype queries run |
| A1 | 3 to 8 | Food pack ontology, seeded generator (suppliers, lots, batches, tests, shipments, customers), declarative fault injector, scenario files | Two seeds yield different graphs; scenario expectations hold |
| A2 | 8 to 13 | Query builder generated from ontology and policy; all Query API functions; algorithm functions (shortest path, centrality, components) | Tests pass on the food pack and a tiny second pack |
| A3 | 13 to 24 | Golden-file tests for templates; property test: a decision is never reaffirmed while policy-required independent support is absent; support for B's integration | Property test passes on random graphs |
| A4 | 24 to 31 | Evaluation harness: N randomised incidents; metrics below; JSON report for C to display | Report generated end to end |
| A5 | 31 to 36 | Fresh-seed rehearsal data, bug fixes only | Three clean seeds |

**Metrics to produce:** precision versus naive recall (tainted batches over batches a naive recall would hit), safe-release rate, false-reaffirm count (must be 0 on generated ground truth), hidden-link recall (target 100 percent), time to scope, explanation coverage (target 100 percent).

**Part A rules:** scenario `expect` blocks are read only by tests, never by agents. The generator picks fault targets randomly from eligible nodes; no fixed ids. Public recall patterns (for example openFDA enforcement reports) may anchor hazard vocabulary and scope distributions; verify availability at build time and say so honestly.

### PART B: Agents, tool server and memory (Member 2)

**Owns:** `agents/`, `toolserver/`, procedural memory logic.

**Mission:** Make the system genuinely agentic while keeping every verdict policy-derived.

**Phases**

| Phase | Hours | Deliverable | Exit check |
| --- | --- | --- | --- |
| B0 | 0 to 3 | Agent base class, event loop skeleton that polls graph queries (no agent-to-agent calls), LLM adapter interface, contract drafting with A and C | Loop runs against a stub graph client built from the contract |
| B1 | 3 to 13 | Sentinel and Tracer against the Query API as it lands; write `Event` and `TAINTS` edges | Trace writes hops and via-path for a generated incident |
| B2 | 13 to 18 | MCP server with gate evaluator; tool list is computed per decision from graph state; algorithm tools registered | A hold on an untainted batch is refused because the tool is absent |
| B3 | 18 to 24 | Adjudicator (policy only, no LLM verdict) and Dispatcher; Action nodes; draft notice requires human approval | Kill and restart any agent mid-incident; final graph state is identical |
| B4 | 24 to 31 | Episodes and procedure ranking from outcome edges with the minimum-evidence threshold from policy; one real LLM judgement task (see below); concurrent two-tenant run | Below threshold the system says so and asks a human instead of claiming it learned |
| B5 | 31 to 36 | Hardening, restart tests, timing | Three clean runs on different seeds |

**LLM judgement task (required):** when the Adjudicator returns `unverifiable`, the model drafts a specific question for a human naming the missing link, using only graph facts passed to it. Optionally it ranks permitted procedures for the Dispatcher. It never sets status.

**Part B rules:** agents are idempotent and restart-safe because their work queue is a query. Describe memory in all text as ranked by stored outcomes, never as training or learning of the model. Gates are evaluated before the tool list is built, every time.

### PART C: API, interface and demo (Member 3)

**Owns:** `api/`, `ui/`, demo script, pitch.

**Mission:** Make the proof visible. The interface must read as a forensic instrument or printed case file, not a SaaS template.

**Phases**

| Phase | Hours | Deliverable | Exit check |
| --- | --- | --- | --- |
| C0 | 0 to 3 | Design brief, token file, contract drafting with A and B, Next.js and FastAPI skeleton | Brief and banned list committed |
| C1 | 3 to 13 | `/api/registry`, SSE stream of the event contract, UI shell on the baseline grid, ledger column, query log column | UI renders from the registry with a replayed recording of real events |
| C2 | 13 to 24 | Graph canvas: ship a styled force layout first; ledger-tag nodes, dashed `TAINTS` edges, weight by support | Canvas shows a live incident from real agents |
| C3 | 24 to 31 | Stamps (carrying real state), hop-by-hop propagation with a hold between hops, quiet reaffirmation draw-back, Why drawer chain-of-custody strip, tenant index tab, evaluation panel | Banned-list review passes against screenshots |
| C4 | 31 to 36 | Timed demo runs, pitch, fallback recording | Three clean 3-minute runs on fresh seeds |

**Design brief (non-negotiable):** warm paper background, near-black ink, three signal inks only (tainted, reaffirmed, suspect) read from the registry; serif display face, mono for ids, queries and timestamps, restrained grotesque for body; asymmetric columns, hairline rules, no shadows, no blur; graph about 60 percent width with a running ledger beside it; no spring easing, no confetti.

**Banned list:** purple-to-blue gradients, glassmorphism, centred hero with two buttons, three-up icon cards, rounded-xl everywhere, emoji as icons, generic stat tiles with sparklines, default component-library look, placeholder copy.

**Part C rules:** all domain wording comes from the pack vocabulary; all colours from the token file; a mock-data path must not exist in production code. Replace the canvas renderer with a custom layer only if C3 has slack.

## 6. Integration milestones (whole team)

| Hour | Milestone | Pass condition |
| --- | --- | --- |
| 3 | Contract freeze | All five contracts committed and acknowledged by A, B and C |
| 13 | Integration 1 | B's Tracer runs against A's real Query API on a generated graph |
| 24 | Integration 2 | Full incident end to end: event to SSE to canvas, with real gates |
| 31 | Feature freeze | Only bug fixes after this point |
| 34 | Dress rehearsal | Three fresh-seed runs, each under three minutes |

## 7. Cut order if time runs short

**Never cut:** gating, reaffirmation, the Why path, the config contract, the evaluation report, at least two algorithm tools.

**Cut in this order:** tenant-switch animation; second-incident replay polish; procedure memory UI (keep the stored stats and the honest statement); custom canvas rendering; second-ontology portability test (run it last if time allows).

## 8. Three-minute demo script (Part C drives, all rehearse)

| Time | Beat |
| --- | --- |
| 0:00 | Calm paper canvas; everything shipped on trust in a sensor reading |
| 0:20 | Calibration alert arrives; Sentinel ledger entry; affected results turn ochre |
| 0:40 | Tracer advances hop by hop; each Cypher call prints in the query log |
| 1:20 | Stamps flip to REAFFIRMED where independent support remains; naive-versus-Tainted counter |
| 1:50 | Hidden lateral link stamps a batch of another product through a shared lot |
| 2:20 | Holds placed; notices drafted for exposed customers only; a human approves one |
| 2:40 | Why drawer: chain-of-custody strip lights the full stored path |

Always run on a fresh seed. An unplanned batch appearing as the hidden link is the best proof that nothing is hardcoded.

## 9. Definition of done (every box needs evidence in `docs/PROGRESS.md`)

- [ ] Repo search for batch, instrument or customer ids returns zero matches outside generated fixtures
- [ ] Changing `min_independent` in config changes verdicts with no code edit
- [ ] Swapping the second ontology leaves engine tests passing
- [ ] A new status added to the registry appears in the UI with no frontend change
- [ ] Killing an agent mid-incident leaves the final graph state identical
- [ ] A hold on an untainted batch via the tool server is refused because the tool is absent
- [ ] At least two graph-algorithm tools are callable over MCP and used in the demo
- [ ] Evaluation report shows precision versus naive recall and a false-reaffirm count of 0
- [ ] Every action in the demo returns a stored path in the Why drawer
- [ ] Three fresh-seed runs under three minutes, each with one reaffirmation and one lateral link
- [ ] Screenshot review against the banned list is clean
- [ ] Organisers confirmed on required FalkorDB and MCP usage (do this before Hour 0)

## 10. First prompt to paste into Antigravity

> Read `ROADMAP.md` fully. I am Part \[A/B/C\]. Follow section 0 rules strictly. Start at phase \[X0\]. Work only in the directories my Part owns. After each task run the lint and the phase exit check, record the output in `docs/PROGRESS.md`, and stop at the end of the phase for my approval. If anything is unclear or blocked, write it to `docs/BLOCKERS.md` instead of guessing.
