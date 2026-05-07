# Domain Docs

**Layout:** Single-context

## Files

| File | Purpose |
|------|---------|
| `CONTEXT.md` | Project domain language, key concepts, and system overview |
| `docs/adr/` | Architectural Decision Records |

## Consumer rules

When a skill reads domain context:

1. Read `CONTEXT.md` at the repo root first
2. Read any ADRs in `docs/adr/` that are relevant to the current task
3. Prefer definitions from `CONTEXT.md` when there is ambiguity
4. Do not modify `CONTEXT.md` or ADRs unless the task is explicitly to update them

## Creating new ADRs

ADR files live in `docs/adr/` and follow the naming convention `NNNN-short-title.md` (e.g. `0001-use-qr-library.md`).
