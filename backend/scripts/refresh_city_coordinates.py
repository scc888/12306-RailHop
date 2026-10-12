"""Rebuild the offline, attributed city-centre snapshot; no runtime geocoding.

Only unambiguous exact Chinese city aliases from GeoNames are joined to the
12306 dictionary. Coordinates are geographical proxies, never railway mileage.
Run from backend: python scripts/refresh_city_coordinates.py
"""
import hashlib
import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.station_service import station_service

URL = 'https://download.geonames.org/export/dump/cities15000.zip'


def main():
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    raw = response.content
    archive = zipfile.ZipFile(io.BytesIO(raw))
    aliases = {}
    for line in archive.read('cities15000.txt').decode('utf-8').splitlines():
        fields = line.split('\t')
        if fields[8] != 'CN' or fields[6] != 'P':
            continue
        entry = dict(geoname_id=int(fields[0]), latitude=float(fields[4]), longitude=float(fields[5]))
        for name in {fields[1], *fields[3].split(',')}:
            aliases.setdefault(name, {})[fields[0]] = entry
    station_service.ensure_loaded()
    cities = {}
    for station in station_service.stations:
        name = station.city_name
        if not name or name in cities:
            continue
        matches = aliases.get(name, {}) or aliases.get(name + '市', {})
        if len(matches) == 1:
            cities[name] = next(iter(matches.values()))
    snapshot = dict(source_url=URL, source_info='https://www.geonames.org/export/',
        license='CC BY 4.0', checked_at=date.today().isoformat(),
        archive_sha256=hashlib.sha256(raw).hexdigest(),
        description='GeoNames city centres, exact unambiguous Chinese alias match; not station coordinates or railway distance.',
        cities=dict(sorted(cities.items())))
    target = Path(__file__).resolve().parents[1] / 'data' / 'city_coordinates.json'
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(cities)} cities. Missing city data is deliberately not guessed.')
    for name in ['北京', '上海', '长春', '南京', '杭州', '郑州', '武汉', '成都', '重庆', '天津']:
        print(name, cities.get(name))


if __name__ == '__main__':
    main()
