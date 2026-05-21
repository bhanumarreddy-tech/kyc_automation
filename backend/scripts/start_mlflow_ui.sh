#!/bin/sh
set -eu

URI="${MLFLOW_TRACKING_URI:-}"
if [ -z "$URI" ]; then
  URI="${DATABASE_URL:-}"
fi
if [ -z "$URI" ]; then
  URI="${DATABASE_PUBLIC_URL:-}"
fi
if [ -z "$URI" ]; then
  echo "error: set MLFLOW_TRACKING_URI, DATABASE_URL, or DATABASE_PUBLIC_URL" >&2
  exit 1
fi

PORT="${PORT:-5000}"
echo "Starting MLflow UI on 0.0.0.0:${PORT}"

exec mlflow ui --host 0.0.0.0 --port "$PORT" --backend-store-uri "$URI"
