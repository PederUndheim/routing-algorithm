---
name: align-with-docs
description: Build a strong shared understanding of a proposed change by inspecting the relevant code, interviewing the user in dependency-aware rounds, and saving only durable vocabulary and decisions. Use manually at the start of a fuzzy or meaningful change.
disable-model-invocation: true
---
# Align With Docs

Create a trustworthy shared understanding before implementation. Work in the current conversation without subagents.

## Principles
- Understanding comes before planning.
- Inspect before asking. Do not ask the user what the repository can answer cheaply.
- Ask the full current frontier: questions that can be answered now and whose answers may change the design.
- Do not ask a question that depends on an unresolved earlier answer.
- The user decides. Recommendations must be explicit and must not be presented as settled facts.
- Continue until important assumptions are resolved, not until an arbitrary question limit is reached.
- Conserve context by reading targeted paths, symbols, and nearby tests or documentation, not the entire repository.

## Start
1. Restate the proposed outcome and what appears uncertain.
2. Read `CONTEXT.md` and `WORKING.md` if present.
3. Locate the relevant entry points using filenames, search, imports, and symbols.
4. Read only enough code to map current behavior, vocabulary, boundaries, and constraints.
5. Maintain a short internal decision tree. Do not print a large plan.

## Interview loop
Ask questions in rounds. A normal round contains 2 to 5 independent questions.

Format every question as:

```markdown
❓ 1. Short decision title
Why this changes the solution, plus the concrete options.
➡️ Recommendation: one option and a short reason.
```

After each answer round:
1. Reflect the decisions in a short summary.
2. Correct the model of the change.
3. Save newly resolved durable information immediately according to the documentation rules below.
4. Ask the next frontier only.

Challenge contradictions, ambiguous terms, hidden scope, unclear ownership, failure behavior, and assumptions about current code. Accept `I don't know`; record it as open rather than manufacturing certainty.

## Documentation rules
Write only when something has genuinely crystallized.

### `CONTEXT.md`
Use for stable vocabulary, invariant constraints, and a concise architecture map. Keep it small. Update existing entries rather than duplicating them.

### `docs/decisions/YYYY-MM-DD-short-title.md`
Use only when a decision is costly to reverse, affects future work, or has plausible alternatives. Include context, decision, alternatives, and consequences. Do not create a decision record for ordinary implementation choices.

### `WORKING.md`
Use for the current change only: goal, settled boundaries, unresolved questions, relevant paths, and next action. Replace stale content rather than accumulating history.

Never save transcripts, long summaries, copied source code, speculative ideas, or facts that are cheap to rediscover.

## Finish
Finish when outcome, boundaries, key behavior, and major constraints are mutually understood. Return:

```markdown
## Shared understanding
Outcome:
Current behavior:
Agreed behavior:
In scope:
Out of scope:
Important constraints:
Open questions:
Relevant code:
Suggested next move: implement | make-plan | investigate
```

Then update `WORKING.md`. Recommend `implement` when the change is clear and manageable in one session. Recommend `make-plan` only when ordering or cross-session continuity adds real value. Recommend `investigate` when evidence, not discussion, is missing.
