# Inter-Part Requests and Dependency Log

## Request from Part A to Part B (Phase A3)
- **Target File**: `agents/stub_client.py` (line 236)
- **Detail**: In `StubGraphClient.support`, update `if is_valid and group_id:` to `if is_valid and not is_unverifiable and group_id:`.
- **Rationale**: An evidence marked `unverifiable=True` represents a missing link / unknown state per Rule 6 and must not be counted as a valid independent support group when evaluating policy gates.
- **Status**: Implemented & Approved.

## Part C Requests & Dependencies
This section tracks cross-part change requests and dependencies as mandated by Rule 1 and Rule 12.

| Date | Requesting Part | Target Part | Request Description | Status | Decision / Note |
| --- | --- | --- | --- | --- | --- |
| 2026-10-15 | Part C | Part A/B | Verify Event and Registry contracts | Approved | Synchronized in `contracts/` |
