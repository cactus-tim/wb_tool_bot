#!/usr/bin/env bash
set -e

echo "[entrypoint] waiting for postgres at ${DB_HOST}:${DB_PORT} ..."
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; do
  sleep 1
done

echo "[entrypoint] postgres is ready. starting bot..."
exec python -m main