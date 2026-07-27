# Production Runbook

Status: `V2: PARTIAL`

Production Ready: `NO`

This runbook describes the free/open self-hosted target. It is executable only after
the protected environment supplies immutable registry digests, trusted HTTPS, real
OIDC identities, database/Redis targets, key custody and alert routing. File presence
does not prove any hosted gate.

## Deployment

1. Verify the immutable source candidate, registry digests, SBOM, Trivy result and all
   four Sigstore identities against `deploy/attestation-policy.yaml`.
2. Populate the names in `deploy/env.production.example` through the platform secret
   manager. Never use `backend/.env` or commit a populated file.
3. Terminate trusted TLS at the platform ingress and forward only to the loopback-bound
   `ingress` service. `NEXTAUTH_URL` must be the same public HTTPS origin.
4. Run `docker compose --env-file <protected-file> -f deploy/docker-compose.production.yml config`.
5. Run the migration service once, start the stack, wait for every health check and
   execute API, Agent Protocol and hosted browser preflight checks.
6. Record source SHA, image digests, migration revision and preflight hashes outside
   the repository before importing approved evidence.

## Rollback

Stop admission, retain Product and Agent databases, select the previously attested
image digests and execute the documented schema compatibility check before switching
traffic. Never downgrade the database blindly. Confirm pending Runs, checkpoints,
commands and usage reconciliation before reopening admission.

## Backup And Restore

Use PostgreSQL-native, encrypted backups for both databases. A release requires a
measured restore into isolated infrastructure, constraint validation, source/restore
row-count checks, PITR evidence and RTO/RPO measurements. The local backup rehearsal
does not satisfy this gate.

## Key Rotation

Rotate OIDC, NextAuth, internal JWT and integration-secret material independently.
Preserve JWT overlap only for the bounded verification window and prove old-token
rejection afterwards. Signing keys belong to the protected platform or Sigstore
keyless identity; do not store private release keys in the repository.

## Provider And Observability Outages

Market, search and model exhaustion fails the affected analysis closed. LangSmith or
Langfuse delivery exhaustion must not alter a valid business result, but must emit the
redacted provider-specific fingerprint in `deploy/alerts.yaml`. Verify both positive
alerts and a negative control in the hosted receiver.

## Quota And Entitlement Incidents

Do not bypass admission limits. Inspect immutable usage rows, reconciliation receipts
and the applicable entitlement version. Apply a versioned policy change only after
review; record the actor, reason and rollback target.

## Data Deletion

Run deletion through the Product lifecycle API and worker. Confirm append-only receipts
and survivor scans for Product DB, official Aegra Threads/checkpoints and Store. Hosted
telemetry, object/index stores, logs and backup expiry remain pending until their own
official deletion or retention receipt exists.

## Evidence Boundary

Local Compose, fixture, skipped, in-memory and mutable-image results are never
production evidence. External notification sending is excluded. Production acceptance
still requires public HTTPS/OIDC actor tests, hosted HA/DR/SLO/security, clean CVE
policy, registry/protected signing, immutable evidence and independent review.
