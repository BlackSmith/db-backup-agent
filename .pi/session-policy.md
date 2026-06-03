# Session Policy

## Purpose

This policy defines how future agent sessions should work on this repository.

## Required reading order

Before making changes, read:

1. `/home/vscode/.pi/agent/AGENTS.md`
2. `.pi/context.md`
3. `.pi/architecture.md`
4. the relevant `.pi/tasks/*.md` file
5. any additional local instructions

## Session roles

### Architect session
Use for:

- architecture analysis
- task shaping
- planning and sequencing work
- documenting design decisions
- preparing coder handoffs

Architect sessions must not modify application source files outside `.pi/`.

### Coder session
Use for:

- implementing a single task
- making minimal localized code changes
- writing the corresponding `.pi/done/<task>.md`
- running targeted verification
- creating exactly one commit per task when requested

## Task execution rules

- Prefer one task per coder session.
- Keep implementation changes localized.
- Do not change unrelated files.
- Preserve existing behavior unless the task explicitly requires a change.
- If requirements are ambiguous, stop and ask for clarification.
- If implementation work spans multiple architectural concerns, prefer a short handoff rather than a large guess.

## Documentation rules

- New agent-authored content must be written in English.
- If architecture or workflow changes meaningfully, update `.pi/context.md` after the work is understood.
- If the architecture itself changes, update `.pi/architecture.md` with a concise note or addendum.
- Keep `.pi/done/` notes factual, short, and task-specific.

## Verification rules

- Run focused tests for the changed area when possible.
- Prefer repository-native test commands.
- Report the exact verification steps in the task completion note.

## Handoff rules

When a task is ready for implementation, prepare a coder handoff that includes:

- objective
- scope
- constraints
- acceptance criteria
- any relevant design caveats

If the user asks for implementation and the architecture is clear, the coder session may proceed directly; otherwise, stop and clarify first.
