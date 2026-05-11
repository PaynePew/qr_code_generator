# Coding Standards (harness review)

The review agent loads this file via `/workspace/.harness/CODING_STANDARDS.md` and enforces these standards during code review. Implementation agents are *not* required to read it during their pass — keeping it review-only saves implementer tokens and gives the review phase a clear job.

## Style

### TypeScript / React

- Prefer **named exports** over default exports.
- No `any`. If unavoidable, comment why on the same line.
- Function components only. Hooks at top level.
- Reach for `useCallback` / `useMemo` only when there is a measurable referential-identity reason — not by default.
- Tailwind: keep class lists short. If you need `cn(...)` with > 6 conditional classes, extract a sub-component instead.
- File naming: `PascalCase.tsx` for components, `camelCase.ts` for utilities and hooks.

### Python

- `snake_case` for functions and variables, `PascalCase` for classes.
- Type hints on every public function.
- Prefer `pathlib.Path` over `os.path`.
- Use dataclasses or Pydantic models — not raw dicts — for structured data crossing module boundaries.

## Commits

- Conventional Commits: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`.
- Subject line ≤ 72 chars, imperative mood (`add X`, not `added X`).
- Body explains **why**, not what (the diff already shows what).
- One logical change per commit. Refactors live in their own commits, not bundled with feature work.

## Tests

- Every new public function gets at least one test.
- Test names describe behavior, not implementation: `'rejects 4xx with normalized ApiError'` ✅, `'test1'` ❌.
- **Frontend:** Vitest + msw for HTTP. No global `fetch` mocking.
- **Backend:** pytest, fixtures over per-test setup/teardown.
- Tests for the same module live in `<module>.test.ts(x)` next to the source.

## Architecture

- Single Responsibility per module. If a file does two things, split it.
- **Frontend:** keep page components thin; push logic into hooks (`use*`) or utilities under `src/lib/`.
- **Backend:** routes thin, services hold business logic, repositories hold persistence.
- Domain language must match `CONTEXT.md`. Don't introduce a new term without updating CONTEXT.md in the same branch.

## What NOT to do

- No `console.log` in committed code. (Same for `print()` in committed Python code outside scripts.)
- No hardcoded secrets — env vars, validated at startup.
- No silent error swallowing. At minimum: log + rethrow. Better: handle it deliberately at a known boundary.
- No backwards-compat shims for unreleased code paths. The product hasn't shipped yet — just change the code.
- No mutation of function arguments. Spread or build new.
- No `as any` / `// @ts-ignore` / `# type: ignore` without an inline comment explaining why.
- No nested ternaries. Use `if/else` or extract a helper.
