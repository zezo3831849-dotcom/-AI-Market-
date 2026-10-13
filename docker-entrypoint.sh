#!/bin/bash
set -e

echo "[GCP] Running database migrations..."
python manage.py migrate --noinput

echo "[GCP] Seeding initial market data..."
python manage.py seed_market_data

echo "[GCP] Starting Gunicorn server on port ${PORT:-8080}..."
exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 market_core.wsgi:application
