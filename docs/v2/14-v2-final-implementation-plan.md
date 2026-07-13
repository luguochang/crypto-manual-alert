# V2 Final Implementation Plan

> authority_class: approved_normative
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Every production change follows red-green-refactor and receives specification review before code-quality review.

**Goal:** Build and verify the final multi-user crypto intelligence Agent product using the official LangChain, LangGraph, Deep Agents, Agent Server, LangSmith, Langfuse and React SDK contracts.

**Architecture:** One canonical LangGraph runs on Agent Server. LangChain agent factories own model/tool/middleware assembly; deterministic domain code owns evidence and risk decisions; Product PostgreSQL owns user-visible business records; `@langchain/react` owns live runtime state while Product APIs own history and projections.

**Tech Stack:** Python 3.12, uv, LangChain 1.3.13, LangGraph 1.2.9, Deep Agents 0.6.12, Agent Server, PostgreSQL 16, Redis 7, SQLAlchemy 2, Alembic, PyJWT, Next.js/React, Auth.js, `@langchain/react`, Zod, Playwright, LangSmith and Langfuse.

---

## Execution Rules

- Task 0 is the bootstrap exception to the later-task note and preexisting-`NORMATIVE_SHA` rules: its review requests identify the proposed normative candidate SHA, its three reviews run sequentially as specified below, and its manifest-only commit is the Task 0 attestation. Task 0B is the one-time exception to the preexisting requirement-registry receipt because it creates that registry; it still uses TDD, a note, candidate and two ordered reviews. Tasks 1-14 follow the complete registry/note/candidate/attestation protocol.
- Do not copy the prototype wholesale. Read the prototype only to migrate a named domain rule, test or presentation component.
- Do not implement more than one task before its tests and two reviews are complete.
- Do not use a fixture to prove a requirement that says real provider, real database, real browser or real observability.
- Do not expose secrets in source, logs, screenshots, traces or test artifacts.
- Add one Chinese implementation note under `docs/v2/implementation/` for each task.
- Each task uses a realizable two-commit protocol. First create a Conventional **candidate commit** containing GREEN code/tests and an implementation-note draft. Reviewers inspect that immutable candidate SHA; fixes create new candidate commits and are re-reviewed. After specification approval and then code-quality approval, create a `docs: attest task NN reviews` **attestation-only commit** that changes only the implementation note. The task is incomplete until this attestation exists.
- The note draft contains exact RED command/output/exit code, GREEN command/output/test count, implementer agent ID, base SHA and real-evidence limitations. The attestation adds the final reviewed candidate SHA, specification reviewer/result/findings/disposition and code-quality reviewer/result/findings/disposition. Code-quality review cannot start before specification approval, and no production/test/config file may change in the attestation commit.
- Every test file listed by a task must be executed once in RED for the intended missing behavior, including integration/real/browser tests. If external credentials are unavailable, collection/import must still fail for the intended missing implementation before credential/skip logic; a skip is not RED.
- Before each task's RED command, the controller uses the Task 0B structured registry tool to assign one accountable implementation role and concrete Agent ID to every requirement ID owned by that task, verifies source hashes/coverage, and writes an immutable pre-RED receipt containing the registry hash, owner assignments, timestamp and `NORMATIVE_SHA`. The task candidate stages the structured registry update, receipt and note draft. Placeholders, catch-all ownership or a RED timestamp preceding the receipt are rejected.
- The mandatory shared file inventory appended to every Task 1-14 `Files` section is: Modify `docs/v2/requirements-registry.yaml`; Create `artifacts/v2-final/pre-red/task-N.json`; Modify/Create that task's implementation note. Immediately before every candidate commit run `verify_requirements.py --phase candidate --task N --receipt artifacts/v2-final/pre-red/task-N.json --check-index`; it verifies the staged registry/receipt hashes, concrete Agent ID, `NORMATIVE_SHA`, timestamps and exact RED command against the pre-RED record. The candidate must force-stage the ignored receipt and include all three shared paths.

## Task 0: Commit the Immutable Normative Baseline

**Files:**
- Create: `docs/v2/normative-baseline.json`
- Review/modify only as required: `docs/v2/README.md`
- Review/modify only as required: `docs/v2/01-v2-product-and-architecture.md`
- Review/modify only as required: `docs/v2/02-official-framework-constraints.md`
- Review/modify only as required: `docs/v2/03-v2-delivery-checklist.md`
- Review/modify only as required: `docs/v2/04-implementation-note-template.md`
- Review/modify only as required: `docs/v2/05-official-research-evidence.md`
- Review/modify only as required: `docs/v2/06-c-end-agent-product-blueprint.md`
- Review/modify only as required: `docs/v2/07-official-doc-coverage-index.md`
- Review/modify only as required: `docs/v2/08-production-governance-and-nonfunctional.md`
- Review/modify only as required: `docs/v2/09-review-packet-and-decisions.md`
- Review/modify only as required: `docs/v2/10-implementation-roadmap.md`
- Review/modify only as required: `docs/v2/11-core-object-access-recovery-contract.md`
- Review/modify only as required: `docs/v2/12-production-proof-slo-and-lifecycle.md`
- Review/modify only as required: `docs/v2/13-v2-final-rebuild-spec.md`
- Review/modify only as required: `docs/v2/14-v2-final-implementation-plan.md`
- Review/modify only as required: `docs/v2/adr/README.md`
- Review/modify only as required: `docs/v2/adr/0001-agent-runtime-deployment.md`
- Review/modify only as required: `docs/v2/adr/0002-web-search-provider.md`
- Review/modify only as required: `docs/v2/adr/0003-identity-and-auth-bootstrap.md`
- Review/modify only as required: `docs/v2/adr/0004-frontend-presentation-stack.md`
- Review/modify only as required: `docs/v2/adr/0005-observability-and-prompt-source.md`
- Review/modify only as required: `docs/v2/adr/0006-production-slo-retention-and-outcome.md`
- Review/modify only as required: `docs/v2/adr/0007-launch-and-financial-product-boundary.md`
- Review/modify only as required: `docs/v2/adr/0008-production-deployment-profile.md`

- [ ] **Step 1: Verify the allowlisted documentation tree**

Run `git diff --check`, the forbidden-placeholder scan, secret-pattern scan and an authority-consistency scan that compares status/approval state across the checklist, index and ADR registry. Require every allowlisted file to declare exactly one machine-readable blockquote field `authority_class: approved_normative|mixed|verified_evidence_index|informative|superseded|proposed_gate`, with explicit normative-region anchors for `mixed` files; fail on missing/duplicate/unknown classification or any dirty path outside the reviewed V2 documentation allowlist.

- [ ] **Step 2: Create and review the normative candidate**

Stage every reviewed V2 baseline document explicitly, never with a bulk working-tree add, and commit `docs: finalize v2 normative baseline`. Dispatch a fresh specification/authority reviewer against that exact proposed normative candidate SHA; fix findings through a new candidate and repeat until approved. Then dispatch the plan-executability reviewer against the approved candidate; any finding creates a new candidate and restarts specification review before plan review. Only after both approve, dispatch the official-framework reviewer; any finding again creates a new candidate and restarts all three reviews in order. Task 0 is complete only at zero Critical/Important findings from the sequential chain.

- [ ] **Step 3: Attest the immutable baseline**

After zero Critical/Important findings, generate `docs/v2/normative-baseline.json` containing schema version, the reviewed candidate SHA as `NORMATIVE_SHA`, every reviewed candidate file with one explicit classification (`approved_normative`, `mixed`, `verified_evidence_index`, `informative`, `superseded`, or `proposed_gate`), explicit `normative_regions` anchors for mixed files, replacement/priority metadata, each candidate-file SHA-256, all three reviewer identities/results and timestamp. The manifest explicitly excludes itself from its file-hash set to avoid a self-hash cycle. Commit only that manifest as `docs: attest v2 normative baseline`, verify a clean tree, and require every later implementation note, review request and release-evidence entry to reference `NORMATIVE_SHA`. Normative changes after this point require a new candidate, the full sequential review chain, a new manifest and revalidation of affected implementation tasks.

## Task 0B: Bootstrap the Requirement Registry Before Any Product RED

**Files:**
- Create: `tools/v2/build_requirement_registry.py`
- Create: `tools/v2/verify_requirements.py`
- Create: `tools/v2/transition_normative_baseline.py`
- Create: `tools/v2/tests/test_requirement_registry.py`
- Create: `docs/v2/requirements-registry.yaml`
- Create: `docs/v2/implementation/2026-07-13-task-00b-requirements.md`

- [ ] **Step 1: Write the registry/bootstrap tests**

Tests load `normative-baseline.json`, require every `approved_normative` statement and every declared `mixed.normative_regions` statement to have one stable versioned ID/source anchor/content hash/task owner, create non-normative gate entries for `proposed_gate` statements, reject requirements extracted from informative/evidence/superseded regions, reject missing child entries/catch-all mappings, and verify structured owner assignment plus pre-RED receipt generation. Transition tests promote a reviewed proposed gate to approved normative in a new manifest generation, preserve its stable gate IDs, attach the new review chain/NORMATIVE_SHA and reject promotion without all required reviewers/evidence.

- [ ] **Step 2: Run RED**

Run: `python3.12 tools/v2/tests/test_requirement_registry.py`

Expected: FAIL because the generator, verifier and seed registry do not exist. A parse error or unavailable third-party dependency is not acceptable; before Task 1 dependencies exist, `requirements-registry.yaml` uses JSON-compatible YAML and the bootstrap tool parses it with Python 3.12's standard `json` module rather than ad hoc text manipulation.

- [ ] **Step 3: Generate the complete seed and prove pre-RED assignment**

Generate `requirements-registry.yaml` only from manifest files/regions classified `approved_normative`/`mixed.normative_regions`, plus stable non-normative gate entries for `proposed_gate` sources such as ADR 0008. Before implementation starts, every entry freezes its stable ID, source/content hash, implementation task/slice, accountable role, intended RED test/command and expected missing behavior, intended GREEN test/command, proof classification, final proof target and required environment. Production requirements and proposed production gates require `hosted-production` final proof. Run a dry assignment for Task 1 with a disposable test Agent ID, generate a receipt, verify it, then reset only that disposable assignment through the tested structured command so the committed seed has roles/tasks/proof mappings but no fake concrete implementer.

Run:

```bash
python3.12 tools/v2/tests/test_requirement_registry.py
python3.12 tools/v2/build_requirement_registry.py --manifest docs/v2/normative-baseline.json --registry docs/v2/requirements-registry.yaml --check
python3.12 tools/v2/verify_requirements.py --registry docs/v2/requirements-registry.yaml --manifest docs/v2/normative-baseline.json --phase bootstrap
```

- [ ] **Step 4: Create the candidate commit, run both reviews, then attest**

Commit: `build: bootstrap v2 requirement registry`

For every later Task N, before its first RED run execute the structured `--assign-owner` and `--phase pre-red --task N --receipt artifacts/v2-final/pre-red/task-N.json` commands. The verifier must exit 0 before RED; the candidate later includes the same registry hash/receipt and rejects reordered timestamps or changed ownership.

## Task 1: Dependency Lock and Agent Server Bootstrap

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/uv.lock`
- Create: `backend/langgraph.json`
- Create: `backend/src/crypto_alert_v2/__init__.py`
- Create: `backend/src/crypto_alert_v2/config.py`
- Create: `backend/src/crypto_alert_v2/graph/__init__.py`
- Create: `backend/src/crypto_alert_v2/graph/state.py`
- Create: `backend/src/crypto_alert_v2/graph/graph.py`
- Create: `backend/tests/contract/test_dependency_contract.py`
- Create: `backend/tests/contract/test_graph_export.py`
- Create: `tools/v2/probe_agent_server.sh`
- Create: `deploy/agent-server-image.lock`
- Create: `artifacts/v2-final/versions.json`
- Create: `docs/v2/implementation/2026-07-13-task-01-foundation.md`

- [ ] **Step 1: Write dependency and graph export tests**

```python
from importlib.metadata import version


def test_framework_compatibility_group() -> None:
    assert version("langchain") == "1.3.13"
    assert version("langgraph") == "1.2.9"
    assert version("deepagents") == "0.6.12"
    assert version("langchain-openai") == "1.3.5"
    assert version("langchain-tavily") == "0.2.18"
    assert version("langgraph-checkpoint-postgres") == "3.1.0"
    assert version("langgraph-cli") == "0.4.31"
    assert version("langgraph-api") == "0.11.0"
    assert version("langgraph-sdk") == "0.4.2"
    assert version("langchain-protocol") == "0.0.18"
    assert version("langsmith") == "0.10.2"
    assert version("langfuse") == "4.14.0"
    assert version("SQLAlchemy") == "2.0.51"
    assert version("alembic") == "1.18.5"
    assert version("asyncpg") == "0.31.0"
    assert version("fastapi") == "0.139.0"
    assert version("pydantic-settings") == "2.14.2"
    assert version("PyJWT") == "2.13.0"


def test_graph_is_compiled() -> None:
    from crypto_alert_v2.graph import graph

    assert type(graph).__name__ == "CompiledStateGraph"
```

- [ ] **Step 2: Run tests and confirm the expected import failure**

Run: `cd backend && uv run pytest tests/contract/test_dependency_contract.py tests/contract/test_graph_export.py -q`

Expected: FAIL at the first missing exact-version assertion or missing graph export. A test that only fails because `pytest` is unavailable is not an acceptable RED result.

- [ ] **Step 3: Create exact dependencies and minimal canonical graph**

The graph contains only `bootstrap -> complete` for this task. It must export `graph`, use official `StateGraph`, and configure no application-owned checkpointer or store.

- [ ] **Step 4: Generate lock and verify fresh installation**

Run:

```bash
cd backend
uv lock
uv sync --all-extras
uv run pytest tests/contract/test_dependency_contract.py tests/contract/test_graph_export.py -q
uv run python -c "from crypto_alert_v2.graph import graph; print(type(graph).__name__)"
uv run langgraph dev --help
../tools/v2/probe_agent_server.sh
```

`probe_agent_server.sh` starts `langgraph dev` in the background, records its PID, installs an EXIT trap before the first readiness poll, waits for `/ok`, probes Graph schema, and always terminates the process. Resolve the production Agent Server image to an immutable digest and store only `repository@sha256:...` in `deploy/agent-server-image.lock`. Generate `artifacts/v2-final/versions.json` from installed Python packages, Node packages, Docker/Compose versions and the image digest. Expected: all tests pass; output includes `CompiledStateGraph`; CLI help and HTTP probes exit 0; the versions artifact has no mutable image tag.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

```bash
git add backend deploy/agent-server-image.lock tools/v2/probe_agent_server.sh docs/v2/requirements-registry.yaml docs/v2/implementation/2026-07-13-task-01-foundation.md
git add -f artifacts/v2-final/versions.json artifacts/v2-final/pre-red/task-1.json
python3.12 tools/v2/verify_requirements.py --registry docs/v2/requirements-registry.yaml --manifest docs/v2/normative-baseline.json --phase candidate --task 1 --receipt artifacts/v2-final/pre-red/task-1.json --check-index
git commit -m "build: lock v2 official framework dependencies"
```

## Task 2: ActorContext, Auth Boundaries and Tenant Isolation

**Files:**
- Create: `backend/src/crypto_alert_v2/auth/context.py`
- Create: `backend/src/crypto_alert_v2/auth/agent_server.py`
- Create: `backend/src/crypto_alert_v2/auth/internal_token.py`
- Create: `backend/src/crypto_alert_v2/auth/membership.py`
- Create: `backend/src/crypto_alert_v2/auth/store_namespace.py`
- Create: `backend/src/crypto_alert_v2/governance/launch_boundary.py`
- Modify: `backend/langgraph.json`
- Modify: `backend/src/crypto_alert_v2/graph/state.py`
- Modify: `backend/src/crypto_alert_v2/graph/graph.py`
- Create: `backend/tests/contract/test_actor_context.py`
- Create: `backend/tests/contract/test_internal_token.py`
- Create: `backend/tests/contract/test_store_namespace_isolation.py`
- Create: `backend/tests/security/test_internal_alpha_boundary.py`
- Create: `backend/tests/integration/test_cross_tenant_access.py`
- Create: `docs/v2/implementation/2026-07-13-task-02-auth.md`

- [ ] **Step 1: Write failing ActorContext and namespace tests**

```python
def test_untrusted_payload_cannot_override_actor_context() -> None:
    actor = resolve_actor_context(
        mode="development",
        authenticated_claims=None,
        untrusted_payload={"tenant_id": "attacker", "user_id": "attacker"},
    )
    assert actor.tenant_id == "dev-tenant"
    assert actor.workspace_id == "dev-workspace"
    assert actor.user_id == "dev-user"


def test_namespace_is_always_prefixed() -> None:
    actor = ActorContext(
        tenant_id="t1",
        workspace_id="w1",
        user_id="u1",
        roles=("member",),
        permissions=("memory:read", "memory:write"),
    )
    assert rewrite_namespace(
        actor,
        scope="private",
        principal_id="u1",
        namespace=("preferences",),
    ) == (
        "tenant", "t1", "workspace", "w1", "scope", "private",
        "principal", "u1", "preferences",
    )
