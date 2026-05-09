# Run the implementation agent against a single GitHub issue.
#
# Usage:
#   pwsh .\.harness\run-issue.ps1 -Issue 7
#
# What it does:
#   1. Substitutes the issue number into the implement prompt template.
#   2. Mounts ~/.claude/.credentials.json (read-only) and the repo into a
#      fresh container.
#   3. Mounts ~/.config/gh (read-only) so `gh` inside the container is
#      authenticated against your GitHub account.
#   4. Runs `claude -p "$prompt" --max-turns 50` inside the container.
#   5. Container exits; commits land on a new local branch in your host repo.
#   6. You inspect, push, and merge from the host.

param(
    [Parameter(Mandatory=$true)]
    [int]$Issue,

    [int]$MaxTurns = 50
)

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$cred       = "$env:USERPROFILE\.claude\.credentials.json"
$promptPath = Join-Path $PSScriptRoot "prompts\implement.md"

# --- Pre-flight checks ---------------------------------------------------

if (-not (Test-Path $cred)) {
    Write-Error "Missing $cred. Run 'claude login' on the host first."
    exit 1
}
if (-not (Test-Path $promptPath)) {
    Write-Error "Missing prompt template at $promptPath."
    exit 1
}

# Extract GitHub token from host keyring. On Windows, gh stores the token
# in Credential Manager, not in hosts.yml — so we can't mount a config dir;
# we have to pull the token out and pass it as an env var.
try {
    $ghToken = (gh auth token 2>$null).Trim()
} catch {
    $ghToken = $null
}
if ([string]::IsNullOrWhiteSpace($ghToken)) {
    Write-Error "Could not get a GitHub token via 'gh auth token'. Run 'gh auth login' on the host first."
    exit 1
}

# --- Substitute issue number into prompt --------------------------------

$prompt = (Get-Content $promptPath -Raw).Replace("{{ISSUE}}", "$Issue")
$promptStaged = New-TemporaryFile
Set-Content -Path $promptStaged -Value $prompt -Encoding UTF8

Write-Host "Issue:     #$Issue" -ForegroundColor Cyan
Write-Host "Repo:      $repoRoot" -ForegroundColor Cyan
Write-Host "Max turns: $MaxTurns" -ForegroundColor Cyan
Write-Host ""

# --- Run container ------------------------------------------------------
#
# Mounts:
#   - credentials file: copied to a writable location inside container so
#     OAuth refresh works without touching the host file.
#   - repo: read-write; agent commits here, host sees them after exit.
#   - prompt: read-only; staged temp file with {{ISSUE}} substituted.
#
# Env vars:
#   - GH_TOKEN: extracted from host keyring; container's gh CLI picks it up
#     automatically with no config file mounting needed.
#
# Container starts as user `agent` (uid 1000). On Docker Desktop for
# Windows, bind-mounted file ownership is virtualized and `agent` can
# read the mounted files regardless of host ACLs.

try {
    docker run --rm `
        -v "${cred}:/tmp/host-credentials.json:ro" `
        -v "${repoRoot}:/workspace:rw" `
        -v "${promptStaged}:/tmp/implement-prompt.md:ro" `
        -e "GH_TOKEN=$ghToken" `
        -w /workspace `
        qr-agent:latest `
        bash -lc @"
set -euo pipefail

# --- Set up auth inside container ---
mkdir -p ~/.claude
cp /tmp/host-credentials.json ~/.claude/.credentials.json
chmod 600 ~/.claude/.credentials.json

# --- Set up git config (commits need an author) ---
git config --global user.name 'qr-harness-agent'
git config --global user.email 'agent@local.harness'
git config --global --add safe.directory /workspace

# --- Run the implementer ---
echo '=== Starting agent for issue #$Issue ==='
claude -p "`$(cat /tmp/implement-prompt.md)" \
    --max-turns $MaxTurns \
    --add-dir /workspace \
    --permission-mode bypassPermissions \
    --verbose
"@

    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item $promptStaged -Force -ErrorAction SilentlyContinue
}

# --- Post-run summary ---------------------------------------------------

Write-Host "`n=== Container exit: $exitCode ===" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })

Push-Location $repoRoot
try {
    Write-Host "`nCurrent branch:" -ForegroundColor Cyan
    git rev-parse --abbrev-ref HEAD

    Write-Host "`nNew local branches (likely the agent's work):" -ForegroundColor Cyan
    git branch --list "slice-*"

    Write-Host "`nUncommitted changes (should be empty if agent finished cleanly):" -ForegroundColor Cyan
    git status --short
} finally {
    Pop-Location
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. git checkout slice-$Issue-..."
Write-Host "  2. git log --oneline main..HEAD     # review the agent's commits"
Write-Host "  3. git push -u origin slice-$Issue-..."
Write-Host "  4. gh pr create   # or merge directly"

exit $exitCode
