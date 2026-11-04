#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
# No access log: OAuth callback URLs contain short-lived authorization codes.
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
