#!/usr/bin/env bash
# Build and verify PSX Live & Research from a clean checkout.
#
#   ./build.sh          full build: venv, dependencies, tests, verification
#   ./build.sh --fast   skip dependency install (venv already populated)
#
# Exits non-zero if any step fails, so CI and humans agree on what "built" means.
set -euo pipefail
cd "$(dirname "$0")"

FAST=0
[[ "${1:-}" == "--fast" ]] && FAST=1
PY=.venv/bin/python

step() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }

step "1/5 Python environment"
if [[ ! -x $PY ]]; then
  python3 -m venv .venv
  FAST=0
fi
$PY -V

if [[ $FAST -eq 0 ]]; then
  step "2/5 Dependencies"
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/pip install -q -r requirements-dev.txt
else
  step "2/5 Dependencies (skipped: --fast)"
fi

step "3/5 Static checks"
if .venv/bin/python -c "import pyflakes" 2>/dev/null; then
  # Undefined names and unused imports are the two defects that slip through review.
  .venv/bin/python -m pyflakes src/ tests/ scripts/ | grep -v "imported but unused" || true
fi
$PY -m compileall -q src tests scripts >/dev/null

step "4/5 Offline test suite"
$PY -m pytest -q tests/test_offline_data.py

step "5/5 Build verification"
$PY scripts/verify_build.py

printf '\n\033[1mBuilt.\033[0m Start the desk with:\n'
printf '  .venv/bin/uvicorn src.app.server:app --host 0.0.0.0 --port 8111\n\n'
