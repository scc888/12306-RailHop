"""Explainable conservative detour guard using city-centre geography and elapsed time.

This is a product preference, not a railway permission rule. Distances are
great-circle proxies, NOT track kilometres. Missing/ambiguous data never mean 0.
"""
import json
from math import radians, sin, cos, atan2, sqrt
from pathlib import Path

SNAPSHOT = json.loads((Path(__file__).resolve().parents[2] / 'data' / 'city_coordinates.json').read_text(encoding='utf-8'))


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 6371 * 2 * atan2(sqrt(min(1,h)), sqrt(max(0,1-h)))


class RoutePolicy:
    # Slack accommodates city centres, local geography and non-straight railways.
    # A route passing the guard is not a claim of optimality or actual mileage.
    MAX_RATIO = 1.7
    SLACK_KM = 150

    def __init__(self, origin, destination, stations, *, allow_large_detour=False, required=()):
        stations.ensure_loaded()
        self.city_by_code = {s.telecode:s.city_name for s in stations.stations}
        self.origin, self.destination = origin, destination
        self.expanded, self.required_order = allow_large_detour, list(required)
        self.required = set(required)
        self.notes = []

    def point(self, code):
        item = SNAPSHOT['cities'].get(self.city_by_code.get(code))
        return (item['latitude'], item['longitude']) if item else None

    def geography(self, codes):
        points = [self.point(c) for c in codes]
        if any(p is None for p in points):
            return None, None
        return sum(distance(a,b) for a,b in zip(points,points[1:])), distance(points[0],points[-1])

    def candidate(self, code):
        total, base = self.geography([self.origin,code,self.destination])
        if total is None:
            note = '部分城市缺少可核对坐标；默认排除无法判断方向的自动候选，可主动扩大范围或指定站。'
            if note not in self.notes:
                self.notes.append(note)
            return self.expanded or code in self.required
        return self.expanded or code in self.required or total <= base*self.MAX_RATIO+self.SLACK_KM

    def evaluate(self, codes, minutes):
        total, base = self.geography(codes)
        # 36h minimum preserves normal overnight trains; long trips scale with
        # geography at a conservative 50km/h plus 12h for station waiting.
        time_limit = max(36*60, (base/50*60+12*60)) if base is not None else None
        unusual = total is None or total > base*self.MAX_RATIO+self.SLACK_KM or minutes > time_limit
        manual = bool(self.required.intersection(codes[1:-1]))
        mode = 'manual' if manual else 'expanded' if self.expanded else 'normal'
        warnings = []
        if total is None:
            warnings.append('缺少城市坐标，无法判断绕行程度，请自行核对经由站和全程耗时。')
        elif unusual:
            warnings.append('此路线可能明显绕行或等待较长，请核对经由站和全程耗时。')
        if manual and not self.expanded:
            # Only exempt the deviation the user explicitly requested. Automatic
            # extra stops must still stay within the mandatory-path envelope.
            mandatory = [codes[0], *self.required_order, codes[-1]]
            manual_distance, _ = self.geography(mandatory)
            extra = [c for c in codes[1:-1] if c not in self.required]
            if total is None or manual_distance is None:
                if extra:
                    return False, {}
            else:
                manual_time_limit = max(36*60,manual_distance/50*60+12*60)
                if total > manual_distance*self.MAX_RATIO+self.SLACK_KM or minutes > manual_time_limit:
                    return False, {}
        if unusual and mode == 'normal':
            return False, {}
        return True, dict(mode=mode, warnings=warnings,
            geographic_km=round(total,1) if total is not None else None,
            geographic_direct_km=round(base,1) if base is not None else None,
            distance_kind='city-centre great-circle proxy, not railway mileage',
            elapsed_minutes=minutes, elapsed_limit_minutes=round(time_limit) if time_limit is not None else None,
            source_url=SNAPSHOT['source_info'], checked_at=SNAPSHOT['checked_at'])
