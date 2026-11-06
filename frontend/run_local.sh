#!/usr/bin/env bash
set -euo pipefail

dashboard_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_dir="$(dirname "$dashboard_dir")"
# Run from frontend/ so .streamlit/config.toml (light theme) is loaded.
cd "$dashboard_dir"

export PYTHONPATH="$repository_dir${PYTHONPATH:+:$PYTHONPATH}"

# API keys (e.g. ANTHROPIC_API_KEY) from the repository's .env file, if there is one.
# .env is gitignored: never commit keys. Variables already set in the shell win.
if [ -f "$repository_dir/.env" ]; then
  while IFS='=' read -r key value || [ -n "$key" ]; do  # "|| ..." keeps a last line that has no newline
    case "$key" in ''|\#*) continue ;; esac
    key="${key#export }"; value="${value%$'\r'}"; value="${value%\"}"; value="${value#\"}"
    if [ -z "${!key:-}" ]; then export "$key=$value"; fi
  done < "$repository_dir/.env"
fi

# Keep uv's downloaded packages and temporary environment inside this project,
# so the launcher also works in restricted development environments.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$dashboard_dir/.uv-cache}"

exec uv run \
  --python 3.12 \
  --with-requirements requirements.txt \
  streamlit run frontend/dashboard.py \
  --server.address 127.0.0.1 \
  --server.headless true \
  --server.port "${PORT:-8503}" \
  --browser.gatherUsageStats false
