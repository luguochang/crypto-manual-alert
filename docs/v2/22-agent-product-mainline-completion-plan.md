# Agent Product Mainline Completion Plan

Date: 2026-07-22 (Asia/Shanghai)

Authority class: `informative execution control`

Status: `V2: PARTIAL`

Production Ready: `NO`

This plan translates the user-approved completion goal into stable working IDs and
evidence targets. It does not replace `normative-baseline.json`, the reviewed
requirement registry, or the Task 0/0B review chain. Normative conflicts are resolved
by the authority order in `13-v2-final-rebuild-spec.md` section 0.

## 1. Scope and exclusion

The target is the complete Agent product loop around the existing real market-analysis
and Deep Research mainline:

```text
manual / scheduled / postmortem / eval / system request
  -> typed DecisionRequest
  -> intent, complexity, slot and position/risk policy
  -> existing Product admission and canonical LangGraph
  -> real market/search/model or frozen replay inputs
  -> deterministic evidence/risk gates and HITL
  -> durable Artifact, history and usage
  -> Memory and Outcome lifecycle
  -> feedback, experiment, candidate, release approval, shadow and rollback
```

External notification delivery is explicitly out of scope. Existing Outbox data may
remain for compatibility and audit, but Bark, Web Push, Email and equivalent delivery
receipts are not completion requirements. Scheduled Monitor completion ends at a
persisted Product result, not an external notification.

The system remains manual-only. It must never place/cancel orders, transfer funds or
read trade/withdraw credentials.

## 2. Reuse policy

| Capability | Required owner | Project code allowed |
| --- | --- | --- |
| Agent loop, tools, middleware, structured output | LangChain `create_agent` and typed response formats | Domain prompts, tools and adapters only |
| Graph routing, checkpoint, interrupt, resume, stream | LangGraph official APIs | Typed state, nodes and deterministic domain routing only |
| Restricted delegated research | Deep Agents when its locked free/open capability enforces the policy; otherwise one official `create_agent` fallback | Selector and permission policy only; never a second Agent loop |
| Threads, Runs, checkpoint persistence, Cron | Apache-2.0 Aegra and official LangGraph SDK/protocol | Product admission, projection and ACL bridge only |
| Product history, commands, Memory metadata, Outcome, usage | PostgreSQL/Alembic; Redis only for runtime coordination already owned by Aegra | Product repositories, transactions and workers |
| Browser identity | Auth.js standard OIDC flow | Membership resolution and short-lived internal JWT only |
| Telemetry | OpenTelemetry plus a verified free/self-hosted backend; Langfuse may be optional after license/deployment verification | One centralized callback/export boundary only |
| TLS/ingress and HA | Existing container standards plus a verified free/open ingress/runtime | Repository deployment policy and health probes only |
| SBOM, CVE, signing, attestation | CycloneDX/Syft or equivalent, Trivy or equivalent, Cosign/Sigstore | Evidence orchestration and fail-closed policy only |

No custom checkpoint store, interrupt protocol, SSE transport, stream deduplication,
general Agent loop, Cron scheduler or browser thread store may be introduced. A new
project implementation is permitted only after a source-and-license review records
that no applicable free official capability exists.

## 3. Requirement-to-evidence registry

`Current` describes evidence at the time this plan was created. `Complete` always means
the named final evidence exists; path presence or a fixture test is insufficient.

