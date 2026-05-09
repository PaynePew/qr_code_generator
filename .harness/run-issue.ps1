# Two-phase agent run: implement → review.
#
# Usage:
#   pwsh .\.harness\run-issue.ps1 -Issue 7
#   pwsh .\.harness\run-issue.ps1 -Issue 7 -MaxTurns 80 -SkipReview
#   pwsh .\.harness\run-issue.ps1 -Issue 7 -ImplementModel claude-sonnet-4-6 -ReviewModel claude-opus-4-7
#
# Phase 1 — implement:
#   Default model: claude-sonnet-4-6 (best coding model, fast).
#   Reads the issue, scaffolds / implements on a fresh slice-<N>-... branch,
#   writes tests in RGR style, commits.
#
# Phase 2 — review:
#   Default model: claude-opus-4-6 (deeper reasoning for catch).
#   Checks out the same branch, reads the diff, applies safe refactors,
#   commits with `refactor:` prefix, or no-ops if the code is already clean.
#
# Both phases run in fresh containers; state lives in the branch on the
# host repo, which both containers see via the /workspace bind mount.

param(
    [Parameter(Mandatory=$true)]
    [int]$Issue,

    [int]$MaxTurns = 60,

    [string]$ImplementModel = 'claude-sonnet-4-6',
    [string]$ReviewModel    = 'claude-opus-4-6',

    [switch]$SkipReview,
    [switch]$SkipImplement   # rare: re-run review only, e.g. after manual edits
)

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$cred       = "$env:USERPROFILE\.claude\.credentials.json"
$implPath   = Join-Path $PSScriptRoot "prompts\implement.md"
$reviewPath = Join-Path $PSScriptRoot "prompts\review.md"

# --- Pre-flight ---------------------------------------------------------

if (-not (Test-Path $cred)) {
    Write-Error "Missing $cred. Run 'claude login' on the host first."
    exit 1
}
if (-not $SkipImplement -and -not (Test-Path $implPath)) {
    Write-Error "Missing $implPath."
    exit 1
}
if (-not $SkipReview -and -not (Test-Path $reviewPath)) {
    Write-Error "Missing $reviewPath. Pass -SkipReview if review is intentionally disabled."
    exit 1
}

try {
    $ghToken = (gh auth token 2>$null).Trim()
} catch {
    $ghToken = $null
}
if ([string]::IsNullOrWhiteSpace($ghToken)) {
    Write-Error "Could not get a GitHub token via 'gh auth token'. Run 'gh auth login' on the host first."
    exit 1
}

# --- Helpers ------------------------------------------------------------

