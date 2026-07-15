# M4 Identity, Fork, and Security Evidence

> authority_class: informative
>
> Evidence date: 2026-07-15 (Asia/Shanghai)
>
> This document records the current M4 implementation and its proof boundary. It
> does not replace the normative requirements in `13-v2-final-rebuild-spec.md` or
> `14-v2-final-implementation-plan.md`.

## 1. Verdict

M4 now has a green local Product/Agent/PostgreSQL/browser slice for membership
authority, cross-tenant admission, Agent Store isolation, and checkpoint fork.
It is still `partial`, not `done`, because no real hosted OIDC provider, trusted
HTTPS deployment, multi-principal browser storage states, or licensed durable
Agent Server restart proof exists.

V2 is not production ready. M5 and M6 remain open.

## 2. Implemented Contract

### 2.1 Identity and membership authority

- Auth.js accepts authentication identity only as normalized OIDC
  `issuer + subject`; profile tenant/workspace/role/permission claims are ignored.
- OIDC profile `iss` must exactly match configured `OIDC_ISSUER` after the
  documented normalization or login fails closed.
- Identity-discovery JWTs select no workspace and contain no authority claims.
- Browser workspace selection submits only opaque `context_id`.
- Scoped user JWTs contain `issuer`, `subject`, `identity_issuer`, `context_id`,
  token lifecycle claims, and no tenant/workspace/role/permission authority.
- Product API and Agent Server resolve active membership from Product PostgreSQL
  for every user request. A previously signed token stops working after revoke.
- Provisioning requires a hosted HTTPS identity issuer and persists the exact
  `(tenant, identity_issuer, external_subject)` identity.
- Worker and health-check principals use explicit service token purposes rather
  than browser sessions.

### 2.2 Agent Store boundary

The official `@auth.on.store` handler rewrites every Store namespace to:

```text
tenant/{tenant}/workspace/{workspace}/scope/private/
principal/{issuer-and-subject-derived-principal}/agent-memory/{logical-namespace...}
```

Client-supplied authority components are rejected. Empty list-namespaces calls
remain inside the same private purpose boundary. Two users in one workspace do
not share a Store namespace. The principal is derived from both OIDC issuer and
subject, so equal subjects from different trusted issuers cannot collide; the
raw OIDC subject is not exposed in production Store namespaces.

### 2.3 Durable checkpoint fork

- Product endpoint: `POST /api/v2/tasks/{task_id}/fork`.
- Browser payload requires only owner-scoped `source_run_id`; the browser never
  receives or invents checkpoint coordinates.
- An optional checkpoint supplied by compatibility callers is constant-time
  compared with the Product-owned source Run and rejected on mismatch.
- Admission atomically appends one immutable Product Run and one durable
  `TaskCommand(command_type="fork")` on the same Task and Thread.
- The new Run persists `forked_from_run_id` and
  `forked_from_checkpoint_id`; migration `0009_run_fork_lineage` enforces the
  same tenant/workspace/owner/task source scope, complete lineage, and no self
  reference.
- A pending source pause and its members are atomically cancelled and their
  waiting Product Run is terminalized before fork admission. A responding pause
  with an already accepted human decision rejects fork instead of discarding the
  decision.
- Dispatcher validates Product source/destination lineage, then verifies the
  official checkpoint belongs to the declared source official Run.
- Official creation is exactly `runs.create(..., input=None,
  checkpoint_id=..., durability="sync")`; `checkpoint_id` is a top-level SDK
  argument, never hidden in `config` and never sent as Protocol `state.fork`.
- Timeout handling reconciles by Product Run metadata and refuses a second
  create. A replacement worker uses `find` only.
- Worker loop logs unexpected iteration failures and remains alive; `--once`
  still surfaces the exception to test and operator callers.

## 3. Security Matrix

The real PostgreSQL M4 matrix proves:

- identity context discovery and opaque context selection;
- same-tenant peer and cross-tenant list/detail non-disclosure;
- cross-scope respond, cancel, and fork denial;
- owner fork admission;
- immediate create/respond/cancel/fork denial after membership revoke;
- exact OIDC issuer plus subject provisioning/discovery;
- Store namespace separation for two users in one workspace.

Hosted browser security remains RED until real OIDC storage states exist. The
current `cross-tenant-security.spec.ts` contains no route mocks, but its skip gate
and missing hosted credentials mean it is an executable requirement, not passed
evidence.

## 4. Real Fork Proof

The local real stack used:

- Next production server: `http://127.0.0.1:3001`;
- Product API: `http://127.0.0.1:8124`;
- official LangGraph development Agent Server: `http://127.0.0.1:8123`;
- PostgreSQL Product database and a durable command worker.

Final repeated UI proof used Task
`8477da74-ec98-4375-9a57-d975c33242f8`, source Product Run
`ab2e2c0c-e544-4cdb-bff1-1edcc4474c24`, and eight sequential UI forks. The
independent database check found:

