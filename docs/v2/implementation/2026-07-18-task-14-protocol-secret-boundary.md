# Task 14 Protocol Secret Boundary Record

Date: 2026-07-18 Asia/Shanghai
Phase: Task 14 / protocol and Product DTO security
Status: local behavioral gate complete; full production canary evidence open

## Objective

Prove with synthetic credentials that Product admission, the canonical Graph,
official LangGraph state streams, terminal errors, Artifact provenance, and the
notification settings DTO do not serialize runtime credentials or raw secret
input. This slice implements the repository test named by Task 14 without
claiming the broader hosted release gate.

## RED

The first focused run produced a real behavior failure:

```text
3 failed, 1 passed
```

`AnalysisSubmission` and `AnalysisRequest` preserved a query containing an API
key assignment and email address. The raw values consequently appeared in the
Product JSON payload, Graph state, official `updates`/`values` stream, research
query, model input, and terminal state. Runtime object attributes and exception
messages did not leak; the missing boundary was input redaction before Product
persistence and Graph state creation.

## Implementation

- `AnalysisSubmission.query_text` now passes through the existing centralized
  PII/secret redactor before `ProductAnalysisService` computes the idempotency
  hash or stores Task/Command payloads.
- `AnalysisRequest.query_text` applies the same validation at the canonical
  Graph boundary. This is defense in depth for non-Product callers and does not
  create a second Graph, Agent loop, stream protocol, or persistence authority.
- Existing official LangChain `PIIMiddleware` remains responsible for model
  input/output and tool-result protection. Existing LangSmith/Langfuse masking
  remains the observability egress boundary.
- The new behavioral test executes the compiled canonical `StateGraph` with
  Provider/Research/Agent objects that contain synthetic secret attributes. It
  serializes official `updates` and `values`, terminal state, typed terminal
  DTO, research inputs, model inputs, errors, provenance, and notification
  settings DTOs, then asserts the canaries are absent.
- Frontend Product/Agent BFF source was reviewed. Both proxies already replace
  browser authority with server-owned authorization, expose bounded response
  header allowlists, return generic transport failures, and expose no browser
  Run-creation route. No frontend production code was changed in this slice.

## Files

- `backend/src/crypto_alert_v2/api/schemas.py`
- `backend/src/crypto_alert_v2/graph/request.py`
- `backend/tests/security/test_protocol_secret_leak.py`

No database migration, API route, Graph State field, custom event, frontend
schema, or dependency was added.

## Verification

```text
protocol secret gate:       4 passed
complete security suite:   31 passed
Graph and Product API:    115 passed
domain/persistence DTO:    80 passed
backend hermetic suite:   800 passed, 157 skipped, 1 warning
Ruff focused check:       passed
```

The 157 skipped tests remain unproved external/real PostgreSQL requirements.
`PRODUCT_DATABASE_URL` was not configured in this shell, so no fresh real
PostgreSQL result is claimed for this slice. The earlier `184 passed` database
run belongs to the key-rotation/migration slice and is not reused as current
evidence.

## Evidence Boundary

This is a local synthetic-canary behavior gate. It does not yet execute the
complete Task 14 requirement across a licensed persistent Agent Server,
persisted checkpoint restart, hosted LangSmith and Langfuse, browser HTML and
screenshots, repository/release artifacts, real OIDC sessions, or a protected
HTTPS deployment. Notification coverage proves DTO non-echo but not a real
Bark plus Web Push-or-Email receipt. The full wire/checkpoint/trace/log/browser
scan, hosted multi-user matrix, source candidate, review, and attestation remain
open. V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was
performed.