```

- [ ] **Step 2: Confirm failures**

Run: `cd backend && uv run pytest tests/contract/test_actor_context.py tests/contract/test_internal_token.py tests/contract/test_store_namespace_isolation.py tests/security/test_internal_alpha_boundary.py tests/integration/test_cross_tenant_access.py -q`

Expected: FAIL because `ActorContext`, `resolve_actor_context` and namespace rewriting do not exist; no HTTP route is required in this task.

- [ ] **Step 3: Implement server-owned identity**

Development mode injects one fixed member identity only for `local/test`, loopback bind and loopback Origin/Host; preview/staging/production fail startup if development identity is enabled, and the dev role is plain `member` with admin/billing/cross-tenant/high-risk integrations disabled. Production mode refuses to start without an authentication handler and trusted verification keys. Validate short-lived internal JWT `iss/aud/sub/tenant_id/workspace_id/roles/permissions/jti/iat/exp/kid`, reject unknown/expired keys and re-check claims against an injected membership resolver; Task 7 supplies the Product Repository adapter. Client payload/header fields named `tenant_id`, `workspace_id`, `user_id`, `roles` or `permissions` never become authority.

`launch_boundary.py` enforces ADR 0007 for `internal_alpha`: invite-only authentication with no public registration, no marketing/public-discovery mode, no exchange private keys or trade/order/cancel/transfer/withdraw permissions, no automatic execution routes/tools, and tier-gated sensitive financial fields/claims. Selecting External Beta/GA fails startup unless the jurisdiction, age, disclosure, personalization, suitability and field-display decisions are all accepted and referenced by immutable governance IDs. Contract/security tests inspect registered routes, tools, provider scopes, configuration keys and rendered product capabilities; a disclaimer alone cannot satisfy the boundary.

- [ ] **Step 4: Cover all Store methods**

Contract tests must exercise `put`, `get`, `search`, `delete` and `list_namespaces`. Tenant B must not infer the existence of Tenant A data. Add ACL cases for `private`, `workspace` and `restricted` resources, including user-a/user-b, tenant-a/tenant-b, an allowed workspace collaborator, a removed member, a denied non-member and an operator whose cross-tenant access requires an explicit action/reason audit record.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Run: `cd backend && uv run pytest tests/contract/test_actor_context.py tests/contract/test_internal_token.py tests/contract/test_store_namespace_isolation.py tests/security/test_internal_alpha_boundary.py tests/integration/test_cross_tenant_access.py -q`

Commit: `feat: enforce actor context and tenant isolation`

## Task 3: Domain Models, Evidence Gate and Risk Gate

**Files:**
- Create: `backend/src/crypto_alert_v2/domain/models.py`
- Create: `backend/src/crypto_alert_v2/domain/evidence_policy.py`
- Create: `backend/src/crypto_alert_v2/domain/risk_policy.py`
- Create: `backend/tests/unit/test_domain_models.py`
- Create: `backend/tests/unit/test_evidence_policy.py`
- Create: `backend/tests/unit/test_risk_policy.py`
- Create: `backend/tests/fixtures/golden_cases.py`
- Create: `docs/v2/implementation/2026-07-13-task-03-domain.md`

- [ ] **Step 1: Port tests before implementation**

Port only assertions with clear business meaning. Add explicit tests for required macro evidence:

```python
@pytest.mark.parametrize(
    "missing",
    ["vix", "real_yield_10y", "dxy", "macro_event_scan"],
)
def test_opening_action_requires_each_macro_field(valid_snapshot, valid_research, missing):
    valid_research[missing] = None
    verdict = check_evidence_sufficiency(
        market_snapshot=valid_snapshot,
        research_bundle=valid_research,
        main_action="open_long",
    )
    assert verdict.sufficient is False
    assert missing in verdict.missing_required
```

- [ ] **Step 2: Verify tests fail without implementation**

Run: `cd backend && uv run pytest tests/unit/test_domain_models.py tests/unit/test_evidence_policy.py tests/unit/test_risk_policy.py -q`

Expected: FAIL during import of the missing domain modules or on the first missing evidence/risk invariant. A RED result caused only by a missing test dependency is invalid.

- [ ] **Step 3: Implement pure deterministic policies**

No domain module may import LangChain, LangGraph, SQLAlchemy, HTTP clients or settings. Invalid inputs raise typed validation errors; missing evidence produces an explicit verdict.

- [ ] **Step 4: Run unit suite and coverage**

Run: `cd backend && uv run pytest tests/unit -q --cov=crypto_alert_v2.domain --cov-report=term-missing --cov-fail-under=95`

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: add deterministic evidence and risk domain`

## Task 4: Typed OKX and Web Search Providers

**Files:**
- Create: `backend/src/crypto_alert_v2/providers/okx.py`
- Create: `backend/src/crypto_alert_v2/providers/search.py`
- Create: `backend/src/crypto_alert_v2/providers/capability_probe.py`
- Create: `backend/src/crypto_alert_v2/providers/models.py`
- Create: `backend/src/crypto_alert_v2/providers/errors.py`
- Create: `backend/src/crypto_alert_v2/providers/retry_policy.py`
- Create: `backend/tests/unit/test_okx_parser.py`
- Create: `backend/tests/unit/test_search_parser.py`
- Create: `backend/tests/contract/test_provider_retry_budget.py`
- Create: `backend/tests/contract/test_search_capability_selection.py`
- Create: `backend/tests/integration/test_okx_provider.py`
- Create: `backend/tests/integration/test_search_provider.py`
- Create: `backend/tests/real/test_real_market_and_search.py`
- Create: `artifacts/v2-final/provider-proof/.gitkeep`
- Create: `artifacts/v2-final/provider-proof/search-provider-selection.json`
- Create: `docs/v2/implementation/2026-07-13-task-04-providers.md`

- [ ] **Step 1: Write parser and failure-semantics tests**

```python
def test_okx_parser_returns_numbers_not_raw_envelopes(okx_fixture):
    snapshot = parse_okx_snapshot(okx_fixture)
    assert snapshot.ticker.last > 0
    assert isinstance(snapshot.mark_price, Decimal)
    assert snapshot.index_price > 0
    assert snapshot.funding_rate is not None
    assert snapshot.open_interest > 0
    assert snapshot.order_book.bids
    assert snapshot.order_book.asks
    assert snapshot.candles
    assert snapshot.candles[0].close > 0


def test_provider_failure_is_not_success(http_500_transport):
    with pytest.raises(ProviderUnavailable):
        OkxProvider(transport=http_500_transport).fetch_snapshot("BTC-USDT-SWAP")
```

- [ ] **Step 2: Confirm parser tests fail**

Run: `cd backend && REAL_PROVIDER_TESTS=1 uv run pytest tests/unit/test_okx_parser.py tests/unit/test_search_parser.py tests/contract/test_provider_retry_budget.py tests/contract/test_search_capability_selection.py tests/integration/test_okx_provider.py tests/integration/test_search_provider.py tests/real/test_real_market_and_search.py -q`

Expected: FAIL before any network call because typed provider models/parsers, retry policy or capability-selection logic do not exist, or because inherited parsers return raw provider envelopes. The real test must not skip; its first failure must be missing implementation, not provider timeout.

- [ ] **Step 3: Implement adapters and LangChain tools**

Provider adapters parse and validate external data first. Thin `@tool` wrappers expose typed results to Agents. Errors retain provider, endpoint, retryability and correlation ID. The OKX adapter is public-market-data only: configuration schemas, HTTP clients, registered tools and tests reject API secret/passphrase/private-auth headers and contain no order, amend, cancel, transfer, withdrawal or account-balance capability. Market GET owns at most 3 attempts/10 seconds while still satisfying freshness; Web Search owns at most 3 attempts/30 seconds and honors Retry-After. Every attempt is recorded once, and Provider SDK retries are disabled or counted inside the same budget.

At startup, `capability_probe.py` tests the configured OpenAI-compatible provider independently for Tool Calling, Structured Output, streaming, usage reporting and built-in `web_search`. Tool Calling, Structured Output, streaming or usage failure always fails model readiness; Tavily cannot repair those capabilities. Only a built-in `web_search` failure may select locked `langchain-tavily`, and then Tavily key plus connectivity are required in readiness. If neither search path is ready, readiness fails and analysis cannot start; no silent provider fallback is allowed. Persist the selected provider, every capability result, timestamps and redacted endpoint/model metadata in `search-provider-selection.json`.

Immutable market records include venue, symbol, operation, exchange/client timestamps, clock skew, raw hash, normalized schema/freshness version and source level. Web Evidence includes query, final URL, redirect chain, HTTP status, fetched/published times, content hash or object reference, parser version, title/author/source, excerpt and evidence relation.

- [ ] **Step 4: Run fixture and real-provider tests separately**

Run:

```bash
cd backend
uv run pytest tests/unit/test_okx_parser.py tests/unit/test_search_parser.py tests/contract/test_provider_retry_budget.py tests/contract/test_search_capability_selection.py tests/integration/test_okx_provider.py tests/integration/test_search_provider.py -q
REAL_PROVIDER_TESTS=1 uv run pytest tests/real/test_real_market_and_search.py -q -s
```

Expected real proof: BTC/ETH/SOL each return nonempty ticker, mark, index, funding, open interest, order-book bids/asks and candles with source/freshness metadata; search returns at least one URL/title/published/fetched/snippet result. Provider errors fail visibly. Web Search cannot substitute any exchange-native field.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: add typed market and research providers`

## Task 5: Official Agent Factories and Structured Output

**Files:**
- Create: `backend/src/crypto_alert_v2/agents/market_analysis.py`
- Create: `backend/src/crypto_alert_v2/agents/research.py`
- Create: `backend/src/crypto_alert_v2/agents/middleware.py`
- Create: `backend/src/crypto_alert_v2/agents/middleware_profiles.py`
- Create: `backend/src/crypto_alert_v2/prompts/market_analysis.py`
- Create: `backend/tests/contract/test_agent_factory.py`
- Create: `backend/tests/contract/test_model_retry_budget.py`
- Create: `backend/tests/contract/test_middleware_profiles.py`
- Create: `backend/tests/contract/test_middleware_hook_order.py`
- Create: `backend/tests/security/test_pii_middleware_canaries.py`
- Create: `backend/tests/contract/test_structured_output.py`
- Create: `backend/tests/contract/test_research_permissions.py`
- Create: `backend/tests/real/test_real_model_analysis.py`
- Create: `docs/v2/implementation/2026-07-13-task-05-agents.md`

- [ ] **Step 1: Write factory and structured-response tests**

```python
async def test_market_agent_reads_structured_response(fake_model):
    agent = create_market_analysis_agent(model=fake_model)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "analyze"}]})
    assert isinstance(result["structured_response"], MarketAnalysis)


async def test_research_agent_binds_only_effective_read_tools(recording_model):
    agent = create_research_agent(model=recording_model)
    await agent.ainvoke({"messages": [{"role": "user", "content": "research"}]})
    names = set(recording_model.last_bound_tool_names)
    assert not names & {
        "write_file", "edit_file", "execute",
        "database_write", "send_notification",
    }
    assert approved_subagent_invocation_succeeds(agent)
    assert general_purpose_subagent_is_disabled(agent)
```

- [ ] **Step 2: Confirm failures**

Run: `cd backend && REAL_MODEL_TESTS=1 uv run pytest tests/contract/test_agent_factory.py tests/contract/test_model_retry_budget.py tests/contract/test_middleware_profiles.py tests/contract/test_middleware_hook_order.py tests/contract/test_structured_output.py tests/contract/test_research_permissions.py tests/security/test_pii_middleware_canaries.py tests/real/test_real_model_analysis.py -q`

Expected: FAIL because centralized factories do not exist, `structured_response` is absent, or the effective model-bound Deep Agents tool set still exposes forbidden built-ins. Tests must not rely on a hand-authored manifest or private graph internals to manufacture RED.

- [ ] **Step 3: Implement centralized factories**

Only factory modules may call `create_agent` or `create_deep_agent`. Use official middleware and `response_format`. Do not inspect the final message or call `json.loads` on model text. `middleware_profiles.py` freezes separate Coordinator, Research, Decision, Integration and Eval matrices plus exact before/after model/tool hook ordering. Official `PIIMiddleware` protects model output and tool results; key, Cookie and Authorization canaries must be absent from events, Protocol frames and persisted/observed output. `ModelRetryMiddleware` owns at most 2 transient attempts of 60 seconds each with no more than 4 model calls per Task; Structured Output owns at most one repair and does not nest another model retry budget. Deep Agents permission tests inspect the effective tool list bound to the model or execute calls against the compiled harness; a hand-authored manifest alone is not evidence.

- [ ] **Step 4: Execute a real model proof**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_agent_factory.py tests/contract/test_model_retry_budget.py tests/contract/test_middleware_profiles.py tests/contract/test_middleware_hook_order.py tests/contract/test_structured_output.py tests/contract/test_research_permissions.py tests/security/test_pii_middleware_canaries.py -q)
(cd backend && REAL_MODEL_TESTS=1 uv run pytest tests/real/test_real_model_analysis.py -q -s)
```

Expected: a validated `MarketAnalysis`, provider/model metadata and no raw secret in output.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: build official market and research agents`

## Task 6: Canonical Graph and Complete HITL Semantics

**Files:**
- Create: `backend/src/crypto_alert_v2/graph/request.py`
- Modify: `backend/src/crypto_alert_v2/graph/state.py`
- Modify: `backend/src/crypto_alert_v2/graph/graph.py`
- Create: `backend/src/crypto_alert_v2/graph/routes.py`
- Create: `backend/src/crypto_alert_v2/graph/runtime.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/bootstrap.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/validate_request.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/collect_market_snapshot.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/research_events.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/analyze_market.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/persist_stage.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/validate_evidence.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/apply_risk_policy.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/build_artifact.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/review_policy.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/interrupt_review.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/apply_edits.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/commit_artifact.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/complete_blocked.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/complete.py`
- Create: `backend/tests/contract/test_graph_topology.py`
- Create: `backend/tests/contract/test_analysis_request.py`
- Create: `backend/tests/contract/test_state_reducers.py`
- Create: `backend/tests/contract/test_execution_identity.py`
- Create: `backend/tests/contract/test_terminal_states.py`
- Create: `backend/tests/contract/test_event_stream_contract.py`
- Create: `backend/tests/integration/test_interrupt_resume.py`
- Create: `backend/tests/integration/test_interrupt_namespaces.py`
- Create: `backend/tests/integration/test_atomic_interrupt_state_update.py`
- Create: `backend/tests/integration/test_interrupt_races.py`
- Create: `backend/tests/integration/test_interrupt_expiry.py`
- Create: `backend/tests/integration/test_edit_revalidation.py`
- Create: `docs/v2/implementation/2026-07-13-task-06-graph.md`

- [ ] **Step 1: Write topology and terminal-state tests**

Define and test the public `AnalysisRequest(symbol, horizon, query_text, notify)` input contract, with normalized supported symbols/horizons and no authority fields accepted from untrusted payloads. Define typed `AnalysisState` fields and reducers for messages, evidence, artifacts, usage, progress, errors and terminal projection; reducer tests prove deterministic merge, deduplication and replay behavior. Every invocation generates or validates stable business/request/thread/task/run correlation IDs, propagates them through every custom event and node update, and rejects attempts to overwrite server-owned IDs. Task 7 later binds these IDs to the complete Workspace/Thread/Task/Run/Artifact/Interrupt/Checkpoint/EventProjection relational contract.

Cover required node names, parallel collection, default-development `review_policy=bypass`, forced `review_policy=required`, approve, reject, edit, provider failure, evidence block, expiry and replay from the beginning of the interrupting node. Client input cannot downgrade a Workspace-required review. Dedicated tests create both a root Graph interrupt and a nested approved research-subagent interrupt, preserve each interrupt ID plus full namespace/checkpoint identity, route responses only to the matching namespace and prove restart replay. When a response includes an allowed state correction, the official respond command applies the response and state update atomically at one checkpoint/version; injected failure cannot commit only one half. Interrupt responses carry interrupt ID, namespace, checkpoint ID and response version; `(interrupt_id, checkpoint_id, response_version)` is the idempotency key, first successful response wins and later responses return `INTERRUPT_ALREADY_RESOLVED`. Assert exact terminal statuses.

```python
def test_reject_is_blocked(graph_with_memory, thread_config):
    graph_with_memory.invoke(valid_input(), config=thread_config)
    result = graph_with_memory.invoke(Command(resume={"action": "reject"}), config=thread_config)
    assert result["terminal_status"] == "blocked"


def test_edit_is_applied_and_revalidated(graph_with_memory, thread_config):
    graph_with_memory.invoke(valid_input(entry=100), config=thread_config)
    result = graph_with_memory.invoke(
        Command(resume={"action": "edit", "edits": {"entry_trigger": 200}}),
        config=thread_config,
    )
    assert result["final_result"]["entry_trigger"] == 200
```

- [ ] **Step 2: Observe expected failures**

Run: `cd backend && uv run pytest tests/contract/test_analysis_request.py tests/contract/test_state_reducers.py tests/contract/test_execution_identity.py tests/contract/test_graph_topology.py tests/contract/test_terminal_states.py tests/contract/test_event_stream_contract.py tests/integration/test_interrupt_resume.py tests/integration/test_interrupt_namespaces.py tests/integration/test_atomic_interrupt_state_update.py tests/integration/test_interrupt_races.py tests/integration/test_interrupt_expiry.py tests/integration/test_edit_revalidation.py -q`

Expected: topology fails on missing required nodes/edges; reject fails unless it is `blocked`; edit fails unless the edited value is applied and the evidence/risk nodes execute again.

- [ ] **Step 3: Implement nodes and routes**

Each node accepts typed state/runtime dependencies declared in `graph/runtime.py`. Idempotent `persist_stage` commits are allowed before the interrupt so paid market/search/model/verdict outputs survive later failure; non-idempotent notification or external business side effects remain forbidden before the interrupt. Provider failure sets `failed`; deterministic no-trade sets `succeeded` with `main_action=no_trade` and an explicit evidence reason.

- [ ] **Step 4: Verify streaming contract**

`test_event_stream_contract.py` consumes both `agent.astream_events(..., version="v3")` and `graph.astream(..., stream_mode=["updates", "messages", "custom", "tasks"], subgraphs=True)`. It validates versioned `custom:task_progress`, `custom:artifact`, `custom:evidence`, `custom:usage`, `custom:notification` and `custom:quality` payloads without redefining official channels. Agent Server Protocol/OpenAPI contract coverage is completed in Task 8.

Run: `cd backend && uv run pytest tests/contract/test_analysis_request.py tests/contract/test_state_reducers.py tests/contract/test_execution_identity.py tests/contract/test_graph_topology.py tests/contract/test_terminal_states.py tests/contract/test_event_stream_contract.py tests/integration/test_interrupt_resume.py tests/integration/test_interrupt_namespaces.py tests/integration/test_atomic_interrupt_state_update.py tests/integration/test_interrupt_races.py tests/integration/test_interrupt_expiry.py tests/integration/test_edit_revalidation.py -q`

Expected: PASS with both official streaming APIs exercised; emitted custom payloads validate against versioned schemas and contain correlation/thread/task/run identifiers without a private SSE envelope.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: implement canonical analysis graph and hitl`

