# Web Evidence Partial State and Full QA Convergence

Date: 2026-07-18 (Asia/Shanghai)

Scope: truthful cross-layer projection when verified Web Evidence survives a
later research-stage failure, official structured-output repair exhaustion, and
current-worktree full local verification.

Verdict: `GREEN` for the implemented local contracts and static gates. V2
remains `PARTIAL`; `Production Ready: NO`.

## Reproduced Data Path

The failure is a valid ordered state, not cross-Run database corruption:

1. OKX retries can exhaust.
2. The Web Search market fallback can succeed and put a verified
   `market_snapshot` Evidence item in Graph state.
3. The independent `research_events` search can fail afterward.
4. The Graph terminates as failed while preserving the earlier Evidence.
5. Dispatcher persists both the Run failure payload and Evidence for the same
   Task/Run.
6. Product API reads the same selected/latest Run for errors and Evidence.

The partial output is intentional and auditable. Clearing the Evidence would
hide valid provider output and was rejected as a fix.

## Retained RED

- Graph `research_unavailable` omitted its stage identifier.
- `_public_error()` always returned `检索服务没有返回可验证来源`, even when the
  same terminal payload contained Evidence.
- Frontend `toResearch()` gave the error code precedence over Evidence count.
- The page header therefore said `检索不可用` while rendering a verified source
  card below it, and the failure panel repeated that no source existed.
- Official `ToolStrategy(handle_errors=...)` repair is bounded by
  `ModelCallLimitMiddleware(run_limit=3)`. After three invalid model calls the
  official middleware raises `ModelCallLimitExceededError`; the Graph initially
  reported this structured-output exhaustion as generic `model_unavailable`.
- Full QA additionally retained a stale `langgraph-api 0.11.0` dev dependency
  contract, a stale inline stream-eligibility structure assertion and two
  Docker Compose harness failures caused by removing the CLI plugin's `HOME`.

None of these failures was skipped or accepted as green.

## Implementation

- Graph research failures include the safe endpoint `research_events`.
- Verified Evidence is preserved across the later failure.
- Product API derives public research-failure text from the same terminal
  payload's Evidence count. With Evidence it says the research stage did not
  finish and names how many verified sources were retained.
- Frontend research state now distinguishes `partial` from `available` and
  `unavailable`. The partial badge uses the existing amber warning palette and
  reads `已保留 N 条来源，研究未完成`.
- The failure panel remains visible and non-actionable Evidence remains fully
  inspectable; the fix does not convert a failed Run into success.
- Bounded structured-output repair exhaustion maps to non-retryable
  `model_invalid_output`. Direct factory tests assert the official exception and
  exact `3/3` run budget rather than pretending it is a final validation error.
- Dev Runtime dependency contracts now match `langgraph-api 0.11.1`; production
  image contracts remain independently pinned to the existing 0.11.0 base.
- Historical stream structure tests now verify the exported pure eligibility
  rule, including historical, terminal and cancel-requested exclusions.

## Fresh Verification

| Gate | Result | Boundary |
|---|---:|---|
| Backend focused Graph/API/failure contracts | `151 passed` | typed partial failure and official repair classification |
| Backend complete hermetic | `840 passed, 164 skipped, 1 warning` | local non-real suite; skips remain unproved |
| PostgreSQL 16 migration | `0001 -> 0018` passed | fresh isolated temporary database |
| PostgreSQL complete integration | `191 passed, 0 skipped` | Product persistence/worker/integration baseline |
| Frontend unit | `366 passed / 30 files` | view-model and rendered partial-state content |
| Frontend typecheck / full ESLint | passed | current source |
| Frontend production build | passed | isolated copy; 14 routes generated |
| Root complete suite | `1184 passed` | structure, deployment, migration and compatibility |
| Playwright discovery contract | `29 passed` | `--list` only; no browser body |
| Playwright profile listing | `78 instances / 11 profiles` | discovered, not executed |
| Ruff check / format | passed; `179 files already formatted` | backend source and tests |

The initial full root run preserved four failures. Updating the two stale
contracts fixed real drift. The two Compose failures disappeared when the empty
test environment retained only the user's `HOME` so Docker could find its CLI
plugin; Compose itself continued with env-file loading disabled and placeholder
values. The corrected full root suite then passed.

## Open Gates

- The new partial-state scenario has Graph, Product public-error and frontend
  render contracts, but no dedicated real Playwright body or screenshot yet.
- The current real Agent Server remains the official in-memory development
  Runtime and has not proved restart durability.
- Approved built-in Search/Tavily, hosted egress and seven real provider/model
  tests remain unverified.
- Hosted OIDC/HTTPS, real LangSmith/Langfuse correlation, notification receipts,
  DR/HA/SLO, signed SBOM and release attestation remain open.
- The model's free-text `unavailable_data` still needs a later typed capability
  code design; prompt text alone is not accepted as a deterministic guarantee.

No commit, stage or push was performed.
