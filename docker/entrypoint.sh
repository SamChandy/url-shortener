#!/bin/sh
# Container start-up: make sure a SECRET_KEY exists, migrate the database, start gunicorn.
set -e

if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
    export SECRET_KEY
    echo "WARNING: SECRET_KEY is not set. Generated a temporary one: logins will be invalidated"
    echo "         whenever the container restarts. Set SECRET_KEY in .env for anything real."
fi

echo "Applying database migrations..."
attempt=0
until alembic upgrade head; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 10 ]; then
        echo "ERROR: database migrations failed after $attempt attempts."
        exit 1
    fi
    echo "Database not ready yet, retrying in 3 seconds ($attempt/10)..."
    sleep 3
done

echo "Starting gunicorn..."
exec gunicorn "app.main:create_app()" \
    --bind "0.0.0.0:5000" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout 30 \
    --access-logfile - \
    --error-logfile -
