# Harness extraction prep — handover doc

**Goal:** make `.harness/` generic enough to extract as a standalone repo for reuse in other projects. After all steps below pass, do a `git subtree split` and push to a new GitHub repo.

**Branch:** `kanban-harness-genericize`

**To resume:** open this file, jump to the first unchecked step, follow its instructions. Each step is one logical commit.

---

## Audit summary (frozen — don't redo)

| Tier | Severity | What | Files |
|---|---|---|---|
| 1 | 🔴 Must | hardcoded `PaynePew/qr_code_generator` repo name | `config.yml:11`, 6 fixtures in `tests/fixtures/*.yml` |
| 2 | 🟡 Strong | hardcoded test/build commands assuming Python+JS layout | `config.yml:36,39`, `Dockerfile:4-5` (comments), `README.md:207,210` |
| 3 | 🟠 Real bug | `run.ps1:383` and `run.sh:115` ignore `cfg.docs.adr_dir` and hardcode `docs/adr` | `run.ps1`, `run.sh` |
| 4 | 🟢 Nice | per-project content shipped as the example (CODING_STANDARDS describes React/Pydantic) | `CODING_STANDARDS.md`, `README.md:5` (PRD #27 link) |

**Generic-clean (don't touch):** `lib/`, `prompts/`, `Dockerfile` install logic, `run.ps1`/`run.sh` main flow, `tests/` test logic. Already use `{{KEY}}` substitution or config-driven.

**Not actually a coupling (don't touch):** `kanban-issue` branch_prefix in fixtures and code comments — used as a sample value, the real value comes from `cfg.branch_prefix`. Renaming would be cosmetic-only and risk breaking tests.

---

## Step 1 — Fix Tier 3 (real bug: ADR path leak)

**Files:** `.harness/run.ps1`, `.harness/run.sh`

**Change:** replace the hardcoded `docs/adr` fallback with config-driven lookup. Fallback to empty string when config doesn't specify (then no ADR list is injected into the plan prompt).

**Before:**
```powershell
# run.ps1:383
$adrDir   = "$RepoRoot/docs/adr"
```
```bash
# run.sh:115
ADR_DIR="$REPO_ROOT/docs/adr"
```

**After:**
```powershell
$adrDirRel = if ($cfg.ContainsKey('docs') -and $cfg.docs.ContainsKey('adr_dir')) { $cfg.docs.adr_dir } else { '' }
$adrDir    = if ($adrDirRel) { Join-Path $RepoRoot $adrDirRel } else { '' }
```
(equivalent for bash)

**Test:** add a Pester test asserting that `run.ps1` reads `cfg.docs.adr_dir` (regression guard so this doesn't get re-hardcoded later).

**Commit:** `fix(harness): respect cfg.docs.adr_dir instead of hardcoded fallback`

**Status:** [x] DONE — see next commit

---

## Step 2 — Fix Tier 1 fixtures (rename project name in test fixtures)

**Files:** `.harness/tests/fixtures/*.yml` (6 files)

**Change:** replace `PaynePew/qr_code_generator` with `acme/example` in:
- `valid-config.yml`
- `flat-layout-config.yml`
- `agents-config.yml`
- `minimal-config.yml`
- `missing-tracker-type.yml`
- `missing-tracker-repo.yml` (verify if it has the line; some don't)

Also check `load-config.Tests.ps1` and `load-config.bats` for assertions tied to the old value — update them too.

**Commit:** `chore(harness): rename test fixtures to use generic acme/example`

**Status:** [x] DONE — see next commit

---

## Step 3 — Convert config.yml + CODING_STANDARDS.md to .example templates

**Files:**
- Move `.harness/config.yml` → `.harness/config.yml.example` (and update `run.ps1`/`run.sh` to look for both, real first then example)
- Move `.harness/CODING_STANDARDS.md` → `.harness/CODING_STANDARDS.md.example` (same dual-lookup in run.ps1)
- Update `.harness/.gitignore` to ignore the un-suffixed versions
- Update `prompts/review.md` reference path text (still says `.harness/CODING_STANDARDS.md`)
- Update `tests/legacy-retired.Tests.ps1` and `legacy-retired.bats` if they assert on the file
- Update `tests/review-prompt.Tests.ps1` regression guard (it asserts `.harness/CODING_STANDARDS.md` exists — change to assert `.example` exists)

**Important:** Inside the QR project itself, copy `.example` back to the un-suffixed names so the harness keeps working as before. Verify smoke-test still works after.

**Commit:** `refactor(harness): ship config.yml and CODING_STANDARDS.md as .example templates`

**Status:** [ ] todo

---

## Step 4 — Tier 2 cosmetics (Dockerfile + example test commands)

**Files:**
- `.harness/Dockerfile` lines 4–5: change comments from "frontend build / backend pytest" to generic "Node for JS-based projects, Python for Python-based projects"
- `.harness/config.yml.example` lines 36, 39: change `pytest backend/ && npm test --prefix frontend` to placeholder like `pytest .` and `# typecheck: { block: <your typecheck command> }`
- `.harness/README.md` lines 207, 210: same as above

**Commit:** `chore(harness): generic-ize Dockerfile comments and example commands`

**Status:** [ ] todo

---

## Step 5 — Tier 4 content templating (CODING_STANDARDS + README PRD link)

**Files:**
- `.harness/CODING_STANDARDS.md.example`: rewrite as generic skeleton with placeholder sections (TypeScript, Python, Tests, Architecture, What NOT to do) — strip qr-specific bullets like "Tailwind class lists", "Pydantic models". Leave instructive comments like "<!-- Add your project's TS rules here -->".
- `.harness/README.md` line 5: replace `[PRD #27](https://github.com/PaynePew/qr_code_generator/issues/27)` with a generic mention of "design rationale lives in the ADR/PRD of this repo (TODO: link your own)".

**Commit:** `docs(harness): template-ize CODING_STANDARDS and remove qr-specific PRD link`

**Status:** [ ] todo

---

## Step 6 — Verify

Run full Pester suite. Expect 201 (current count) or higher (if Step 1 added a regression test).

```powershell
Invoke-Pester .harness/tests/ -Output Normal
```

Run smoke-test to confirm QR project still works after all the .example refactoring:

```powershell
pwsh ./.harness/run.ps1 -SmokeTest
```

**Status:** [ ] todo

---

## Step 7 — Open PR + merge

```bash
git push -u origin kanban-harness-genericize
gh pr create --title "refactor(harness): genericize for extraction to standalone repo" --body "..."
# wait for CI
gh pr merge <N> --merge --delete-branch
```

**Status:** [ ] todo

---

## Step 8 — Extract to standalone repo (needs USER input)

**Pause and ask user for:**
1. New GitHub repo name (suggested: `agent-harness` under their account/org)
2. Whether they want to use `git subtree split` (preserves history; can push back changes from QR later) or just `git filter-repo` (cleaner but cuts the link)

Then:
```bash
# B-1 with git subtree split:
git subtree split --prefix=.harness -b extracted-harness
# (user creates empty repo on GitHub: https://github.com/<owner>/agent-harness)
git push https://github.com/<owner>/agent-harness.git extracted-harness:main

# Verify by cloning fresh and inspecting
git clone https://github.com/<owner>/agent-harness.git /tmp/check
ls /tmp/check
```

After this, optionally delete `.harness/` from QR and re-add via subtree to get future updates:
```bash
git rm -rf .harness/
git commit -m "chore: prepare to consume .harness via subtree"
git subtree add --prefix=.harness https://github.com/<owner>/agent-harness.git main --squash
```

(Skip the re-add step if you'd rather keep .harness/ as a one-time copy.)

**Status:** [ ] todo

---

## Step 9 — Cleanup

Once extraction succeeds:
- Delete `EXTRACTION_PLAN.md` (this file)
- Update `CLAUDE.md` and `CONTEXT.md` if they mention `.harness/` extensively
- Consider archiving the legacy `.harness/CODING_STANDARDS.md` content somewhere project-specific in QR (since it had real value, just lived in the wrong spot)

**Status:** [ ] todo

---

## Handover notes

- Each step is one commit. After completing a step, mark it `[x] done in <commit-hash>` and move on.
- If a step turns out to be more work than estimated, add a sub-step rather than expanding the original.
- All work happens on branch `kanban-harness-genericize`.
- Don't merge to main until Step 7 explicitly.
- Step 8 is the only one that needs user input (new repo name).
- If Pester drops below 201 at any point, stop and investigate — don't push through failures.
