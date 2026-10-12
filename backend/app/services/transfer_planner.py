"""Bounded label search: actual stations, dates and seat availability connect legs."""
import hashlib
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from ..config import settings
from ..models.transfer_schemas import TransferConnection, TransferPlan, TransferSearchMeta, TransferSearchResult
from .client_12306 import RailwayQueryError
from .transfer_ticket_gateway import CST
from .station_service import station_service


class TransferPlanner:
    def __init__(self, stations, gateway, limits=None, sleep_fn=time.sleep):
        self.stations = stations
        self.gateway = gateway
        self.sleep = sleep_fn
        self.cache = OrderedDict()
        self.limits = dict(max_candidates=settings.TRANSFER_MAX_CANDIDATES,
            max_queries=settings.TRANSFER_MAX_QUERIES, max_seconds=settings.TRANSFER_MAX_SECONDS,
            max_states=settings.TRANSFER_MAX_STATES, max_results=settings.TRANSFER_MAX_RESULTS,
            horizon_hours=settings.TRANSFER_HORIZON_HOURS,
            request_interval=settings.TRANSFER_REQUEST_INTERVAL, query_timeout=settings.TRANSFER_QUERY_TIMEOUT,
            cache_seconds=settings.TRANSFER_CACHE_SECONDS, cache_size=settings.TRANSFER_CACHE_SIZE)
        self.limits.update(limits or {})

    def search(self, request, now=None, *, origin_codes=None, destination_codes=None, budget_seconds=None, route_policy=None):
        now = now or datetime.now(CST)
        if request.train_date < now.date():
            raise ValueError('乘车日期不能早于今天')
        def endpoint_codes(anchor, scope, supplied):
            if scope == 'station':
                return {anchor}
            values = set(supplied) if supplied is not None else {
                s.telecode for s in station_service.city_stations(anchor)}
            if not values or anchor not in values:
                raise ValueError('无法识别起点或终点的城市范围，请重新选择城市')
            return values

        origins = endpoint_codes(request.from_station, request.from_scope, origin_codes)
        destinations = endpoint_codes(request.to_station, request.to_scope, destination_codes)
        required = request.ordered_via_stations
        self.stations.validate_via(required)
        if any(code in origins | destinations for code in required):
            raise ValueError('指定中转站不能属于所选起点或终点范围')
        available = [s for s in self.stations.search('', 10000)
                     if s.station_code not in origins | destinations]
        if route_policy is not None:
            available = [s for s in available if route_policy.candidate(s.station_code)]
        by_code = {s.station_code: s for s in available}
        candidates = [by_code[c] for c in required] + [s for s in available if s.station_code not in required]
        candidates = candidates[:max(self.limits['max_candidates'], len(required))]
        by_code = {s.station_code: s for s in candidates}
        meta = TransferSearchMeta(queried_at=now, candidate_station_codes=list(by_code), limits=self.limits,
            station_data_checked_at=min((s.verified_at for s in candidates), default=None),
            from_scope=request.from_scope, to_scope=request.to_scope,
            origin_station_codes=sorted(origins), destination_station_codes=sorted(destinations))
        if route_policy is not None:
            meta.coverage_notes.extend(route_policy.notes)
            meta.coverage_notes.append('默认使用城市中心地理距离与全程耗时排除明显绕行；地理距离不是实际铁路里程。')
            if request.allow_large_detour:
                meta.coverage_notes.append('已主动扩大绕行范围，仍受72小时行程及查询预算限制。')

        def truncated(reason):
            meta.truncated = True
            if reason not in meta.truncation_reasons:
                meta.truncation_reasons.append(reason)

        if len(available) > len(candidates):
            truncated('candidate_limit')
        if request.from_scope == 'city' or request.to_scope == 'city':
            meta.coverage_notes.append('城市范围依据12306车站字典；接纳代表站查询返回的同城实际车站，未逐一遍历全部站对。')
            if len(origins) > 1 or len(destinations) > 1:
                truncated('city_representative_query')
        if len(candidates) < request.transfer_count:
            if meta.truncated:
                meta.status = 'partial'
            return TransferSearchResult(plans=[], meta=meta)
        deadline = time.monotonic() + min(self.limits['max_seconds'],
            self.limits['max_seconds'] if budget_seconds is None else max(0, budget_seconds))

        def expired():
            if time.monotonic() >= deadline:
                truncated('time_limit')
                return True
            return False

        local_cache = {}
        success_count = 0
        last_request_at = None

        def query(day, a, b, query_origins, query_destinations):
            nonlocal success_count, last_request_at
            if expired():
                return None
            key = (day, a, b, tuple(request.allowed_seats), tuple(sorted(query_origins)),
                   tuple(sorted(query_destinations)))
            if key in local_cache:
                return local_cache[key]
            cached = self.cache.get(key)
            if cached and time.monotonic() - cached[0] < self.limits['cache_seconds']:
                local_cache[key] = cached[1]
                success_count += 1
                return cached[1]
            if meta.query_count >= self.limits['max_queries']:
                truncated('query_limit')
                return None
            if last_request_at is not None:
                pause = self.limits['request_interval'] - (time.monotonic() - last_request_at)
                if pause > 0:
                    self.sleep(min(pause, max(0, deadline - time.monotonic())))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                truncated('time_limit')
                return None
            meta.query_count += 1
            try:
                if query_origins == {a} and query_destinations == {b}:
                    values = self.gateway.query(day, a, b, request.allowed_seats,
                                                min(remaining, self.limits['query_timeout']))
                else:
                    values = self.gateway.query_scoped(day, a, b, request.allowed_seats,
                        min(remaining, self.limits['query_timeout']), allowed_origin_codes=query_origins,
                        allowed_destination_codes=query_destinations)
                success_count += 1
                issues = getattr(self.gateway, 'last_issues', [])
                if issues:
                    meta.failed_pairs.append(dict(date=day.isoformat(), from_station=a, to_station=b,
                                                  reason='；'.join(dict.fromkeys(issues))))
                else:
                    self.cache[key] = (time.monotonic(), values)
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.limits['cache_size']:
                        self.cache.popitem(last=False)
            except RailwayQueryError:
                values = []
                meta.failed_pairs.append(dict(date=day.isoformat(), from_station=a, to_station=b,
                                              reason='铁路接口查询失败，请稍后重试'))
            finally:
                last_request_at = time.monotonic()
            local_cache[key] = values
            return values

        paths = [([], [], [])]  # legs, intermediate station codes, connection records
        complete = {}  # Retain only the best max_results unique plans during enumeration.
        expanded = 0
        exhausted = False
        for stage in range(request.transfer_count + 1):
            if expired():
                break
            next_paths = []
            paths.sort(key=lambda p: (p[0][-1].arrival_at - p[0][0].departure_at).total_seconds() if p[0] else 0)
            for legs, via, connections in paths:
                if expired():
                    exhausted = True
                    break
                if expanded >= self.limits['max_states']:
                    truncated('state_limit')
                    exhausted = True
                    break
                expanded += 1
                start = legs[-1].to_station if legs else request.from_station
                targets = [request.to_station] if stage == request.transfer_count else list(by_code)
                matched = sum(1 for c in via if c in required)
                # Required stations already seen must form exactly the required prefix.
                for target in targets:
                    if expired():
                        exhausted = True
                        break
                    if target in via or target == start:
                        continue
                    if stage < request.transfer_count:
                        if target in required and target != required[matched]:
                            continue
                        remaining_required = len(required) - matched - int(target in required)
                        if remaining_required > request.transfer_count - stage - 1:
                            continue
                    elif matched != len(required):
                        continue
                    # Use the actual connecting departure day to check reference validity below.
                    effective = max(request.min_transfer_minutes or 0, 1) if legs else 0
                    earliest = legs[-1].arrival_at + timedelta(minutes=effective) if legs else now
                    horizon = legs[0].departure_at + timedelta(hours=self.limits['horizon_hours']) if legs else None
                    day = earliest.date() if legs else request.train_date
                    last_day = horizon.date() if legs else request.train_date
                    query_origins = {start} if legs else origins
                    query_destinations = destinations if stage == request.transfer_count else {target}
                    while day <= last_day:
                        values = query(day, start, target, query_origins, query_destinations)
                        if values is None:
                            exhausted = True
                            break
                        for item in values:
                            if expired():
                                exhausted = True
                                break
                            high_speed = item.train_code[:1].upper() in ('G','D','C')
                            if request.train_type == 'high_speed' and not high_speed:
                                continue
                            if request.train_type == 'regular' and high_speed:
                                continue
                            if item.from_station not in query_origins or item.to_station not in query_destinations:
                                continue
                            if item.departure_at.date() != day or item.departure_at < earliest:
                                continue
                            if item.arrival_at <= item.departure_at or not item.seats:
                                continue
                            end_limit = horizon or item.departure_at + timedelta(hours=self.limits['horizon_hours'])
                            if item.arrival_at > end_limit:
                                truncated('horizon_limit')
                                continue
                            if any(previous.train_no == item.train_no and
                                   (previous.run_date is None or item.run_date is None or previous.run_date == item.run_date)
                                   for previous in legs):
                                continue
                            new_connections = connections
                            if legs:
                                station = by_code[start]
                                official_minutes = station.reference_minutes_on(item.departure_at.date())
                                required_minutes = max(request.min_transfer_minutes or 0, official_minutes or 15)
                                if item.departure_at < legs[-1].arrival_at + timedelta(minutes=required_minutes):
                                    continue
                                if station.same_day_only and legs[-1].arrival_at.date() != item.departure_at.date():
                                    continue
                                prefixes = station.allowed_train_prefixes
                                if prefixes and any(x.train_code[:1].upper() not in prefixes for x in (legs[-1], item)):
                                    continue
                                wait = int((item.departure_at - legs[-1].arrival_at).total_seconds() // 60)
                                new_connections = connections + [TransferConnection(station=station, wait_minutes=wait,
                                    required_minutes=required_minutes, official_min_minutes=official_minutes,
                                    source_url=station.source_url)]
                            new_legs = legs + [item]
                            if stage == request.transfer_count:
                                plan = self._plan(new_legs, new_connections)
                                if route_policy is not None:
                                    accepted, assessment = route_policy.evaluate(
                                        [new_legs[0].from_station] + [l.to_station for l in new_legs], plan.total_minutes)
                                    if not accepted:
                                        continue
                                    plan.route_assessment = assessment
                                complete[plan.id] = plan
                                if len(complete) > self.limits['max_results']:
                                    truncated('result_limit')
                                    worst = max(complete, key=lambda key: self._sort_key(complete[key], request.sort_by))
                                    del complete[worst]
                            elif len(next_paths) < self.limits['max_states']:
                                next_paths.append((new_legs, via + [target], new_connections))
                            else:
                                truncated('state_limit')
                        if exhausted:
                            break
                        day += timedelta(days=1)
                    if exhausted:
                        break
                if exhausted:
                    break
            paths = next_paths
            if exhausted:
                break
        expired()
        plans = sorted(complete.values(), key=lambda plan: self._sort_key(plan, request.sort_by))
        if meta.failed_pairs:
            meta.status = 'partial' if success_count else 'upstream_error'
        elif meta.truncated:
            meta.status = 'partial'
        return TransferSearchResult(plans=plans[:self.limits['max_results']], meta=meta)

    @staticmethod
    def _plan(legs, connections):
        selected = [min(leg.seats, key=lambda s: (s.price_fen is None, s.price_fen or 0, s.code)) for leg in legs]
        known = sum(s.price_fen for s in selected if s.price_fen is not None)
        identity = '|'.join(f'{leg.train_no}:{leg.from_station}:{leg.to_station}:{leg.departure_at.isoformat()}' for leg in legs)
        return TransferPlan(id=hashlib.sha256(identity.encode()).hexdigest()[:20], legs=legs, connections=connections,
            total_minutes=int((legs[-1].arrival_at - legs[0].departure_at).total_seconds() // 60),
            selected_seat_codes=[s.code for s in selected], known_price_fen=known,
            total_price_fen=known if all(s.price_fen is not None for s in selected) else None)

    @staticmethod
    def _sort_key(plan, sort_by):
        if sort_by == 'arrival':
            return (plan.legs[-1].arrival_at, plan.total_minutes, plan.id)
        if sort_by == 'price':
            return (plan.total_price_fen is None, plan.total_price_fen or 0, plan.total_minutes, plan.id)
        return (plan.total_minutes, plan.legs[-1].arrival_at, plan.id)
