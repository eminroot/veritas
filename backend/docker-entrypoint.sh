#!/bin/sh
set -e

# Postgres may still be starting even after its healthcheck on a cold boot; retry briefly.
tries=0
until alembic upgrade head; do
  tries=$((tries + 1))
  if [ "$tries" -ge 15 ]; then
    echo "migrations failed 15 times, giving up" >&2
    exit 1
  fi
  echo "database not ready, retrying in 2s" >&2
  sleep 2
done

python scripts/seed_demo.py

exec uvicorn veritas.api.app:create_app --factory \
  --host 0.0.0.0 --port 8000 \
  --workers "${API_WORKERS:-2}" \
  --proxy-headers --forwarded-allow-ips '*'
