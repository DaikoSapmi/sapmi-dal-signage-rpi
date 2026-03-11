#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
while true; do
  python3 scripts/update_data.py || true
  sleep 300
done
