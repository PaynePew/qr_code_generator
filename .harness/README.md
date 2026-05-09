# Agent harness

A Docker-based runner that drives `claude` against a single GitHub issue, using your **Claude subscription** (not an API key), in two phases:

1. **Implement** — Sonnet 4.6 (default). Reads the issue, scaffolds, writes tests in Red-Green-Refactor style, commits.
2. **Review** — Opus 4.6 (default). Checks out the same branch, reads the diff, applies safe refactors against `CODING_STANDARDS.md`, commits with `refactor:` prefix or no-ops.

It is intentionally **not** a Sandcastle replica — no parallelism across issues, no auto-merge, no orchestrator queue. Each `run-issue.ps1` invocation handles one issue end-to-end on the host.

## How it works

```
┌─ host (Windows / Docker Desktop) ─────────────────────────────────┐
│                                                                    │
│  ~/.claude/.credentials.json   (OAuth, subscription auth)          │
│  Windows Credential Manager    (gh auth token)                     │
│  qr_code_generator/            (this repo)                         │
│       │                                                            │
│       ├── docker run #1 ─── implement (Sonnet 4.6) ───────────┐    │
│       │       │                                               │    │
│       │       ▼ exits → branch slice-N-... has commits        │    │
│       │                                                       │    │
│       └── docker run #2 ─── review (Opus 4.6) ────────────────┤    │
│               │                                               │    │
│               ▼ exits → branch may have refactor: commits     │    │
│                                                                    │
│  qr_code_generator/  ← branch ready for PR                         │
└────────────────────────────────────────────────────────────────────┘
```

Two credentials cross the boundary by different mechanisms:

- **Claude OAuth** — `~/.claude/.credentials.json` is bind-mounted read-only, then *copied* to a writable location inside so OAuth refresh works without touching the host file.
- **GitHub token** — On Windows, `gh` keeps the token in Credential Manager (not in `hosts.yml`), so we shell out to `gh auth token` on the host and pass the result as `GH_TOKEN`. The container's `gh` CLI auto-detects this.

## Prerequisites

1. **Docker Desktop running** on Windows.
2. **Claude logged in on host:** `claude login` (populates `~/.claude/.credentials.json`).
3. **GitHub CLI logged in:** `gh auth login` — verify with `gh auth status`.
4. **Repo cloned and you are inside it.**

## Build the image (one time, ~5 min)

```powershell
docker build -t qr-agent:latest .\.harness\
```

Re-run this whenever `.harness/Dockerfile` changes.

## Step 1 — Smoke test

```powershell
pwsh .\.harness\run-hello.ps1
```

Expected output: `PONG`. Validates that subscription auth reaches the CLI inside the container.

## Step 2 — Run on a real issue

Default flow (implement → review):

```powershell
pwsh .\.harness\run-issue.ps1 -Issue 7
```

This runs **two containers** in sequence on the same `slice-7-...` branch:

1. **Implement (Sonnet 4.6):** reads issue #7, scaffolds, tests, commits.
2. **Review (Opus 4.6):** reads the diff, applies safe refactors per `CODING_STANDARDS.md`, commits with `refactor:` prefix (or skips if clean).

### Useful flags

| Flag | Default | Purpose |
|---|---|---|
| `-MaxTurns` | `60` | Per-phase budget. Slice-1 scaffold needed ~30; complex slices may need 80+. |
| `-ImplementModel` | `claude-sonnet-4-6` | Model used for the implement phase. |
| `-ReviewModel` | `claude-opus-4-6` | Model used for the review phase. |
| `-SkipReview` | off | Run implement only — useful when you'll review by hand. |
| `-SkipImplement` | off | Re-run review on an existing branch (e.g. after manual edits). |

Examples:

```powershell
# Implement-only run (skip the Opus review)
pwsh .\.harness\run-issue.ps1 -Issue 8 -SkipReview

# Re-run review on a branch you already have
pwsh .\.harness\run-issue.ps1 -Issue 7 -SkipImplement

# Override models — e.g. if claude-opus-4-6 is rejected by your CLI version
pwsh .\.harness\run-issue.ps1 -Issue 9 -ReviewModel claude-opus-4-7

# Bigger turn budget for a complex slice
pwsh .\.harness\run-issue.ps1 -Issue 11 -MaxTurns 100
```

## Files

| Path | Purpose |
|---|---|
| `Dockerfile` | Base image: Node 22, Python 3, git, gh, claude CLI; `node` user renamed to `agent` (UID 1000). |
| `run-hello.ps1` | Smoke test — verifies subscription auth works in the container. |
| `run-issue.ps1` | Two-phase orchestrator (implement → review). |
| `prompts/implement.md` | Implementation prompt — RGR discipline, branch contract, scope guards. |
| `prompts/review.md` | Review prompt — diff-driven refactor against `CODING_STANDARDS.md`. |
| `CODING_STANDARDS.md` | Project standards loaded by the reviewer (not the implementer — saves implement-phase tokens). |

## What the agents CAN and CANNOT do

Both phases enforce:

- ✅ Operate on a feature branch `slice-{N}-...`
- ❌ Push to `origin` (the host operator does this after inspection)
- ❌ Modify `main`
- ❌ Touch `.harness/`, `.sandcastle/`, `.claude/`
- ❌ Close the issue
- ❌ Rewrite history (no `--amend`, no rebase)

The implement phase additionally:

- ✅ Creates the branch, scaffolds, writes tests, commits with conventional-commit prefixes

The review phase additionally:

- ✅ Reads the diff and `CODING_STANDARDS.md`, applies safe refactors with `refactor:` commits
- ❌ Adds new features or expands scope (it flags those for the human instead)
- ❌ Changes WHAT the code does — only HOW

## Cost / rate-limit reality (Pro subscription)

- Pro has a 5-hour message window. A two-phase run can consume a meaningful fraction depending on tool use.
- **One issue at a time.** Parallelism with this harness will hit your rate limit before it finishes.
- If a run crashes mid-way for rate-limit reasons, partial commits stay on the local branch. You can `git reset --hard origin/main` and retry, or amend.
- If the implement phase succeeds but review hits a rate limit, the implementer's commits are preserved — you can `-SkipImplement` to re-run only the review later.

## Known gaps vs Sandcastle

| Sandcastle feature | This harness | Notes |
|---|---|---|
| Multi-issue planning | ❌ | You name the issue manually. |
| Parallel execution | ❌ | One container at a time. |
| Plan phase | ❌ | Planner agent isn't wired in (the implement prompt explores directly). |
| Reviewer pass | ✅ | Default-on, runs on Opus 4.6 against `CODING_STANDARDS.md`. |
| Auto-merge | ❌ | You merge on host with `gh pr merge` or `git merge`. |
| MCP server config | ⚠️ | Inherits from `~/.claude/settings.json`; not yet copied into container. |
| Hooks | ❌ | Settings hooks aren't propagated. |

## When this stops being enough

You'll outgrow this harness when:

1. You want N issues running concurrently → switch to API (Sandcastle as-is, or build a similar TS orchestrator).
2. Rate-limit failures dominate → switch to API.
3. You want unattended overnight runs → add an orchestrator that loops `run-issue.ps1` over a queue.

Each upgrade is additive. The Dockerfile and prompts stay the same.