```text
run_count=9, attempts=1-9
fork_run_count=8
official_fork_count=8
pause_statuses=cancelled x8, pending x1
fork_command_statuses=dispatched x8
latest_run=db525b37-4c86-434b-94f0-f339d8d79b60:waiting_human
```

Every browser write went to the same-origin Product BFF. The test rejects direct
browser writes to Agent endpoints and asserts the body is exactly
`{ source_run_id }`.

Desktop Chrome `1440x1000` and Pixel 7 `412x915` both passed:

- real rendered historical Run selection;
- one Product fork write with an idempotency key;
- authoritative switch back to the latest Run;
- polling to the new `waiting_human` state;
- one rendered review panel;
- axe accessibility scan;
- DOM horizontal-overflow and clipped-control scan;
- masked visual baseline generation and a second pixel-regression run.

Visual baselines are stored beside `real-fork-flow.spec.ts` for both projects.

## 5. Failures Found and Fixed

The real stack was intentionally allowed to fail, and the candidate then received
an independent security/recovery review. The following root causes and failure
modes were fixed:

1. Local Next was started without its server-only local token and Product base
   URL, causing Auth.js `NO_SECRET` and BFF `502`. The canonical local start now
   supplies the loopback Product URL and server-only local token.
2. The first official fork reached a new interrupt while the source pause was
   still active, causing `uq_interrupt_pauses_one_active_task` and crashing the
   old worker. Admission now closes pending source lineage atomically, and the
   long-running worker survives and logs unexpected iteration failures.
3. The cancelled source Run originally remained `waiting_human`, producing an
   impossible historical DTO with no active pause; the frontend correctly
   rejected it. Source waiting Runs are now terminalized as cancelled, and the
   historical ForkPanel no longer confuses a cancelled historical Run with a
   cancelled Task.
4. Store principal isolation originally used only OIDC `subject`; equal subjects
   from two trusted issuers could collide. Production Store principals are now
   derived from the full `issuer + subject` identity, and the raw subject is not
   exposed in the namespace.
5. OIDC provisioning and Auth.js originally removed a trailing `/` from issuer
   URLs. Because OIDC issuer matching is exact, both paths now preserve and
   compare the configured issuer byte-for-byte after trimming only CLI
   whitespace.
6. Fork create treated SDK timeouts as indeterminate but not connection resets,
   and a hung create could renew its lease forever. Timeout and connection
   failures now enter find-only reconciliation; the dispatcher enforces a total
   remote-operation deadline and cancels its local task without allowing a
   second create.
7. Migration `0009` originally scoped the source Run foreign key without binding
   the source checkpoint value. The database now has a composite unique target
   and foreign key that require `forked_from_checkpoint_id` to equal the selected
   source Run's `checkpoint_id`; a real PostgreSQL mismatch insertion is rejected.
8. The worker survival test originally stopped on the same failing iteration. It
   now proves the long-running worker logs the first failure and executes a
   successful second iteration.

The in-memory development Agent Server also lost old Threads after backend hot
reload. This is not hidden as a product pass: final proof used a fresh stable
server, while licensed persistent Agent Server restart remains an M6 release
blocker.

## 6. Fresh Gates

| Gate | Result |
|---|---|
| Backend hermetic/local | `516 passed, 107 skipped, 1 warning` |
| Real PostgreSQL integration | `122 passed` |
| Migration `0008 -> 0009 -> 0008 -> 0009` | passed; revision and row counts preserved |
| Frontend unit | `234 passed` |
| Frontend lint, typecheck, production build | passed |
| Real Inbox Desktop + Pixel 7 | `2 passed` |
| Real fork snapshot update Desktop + Pixel 7 | `2 passed` |
| Real fork pixel regression Desktop + Pixel 7 | `2 passed` |

The 107 backend skips remain unproved external/provider/runtime gates. They are
not counted as passes.

## 7. Remaining M4 Checklist

- [x] OIDC issuer/subject identity model and migration.
- [x] Product DB membership authority for Product API and Agent Server.
- [x] Opaque context discovery/selection and context-switch fencing.
- [x] Two-user/two-tenant PostgreSQL read/write/revoke matrix.
- [x] User-private Agent Store namespace rewrite.
- [x] Hosted-safe provisioning issuer contract.
- [x] Durable Product/official checkpoint fork and recovery contracts.
- [x] Real local BFF/worker/official Agent fork proof.
- [x] Desktop/Pixel 7 real fork visual and DOM regression.
- [ ] Real hosted OIDC provider and trusted HTTPS deployment.
- [ ] Owner, same-tenant peer, cross-tenant, and revoked-user browser storage
      states generated through real login.
- [ ] Hosted zero-mock respond/cancel/fork matrix on Desktop and Pixel 7.
- [ ] Context switch with deliberately late old-workspace responses in hosted UI.
- [ ] Licensed persistent Agent Server restart/recovery proof.
- [ ] Independent operator audit and release attestation.

Until the unchecked items pass, M4 and V2 remain `partial`.
