#!/bin/sh
# Start the bundled PanSou API and MovieSync web app in one container.
set -u

/usr/local/bin/pansou &
PANSOU_PID=$!

gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 8 --timeout 120 main:app &
APP_PID=$!

shutdown() {
    kill -TERM "$APP_PID" "$PANSOU_PID" 2>/dev/null || true
}

trap shutdown INT TERM
wait "$APP_PID"
STATUS=$?
shutdown
wait "$PANSOU_PID" 2>/dev/null || true
exit "$STATUS"
