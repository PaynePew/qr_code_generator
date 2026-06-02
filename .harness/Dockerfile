# Project-customised agent harness — qr_code_generator
#
# Forked from kanban-harness v0.1.1 (upstream sha 90fb5fb).
# This project uses plain pip + SQLite + Vite, so we keep the base image
# minimal: just the toolchains the prompts actually invoke.
#
# Why no `uv`:
#   The backend uses pip + requirements.txt (see /requirements.txt at repo
#   root) — `pytest` is invoked directly, no `uv run` wrapper.
#
# Why no `postgresql-client` / docker-compose:
#   Backend storage is SQLite (qr_codes.db committed at repo root). There
#   is no per-issue Postgres/ElasticMQ stack to provision and no
#   `host.docker.internal` wiring needed.

FROM node:22-bookworm-slim

# System tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates build-essential jq \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Allow pip to install into system Python inside the container
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# GitHub CLI (Debian repo)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Rename the base image's `node` user (UID 1000) to `agent` and move its
# home dir. Avoids a UID collision that would happen if we created a new
# user with -u 1000.
RUN usermod -d /home/agent -m -l agent node \
    && groupmod -n agent node

USER agent

# Claude Code CLI — installed per-user via Anthropic's official script.
# Uses subscription via OAuth (NOT API key). Goes to ~/.local/bin.
RUN curl -fsSL https://claude.ai/install.sh | bash

# Add the per-user install dir to PATH
ENV PATH="/home/agent/.local/bin:$PATH"

WORKDIR /workspace

# Sanity: print versions on container start unless overridden
CMD ["bash", "-lc", "node --version && python3 --version && git --version && gh --version | head -1 && claude --version"]
