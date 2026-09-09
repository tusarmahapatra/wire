#!/usr/bin/env bash
# Wire — one-command setup and launch.
#
# Step 1: run this once — it creates .env for you, then stops so you can add
#         your Groq key.
# Step 2: run it again — it installs everything and starts the app.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env"
    echo
    echo "Add your free Groq key (https://console.groq.com/keys) to .env:"
    echo "  GROQ_API_KEY=gsk_..."
    echo
    echo "Then run ./startup.sh again to install and start Wire."
    exit 0
fi

if ! grep -q '^GROQ_API_KEY=.\+' .env; then
    echo "Note: GROQ_API_KEY is empty in .env — Wire will still run, but the chat feature will be disabled."
    echo "Get a free key at https://console.groq.com/keys and add it to .env to enable chat."
    echo
fi

PYTHON=python3
command -v python3 >/dev/null 2>&1 || PYTHON=python

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

if [ -f .venv/Scripts/activate ]; then
    source .venv/Scripts/activate   # Windows
else
    source .venv/bin/activate       # Linux/Mac
fi

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo
echo "Starting Wire at http://localhost:8000"
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
