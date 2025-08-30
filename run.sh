#!/usr/bin/env bash
# Run MACATS multi-agent trading system (Linux/macOS)

set -e

cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "[setup] Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Ensure pip is up-to-date
python -m pip install --upgrade pip

# Install requirements if not already satisfied
if [ -f "requirements.txt" ]; then
  pip install --quiet -r requirements.txt
fi
if [ -f "requirements-dev.txt" ]; then
  pip install --quiet -r requirements-dev.txt
fi

echo "[run] Starting MACATS..."
python main.py