#!/bin/bash
# Shared launcher used by "Start Bot.command" and "Try Demo.command".
cd "$(dirname "$0")/.." || exit 1

fail() { echo; echo "PROBLEM: $1"; echo "Press Enter to close."; read -r; exit 1; }

echo "Getting ready (first time takes a minute)..."
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  fail "Python 3.9+ is not installed. Get it from https://www.python.org/downloads/ , install it, then double-click again."
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || fail "Could not create the virtual environment."
fi
if ! cmp -s requirements.txt .venv/.installed; then
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt || fail "Could not install requirements (check your internet)."
  cp requirements.txt .venv/.installed
fi

PORT=$(.venv/bin/python -c 'import json; print(json.load(open("config.json"))["dashboard_port"])') || fail "config.json is broken."
if command -v open >/dev/null 2>&1; then
  (sleep 4; open "http://localhost:$PORT") &
fi

# caffeinate keeps the Mac awake while the bot runs (it stops when the bot stops).
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -is .venv/bin/python bot.py "$@"
else
  .venv/bin/python bot.py "$@"
fi
echo
echo "Bot stopped. You can close this window."
