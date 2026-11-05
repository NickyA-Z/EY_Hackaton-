#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$app_dir"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$app_dir/.uv-cache}"

exec uv run \
  --python 3.12 \
  --with-requirements ../sea_dashboard/requirements.txt \
  streamlit run app.py \
  --server.port "${PORT:-8502}"
