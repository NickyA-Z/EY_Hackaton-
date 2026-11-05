#!/usr/bin/env bash
set -euo pipefail

dashboard_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_dir="$(dirname "$dashboard_dir")"
cd "$repository_dir"

export PYTHONPATH="$repository_dir${PYTHONPATH:+:$PYTHONPATH}"

# Keep uv's downloaded packages and temporary environment inside this project,
# so the launcher also works in restricted development environments.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$dashboard_dir/.uv-cache}"

exec uv run \
  --python 3.12 \
  --with-requirements frontend/requirements.txt \
  streamlit run frontend/frontend/dashboard.py \
  --server.address 127.0.0.1 \
  --server.headless true \
  --server.port "${PORT:-8503}" \
  --browser.gatherUsageStats false
