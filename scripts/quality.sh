#!/usr/bin/env bash

STRICT=false
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=true ;;
  esac
done

if $STRICT; then
  set -euo pipefail
else
  set -uo pipefail
fi

rc=0

uv run ruff format --check src tests scripts || rc=$?
uv run ruff check src tests scripts          || rc=$?
uv run mypy src                              || rc=$?



uv run xenon --max-absolute D --max-modules B --max-average A src || rc=$?
uv run vulture src tests --min-confidence 80 || rc=$?
uv run deptry .                              || rc=$?
uv run pytest --cov=arxiv_md --cov-report=term-missing --cov-fail-under=85 || rc=$?

if [ $rc -ne 0 ]; then
  echo ""
  echo "quality: some steps failed (rc=$rc). Pass --strict for fail-fast mode."
fi
exit $rc
