#!/usr/bin/env bash
# Per-issue infrastructure provisioning — no-op stub for qr_code_generator.
#
# The chatgpt_task upstream version of this script carves out a per-issue
# Postgres database (app_issue_<N>) and ElasticMQ queue pair, so parallel
# slices don't race on shared rows / messages.
#
# This project doesn't need any of that:
#   - Backend storage is SQLite, file-local to each worktree (qr_codes.db
#     in the bind-mount). Two worktrees → two independent DB files.
#   - There is no queue / DLQ / outbox in this project.
#   - There is no docker-compose stack to bring up.
#
# We keep the script (run.ps1 calls Invoke-IssueInfra unconditionally) but
# make every action a no-op. If a future slice introduces shared infra,
# replace this stub with a real implementation.
#
# Usage (called by run.ps1 — do not invoke manually):
#   .harness/lib/issue-infra.sh provision <issue-number>
#   .harness/lib/issue-infra.sh destroy   <issue-number>

set -euo pipefail

action="${1:-}"
issue="${2:-}"

if [[ -z "$action" || -z "$issue" ]]; then
    echo "usage: $0 {provision|destroy} <issue-number>" >&2
    exit 2
fi
if ! [[ "$issue" =~ ^[0-9]+$ ]]; then
    echo "issue must be a positive integer, got: '$issue'" >&2
    exit 2
fi

case "$action" in
    provision)
        echo "[issue-infra] no-op (qr_code_generator uses SQLite — no per-issue infra to provision)"
        ;;
    destroy)
        echo "[issue-infra] no-op (qr_code_generator uses SQLite — nothing to destroy)"
        ;;
    *)
        echo "unknown action: ${action} (expected provision|destroy)" >&2
        exit 2
        ;;
esac