## Task 7: Product PostgreSQL, Alembic, Projections and Outbox

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/__init__.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/identity.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/execution.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/analysis.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/interrupts.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/commands.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/notifications.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/feedback.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/governance.py`
- Create: `backend/src/crypto_alert_v2/persistence/models/commerce.py`
- Create: `backend/src/crypto_alert_v2/persistence/unit_of_work.py`
- Create: `backend/src/crypto_alert_v2/persistence/retry_policy.py`
- Create: `backend/src/crypto_alert_v2/persistence/repositories.py`
- Create: `backend/src/crypto_alert_v2/projections/run_projection.py`
- Create: `backend/src/crypto_alert_v2/projections/reconciler.py`
- Create: `backend/src/crypto_alert_v2/commands/models.py`
- Create: `backend/src/crypto_alert_v2/commands/dispatcher.py`
- Create: `backend/src/crypto_alert_v2/notifications/outbox_worker.py`
- Create: `backend/src/crypto_alert_v2/notifications/webhook_worker.py`
- Create: `backend/src/crypto_alert_v2/notifications/retry_policy.py`
- Create: `backend/src/crypto_alert_v2/notifications/adapters.py`
- Create: `backend/src/crypto_alert_v2/workers/__init__.py`
- Create: `backend/src/crypto_alert_v2/workers/app.py`
- Create: `backend/src/crypto_alert_v2/workers/loops.py`
- Create: `backend/src/crypto_alert_v2/workers/health.py`
- Create: `backend/src/crypto_alert_v2/workers/__main__.py`
- Modify: `backend/src/crypto_alert_v2/graph/runtime.py`
- Modify: `backend/src/crypto_alert_v2/graph/nodes/persist_stage.py`
- Modify: `backend/src/crypto_alert_v2/graph/nodes/commit_artifact.py`
- Modify: `backend/src/crypto_alert_v2/graph/graph.py`
- Replace: `docker-compose.yml`
- Create: `docker/postgres-init.sql`
- Create: `backend/tests/integration/test_migrations.py`
- Create: `backend/tests/integration/test_database_role_isolation.py`
- Create: `backend/tests/integration/test_artifact_transaction.py`
- Create: `backend/tests/integration/test_progressive_stage_persistence.py`
- Create: `backend/tests/integration/test_outbox_idempotency.py`
- Create: `backend/tests/integration/test_outbox_manual_resend.py`
- Create: `backend/tests/integration/test_command_dispatcher.py`
- Create: `backend/tests/integration/test_cancel_task.py`
- Create: `backend/tests/integration/test_projection_reconciler.py`
- Create: `backend/tests/integration/test_reconciler_deadlines.py`
- Create: `backend/tests/integration/test_notification_worker.py`
- Create: `backend/tests/integration/test_worker_process_lifecycle.py`
- Create: `backend/tests/contract/test_persistence_delivery_retry_budgets.py`
- Create: `backend/tests/contract/test_domain_event_contract.py`
- Create: `tools/v2/probe_persistence.sh`
- Create: `artifacts/v2-final/migrations/.gitkeep`
- Create: `docs/v2/implementation/2026-07-13-task-07-persistence.md`

- [ ] **Step 1: Write migration and transaction tests**

```python
async def test_artifact_decision_and_outbox_commit_atomically(uow):
    async with uow:
        await uow.artifacts.add(valid_artifact())
        await uow.decisions.add(valid_decision())
        await uow.outbox.add(valid_notification())
        await uow.commit()
    assert await count_rows("artifacts") == 1
    assert await count_rows("decisions") == 1
    assert await count_rows("notification_outbox") == 1
```

Add a rollback test where the third insert fails and all counts remain zero.

`test_progressive_stage_persistence.py` commits market snapshot, search evidence, structured analysis, Evidence Verdict and Risk Verdict with stable stage idempotency keys, then injects a later failure and proves the already-paid successful stages remain queryable without producing a final success Artifact.

`test_migrations.py` asserts the initial revision creates every required Product DB entity: tenants, workspaces, users, external identities, memberships, agent threads, tasks, immutable run attempts, messages, subagent invocations, market snapshots, Web Evidence, artifacts, immutable artifact versions, decisions, interrupt inbox/projections, task commands, product event projections, retry-attempt ledger, observability links, notification outbox/attempts, feedback, outcomes, audit events, assignments, export/deletion/retention jobs, entitlements, usage ledger, subscription hooks and integrations. Ownership, visibility, lineage, foreign keys, uniqueness constraints, RLS/query indexes and immutable-version rules are part of the assertion.

`test_database_role_isolation.py` proves the Product role cannot read/write Agent Server checkpoint/store schemas and the Agent Server role cannot read/write Product tables. Local Compose may share one PostgreSQL process, but `docker/postgres-init.sql` must create separate databases and roles with no cross grants.

- [ ] **Step 2: Confirm the expected missing-persistence RED**

Run: `cd backend && uv run pytest tests/contract/test_persistence_delivery_retry_budgets.py tests/contract/test_domain_event_contract.py tests/integration/test_migrations.py tests/integration/test_database_role_isolation.py tests/integration/test_artifact_transaction.py tests/integration/test_progressive_stage_persistence.py tests/integration/test_outbox_idempotency.py tests/integration/test_outbox_manual_resend.py tests/integration/test_command_dispatcher.py tests/integration/test_cancel_task.py tests/integration/test_projection_reconciler.py tests/integration/test_reconciler_deadlines.py tests/integration/test_notification_worker.py tests/integration/test_worker_process_lifecycle.py -q`

Expected: FAIL during collection because persistence models, the migration revision, UnitOfWork or dispatcher are missing. Do not start Docker in RED; a connection-refused failure is not evidence that the persistence contract is missing.

- [ ] **Step 3: Implement schema, UnitOfWork and durable workers**

All user-owned tables include tenant/workspace ownership, actor attribution, timestamps and indexes. Foreign keys are real constraints. Run projection stores stable product fields, not full checkpoint snapshots.

`task_commands` records `command_id`, `task_id`, `thread_id`, actor, a Thread-global sequence, payload hash, status, lease owner/deadline, attempt, idempotency key and official run/command references. `CommandDispatcher` uses `thread_id` as the sole serialization lease key and creates a new immutable Run for submit, resume, retry, edit/regenerate and fork. Tests enqueue commands from two Tasks sharing one Thread and prove strict sequence with no concurrent checkpoint mutation; Scenario Compare uses a new lineage Thread. `cancel_run` cancels the selected active Run and preserves retry. `cancel_task` atomically marks the Task cancelled, rejects undispatched commands and fences dispatcher leases. The Product backend groups Product-owned pending/running Run IDs by Thread, skips empty groups and invokes exactly one locked Python SDK bulk cancellation per non-empty group with `await client.runs.cancel_many(thread_id=thread_id, run_ids=run_ids)`; it never cancels another Task sharing that Thread. The equivalent locked JavaScript SDK shape is `client.runs.cancelMany({ threadId, runIds })`, but the frontend calls Product cancellation APIs only and never invokes either SDK cancellation method directly.

Dispatcher ownership is fenced on both sides of remote Run creation: perform a pre-dispatch lease/fencing/cancellation check, create the official remote Run, then persist the returned official Run ID and Product ownership reference only while the same lease and Task state remain valid. If post-create registration loses the lease, observes Task cancellation or cannot commit the local reference, immediately issue a compensating official cancel for that newly created Run and persist the reconciliation outcome. Tests inject cancellation and lease loss before remote create, after remote create but before local reference commit, during the reference commit and immediately after it. They also prove shared-Thread isolation and that no unowned pending/running Agent Server Run survives any boundary. Duplicate, stale, unauthorized or interrupt-mismatched commands are rejected. The Agent Server transport remains an injected port until Task 8 supplies the official SDK adapter.

`ProjectionReconciler` compares public checkpoint/run observations with Product projection versions and repairs only supported inconsistencies; it never reads Agent Server internal tables. Run rows store `last_heartbeat_at`, `recovery_deadline_at`, official run/checkpoint IDs and recovery attempt count. Internal Alpha tests freeze heartbeat every 10 seconds, stale after 30 seconds, at most 2 automatic recoveries, 5-minute per-attempt deadline, RTO <= 10 minutes, RPO <= 30 seconds, running projection <= 5 seconds and terminal projection <= 2 seconds. The old Run retains a standard Run `status` while `recovery_status` moves `pending -> recovering -> superseded`; recovery creates a distinct immutable resume Run. Exhausted/expired recovery becomes `status=failed`, `failure_code=orphaned`. No recovery-only value is written into `status`, and no stale record remains permanently `running`.

`test_domain_event_contract.py` requires exactly `market.snapshot.committed`, `research.evidence.committed`, `agent.output.committed`, `evidence.verdict.committed`, `risk.verdict.committed`, `artifact.committed`, `notification.planned` and `run.terminal`. Every envelope contains event/task/run/checkpoint IDs, schema version, payload ref/hash, Thread-global sequence and timestamp; full recoverable payload lives in Product DB/Object Storage while Graph state keeps IDs/summaries.

`OutboxWorker` claims rows with owner/expiry/fencing-token leases and exact unique logical key `(workspace_id, task_id, channel, type, decision_version)`, records every attempt and delegates to Bark/Web Push/Email adapters. Same key/different payload is an audited conflict; uncertain delivery becomes `unknown` and is not automatically resent. Manual resend creates a new attempt under the same logical notification/audit chain. Graph nodes do not send notifications directly.

`python -m crypto_alert_v2.workers` is the single process entrypoint for command-dispatch, projection-reconciliation, notification and webhook lease loops. It exposes worker liveness/readiness, installs TERM/INT handlers, stops claiming new leases, finishes or releases in-flight leases with fencing, and exits within the shutdown budget. `test_worker_process_lifecycle.py` kills/restarts the process and proves pending durable work resumes once without duplicate side effects.

The remaining numerical retry contract is exact: PostgreSQL retries only serialization/deadlock failures, at most 2 attempts and 5 seconds total; Notification Outbox uses at most 5 attempts with exponential backoff and reaches terminal/`unknown` after 24 hours; Webhook uses at most 5 attempts then writes a DLQ record. Every attempt records owner, reason, delay, Retry-After, cost and result. Tests prove non-retryable database failures execute once and no lower-level SDK multiplies these budgets.

Wire the concrete Product UnitOfWork into the typed runtime assembly. `persist_stage.py` performs one idempotent Product transaction per paid stage and writes the matching `product_event_projection`; `commit_artifact.py` performs the single ArtifactVersion + Decision + notification-planned transaction. Integration tests invoke the canonical graph with the real runtime assembly, not repositories in isolation.

The Compose file in this task contains only V2 PostgreSQL and Redis foundations plus explicit health checks. It must not start the V1 scheduler/API/frontend services.

- [ ] **Step 4: Start foundations and verify migrations/workers**

Run: `./tools/v2/probe_persistence.sh`

`probe_persistence.sh` installs its cleanup trap first, starts a unique PostgreSQL/Redis Compose project, waits for health, runs upgrade/downgrade/upgrade, starts the real worker process, executes every Task 7 contract/integration test including worker restart, writes migration evidence, then stops workers and foundations on success or failure.

Expected: PostgreSQL and Redis become healthy; upgrade/downgrade/upgrade succeeds; all persistence and worker tests pass; the migration evidence records revision `0001_initial` without credentials.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: add product persistence and notification outbox`

## Task 8: Product APIs and Agent Server Integration

**Files:**
- Create: `backend/src/crypto_alert_v2/api/app.py`
- Create: `backend/src/crypto_alert_v2/api/dependencies.py`
- Create: `backend/src/crypto_alert_v2/api/routes/runs.py`
- Create: `backend/src/crypto_alert_v2/api/routes/inbox.py`
- Create: `backend/src/crypto_alert_v2/api/routes/commands.py`
- Create: `backend/src/crypto_alert_v2/api/routes/workspaces.py`
- Create: `backend/src/crypto_alert_v2/api/routes/feedback.py`
- Create: `backend/src/crypto_alert_v2/api/routes/system.py`
- Create: `backend/src/crypto_alert_v2/agent_server/client.py`
- Modify: `backend/langgraph.json`
- Create: `backend/tests/contract/test_api_schemas.py`
- Create: `backend/tests/contract/test_agent_server_protocol.py`
- Create: `backend/tests/contract/test_protocol_v2_capabilities.py`
- Create: `backend/tests/integration/test_run_durability.py`
- Create: `backend/tests/integration/test_runs_api.py`
- Create: `backend/tests/integration/test_inbox_api.py`
- Create: `backend/tests/integration/test_commands_api.py`
- Create: `backend/tests/integration/test_agent_server_interrupt_routing.py`
- Create: `backend/tests/integration/test_workspaces_api.py`
- Create: `backend/tests/integration/test_feedback_api.py`
- Create: `tools/v2/probe_product_api.sh`
- Create: `tools/v2/probe_protocol_v2.mjs`
- Create: `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-checkpoints.md`
- Create: `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-state-fork.md`
- Create: `docs/v2/implementation/2026-07-13-task-08-api.md`

- [ ] **Step 1: Write tenant-scoped API tests**

Test workspace membership/list/switch authorization, run list/detail, interrupt inbox, feedback, command admission, `cancel_run`, `cancel_task`, health/readiness and cross-tenant 404 behavior. Product endpoints use `/app/*` and do not shadow Agent Server system routes. `test_agent_server_protocol.py` loads the live Agent Server OpenAPI schema and asserts official assistants/threads/runs plus `POST /threads/{thread_id}/commands` and `POST /threads/{thread_id}/stream/events`; Product additions do not redefine them. Method-specific Protocol-shaped `run.start`, `input.respond` and batch respond validate against locked schemas. The compatibility test proves Protocol 0.0.18 types declare `state.fork` while Agent Server 0.11.0 returns `unknown_command`; Product fork admission must therefore map a checkpoint to a new official Run, not send `state.fork`. React/JS `forkFrom` becomes Protocol `config.configurable.checkpoint_id`, but the Python `langgraph-sdk==0.4.2` Runs client requires the separate keyword-only `checkpoint_id=`. The dispatcher explicitly lifts the admitted config value and calls `await client.runs.create(thread_id, assistant_id, input=run_input, checkpoint_id=checkpoint_id, durability="sync", metadata=metadata)`; the outbound Runs REST JSON must contain top-level `"checkpoint_id"`. Retaining the config value for correlation is optional and cannot replace the top-level argument. Likewise Protocol `run.start` has no `durability` field. Resume uses the official `command={"resume": ..., "update": ..., "goto": ...}` parameter. Tests prove `sync` and `exit` are expressible and server-effective through the Runs API adapter, never inside Protocol params. Cancellation validates against Product schemas and official `langgraph-sdk` Runs cancel APIs because it is not in the Protocol v2 Command union. Write the hermetic `probe_product_api.sh` harness in this step so RED can start foundations/integration runtime and assert test failures rather than connection failures.

`probe_protocol_v2.mjs` opens a real stream with the React root channel set including `checkpoints`, submits single and batched interrupt responses, verifies the locked `state.fork` rejection, reconnects with `since`, and proves replay/ordering. `test_agent_server_interrupt_routing.py` runs root and approved nested-subagent interrupts through the live Product admission and Agent Server paths, verifies namespace/checkpoint preservation, atomic respond-plus-allowed-state-update, restart replay and one-winner idempotency. `test_run_durability.py` creates `sync` and `exit` Runs through Product admission and the official Runs REST adapter, waits for committed state, restarts the integration Agent Server, reconnects and resumes the same Thread without losing the acknowledged Product/runtime state. The Product API returns Protocol-shaped success data expected by `AgentServerAdapter.send()` even though dispatch uses Runs REST internally. Both known Protocol/OpenAPI exceptions are accepted only if live capability probes pass and their exception documents record affected versions, validator rules, regression tests and removal conditions.

- [ ] **Step 2: Confirm failures**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_api_schemas.py tests/integration/test_workspaces_api.py tests/integration/test_runs_api.py tests/integration/test_inbox_api.py tests/integration/test_feedback_api.py tests/integration/test_commands_api.py -q)
./tools/v2/probe_product_api.sh --expect-contract-failure
```

Expected: the pure locked Agent Server route/channel/type assertions pass as prerequisite capability checks, while Task 8-owned assertions fail because Product custom-route non-shadowing, explicit durability admission, live interrupt routing and the official SDK client adapter are missing. In `--expect-contract-failure` mode the probe starts a healthy integration server, executes `test_agent_server_protocol.py`, `test_protocol_v2_capabilities.py`, `test_agent_server_interrupt_routing.py`, `test_run_durability.py` and `probe_protocol_v2.mjs`, and requires the failing assertions to name an unmet Product integration contract rather than collection failure, connection refusal or process-start failure. Do not manufacture a failure in an already-supported official capability merely to obtain RED.

- [ ] **Step 3: Implement custom app and explicit AuthZ**

Every route resolves ActorContext first, then applies repository ACL filters. Success and error envelopes have Pydantic schemas and correlation IDs. `agent_server/client.py` is the only Product API adapter that invokes the official `langgraph-sdk`; it implements the port consumed by `CommandDispatcher` and never calls private Agent Server tables or endpoints.

- [ ] **Step 4: Start the integration Agent Server and probe real HTTP routes**

Run: `./tools/v2/probe_product_api.sh`

`probe_product_api.sh` installs its cleanup trap before any process, starts its own unique PostgreSQL/Redis foundations, applies Product migrations, starts the worker process and locked container integration runtime with `langgraph up`, records all project identifiers, waits for readiness, downloads `/openapi.json`, probes `/app/system/readiness`, runs the protocol/durability probes plus workspace/run/inbox/feedback/command Product API tests, restarts Agent Server for the durability test, and tears down every owned process/container even on failure. It never depends on Task 7 leftovers. `langgraph dev` remains only the Task 1 development smoke test. Expected: official protocol v2 routes, explicit `sync`/`exit` durability, root channels, single/batch commands, replay, restart recovery and all Product routes pass against the integration topology.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: expose tenant-scoped product api`

## Task 9: LangSmith, Langfuse and Secret-Safe Observability

