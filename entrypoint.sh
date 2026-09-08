#!/bin/sh
set -e

if [ "$MODE" = "api" ]; then
    echo "Starting FastAPI application..."
    exec uvicorn contexta.api.app:app --host 0.0.0.0 --port 8000
elif [ "$MODE" = "worker" ]; then
    echo "Starting Celery worker..."
    exec celery -A contexta.workers.celery_app.celery_app worker --loglevel=info -Q extraction,embedding,maintenance,celery
elif [ "$MODE" = "beat" ]; then
    echo "Starting Celery beat..."
    exec celery -A contexta.workers.celery_app.celery_app beat --loglevel=info
elif [ "$MODE" = "migrate" ]; then
    echo "Running Alembic migrations..."
    exec alembic upgrade head
elif [ "$MODE" = "model-server" ]; then
    echo "Starting Contexta Persistent Model Server..."
    exec uvicorn contexta.workers.model_server:app --host 0.0.0.0 --port ${MODEL_SERVER_PORT:-8001} --workers 1
else
    echo "Unknown or missing MODE: '$MODE'. Defaulting to running the API."
    exec uvicorn contexta.api.app:app --host 0.0.0.0 --port 8000
fi
