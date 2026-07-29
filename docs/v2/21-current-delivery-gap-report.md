# V2 Current Delivery Gap Report

Date: 2026-07-23 (Asia/Shanghai)

Status: `V2: PARTIAL`

Production Ready: `NO`

Authority: evidence-backed current-state inventory. Normative requirements remain in
`13-v2-final-rebuild-spec.md` and `14-v2-final-implementation-plan.md`. This report
does not replace the missing reviewed `normative-baseline.json` or
`requirements-registry.yaml`.

## 1. Executive verdict

The current-source Product Agent main flow works. Fresh Desktop and Pixel 7 runs each
completed against real OKX, real provider-backed Web evidence and model calls, including
the official LangGraph human-review interruption and persisted final Artifact. Browser
inspection of latest Run `e3a47596-18a2-4bcd-ab80-de0062b7f12c` shows four citations,
evidence/risk gates, the final decision and two model-call audit records with no console
errors. Earlier failed proxy/provider runs remain visible as truthful history.

All six repository/local product groups are now implemented at their stated proof
levels: unified request routing; Scheduled Monitor through official Aegra Cron and a
matured Outcome; Memory/Outcome; controlled improvement; entitlement/usage,
Webhook/Secret Store and lifecycle receipts; and the locally executable production
operations/supply-chain checks. External notification sending remains excluded.

The current local stack is healthy and the inspection entry is
`http://127.0.0.1:3001/work`.

This is not a production release. The remaining blockers require a real hosting and
release environment: trusted HTTPS/OIDC identities, hosted telemetry/formal SLO,
production PITR/DR, registry/protected signing and an immutable independently reviewed
candidate. The current backend image also fails the CVE release gate.

## 2. Current local evidence

| Gate | Current result | Claim boundary |
| --- | --- | --- |
| Real Product Agent mainline | Desktop and Pixel 7 passed with real provider/model, two HITL cycles and Aegra replacement/recovery | Local dirty-worktree evidence, not hosted acceptance |
| Current real Product Agent mainline | Desktop and Pixel 7 `2 passed`; latest committed Run inspected in browser | Local real-provider dirty-worktree evidence, not hosted acceptance |
| Backend unit/contract | Unit `240 passed`; contract `834 passed, 1 skipped` | The live Agent Protocol skip remains unproved |
| Repository deployment/governance tools | Current grouped suites exited zero | Local contracts only |
| Task 14 production packaging | CI, non-root/read-only images, immutable-image Compose, alerts/attestation policy, hosted browser profiles, runbook, Syft/Trivy build runner and Compose probe contracts passed `70 passed` | Repository/local packaging only; dirty source and hosted inputs make release execution fail closed |
| Frontend | `472 passed`; lint, typecheck and Next production build passed | Local image, not registry-published |
| PostgreSQL migration | Current Product database at `0031_lifecycle_receipt_retention` | Local PostgreSQL 16, not hosted migration proof |
| Upgrade/rollback | `0022 -> 0015 -> 0022` | Local rehearsal, not zero-downtime rollout |
| Credential rotation | Four credentials rewrapped; interrupted resume and old-JWT rejection passed | Local rehearsal, not protected production key custody |
| Backup/restore | 32 tables, 52 rows, stable source counts, isolated restore match, zero unvalidated constraints | No PITR, cross-region restore, RTO or RPO proof |
| Local health load | 200/200 at concurrency 20; p95 118.387 ms | Health endpoint only; no business SLO claim |
| Product DB SLO observation | Settled read-only snapshot; formal coverage `0/12` | Proxy diagnostics only |
| Dependency/SBOM | Python 154 packages and frontend 584 dependencies, zero vulnerabilities; two CycloneDX SBOMs | Dirty source; no hosted audit |
| Backend image SBOM | 773 components, 2668 dependencies, exact image `sha256:a8e5a0cf...` | No registry digest |
| Image CVE | 168 findings; 4 Critical, 19 High, zero currently fixable | Release gate RED |
| Local Cosign rehearsal | Offline verify and tamper rejection passed; temporary key deleted | No protected/keyless identity, Rekor, timestamp or OCI attestation |

Current external evidence roots added or refreshed during this audit:

- `E:\project\study\codex\crypto\product-database-backup-20260722-01`
- `E:\project\study\codex\crypto\local-load-slo-20260722-01`
- `E:\project\study\codex\crypto\backend-full-real-db-20260722-02`
- `E:\project\study\codex\crypto\crypto-manual-alert-supply-20260722-07`
- `E:\project\study\codex\crypto\container-image-sbom-20260722-05`
- `E:\project\study\codex\crypto\container-image-signature-20260722-05`
- `E:\project\study\codex\crypto\production-readiness-blockers-20260722-02.json`
- `E:\project\study\codex\crypto\aegra-ha-current-20260723-02`
- `E:\project\study\codex\crypto\supply-chain-current-20260723-03`
- `E:\project\study\codex\crypto\trivy-current-20260723-02`
- `E:\project\study\codex\crypto\cosign-current-20260723-02`
- `E:\project\study\codex\crypto\production-readiness-blockers-current-20260723-03.json`
- `E:\project\study\codex\crypto\production-readiness-blockers-current-20260723-04.json`

