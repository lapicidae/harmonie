#!/bin/bash
#
# Health check probe for Harmonie
# Checks the public HTTP liveness endpoint

set -euo pipefail

readonly HEALTH_PORT="${HARMONIE_PORT:-8842}"
readonly HEALTH_URL="http://localhost:${HEALTH_PORT}/health"

if command -v curl >/dev/null 2>&1; then
    curl -fsS "${HEALTH_URL}" >/dev/null 2>&1 && exit 0
elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import urllib.request; urllib.request.urlopen('${HEALTH_URL}', timeout=4)" >/dev/null 2>&1 && exit 0
fi

exit 1