| ID | Requirement and acceptance | Framework/reuse boundary | Final evidence | Current |
| --- | --- | --- | --- | --- |
| PM-ENTRY-001 | One typed `DecisionRequest` represents manual, scheduled, postmortem, eval/replay and system requests with actor, workspace, session, intent, complexity, symbol, horizon, position, risk mode and side-effect policy. | Pydantic models; reuse current Product admission schemas. | Unit/contract schemas, migration compatibility and API round-trip tests. | Missing generalized request; only market-analysis/deep-research submissions exist. |
| PM-ENTRY-002 | Intent classification is typed, confidence-bounded and fail-closed; unknown financial intent requests clarification or research, never an invented action. | Deterministic rules first; optional LangChain structured classifier only where ambiguity remains. | Golden cases plus real model cases with stable typed output. | Missing. |
| PM-ENTRY-003 | Complexity routing selects `simple_fast`, `standard`, `deep_research`, `eval_replay` or `blocked_clarify` from explicit policy and budgets. | Deterministic Product policy; delegates only the selected existing Graph branch. | Policy unit tests and end-to-end route evidence. | Only explicit analysis/deep-research UI modes exist. |
| PM-ENTRY-004 | Slot policy handles symbol, horizon, position side/entry/size/leverage and risk mode; missing execution facts block open/flip actions. | Existing Evidence/Risk gates and typed DTOs. | Golden missing/conflict cases and real UI/API assertions. | Partial domain fields exist; entry request is not position-aware. |
| PM-ENTRY-005 | Work UI supports all five entry semantics without exposing raw Graph state; postmortem/eval never trigger live side effects. | Existing Next.js BFF, Product API and view-model ownership. | Desktop/Pixel 7 Playwright and persisted reload evidence. | Manual analysis/deep research only. |
| PM-MON-001 | Monitor creation from an Artifact persists schedule, condition, expiry, quiet hours and ownership. | Existing Product Monitor repository/API/UI. | PostgreSQL/API/UI tests. | Implemented locally. |
| PM-MON-002 | Aegra Cron creates only an infrastructure trigger; Product admission remains sole owner of the analysis Task/Run. | Aegra Cron and official SDK; existing command dispatcher. | Real Cron/trigger/admission lineage across restart. | Partial local implementation; complete Product execution proof missing. |
| PM-MON-003 | Scheduled execution ends in durable Artifact/status/usage and survives reconnect/restart, with no external notification requirement. | Existing canonical Graph, Product projections and Aegra checkpoints. | Desktop/Pixel 7 plus worker/server restart evidence. | Missing full real chain. |
| PM-MEM-001 | Session memory stores current clarification, declared position/risk and unresolved slots without treating historical market conclusions as facts. | LangGraph state/checkpoint for current execution; Product DB for durable session projection. | Isolation, TTL, stale-fact and reconnect tests. | Missing. |
| PM-MEM-002 | Long-term Memory supports profile, released strategy config, process lessons, refreshed event memory and badcase metadata with separate purposes. | Official LangGraph Store namespace rewriting; Product metadata/ACL. | Cross-tenant Store tests and real persistence evidence. | Store isolation exists; product Memory service is missing. |
| PM-MEM-003 | Users can list, cap, disable and delete Memory; deletes enter a durable queue and legal-hold/retention states are visible. | Existing Product lifecycle worker patterns. | API/UI/PostgreSQL/Desktop/Pixel 7 evidence. | Missing. |
| PM-OUT-001 | Outcome maturation schedules from Artifact horizon and binds exchange-native price evidence with observation timestamps. | Existing OKX typed provider and Product worker model. | Real exchange-native maturation receipt and source hashes. | Missing. |
| PM-OUT-002 | Scoring records decision, hold and no-trade baselines plus Brier/calibration, MFE, MAE, fees, slippage and funding where applicable. | Deterministic evaluators; no LLM decides profitability. | Unit/golden tests and at least one real matured cohort. | Missing. |
| PM-OUT-003 | UI always labels sample count/window/source and cannot claim quality at insufficient sample size. | Existing Product API/view-model pattern. | Unit, accessibility and responsive Playwright evidence. | Missing. |
| PM-EVAL-001 | Feedback can create a typed postmortem/badcase without changing live policy. | Existing Feedback projection plus Product workflow. | API/UI/ACL tests and retained case evidence. | Feedback foundation only. |
| PM-EVAL-002 | Frozen Replay binds request, versions, market/evidence packets, gates and observed output; replay never fetches new facts or writes live plans. | Existing evaluation dataset/experiment modules; canonical domain functions. | Determinism, no-network and no-side-effect tests. | Foundation only. |
| PM-EVAL-003 | Baseline/candidate experiments include RuleJudge, advisory LLM judge and Outcome metrics; no judge bypasses Risk Gate. | LangSmith is optional; use local/open experiment storage and official SDK adapters where available. | Reproducible experiment artifact with hashes. | Partial backend foundation; no product loop. |
| PM-EVAL-004 | Candidate prompt/rule/workflow changes carry a diff, rationale, metrics and rollback target and require human review. | Product DB/HITL; reuse LangGraph interrupt for approval. | Candidate API/UI and approve/reject audit evidence. | Missing. |
| PM-EVAL-005 | Release Gate supports offline experiment, shadow execution, explicit promotion and rollback without self-modifying production. | Existing release-gate module, immutable version references and deployment policy. | Baseline/candidate/shadow/rollback evidence. | Backend foundation only. |
| PM-COM-001 | Entitlements cover modes, model/search budgets, concurrency, storage, retention and scheduled tasks across workspaces. | Product PostgreSQL policy. | Cross-workspace contract and API/UI evidence. | Monitor-only entitlement slice. |
| PM-COM-002 | Usage is immutable and reconciles model/search/runtime/storage totals; quota failures are stable and auditable. | Product ledger plus provider/runtime receipts. | PostgreSQL process-restart and drift evidence. | Missing complete implementation. |
| PM-INT-001 | Webhooks use rotating keys, timestamp/nonce replay protection, idempotency and delivery audit. | Standard cryptographic libraries and Product Outbox patterns; no custom transport protocol. | Positive, replay, tamper and rotation tests. | Missing. |
| PM-INT-002 | Integration secrets use a configured secret-store adapter and never enter Graph state, prompt, trace or browser. | Verified free secret-store option or deployment-native secret files; centralized adapter. | Secret canaries across protocol/trace/log/UI. | Missing. |
| PM-LIFE-001 | Export/deletion covers Product DB, checkpoint, Store, object storage, indexes, telemetry, logs and backup-expiry queues. | Existing lifecycle job/worker plus official backend APIs. | Per-system receipts and survivor scan. | Product DB slice only; external systems pending. |
| PM-PROD-001 | Trusted HTTPS and real OIDC prove owner, peer, cross-tenant and revoked-user browser matrices. | Auth.js OIDC plus free/open ingress. | Hosted Desktop/Pixel 7 zero-mock evidence. | Missing. |
| PM-PROD-002 | Self-hosted Aegra deployment proves multi-instance ingress, rolling update, failover, checkpoint recovery and Product retry/cancel/fork. | Aegra/PostgreSQL/Redis and official SDK only. | Hosted kill/upgrade/failover artifacts. | Local QA/HA evidence only. |
| PM-PROD-003 | Central telemetry proves correlation, redaction, outage tolerance, SLOs and alerts without a paid service dependency. | OpenTelemetry plus verified free/self-hosted backend; optional adapters only. | Same-run trace/query and alert receipts. | Local contracts only. |
| PM-PROD-004 | Production DB proves roles, migration, PITR/restore, RTO/RPO and reconciliation. | PostgreSQL-native/managed-compatible tooling. | Isolated and hosted DR evidence. | Local backup/rollback only. |
| PM-PROD-005 | Image has registry digest, CVE result, SBOM, protected free/open signing identity and signed provenance/attestation. | Trivy-equivalent, CycloneDX/Syft-equivalent and Cosign/Sigstore. | Registry verification, policy and tamper evidence. | Local SBOM/ephemeral signature only. |
| PM-PROD-006 | Reviewed immutable candidate maps every applicable requirement to evidence and has no Critical/Important findings. | Existing requirement tools plus independent reviewers. | Signed final review/attestation. | Missing. |
| PM-NOTIFY-X01 | External Bark/Web Push/Email delivery is excluded. Existing notification code must remain safe and compatible but is not extended or used as production-completion evidence. | No new provider. | Scope assertion and discovery tests only. | Explicitly excluded by user. |