**Files:**
- Create: `backend/src/crypto_alert_v2/observability/config.py`
- Create: `backend/src/crypto_alert_v2/observability/callbacks.py`
- Create: `backend/src/crypto_alert_v2/observability/logging.py`
- Create: `backend/src/crypto_alert_v2/observability/redaction.py`
- Create: `backend/src/crypto_alert_v2/observability/tenant_policy.py`
- Create: `backend/src/crypto_alert_v2/evaluation/dataset.py`
- Create: `backend/src/crypto_alert_v2/evaluation/experiment.py`
- Create: `backend/src/crypto_alert_v2/evaluation/release_gate.py`
- Modify: `backend/src/crypto_alert_v2/agents/market_analysis.py`
- Modify: `backend/src/crypto_alert_v2/agents/research.py`
- Create: `backend/tests/contract/test_observability_assembly.py`
- Create: `backend/tests/integration/test_observability_cardinality.py`
- Create: `backend/tests/integration/test_observability_outage.py`
- Create: `backend/tests/contract/test_langsmith_release_gate.py`
- Create: `backend/tests/contract/test_observability_tenant_policy.py`
- Create: `backend/tests/real/test_real_langsmith_experiment.py`
- Create: `backend/tests/security/test_secret_redaction.py`
- Create: `backend/tests/real/test_real_observability.py`
- Create: `artifacts/v2-final/observability/.gitkeep`
- Create: `docs/v2/implementation/2026-07-13-task-09-observability.md`

- [ ] **Step 1: Write assembly and canary tests**

Inject synthetic API keys into model input, tool output, logs and trace metadata. Assert no raw canary appears in serialized events or captured logs. Tenant-policy tests cover anonymous Langfuse user IDs, sensitive-tenant I/O suppression or full tracing disable, async/non-blocking delivery, configurable sampling after the initial full-capture period, 30-day default retention, and mandatory preservation of failed/blocked/negative-feedback/release-proof traces. Cardinality tests create direct model, retry, resume and Tool-internal model attempts, persist `observability_links`, and require exactly one LangSmith LLM child plus one Langfuse generation per stable model call ID, with separate IDs and correct retry/resume lineage. Outage tests independently fail LangSmith and Langfuse delivery, prove the business result remains semantically correct, and require a redacted local structured event containing provider, correlation ID, retry state, dropped/sampled status and alert fingerprint. LangSmith release tests create the minimum dataset cases `normal/missing/stale/conflict/model_error/notification_error`, run a repeatable offline Experiment, and gate structure, evidence, risk and product-output metrics with Prompt/Git version linkage.

- [ ] **Step 2: Confirm failures**

Run: `cd backend && REAL_OBSERVABILITY_TESTS=1 uv run pytest tests/contract/test_observability_assembly.py tests/contract/test_observability_tenant_policy.py tests/contract/test_langsmith_release_gate.py tests/integration/test_observability_cardinality.py tests/integration/test_observability_outage.py tests/security/test_secret_redaction.py tests/real/test_real_observability.py tests/real/test_real_langsmith_experiment.py -q`

Expected: FAIL because callback assembly/redaction does not exist or because the synthetic canary leaks through at least one serialized boundary. Disabling assertions when observability credentials are absent is not an acceptable RED result for local redaction tests.

- [ ] **Step 3: Implement centralized callbacks**

LangSmith uses automatic tracing. Langfuse creates one handler per invocation. Both receive correlation/thread/task/run/user IDs through framework config, not manual generation calls in nodes. Observability delivery runs outside the business transaction and cannot change a valid domain result into failure, but every exhausted delivery writes the required structured local event and emits the alert fingerprint consumed by Task 14 production alert rules.

- [ ] **Step 4: Run real trace proof**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_observability_assembly.py tests/contract/test_observability_tenant_policy.py tests/contract/test_langsmith_release_gate.py tests/integration/test_observability_cardinality.py tests/integration/test_observability_outage.py tests/security/test_secret_redaction.py -q)
(cd backend && REAL_OBSERVABILITY_TESTS=1 uv run pytest tests/real/test_real_observability.py tests/real/test_real_langsmith_experiment.py -q -s)
```

Expected: tests write secret-safe trace/call IDs, Dataset ID, Experiment result, outage structured-log hashes/alert fingerprints and release report under `artifacts/v2-final/observability/`, verify both platforms contain the same correlation ID and exactly one matching child/generation per model call ID, and print no prompt, provider payload or credential.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: integrate langsmith and langfuse observability`

## Task 10: Frontend Runtime, BFF and Product View Models

**Files:**
- Replace: `frontend/package.json`
- Replace: `frontend/package-lock.json`
- Create: `frontend/.nvmrc`
- Modify: `frontend/next.config.ts`
- Create: `frontend/src/auth.ts`
- Create: `frontend/src/middleware.ts`
- Create: `frontend/src/app/api/auth/[...nextauth]/route.ts`
- Create: `frontend/src/app/api/agent/[...path]/route.ts`
- Create: `frontend/src/app/api/product/[...path]/route.ts`
- Create: `frontend/src/app/sign-in/page.tsx`
- Create: `frontend/src/lib/auth/internal-token.ts`
- Create: `frontend/src/lib/auth/session-context.ts`
- Create: `frontend/src/features/agent-runtime/use-agent-thread.ts`
- Create: `frontend/src/features/agent-runtime/product-command-adapter.ts`
- Create: `frontend/src/features/agent-runtime/projection-ownership.ts`
- Create: `frontend/src/features/agent-runtime/durable-submission-queue.ts`
- Create: `frontend/src/features/agent-runtime/contracts.ts`
- Create: `frontend/src/lib/schemas/analysis.ts`
- Create: `frontend/src/lib/schemas/product-api.ts`
- Create: `frontend/src/lib/api/product-client.ts`
- Create: `frontend/tests/unit/dependency-contract.test.ts`
- Create: `frontend/tests/unit/auth-contract.test.ts`
- Create: `frontend/tests/unit/command-admission-contract.test.ts`
- Create: `frontend/tests/unit/projection-ownership.test.ts`
- Create: `frontend/tests/unit/runtime-contract.test.ts`
- Replace: `frontend/playwright.config.ts`
- Replace: `frontend/tests/e2e/global-teardown.ts`
- Create: `frontend/tests/e2e/runtime-smoke.spec.ts`
- Create: `backend/src/crypto_alert_v2/testing/fixture_providers.py`
- Create: `backend/src/crypto_alert_v2/testing/scenario_control.py`
- Create: `backend/src/crypto_alert_v2/api/routes/test_control.py`
- Create: `backend/tests/contract/test_fixture_profile.py`
- Create: `tools/v2/profiles/fixture.env`
- Create: `tools/v2/process_lib.sh`
- Create: `tools/v2/start_stack.sh`
- Create: `tools/v2/stop_stack.sh`
- Create: `tools/v2/verify_stack.sh`
- Create: `artifacts/v2-final/playwright/.gitkeep`
- Create: `docs/v2/implementation/2026-07-13-task-10-frontend-runtime.md`

- [ ] **Step 1: Write TypeScript contract tests**

`dependency-contract.test.ts` asserts the exact locked frontend group and Node 22, including `react-markdown@10.1.0` and `rehype-sanitize@6.0.0`. `auth-contract.test.ts` proves the Auth/OIDC/internal-JWT contract plus invite-only Internal Alpha: no public registration route/link, no External Beta selection without accepted governance IDs, and no browser-visible exchange private credential or trade/transfer capability. `command-admission-contract.test.ts` proves Protocol commands emit nothing before Product commit; `cancel_run` and `cancel_task` call same-origin Product APIs only. The backend commits cancellation admission before invoking the official Runs API; for `cancel_task` it atomically terminalizes the Task, rejects undispatched commands, groups Product-owned pending/running Run IDs by Thread, skips empty groups and calls `await client.runs.cancel_many(thread_id=thread_id, run_ids=run_ids)` once per non-empty group without touching another Task sharing the Thread. Tests assert that frontend code never calls Python `cancel_many`, JavaScript `client.runs.cancelMany({ threadId, runIds })`, direct `useStream.stop()` or `multitaskStrategy="enqueue"`. An active-run submit creates Product `task_commands` immediately, survives remount, and dispatches once only when the Thread is available. `projection-ownership.test.ts` covers hydration, reconnect and projection lag, including stale Checkpoint interrupts after cancellation/resolution; controls remain disabled unless Product says the exact interrupt projection is unresolved/actionable. Runtime tests reject unknown Graph State, malformed interrupt and missing correlation ID. No SDK boundary uses `as any`.

Before RED, create the Playwright/process/profile **test harness scaffolding**: replace the config/teardown, define `fixture-desktop`/`fixture-pixel-7` with exact `testMatch`, and provide startup/cleanup scripts that boot the already-green Task 9 integration stack without fixture adapters or Task 10 product behavior. The harness must reach healthy services and collect `runtime-smoke.spec.ts`; the test then fails on a named missing BFF/root-runtime/UI assertion. Fixture providers, scenario control and production behavior remain unimplemented until Step 3.

- [ ] **Step 2: Install exact versions and verify failing tests**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_fixture_profile.py -q)
cd frontend
npm ci
npm run typecheck
npm run test:unit
npm run test:e2e -- runtime-smoke.spec.ts --project=fixture-desktop
```

Expected: FAIL on the first inherited/missing exact dependency or because runtime schemas, BFF and the root stream hook do not exist. Unknown Playwright project, zero collected tests, skip/deselection, unhealthy stack or `npm ci` failure caused by an intentionally inconsistent lockfile is not accepted as RED.

- [ ] **Step 3: Implement same-origin BFF and one root stream**

Auth.js uses a standard OIDC provider in production and a separately gated development provider only outside production. Both BFF proxies require a server-side session, resolve an allowed workspace membership and sign a rotating-key, short-lived internal JWT for backend calls; the browser never receives model/provider credentials or chooses authority claims. Browser reads/events connect through same-origin `/api/agent`; Product history and command admission use `/api/product`. `product-command-adapter.ts` implements the official `AgentServerAdapter` structural contract: `openEventStream/getState/getHistory` delegate to the Agent Server proxy, while durable command `send()` paths first call Product command admission and return only the official dispatched response. Admitted fork never emits the unsupported Protocol `state.fork`; React `submit(input, { forkFrom: checkpointId })` semantics are normalized into Product admission with the selected checkpoint. The backend lifts `config.configurable.checkpoint_id` to the Python Runs REST client's top-level `checkpoint_id=` argument and creates a new lineage Run; frontend code never sends `forkFrom` to the Python client. History reads use the official Thread history API. The root product hook exposes `threadId`, admitted submit/respond/respondAll/cancelRun/cancelTask/fork/retry, disconnect, pending interrupts and named live execution fields; it does not expose direct `stop()`, SDK `multitaskStrategy="enqueue"` or the entire raw Graph state. When a Run is active, `durable-submission-queue.ts` writes the next submit to Product command admission immediately and waits for the backend dispatcher instead of invoking the SDK-local in-memory queue. Product components consume typed selectors/View Models.

Complete the pre-RED Playwright harness with deterministic V2-only market/search/model/notification adapters and a test-only scenario-reset route that is impossible to register outside `local/test`. The V2 config starts PostgreSQL, Redis, Agent Server, workers and Next.js through `tools/v2/start_stack.sh`; it must never invoke `tools/local_stack` or seed V1 SQLite data.

`start_stack.sh` uses `process_lib.sh` to create a per-run PID directory, installs `EXIT/INT/TERM` traps before spawning children, starts Docker foundations, migrations, `python -m crypto_alert_v2.workers`, the locked `langgraph up` integration runtime and Next.js. It records the worker PID/process group, probes worker readiness, kills/restarts it once in the fixture smoke test to prove durable recovery, then remains in the foreground with `wait`. `stop_stack.sh` is idempotent, terminates only recorded PIDs/process groups/Compose projects, waits for exit and removes the PID directory. Playwright `global-teardown.ts` always invokes `stop_stack.sh`; the same cleanup runs when startup, tests or the parent process fail.

- [ ] **Step 4: Verify build without bypasses**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_fixture_profile.py -q)
cd frontend
npm run lint
npm run typecheck
npm run test:unit
npm run build
npm run test:e2e -- runtime-smoke.spec.ts --project=fixture-desktop
if rg -n "as any|localhost:2024|JSON.stringify\(values|stream\.values|stream\.stop\(|multitaskStrategy.*enqueue" src; then exit 1; fi
```

Expected: all commands pass, Playwright artifacts are written under `artifacts/v2-final/playwright/`, and the forbidden-pattern scan returns no matches.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: add typed frontend agent runtime and bff`

## Task 11: Work, Runs, Inbox, Library and Responsive Product UI

**Files:**
- Replace: `frontend/src/app/page.tsx`
- Create/Replace: `frontend/src/app/home/page.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Replace: `frontend/src/app/error.tsx`
- Replace: `frontend/src/app/loading.tsx`
- Replace: `frontend/src/app/not-found.tsx`
- Create/Replace: `frontend/src/app/work/page.tsx`
- Create/Replace: `frontend/src/app/runs/page.tsx`
- Delete before creating the new dynamic route: `frontend/src/app/runs/[traceId]/`
- Create/Replace: `frontend/src/app/runs/[runId]/page.tsx`
- Create/Replace: `frontend/src/app/inbox/page.tsx`
- Create/Replace: `frontend/src/app/library/page.tsx`
- Create/Replace: `frontend/src/app/settings/page.tsx`
- Create: `frontend/src/components/app-shell.tsx`
- Create: `frontend/src/components/primary-navigation.tsx`
- Create: `frontend/src/components/workspace-switcher.tsx`
- Create: `frontend/src/features/home/watchlist.tsx`
- Create: `frontend/src/features/home/active-work.tsx`
- Create: `frontend/src/features/home/recent-reports.tsx`
- Create: `frontend/src/features/work/work-mode-control.tsx`
- Create: `frontend/src/features/analysis/analysis-view-model.ts`
- Create: `frontend/src/features/analysis/artifact-adapter.ts`
- Create: `frontend/src/features/analysis/analysis-result.tsx`
- Create: `frontend/src/features/analysis/trade-plan.tsx`
- Create: `frontend/src/features/analysis/progress-timeline.tsx`
- Create: `frontend/src/features/evidence/evidence-view-model.ts`
- Create: `frontend/src/features/evidence/evidence-list.tsx`
- Create: `frontend/src/features/evidence/evidence-source.tsx`
- Create: `frontend/src/features/interrupts/interrupt-contract.ts`
- Create: `frontend/src/features/interrupts/interrupt-review-panel.tsx`
- Create: `frontend/src/features/interrupts/interrupt-actions.tsx`
- Create: `frontend/src/features/runs/run-view-model.ts`
- Create: `frontend/src/features/runs/run-list.tsx`
- Create: `frontend/src/features/runs/run-detail.tsx`
- Create: `frontend/src/features/runs/run-status-badge.tsx`
- Create: `frontend/src/features/runs/checkpoint-history.tsx`
- Create: `frontend/src/features/library/artifact-library.tsx`
- Create: `frontend/src/features/library/artifact-library-view-model.ts`
- Create: `frontend/src/features/agent-runtime/safe-tool-card.tsx`
- Create: `frontend/src/features/notifications/notification-status.tsx`
- Create: `frontend/src/features/feedback/feedback-control.tsx`
- Create: `frontend/src/features/content/safe-markdown.tsx`
- Create: `frontend/src/features/reasoning/reasoning-panel.tsx`
- Create: `frontend/src/features/attachments/attachment-renderer.tsx`
- Create: `frontend/src/lib/schemas/versioned-view-model.ts`
- Create: `frontend/src/app/globals.css`
- Create: `frontend/tests/unit/interrupt-contract.test.ts`
- Create: `frontend/tests/unit/view-model-compat.test.ts`
- Create: `frontend/tests/unit/content-safety.test.ts`
- Create: `frontend/tests/unit/time-travel-contract.test.ts`
- Create: `frontend/tests/e2e/product-ui.spec.ts`
- Create: `frontend/tests/e2e/accessibility.spec.ts`
- Create: `frontend/tests/e2e/mobile-depth.spec.ts`
- Create: `docs/v2/implementation/2026-07-13-task-11-product-ui.md`

- [ ] **Step 1: Write Playwright product assertions before UI implementation**

Cover desktop and Pixel 7. Assert:

- Home shows real BTC/ETH/SOL Watchlist, active Tasks, pending Inbox work and recent reports; Work remains the default direct action screen.
- Work has explicit Chat/Analysis segmented modes and user-scoped Thread/Task lists.
- Signed-out users are redirected to Sign In; signed-in users can switch only among workspaces returned by their membership API.
- Internal Alpha UI is invite-only: it exposes no public registration, marketing/public-share mode, automatic trading, order/cancel/transfer/withdraw control, private exchange credential form or unsupported financial-performance claim.
- No raw JSON or engineering labels appear in normal mode.
- Analysis result includes action, reference, entry, stop, targets, probability, evidence and risk.
- HITL buttons exist only while an interrupt is pending.
- HITL buttons require a nonterminal Product Task, Product Run `waiting_human`, an unresolved Product projection and a matching live interrupt tuple; stale hydration after cancel/resolve never re-enables them.
- Cancel Run preserves Task history and enables Retry; Cancel Task cancels the active Run, marks the Task cancelled and prevents further generation.
- Approve/reject/edit submit the exact pending interrupt ID; a stale ID is rejected and cannot mutate UI state.
- Multiple simultaneous interrupts render independently and call the locked `stream.respondAll(responsesById)` API through `ProductCommandAdapter` in one admitted resume command; sequential `respond()` calls are forbidden for the same checkpoint.
- Runs and Inbox survive page reload.
- Library lists persisted Artifact versions from Product API and deep-links to their Task/Run without static arrays.
- Notification delivery/attempt state and user feedback are visible and persisted.
- Checkpoint history/time travel is read-only through official history APIs and cannot mutate canonical Product history without an admitted fork.
- Markdown is sanitized; dangerous HTML/URLs are rejected. Reasoning is typed, collapsed by default and labeled as a summary rather than chain-of-thought. Image/audio/video/file attachments render loading/error/unsupported degradation.
- No horizontal clipping or overlapping controls at 412px.
- Current and previous-minor View Model schemas render directly; missing optional fields show local unknown/skeleton states and missing critical fields show a readable incomplete-result state without hiding valid Evidence.
- Unknown Tool output renders a safe name/status/time/redacted-summary card; unknown Generative UI components fall back to the Artifact summary and never execute arbitrary JSX.
- Mobile tests cover Chinese IME composition, safe areas, 44px targets, portrait/landscape, deep scrolling, offline/reconnect and stable back navigation.
- Accessibility tests cover axe, keyboard-only flows, focus restore after Interrupt, throttled live regions, reduced motion, non-color-only statuses and text alternatives for charts/ranges.

