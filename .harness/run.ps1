#Requires -Version 7
<#
.SYNOPSIS
    Generic Docker agent harness entry point for Windows / PowerShell.
.PARAMETER Plan
    Run the plan phase only; print ranked candidates and exit.
.PARAMETER Yes
    Auto-confirm the top candidate from the plan phase (skip the Y/n prompt).
.PARAMETER SmokeTest
    Run the smoke-test prompt (validates plumbing without spending agent tokens).
.PARAMETER Issue
    Issue number. Skips plan and runs the implement agent directly.
.PARAMETER Resume
    Resume implement on an existing branch for the given -Issue. Fails if no
    matching branch exists. Cannot be used without -Issue.
.EXAMPLE
    pwsh ./.harness/run.ps1               # plan → confirm → exit
    pwsh ./.harness/run.ps1 -Plan         # plan only, print ranking
    pwsh ./.harness/run.ps1 -Yes          # plan + auto-confirm top candidate
    pwsh ./.harness/run.ps1 -Issue 30     # skip plan, claim + implement #30
    pwsh ./.harness/run.ps1 -Issue 30 -Resume
    pwsh ./.harness/run.ps1 -SmokeTest
#>
[CmdletBinding()]
param(
    [switch]$Plan,
    [switch]$Yes,
    [switch]$SmokeTest,
    [int]$Issue,
    [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HarnessRoot = $PSScriptRoot
$RepoRoot    = Split-Path $HarnessRoot -Parent

. "$HarnessRoot/lib/load-config.ps1"
. "$HarnessRoot/lib/render-prompt.ps1"
. "$HarnessRoot/lib/image-cache.ps1"
. "$HarnessRoot/lib/branch-claim.ps1"
. "$HarnessRoot/lib/heartbeat.ps1"
. "$HarnessRoot/lib/parse-plan.ps1"
. "$HarnessRoot/lib/scan-deconflict.ps1"

# ── Terminal rendering helpers ─────────────────────────────────────────────────

$script:AnsiOk = $false
try { $script:AnsiOk = [bool]$Host.UI.RawUI.SupportsVirtualTerminal } catch {}
$script:HbVisible = $false

function Write-RunHeader([string]$IssueLabel, [string]$Model, [string]$Branch, [string]$LogFile) {
    Write-Host "Issue: $IssueLabel  Agent: $Model  Branch: $Branch  Log: $LogFile" -ForegroundColor Cyan
}

function Write-HbLine([hashtable]$State) {
    $line = "  [turns=$($State.turns) elapsed=$($State.elapsed_s)s action=$($State.last_action)]"
    if ($script:AnsiOk -and $script:HbVisible) {
        Write-Host "`e[1A`e[2K$line"
    } else {
        Write-Host $line
    }
    $script:HbVisible = $true
}

function Close-HbLine([string]$Msg, [string]$Color = 'Green') {
    if ($script:AnsiOk -and $script:HbVisible) {
        Write-Host "`e[1A`e[2K$Msg" -ForegroundColor $Color
    } else {
        Write-Host $Msg -ForegroundColor $Color
    }
    $script:HbVisible = $false
}

function Format-Exclusions([System.Collections.Generic.HashSet[int]]$Set) {
    if ($Set.Count -eq 0) { return 'none' }
    ($Set | Sort-Object | ForEach-Object { "#$_" }) -join ', '
}

# ── Helpers ────────────────────────────────────────────────────────────────────

function Fail([string]$Msg, [string]$Remedy = '') {
    Write-Host "ERROR: $Msg" -ForegroundColor Red
    if ($Remedy) { Write-Host "  Run: $Remedy" -ForegroundColor Yellow }
    exit 1
}

function Step([string]$Label) {
    Write-Host "── $Label " -ForegroundColor Cyan -NoNewline
    Write-Host ('─' * [Math]::Max(0, 50 - $Label.Length)) -ForegroundColor DarkGray
}

# ── Pre-flight checks ──────────────────────────────────────────────────────────

Step 'Pre-flight checks'

# 1. CLAUDE_CODE_OAUTH_TOKEN
$token = $env:CLAUDE_CODE_OAUTH_TOKEN
if (-not $token) {
    $envFile = "$HarnessRoot/.env.local"
    if (Test-Path $envFile) {
        foreach ($line in (Get-Content $envFile)) {
            if ($line -match '^CLAUDE_CODE_OAUTH_TOKEN=(.+)$') {
                $env:CLAUDE_CODE_OAUTH_TOKEN = $Matches[1].Trim()
                $token = $env:CLAUDE_CODE_OAUTH_TOKEN
                break
            }
        }
    }
}
if (-not $token) { Fail 'Missing CLAUDE_CODE_OAUTH_TOKEN.' 'claude setup-token' }

# 2. Docker daemon
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'Docker daemon not running. Start Docker Desktop and retry.' }

# 3. gh auth
gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'Not authenticated with GitHub CLI.' 'gh auth login' }

