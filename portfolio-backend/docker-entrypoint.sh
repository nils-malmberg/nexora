#!/bin/sh
set -e

if [ "${SKIP_MIGRATIONS:-}" != "1" ]; then
  echo "applying database migrations..."
  alembic upgrade head
fi

exec "$@"
