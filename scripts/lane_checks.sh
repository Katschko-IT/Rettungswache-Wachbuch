#!/usr/bin/env bash
# Lane-Checks: identisch zur CI-Reihenfolge, nur ohne Docker.
set -u
cd /opt/data/workspace/wachbuch-i18n-full-20261019 || exit 1
PY=/opt/data/workspace/agy-eval-wachbuch/.venv/bin/python
export DJANGO_SECRET_KEY=ci-only-secret
export DJANGO_DEBUG=false
export MFA_ENABLED=true
export REDIS_URL=""
rc=0
step() { echo; echo "### $*"; }

step "i18n catalog check"
$PY scripts/i18n_catalog.py check; rc=$((rc+$?))

step "makemigrations --check"
$PY manage.py makemigrations --check --dry-run --settings=config.test_settings; rc=$((rc+$?))

step "django check (test settings)"
$PY manage.py check --settings=config.test_settings; rc=$((rc+$?))

step "ruff E4,E7,E9"
( cd . && ruff check config core --select E4,E7,E9 --output-format=concise ) 2>&1 | tail -20; rc=$((rc+$?))

step "site checks"
$PY site/tests/check_site.py; rc=$((rc+$?))

step "django test suite"
$PY manage.py test --settings=config.test_settings 2>&1 | tail -25
echo
echo "== aggregate rc=$rc =="
