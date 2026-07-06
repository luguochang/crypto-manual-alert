# Checkpoint 7 - Root Cause Budget And Deadline

## Context

`RootCauseSearchSkill` already supported `max_depth` through
`SkillTaskContext` and `max_branch_count` through the skill constructor. The
remaining provider-boundary gap was internal recursion control: a provider could
keep receiving expansion calls until depth/branch limits ended, but the skill did
not expose an explicit expansion budget or deadline to the provider request.

## Changes

- Added `deadline_at` and `remaining_budget` to `RootCauseSearchRequest`.
- Kept those fields out of dataclass equality comparisons so existing request
  assertions remain stable.
- Added `max_expansion_calls` and injectable monotonic `clock` to
  `RootCauseSearchSkill`.
- Recursive expansion now stops when either the deadline expires or expansion
  budget is exhausted.
- The provider receives the same deadline and the remaining expansion budget on
  each request.

## Verification

```powershell
python -m pytest tests/skills/test_root_cause_recursion.py -q
python -m pytest tests/skills tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py -q
```

API smoke:

- trace id: `39e1435ece49462db99a022c685428eb`
- root_cause_search tool calls: 1
- root_cause_search status: `ok`
- root_cause_search freshness: `fresh`

## Remaining Gaps

- `responses_web_search` is still fail-closed for skill provider config until a
  real provider implementation is added with explicit key handling and
  redaction.
- `liquidity_order_book=exchange_native` is still fail-closed and needs a real
  exchange-native adapter.
- Provider stale data handling still needs a focused execution-fact gate test.