- [ ] **Step 2: Run tests and observe failure**

Run:

```bash
(cd frontend && npm run test:unit -- interrupt-contract.test.ts view-model-compat.test.ts content-safety.test.ts time-travel-contract.test.ts)
(cd frontend && npm run test:e2e -- product-ui.spec.ts accessibility.spec.ts --project=fixture-desktop)
(cd frontend && npm run test:e2e -- mobile-depth.spec.ts --project=fixture-pixel-7)
```

Expected: FAIL because the V2 Work/Runs/Inbox/Library pages, error/loading/not-found states and product View Models do not exist, or because inherited pages expose raw JSON/static data and V1 links. A RED caused only by an unavailable backend is invalid; the fixture projects must reach the V2 stack first.

- [ ] **Step 3: Implement product pages**

Reuse presentation components only after adapting them to the new View Model. Remove static arrays and debug pages from navigation. Use icons for tools, tabs for views, and stable responsive dimensions.

- [ ] **Step 4: Run DOM and visual checks**

Run:

```bash
(cd frontend && npm run test:unit -- interrupt-contract.test.ts)
(cd frontend && npm run test:unit -- view-model-compat.test.ts)
(cd frontend && npm run test:unit -- content-safety.test.ts time-travel-contract.test.ts)
(cd frontend && npm run test:e2e -- product-ui.spec.ts accessibility.spec.ts --project=fixture-desktop)
(cd frontend && npm run test:e2e -- product-ui.spec.ts mobile-depth.spec.ts --project=fixture-pixel-7)
```

Playwright captures console/network failures, full-page screenshots and a DOM audit that checks viewport overflow, overlapping interactive controls, clipped text, invisible focus, unnamed controls and raw JSON blocks. Compare screenshots only after dynamic IDs/timestamps are masked. Store the automated accessibility report and a VoiceOver walkthrough transcript under `artifacts/v2-final/playwright/`. Expected: unit and both browser projects pass; no unexpected console/network errors, axe violations or DOM violations are reported.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `feat: deliver responsive agent workspace ui`

## Task 12: Full Real-Environment E2E and Failure Injection

**Files:**
- Create: `frontend/tests/e2e/real-analysis-flow.spec.ts`
- Create: `frontend/tests/e2e/hitl-recovery.spec.ts`
- Create: `frontend/tests/e2e/cross-tenant-security.spec.ts`
- Create: `frontend/tests/e2e/provider-failures.spec.ts`
- Create: `frontend/tests/e2e/notification-delivery.spec.ts`
- Create: `frontend/tests/e2e/visual-regression.spec.ts`
- Modify: `frontend/playwright.config.ts`
- Modify: `frontend/tests/e2e/global-teardown.ts`
- Modify: `tools/v2/start_stack.sh`
- Modify: `tools/v2/stop_stack.sh`
- Modify: `tools/v2/verify_stack.sh`
- Create: `backend/src/crypto_alert_v2/testing/failure_injection.py`
- Create: `backend/tests/contract/test_failure_injection_profile.py`
- Create: `tools/v2/profiles/real-provider.env`
- Create: `tools/v2/profiles/failure-injection.env`
- Modify: `docker-compose.yml`
- Create: `artifacts/v2-final/test-logs/.gitkeep`
- Create: `docs/v2/implementation/2026-07-13-task-12-e2e.md`

- [ ] **Step 1: Write real-flow and failure tests**

The default real analysis test submits one BTC request with development `review_policy=bypass`, observes market/search/model stages, validates and persists the rendered artifact without blocking on Interrupt, verifies history and matches correlation IDs. The same Run must produce a real Bark provider delivery receipt plus its In-app Inbox record; `notification-delivery.spec.ts` separately proves a real Web Push or Email delivery/receipt so Bark is not the sole formal channel. All receipts bind provider attempt, correlation, task, run and artifact IDs and reject fixture adapters. `hitl-recovery.spec.ts` explicitly forces `review_policy=required` and covers approve, reject, edit, expire, refresh recovery and cancellation.

As test harness scaffolding before RED, add the `real-provider-desktop`/`real-provider-pixel-7` and `failure-injection-desktop`/`failure-injection-pixel-7` Playwright projects, isolated profile env files and startup selection. They boot the healthy Task 11 stack; real-provider projects use existing real adapters, while failure-injection projects start without the still-missing scenario control. Every named test must collect and execute; RED comes from missing end-to-end persistence/receipt/recovery/failure-control assertions, not an unknown project or startup failure.

- [ ] **Step 2: Confirm missing-profile and missing-flow RED**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_failure_injection_profile.py -q)
(cd frontend && npm run test:e2e -- real-analysis-flow.spec.ts notification-delivery.spec.ts hitl-recovery.spec.ts cross-tenant-security.spec.ts visual-regression.spec.ts --project=real-provider-desktop)
(cd frontend && npm run test:e2e -- provider-failures.spec.ts visual-regression.spec.ts --project=failure-injection-desktop)
```

Expected: FAIL on named missing persisted-flow, notification, HITL recovery, cross-tenant, visual or failure-injection assertions. Unknown project, zero collection, unhealthy stack, connection-only failure or credential skip is invalid when the corresponding project was explicitly selected.

- [ ] **Step 3: Extend the V2 stack and add failure injection**

Complete the pre-RED real/failure projects with the failure-injection implementation. Each project keeps exact `testMatch`, profile env and an isolated Compose project. Failure scenarios are controlled through the test-only scenario API and reset before each test; the route/profile fail startup outside `local/test`. Release proof uses both real-provider projects; fixture tests cannot satisfy real-provider gates.

Explicitly test OKX 500/timeout, search unavailable, model invalid structured output, database rollback, Bark/Web Push-or-Email notification failure, LangSmith unavailable and Langfuse unavailable. Provider/model/database failures end as `failed`. Notification or observability failures may end as `succeeded` only with explicit warnings and an incomplete `completion_scope`; neither is a separate Run terminal status. Each observability outage also proves a redacted structured local log with correlation/retry state and the matching alert fingerprint; Task 14 later proves the production alert rule fires. No scenario may show generic success.

Against a live Agent Server and Product command dispatcher, `hitl-recovery.spec.ts` also submits a stale interrupt ID, races two responses for the same `(interrupt_id, checkpoint_id, response_version)`, and resolves simultaneous interrupts with one `respondAll()` call. It asserts one winner, `INTERRUPT_ALREADY_RESOLVED` for the loser, namespace/checkpoint matching and one immutable resume Run.

- [ ] **Step 4: Run the full verification matrix**

```bash
./tools/v2/verify_stack.sh
(cd backend && uv run pytest -q --cov=crypto_alert_v2 --cov-report=term-missing)
(cd frontend && npm run lint && npm run typecheck && npm run test:unit && npm run build)
(cd frontend && npm run test:e2e -- --project=fixture-desktop --project=fixture-pixel-7)
(cd frontend && npm run test:e2e -- --project=real-provider-desktop --project=real-provider-pixel-7)
(cd frontend && npm run test:e2e -- --project=failure-injection-desktop --project=failure-injection-pixel-7)
```

Expected: zero failures, no browser console errors, no failed network requests outside injected scenarios, desktop/mobile screenshots accepted, real Bark plus Web Push-or-Email receipts are stored, and all real provider proof fields are populated under `artifacts/v2-final/provider-proof/`; command logs and observability-outage alert/log hashes are stored under `artifacts/v2-final/test-logs/` with secrets redacted.

- [ ] **Step 5: Create the candidate commit, run both reviews, then attest**

Commit: `test: verify v2 full stack and failure semantics`

## Task 13: Deep Research, Background Runs and Data Lifecycle

**Files:**
- Create: `backend/src/crypto_alert_v2/graph/research_subgraph.py`
- Create: `backend/src/crypto_alert_v2/graph/nodes/monitor_ingress.py`
- Create: `backend/src/crypto_alert_v2/agents/research_harness_selection.py`
- Create: `backend/src/crypto_alert_v2/api/routes/tasks.py`
- Create: `backend/src/crypto_alert_v2/api/routes/lifecycle.py`
- Create: `backend/src/crypto_alert_v2/api/routes/outcomes.py`
- Create: `backend/src/crypto_alert_v2/persistence/task_repository.py`
- Create: `backend/src/crypto_alert_v2/lifecycle/retention.py`
- Create: `backend/src/crypto_alert_v2/lifecycle/export.py`
- Create: `backend/src/crypto_alert_v2/lifecycle/deletion.py`
- Create: `backend/src/crypto_alert_v2/lifecycle/outcomes.py`
- Create: `backend/src/crypto_alert_v2/memory/service.py`
- Create: `backend/src/crypto_alert_v2/memory/policy.py`
- Create: `backend/src/crypto_alert_v2/api/routes/memory.py`
- Create: `backend/src/crypto_alert_v2/monitors/models.py`
- Create: `backend/src/crypto_alert_v2/monitors/service.py`
- Create: `backend/src/crypto_alert_v2/monitors/agent_server_cron.py`
- Create: `backend/src/crypto_alert_v2/commerce/entitlements.py`
- Create: `backend/src/crypto_alert_v2/commerce/usage.py`
- Create: `backend/src/crypto_alert_v2/commerce/reconciler.py`
- Create: `backend/src/crypto_alert_v2/integrations/webhook_signing.py`
- Create: `backend/src/crypto_alert_v2/integrations/secret_store.py`
- Create: `backend/src/crypto_alert_v2/api/routes/monitors.py`
- Create: `backend/src/crypto_alert_v2/api/routes/usage.py`
- Modify: `backend/src/crypto_alert_v2/workers/app.py`
- Modify: `backend/src/crypto_alert_v2/workers/loops.py`
- Modify: `backend/src/crypto_alert_v2/workers/health.py`
- Create: `backend/tests/contract/test_research_harness.py`
- Create: `backend/tests/contract/test_research_harness_fallback.py`
- Create: `backend/tests/integration/test_background_research.py`
- Create: `backend/tests/integration/test_retention_export_deletion.py`
- Create: `backend/tests/integration/test_outcome_maturation.py`
- Create: `backend/tests/contract/test_entitlement_and_usage.py`
- Create: `backend/tests/contract/test_webhook_security.py`
- Create: `backend/tests/integration/test_monitor_cron.py`
- Create: `backend/tests/integration/test_usage_reconciliation.py`
- Create: `backend/tests/integration/test_lifecycle_worker_process.py`
- Create: `backend/tests/integration/test_memory_controls.py`
- Create: `frontend/src/features/research/research-view-model.ts`
- Create: `frontend/src/features/research/research-task-panel.tsx`
- Create: `frontend/src/features/research/research-progress.tsx`
- Create: `frontend/src/features/settings/data-lifecycle-controls.tsx`
- Create: `frontend/src/features/outcomes/outcome-status.tsx`
- Create: `frontend/src/features/monitors/create-monitor.tsx`
- Create: `frontend/src/features/monitors/monitor-list.tsx`
- Create/Replace: `frontend/src/app/monitors/page.tsx`
- Create: `frontend/src/features/settings/usage-and-entitlements.tsx`
- Create: `frontend/src/features/settings/memory-controls.tsx`
- Modify: `frontend/src/app/settings/page.tsx`
- Create: `frontend/tests/unit/research-contract.test.ts`
- Create: `frontend/tests/unit/lifecycle-contract.test.ts`
- Create: `frontend/tests/unit/entitlement-contract.test.ts`
- Create: `frontend/tests/e2e/background-research.spec.ts`
- Create: `frontend/tests/e2e/data-lifecycle.spec.ts`
- Create: `frontend/tests/e2e/monitor-and-entitlement.spec.ts`
- Create: `frontend/tests/e2e/memory-controls.spec.ts`
- Create: `docs/v2/implementation/2026-07-13-task-13-research.md`

- [ ] **Step 1: Assert permissions and background semantics**

Tests must prove the effective model-bound tool set excludes `write_file`, `edit_file`, `execute`, database-write and notification tools; the default general-purpose subagent is disabled; retained `task` can invoke only explicitly approved read-only subagents. A capability-failure test selects one restricted `create_agent` fallback and proves the Deep Agent harness is not also active. Tests also cover bounded model/search calls, background continuation after browser disconnect and persisted task progress. Lifecycle tests cover 365-day Product/Artifact defaults, 30-day completed checkpoint/log/trace defaults, raw Prompt/Response not stored by default, versioned export manifests with hashes, deletion jobs across every declared system, legal-hold disclosure and one matured/scored Outcome pipeline proof. Memory tests let the user list, cap, disable and delete long-term Agent Store memory; delete enters the queue immediately, namespace ACL remains enforced, and ordinary business settings never enter Store. Commercial-foundation tests cover Agent Server Cron monitors, signed/replay-protected/idempotent webhooks, immutable usage ledger, reconciliation against provider/trace/runtime/storage/notification totals, stable quota errors and entitlements for model/mode/concurrency/search/storage/retention/scheduled tasks across two workspaces.

- [ ] **Step 2: Confirm the expected missing-research RED**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_research_harness.py tests/contract/test_research_harness_fallback.py tests/contract/test_entitlement_and_usage.py tests/contract/test_webhook_security.py tests/integration/test_background_research.py tests/integration/test_retention_export_deletion.py tests/integration/test_outcome_maturation.py tests/integration/test_memory_controls.py tests/integration/test_monitor_cron.py tests/integration/test_usage_reconciliation.py tests/integration/test_lifecycle_worker_process.py -q)
(cd frontend && npm run test:unit -- research-contract.test.ts lifecycle-contract.test.ts entitlement-contract.test.ts)
(cd frontend && npm run test:e2e -- background-research.spec.ts data-lifecycle.spec.ts monitor-and-entitlement.spec.ts memory-controls.spec.ts --project=fixture-desktop)
```

Expected: FAIL because the restricted Deep Agents harness, task API/projection and research UI do not exist. A passing test that substitutes a synchronous fake function for background continuation is invalid.

- [ ] **Step 3: Implement restricted research harness**

Use locked `deepagents.create_deep_agent` with official `HarnessProfile.excluded_tools` to remove `write_file`, `edit_file` and `execute`, and `GeneralPurposeSubagentProfile(enabled=False)` to disable the default broad subagent. Retain `task` only when explicit read-only synchronous SubAgents are configured, constrain each one, and prove a positive invocation; otherwise exclude it. Use a non-executing `StateBackend`, explicit deny permissions as defense in depth, and never expose the backend object directly through a tool. If the capability test cannot enforce these constraints, select one restricted official `create_agent` research harness and disable Deep Agents entirely for that deployment; no custom runtime and no dual active harness.

- [ ] **Step 4: Implement monitor ingress, retention, export, deletion and Outcome workers**

Data export emits a schema/version/hash manifest and verifies its own completeness. Account/Workspace deletion creates an auditable job spanning Product DB, Object Storage, Checkpoint, Store, search indexes, LangSmith, Langfuse, logs and backup-expiry queues; online deletion meets 30 days and backup propagation 35 days, with legal-hold exceptions visible to the user. Outcome maturation/scoring is deterministic and labels one sample only as pipeline proof; the UI exposes no-trade baseline, calibration/Brier and MFE/MAE/fees/slippage/funding fields only with sample/time-window labels and does not claim External Beta/GA quality until accepted gates are met.

Scheduled Monitor creation starts from an Artifact. Product PostgreSQL owns thesis, conditions, frequency, expiry, quiet hours, channels, Product monitor ID and ownership. The official Agent Server Cron API receives only stable monitor/trigger references in `input`/`metadata`; those Product fields are not invented Cron parameters. Cron targets the canonical graph's restricted `monitor_ingress` branch. Its short infrastructure Trigger Run validates the monitor reference, entitlement, expiry, quiet hours and conditions, atomically creates the Product Task plus `task_commands`, records trigger-run lineage/usage, and terminates without executing market analysis. The Product dispatcher later creates the distinct Product-owned analysis Run only when the Thread is dispatchable. Thus Product `task_commands` remains the sole durable Product analysis queue and sole owner of analysis Run creation, while the Cron Run is explicitly classified as infrastructure trigger execution. Cancellation/reconciliation tests distinguish both Run kinds, prove no Cron trigger bypasses admission/provider quotas, and ensure `cancel_task` affects the Product analysis Runs without corrupting unrelated trigger history. Usage records token/cost/search/runtime/storage/notification as immutable ledger entries and the reconciler reports drift. Webhooks use rotating signing keys, timestamp/nonce replay protection, idempotency and delivery audit. OAuth/integration secrets use the configured secret-store adapter and never enter Graph State, Prompt or Trace.

- [ ] **Step 5: Verify subagent/task UI and lifecycle**

Only expanded tasks subscribe to detailed subagent streams. Product history comes from Task/Artifact projections.

Run:

```bash
(cd backend && uv run pytest tests/contract/test_research_harness.py tests/contract/test_research_harness_fallback.py tests/contract/test_entitlement_and_usage.py tests/contract/test_webhook_security.py tests/integration/test_background_research.py tests/integration/test_retention_export_deletion.py tests/integration/test_outcome_maturation.py tests/integration/test_memory_controls.py tests/integration/test_monitor_cron.py tests/integration/test_usage_reconciliation.py tests/integration/test_lifecycle_worker_process.py -q)
(cd frontend && npm run test:unit -- research-contract.test.ts lifecycle-contract.test.ts entitlement-contract.test.ts)
(cd frontend && npm run test:e2e -- background-research.spec.ts data-lifecycle.spec.ts monitor-and-entitlement.spec.ts memory-controls.spec.ts --project=fixture-desktop)
```

Expected: all tests pass; the browser can disconnect and reconnect while the server-side task continues; persisted progress is queryable without subscribing every row to a live subagent stream; export/deletion status survives reload; one mature Outcome is scored without overstating financial quality.

- [ ] **Step 6: Create the candidate commit, run both reviews, then attest**

Commit: `feat: add restricted background deep research`

## Task 14: Production Gates and Legacy Removal

