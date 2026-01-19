#!/usr/bin/env bash
set -euo pipefail

# bootstrap.sh
# - clones are done by you (this script assumes you're already inside the repo)
# - creates/uses .venv
# - installs requirements
# - (optionally) installs Playwright browsers if playwright is installed
# - starts uvicorn

APP_MODULE="${APP_MODULE:-main:app}"     # e.g. main:app
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8006}"
VENV_DIR="${VENV_DIR:-.venv}"
REQ_FILE="${REQ_FILE:-requirements.txt}"

echo "==> Working dir: $(pwd)"
echo "==> App module : ${APP_MODULE}"
echo "==> Host/Port  : ${HOST}:${PORT}"

echo "==> Updating apt + installing system deps (python venv, build tools)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip \
  build-essential \
  git curl ca-certificates

# Optional: if your stack uses lxml and you want fewer build surprises.
# (If you already have wheels available, this won’t hurt much.)
sudo apt-get install -y --no-install-recommends \
  libxml2-dev libxslt1-dev zlib1g-dev

echo "==> Creating venv (if missing): ${VENV_DIR}"
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

echo "==> Activating venv"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "==> Upgrading pip tooling"
python -m pip install --upgrade pip setuptools wheel

echo "==> Installing Python dependencies"
if [[ -f "${REQ_FILE}" ]]; then
  pip install -r "${REQ_FILE}"
elif [[ -f "pyproject.toml" ]]; then
  pip install -e .
else
  echo "ERROR: No requirements.txt or pyproject.toml found."
  exit 1
fi

echo "==> Pip sanity check"
pip check || true

# If playwright is installed in the environment, install browser binaries.
if python -c "import playwright" >/dev/null 2>&1; then
  echo "==> Playwright detected; installing browsers"
  python -m playwright install --with-deps
else
  echo "==> Playwright not installed; skipping browser install"
fi

echo "==> Starting uvicorn"
exec uvicorn "${APP_MODULE}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --timeout-keep-alive 120