### 3.1 Current evidence refresh (2026-07-23)

The `Current` column above is the 2026-07-22 planning baseline. The following delta is
the authoritative execution status for this working tree:

| Group | Current result | Evidence boundary |
| --- | --- | --- |
| PM-ENTRY | Local acceptance closed: one typed envelope covers all six request semantics; deterministic intent, complexity, slot, position/risk and side-effect policy are persisted; the Work UI exposes the six modes and non-live modes fail closed. | Real local PostgreSQL/API/UI plus contracts; only provider-backed manual/scheduled analysis is production-like execution. |
| PM-MON | Local acceptance closed: official Aegra Cron -> Product admission -> canonical Graph/HITL -> committed Artifact -> exchange-native matured Outcome survived API/worker restart. | Real local Aegra/PostgreSQL/provider/model/browser evidence; not hosted scheduler or host-loss proof. |
| PM-MEM / PM-OUT | Local acceptance closed: scoped/TTL Memory with safe injection and user disable/delete; Outcome maturation, decision/no-trade/hold baselines and deterministic Brier/MFE/MAE/cost metrics; responsive UI labels source/window/sample limits. | Real local PostgreSQL and OKX evidence. One QA sample is explicitly insufficient to claim strategy quality. |
| PM-EVAL | Local acceptance closed: Feedback/Postmortem, immutable Frozen Replay, Dataset/Experiment, official LangGraph candidate-review interrupt, frozen Shadow, promote/rollback and append-only release events are visible in Product UI. | Real local PostgreSQL/Aegra/browser evidence; frozen Shadow is not live production traffic. |
| PM-COM / PM-INT / PM-LIFE | Repository/local acceptance closed: entitlement/quota, immutable usage and reconciliation, signed nonce/timestamp Webhook, file Secret Store, official Aegra Thread/Store deletion and append-only per-system receipts. | Real local PostgreSQL/Aegra evidence. Hosted telemetry/object/index deletion and log/backup expiry remain pending or not applicable, never reported as deleted. |
| PM-PROD | Local portions complete and fail closed: current-image Aegra durability/HA, backup/restore, local SLO observation, SBOM, offline signing/tamper check and Trivy scan. | Production acceptance remains open: no public HTTPS/OIDC, hosted SLO/DR, registry/protected signing identity, immutable candidate or independent review; current image has 4 Critical and 19 High unfixed findings. |