Task 14 is intentionally split into packaging, release-source, deployment-governance and evidence slices because later proof must reference earlier immutable commits. Packaging and release-source candidate commits stage the current Task 14 implementation-note draft, are reviewed first for specification compliance and then code/release quality, and are followed by an attestation-only commit that changes only that note before the next slice begins. Deployment-governance is a normative-baseline transition: after its full Task 0 review chain, its attestation commit may add only the regenerated `normative-baseline.json`, transitioned requirement-registry entries, fixed `governance-candidate-sha.txt` pointer and Task 14 note; it may not change the already-reviewed ADR or runtime evidence. The note draft records the base SHA and executed RED/GREEN evidence; it must not claim the candidate SHA before the candidate exists. Its attestation records the actual reviewed candidate SHA and reviewer dispositions. The Step 10 evidence commit is the immutable candidate for the final independent review; Step 11 keeps that evidence byte-for-byte unchanged and adds only the separate review note plus signed final-review attestation files.

Before any pre-`SOURCE_SHA` proof, set `V2_EVIDENCE_STAGING_ROOT` to a content-addressed directory outside every repository/worktree and verify it is not a symlink into the repo. Baseline, local recovery/lifecycle/load/SLO and V1 inventory/signature outputs are written only there, with a canonical staged-evidence manifest. No pre-source proof writes under repository `artifacts/`. After the source candidate and its attestation are immutable, `import_staged_evidence.py` verifies every hash/signature/source identity and imports the approved files into `artifacts/v2-final/` for the Step 10 evidence candidate.