# 4. git repo
if (-not (Test-Path "$RepoRoot/.git")) { Fail 'Not inside a git repository.' }

Write-Host '  All pre-flight checks passed.' -ForegroundColor Green

# ── Load config ────────────────────────────────────────────────────────────────

Step 'Loading config'
try {
    $cfg = Import-HarnessConfig -ConfigPath "$HarnessRoot/config.yml"
} catch {
    Fail "Config error: $_"
}
$imageName  = $cfg.image
$markerPath = "$HarnessRoot/.image-hash"
Write-Host "  image=$imageName  branch_prefix=$($cfg.branch_prefix)" -ForegroundColor DarkGray

# ── Image cache check / rebuild ────────────────────────────────────────────────

Step 'Image cache check'
if (Test-ImageRebuildNeeded -DockerfilePath "$HarnessRoot/Dockerfile" -MarkerPath $markerPath -ImageName $imageName) {
    Write-Host "  Rebuilding image: $imageName" -ForegroundColor Yellow
    docker build -t $imageName -f "$HarnessRoot/Dockerfile" "$RepoRoot"
    if ($LASTEXITCODE -ne 0) { Fail 'docker build failed.' }
    Save-ImageHash -DockerfilePath "$HarnessRoot/Dockerfile" -MarkerPath $markerPath
    Write-Host '  Image built and hash cached.' -ForegroundColor Green
} else {
    Write-Host '  Image up-to-date — no rebuild needed.' -ForegroundColor Green
}

# ── Select prompt, claim branch, build substitutions ──────────────────────────

$branchName     = ''
$implementModel = ''
$maxTurns       = ''

