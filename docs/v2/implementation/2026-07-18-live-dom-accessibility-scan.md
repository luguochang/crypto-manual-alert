# 2026-07-18 Live DOM Accessibility Scan

## Finding

The live partial-failure Work page rendered the expected evidence state, but a
deep DOM scan found one unnamed control: the visually labelled Bark notification
checkbox was wrapped by a label while the hidden input itself had no explicit
accessible name.

## Fix

`frontend/src/features/work/work-surface.tsx` now gives the checkbox the
explicit accessible name `完成后通知 Bark`. The visual structure, state model,
submit payload and notification behavior are unchanged.

## Verification

- Frontend unit tests: `368 passed` in `30 files`.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm run build`: passed; `14` routes generated.
- `git diff --check`: passed.
- Live Work page: `rawJson=0`, `horizontalOverflow=0`, `unnamedControls=0`.
- Frontend health probe: HTTP `200`.
- Official Agent Server docs probe: HTTP `200`.

This is a local DOM/accessibility correction. It does not prove hosted OIDC,
licensed Agent Server durability, production notification delivery or release
acceptance.

