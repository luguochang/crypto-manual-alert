# Checkpoint 1 Current State Freeze

Date: 2026-07-02

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Git State

`git status --short` summary at freeze time:

- Modified: 31
- Deleted: 36
- Untracked: 68
- Renamed: 0
- Other: 0
- Total: 135

Interpretation:

- The dirty tree is expected for the ongoing directory migration. Old root-package modules are deleted while canonical subpackages are present as untracked files.
- This record does not mark the repository clean and does not commit or revert any user/previous changes.
- The next implementation checkpoint must continue working with this dirty tree and must not assume a clean baseline.

Root-package deletion mapping checked:

| Old root file | Canonical target |
|---|---|
| `cli.py` | `cli/__init__.py`, `cli/main.py`, `cli/__main__.py` |
| `config.py` | `config/` |
| `domain.py` | `domain/` |
| `frozen_input.py` | `decision/frozen_input.py` |
| `journal.py` | `storage/journal.py` |
| `llm_telemetry.py` | `telemetry/llm.py` |
| `market_data.py` | `market/providers.py` |
| `notifier.py` | `notification/sinks.py` |
| `observability.py` | `telemetry/observability.py` |
| `plan_parser.py` | `decision/plan_parser.py` |
| `research.py` | `research_pipeline/core.py` |
| `risk.py` | `decision/risk.py` |
| `runner.py` | `cli/main.py`, `workflow/executor.py`, `workflow/legacy_plan_runner.py` |
| `scheduler.py` | `workflow/scheduler.py` |
| `skill_runtime.py` | `skills/runtime.py` |

## Structure Facts

- `src/crypto_manual_alert/*.py` contains only `__init__.py`.
- `tests/` root contains no direct `.py` test or local script files.
- Local stack scripts live under `tools/local_stack/`.
- `src/`, `tests/`, and `tools/` `__pycache__` directories were removed after verification.

## Documentation State

- `README.md` now explicitly states that production still runs the legacy prompt chain and that Agent Swarm modules are shadow/candidate/replay side paths.
- `docs/formal/00-文档索引.md` now lists document 31 as the current checkpoint tracking entry.
- Documents 29 and 30 remain design/contract references; new execution records should go under `docs/migration/` or `docs/implementation/`.

## Verification

Commands run:

```powershell
python -m pytest tests/structure/test_root_package_structure.py tests/structure/test_tests_layout.py -q
python -m pytest tests/structure -q
```

Observed result:

- Root package and test layout checks: 9 passed.
- Full structure suite: 78 passed.

## Remaining Boundary

Checkpoint 1 freezes and clarifies the current state. It does not complete the full Agent Swarm migration and does not switch production final input to `DecisionInput`.