if ($SmokeTest) {
    $promptFile = "$HarnessRoot/prompts/smoke-test.md"
    $logFile    = "$HarnessRoot/logs/smoke-test.log"
    $runLabel   = 'smoke-test'
    $subs       = @{}
} elseif ($Issue) {
    $promptFile = "$HarnessRoot/prompts/implement.md"
    $logFile    = "$HarnessRoot/logs/issue-$Issue.log"
    $runLabel   = "issue-$Issue"

    # Derive kebab slug from issue title (used to form the branch name)
    $issueTitle = gh issue view $Issue --repo $cfg.tracker.repo --json title --jq '.title' 2>&1
    if ($LASTEXITCODE -ne 0) { Fail "gh issue view #$Issue failed: $issueTitle" }
    $slug = ($issueTitle -replace '[^A-Za-z0-9]+', '-').ToLower().Trim('-')
    if ($slug.Length -gt 40) { $slug = $slug.Substring(0, 40).TrimEnd('-') }
    if (-not $slug) { Fail "Could not derive slug from issue #$Issue title: '$issueTitle'" }

    # Atomic branch claim — exits with error if already claimed and no -Resume
    Step "Claiming branch"
    try {
        $branchName = Invoke-BranchClaim `
            -Prefix      $cfg.branch_prefix `
            -IssueNumber $Issue `
            -Slug        $slug `
            -Resume:$Resume
    } catch {
        Fail "$_" "pwsh ./.harness/run.ps1 -Issue $Issue -Resume"
    }
    Write-Host "  Branch: $branchName" -ForegroundColor Green

    $implementModel = $cfg.agents.implement.model
    $maxTurns       = $cfg.agents.implement.max_turns

    # Resolve substitution values from config (missing paths drop their line via render-prompt)
    $docsPrdDir     = if ($cfg.docs -is [hashtable])      { $cfg.docs.prd_dir }         else { '' }
    $docsContext    = if ($cfg.docs -is [hashtable])      { $cfg.docs.context }          else { '' }
    $docsAdrDir     = if ($cfg.docs -is [hashtable])      { $cfg.docs.adr_dir }          else { '' }
    $testsBlock     = if ($cfg.tests -is [hashtable])     { $cfg.tests.block }           else { '' }
    $typecheckBlock = if ($cfg.typecheck -is [hashtable]) { $cfg.typecheck.block }       else { '' }
    $commitStyle    = if ($cfg.commit -is [hashtable])    { $cfg.commit.style }          else { '' }

    $subs = @{
        ISSUE           = "$Issue"
        BRANCH          = $branchName
        DOCS_PRD_DIR    = $docsPrdDir
        DOCS_CONTEXT    = $docsContext
        DOCS_ADR_DIR    = $docsAdrDir
        TESTS_BLOCK     = $testsBlock
        TYPECHECK_BLOCK = $typecheckBlock
        COMMIT_STYLE    = $commitStyle
    }
} elseif ($Plan -or $Yes -or (-not $SmokeTest -and -not $Issue)) {
    # ── Plan phase (bare run, -Plan, or -Yes) ─────────────────────────────────
    Step 'Plan phase'

    $planModel    = $cfg.agents.plan.model
    $planMaxTurns = $cfg.agents.plan.max_turns

    $excluded = Get-DeconflictExclusions -BranchPrefix $cfg.branch_prefix
    Write-Host "  In-progress: $(Format-Exclusions $excluded)" -ForegroundColor DarkGray

    $adrDir   = "$RepoRoot/docs/adr"
    $adrNames = if (Test-Path $adrDir) {
        (Get-ChildItem $adrDir -Filter '*.md' | Select-Object -ExpandProperty Name) -join ', '
    } else { '' }

    $labelFlag = if ($cfg.tracker -is [hashtable] -and $cfg.tracker['filter_label']) {
        "--label '$($cfg.tracker.filter_label)'"
    } else { '' }

    $planSubs = @{
        REPO               = $cfg.tracker.repo
        BRANCH_PREFIX      = $cfg.branch_prefix
        IN_PROGRESS_LIST   = Format-Exclusions $excluded
        ADR_FILENAMES      = $adrNames
        TRACKER_LABEL_FLAG = $labelFlag
    }

    $planFile = "$HarnessRoot/prompts/plan.md"
    if (-not (Test-Path $planFile)) { Fail "Plan prompt not found: $planFile" }

    $rendered    = Invoke-RenderPrompt -Template (Get-Content $planFile -Raw) -Substitutions $planSubs
    $promptMount = "$HarnessRoot/.current-prompt.md"
    Set-Content -Path $promptMount -Value $rendered -Encoding UTF8

    $logFile = "$HarnessRoot/logs/plan-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
    $logDir2 = Split-Path $logFile -Parent
    if (-not (Test-Path $logDir2)) { New-Item -ItemType Directory $logDir2 | Out-Null }

    Write-RunHeader -IssueLabel '?' -Model $planModel -Branch '(pending)' -LogFile $logFile
    Write-Host "  max_turns=$planMaxTurns" -ForegroundColor DarkGray

    $hbState    = @{ turns = 0; elapsed_s = 0; last_action = '' }
    $accContent = [System.Text.StringBuilder]::new()

    $claudeCmd = "claude --output-format stream-json --model $planModel --max-turns $planMaxTurns -p `"`$(cat /workspace/.harness/.current-prompt.md)`""
    $dockerPlan = @(
        'run', '--rm',
        '--volume', "${RepoRoot}:/workspace",
        '--env',    'CLAUDE_CODE_OAUTH_TOKEN',
        '--workdir', '/workspace',
        $imageName,
        'bash', '-lc', $claudeCmd
    )

    try {
        & docker @dockerPlan 2>&1 | ForEach-Object {
            Add-Content -Path $logFile -Value $_
            try {
                $ev = $_ | ConvertFrom-Json -AsHashtable
                $hbState = Invoke-HeartbeatReduce -State $hbState -Event $ev
                if ($ev.type -eq 'assistant.text' -and $ev.ContainsKey('text')) { [void]$accContent.Append($ev.text) }
                if ($ev.type -eq 'result'         -and $ev.ContainsKey('result')) { [void]$accContent.Append($ev.result) }
                Write-HbLine -State $hbState
            } catch { }
        }
        $planExit = $LASTEXITCODE
    } finally {
        Remove-Item -ErrorAction SilentlyContinue $promptMount
    }

    if ($planExit -ne 0) {
        Close-HbLine "  FAILED: docker exit $planExit" -Color 'Red'
        exit $planExit
    }
    Close-HbLine "  Plan agent complete." -Color 'Green'

    $parsed = Invoke-ParsePlan -Content $accContent.ToString()
    if ($parsed.Error) {
        Write-Host "ERROR: Could not parse plan — $($parsed.Error)" -ForegroundColor Red
        Write-Host "  Raw log: $logFile" -ForegroundColor DarkGray
        exit 1
    }

    $pd  = $parsed.Plan
    $top = $pd.top
    Write-Host ''
    Write-Host '┌─ Plan ranking ──────────────────────────────────────────────┐' -ForegroundColor Cyan
    Write-Host ("│  TOP  #$($top.id) — $($top.title)".PadRight(64) + '│') -ForegroundColor Green
    Write-Host ("│       Branch : $($top.branch)".PadRight(64) + '│') -ForegroundColor DarkGray
    Write-Host ("│       Reason : $($top.reason)".PadRight(64) + '│') -ForegroundColor DarkGray
    Write-Host ("│       AC     : $($top.ac_count) items".PadRight(64) + '│') -ForegroundColor DarkGray
    if ($pd.alternatives.Count -gt 0) {
        Write-Host '│  ── Alternatives ───────────────────────────────────────────│' -ForegroundColor DarkGray
        foreach ($alt in $pd.alternatives) {
            Write-Host ("│  #$($alt.id) $($alt.title) — $($alt.reason)".PadRight(64) + '│') -ForegroundColor DarkGray
        }
    }
    if ($pd.blocked.Count -gt 0) {
        Write-Host '│  ── Blocked ─────────────────────────────────────────────────│' -ForegroundColor DarkGray
        foreach ($b in $pd.blocked) {
            Write-Host ("│  #$($b.id) $($b.title) (blocked by #$($b.blocked_by))".PadRight(64) + '│') -ForegroundColor Yellow
        }
    }
    Write-Host '└─────────────────────────────────────────────────────────────┘' -ForegroundColor Cyan
    Write-Host ''

    if ($Plan) { exit 0 }

    $confirmed = $false
    if ($Yes) {
        Write-Host "  Auto-confirming #$($top.id) ($($top.title))..." -ForegroundColor Green
        $confirmed = $true
    } else {
        $ans = Read-Host "Run #$($top.id) — $($top.title)? [Y/n]"
        $confirmed = ($ans -eq '' -or $ans -match '^[Yy]')
    }

    if (-not $confirmed) {
        Write-Host '  Exiting — no branch created.' -ForegroundColor DarkGray
        exit 0
    }

    # Branch creation is the atomic claim (deferred to Slice 3 implement).
    $slug3      = ($top.title -replace '[^A-Za-z0-9]+', '-').ToLower().Trim('-')
    $claimBranch = if ($top.branch) { $top.branch } else { "$($cfg.branch_prefix)$($top.id)-$slug3" }
    Write-Host "  Claimed: $claimBranch" -ForegroundColor Green
    Write-Host "  Implement phase will create this branch in Slice 3." -ForegroundColor DarkGray
    exit 0
} else {
    Fail 'Specify -SmokeTest, -Issue N, -Plan, or -Yes; or run bare for plan phase.'
}

