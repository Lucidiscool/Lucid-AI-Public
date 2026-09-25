#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

PYTHON="${LUCID_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PYTHON="$PWD/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || true)"
  fi
fi
if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  echo "Python 3.11 or newer is required. Set LUCID_PYTHON to its executable." >&2
  exit 1
fi
"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11 or newer is required.')
PY
if [[ ! -f local_model.json ]]; then
  echo "Local model is not configured. Install a Linux llama.cpp Vulkan runtime and GGUF model, then create local_model.json as described in ADMIN.md." >&2
  exit 1
fi
if ! command -v gh >/dev/null || ! command -v git >/dev/null; then
  echo "Install Git and GitHub CLI, then run 'gh auth login' with access to both Lucid repositories." >&2
  exit 1
fi
if ! command -v cloudflared >/dev/null && [[ ! -x runtime/cloudflared ]]; then
  echo "Install Cloudflare Tunnel (cloudflared) and ensure it is on PATH." >&2
  exit 1
fi
if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi
PYTHON="$PWD/.venv/bin/python"
"$PYTHON" -m pip install -r requirements-web.txt
exec "$PYTHON" -u host_public.py --admin --publish
