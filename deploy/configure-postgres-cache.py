"""Run on the Docker host to prepare a dedicated RailHop cache database and role.

No credentials are printed. Existing application databases and containers are not changed.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


def configure(container='pgsql16', config_dir=Path('/etc/railhop')):
    config_dir = Path(config_dir)
    env_file = config_dir / 'cache.env'
    network_file = config_dir / 'docker-network'
    if env_file.exists():
        print(f'Cache credentials already exist at {env_file}; kept existing configuration.')
        return
    info = json.loads(subprocess.check_output(['docker','inspect',container], text=True))[0]
    networks = sorted(info['NetworkSettings']['Networks'])
    if len(networks) != 1:
        raise RuntimeError('PostgreSQL must have one unambiguous Docker network; configure the connection manually.')
    admin = next((value.split('=',1)[1] for value in info['Config']['Env']
                  if value.startswith('POSTGRES_USER=')), 'postgres')
    psql = ['docker','exec','-i','-u','postgres',container,'psql','-X','-v','ON_ERROR_STOP=1','-U',admin,'-d','postgres']
    existing = subprocess.check_output(psql + ['-Atc',
        "SELECT EXISTS (SELECT FROM pg_roles WHERE rolname='railhop_cache') OR EXISTS (SELECT FROM pg_database WHERE datname='railhop_cache')"], text=True).strip()
    if existing != 'f':
        raise RuntimeError('railhop_cache already exists without a saved configuration; refusing to change its credentials.')
    password = secrets.token_urlsafe(36)
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Server-generated credentials stay on the Docker host. PostgreSQL utility
    # output is captured so a failed setup cannot echo SQL/passwords to CI logs.
    sql = f"CREATE ROLE railhop_cache LOGIN PASSWORD '{password}';\nCREATE DATABASE railhop_cache OWNER railhop_cache;\n"
    completed = subprocess.run(psql, input=sql, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError('PostgreSQL cache provisioning failed; inspect PostgreSQL server logs locally.')
    connection = f'postgresql://railhop_cache:{password}@{container}:5432/railhop_cache'
    descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(f'QUERY_CACHE_DATABASE_URL={connection}\nTICKET_CACHE_SECONDS=15\n')
    if not network_file.exists():
        descriptor = os.open(network_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(networks[0] + '\n')
    print(f'Dedicated railhop_cache database and role ready; credentials saved to {env_file}.')
    print('The application will use this configuration on its next deployment.')


if __name__ == '__main__':
    try:
        configure(sys.argv[1] if len(sys.argv)>1 else 'pgsql16')
    except Exception as exc:
        print(f'Cache setup failed ({type(exc).__name__}): {exc}', file=sys.stderr)
        sys.exit(1)
