# Contract Changes Log

Contracts are drafted in Hour 0 to 3 by all three members (Parts A, B, and C).
After Hour 3, contracts are frozen and change only through an approved change note here.

## Initial Contracts (Hour 0-3 Draft)
- `contracts/ontology.py`: Generic roles, node kinds, edge roles, and ontology declaration schemas.
- `contracts/query_api.py`: Typed Query API protocol (trace, support, siblings, exposure, explain, evaluate_gate, algo_shortest_path, algo_centrality, algo_components).
- `contracts/events.py`: SSE event contract and envelope schema with no domain words in event types.
- `contracts/registry.py`: Statuses, vocabulary, and node presentation schemas.
- `contracts/gates.py`: Tool gate definitions, Cypher parameterization schemas, and gate evaluation protocol.

## Approved Change Notes

| Date | Contract File | Proposed Change | Motivation | Approved By (A, B, C) | Status |
| --- | --- | --- | --- | --- | --- |
| 2026-10-17 | docs/DESIGN_BRIEF.md | DESIGN_BRIEF.md is superseded for line weight (solid 2-3px borders from one token), shadows (hard offset shadows with zero blur from one token, used only to show interactive or selected), and corners (square corners, border-radius: 0px) only. Everything else stays: paper palette, three signal inks from the status registry, stamps, query log, Why drawer, banned list. | Adopt minimalist neobrutalism to heighten tactile clarity, forensic authority, and unambiguous interactive state signaling. | Team (A, B, C) | APPROVED |

