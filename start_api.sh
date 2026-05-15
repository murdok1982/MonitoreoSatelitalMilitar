#!/bin/bash
# start_api.sh — Launch the AEGIS-IMINT FastAPI REST server
set -euo pipefail

# Activate virtual environment if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

PORT="${API_PORT:-8502}"
echo "=========================================="
echo "  AEGIS-IMINT REST API"
echo "  Port    : ${PORT}"
echo "  API Key : ${AEGIS_API_KEY:-aegis-dev-key-change-in-production}"
echo "  Docs    : http://localhost:${PORT}/api/docs"
echo "  ReDoc   : http://localhost:${PORT}/api/redoc"
echo "=========================================="

python -m api.run
