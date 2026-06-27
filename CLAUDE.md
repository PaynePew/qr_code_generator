## Agent skills

### Issue tracker

**Primary tracker is bd (beads)** — bd is the **source of truth**. See the "Beads Issue Tracker" section below and `docs/agents/issue-tracker.md`. All new issues, including those produced by the `to-issues` and `triage` skills, go into bd via the `bd` CLI.

**GitHub Issues mirrors bd** (`PaynePew/bbqrcode-generator`) **one-way, local→GitHub only**. bd is the source of truth; GitHub is a read-only window for non-terminal stakeholders. ⚠️ **Do NOT run bare `bd github sync`** — it defaults to *bidirectional + `--prefer-newer`*, so GitHub's stale state gets pulled back and **re-opens locally-closed beads** (on 2026-06-03 it reverted 6 closed foundation slices + the ttb epic). Publish progress with push-only instead:

```bash
bd github push <ids>                         # curated: push specific beads (= sync --push-only --issues <ids>)
bd github sync --push-only --prefer-local    # push ALL non-closed beads, local always wins
pwsh -File scripts/bd-publish-loop.ps1       # periodic push-only loop; safe to run WHILE slice-workflow runs
```

`--push-only` never modifies the local DB, so you can publish continuously during a slice-workflow run without it clobbering your beads. ⚠️ `bd dolt push` does **not** put issues on GitHub's Issues tab (it only syncs the Dolt ref `refs/dolt/data`) — use push-only for GitHub. Token auto-loads from `.beads/.env` (gitignored); refresh on 401 by rewriting `GITHUB_TOKEN=$(gh auth token)` into that file. Caveat: a full push mirrors **all non-closed beads** (incl. `hitl`/throwaway), so `bd delete <id> --force` any junk bead *before* pushing; after a delete run `bd export -o .beads/issues.jsonl` to clear the stale-jsonl warning, and **never** run `bd init --from-jsonl` (it resurrects deleted beads). Pre-bd GitHub issues (#23–#26) are historical — link one with `bd create ... --external-ref gh-<number>`. Full operational detail: bd memory `github-issue-mirror-via-bd-github-push` and `do-not-run-bd-github-sync-on-this`.

### Triage labels

Default label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), applied with `bd label add`. Note that `bd ready` natively replaces the `ready-for-agent` gate (open issue + no open blockers). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` and `docs/adr/` at repo root. See `docs/agents/domain.md`.

## Planning Document Rule

When writing `prompts/plan.md`, `prompts/implement.md`, `prompts/review.md`, or `prompts/merge.md`, delegate to an Agent sub-task with `model="opus"` instead of writing directly. After the agent completes, resume with the current model.

## Frontend Development Workflow

- Use the loaded `frontend-skill` to ensure best practices for React, Tailwind and UI design.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
