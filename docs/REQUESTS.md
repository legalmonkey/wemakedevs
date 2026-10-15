# Inter-Part Requests and Dependency Log

## Request from Part A to Part B (Phase A3)
- **Target File**: `agents/stub_client.py` (line 236)
- **Detail**: In `StubGraphClient.support`, update `if is_valid and group_id:` to `if is_valid and not is_unverifiable and group_id:`.
- **Rationale**: An evidence marked `unverifiable=True` represents a missing link / unknown state per Rule 6 and must not be counted as a valid independent support group when evaluating policy gates.

