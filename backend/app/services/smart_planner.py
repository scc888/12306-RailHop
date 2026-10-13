"""Read-only, fully ticketed continuation on one physical train.

A segment must match the train's internal identity, running day, actual stations
and duration-derived timestamps. No itinerary relies on a later onboard extension.
"""
import re
import hashlib
import time
from datetime import date, datetime, timedelta
from itertools import combinations
from typing import List, Optional

from ..models.schemas import SmartPlan, PlanSegment, TrainTicketInfo
from ..models.transfer_schemas import SEAT_NAMES, TransferSeat, TransferLeg
from ..models.journey_schemas import ShortTicketOption
from .client_12306 import client_12306, RailwayQueryError
from .station_service import station_service
from .transfer_ticket_gateway import CST, has_ticket, parse_price_fen

SEAT_PRIORITY = ['ze', 'zy', 'yw', 'rw', 'srrb', 'swz', 'gr', 'rz', 'yz', 'wz']


class SmartRoutePlanner:
    def calculate_smart_plans(self, train_date: str, train_code: str, train_no: str,
                              from_code: str, to_code: str,
                              allowed_seats: Optional[List[str]] = None,
                              max_tickets: int = 2, max_transfers: Optional[int] = None) -> List[SmartPlan]:
        """Compatibility entrypoint returning only fully ticketed plans."""
        return self.calculate_with_meta(train_date, train_code, train_no, from_code, to_code,
                                        allowed_seats, max_tickets, max_transfers)['plans']

    def calculate_with_meta(self, train_date: str, train_code: str, train_no: str,
                            from_code: str, to_code: str,
                            allowed_seats: Optional[List[str]] = None,
                            max_tickets: int = 2, max_transfers: Optional[int] = None,
                            *, budget_seconds: float = 15, max_queries: int = 45,
                            anchor_ticket: Optional[TrainTicketInfo] = None,
                            include_short_fallback: bool = False, short_fallback_only: bool = False):
        start = time.monotonic()
        deadline = start + max(0, budget_seconds)
        max_queries = max(0, max_queries)
        plans = []
        short_fallbacks = []
        meta = dict(status='complete', query_count=0, failed_queries=[], truncated=False,
                    truncation_reasons=[], warnings=[], notices=[],
                    queried_at=datetime.now(CST).isoformat(),
                    limits=dict(budget_seconds=budget_seconds, max_queries=max_queries))

        def finish():
            if meta['truncated'] or meta['failed_queries'] or meta['warnings']:
                meta['status'] = 'partial'
            if meta['failed_queries'] and not plans and not short_fallbacks:
                meta['status'] = 'upstream_error'
            meta['notices'] = list(dict.fromkeys(meta['warnings'] + meta['truncation_reasons']))
            if meta['failed_queries']:
                meta['notices'].append('部分12306查询失败，同车接续结果可能不完整')
            return dict(plans=plans, short_fallbacks=short_fallbacks, meta=meta)

        def room(network=False):
            reason = None
            if time.monotonic() >= deadline:
                reason = '查询时间达到上限'
            elif network and meta['query_count'] >= max_queries:
                reason = '查询次数达到上限'
            if reason:
                meta['truncated'] = True
                if reason not in meta['truncation_reasons']:
                    meta['truncation_reasons'].append(reason)
                return False
            return True

        cache = {}

        def query(day, a, b):
            key = (day.isoformat(), a, b)
            if not room():
                return []
            if key not in cache:
                if not room(network=True):
                    return []
                meta['query_count'] += 1
                try:
                    cache[key] = client_12306.query_tickets_strict(
                        *key, timeout_seconds=max(.001, deadline - time.monotonic()))
                except RailwayQueryError:
                    meta['failed_queries'].append(dict(train_date=key[0], from_station=a,
                                                       to_station=b, reason='12306余票查询失败'))
                    cache[key] = []
                if not room():
                    return []
            return cache[key]

        try:
            day = date.fromisoformat(train_date)
        except (ValueError, TypeError):
            meta['warnings'].append('出发日期无效')
            return finish()
        seats_allowed = set(SEAT_NAMES if allowed_seats is None else allowed_seats)
        seat_codes = [code for code in SEAT_PRIORITY if code in seats_allowed]
        limit = max(1, min(3, max_tickets if max_transfers is None else max_transfers))
        if limit < 2 or not seat_codes or from_code == to_code:
            return finish()

        candidates = [anchor_ticket] if anchor_ticket is not None else query(day, from_code, to_code)
        anchors = [t for t in candidates if self._identity(t, train_no, from_code, to_code)
                   and self._times(t, day) is not None]
        # Ambiguous upstream identity is not enough evidence to join segments.
        if len(anchors) != 1:
            meta['warnings'].append('未取得可核对运行日期和完整区间的列车信息')
            return finish()
        anchor = anchors[0]
        departure, arrival = self._times(anchor, day)
        run_date = anchor.run_date
        if not room(network=True):
            return finish()
        meta['query_count'] += 1
        try:
            stops = client_12306.query_train_stops_strict(
                train_no, from_code, to_code, train_date,
                timeout_seconds=max(.001, deadline - time.monotonic()))
        except RailwayQueryError:
            meta['failed_queries'].append(dict(train_date=train_date, from_station=from_code,
                                               to_station=to_code, reason='12306停站时刻查询失败'))
            return finish()
        if not room():
            return finish()
        codes = [station_service.get_code(s.station_name) for s in stops]
        if codes.count(from_code) != 1 or codes.count(to_code) != 1:
            meta['warnings'].append('列车停站无法与实际车站准确对应')
            return finish()
        first, last = codes.index(from_code), codes.index(to_code)
        if first >= last:
            return finish()
        stops, codes = stops[first:last + 1], codes[first:last + 1]
        if any(not c for c in codes) or len(codes) != len(set(codes)):
            meta['warnings'].append('停站电报码缺失或存在歧义')
            return finish()
        end = len(stops) - 1
        if end < 2:
            return finish()
        if stops[0].start_time != anchor.start_time or stops[-1].arrive_time != anchor.arrive_time:
            meta['warnings'].append('停站时刻与完整区间列车信息不一致')
            return finish()

        departures, arrivals = {0: departure}, {end: arrival}
        timings_checked = set()
        segment_cache = {}

        def timing(index):
            if index in (0, end):
                return True
            if index in timings_checked:
                return index in departures
            timings_checked.add(index)
            for t in query(day, from_code, codes[index]):
                if not room():
                    return False
                if not self._identity(t, train_no, from_code, codes[index], run_date):
                    continue
                times = self._times(t, day)
                if not times or times[0] != departure:
                    continue
                at = times[1]
                dwell_text = stops[index].stopover_time.strip()
                dwell = re.fullmatch(r'(\d+)(?:分钟|分)?', dwell_text)
                if not dwell or at.strftime('%H:%M') != stops[index].arrive_time:
                    continue
                leave = at + timedelta(minutes=int(dwell.group(1)))
                if (leave.strftime('%H:%M') != stops[index].start_time
                        or not departure < at <= leave < arrival):
                    continue
                arrivals[index], departures[index] = at, leave
                return True
            meta['warnings'].append('部分接续站缺少可核对的停留时间或区间时刻，相关路线尚未验证。')
            return False

        def segment(i, j):
            if not room():
                return None
            if (i, j) in segment_cache:
                return segment_cache[i, j]
            segment_cache[i, j] = None
            if not timing(i) or not timing(j):
                return None
            for t in query(departures[i].date(), codes[i], codes[j]):
                if not room():
                    return None
                if not self._identity(t, train_no, codes[i], codes[j], run_date) or not t.can_buy:
                    continue
                times = self._times(t, departures[i].date())
                if not times or times != (departures[i], arrivals[j]):
                    meta['warnings'].append('同一运行列车的区间时刻无法与完整路线核对，相关接续尚未验证。')
                    continue
                choices = [TransferSeat(code=code, name=SEAT_NAMES[code],
                            availability=getattr(t.seats, code),
                            price_fen=parse_price_fen(t.prices.get(code, '')))
                           for code in seat_codes if has_ticket(getattr(t.seats, code, '--'))]
                if not choices:
                    continue
                selected = choices[0]
                item = PlanSegment(from_station=stops[i].station_name, to_station=stops[j].station_name,
                    from_station_telecode=codes[i], to_station_telecode=codes[j],
                    train_code=t.train_code, start_time=t.start_time, arrive_time=t.arrive_time,
                    departure_at=times[0], arrival_at=times[1], seats=choices,
                    seat_code=selected.code, seat_name=selected.name, seat_status=selected.availability,
                    seat_price=t.prices.get(selected.code, ''), price_fen=selected.price_fen,
                    tip='按本段有效车票对应的席位乘车；车厢和座位号以出票为准')
                segment_cache[i, j] = item
                return item
            return None

        if include_short_fallback:
            # Keep one option per running train: the farthest verified buyable prefix.
            for index in range(end - 1, 0, -1):
                if not room():
                    return finish()
                prefix = segment(0, index)
                if prefix is None:
                    continue
                choices = prefix.seats
                selected = min(choices, key=lambda s:(s.price_fen is None,s.price_fen or 0,s.code))
                identity = f'{train_no}:{run_date}:{from_code}:{codes[index]}:{to_code}:{departure.isoformat()}'
                short_fallbacks.append(ShortTicketOption(
                    id=hashlib.sha256(identity.encode()).hexdigest()[:20],
                    ticketed_leg=TransferLeg(train_no=train_no,train_code=prefix.train_code,
                        from_station=from_code,to_station=codes[index],from_station_name=prefix.from_station,
                        to_station_name=prefix.to_station,departure_at=prefix.departure_at,arrival_at=prefix.arrival_at,
                        seats=choices,queried_at=datetime.now(CST),run_date=datetime.strptime(run_date,'%Y%m%d').date()),
                    selected_seat_code=selected.code,destination_station=to_code,
                    destination_station_name=stops[-1].station_name,scheduled_arrival_at=arrival,
                    known_price_fen=selected.price_fen or 0))
                break
        if short_fallback_only:
            return finish()

        for ticket_count in range(2, limit + 1):
            for via in combinations(range(1, end), ticket_count - 1):
                if not room():
                    return finish()
                points = (0, *via, end)
                parts = []
                for i, j in zip(points, points[1:]):
                    item = segment(i, j)
                    if item is None:
                        break
                    parts.append(item)
                if len(parts) != ticket_count:
                    continue
                if not room():
                    return finish()
                prices = [p.price_fen for p in parts]
                known = sum(p for p in prices if p is not None)
                via_names = '、'.join(stops[i].station_name for i in via)
                plans.append(SmartPlan(plan_type=2, plan_type_name='同车接续',
                    train_code=train_code, train_no=train_no, ticket_count=ticket_count,
                    transfer_count=ticket_count - 1, title=f'同一趟列车，经{via_names}分段接续',
                    segments=parts, recommendation_score=100 - ticket_count * 5, risk_level=0,
                    risk_notice='仅查询各区段均有票的同一趟列车。需持覆盖全程的有效车票，接续时按票面席位调整；不保证原座续坐。余票与票价以12306实时结果为准。',
                    total_minutes=int((arrival - departure).total_seconds() // 60),
                    total_price_fen=known if all(p is not None for p in prices) else None,
                    known_price_fen=known))
                if len(plans) >= 50:
                    meta['truncated'] = True
                    meta['truncation_reasons'].append('方案数量达到上限')
                    return finish()
        return finish()

    @staticmethod
    def _identity(ticket, train_no, from_code, to_code, run_date=None):
        if (ticket.train_no != train_no
                or (ticket.from_station_telecode, ticket.to_station_telecode) != (from_code, to_code)):
            return False
        try:
            if not re.fullmatch(r'\d{8}', ticket.run_date or ''):
                return False
            datetime.strptime(ticket.run_date or '', '%Y%m%d')
        except (ValueError, TypeError):
            return False
        return run_date is None or ticket.run_date == run_date

    @staticmethod
    def _times(ticket, day):
        try:
            if not re.fullmatch(r'\d+:\d{2}', ticket.duration):
                return None
            hours, minutes = map(int, ticket.duration.split(':'))
            if hours < 0 or minutes >= 60 or hours * 60 + minutes <= 0:
                return None
            departure = datetime.combine(day, datetime.strptime(ticket.start_time, '%H:%M').time(), CST)
            arrival = departure + timedelta(hours=hours, minutes=minutes)
            running_day = datetime.strptime(ticket.run_date, '%Y%m%d').date()
            if running_day > day or arrival.strftime('%H:%M') != ticket.arrive_time:
                return None
            return departure, arrival
        except (ValueError, TypeError, OverflowError):
            return None


smart_planner = SmartRoutePlanner()