**Files:**
- Create: `.github/workflows/v2-ci.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `deploy/docker-compose.production.yml`
- Create: `deploy/env.production.example`
- Replace: `.env.example`
- Modify: `.dockerignore`
- Create: `backend/tests/security/test_protocol_secret_leak.py`
- Create: `backend/tests/security/test_cross_tenant_matrix.py`
- Create: `backend/tests/contract/test_legacy_parity.py`
- Create: `backend/tests/contract/test_requirement_evidence.py`
- Create: `backend/tests/contract/test_authority_consistency.py`
- Create: `backend/tests/contract/test_alert_rules.py`
- Create for packaging slice: `backend/tests/contract/test_release_source_tooling.py`
- Create after packaging attestation: `backend/tests/contract/test_release_source_manifest.py`
- Create: `backend/tests/contract/test_baseline_attestation.py`
- Create: `backend/tests/contract/test_staged_evidence_import.py`
- Create: `backend/tests/performance/test_slo_contract.py`
- Create: `backend/tests/performance/test_concurrency_stream_load.py`
- Create after baseline proof: `backend/alembic/versions/0002_release_metadata.py`
- Create: `backend/tests/integration/test_release_migration_compatibility.py`
- Create: `tools/v2/backup_restore_drill.sh`
- Create: `tools/v2/data_lifecycle_drill.sh`
- Create: `tools/v2/build_production_images.sh`
- Create: `tools/v2/upgrade_rollback_drill.sh`
- Create: `tools/v2/run_load_probe.py`
- Create: `tools/v2/key_rotation_drill.sh`
- Create: `tools/v2/entitlement_quota_drill.sh`
- Create: `tools/v2/build_legacy_inventory.py`
- Create: `tools/v2/probe_production_stack.sh`
- Create: `tools/v2/verify_hosted_release.sh`
- Create: `tools/v2/deployment_exit_drill.sh`
- Create: `tools/v2/secret_scan.sh`
- Create: `tools/v2/run_slo_probe.py`
- Create: `tools/v2/verify_legacy_parity.py`
- Modify: `tools/v2/build_requirement_registry.py`
- Modify: `tools/v2/verify_requirements.py`
- Create: `tools/v2/verify_source_identity.py`
- Create: `tools/v2/verify_task14_test_report.py`
- Create: `tools/v2/verify_production_alerts.sh`
- Create: `tools/v2/verify_attestation_identities.py`
- Create: `tools/v2/build_final_review_attestation.py`
- Create: `tools/v2/build_baseline_attestation.py`
- Create: `tools/v2/verify_baseline_attestation.py`
- Create: `tools/v2/import_staged_evidence.py`
- Create: `tools/v2/stage_release_source.sh`
- Create: `tools/v2/build_release_source_manifest.py`
- Create: `docs/v2/legacy-parity-map.yaml`
- Modify: `docs/v2/requirements-registry.yaml`
- Create: `artifacts/v2-final/requirements-evidence.json`
- Create: `artifacts/v2-final/final-review-attestation.json`
- Create: `artifacts/v2-final/final-review-attestation.sigstore.json`
- Create: `artifacts/v2-final/recovery/.gitkeep`
- Create: `artifacts/v2-final/lifecycle/.gitkeep`
- Create: `artifacts/v2-final/deployment/.gitkeep`
- Create: `artifacts/v2-final/deployment/baseline-attestation.json`
- Create: `artifacts/v2-final/deployment/baseline-attestation.sigstore.json`
- Create: `artifacts/v2-final/deployment/baseline-verification.json`
- Create: `artifacts/v2-final/deployment/baseline-source-sha.txt`
- Create: `artifacts/v2-final/deployment/baseline-digest.txt`
- Create: `artifacts/v2-final/deployment/source-sha.txt`
- Create: `artifacts/v2-final/deployment/staged-source.json`
- Create: `artifacts/v2-final/deployment/governance-candidate-sha.txt`
- Create: `artifacts/v2-final/deployment/preflight.json`
- Create: `artifacts/v2-final/deployment/exit-drill.json`
- Create: `artifacts/v2-final/deployment/candidate-digest.txt`
- Create: `artifacts/v2-final/hosted-playwright/.gitkeep`
- Create: `artifacts/v2-final/slo/.gitkeep`
- Create: `artifacts/v2-final/load/.gitkeep`
- Create: `artifacts/v2-final/security/.gitkeep`
- Create: `artifacts/v2-final/alerts/.gitkeep`
- Create: `artifacts/v2-final/pre-deletion-inventory.json`
- Create: `artifacts/v2-final/post-deletion-survivor-scan.json`
- Create: `artifacts/v2-final/v1-data-attestation.json`
- Create: `artifacts/v2-final/v1-data-attestation.data-custodian.sigstore.json`
- Create: `artifacts/v2-final/v1-data-attestation.platform-custodian.sigstore.json`
- Create: `artifacts/v2-final/v1-data-attestation.data-custodian-verification.json`
- Create: `artifacts/v2-final/v1-data-attestation.platform-custodian-verification.json`
- Create: `artifacts/v2-final/v1-data-attestation.identity-verdict.json`
- Create: `frontend/tests/e2e/hosted-production.spec.ts`
- Create: `frontend/tests/e2e/hosted-security.spec.ts`
- Modify: `frontend/playwright.config.ts`
- Create: `tools/v2/profiles/hosted-production.env.example`
- Create: `docs/v2/implementation/final-independent-review.md`
- Create: `docs/archive/v1/README.md`
- Create: `docs/v2/runbooks/production.md`
- Create: `deploy/alerts.yaml`
- Create: `deploy/attestation-policy.yaml`
- Create: `deploy/release-source-policy.json`
- Create: `deploy/release-source-manifest.txt`
- Create: `artifacts/v2-final/pre-source-evidence-manifest.json`
- Modify: `docs/README.md`
- Modify after deployment-profile preflight and before hosted proof: `docs/v2/adr/0008-production-deployment-profile.md`
- Modify: `README.md`
- Delete after parity verification: `src/crypto_manual_alert/`
- Delete after parity verification: `tests/`
- Delete after parity verification: `config/`
- Delete after parity verification: `third_party/`
- Delete after parity verification: `tools/local_stack/`
- Delete after parity verification: `tools/deployment/`
- Delete after parity verification: `pyproject.toml`
- Delete after parity verification: `Dockerfile`
- Delete after parity verification: `Dockerfile.frontend`
- Delete after parity verification: `.env.production.example`
- Delete after parity verification: `frontend/src/app/config/`
- Delete after parity verification: `frontend/src/app/eval/`
- Delete after parity verification: `frontend/src/app/manual-run/`
- Delete after parity verification: `frontend/src/app/shared/`
- Delete after parity verification: `frontend/src/app/styles.css`
- Delete after parity verification: `frontend/src/lib/api/client.ts`
- Delete after parity verification: `frontend/src/lib/api/eval.ts`
- Delete after parity verification: `frontend/src/lib/api/runs.ts`
- Delete after parity verification: `frontend/src/lib/api/system.ts`
- Delete after parity verification: `frontend/src/lib/schemas/api.ts`
- Delete after parity verification: `frontend/src/lib/schemas/eval.ts`
- Delete after parity verification: `frontend/src/lib/schemas/manual-run.ts`
- Delete after parity verification: `frontend/src/lib/schemas/runs.ts`
- Delete after parity verification: `frontend/src/lib/schemas/system.ts`
- Delete after parity verification: `frontend/tests/e2e/async-and-mobile-depth.spec.ts`
- Delete after parity verification: `frontend/tests/e2e/audit-helpers.ts`
- Delete after parity verification: `frontend/tests/e2e/diagnostic-access-gate.spec.ts`
- Delete after parity verification: `frontend/tests/e2e/error-states.spec.ts`
- Delete after parity verification: `frontend/tests/e2e/full-stack-visual.spec.ts`
- Delete after parity verification: `frontend/tests/e2e/full-stack-visual.spec.ts-snapshots/`
- Delete after parity verification: `frontend/tests/e2e/hosted-prod-actionable-visual.spec.ts`
- Delete after parity verification: `frontend/tests/e2e/product-copy.spec.ts`
- Move after parity verification: `docs/formal/` -> `docs/archive/v1/formal/`
- Move after parity verification: `docs/migration/` -> `docs/archive/v1/migration/`
- Move after parity verification: `docs/implementation/` -> `docs/archive/v1/implementation/`
- Move after parity verification: `docs/agent-skill-final-architecture.md` -> `docs/archive/v1/agent-skill-final-architecture.md`
- Move after parity verification: `docs/agent-skill-refactor-plan.md` -> `docs/archive/v1/agent-skill-refactor-plan.md`
- Move after parity verification: `docs/architecture-optimization-review.md` -> `docs/archive/v1/architecture-optimization-review.md`
- Move after parity verification: `docs/auto-trading-plan.md` -> `docs/archive/v1/auto-trading-plan.md`
- Move after parity verification: `docs/configuration.md` -> `docs/archive/v1/configuration.md`
- Move after parity verification: `docs/deployment.md` -> `docs/archive/v1/deployment.md`
- Move after parity verification: `docs/end-to-end-business-flow.md` -> `docs/archive/v1/end-to-end-business-flow.md`
- Move after parity verification: `docs/memory-and-dialogue-design.md` -> `docs/archive/v1/memory-and-dialogue-design.md`
- Move after parity verification: `docs/operation.md` -> `docs/archive/v1/operation.md`
- Move after parity verification: `docs/prerequisites-keys-costs.md` -> `docs/archive/v1/prerequisites-keys-costs.md`
- Move after parity verification: `docs/production-optimization-backlog.md` -> `docs/archive/v1/production-optimization-backlog.md`
- Move after parity verification: `docs/quickstart.md` -> `docs/archive/v1/quickstart.md`
- Create: `docs/v2/implementation/2026-07-13-task-14-production-gate.md`

- [ ] **Step 1: Write only the packaging-slice contract tests**

Create only `test_alert_rules.py`, `test_release_source_tooling.py`, `test_baseline_attestation.py` and `test_staged_evidence_import.py` in this slice. They use temporary synthetic repositories/indexes and deterministic fixture manifests, so they can become GREEN before the packaging candidate is reviewed. The proof-dependent parity, requirement, security, performance, repository-state source-manifest and hosted tests described below are not created until Step 3B after packaging attestation.

`test_legacy_parity.py` requires three machine-readable sections: every retained V1 business rule/golden/presentation behavior maps to a named V2 test or explicit `retired` rationale; every V1 table maps to a V2 table or legacy-readonly decision with source/target row counts and checksums; every V1 path maps to migrate/delete/archive with verification. `build_legacy_inventory.py` generates the authoritative source inventory from full V1 commit `a44a7d24ba5ec02e784522fb684bb39b99802773`, prototype commit `b583e5a5fbdf7fc0df99e8182d1701c8df1f4082`, tracked paths/tests/schema definitions and the authoritative V1 data snapshot. `V1_DATA_DIR` is required when data exists; otherwise a signed zero-data attestation identifying searched hosts/paths/owners is required. Missing databases cannot be self-declared `no-data` by the migration script.

Task 14 fills observed evidence fields in the Task 0B registry but never creates requirement IDs or intended proof mappings retroactively. `build_requirement_registry.py` reads the complete source set exclusively from `normative-baseline.json`: files/regions classified `approved_normative`/`mixed.normative_regions` become normative entries, `proposed_gate` sources retain stable non-normative gate entries, and informative/verified/superseded regions are excluded or referenced only as supporting evidence. When ADR 0008 is accepted through the new Task 0 manifest, its existing gate IDs transition to normative without recreation. `requirements-registry.yaml` records observed RED/GREEN commands, hashes/counts, final proof receipts, reviewer dispositions, the applicable `NORMATIVE_SHA` generation and `SOURCE_SHA` against the intended mappings frozen in Task 0B. The generator/verifier fails when a source is added, changed or removed without a corresponding registry transition, when a child requirement is replaced by a catch-all meta-entry, or when owner/evidence fields contain placeholders, shared catch-all owners, skips or indirect proof.

`test_requirement_evidence.py` supports explicit `EVIDENCE_PHASE=source_candidate|pre_review|post_review`. `source_candidate` uses deterministic synthetic manifests to verify registry/evidence schemas, source coverage and verifier behavior without pretending runtime proof already exists; it must be GREEN before the release-source candidate. `pre_review` validates the complete real immutable `requirements-evidence.json`; `post_review` revalidates that same snapshot plus the separate final-review attestation without mutation. `test_slo_contract.py` and `test_concurrency_stream_load.py` likewise use deterministic contract fixtures in `source_candidate` mode, while real local/hosted measurements are mandatory in later evidence modes. An authority-consistency test rejects contradictory status headers, unchecked approval prerequisites, unresolved owner placeholders and ADR/index/checklist disagreements.

`test_protocol_secret_leak.py` injects canary credentials through model, search, market, notification and auth paths and scans Protocol frames, checkpoints, Product projections, traces, logs, screenshots and HTML reports. `test_cross_tenant_matrix.py` exercises every read/write/list/resume/cancel/fork endpoint for same-user cross-workspace, cross-user same-tenant and cross-tenant actors. `hosted-production.spec.ts` contains no fixture interception and requires the hosted proof identifiers, responsive rendering and shared Task/Run/Artifact continuity on desktop and Pixel 7 projects. `hosted-security.spec.ts` uses two real OIDC users, two tenants, two workspaces, a removed member and a least-privilege operator; it exercises list/read/write/resume/respond/cancel/retry/fork/feedback/export/delete through BFF, official SDK and UI, verifies non-disclosure denials plus operator action/reason audit, and proves invite-only Internal Alpha with no registration/trading/private-exchange capability.

`test_alert_rules.py` validates the `deploy/alerts.yaml` schema, unique rule IDs, provider/fingerprint selectors, severity/routing, source labels and positive/negative fixtures for independent LangSmith and Langfuse delivery exhaustion. `verify_production_alerts.sh` later injects those failures into the accepted hosted monitoring stack and requires real alert receipts; a local structured-log fingerprint alone is insufficient.

`test_release_source_tooling.py` validates the canonical newline-delimited UTF-8/LF path schema, sorting/uniqueness, policy include/exclude rules, self-inclusion and staged-index behavior against temporary synthetic Git indexes. The later `test_release_source_manifest.py` applies the same contract to the actual final repository index and fails if application/backend/frontend source, tests, migrations, locks, Dockerfiles, deployment/profile config, CI, build/deploy/probe/secret/parity/requirement/source-identity/alert verifiers, or the manifest itself are omitted, or if unrelated local/runtime/evidence files are included.

`test_baseline_attestation.py` requires deterministic canonical JSON and verifies that baseline provenance binds the exact Task 13 `BASELINE_SHA`, reviewed packaging candidate SHA, image digest, migration/database checksum manifest, hosted profile/environment and timestamps. It rejects nonexistent commits, mutable image tags, mismatched hashes, absent probe fields and signing before the binding verifier passes.

`test_staged_evidence_import.py` rejects staging roots inside/symlinked into any repository, requires a content-addressed manifest for every external pre-source artifact, verifies source/tool/signature bindings, refuses unexpected or changed files, and imports only the allowlisted evidence paths after `SOURCE_SHA` plus governance attestation exist.

- [ ] **Step 2: Confirm the packaging-slice RED**

Run:

```bash
(cd backend && uv run pytest tests/contract/test_alert_rules.py tests/contract/test_release_source_tooling.py tests/contract/test_baseline_attestation.py tests/contract/test_staged_evidence_import.py -q)
```

Expected: FAIL on missing packaging/alert/attestation/import implementations. Every file is collected; temporary Git/index fixtures initialize successfully; a dependency/setup-only failure is invalid.

- [ ] **Step 3: Add production packaging and CI gates**

Production images use the locked Python/Node runtimes, non-root users, health checks and immutable dependencies. `deploy/docker-compose.production.yml` starts PostgreSQL, Redis, Agent Server/Product API, workers and Next.js without development mounts or V1 services. `deploy/env.production.example` names required variables with empty values and contains no credential. `build_production_images.sh` builds immutable digests, generates SBOMs and runs Trivy filesystem/image scans. `probe_production_stack.sh` starts the actual production Compose profile, executes migrations, waits for all health checks, runs API/Agent schema smoke tests and always tears down through a trap.

`deploy/attestation-policy.yaml` defines trusted Sigstore OIDC issuers and exact identity patterns for four distinct roles: protected `release_signer`, independent `release_reviewer`, `data_custodian` and `platform_custodian`. Detached bundles are verified with `cosign verify-blob`; a self-declared JSON `signature` field is invalid. Baseline provenance binds `BASELINE_SHA`, reviewed packaging candidate SHA, image digest, migration/database checksums, environment and signer. V1 data/zero-data evidence requires independent data-custodian and platform-custodian bundles over the same canonical attestation, including searched hosts/paths, timestamps, access results and snapshot/checksum identity; the migration script cannot sign its own evidence.

CI installs from locks, verifies each code slice added a new implementation note with required front matter, runs backend/frontend tests, migration smoke tests, Agent Server schema contracts, secret/SBOM scans, parity/evidence verifiers and Playwright fixture suite. Real-provider, real-observability, backup/restore, production-image, load, hosted Playwright and SLO jobs run in a protected environment and are required for release tags. `deploy/alerts.yaml` covers readiness, market/search/model failures, independent LangSmith/Langfuse delivery exhaustion, projection lag, stale workers, outbox/DLQ, security and error-budget burn; alert tests inject positive canaries and record query/result hashes. The runbook documents deploy/rollback, incidents, backup/restore, key rotation, quota/entitlement failures, deletion and provider/observability outages.

`deploy/release-source-policy.json` defines the exact include/exclude roots. `deploy/release-source-manifest.txt` is generated only for the final source candidate, after every Task 14 source addition/change/deletion has been staged in the Git index. It is a sorted, unique, repository-relative, newline-delimited UTF-8/LF path manifest that includes itself and every staged/tracked release-critical path under backend application/tests/migrations/locks, frontend source/tests/dependency/config files, production Dockerfiles/Compose/profile configuration, `.github/workflows/v2-ci.yml`, `tools/v2/`, accepted V2 normative/ADR/implementation records and root release metadata. It explicitly excludes secrets, local environments, caches, generated runtime/evidence outputs, V1/archive-only paths and developer-machine files. `build_release_source_manifest.py` generates/checks the manifest against the staged index and policy, fails on any omitted release-critical or unexpected path, and emits a deterministic SHA-256. `stage_release_source.sh` prepares/verifies that index and emits a staged-path/hash report; it never stages an unreviewed path or absorbs unrelated changes.

Before the packaging candidate exists, record the already-green Task 13 attestation commit as `BASELINE_SHA` in the Task 14 note draft and under the external staged-evidence root. Commit only packaging policy/code/tests/tooling, the Task 14 registry/receipt and note draft as the early tooling candidate; the final source manifest does not exist yet. Review that immutable candidate, apply fixes through new candidates and re-review, then create the note-only attestation commit. Build the recorded Task 13 baseline source with the reviewed committed tooling, deploy it to non-production, run smoke/migration/checksum tests and store signed known-good baseline evidence outside the source worktree. This distinct baseline, not two builds of the same candidate, is required by the final rollback gate.

Run:

```bash
python3.12 tools/v2/import_staged_evidence.py --validate-root "$V2_EVIDENCE_STAGING_ROOT"
git rev-parse HEAD > "$V2_EVIDENCE_STAGING_ROOT/baseline-source-sha.txt"
(cd backend && uv run pytest tests/contract/test_alert_rules.py tests/contract/test_release_source_tooling.py tests/contract/test_baseline_attestation.py tests/contract/test_staged_evidence_import.py -q)
git add .github/workflows/v2-ci.yml backend/Dockerfile backend/tests/contract/test_alert_rules.py backend/tests/contract/test_release_source_tooling.py backend/tests/contract/test_baseline_attestation.py backend/tests/contract/test_staged_evidence_import.py frontend/Dockerfile deploy/docker-compose.production.yml deploy/env.production.example deploy/alerts.yaml deploy/attestation-policy.yaml deploy/release-source-policy.json .dockerignore .env.example tools/v2/build_production_images.sh tools/v2/probe_production_stack.sh tools/v2/upgrade_rollback_drill.sh tools/v2/deployment_exit_drill.sh tools/v2/secret_scan.sh tools/v2/build_release_source_manifest.py tools/v2/stage_release_source.sh tools/v2/verify_production_alerts.sh tools/v2/build_baseline_attestation.py tools/v2/verify_baseline_attestation.py tools/v2/import_staged_evidence.py docs/v2/requirements-registry.yaml docs/v2/implementation/2026-07-13-task-14-production-gate.md
git add -f artifacts/v2-final/pre-red/task-14.json
uv run --project backend python tools/v2/verify_requirements.py --registry docs/v2/requirements-registry.yaml --manifest docs/v2/normative-baseline.json --phase candidate --task 14 --receipt artifacts/v2-final/pre-red/task-14.json --check-index
git commit -m "build: add v2 release packaging and rollback tooling"
```

After both reviews approve and the packaging note-only attestation is committed, run:

```bash
PACKAGING_CANDIDATE_SHA="$(git rev-parse HEAD^)"
BASELINE_SHA="$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-source-sha.txt")"
./tools/v2/build_production_images.sh --source-sha "$BASELINE_SHA" --output-digest "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt"
./tools/v2/probe_production_stack.sh --image-digest "$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt")" --output "$V2_EVIDENCE_STAGING_ROOT/baseline-probe.json"
uv run --project backend python tools/v2/build_baseline_attestation.py --baseline-sha "$BASELINE_SHA" --packaging-candidate-sha "$PACKAGING_CANDIDATE_SHA" --image-digest-file "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt" --probe-manifest "$V2_EVIDENCE_STAGING_ROOT/baseline-probe.json" --profile non-production-hosted --output "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.json"
uv run --project backend python tools/v2/verify_baseline_attestation.py --attestation "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.json" --baseline-sha "$BASELINE_SHA" --packaging-candidate-sha "$PACKAGING_CANDIDATE_SHA" --image-digest-file "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt" --probe-manifest "$V2_EVIDENCE_STAGING_ROOT/baseline-probe.json"
cosign sign-blob --yes --bundle "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.sigstore.json" "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.json"
cosign verify-blob --output json --bundle "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.sigstore.json" --certificate-identity-regexp "$(yq '.release_signer.identity_regexp' deploy/attestation-policy.yaml)" --certificate-oidc-issuer "$(yq '.release_signer.issuer' deploy/attestation-policy.yaml)" "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.json" > "$V2_EVIDENCE_STAGING_ROOT/baseline-verification.json"
```

Only after the baseline is proven, write `test_release_migration_compatibility.py` and run its own explicit RED before adding the migration:

```bash
(cd backend && uv run pytest tests/integration/test_release_migration_compatibility.py -q)
```

Expected RED: the test reaches the proven baseline database/application topology and fails because revision `0002_release_metadata` and its forward-compatibility behavior do not exist; collection failure, connection refusal or credential skip is not acceptable. Then add the expand-only migration `0002_release_metadata`. The baseline application must remain healthy after the forward migration, and rollback to the baseline image must not require a destructive downgrade. This gives the final drill a distinct known-good application image and a real schema transition.

- [ ] **Step 3B: Write the remaining release-gate tests and record their RED**

Now create `test_legacy_parity.py`, `test_requirement_evidence.py`, `test_authority_consistency.py`, `test_release_source_manifest.py`, both performance tests, both security tests, `hosted-production.spec.ts`, `hosted-security.spec.ts` and the final hosted Playwright project/profile scaffolding. The hosted projects must collect successfully but are not executed before ADR 0008 acceptance. Run the non-hosted RED matrix:

```bash
(cd backend && EVIDENCE_PHASE=pre_review uv run pytest tests/contract/test_legacy_parity.py tests/contract/test_requirement_evidence.py tests/contract/test_authority_consistency.py tests/contract/test_release_source_manifest.py tests/performance/test_slo_contract.py tests/performance/test_concurrency_stream_load.py -q)
(cd backend && uv run pytest tests/security/test_protocol_secret_leak.py tests/security/test_cross_tenant_matrix.py -q)
uv run --project backend python tools/v2/verify_legacy_parity.py --check
uv run --project backend python tools/v2/verify_requirements.py --check
```

Expected: every named file collects and fails on its intended missing parity/evidence/source-manifest/security/SLO behavior. Unknown project, zero tests, skip, missing dependency or connection-only failure is invalid. Hosted browser/alert-delivery RED remains deferred until the accepted deployment transition in Step 7.

- [ ] **Step 4: Run supplemental local security, recovery and SLO gates**

Canary secrets must not appear in Protocol frames, snapshots, traces, logs, screenshots or HTML reports. Tenant/user matrix covers every read/write/list/resume endpoint.

Create an interrupted run, restart Agent Server, restore databases, resume the same thread and verify product projection consistency. The positive path proves the old Run keeps a valid standard `status` while `recovery_status` transitions `pending -> recovering -> superseded`, a distinct immutable resume Run is created with lineage, and the Task/Artifact continuation points to the new Run. The drill also injects stale heartbeat, expired recovery deadline, exhausted two-attempt budget, running projection delay above 5 seconds and terminal projection delay above 2 seconds; it asserts alerts/reconciliation fire and no record remains permanently `running`.

`data_lifecycle_drill.sh` uses a clock-controlled hosted-compatible backup lifecycle. It creates tenant data across Product DB, Object Storage, Checkpoint/Store, search, observability and logs; takes a restorable backup; requests deletion; advances through the 30-day online deletion boundary and proves all online adapters are complete; rotates backup generations through the 35-day propagation boundary; and proves the deleted tenant cannot be listed or restored from the surviving backup set. Legal-hold cases remain recoverable and auditable until release, then pass the same completed-deletion proof. A queued expiry job or scheduled timestamp alone does not satisfy this gate.

Run:

```bash
(cd backend && uv run pytest tests/security -q)
./tools/v2/backup_restore_drill.sh --output-root "$V2_EVIDENCE_STAGING_ROOT/local-recovery"
./tools/v2/data_lifecycle_drill.sh --output-root "$V2_EVIDENCE_STAGING_ROOT/local-lifecycle"
./tools/v2/key_rotation_drill.sh --output-root "$V2_EVIDENCE_STAGING_ROOT/local-security"
./tools/v2/entitlement_quota_drill.sh --output-root "$V2_EVIDENCE_STAGING_ROOT/local-entitlement"
uv run --project backend python tools/v2/run_load_probe.py --release-tier internal_alpha --output "$V2_EVIDENCE_STAGING_ROOT/local-load/results.json"
uv run --project backend python tools/v2/run_slo_probe.py --release-tier internal_alpha --output "$V2_EVIDENCE_STAGING_ROOT/local-slo/results.json"
(cd backend && uv run pytest tests/integration/test_release_migration_compatibility.py tests/performance/test_slo_contract.py tests/performance/test_concurrency_stream_load.py -q)
```

Expected: security tests pass; staged recovery proof shows the same thread resumes after Agent Server and database restoration; lifecycle proof verifies export hashes, online-system deletion completion by day 30 and irreversible backup-set propagation by day 35 through a failed restore/list attempt for the deleted tenant; SLO results satisfy ADR 0006; no staged artifact contains a secret.

These local results are development/preflight evidence only. They cannot satisfy hosted production recovery, real-user isolation, load or SLO requirements.

- [ ] **Step 5: Prove parity, then remove the exact V1 paths**

Before deletion, obtain the independently signed V1 data snapshot/zero-data attestation under the external staged-evidence root and verify both custodian identities against `deploy/attestation-policy.yaml`; verification output is part of the immutable evidence. Then run `uv run --project backend python tools/v2/build_legacy_inventory.py --v1-ref a44a7d24ba5ec02e784522fb684bb39b99802773 --prototype-ref b583e5a5fbdf7fc0df99e8182d1701c8df1f4082 --output "$V2_EVIDENCE_STAGING_ROOT/pre-deletion-inventory.json"`. Map every generated business rule/golden case, V1 table and V1 path. Table evidence records authoritative source/target row counts and checksums or a signed retired decision. Keep V1 available through the archived branch/tag, not in the V2 Final production tree.

Run the two independent checks over the same canonical attestation and then verify role separation:

```bash
cosign verify-blob --output json --bundle "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.data-custodian.sigstore.json" --certificate-identity-regexp "$(yq '.data_custodian.identity_regexp' deploy/attestation-policy.yaml)" --certificate-oidc-issuer "$(yq '.data_custodian.issuer' deploy/attestation-policy.yaml)" "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.json" > "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.data-custodian-verification.json"
cosign verify-blob --output json --bundle "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.platform-custodian.sigstore.json" --certificate-identity-regexp "$(yq '.platform_custodian.identity_regexp' deploy/attestation-policy.yaml)" --certificate-oidc-issuer "$(yq '.platform_custodian.issuer' deploy/attestation-policy.yaml)" "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.json" > "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.platform-custodian-verification.json"
uv run --project backend python tools/v2/verify_attestation_identities.py --policy deploy/attestation-policy.yaml --data-verification "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.data-custodian-verification.json" --platform-verification "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.platform-custodian-verification.json" --forbid-roles release_signer,release_reviewer,implementer,migration_process --output "$V2_EVIDENCE_STAGING_ROOT/v1-data-attestation.identity-verdict.json"
```

The verifier fails unless the certificate identities are distinct, policy-trusted and different from every forbidden role. A missing database, unsigned attestation, self-signature or migration/implementer/release identity blocks deletion.

The parity verifier first checks that the map covers every hashed staged pre-deletion inventory record, then validates dispositions. Run it before deletion. Only after it exits 0, delete exactly the paths listed in this task. Run frontend typecheck/build and generate the separate immutable `$V2_EVIDENCE_STAGING_ROOT/post-deletion-survivor-scan.json`; verify it against the frozen pre-deletion hash to prove no surviving source/test imports a removed module and all mapped V2 evidence remains available.

- [ ] **Step 6: Create and review the clean immutable release-source candidate, then attest**

After parity deletion and all Task 14 code/tooling/config changes are ready, run local preflight tests, then commit them before producing any release evidence:

```bash
./tools/v2/secret_scan.sh
uv run --project backend python tools/v2/verify_legacy_parity.py --check
(cd frontend && npm run typecheck && npm run build)
./tools/v2/stage_release_source.sh --prepare-index --policy deploy/release-source-policy.json --note docs/v2/implementation/2026-07-13-task-14-production-gate.md --report "$V2_EVIDENCE_STAGING_ROOT/staged-source.json"
uv run --project backend python tools/v2/build_release_source_manifest.py --from-index --policy deploy/release-source-policy.json --write deploy/release-source-manifest.txt
git add deploy/release-source-manifest.txt
uv run --project backend python tools/v2/build_release_source_manifest.py --check-index deploy/release-source-manifest.txt --policy deploy/release-source-policy.json
./tools/v2/stage_release_source.sh --verify-index --manifest deploy/release-source-manifest.txt --note docs/v2/implementation/2026-07-13-task-14-production-gate.md --report "$V2_EVIDENCE_STAGING_ROOT/staged-source.json"
(cd backend && EVIDENCE_PHASE=source_candidate uv run pytest tests/security/test_protocol_secret_leak.py tests/security/test_cross_tenant_matrix.py tests/contract/test_legacy_parity.py tests/contract/test_requirement_evidence.py tests/contract/test_authority_consistency.py tests/contract/test_release_source_manifest.py tests/contract/test_alert_rules.py tests/contract/test_release_source_tooling.py tests/contract/test_baseline_attestation.py tests/contract/test_staged_evidence_import.py tests/performance/test_slo_contract.py tests/performance/test_concurrency_stream_load.py tests/integration/test_release_migration_compatibility.py -q)
uv run --project backend python tools/v2/verify_requirements.py --registry docs/v2/requirements-registry.yaml --manifest docs/v2/normative-baseline.json --phase candidate --task 14 --receipt artifacts/v2-final/pre-red/task-14.json --check-index
git commit -m "chore: prepare v2 release candidate"
test -z "$(git status --porcelain)"
```

Review this immutable release-source candidate for specification compliance and then release/code quality. Any fix creates a new candidate and repeats both reviews. After approval, create the Task 14 note-only attestation commit, then write the reviewed candidate SHA, not the later attestation SHA, to `artifacts/v2-final/deployment/source-sha.txt` in the next evidence/governance slice. Call that reviewed clean candidate `SOURCE_SHA`. All production images, hosted tests and runtime evidence must identify `SOURCE_SHA`. Any later change to application code, tests, migrations, dependency locks, Dockerfiles, deployment/profile config, CI, build/deploy/probe scripts, requirement/parity/secret/source-identity verifiers or other release-critical tooling creates a new release-source candidate, repeats both reviews and invalidates all prior production evidence.

- [ ] **Step 7: Accept the deployment profile before hosted runtime proof**

Write the reviewed release-source candidate SHA to `artifacts/v2-final/deployment/source-sha.txt`. In the candidate non-production target, run preflight and exit drills with explicit output paths; the exit drill exports Thread/Checkpoint/Store/Product data, switches to the documented alternate profile without changing frontend/DTO contracts, validates hashes, and switches back. Only after license/region/egress/Auth/persistence/HA/SLO/cost plus this real exit evidence pass may the governance candidate change ADR 0008 from `Proposed`/`authority_class: proposed_gate` to `Accepted`/`authority_class: approved_normative`. The same candidate updates the root/ADR indexes consistently but does not yet mutate `normative-baseline.json`:

```bash
./tools/v2/verify_hosted_release.sh --preflight --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --output artifacts/v2-final/deployment/preflight.json
./tools/v2/deployment_exit_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --output artifacts/v2-final/deployment/exit-drill.json
git add docs/v2/adr/0008-production-deployment-profile.md docs/v2/adr/README.md docs/v2/README.md docs/v2/implementation/2026-07-13-task-14-production-gate.md
git add -f artifacts/v2-final/deployment/source-sha.txt artifacts/v2-final/deployment/preflight.json artifacts/v2-final/deployment/exit-drill.json
git commit -m "docs: accept v2 production deployment profile"
```

Treat that exact governance candidate as a new proposed normative baseline. Run the complete Task 0 sequence: specification/authority review to approval, then plan-executability review to approval, then official-framework review to approval; any finding creates a new governance candidate and restarts all three reviews in order. After zero Critical/Important findings, write the reviewed candidate SHA, generate a new manifest generation that promotes ADR 0008 from `proposed_gate` to `approved_normative`, and transition the existing stable gate requirement IDs without recreation. Revalidate every affected deployment/hosted registry entry before committing only the transition metadata:

```bash
git rev-parse HEAD > artifacts/v2-final/deployment/governance-candidate-sha.txt
uv run --project backend python tools/v2/transition_normative_baseline.py --current-manifest docs/v2/normative-baseline.json --candidate-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --promote docs/v2/adr/0008-production-deployment-profile.md --review-note docs/v2/implementation/2026-07-13-task-14-production-gate.md --output docs/v2/normative-baseline.json
uv run --project backend python tools/v2/build_requirement_registry.py --manifest docs/v2/normative-baseline.json --registry docs/v2/requirements-registry.yaml --transition-gate ADR-0008 --check
uv run --project backend python tools/v2/verify_requirements.py --registry docs/v2/requirements-registry.yaml --manifest docs/v2/normative-baseline.json --phase governance-transition --require-normative-sha "$(jq -er '.normative_sha' docs/v2/normative-baseline.json)"
git add docs/v2/normative-baseline.json docs/v2/requirements-registry.yaml docs/v2/implementation/2026-07-13-task-14-production-gate.md
git add -f artifacts/v2-final/deployment/governance-candidate-sha.txt
git commit -m "docs: attest accepted v2 deployment baseline"
```

Hosted release proof is forbidden before that reviewed governance candidate, new manifest generation, transitioned registry and attestation exist. All subsequent evidence records the new `NORMATIVE_SHA` plus the unchanged application `SOURCE_SHA`.

After the reviewed governance candidate is accepted, deploy the signed Task 13 baseline image to that accepted non-production hosted profile and execute the explicitly deferred browser RED:

```bash
./tools/v2/verify_hosted_release.sh --red --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-source-sha.txt")" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt")"
./tools/v2/verify_production_alerts.sh --red --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-source-sha.txt")" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt")" --output artifacts/v2-final/alerts/hosted-red.json
```

The commands must reach a healthy public HTTPS deployment. Browser RED collects `hosted-production.spec.ts` and `hosted-security.spec.ts` on both named desktop/Pixel projects and fails on the intentionally missing release-candidate proof/enforcement assertion. Alert RED independently exhausts LangSmith and Langfuse delivery and fails because the baseline monitoring stack does not produce the required rule/receipt. Unknown project, localhost/private/tunnel URL, credential skip, connection refusal, zero collected tests or failure to inject the canary is not RED evidence. The same browser and alert cases run GREEN only in Step 8 against `SOURCE_SHA`.

- [ ] **Step 8: Build, scan, deploy, upgrade and rollback the clean source**

Run:

```bash
./tools/v2/build_production_images.sh --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --output-digest artifacts/v2-final/deployment/candidate-digest.txt
./tools/v2/probe_production_stack.sh --profile hosted-production --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/verify_hosted_release.sh --run --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/upgrade_rollback_drill.sh --profile hosted-production --baseline-digest "$(cat "$V2_EVIDENCE_STAGING_ROOT/baseline-digest.txt")" --baseline-attestation "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.json" --baseline-attestation-bundle "$V2_EVIDENCE_STAGING_ROOT/baseline-attestation.sigstore.json" --candidate-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --candidate-source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)"
./tools/v2/backup_restore_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/data_lifecycle_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/entitlement_quota_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/verify_production_alerts.sh --run --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --output artifacts/v2-final/alerts/hosted-green.json
uv run --project backend python tools/v2/run_load_probe.py --profile hosted-production --base-url "$HOSTED_BASE_URL" --release-tier internal_alpha --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --output artifacts/v2-final/load/hosted-results.json
uv run --project backend python tools/v2/run_slo_probe.py --profile hosted-production --base-url "$HOSTED_BASE_URL" --release-tier internal_alpha --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --output artifacts/v2-final/slo/hosted-results.json
```

`verify_hosted_release.sh` refuses localhost, private IPs, tunnels and non-HTTPS URLs. It runs `hosted-production.spec.ts` and `hosted-security.spec.ts` in explicit `hosted-production-desktop` and `hosted-production-pixel-7` projects without `page.route`, HAR, fixture providers or seeded results, and fails unless every file/project is collected, executed and has zero skip/deselection. An API gate creates one real long-running Deep Research Task/Run. The browser observes coordinator, approved subagent, Tool, Artifact, Evidence and Risk components from official `stream.subagents` plus Product projections; diagnostic `stream.subgraphs` is not used as the ordinary UI source. A hosted review case creates both root and approved nested-subagent interrupts, verifies namespace/checkpoint routing, submits an allowed state correction atomically with the response, restarts Agent Server, rejoins and proves one-winner replay/idempotency. Playwright also disconnects during an active background Run, closes the page, rejoins from a fresh browser context with `since`, proves ordered replay without duplicated messages/events, waits for completion and verifies the real Bark receipt plus Inbox link and a real Web Push-or-Email receipt bind to the same Task/Run/Artifact. Desktop and mobile then open that same task/run/artifact and verify market/search/model/risk/database/notification/observability proof IDs and correlation ID. The hosted security project uses the two real tenants/users, removed member and operator described in Step 1 and verifies all BFF/SDK/UI denials, audits and Internal Alpha boundaries. Save HTML, JUnit, screenshots, traces, video, network logs, URLs, actor/tenant/workspace IDs, provider receipts, `SOURCE_SHA`, governance commit, image digests, `release_tier=internal_alpha`, profile and timestamps under `artifacts/v2-final/hosted-playwright/`.

`upgrade_rollback_drill.sh` first verifies the baseline Sigstore bundle/trusted signer and the attestation's baseline digest/source/packaging/migration/database checksum bindings, then verifies the candidate digest carries the requested `SOURCE_SHA`/governance labels. Only then may it apply forward-compatible migrations, wait for health/error thresholds, validate data checksums, upgrade, roll back to the baseline and revalidate. A same-source bootstrap mechanics run is supplemental only and cannot satisfy the normative rollback gate. Evidence is stored under `artifacts/v2-final/deployment/upgrade-rollback/`.

`verify_production_alerts.sh` independently exhausts LangSmith and Langfuse delivery, requires the configured hosted monitoring backend to fire the corresponding exact fingerprint/rule, waits through pending-to-firing resolution, and stores rule/query hashes, correlation ID, alert receipt/state, timestamps, `SOURCE_SHA`, governance SHA and image digest under `artifacts/v2-final/alerts/`. It also proves a negative control does not fire.

All build/deploy/probe scripts materialize source from the committed `SOURCE_SHA` (git archive or isolated worktree) and refuse to copy application files from the current dirty evidence worktree. Hosted security/recovery/load/SLO/alert commands require the accepted profile, public HTTPS URL, `SOURCE_SHA`, governance SHA and image digest; they reject localhost/private/tunnel/fixture targets, zero samples, skip/deselection, missing positive canary receipts and connection failures. Reproducible build labels, SBOMs and image annotations must contain the same source tree hash.

- [ ] **Step 9: Run the complete pre-review matrix and freeze logs**

```bash
./tools/v2/secret_scan.sh
./tools/v2/verify_stack.sh
(cd backend && EVIDENCE_PHASE=pre_review uv run pytest -q --cov=crypto_alert_v2 --cov-report=term-missing)
(cd frontend && npm run lint && npm run typecheck && npm run test:unit && npm run build && npm run test:e2e -- --project=fixture-desktop --project=fixture-pixel-7 --project=real-provider-desktop --project=real-provider-pixel-7 --project=failure-injection-desktop --project=failure-injection-pixel-7)
uv run --project backend python tools/v2/verify_legacy_parity.py --check
./tools/v2/probe_production_stack.sh --profile hosted-production --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/backup_restore_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/data_lifecycle_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/key_rotation_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/entitlement_quota_drill.sh --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
./tools/v2/verify_production_alerts.sh --run --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --output artifacts/v2-final/alerts/hosted-green.json
uv run --project backend python tools/v2/run_load_probe.py --profile hosted-production --base-url "$HOSTED_BASE_URL" --release-tier internal_alpha --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --output artifacts/v2-final/load/hosted-results.json
uv run --project backend python tools/v2/run_slo_probe.py --profile hosted-production --base-url "$HOSTED_BASE_URL" --release-tier internal_alpha --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --output artifacts/v2-final/slo/hosted-results.json
./tools/v2/verify_hosted_release.sh --run --profile hosted-production --base-url "$HOSTED_BASE_URL" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)"
```

Every command writes an immutable, secret-redacted log under `artifacts/v2-final/test-logs/`. Regenerate `versions.json` after final locks/images. Expected: every command exits 0; no V1 runtime appears in images; local production and public HTTPS proofs pass against `SOURCE_SHA`.

The Task 14 GREEN evidence must also execute every declared Task 14 test path by name, with machine-readable reports proving collection, execution, pass count and zero skips/deselections:

```bash
(cd backend && EVIDENCE_PHASE=pre_review uv run pytest tests/security/test_protocol_secret_leak.py tests/security/test_cross_tenant_matrix.py tests/security/test_internal_alpha_boundary.py tests/contract/test_legacy_parity.py tests/contract/test_requirement_evidence.py tests/contract/test_authority_consistency.py tests/contract/test_alert_rules.py tests/contract/test_release_source_tooling.py tests/contract/test_release_source_manifest.py tests/contract/test_baseline_attestation.py tests/contract/test_staged_evidence_import.py tests/performance/test_slo_contract.py tests/performance/test_concurrency_stream_load.py tests/integration/test_release_migration_compatibility.py -q --junitxml=../artifacts/v2-final/test-logs/task-14-backend-green.xml)
(cd frontend && PLAYWRIGHT_JUNIT_OUTPUT_FILE=../artifacts/v2-final/test-logs/task-14-hosted-green.xml npx playwright test tests/e2e/hosted-production.spec.ts tests/e2e/hosted-security.spec.ts --project=hosted-production-desktop --project=hosted-production-pixel-7 --reporter=line,junit)
uv run --project backend python tools/v2/verify_task14_test_report.py --backend-junit artifacts/v2-final/test-logs/task-14-backend-green.xml --hosted-junit artifacts/v2-final/test-logs/task-14-hosted-green.xml --expected-backend-tests tests/security/test_protocol_secret_leak.py,tests/security/test_cross_tenant_matrix.py,tests/security/test_internal_alpha_boundary.py,tests/contract/test_legacy_parity.py,tests/contract/test_requirement_evidence.py,tests/contract/test_authority_consistency.py,tests/contract/test_alert_rules.py,tests/contract/test_release_source_tooling.py,tests/contract/test_release_source_manifest.py,tests/contract/test_baseline_attestation.py,tests/contract/test_staged_evidence_import.py,tests/performance/test_slo_contract.py,tests/performance/test_concurrency_stream_load.py,tests/integration/test_release_migration_compatibility.py --expected-frontend-files frontend/tests/e2e/hosted-production.spec.ts,frontend/tests/e2e/hosted-security.spec.ts --expected-projects hosted-production-desktop,hosted-production-pixel-7
```

`verify_task14_test_report.py` is a declared release verifier and fails on missing collection, deselection, skip, zero tests, wrong project, connection/setup-only failure or a report not bound to `SOURCE_SHA` and the accepted governance SHA.

- [ ] **Step 10: Generate, verify and commit the pre-review evidence snapshot**

Generate `requirements-evidence.json` from the complete requirement registry plus frozen logs, versions/SBOMs, provider/migration/Playwright/observability/production-alert/recovery/lifecycle/load/SLO/hosted/parity proof. Every requirement entry records its stable ID, source hash, accountable owner role/Agent ID, implementation task/slice, RED command/exit/log hash/intended failure, GREEN command/pass count/log hash, final proof artifact/classification/environment, reviewer dispositions, `NORMATIVE_SHA`, `SOURCE_SHA`, governance commit, artifact SHA-256 and redaction result. No parent/meta entry may stand in for its child requirements.

Run:

```bash
uv run --project backend python tools/v2/import_staged_evidence.py --root "$V2_EVIDENCE_STAGING_ROOT" --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --output-root artifacts/v2-final --manifest artifacts/v2-final/pre-source-evidence-manifest.json
(cd backend && EVIDENCE_PHASE=pre_review uv run pytest tests/contract/test_requirement_evidence.py -q)
uv run --project backend python tools/v2/verify_requirements.py --check --phase pre_review
uv run --project backend python tools/v2/verify_source_identity.py --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)"
git add -f artifacts/v2-final
git add docs/v2/implementation docs/v2/runbooks docs/v2/adr/0008-production-deployment-profile.md
git commit -m "docs: stage v2 release evidence"
test -z "$(git status --porcelain)"
```

This commit includes the current Task 14 note draft and is the immutable evidence candidate. Do not insert its own SHA into the draft before committing it; the final independent review in Step 11 supplies that SHA and disposition in the attestation-only closeout.

- [ ] **Step 11: Run the independent review as the last release gate**

Set `EVIDENCE_SHA` to the exact current clean commit and dispatch a fresh evidence-specification reviewer against it. Fix any finding through a new evidence candidate and repeat the specification review until approved. Only then dispatch a different release-evidence quality reviewer against the same immutable candidate; any quality finding creates a new evidence candidate and repeats both reviews in order. The reviewers may read runtime source, tests, tooling and all evidence but must not edit them. Any Critical/Important finding invalidates the evidence; any change to application, tests, migrations, Dockerfiles, deployment/profile config, CI or release-verification tooling creates a new `SOURCE_SHA` and repeats Steps 7-10.

After both approvals, keep `requirements-evidence.json` byte-for-byte immutable. Write both reviewer results to `final-independent-review.md` and create `final-review-attestation.json` containing `EVIDENCE_SHA`, specification and quality reviewer identities/results/findings/dispositions, the immutable evidence-manifest SHA-256, reviewed source/governance/image identities and timestamp. Sign that canonical attestation with the trusted release-reviewer identity and verify the detached Sigstore bundle before committing only these attestation artifacts:

```bash
uv run --project backend python tools/v2/build_final_review_attestation.py --evidence-sha "$(git rev-parse HEAD)" --requirements-evidence artifacts/v2-final/requirements-evidence.json --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)" --governance-sha "$(cat artifacts/v2-final/deployment/governance-candidate-sha.txt)" --image-digest "$(cat artifacts/v2-final/deployment/candidate-digest.txt)" --review-note docs/v2/implementation/final-independent-review.md --output artifacts/v2-final/final-review-attestation.json
cosign sign-blob --yes --bundle artifacts/v2-final/final-review-attestation.sigstore.json artifacts/v2-final/final-review-attestation.json
cosign verify-blob --bundle artifacts/v2-final/final-review-attestation.sigstore.json --certificate-identity-regexp "$(yq '.release_reviewer.identity_regexp' deploy/attestation-policy.yaml)" --certificate-oidc-issuer "$(yq '.release_reviewer.issuer' deploy/attestation-policy.yaml)" artifacts/v2-final/final-review-attestation.json
git add docs/v2/implementation/final-independent-review.md
git add -f artifacts/v2-final/final-review-attestation.json artifacts/v2-final/final-review-attestation.sigstore.json
git commit -m "docs: attest v2 final independent review"
```

- [ ] **Step 12: Verify the exact final attestation commit and stop changing files**

The signed committed `final-review-attestation.json` is the only authority for `EVIDENCE_SHA` and the frozen requirements-evidence hash. The attested `EVIDENCE_SHA` must equal `HEAD^`; the diff may contain only `final-independent-review.md` and the two separate final-review attestation files. `requirements-evidence.json` must match the attested SHA-256 exactly. The source-identity verifier hashes application, tests, migrations, Dockerfiles, deployment/profile config, CI, dependency locks and every release-verification/secret-scan/source-identity tool against `SOURCE_SHA`.

Run:

```bash
set -euo pipefail
cosign verify-blob --bundle artifacts/v2-final/final-review-attestation.sigstore.json --certificate-identity-regexp "$(yq '.release_reviewer.identity_regexp' deploy/attestation-policy.yaml)" --certificate-oidc-issuer "$(yq '.release_reviewer.issuer' deploy/attestation-policy.yaml)" artifacts/v2-final/final-review-attestation.json
EVIDENCE_SHA="$(jq -er '.evidence_sha' artifacts/v2-final/final-review-attestation.json)"
EVIDENCE_MANIFEST_SHA256="$(jq -er '.requirements_evidence_sha256' artifacts/v2-final/final-review-attestation.json)"
test "$EVIDENCE_SHA" = "$(git rev-parse HEAD^)"
printf '%s  %s\n' "$EVIDENCE_MANIFEST_SHA256" artifacts/v2-final/requirements-evidence.json | shasum -a 256 --check -
uv run --project backend python tools/v2/verify_source_identity.py --source-sha "$(cat artifacts/v2-final/deployment/source-sha.txt)"
(cd backend && EVIDENCE_PHASE=post_review uv run pytest tests/contract/test_requirement_evidence.py -q)
uv run --project backend python tools/v2/verify_requirements.py --check --phase post_review
./tools/v2/secret_scan.sh
ACTUAL_PATHS="$(git diff-tree --no-commit-id --name-only --no-renames -r HEAD | LC_ALL=C sort)"
EXPECTED_PATHS="$(printf '%s\n' artifacts/v2-final/final-review-attestation.json artifacts/v2-final/final-review-attestation.sigstore.json docs/v2/implementation/final-independent-review.md | LC_ALL=C sort)"
test "$ACTUAL_PATHS" = "$EXPECTED_PATHS"
test -z "$(git status --porcelain)"
```

## Final Completion Audit

- [ ] Every requirement and proposed gate extracted from the current `normative-baseline.json` generation, covering all `approved_normative`, `mixed.normative_regions` and `proposed_gate` entries, maps to its frozen intended RED/GREEN/final-proof target and observed individually owned evidence. This manifest-derived verifier is authoritative over any human-readable source summary. The final independent review is a separate signed post-review gate over that frozen registry/evidence snapshot, not a retrospectively extracted normative requirement.
- [ ] Backend unit, contract, integration, real-provider and security suites pass.
- [ ] Frontend lint, typecheck, unit, build and all Playwright projects pass.
- [ ] PostgreSQL migrations and backup/restore drill pass.
- [ ] Agent Server restart preserves and resumes an interrupted Thread.
- [ ] Real OKX, Web Search and model results are visible in the product UI.
- [ ] LangSmith and Langfuse share correlation IDs without secret leakage.
- [ ] LangSmith Dataset/Experiment/Release Gate, Agent Server Cron monitors, signed webhooks, entitlements, quota and immutable usage reconciliation pass.
- [ ] Worker restart, concurrent Run/research/stream load, alerting, runbook, key rotation, upgrade/rollback and hosted HTTPS evidence pass against the immutable `SOURCE_SHA`.
- [ ] No V1 runtime, static product mock, raw JSON primary UI, private SSE or generic-success fallback remains.
- [ ] A final independent reviewer reports no open Critical or Important findings.
