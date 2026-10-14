#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8080}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || fail 'Run this script as root: sudo bash deploy-docker.sh'
command -v docker >/dev/null || fail 'Docker is not installed or not in PATH.'

echo "[1/4] Checking and stopping legacy host systemd service and host nginx config..."
if systemctl is-active --quiet railhop.service 2>/dev/null; then
    echo "Stopping legacy host railhop.service..."
    systemctl stop railhop.service
    systemctl disable railhop.service || true
fi
if [ -f /etc/nginx/conf.d/railhop.conf ]; then
    echo "Removing legacy host nginx /etc/nginx/conf.d/railhop.conf..."
    rm -f /etc/nginx/conf.d/railhop.conf
    systemctl reload nginx || true
fi

echo "[2/4] Building Docker container image (12306-railhop:latest)..."
cd "$PACKAGE_DIR"
docker build -t 12306-railhop:latest .

echo "[3/4] Recreating 12306-railhop container..."
if [ "$(docker ps -aq -f name=12306-railhop)" ]; then
    echo "Stopping existing 12306-railhop container..."
    docker stop 12306-railhop || true
    docker rm 12306-railhop || true
fi

docker run -d \
    --name 12306-railhop \
    --restart unless-stopped \
    -p "${PORT}:8080" \
    12306-railhop:latest

echo "[4/4] Verifying container health..."
ready=0
for i in {1..30}; do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done

if (( ! ready )); then
    echo "Container health check timed out. Showing recent container logs:"
    docker logs --tail 50 12306-railhop
    exit 1
fi

echo "Verifying API response..."
curl -fsS "http://127.0.0.1:${PORT}/health"
echo ""
docker ps -f name=12306-railhop
echo "12306-RailHop Docker deployment successful! Access: http://106.13.101.112:${PORT}/"
