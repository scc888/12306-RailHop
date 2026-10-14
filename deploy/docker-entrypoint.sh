#!/usr/bin/env bash
set -e

echo "Starting 12306-RailHop backend service..."
cd /app/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 18000 --workers 1 --timeout-keep-alive 10 &
BACKEND_PID=$!

cleanup() {
    echo "Stopping 12306-RailHop services..."
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
    nginx -s quit 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "Waiting for backend service to become ready..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:18000/health >/dev/null 2>&1; then
        echo "Backend service is ready!"
        break
    fi
    sleep 1
done

echo "Starting Nginx frontend server on port 8080..."
nginx -g "daemon off;" &
NGINX_PID=$!

wait -n $BACKEND_PID $NGINX_PID