Current broad verification is backend unit `240 passed`, backend contract
`834 passed, 1 skipped`, frontend `472 passed` plus typecheck/lint/build, and green
repository deployment/tool checks. Desktop and Pixel 7 real-provider Product E2E passed
`2 passed`. The single skip is classified as unproved, not passed.

## 4. Execution order and stop gates

1. Unified request foundation: PM-ENTRY-001 through PM-ENTRY-005.
2. Scheduled Product result: PM-MON-001 through PM-MON-003, without notification.
3. Memory and Outcome: PM-MEM-001 through PM-OUT-003.
4. Controlled improvement: PM-EVAL-001 through PM-EVAL-005.
5. Product governance/integration/lifecycle: PM-COM-001 through PM-LIFE-001.
6. Production proof: PM-PROD-001 through PM-PROD-006.

Each slice starts with failing contract/integration tests, reuses existing modules, and
ends with real PostgreSQL plus Desktop/Pixel 7 evidence where it has a browser surface.
Framework capability and license are checked before adding a dependency. A fixture can
prove deterministic logic but never closes a real-provider, restart or production row.

Work pauses and the design is corrected when any of these occurs:

- a second Agent/stream/checkpoint/Cron owner becomes reachable;
- a commercial runtime becomes mandatory;
- a local pass is being used to close a hosted row;
- historical market content can enter a live fact slot without refresh;
- an eval/postmortem path can create live side effects;
- a candidate can promote without human approval and rollback data;
- external notification work re-enters scope.

## 5. Completion rule

This goal is complete only when every non-excluded `PM-*` row has its named evidence,
the current source and artifact hashes match, all skips are classified as unproved,
and the final independent audit finds no missing or indirect proof. Until then the
only valid verdict is `V2: PARTIAL`; `Production Ready: NO`.
