---
name: make-plan
description: Turn an established shared understanding into a concise implementation plan for a change that spans several steps or sessions. Avoid for work that can be implemented directly.
disable-model-invocation: true
---
# Make Plan

Work without subagents. Read `WORKING.md`, relevant entries in `CONTEXT.md`, and only the source paths already identified.

Create `plans/<slug>.md` only if a plan reduces likely rework or preserves continuity across sessions. Otherwise say that direct implementation is cheaper.

Use this format:

```markdown
# <Outcome>
Status: ready | active | blocked | done

## Goal
One short paragraph.

## Boundaries
- In:
- Out:

## Current anchors
- `path` or symbol: why it matters

## Steps
1. A small complete change with its observable result.

## Checkpoints
- What the user should inspect or try after each meaningful step.

## Open questions
- Only unresolved items that can block or change implementation.

## Next action
Exactly one concrete action.
```

## Rules
- Prefer 3 to 7 steps.
- Do not create tickets or issues.
- Do not prescribe extensive tests or reviews by default.
- Include lightweight checks proportionate to the risk: run the feature, inspect the UI, check an output, compile, or run an existing targeted test.
- Link to durable docs instead of repeating them.
- If new product decisions appear, stop and return to `/align-with-docs`.
