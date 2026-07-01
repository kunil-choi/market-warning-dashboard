#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "Installing system dependencies..."
apt-get install -y python3-sgmllib3k 2>/dev/null || true

echo "Installing Python dependencies..."
pip install -r "$CLAUDE_PROJECT_DIR/backend/requirements.txt"

echo "Session start complete."