if (-not (Test-Path $promptFile)) { Fail "Prompt file not found: $promptFile" }

$rawPrompt      = Get-Content $promptFile -Raw
$renderedPrompt = Invoke-RenderPrompt -Template $rawPrompt -Substitutions $subs

# Write rendered prompt to a temp file mounted into the container
$promptMount = "$HarnessRoot/.current-prompt.md"
Set-Content -Path $promptMount -Value $renderedPrompt -Encoding UTF8

# ── Run container ──────────────────────────────────────────────────────────────

Step "Running $runLabel"
Write-Host "  Log → $logFile"

$logDir = Split-Path $logFile -Parent
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }

# Build the claude invocation. For implement runs, pass --model and --max-turns.
$claudeInvocation = if ($implementModel -and $maxTurns) {
    "claude --model $implementModel --max-turns $maxTurns -p `"`$(cat /workspace/.harness/.current-prompt.md)`""
} else {
    'claude -p "$(cat /workspace/.harness/.current-prompt.md)"'
}

# Pass the token by reference (no `=value`) so it doesn't appear in
# the host process listing. Docker reads it from our environment.
$dockerArgs = @(
    'run', '--rm',
    '--volume', "${RepoRoot}:/workspace",
    '--env',    'CLAUDE_CODE_OAUTH_TOKEN',
    '--workdir', '/workspace',
    $imageName,
    'bash', '-lc', $claudeInvocation
)

try {
    & docker @dockerArgs 2>&1 | Tee-Object -FilePath $logFile
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item -ErrorAction SilentlyContinue $promptMount
}

# ── Summary ────────────────────────────────────────────────────────────────────

$ok     = $exitCode -eq 0
$color  = if ($ok) { 'Green' } else { 'Red' }
$status = if ($ok) { 'COMPLETE' } else { "FAILED (exit $exitCode)" }

Write-Host ''
Write-Host ('╔' + '═' * 50 + '╗') -ForegroundColor $color
Write-Host ("║  $runLabel — $status".PadRight(51) + '║') -ForegroundColor $color
Write-Host ('╚' + '═' * 50 + '╝') -ForegroundColor $color

if ($ok -and $SmokeTest) {
    Write-Host "  Log saved to: $logFile" -ForegroundColor DarkGray
}

# Rate-limit detection: surface a ready-made resume command
if (-not $ok -and $Issue -and (Test-Path $logFile)) {
    $logContent = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if ($logContent -match 'Rate limit exceeded|usage_limit_exceeded') {
        Write-Host ''
        Write-Host '  Rate limit hit. Resume with:' -ForegroundColor Yellow
        Write-Host "  pwsh ./.harness/run.ps1 -Issue $Issue -Resume" -ForegroundColor Yellow
    }
}

exit $exitCode
