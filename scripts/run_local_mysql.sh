#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ -f "${ROOT_DIR}/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env.local"
  set +a
fi

export PHD_PLATFORM_DB_BACKEND="${PHD_PLATFORM_DB_BACKEND:-mysql}"
export PHD_PLATFORM_MYSQL_HOST="${PHD_PLATFORM_MYSQL_HOST:-127.0.0.1}"
export PHD_PLATFORM_MYSQL_PORT="${PHD_PLATFORM_MYSQL_PORT:-3306}"
export PHD_PLATFORM_MYSQL_DATABASE="${PHD_PLATFORM_MYSQL_DATABASE:-phd_workspace}"
export PHD_PLATFORM_MYSQL_USER="${PHD_PLATFORM_MYSQL_USER:-phd_app}"
export PHD_PLATFORM_COOKIE_SECURE="${PHD_PLATFORM_COOKIE_SECURE:-0}"

if [[ -z "${PHD_PLATFORM_MYSQL_PASSWORD:-}" ]]; then
  echo "PHD_PLATFORM_MYSQL_PASSWORD is required. Put it in ${ROOT_DIR}/.env or ${ROOT_DIR}/.env.local." >&2
  exit 2
fi

exec python3 "${ROOT_DIR}/server.py" --host "${PHD_PLATFORM_HOST:-127.0.0.1}" --port "${PHD_PLATFORM_PORT:-8765}"
