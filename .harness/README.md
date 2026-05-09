# Agent harness (POC)

A minimal Docker-based runner that drives `claude` against a single GitHub issue, using your **Claude subscription** (not an API key).

This is the smallest possible thing that proves "subscription token can drive an agent inside Docker." It is intentionally **not** a Sandcastle replica — no parallelism, no plan/review/merge phases, no orchestrator. Once this works end-to-end, additional phases can be layered on.

## How it works

```
┌─ host (Windows / Docker Desktop) ─────────────────────────┐
│                                                            │
│  ~/.claude/.credentials.json   (OAuth, subscription auth)  │
│  Windows Credential Manager    (gh auth token)             │
│  qr_code_generator/            (this repo)                 │
│       │                                                    │
│       ▼ docker run                                         │
│  ┌─ container (qr-agent:latest) ─────────────────────────┐ │
│  │                                                       │ │
│  │  /home/agent/.claude/.credentials.json  (writable)    │ │
│  │  $GH_TOKEN env var                      (from host)   │ │
│  │  /workspace/                            (RW mount)    │ │
│  │                                                       │ │
│  │  $ claude -p "$(cat /tmp/implement-prompt.md)"        │ │
│  │           --max-turns 50 --add-dir /workspace          │ │
│  │                                                       │ │
│  │  agent → reads issue via gh, writes code, commits     │ │
│  └───────────────────────────────────────────────────────┘ │
│       │                                                    │
│       ▼ container exits                                    │
│  qr_code_generator/  ← new branch with the agent's commits │
└────────────────────────────────────────────────────────────┘
```

Two credentials cross the boundary by different mechanisms:

- **Claude OAuth** — `~/.claude/.credentials.json` is bind-mounted read-only into the container, then *copied* to a writable location inside so OAuth refresh works without touching the host file.
- **GitHub token** — On Windows, `gh` keeps the token in Credential Manager (not in `hosts.yml`), so we shell out to `gh auth token` on the host and pass the result as `GH_TOKEN` env var. The container's `gh` CLI auto-detects this and behaves identically to a logged-in install.

The host's `.credentials.json` is never written to from the container, and the GitHub token never gets persisted in any file the container can see beyond its own process env.

## Prerequisites

1. **Docker Desktop running** on Windows.
2. **Claude logged in on host:** `claude login` (populates `~/.claude/.credentials.json`).
3. **GitHub CLI logged in:** `gh auth login` (token is stored in Windows Credential Manager; verified by `gh auth status` showing "Logged in to github.com").
4. **Repo cloned and you are inside it.**

## Build the image (one time, ~5 min)

```powershell
docker build -t qr-agent:latest .\.harness\
```

Re-run this whenever `.harness/Dockerfile` changes (typically: never, after the first successful build).

## Step 1 — Smoke test (verify auth works inside the container)

```powershell
pwsh .\.harness\run-hello.ps1
```

Expected output: the agent prints `PONG`. If you see "Not authenticated" or model-error noise, your subscription token isn't reaching the CLI inside the container; check Docker Desktop's file-sharing settings and ensure `~/.claude` is on a shared drive.

## Step 2 — Run on a real issue

```powershell
pwsh .\.harness\run-issue.ps1 -Issue 7
```

This runs the agent against issue #7 (Slice 1: project skeleton) with up to 50 agent turns. The container exits when the agent says it's done; the script then prints the new local branches and any uncommitted state on the host.

To override the turn budget:

```powershell
pwsh .\.harness\run-issue.ps1 -Issue 7 -MaxTurns 30
```

## What the agent CAN and CANNOT do

The implement prompt in `prompts/implement.md` enforces:

- ✅ Create a feature branch `slice-{N}-...`
- ✅ Implement the issue's acceptance criteria
- ✅ Write tests for modules called out in the AC
- ✅ Commit on the local branch
- ❌ Push to `origin` (the host operator does this after review)
- ❌ Modify `main`
- ❌ Touch `.harness/`, `.sandcastle/`, or `.claude/`
- ❌ Close the issue

## Cost / rate-limit reality (Pro subscription)

- Pro has a 5-hour message window. A single 50-turn implementer can consume a meaningful fraction of one window depending on tool use.
- **Run one issue at a time.** Parallelism with this harness will hit your rate limit before it finishes. If you want N issues in parallel, use the API and pay separately (that's what `.sandcastle/` is for).
- If a run crashes mid-way for rate-limit reasons, the partial commits are still on the local branch. You can `git reset --hard origin/main` and retry, or amend.

## Known gaps vs Sandcastle

| Sandcastle feature | This harness | Notes |
|---|---|---|
| Multi-issue planning | ❌ | You name the issue manually |
| Parallel execution | ❌ | Single container at a time |
| Reviewer pass | ❌ | Add later if implementer alone isn't reliable |
| Auto-merge | ❌ | You merge on host with `gh pr merge` or `git merge` |
| MCP server config | ⚠️ | Inherits from `~/.claude/settings.json`; not yet copied into container |
| Hooks | ❌ | Settings hooks aren't propagated; add if needed |

## When this stops being enough

You'll outgrow this harness when any of:

1. You want N issues running concurrently → switch to API (Sandcastle as-is, or build a similar TS orchestrator).
2. The implementer's output quality drops without a reviewer → add a `run-review.ps1` that runs a second container on the same branch.
3. Rate-limit failures dominate → switch to API.
4. You want unattended overnight runs → add a TS/Python orchestrator that loops `run-issue.ps1` over a queue.

Each upgrade is additive. The Dockerfile stays the same.
