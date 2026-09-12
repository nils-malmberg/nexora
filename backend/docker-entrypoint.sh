#!/bin/sh
set -e

if [ "${SKIP_MIGRATIONS:-}" != "1" ]; then
  echo "applying database migrations..."
  alembic upgrade head
fi

if [ "${SEED_DEMO_DATA:-}" = "1" ]; then
  echo "seeding demo data..."
  python scripts/seed_demo.py
fi

exec "$@"
