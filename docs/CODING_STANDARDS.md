# Coding Standards

**Audiences (progressive disclosure — read only what your role needs):**
- **Implementer + Reviewer** read the **Core rules** and follow them while writing / refactoring.
- **Reviewer** additionally enforces **Binding by reference** (the full `CONTEXT.md` + ADR set) and runs the **Verification cheatsheet**.

The review agent loads this file as `{{CODING_STANDARDS_BLOCK}}`. If the implement step is wired to read it (via `AGENTS.md`), the implementer should read the **Core rules** and consult **only** the ADR(s) / `CONTEXT.md` entries relevant to the files it is touching (the issue should name them) — **not** the whole ADR set. Reading all ADRs on every task is the reviewer's job and would bloat implementer context for no per-task benefit.

Treat each rule as ground truth: refactor within turn budget, or flag in "Concerns" — never silently accept a violation.

> **Why this file stays small.** It holds only durable engineering principles. Architecture- and domain-specific facts are bound *by reference* (last substantive section), not copied here — so feature work that changes the architecture updates the relevant ADR / `CONTEXT.md`, and this file does not rot.

> This file is gitignored; `CODING_STANDARDS.md.example` is the tracked, identical template — re-create from it after a fresh checkout.

---

# Core rules (implementer + reviewer)

## Style — Python (backend/)

- `snake_case` for functions, variables, modules. `PascalCase` for classes / Pydantic models / SQLAlchemy models.
- **Type hints on every public function**, including `async def`. Prefer `X | None` and built-in generics (`list[int]`, `dict[str, X]`). Don't introduce new `Optional[X]` / `typing.List` — existing `Optional[...]` usages are being migrated, not a pattern to copy.
- `from __future__ import annotations` at the top of new modules.
- Use dataclasses / Pydantic models — not raw dicts — for structured data crossing **internal** module boundaries. (Shaping a `dict` at the router edge purely for an HTTP response body is fine.)
- Names read like the domain glossary (`CONTEXT.md`): `create_link`, `derive_state`, `reactivate_link` — never `do_create`, `handle_op`, `process`.

## Style — TypeScript / React (frontend/)

- Prefer **named exports** over default exports. No `any` — if unavoidable, comment why on the same line.
- Function components only; hooks at top level. Reach for `useCallback` / `useMemo` only when there's a measurable referential-identity reason — not by default.
- File naming: `PascalCase.tsx` for components, `camelCase.ts` for utilities and hooks. Tests live next to source as `<module>.test.ts(x)` — no parallel `__tests__/` tree.
- Keep Tailwind class lists short; if `cn(...)` needs > 6 conditional classes, extract a sub-component.
- Immutable updates only — spread or rebuild; never mutate state or props in place.

## Architecture — durable shape

- **Backend three layers:** HTTP (`router`, FastAPI, error mapping) → domain (pure logic, raises typed domain errors, **never imports a web framework**) → persistence (repositories own the SQLAlchemy queries; no business decisions inside a repository). Any HTTP/framework import (e.g. `from fastapi import …`) inside a domain module is a grep-enforceable review block.
- **Frontend:** page components stay thin; push logic into hooks (`src/state/**`, `src/lib/*`). When a module owns a contract, go through its public interface rather than reaching past it. *Which* module owns *which* contract is defined by the code and `CONTEXT.md`, not enumerated here (so it can't go stale).
- Introducing **new module-level mutable state** in the backend, or a **new external dependency / infrastructure** (cache, queue, object store, third-party API) that changes the runtime or deployment shape, needs an ADR. (There are documented exceptions — see the ADRs.)

## Tests

- A good test asserts **external behavior**, not implementation details: given inputs / requests, assert outputs, persisted state, and error / authorization outcomes — never private internals.
- Every new public function gets at least one test. Test names describe behavior: `'rejects 4xx with a normalized ApiError'` ✅, `'test1'` ❌.
- **Backend:** pytest; fixtures in `tests/conftest.py` (prefer fixtures over per-test setup/teardown). **Frontend:** Vitest + MSW for HTTP — no global `fetch` mocking.
- Run the **full** suite before claiming pass — a passing subset while the full run fails is not "tests pass." If the environment is broken and you can't run them, report **BLOCKED**; do not summarise expected results.
- Test-infrastructure details (engines, containers, harness wiring) live in the test setup itself, not here.

## Commits

- Conventional Commits: `feat | fix | refactor | test | docs | chore | perf | ci`. Subject ≤ 72 chars, imperative; scope in parens when meaningful (`feat(rate-limit):`, `fix(router):`).
- Body explains **why**, not what. When fixing a behavioural bug, name the surprising mechanism in one sentence.
- One logical change per commit; refactors live in separate commits from features.
- Reference the issue by its **tracker ID** in the body. This project uses **bd (beads)** — e.g. `Refs qr_code_generator-ab12`; a migrated GitHub issue is linked at creation via `bd create … --external-ref gh-N`.

## What NOT to do

- No `console.log` in committed TS/TSX. No `print()` in committed Python (outside one-off scripts) — use the project's logger.
- No `as any` / `// @ts-ignore` / `# type: ignore` without a same-line comment explaining why.
- No hardcoded secrets / hostnames / ports. Backend reads from env (validated at startup); frontend from `import.meta.env`.
- No silent error swallowing. At minimum log + rethrow; better, handle at a known boundary.
- No backwards-compat shims for unreleased code paths — the product hasn't shipped to real users; just change the code.
- No mutation of function arguments (spread or build new). No nested ternaries (use `if/else` or extract a helper).
- No new term, state, endpoint, or behavior that contradicts `CONTEXT.md` or an Accepted ADR — see **Binding by reference**.

---

# Reviewer-additional — Binding by reference

> **Implementers:** consult only the ADR(s) / `CONTEXT.md` entries that touch the files you're changing (your issue should name them). **Reviewers:** read these in full, every review.

These ARE review rules — read their current contents and treat them as ground truth:

- **`CONTEXT.md`** — the domain glossary. Using a defined term to mean something else, or introducing a new term / state / concept without updating `CONTEXT.md` in the same branch, is a review block.
- **`docs/adr/*.md` with `Status: Accepted`** — each ADR's **Decision** and **Consequences** are binding rules. When ADRs supersede one another, the superseding ADR wins (an Accepted ADR that says "supersedes NNNN" voids NNNN's rules). Always check a change against the *currently-accepted* set, never a snapshot.
- A change that violates an Accepted ADR — **or** that should have an ADR (a hard-to-reverse, surprising, genuine-trade-off decision) but ships without one — is a review block. Flag it.

This single section replaces every "per ADR 000X …" rule that would otherwise be duplicated above. Domain vocabulary, link/state semantics, dedup policy, analytics-privacy, rate-limit shape, auth / ownership, storage decisions, etc. all live in `CONTEXT.md` + the ADRs and are enforced from there.

---

## Verification cheatsheet (reviewer)

Before marking COMPLETE, run and cite the exit code of:

```bash
pytest tests/
npm test --prefix frontend
npm run typecheck --prefix frontend
```

Only the full run is a valid "tests pass" claim. If a venv / node_modules is broken and you could not execute the tests, report **BLOCKED** — do not summarise what you expect the tests would have done.
