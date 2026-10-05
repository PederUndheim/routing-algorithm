---
name: implement-lean
description: Implement one clearly understood change with fast visible feedback, no subagents, targeted context, and lightweight user checkpoints. Use after align-with-docs or from a concise plan.
disable-model-invocation: true
---
# Implement Lean

Implement the current agreed change without subagents and without adding process that does not reduce risk.

## Load minimal context
1. Read `WORKING.md`.
2. If it names a plan, read that plan. Otherwise use the shared understanding in `WORKING.md`.
3. Read only relevant `CONTEXT.md` sections and source files.
4. Expand the search only when an import, call site, error, or uncertainty requires it.

Before editing, state in at most 4 bullets:
- the user-visible result,
- the first small slice,
- likely files,
- how the user can check it.

## Implementation loop
1. Make the smallest coherent slice that produces visible or inspectable progress.
2. Use the cheapest relevant check. Prefer existing commands and checks; do not introduce a testing framework or broad review process unless requested or clearly necessary.
3. Pause at a useful checkpoint and tell the user exactly what to inspect or try in VS Code or the running application.
4. Incorporate feedback, then continue with the next slice.
5. Keep unrelated improvements out of scope. Note them briefly in `WORKING.md` only if they matter.

## Autonomy boundaries
Continue without asking when the choice is local, reversible, and consistent with established conventions. Stop for the user when a choice changes behavior, scope, data, public interfaces, or is expensive to reverse.

## Token discipline
- Do not narrate routine file reads or every edit.
- Do not repeat the full plan after each step.
- Report diffs by purpose, not line-by-line.
- Do not reopen files already understood unless changed or contradicted.
- Prefer one targeted check over a broad suite when risk is low.

## Finish
Update `WORKING.md` with current state and one next action. Report only:

```markdown
Changed:
How to check it:
Known limitations:
Next action:
```

Use `/save-learning` only if this work revealed durable knowledge.
