"""Discover bounded route-specific interchange candidates, independent of convenience data."""
from collections import defaultdict
from .route_policy import distance


class TransferCandidateDiscovery:
    def __init__(self, stations, gateway, policy):
        self.stations, self.gateway, self.policy = stations, gateway, policy

    def seeds(self, excluded, limit):
        """Choose probes across cities from the full dictionary, near the route corridor."""
        self.stations.directory.ensure_loaded()
        cities = defaultdict(list)
        for station in self.stations.directory.stations:
            code = station.telecode
            if code in excluded or (self.policy and not self.policy.candidate(code)):
                continue
            rank = (0, 0)
            if self.policy:
                point = self.policy.point(code)
                origin, destination = self.policy.point(self.policy.origin), self.policy.point(self.policy.destination)
                if point and origin and destination:
                    a, b = distance(origin, point), distance(point, destination)
                    rank = (a + b + .3 * abs(a - b), abs(a - b))
                else:
                    rank = (float('inf'), float('inf'))
            # Prefer the city's principal named station when geographical scores tie.
            principal = 0 if station.name == station.city_name else 1
            cities[station.city_code or code].append(((*rank, principal, code), code))
        groups = [sorted(values) for values in cities.values()]
        groups.sort(key=lambda values: values[0][0])
        return [values[0][1] for values in groups[:limit]]

    def find(self, request, origins, destinations, run, *, first_train=None, max_probes=4, max_trains=8):
        sources = {}
        excluded = origins | destinations
        seen_trains = set()
        self.stations.directory.ensure_loaded()
        code_by_name = self.stations.directory.name_to_code

        def add(code, source):
            if code in excluded or code not in self.stations.directory.code_to_name:
                return
            if self.policy and not self.policy.candidate(code):
                return
            if source not in sources.setdefault(code, []):
                sources[code].append(source)

        def inspect(day, tickets, allowed_origins, allowed_destinations, *, selected=False):
            for ticket in tickets or []:
                high = ticket.train_code[:1].upper() in ('G', 'D', 'C')
                if ((request.train_type == 'high_speed' and not high) or
                        (request.train_type == 'regular' and high)):
                    continue
                if ticket.from_station_telecode not in allowed_origins or ticket.to_station_telecode not in allowed_destinations:
                    continue
                key = (ticket.train_no, ticket.run_date, day, ticket.from_station_telecode, ticket.to_station_telecode)
                if key in seen_trains or len(seen_trains) >= max_trains:
                    continue
                seen_trains.add(key)
                stops = run(('train_stops', ticket.train_no, ticket.run_date), day, ticket.from_station_telecode, ticket.to_station_telecode,
                    lambda timeout: self.gateway.train_stops(day, ticket, timeout))
                if stops is None:
                    return
                try:
                    ordered = sorted(stops, key=lambda stop: int(stop.station_no))
                    codes = [code_by_name.get(stop.station_name) for stop in ordered]
                    a, b = ticket.from_station_telecode, ticket.to_station_telecode
                    if codes.count(a) != 1 or codes.count(b) != 1 or codes.index(a) >= codes.index(b):
                        continue
                    # Only actual intermediate stops of the queried interval. Selected
                    # train discovery must never extend beyond its destination.
                    for code in codes[codes.index(a)+1:codes.index(b)]:
                        add(code, 'train_stops')
                        if selected:
                            add(code, 'selected_train_stops')
                except (ValueError, TypeError):
                    continue

        if first_train is not None:
            inspect(request.train_date, [first_train], origins, destinations, selected=True)
            if request.transfer_count == 1:
                return sources
        else:
            direct = run('candidate_trains', request.train_date, request.from_station, request.to_station,
                lambda timeout: self.gateway.candidate_trains(request.train_date, request.from_station, request.to_station, timeout))
            inspect(request.train_date, direct, origins, destinations)
        # Probe both sides even without a direct train, so discovery is not limited
        # to the stops of trains that already connect the complete journey.
        for code in self.seeds(excluded, max_probes):
            add(code, 'direction_probe')
            for a, b, starts, ends in [(request.from_station, code, origins, {code}),
                                      (code, request.to_station, {code}, destinations)]:
                trains = run('candidate_trains', request.train_date, a, b,
                    lambda timeout, a=a, b=b: self.gateway.candidate_trains(request.train_date, a, b, timeout))
                if trains is None:
                    return sources
                inspect(request.train_date, trains, starts, ends)
        return sources
