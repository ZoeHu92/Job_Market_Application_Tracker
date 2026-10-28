#!/bin/bash
# macOS / Linux: double-click (or run ./start_tracker.command) to open the tracker in your browser.
cd "$(dirname "$0")" || exit 1

# Get the latest weekly job data and app updates (your statuses in my_data/ are never touched).
if [ -d .git ] && command -v git >/dev/null 2>&1; then
  git pull --ff-only --quiet 2>/dev/null || echo "(Could not update from GitHub - using the copy on this computer.)"
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up Python packages (about a minute)..."
  python3 -m venv .venv || { echo "Python 3 is required: https://www.python.org/downloads/"; read -r; exit 1; }
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt && touch .venv/.installed
fi

exec .venv/bin/python -m streamlit run app.py
