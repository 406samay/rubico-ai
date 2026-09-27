#!/usr/bin/env bash
# One-click start for Mac & Linux:  ./start.sh
# First run: installs everything into a private .venv folder, then offers
# the demo or setup. After that: starts Rubico.
set -e
cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Rubico needs Python 3.10 or newer."
  echo "Download it from https://www.python.org/downloads/ then run this again."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting things up (about a minute)..."
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  touch .venv/.installed
fi

exec .venv/bin/python run.py "$@"