## 3. Open delivery gates

| Priority | Gate | Current evidence | Required completion evidence |
| --- | --- | --- | --- |
| P0 | Normative baseline and requirement registry | Generation-one builder, 27-source candidate policy and repository preflight pass; real extraction still fails closed on unanchored approved-source statements | Ordered Task 0/0B reviews, immutable candidate SHA, reviewed baseline, complete explicit anchors and individually owned registry |
| P0 | Immutable release candidate and independent review | Dirty worktree; no final artifact tree or signed final review | Clean committed candidate, frozen evidence, independent reviewer with zero Critical/Important findings, signed attestation |
| P0 | Production deployment and identity | Production Compose/CI/hosted browser profiles and fail-closed probe now exist; no trusted domain, protected environment or hosted browser proof | Public trusted HTTPS, real OIDC, owner/peer/cross-tenant/revoked-user Desktop and Pixel 7 matrix |
| P0 | Production Aegra availability | Local real restart and QA-only HA are separate evidence sets | Hosted multi-instance ingress, rolling upgrade, failover and full Product retry/cancel/fork recovery |
| P0 | External observability and alerting | Local SDK/transport and redaction contracts only | Same real Run visible through OpenTelemetry in a verified free/self-hosted backend, with correlation/redaction/outage receipts and production alerts; LangSmith/Langfuse remain optional |
| P1 | Production data resilience | Local backup/restore, rollback and key rotation passed | Managed backup policy, PITR, cross-region restore, measured RTO/RPO and hosted migration/rollback |
| P1 | Formal load, SLO and security | Health load passed; Product DB can measure 0/12 formal SLOs | Hosted business-flow load, all 12 source-of-truth metrics, alert receipts, full hosted tenant/secret canary audit |
| P1 | Supply-chain release proof | Current exact-image SBOM/Cosign pass; Trivy gate RED with 4 Critical and 19 High unfixed findings | Clean CVE policy result, registry digest, protected KMS/keyless signer, Rekor/timestamp, signed OCI provenance/attestation |
| P2 | External lifecycle completion | Official local Aegra deletion and immutable receipts pass; logs/backups remain pending expiry | Hosted telemetry/object/index adapters, elapsed retention and survivor scan receipts |

External Bark/Web Push/Email delivery is excluded and is not an open completion gate.

## 4. Structural delivery gaps

The final plan's `Create:` declarations currently resolve to 413 unique paths: 138
exist and 275 do not. This is not a semantic completion score because current code
consolidates several planned modules and Aegra replaces the former commercial Agent
Server packaging. It is still material evidence of plan-to-worktree drift.

The current release-specific audit is unambiguous: six critical repository artifacts
and all 54 referenced final release artifact paths are missing. They are:

- `docs/v2/normative-baseline.json` is absent.
- `docs/v2/requirements-registry.yaml` is absent.
- `artifacts/v2-final/requirements-evidence.json` is absent.
- `artifacts/v2-final/final-review-attestation.json` is absent.
- `artifacts/v2-final/final-review-attestation.sigstore.json` is absent.
- `artifacts/v2-final/versions.json` is absent.

A direct extraction of `artifacts/v2-final/...` references from the final plan found
54 unique paths and zero present. Some are directories/placeholders, so the count is a
path-presence audit rather than 54 independent requirements.

## 5. Inputs that require owner authority

The following cannot be honestly completed from this workstation alone. Values must
be delivered through a secret manager or protected CI environment, not pasted into
tracked files or this report:

1. Production hosting target, region, public domain and DNS/TLS ownership.
2. OIDC provider, tenant/client configuration and test identities for the actor matrix.
3. Managed PostgreSQL, Redis, object storage, backup/PITR and disaster-recovery target.
4. Container registry plus protected KMS or keyless Sigstore identity and policy.
5. LangSmith and Langfuse production projects, credentials, retention and query access.
6. Production monitoring/alert-routing backend and responders.
7. Hosted lifecycle systems and retention authorities for external deletion receipts.
8. Independent specification, code-quality, data-custodian, platform-custodian and final-release reviewers.

## 6. Execution order

1. Establish the reviewed normative baseline and requirement registry. Do not invent
   reviewer identities or backfill evidence after implementation.
2. Produce an immutable release-source candidate and publish exact image digests.
3. Deploy to trusted HTTPS with real OIDC and run the hosted actor/security matrix.
4. Run real LangSmith/Langfuse, alert, PITR/DR, rollout/failover, load,
   SLO, secret-canary and image CVE gates against the same candidate.
5. Freeze `artifacts/v2-final`, verify every requirement mapping and artifact hash,
   then run the final independent review and protected signing/attestation chain.

Until all five remaining stages have real evidence, the only valid overall verdict is
`V2: PARTIAL`; `Production Ready: NO`.
