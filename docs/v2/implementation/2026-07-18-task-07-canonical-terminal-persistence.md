# Task 7 Canonical Terminal Persistence Record

Date: 2026-07-18 Asia/Shanghai
Phase: Task 7 / Product terminal consistency and failure projection
Status: local canonical terminal persistence complete; hosted durability open

## Objective

Every Product Run that reaches a terminal state must atomically own a canonical
terminal output, its SHA-256 hash and one `run.terminal` Domain Event. This also
applies to Product-side failures that occur before or around the official Agent
Server boundary. A terminal Task/Run without this canonical record cannot be
replayed, audited or repaired deterministically.

## Retained RED Evidence

The audit found terminal branches that only changed Task/Run status and failure
columns. Invalid persisted commands, confirmed and permanently failed cancel,
expired submit uncertainty, resume/fork exhaustion, generic Agent Server
exhaustion, terminal database fallback and terminal hash conflict could all
finish without a matching canonical output/hash/event.

Five Product terminal-output contract tests first failed because a failed
payload could omit a structured error, error diagnostics were unbounded and
unknown raw fields could cross the Product API. Four representative dispatcher
integration assertions also failed before the canonical helper was applied.
No failing assertion was removed or converted into a skip.

## Implementation

- `CommandDispatcher._persist_terminal_run` atomically updates the Product
  Task/Run terminal state, completion timestamps, canonical output payload,
  projection fence, terminal output hash and `run.terminal` Domain Event.
- `_persist_failed_terminal_run` constructs the same canonical record for
  Product-owned failures. Invalid commands, submit uncertainty, cancel,
  resume/fork and generic official Runtime exhaustion now use this path.
- Same-hash replay verifies the persisted payload hash and repairs a missing
  terminal Domain Event in the same Product transaction.
- A terminal projection conflict now replaces the stale success projection
  with a canonical `failed/terminal_projection_conflict` output and hash. It no
  longer leaves a failed Run attached to the old successful output.
- `observed_terminal_status` remains an official Runtime observation. Local
  Product-only failures do not fabricate an Agent Server observation.
- Failed terminal output requires at least one structured error. Error codes
  are bounded ASCII snake case; known diagnostics are typed and bounded;
  unknown raw response or authorization fields are discarded.
- The Work surface accepts a same-Task authoritative correction from an older
  terminal state to `failed/terminal_projection_conflict` while retaining the
  existing stale nonterminal and unrelated terminal fencing rules.
- Terminal Product Tasks now enter a separate bounded revalidation window. It
  reads at 5/15/30/60-second intervals, allows one request in flight, pauses
  while the page is hidden, sends at most one overdue read when visibility
  returns and stops on correction, Task/Run change, unmount or budget expiry.
  Task ID, selected Run ID and active-effect checks reject late responses.

## Verification

```text
Product terminal contract RED:                 5 failed
representative dispatcher RED:                 4 failed
real PostgreSQL dispatcher current worktree:  71 passed
backend hermetic current worktree:            820 passed, 163 skipped, 1 warning
backend Ruff:                                  passed
formal docs current-state gate:               18 passed
frontend terminal projection focused:         29 passed
frontend terminal revalidation RED:           3 failed, 320 passed
frontend terminal/error-copy current focus:   62 passed
frontend full verification before final UI
copy/stage-history follow-up:                  29 files / 320 tests, typecheck,
                                               lint and production build passed
```

The real PostgreSQL run used the local Product database at migration `0018`.
The hermetic skips remain explicit real-database/provider/model gates and are
not counted as acceptance.

## Real Browser Observation

A retained local real Product Task failed with `model_invalid_output` after
persisting an exchange-native market snapshot and four Web Evidence rows. It
had no success Artifact, which is the required fail-closed behavior.

- Desktop `1280x720`: failure diagnosis, market context and four sources were
  visible; there was no raw JSON or `<pre>`, no horizontal overflow and no
  console warning/error.
- Pixel 7 `412x915`: the collapsed and expanded failure diagnosis rendered the
  error code, structured-output error type and Product correlation ID. The
  source summary toggle worked, long titles/URLs wrapped, and DOM scanning found
  zero horizontal overflow and zero clipped text nodes.
- The only 1px controls reported by the broad size scan were intentionally
  hidden radio inputs, not visible click targets.

This was a live local browser and Product database observation, not a stored
visual-regression baseline, real device test or hosted acceptance.

## Evidence Boundary

This closes the known local paths that could terminalize without a canonical
Product output/hash/event and adds bounded Product revalidation capable of
receiving a later terminal correction without a manual reload. Its controller
has unit/type/static evidence; the dedicated browser fault-injection proof is
still open. It does not prove that a licensed persistent Agent Server preserves
checkpoints and stream history across process/database restart. Product stage
history is not yet exposed to the frontend. Hosted OIDC/HTTPS, production
database failover, formal SLOs and release attestation remain open. V2 remains
`PARTIAL`; `Production Ready: NO`. No commit or push was performed.
