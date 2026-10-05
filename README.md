# Common Understanding Skills

A small workflow inspired by Matt Pocock's `grill-with-docs`, adjusted for a small project and interactive work in the Claude Code pane in VS Code.

## Skills
- `/align-with-docs`: inspect the repo, interview in dependency-aware rounds, and save resolved understanding as it emerges.
- `/make-plan`: optional compact plan. It creates no tickets.
- `/implement-lean`: implement in small visible slices with lightweight user checkpoints.
- `/save-learning`: persist only durable discoveries.

## Default flow

```text
/align-with-docs -> /implement-lean
```

Add `/make-plan` only when the work spans several steps or sessions.

## Context model
- `CONTEXT.md`: stable knowledge, kept small.
- `WORKING.md`: replaceable state for the current change.
- `docs/decisions/`: only consequential decisions.
- `plans/`: only when a plan pays for itself.

## Install in VS Code without a terminal
Copy `.claude`, `CONTEXT.md`, and `WORKING.md` to the root of the repository. Restart or open a fresh Claude Code conversation, then enter `/align-with-docs`.
