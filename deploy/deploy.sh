#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

# This installer manages only its own service and nginx configuration.
PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT=/opt/12306-railhop
SERVICE_FILE=/etc/systemd/system/railhop.service
SITE_FILE=/etc/nginx/conf.d/railhop.conf
PORT="${PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-18000}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || fail 'Run this script as root: sudo bash deploy.sh'
[[ -d /run/systemd/system ]] || fail 'This installer requires Linux with systemd.'
command -v apt-get >/dev/null || fail 'This installer supports Ubuntu/Debian (apt-get) only.'
for value in "$PORT" "$BACKEND_PORT"; do
    [[ "$value" =~ ^[0-9]{1,5}$ ]] || fail 'PORT and BACKEND_PORT must be numeric.'
    (( 10#$value >= 1024 && 10#$value <= 65535 )) || fail 'Use ports between 1024 and 65535.'
done
PORT="$((10#$PORT))"
BACKEND_PORT="$((10#$BACKEND_PORT))"
[[ "$PORT" != "$BACKEND_PORT" ]] || fail 'Frontend and backend ports must differ.'
for managed_file in "$SERVICE_FILE" "$SITE_FILE"; do
    if [[ -e "$managed_file" ]] && ! grep -q '^# Managed by railhop deployment$' "$managed_file"; then
        fail "Refusing to overwrite an existing unmanaged file: $managed_file"
    fi
done
[[ ! -e "$APP_ROOT/current" || -L "$APP_ROOT/current" ]] || fail "$APP_ROOT/current must be a symlink."

export DEBIAN_FRONTEND=noninteractive
need_packages=0
for tool in python3 nginx curl ss; do
    command -v "$tool" >/dev/null || need_packages=1
done
if command -v python3 >/dev/null; then
    python3 -c 'import venv, ensurepip' 2>/dev/null || need_packages=1
fi
if (( need_packages )); then
    apt-get update
    apt-get install -y --no-upgrade python3 python3-venv nginx curl ca-certificates tzdata iproute2
fi
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"'
[[ -f "$PACKAGE_DIR/SHA256SUMS" ]] || fail 'SHA256SUMS is missing. Extract the whole release package first.'
(cd "$PACKAGE_DIR" && sha256sum --check --quiet SHA256SUMS)

if [[ -n "$(ss -H -ltn "sport = :$PORT")" ]]; then
    if [[ ! -f "$SITE_FILE" ]] || ! grep -q "^[[:space:]]*listen $PORT;" "$SITE_FILE"; then
        fail "Port $PORT is occupied. Retry with PORT=8081 bash deploy.sh (choose an unused port)."
    fi
fi
if [[ -n "$(ss -H -ltn "sport = :$BACKEND_PORT")" ]]; then
    if [[ ! -f "$SERVICE_FILE" ]] || ! systemctl is-active --quiet railhop.service; then
        fail "Backend port $BACKEND_PORT is occupied. Set BACKEND_PORT to an unused port."
    fi
    grep -q -- "--port $BACKEND_PORT " "$SERVICE_FILE" || fail 'The backend port is occupied by a different listener.'
fi

install -d -m 755 "$APP_ROOT/releases" "$APP_ROOT/deployment-backups"
if ! id railhop >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$APP_ROOT" --no-create-home --shell /usr/sbin/nologin railhop
fi
release_dir="$(mktemp -d "$APP_ROOT/releases/20261014-10353b5-XXXXXX")"
chmod 755 "$release_dir"
cp -a "$PACKAGE_DIR/backend" "$release_dir/backend"
install -d -m 755 "$release_dir/frontend"
cp -a "$PACKAGE_DIR/frontend/dist" "$release_dir/frontend/dist"
cp "$PACKAGE_DIR/release-manifest.json" "$release_dir/release-manifest.json"
chown -R railhop:railhop "$release_dir/backend/data"
printf 'Installing Python dependencies in %s\n' "$release_dir/.venv"
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install --no-cache-dir -r "$release_dir/backend/requirements.lock"
(cd "$release_dir/backend" && "$release_dir/.venv/bin/python" -c 'from app.main import app; print("Backend import OK")')

backup_dir="$(mktemp -d "$APP_ROOT/deployment-backups/20261014-XXXXXX")"
previous_release="$(readlink -f "$APP_ROOT/current" || true)"
[[ -L "$APP_ROOT/current" ]] || previous_release=''
printf '%s\n' "$previous_release" > "$backup_dir/previous-release.txt"
[[ ! -f "$SERVICE_FILE" ]] || cp -a "$SERVICE_FILE" "$backup_dir/railhop.service"
[[ ! -f "$SITE_FILE" ]] || cp -a "$SITE_FILE" "$backup_dir/railhop.conf"
was_active=0
was_enabled=0
systemctl is-active --quiet railhop.service && was_active=1
systemctl is-enabled --quiet railhop.service && was_enabled=1

rollback() {
    result=$?
    trap - ERR
    set +e
    printf '\nDeployment failed; restoring previous railhop configuration.\n' >&2
    systemctl stop railhop.service
    if [[ -n "$previous_release" ]]; then
        ln -sfn "$previous_release" "$APP_ROOT/current"
    elif [[ -L "$APP_ROOT/current" ]]; then
        unlink "$APP_ROOT/current"
    fi
    if [[ -f "$backup_dir/railhop.service" ]]; then
        cp -a "$backup_dir/railhop.service" "$SERVICE_FILE"
    else
        systemctl disable railhop.service >/dev/null 2>&1
        rm -f -- "$SERVICE_FILE"
    fi
    if [[ -f "$backup_dir/railhop.conf" ]]; then
        cp -a "$backup_dir/railhop.conf" "$SITE_FILE"
    else
        rm -f -- "$SITE_FILE"
    fi
    systemctl daemon-reload
    (( ! was_enabled )) && systemctl disable railhop.service >/dev/null 2>&1
    (( ! was_active )) || systemctl start railhop.service
    if nginx -t; then
        systemctl is-active --quiet nginx && systemctl reload nginx
    fi
    printf 'Backup: %s\nFailed release retained: %s\n' "$backup_dir" "$release_dir" >&2
    exit "$result"
}
trap rollback ERR

ln -s "$release_dir" "$APP_ROOT/.next-$$"
mv -Tf "$APP_ROOT/.next-$$" "$APP_ROOT/current"
sed "s/__BACKEND_PORT__/$BACKEND_PORT/g" "$PACKAGE_DIR/railhop.service.template" > "$SERVICE_FILE"
sed -e "s/__PORT__/$PORT/g" -e "s/__BACKEND_PORT__/$BACKEND_PORT/g" "$PACKAGE_DIR/nginx.conf.template" > "$SITE_FILE"
nginx -t
systemctl daemon-reload
systemctl restart railhop.service

ready=0
for attempt in {1..30}; do
    if curl -fsS --max-time 3 "http://127.0.0.1:$BACKEND_PORT/health" -o "$backup_dir/health.json"; then
        ready=1
        break
    fi
    sleep 1
done
if (( ! ready )); then
    journalctl -u railhop.service -n 40 --no-pager
    false
fi
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("status")=="healthy" and d.get("stations_loaded",0)>1000; print("Stations loaded:", d["stations_loaded"])' "$backup_dir/health.json"
systemctl is-active --quiet railhop.service
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
else
    systemctl start nginx
fi
curl -fsS --max-time 10 "http://127.0.0.1:$PORT/" -o /dev/null
curl -fsS --max-time 10 "http://127.0.0.1:$PORT/health" -o /dev/null
curl -fsS --max-time 10 "http://127.0.0.1:$PORT/api/stations/search?keyword=shanghai&limit=5" -o "$backup_dir/stations.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("code")==200 and any(s.get("telecode")=="SHH" for s in d.get("data",[])); print("Station API OK")' "$backup_dir/stations.json"
systemctl enable railhop.service nginx
trap - ERR
printf '\nDeployment complete. Open: http://106.13.101.112:%s/\n' "$PORT"
printf 'Allow TCP %s in your cloud security group and any active host firewall.\n' "$PORT"
printf 'Release: %s\nBackup: %s\n' "$release_dir" "$backup_dir"
printf 'Logs: journalctl -u railhop.service -f\n'
