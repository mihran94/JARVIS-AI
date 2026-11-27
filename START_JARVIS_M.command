#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
if [ "$(uname -s)" != "Darwin" ]; then
  echo "Use START_JARVIS_M.cmd on Windows."
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -c 'import sys; assert sys.version_info >= (3,12), "Install Python 3.12 or newer first"'
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python scripts/launch.py
