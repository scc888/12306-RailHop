"""Bounded label search: actual stations, dates and seat availability connect legs."""
import hashlib
import time
import logging
import heapq
from collections import OrderedDict
from datetime import datetime, timedelta
from ..config import settings
from ..models.transfer_schemas import TransferConnection, TransferPlan, TransferSearchMeta, TransferSearchResult
from .client_12306 import RailwayQueryError
from .transfer_ticket_gateway import CST
from .station_service import station_service
from .transfer_candidates import TransferCandidateDiscovery

logger = logging.getLogger(__name__)


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
            cache_seconds=settings.TRANSFER_CACHE_SECONDS, cache_size=settings.TRANSFER_CACHE_SIZE,
            discovery_seconds=settings.TRANSFER_DISCOVERY_SECONDS, discovery_probes=settings.TRANSFER_DISCOVERY_PROBES,
            discovery_trains=settings.TRANSFER_DISCOVERY_TRAINS)
        self.limits.update(limits or {})

    def search(self, request, now=None, *, origin_codes=None, destination_codes=None, budget_seconds=None, route_policy=None,
               first_train=None, candidate_tickets=None):
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

        explicit_origins = getattr(request, 'from_station_codes', None)
        explicit_destinations = getattr(request, 'to_station_codes', None)
        origins = endpoint_codes(request.from_station, request.from_scope,
            origin_codes if origin_codes is not None else explicit_origins)
        destinations = endpoint_codes(request.to_station, request.to_scope,
            destination_codes if destination_codes is not None else explicit_destinations)
        max_transfers = getattr(request, 'max_transfers', None)
        transfer_limit = max_transfers or request.transfer_count
        required = request.ordered_via_stations
        required_stations = self.stations.validate_via(required)
        if any(code in origins | destinations for code in required):
            raise ValueError('指定中转站不能属于所选起点或终点范围')
        meta = TransferSearchMeta(queried_at=now, candidate_station_codes=[], limits=self.limits,
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

        if request.from_scope == 'city' or request.to_scope == 'city':
            if explicit_origins is not None or explicit_destinations is not None:
                meta.coverage_notes.append('明确选中的实际起终点车站分别参与查询，共用查询与时间预算；预算耗尽时可能未覆盖全部站对和日期。')
            else:
                meta.coverage_notes.append('城市范围依据12306车站字典；接纳代表站查询返回的同城实际车站，未逐一遍历全部站对。')
            if ((len(origins) > 1 and explicit_origins is None) or
                    (len(destinations) > 1 and explicit_destinations is None)):
                truncated('city_representative_query')
        deadline = time.monotonic() + min(self.limits['max_seconds'],
            self.limits['max_seconds'] if budget_seconds is None else max(0, budget_seconds))

        def expired():
            if time.monotonic() >= deadline:
                truncated('time_limit')
                return True
            return False

        local_cache = {}
        raw_cache = {}
        success_count = 0
        last_request_at = None
        stage_query_ceiling = self.limits['max_queries']
        stage_deadline = deadline

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
            raw_key = (day, a, b)
            if raw_key in raw_cache and hasattr(self.gateway, 'legs_from_tickets'):
                values = self.gateway.legs_from_tickets(raw_cache[raw_key], day, a, b, request.allowed_seats,
                    allowed_origin_codes=query_origins, allowed_destination_codes=query_destinations)
                if self.gateway.last_issues:
                    meta.failed_pairs.append(dict(date=day.isoformat(), from_station=a, to_station=b,
                        reason='；'.join(dict.fromkeys(self.gateway.last_issues))))
                local_cache[key] = values
                return values
            if meta.query_count >= self.limits['max_queries']:
                truncated('query_limit')
                return None
            # Reserve later-leg budgets only after a path exists to advance.
            # Before that, borrowing avoids abandoning late candidates with
            # most of the total budget still unused.
            if next_paths and (meta.query_count >= stage_query_ceiling or time.monotonic() >= stage_deadline):
                truncated('stage_budget')
                return None
            if last_request_at is not None:
                pause = self.limits['request_interval'] - (time.monotonic() - last_request_at)
                if pause > 0:
                    active_deadline = stage_deadline if next_paths else deadline
                    self.sleep(min(pause, max(0, active_deadline - time.monotonic())))
            remaining = (stage_deadline if next_paths else deadline) - time.monotonic()
            if remaining <= 0:
                truncated('time_limit' if time.monotonic() >= deadline else 'stage_budget')
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

        discovery_cache = {}
        discovery_deadline = min(deadline, time.monotonic() + self.limits['discovery_seconds'])

        def discover(kind, day, a, b, load):
            nonlocal success_count, last_request_at
            if expired():
                return None
            if time.monotonic() >= discovery_deadline:
                truncated('discovery_limit')
                return None
            key = (kind, day, a, b)
            if key in discovery_cache:
                return discovery_cache[key]
            if meta.query_count >= self.limits['max_queries']:
                truncated('query_limit')
                return None
            if last_request_at is not None:
                pause = self.limits['request_interval'] - (time.monotonic() - last_request_at)
                if pause > 0:
                    self.sleep(min(pause, max(0, discovery_deadline - time.monotonic())))
            remaining = discovery_deadline - time.monotonic()
            if remaining <= 0:
                truncated('discovery_limit')
                return None
            meta.query_count += 1
            try:
                values = load(min(remaining, self.limits['query_timeout']))
                success_count += 1
            except RailwayQueryError:
                values = []
                meta.failed_pairs.append(dict(date=day.isoformat(), from_station=a, to_station=b,
                    kind=kind[0] if isinstance(kind, tuple) else kind, reason='铁路候选车次或经停站查询失败，请稍后重试'))
                logger.warning('Transfer candidate discovery failed: kind=%s', kind[0] if isinstance(kind, tuple) else kind)
            finally:
                last_request_at = time.monotonic()
            discovery_cache[key] = values
            if kind == 'candidate_trains':
                raw_cache[(day,a,b)] = values
            return values

        sources = {code: ['manual'] for code in required}
        available = []
        if len(required) < transfer_limit:
            if hasattr(self.gateway, 'candidate_trains'):
                dynamic = TransferCandidateDiscovery(self.stations, self.gateway, route_policy).find(
                    request, origins, destinations, discover, first_train=first_train,
                    initial_tickets=candidate_tickets,
                    max_probes=self.limits['discovery_probes'], max_trains=self.limits['discovery_trains'])
                for code, kinds in dynamic.items():
                    sources.setdefault(code, []).extend(kinds)
                truncated('dynamic_discovery')
                meta.coverage_notes.append('候选来自相关列车经停站及全车站字典的方向探测；无直达车次仍尝试发现候选，未遍历全国全部车次和站对。')
            for reference in self.stations.search('', 10000):
                code = reference.station_code
                if code not in origins | destinations and (route_policy is None or route_policy.candidate(code)):
                    sources.setdefault(code, []).append('convenience_reference')
            auto = [code for code in sources if code not in required]
            # Discovery insertion order reflects timetable and route diversity;
            # the reference catalogue already has its own priority order.
            auto.sort(key=lambda code: ('selected_train_stops' not in sources[code],
                'train_stops' not in sources[code], 'direction_probe' not in sources[code]))
            available = [self.stations.station(code) for code in auto]
        candidates = (required_stations + available)[:max(self.limits['max_candidates'], len(required))]
        if len(required_stations) + len(available) > len(candidates):
            truncated('candidate_limit')
        by_code = {s.station_code: s for s in candidates}
        meta.candidate_station_codes = list(by_code)
        meta.candidate_station_names = {code: s.station_name for code, s in by_code.items()}
        meta.candidate_sources = {code: list(dict.fromkeys(sources[code])) for code in by_code}
        meta.station_data_checked_at = min((s.verified_at for s in candidates if s.verified_at), default=None)
        if route_policy:
            meta.coverage_notes.extend(note for note in route_policy.notes if note not in meta.coverage_notes)
        meta.coverage_notes.append('便捷换乘状态未核实的同站中转默认预留60分钟，可能需要出站重新安检；自定义时间按个人设置。')
        logger.info('Transfer candidates ready: total=%s, manual=%s, discovery_queries=%s',
            len(candidates), len(required), meta.query_count)

        paths = [([], [], [])]  # legs, intermediate station codes, connection records
        complete = {}
        expanded = 0
        for stage in range(transfer_limit + 1):
            if expired() or not paths:
                break
            remaining_stages = transfer_limit + 1 - stage
            remaining_queries = max(0, self.limits['max_queries'] - meta.query_count)
            stage_query_ceiling = meta.query_count + (remaining_queries + remaining_stages - 1) // remaining_stages
            stage_started = time.monotonic()
            stage_deadline = stage_started + max(0, deadline - stage_started) / remaining_stages
            next_paths = []
            next_path_keys = set()
            # One job owns a station-pair/date response and all prefixes which
            # can consume it. This also retains late-departing prefixes when
            # the last available query is shared with an earlier departure.
            jobs = {}
            paths.sort(key=lambda p: (p[0][-1].arrival_at - p[0][0].departure_at).total_seconds() if p[0] else 0)
            for prefix_rank, (legs, via, connections) in enumerate(paths):
                if expired():
                    break
                if expanded >= self.limits['max_states']:
                    truncated('state_limit')
                    break
                expanded += 1
                matched = sum(1 for code in via if code in required)
                can_finish = (stage >= 1 and matched == len(required)
                    and (max_transfers is not None or stage == transfer_limit))
                targets = ([request.to_station] if can_finish else [])
                if stage < transfer_limit:
                    targets += list(by_code)
                for target_rank, target in enumerate(targets):
                    final = can_finish and target == request.to_station
                    if target in via:
                        continue
                    if not final:
                        if target in required and target != required[matched]:
                            continue
                        remaining_required = len(required) - matched - int(target in required)
                        if remaining_required > transfer_limit - stage - 1:
                            continue
                    starts = [legs[-1].to_station] if legs else ([first_train.selection.from_station]
                        if first_train is not None else
                        (sorted(origins) if explicit_origins is not None else [request.from_station]))
                    ends = (sorted(destinations) if explicit_destinations is not None else [request.to_station]) if final else [target]
                    for start in starts:
                        for end in ends:
                            if start == end:
                                continue
                            first_day = legs[-1].arrival_at.date() if legs else request.train_date
                            horizon = legs[0].departure_at + timedelta(hours=self.limits['horizon_hours']) if legs else None
                            last_day = horizon.date() if horizon else request.train_date
                            day = first_day
                            while day <= last_day:
                                if expired():
                                    break
                                day_start = datetime.combine(day, datetime.min.time(), CST)
                                earliest = max(day_start, now)
                                if legs:
                                    station = by_code[start]
                                    official = station.reference_minutes_on(day)
                                    minimum = request.min_transfer_minutes if request.min_transfer_minutes is not None else (
                                        official or (15 if station.convenient_transfer_confirmed else 60))
                                    earliest = max(earliest, legs[-1].arrival_at + timedelta(minutes=minimum))
                                    if station.same_day_only and day != legs[-1].arrival_at.date():
                                        break
                                if earliest.date() <= day and (horizon is None or earliest < horizon):
                                    lower_bound = (earliest - legs[0].departure_at).total_seconds() if legs else 0
                                    query_origins = frozenset({start} if legs or first_train is not None else origins)
                                    query_destinations = frozenset(destinations if final else {end})
                                    key = (day, start, end, query_origins, query_destinations)
                                    rank = (lower_bound, target_rank, prefix_rank)
                                    if key not in jobs:
                                        jobs[key] = [rank, []]
                                    else:
                                        jobs[key][0] = min(jobs[key][0], rank)
                                    jobs[key][1].append((legs, via, connections, earliest, horizon, final))
                                day += timedelta(days=1)
            queue = [(rank, serial, key, consumers) for serial, (key, (rank, consumers)) in enumerate(jobs.items())]
            heapq.heapify(queue)
            finish_queue = [entry for entry in queue if entry[3][0][-1]] if stage < transfer_limit else []
            heapq.heapify(finish_queue)
            finish_waiting = {id(consumer[0]) for entry in finish_queue for consumer in entry[3]}
            processed = set()
            while queue:
                if expired():
                    break
                # At a max-depth search, first give existing prefixes a chance
                # to finish. Otherwise the N*N continuation pairs can consume
                # the budget before the Nth one-transfer route is examined.
                # Retain a query in this stage for discovering a deeper prefix.
                finishing = (finish_waiting and finish_queue and
                    meta.query_count < stage_query_ceiling - 1 and time.monotonic() < stage_deadline)
                _, serial, (day, start, target, query_origins, query_destinations), consumers = heapq.heappop(
                    finish_queue if finishing else queue)
                if serial in processed:
                    continue
                processed.add(serial)
                values = query(day, start, target, set(query_origins), set(query_destinations))
                if values is None:
                    break
                if consumers[0][-1]:
                    finish_waiting.difference_update(id(consumer[0]) for consumer in consumers)
                for legs, via, connections, earliest, horizon, final in consumers:
                    for item in values:
                        if expired():
                            break
                        high_speed = item.train_code[:1].upper() in ('G','D','C')
                        if request.train_type == 'high_speed' and not high_speed:
                            continue
                        if request.train_type == 'regular' and high_speed:
                            continue
                        if item.from_station not in query_origins or item.to_station not in query_destinations:
                            continue
                        if not legs and first_train is not None:
                            anchor = first_train.selection
                            if (item.train_no != anchor.train_no or item.run_date != anchor.run_date
                                    or item.from_station != anchor.from_station
                                    or item.departure_at != first_train.departure_at
                                    or item.arrival_at >= first_train.arrival_at):
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
                            required_minutes = (request.min_transfer_minutes if request.min_transfer_minutes is not None
                                                else official_minutes or (15 if station.convenient_transfer_confirmed else 60))
                            if item.departure_at < legs[-1].arrival_at + timedelta(minutes=required_minutes):
                                continue
                            prefixes = station.allowed_train_prefixes
                            if prefixes and any(x.train_code[:1].upper() not in prefixes for x in (legs[-1], item)):
                                continue
                            wait = int((item.departure_at - legs[-1].arrival_at).total_seconds() // 60)
                            new_connections = connections + [TransferConnection(station=station, wait_minutes=wait,
                                required_minutes=required_minutes, official_min_minutes=official_minutes,
                                source_url=station.source_url)]
                        new_legs = legs + [item]
                        if final:
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
                        else:
                            new_via = via + [item.to_station]
                            # City station-pair responses can repeat the same
                            # actual train. Deduplicate physical paths before
                            # either admission or later expansion spends states.
                            prefix_key = (tuple((part.train_no, part.run_date, part.from_station,
                                part.to_station, part.departure_at, part.arrival_at) for part in new_legs),
                                tuple(new_via), tuple((connection.station.station_code,
                                    connection.required_minutes, connection.official_min_minutes)
                                    for connection in new_connections))
                            if prefix_key in next_path_keys:
                                continue
                            if len(next_paths) < self.limits['max_states']:
                                next_path_keys.add(prefix_key)
                                next_paths.append((new_legs, new_via, new_connections))
                            else:
                                truncated('state_limit')
            paths = next_paths
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
        return (plan.total_minutes, len(plan.connections), plan.legs[-1].arrival_at, plan.id)
