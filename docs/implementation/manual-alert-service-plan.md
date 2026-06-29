# Manual Alert Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-shaped, manually executed crypto operation-plan service that fetches public market data, prepares a decision prompt, parses a structured plan, runs configurable risk gates, logs to SQLite, and sends Bark reminders without automatic trading.

**Architecture:** Use a Python CLI batch service with optional in-process scheduler. All external integrations are ports/adapters: OKX public market data, optional future read-only account provider, decision engine, notification sink, and journal repository. Configuration is YAML plus environment variables, with secrets outside files and all automated trading paths disabled by default.

**Tech Stack:** Python 3.11+, httpx, PyYAML, pytest, SQLite, Docker, Docker Compose.

---

## File Structure

- `pyproject.toml`: package metadata, dependencies, pytest config.
- `Dockerfile`: production image for CLI/scheduler.
- `docker-compose.yml`: no host ports, no container name, bind-mounted config/data.
- `.env.example`: safe example environment variables.
- `config/default.yaml`: non-sensitive defaults.
- `config/prod.yaml`: deployment override example.
- `src/jiami_crypto_alert/`: application package.
- `tests/`: unit and integration-style tests.
- `third_party/skills/crypto-macro-decision/`: vendored local skill copy.
- `docs/operation.md`: user operation runbook.
- `docs/deployment.md`: Docker Compose deployment guide.
- `docs/configuration.md`: configuration reference.

## Tasks

### Task 1: Project Scaffold

- [ ] Create Python package layout.
- [ ] Add config files and Docker files.
- [ ] Copy local `crypto-macro-decision` skill into `third_party/skills`.

### Task 2: Core Domain And Config

- [ ] Add dataclasses for market data, decision plans, risk verdicts, notifications, and run records.
- [ ] Add YAML/env config loader.
- [ ] Add validation that automated trading is disabled and trade/withdraw key-like values fail fast.

### Task 3: Market Data And Skill Runtime

- [ ] Add OKX public market adapter for ticker, mark price, index price, funding, open interest, order book, and candles.
- [ ] Add deterministic fixture provider for tests.
- [ ] Add skill runtime that reads vendored skill metadata/hash and prepares a long-timeout prompt packet.
- [ ] Add mock decision engine and command-backed decision engine interfaces.

### Task 4: Plan Parsing, Risk, Journal, Notification

- [ ] Parse strict JSON decision plans.
- [ ] Reject invalid enum, missing stop on new opens, expired plan, stale data, and risk violations.
- [ ] Persist runs and notification attempts to SQLite.
- [ ] Send Bark notifications with timeout, retry, truncation, and secret redaction.

### Task 5: CLI And Scheduler

- [ ] Add CLI commands: `run-once`, `scheduler`, `test-bark`, `show-config`, `record-outcome`.
- [ ] Add scheduler interval config and SQLite job lock to avoid overlap.
- [ ] Ensure failures fail closed and can optionally send failure notifications.

### Task 6: Docs And Verification

- [ ] Add operation, deployment, and configuration docs.
- [ ] Run pytest.
- [ ] Run Docker Compose config validation.
- [ ] Run a dry-run CLI fixture flow.

