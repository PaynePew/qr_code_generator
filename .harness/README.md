# Agent harness

A Docker-based runner that drives `claude` against the project's GitHub issue tracker, using your **Claude subscription** (not an API key), in three phases:

1. **Plan** — Opus 4.7 (default). Surveys open issues, deconflicts in-progress work, ranks the remainder, prints a single top candidate plus alternatives.
2. **Implement** — Sonnet 4.6 (default). Claims a branch atomically, reads the issue, scaffolds, writes tests in Red-Green-Refactor style, commits.
3. **Review** *(legacy two-phase script only — see [Legacy review path](#legacy-review-path))*.

Plan + Implement is the v1 surface (`run.ps1` / `run.sh`). It is intentionally **not** a Sandcastle replica — sequential, one issue at a time, host-side `git`.

## How it works

```
┌─ host (Windows / *nix) ──────────────────────────────────────────────┐
│                                                                       │
│  CLAUDE_CODE_OAUTH_TOKEN     (subscription auth, env var)            │
│  gh CLI                      (issue tracker access)                  │
│  qr_code_generator/                                                  │
│       │                                                              │
│       ├─ run.ps1 / run.sh (bare) ── plan agent (opus) ──────────────┐│
│       │       prints ranked candidates,                              ││
│       │       prompts "Run #N? [Y/n]"                                ││
│       │                                                              ││
│       ├─ run.ps1 -Issue N ── implement agent (sonnet) ──────────────┤│
│       │       claims branch atomically,                              ││
│       │       commits to the slice branch                            ││
│       │                                                              ││
│       └─ run.ps1 -SmokeTest ── one-prompt sanity check ─────────────┘│
│                                                                       │
│  qr_code_generator/  ← branch ready for PR                            │
└───────────────────────────────────────────────────────────────────────┘
```

Both phases run inside the same container image (rebuilt only when its `Dockerfile` hash changes) with the repo bind-mounted as `/workspace`. The OAuth token reaches the container by environment-variable reference — never embedded in the docker argv — so it does not appear in the host process listing.

## Prerequisites

1. **Docker Desktop running.**
2. **Claude subscription token in the environment.** `claude setup-token` then either export `CLAUDE_CODE_OAUTH_TOKEN` in your shell or drop it into `.harness/.env.local` (gitignored).
3. **GitHub CLI logged in:** `gh auth login` — verify with `gh auth status`.
4. **Repo cloned and you are inside it.**

You do not need to `docker build` by hand. The wrappers SHA-256 the `Dockerfile`, compare to `.harness/.image-hash`, and rebuild only when the file changes (or when the image is gone locally).

## Config

`.harness/config.yml` is loaded once per run. Required keys:

```yaml
image:          agent-harness:latest      # docker image tag the harness builds + uses
branch_prefix:  kanban-issue              # branches are named "{prefix}{N}-{slug}"
tracker:
  type:         github                    # only github is supported in v1
  repo:         PaynePew/qr_code_generator # passed to `gh --repo`
```

Optional:

```yaml
defaults:
  model:        claude-sonnet-4-6         # fallback when a phase omits its model

agents:
  plan:
    model:      claude-opus-4-7
    max_turns:  10
  implement:
    model:      claude-sonnet-4-6
    max_turns:  80

docs:
  context:      CONTEXT.md
  prd_dir:      docs/prd
  adr_dir:      docs/adr

tests:
  block:        pytest backend/ && npm test --prefix frontend

typecheck:
  block:        npm run typecheck --prefix frontend

commit:
  style:        Conventional Commits (feat/fix/test/docs/chore/refactor). One logical change per commit.
```

The loader rejects tab indentation (matches PS YAML contract) and fails fast on missing required keys.

## Running

### Plan only (decide what to ship next)

```powershell
pwsh ./.harness/run.ps1            # plan → confirm → exit (you copy the suggested -Issue command)
pwsh ./.harness/run.ps1 -Plan      # plan only, print ranking, never prompt
pwsh ./.harness/run.ps1 -Yes       # plan, skip confirmation prompt (still prints suggestion)
```

Or on *nix / CI:

```bash
./.harness/run.sh --plan
./.harness/run.sh --yes
```

The plan phase deconflicts against:
- local + remote-tracking branches matching `{branch_prefix}{N}-*` (issue N already claimed)
- open PRs whose `headRefName` matches the same pattern

In-progress issue numbers are passed to the planner so it never picks an issue someone else is already shipping.

### Implement on a chosen issue

```powershell
pwsh ./.harness/run.ps1 -Issue 30                # fresh claim
pwsh ./.harness/run.ps1 -Issue 30 -Resume        # resume an existing matching branch
```

The implementer:

- Creates `{branch_prefix}{N}-{slug-from-issue-title}` (atomic — fails if another terminal already claimed it).
- Reads the issue, optionally fetches a parent issue / PRD.
- Implements every AC, RGR-style. Runs `tests.block` and `typecheck.block` from config.
- Commits one logical change at a time using `commit.style` from config.
- Posts a structured COMPLETE or BLOCKED comment back to the issue.
- Never pushes to origin, never modifies `main`, never touches `.harness/` / `.sandcastle/` / `.claude/`, never closes the issue, never rewrites history.

### Smoke test

```powershell
pwsh ./.harness/run.ps1 -SmokeTest
```

Runs `prompts/smoke-test.md` (a one-line "say PONG") inside the container to verify the OAuth token, gh auth, and image are wired correctly.

### Resume after a rate-limit

When `claude` exits non-zero with `Rate limit exceeded` / `usage_limit_exceeded` in the log, the wrapper surfaces the exact resume command:

```powershell
pwsh ./.harness/run.ps1 -Issue 30 -Resume
```

Partial commits on the slice branch are preserved.

## Logs

- `.harness/logs/issue-{N}.log` — implement run output.
- `.harness/logs/plan-{timestamp}.log` — plan run output (raw stream-json).
- `.harness/logs/smoke-test.log` — smoke-test run.

`.harness/logs/` is gitignored except for `.gitkeep`.

## Files

| Path | Purpose |
|---|---|
| `Dockerfile` | Node 22 + Python 3 + git + gh + claude CLI; user is `agent` (UID 1000). |
| `config.yml` | Per-project config (see [Config](#config)). |
| `run.ps1` / `run.sh` | Twin entry points — plan, implement, smoke-test. |
| `lib/*.{ps1,sh}` | Pure-function modules (config loader, prompt renderer, deconflict scanner, image-cache check, branch claim, heartbeat reducer, plan parser). Mirrored across PS and bash. |
| `prompts/{plan,implement,smoke-test}.md` | Project-agnostic prompts rendered with `{{KEY}}` substitution. |
| `prompts/review.md` | Used only by the legacy `run-issue.ps1` (see below). |
| `tests/` | Pester + bats coverage for every `lib/` module. |
| `CODING_STANDARDS.md` | Loaded by the review prompt (legacy path) — not by implement. |

## Legacy review path

`run-issue.ps1` is the proof-of-concept that validated subscription auth and the two-phase **implement → review** loop. It still works and is the only way to trigger an automated Opus review pass today:

```powershell
pwsh ./.harness/run-issue.ps1 -Issue 7              # implement + review on slice-7-... branch
pwsh ./.harness/run-issue.ps1 -Issue 7 -SkipReview  # implement only
pwsh ./.harness/run-issue.ps1 -Issue 7 -SkipImplement # rerun review only
```

Caveats vs `run.ps1`:

- Uses the `slice-{N}-...` branch convention (not `branch_prefix` from config).
- Mounts `~/.claude/.credentials.json` into the container (not env-var auth).
- Hard-codes `qr-agent:latest` as the image tag — run `docker build -t qr-agent:latest .\.harness\` once before first use.
- Passes the GH token through `-e GH_TOKEN=...` (token visible in process listing on the host).

A `run.ps1`-native review phase will land when the four-phase pipeline (plan / implement / review / merge described in PRD 0002 and ADR 0008) is fully realized. Until then, use `run-issue.ps1` when you want an automated review pass.

## Cost / rate-limit reality (Pro subscription)

- Pro has a 5-hour message window. A two-phase implement+review run can consume a meaningful fraction.
- **One issue at a time.** Parallelism with this harness will hit your rate limit before it finishes.
- If a run crashes mid-way, partial commits stay on the local branch. Use `-Resume` to continue.
