# Smoke test: verify the Docker image can run `claude` with the host's
# subscription credentials.
#
# Expected output:
#   PONG
#
# If you see "Not authenticated" or similar, run `claude login` on the host
# first to populate ~/.claude/.credentials.json.

$ErrorActionPreference = "Stop"

$cred = "$env:USERPROFILE\.claude\.credentials.json"
if (-not (Test-Path $cred)) {
    Write-Error "Missing $cred. Run 'claude login' on the host first."
    exit 1
}

Write-Host "Running smoke test in container..." -ForegroundColor Cyan

docker run --rm `
    -v "${cred}:/tmp/host-credentials.json:ro" `
    qr-agent:latest `
    bash -lc @'
mkdir -p ~/.claude
cp /tmp/host-credentials.json ~/.claude/.credentials.json
chmod 600 ~/.claude/.credentials.json
claude -p "Reply with just the word PONG (no other text)." --max-turns 1
'@

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSmoke test passed. Subscription token reachable from container." -ForegroundColor Green
} else {
    Write-Host "`nSmoke test FAILED (exit $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