function Invoke-AgentPhase {
    [CmdletBinding()]
    param(
        [string]$PhaseName,
        [string]$Model,
        [string]$PromptPath,
        [hashtable]$Substitutions
    )

    $prompt = Get-Content $PromptPath -Raw
    foreach ($key in $Substitutions.Keys) {
        $prompt = $prompt.Replace($key, $Substitutions[$key])
    }
    $staged = New-TemporaryFile
    Set-Content -Path $staged -Value $prompt -Encoding UTF8

    # Per-phase log file under .harness/logs/. Same dir mirrors the
    # .sandcastle/logs convention. The dir is gitignored except for
    # .gitkeep so the structure persists but the noise doesn't.
    $logDir = Join-Path $repoRoot '.harness\logs'
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
    $logPath = Join-Path $logDir "issue-$Issue-$PhaseName-$stamp.log"

    Write-Host ""
    Write-Host "===== Phase: $PhaseName  (model: $Model) =====" -ForegroundColor Magenta
    Write-Host "Log: $logPath" -ForegroundColor DarkGray
    Write-Host ""

    try {
        # Streaming strategy:
        #   - claude -p with --output-format stream-json --verbose emits one
        #     JSON event per line, line-buffered.
        #   - jq --unbuffered renders each event into a single readable line
        #     (assistant text, [tool] calls, [result] tool output, [done]).
        #   - Tee-Object on the host duplicates the stream to the log file
        #     while also emitting it to PowerShell stdout for live viewing.
        #
        # NOTE: jq lives inside the qr-agent image (apt-get jq). The filter
        # is single-quoted inside the heredoc so PowerShell does not try
        # to interpolate $.

        docker run --rm `
            -v "${cred}:/tmp/host-credentials.json:ro" `
            -v "${repoRoot}:/workspace:rw" `
            -v "${staged}:/tmp/agent-prompt.md:ro" `
            -e "GH_TOKEN=$ghToken" `
            -w /workspace `
            qr-agent:latest `
            bash -lc @"
set -euo pipefail

mkdir -p ~/.claude
cp /tmp/host-credentials.json ~/.claude/.credentials.json
chmod 600 ~/.claude/.credentials.json

git config --global user.name 'qr-harness-agent'
git config --global user.email 'agent@local.harness'
git config --global --add safe.directory /workspace

echo '=== Starting $PhaseName agent ==='
echo ''
claude -p "`$(cat /tmp/agent-prompt.md)" \
    --model $Model \
    --max-turns $MaxTurns \
    --add-dir /workspace \
    --permission-mode bypassPermissions \
    --verbose \
    --output-format stream-json 2>&1 \
  | jq -r --unbuffered '
      if .type == "assistant" then
        (.message.content[]? |
          if .type == "text" then .text
          elif .type == "tool_use" then "[tool] \(.name) \((.input | tojson) | .[0:240])"
          else empty end)
      elif .type == "user" then
        (.message.content[]? |
          if .type == "tool_result" then
            "[result] " + (
              (.content
                | if type == "array"
                    then (map(.text // (. | tostring)) | join(" "))
                    else (. | tostring)
                  end)
              | tostring | gsub("\n"; " ") | .[0:240])
          else empty end)
      elif .type == "result" then
        "[done] turns=\(.num_turns // 0) duration=\((((.duration_ms // 0) / 1000) | floor))s"
      elif .type == "system" then
        "[init] subtype=\(.subtype // "?") model=\(.model // "?")"
      else empty end
    ' 2>/dev/null
echo ''
echo "=== $PhaseName phase finished ==="
"@ 2>&1 | Tee-Object -FilePath $logPath

        return $LASTEXITCODE
    } finally {
        Remove-Item $staged -Force -ErrorAction SilentlyContinue
    }
}

function Get-SliceBranch {
    Push-Location $repoRoot
    try {
        $b = git branch --list "slice-$Issue-*" --format='%(refname:short)' | Select-Object -First 1
        if ($b) { return $b.Trim() } else { return $null }
    } finally {
        Pop-Location
    }
}

# --- Banner -------------------------------------------------------------

Write-Host "Issue:           #$Issue" -ForegroundColor Cyan
Write-Host "Repo:            $repoRoot" -ForegroundColor Cyan
Write-Host "Max turns/phase: $MaxTurns" -ForegroundColor Cyan
if (-not $SkipImplement) { Write-Host "Implement model: $ImplementModel" -ForegroundColor Cyan }
if (-not $SkipReview)    { Write-Host "Review model:    $ReviewModel"    -ForegroundColor Cyan }
Write-Host ""

# --- Phase 1: implement -------------------------------------------------

$implExit = 0
if ($SkipImplement) {
    Write-Host "Skipping implement phase (--SkipImplement)." -ForegroundColor Yellow
} else {
    $implExit = Invoke-AgentPhase `
        -PhaseName 'implement' `
        -Model $ImplementModel `
        -PromptPath $implPath `
        -Substitutions @{ '{{ISSUE}}' = "$Issue" }

    Write-Host "`n=== Implement exit: $implExit ===" -ForegroundColor $(if ($implExit -eq 0) { "Green" } else { "Red" })
}

# --- Phase 2: review ----------------------------------------------------

$reviewExit = 0
$branch = Get-SliceBranch

if ($SkipReview) {
    Write-Host "Skipping review phase (--SkipReview)." -ForegroundColor Yellow
} elseif (-not $branch) {
    Write-Host "No slice-$Issue-* branch found. Skipping review." -ForegroundColor Yellow
    $reviewExit = -1
} else {
    $reviewExit = Invoke-AgentPhase `
        -PhaseName 'review' `
        -Model $ReviewModel `
        -PromptPath $reviewPath `
        -Substitutions @{
            '{{BRANCH}}'        = $branch
            '{{TARGET_BRANCH}}' = 'main'
        }

    Write-Host "`n=== Review exit: $reviewExit ===" -ForegroundColor $(if ($reviewExit -eq 0) { "Green" } else { "Red" })
}

# --- Post-run summary ---------------------------------------------------

Push-Location $repoRoot
try {
    Write-Host "`nBranches matching slice-$Issue-*:" -ForegroundColor Cyan
    git branch --list "slice-$Issue-*"

    if ($branch) {
        Write-Host "`nCommits on $branch (vs main):" -ForegroundColor Cyan
        git log "main..$branch" --oneline
    }

    Write-Host "`nWorking-tree status:" -ForegroundColor Cyan
    git status --short
} finally {
    Pop-Location
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
if ($branch) {
    Write-Host "  git checkout $branch"
    Write-Host "  git push -u origin $branch"
    Write-Host "  gh pr create"
} else {
    Write-Host "  No branch produced. Inspect the implement log and re-run."
}

# Exit with worst-case status
if ($implExit -ne 0)            { exit $implExit }
if ($reviewExit -gt 0)          { exit $reviewExit }
exit 0
