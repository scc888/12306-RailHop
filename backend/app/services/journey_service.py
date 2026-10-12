"""Bounded orchestration of direct, fully ticketed same-train and same-station routes."""
import time
import logging
from datetime import datetime, timedelta
from ..models.journey_schemas import JourneyResult, JourneyGroup, JourneyGroupMeta, JourneyPlan, ShortTicketGroup
from ..models.transfer_schemas import TransferQueryRequest, TransferLeg
from .client_12306 import RailwayQueryError
from .transfer_ticket_gateway import CST, ticket_to_leg
from .transfer_planner import TransferPlanner
from .route_policy import RoutePolicy

logger = logging.getLogger(__name__)


def matches_type(code, selected):
    high = code[:1].upper() in ('G','D','C')
    return selected == 'all' or (high if selected == 'high_speed' else not high)


class JourneyService:
    def __init__(self, client, stations, same_train, transfer):
        self.client, self.stations, self.same_train, self.transfer = client, stations, same_train, transfer

    def search(self, request, now=None):
        now = now or datetime.now(CST)
        deadline = time.monotonic() + 60
        started = time.monotonic()
        logger.info('Journey query started: mode=%s, date=%s, type=%s, transfers=%s, expanded=%s, short_fallback=%s',
            request.mode,request.train_date,request.train_type,request.transfer_count,request.allow_large_detour,request.include_short_fallback)
        if not now.date() <= request.train_date <= now.date() + timedelta(days=14):
            raise ValueError('出发日期须在 15 天预售范围内（含今天）')
        self.stations.ensure_loaded()
        by_code = {s.telecode:s for s in self.stations.stations}
        if request.from_station not in by_code or request.to_station not in by_code:
            raise ValueError('无法识别出发地或目的地，请从站点提示中选择')
        origins = {s.telecode for s in self.stations.city_stations(request.from_station)} if request.from_scope == 'city' else {request.from_station}
        destinations = {s.telecode for s in self.stations.city_stations(request.to_station)} if request.to_scope == 'city' else {request.to_station}
        if origins & destinations:
            raise ValueError('出发地与目的地范围重叠，请选择不同城市或具体车站')
        # Validate supplied interchange constraints even when auto mode would skip transfer.
        self.transfer.stations.validate_via(request.ordered_via_stations) if hasattr(self.transfer,'stations') else None
        if any(c in origins | destinations for c in request.ordered_via_stations):
            raise ValueError('指定中转站不能属于所选起点或终点范围')
        scope = dict(from_label=self._label(by_code[request.from_station],request.from_scope),
            to_label=self._label(by_code[request.to_station],request.to_scope),
            origin_station_codes=sorted(origins),destination_station_codes=sorted(destinations))
        groups = {key:JourneyGroup(meta=JourneyGroupMeta(status='skipped')) for key in ('direct','same_train','transfer')}
        city_partial = len(origins) > 1 or len(destinations) > 1
        coverage = ['城市范围依据12306字典，接纳代表站查询返回的同城车站；未逐一遍历全部站对。'] if city_partial else []
        candidates, direct_failed, unverified_anchor = [], False, False
        if request.mode != 'transfer' or request.include_short_fallback:
            group = groups['direct']
            group.meta = JourneyGroupMeta(status='partial' if city_partial else 'complete',notices=list(coverage),query_count=1)
            try:
                tickets = self.client.query_tickets_strict(request.train_date.isoformat(),request.from_station,
                    request.to_station,timeout_seconds=min(8,max(.001,deadline-time.monotonic())))
                seen = set()
                for ticket in tickets:
                    if (ticket.from_station_telecode not in origins or ticket.to_station_telecode not in destinations
                            or not matches_type(ticket.train_code,request.train_type)):
                        continue
                    identity=(ticket.train_no,ticket.run_date,ticket.from_station_telecode,ticket.to_station_telecode,ticket.start_time)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    # An unsold complete interval is still the identity/timing anchor for splitting.
                    times = self.same_train._times(ticket,request.train_date)
                    if times and times[0] >= now:
                        candidates.append(ticket)
                    elif not times:
                        unverified_anchor=True
                    try:
                        leg=ticket_to_leg(ticket,request.train_date,request.allowed_seats,queried_at=now)
                    except ValueError:
                        group.meta.status='partial'
                        group.meta.notices.append('部分列车日期或时刻数据异常，已排除。')
                        continue
                    if leg and leg.departure_at >= now:
                        group.plans.append(self._plan([leg],[],'direct'))
            except RailwayQueryError:
                direct_failed=True
                group.meta.status='upstream_error'
                group.meta.notices.append('直达铁路接口查询失败，不能据此判断无票。')
            group.plans=self._top(group.plans,request.sort_by,group.meta)
        need_alternatives = request.mode in ('all','same_train','transfer') or (request.mode=='auto' and not groups['direct'].plans)
        if request.mode in ('auto','all','same_train') and need_alternatives:
            group=groups['same_train']
            group.meta=JourneyGroupMeta(status='complete',notices=list(coverage))
            if unverified_anchor:
                group.meta.status='partial'
                group.meta.notices.append('部分列车缺少可核对的运行日期或完整时刻，接续尚未验证。')
            if direct_failed:
                group.meta.status='upstream_error'
                group.meta.notices.append('未取得可核对的完整列车信息，同车接续暂未查询成功。')
            else:
                candidates.sort(key=lambda t:(self.same_train._times(t,request.train_date)[1]-self.same_train._times(t,request.train_date)[0],t.start_time))
                same_deadline=min(deadline,time.monotonic()+16)
                if len(candidates)>4:
                    group.meta.status='partial'
                    group.meta.notices.append('本次最多核对 4 个同车接续候选车次，其他车次尚未查询。')
                for anchor in candidates[:4]:
                    seconds=same_deadline-time.monotonic()
                    queries=40-group.meta.query_count
                    if seconds<=0 or queries<=0:
                        group.meta.status='partial'
                        group.meta.notices.append('同车接续查询达到时间或次数上限，结果可能不完整。')
                        break
                    found=self.same_train.calculate_with_meta(request.train_date.isoformat(),anchor.train_code,anchor.train_no,
                        anchor.from_station_telecode,anchor.to_station_telecode,allowed_seats=request.allowed_seats,
                        max_tickets=request.max_same_train_segments,budget_seconds=seconds,max_queries=queries,anchor_ticket=anchor)
                    group.meta.query_count+=found['meta'].get('query_count',0)
                    if found['meta'].get('status')!='complete':
                        group.meta.status='partial'
                    group.meta.notices.extend(found['meta'].get('notices',[]))
                    for plan in found['plans']:
                        legs=[TransferLeg(train_no=plan.train_no,train_code=s.train_code,
                            from_station=s.from_station_telecode,to_station=s.to_station_telecode,
                            from_station_name=s.from_station,to_station_name=s.to_station,
                            departure_at=s.departure_at,arrival_at=s.arrival_at,seats=s.seats,queried_at=now,
                            run_date=datetime.strptime(anchor.run_date,'%Y%m%d').date()) for s in plan.segments]
                        if all(matches_type(l.train_code,request.train_type) for l in legs):
                            group.plans.append(self._plan(legs,[],'same_train'))
                if city_partial and group.meta.status=='complete':
                    group.meta.status='partial'
                group.plans=self._top(group.plans,request.sort_by,group.meta)
        if request.mode in ('auto','all','transfer') and need_alternatives:
            group=groups['transfer']
            remaining=deadline-time.monotonic()-(8 if request.include_short_fallback else 0)
            if remaining<=0:
                group.meta=JourneyGroupMeta(status='partial',notices=['查询已达到总时间上限，中转尚未完成。'])
            else:
                found=self.transfer.search(TransferQueryRequest(**request.model_dump()),now=now,
                    origin_codes=origins,destination_codes=destinations,budget_seconds=remaining,
                    route_policy=RoutePolicy(request.from_station,request.to_station,self.stations,
                        allow_large_detour=request.allow_large_detour,required=request.ordered_via_stations))
                details=found.meta.model_dump()
                details['notices']=list(found.meta.coverage_notes)
                reasons={'query_limit':'日期区间查询次数达到上限','time_limit':'查询时间达到上限',
                    'state_limit':'路线组合达到上限','result_limit':'仅展示本次搜索前50条路线',
                    'candidate_limit':'中转候选站范围受限','horizon_limit':'行程范围限定为72小时',
                    'city_representative_query':'城市查询未逐一遍历全部站对'}
                details['notices'].extend(reasons.get(r,r) for r in found.meta.truncation_reasons)
                if found.meta.failed_pairs:
                    details['notices'].append(f'{len(found.meta.failed_pairs)} 个区间查询失败或数据异常，不能视为确定无票。')
                details['notices'].append('当前中转候选来自12站便捷换乘资料，未搜索全国全部车站；参考时间为采集快照。')
                group.meta=JourneyGroupMeta(**details)
                group.plans=[JourneyPlan(**p.model_dump(),kind='transfer') for p in found.plans]
        short_group=ShortTicketGroup()
        if request.include_short_fallback and not any(g.plans for g in groups.values()):
            short_group.meta=JourneyGroupMeta(status='partial' if city_partial else 'complete',notices=list(coverage))
            if unverified_anchor:
                short_group.meta.status='partial'
                short_group.meta.notices.append('部分列车运行日期或时刻无法核对，相关补票备选尚未验证。')
            if direct_failed:
                short_group.meta.status='upstream_error'
                short_group.meta.notices.append('列车信息查询失败，不能核验短途票是否与目的站为同一运行列车。')
            else:
                stop_at=min(deadline,time.monotonic()+8)
                if len(candidates)>4:
                    short_group.meta.status='partial'
                    short_group.meta.notices.append('补票备选最多核对4个车次，未搜索全部列车。')
                for anchor in candidates[:4]:
                    seconds=stop_at-time.monotonic()
                    queries=25-short_group.meta.query_count
                    if seconds<=0 or queries<=0:
                        short_group.meta.status='partial'
                        short_group.meta.notices.append('补票备选查询达到预算，尚未查完。')
                        break
                    found=self.same_train.calculate_with_meta(request.train_date.isoformat(),anchor.train_code,anchor.train_no,
                        anchor.from_station_telecode,anchor.to_station_telecode,allowed_seats=request.allowed_seats,
                        budget_seconds=seconds,max_queries=queries,anchor_ticket=anchor,
                        include_short_fallback=True,short_fallback_only=True)
                    short_group.meta.query_count+=found['meta'].get('query_count',0)
                    if found['meta'].get('status')!='complete':
                        short_group.meta.status='partial'
                    short_group.meta.notices.extend(found['meta'].get('notices',[]))
                    short_group.options.extend(found.get('short_fallbacks',[]))
                unique=list({o.id:o for o in short_group.options}.values())
                if len(unique)>50:
                    short_group.meta.status='partial'
                    short_group.meta.notices.append('补票备选仅展示前50项，不参与全程路线排序。')
                short_group.options=unique[:50]
            short_group.meta.notices.append('只确认前段有票；后续是否允许补票及继续乘坐尚未确认，不参与全程有票排序。')
        if request.mode in ('same_train','transfer'):
            groups['direct']=JourneyGroup(meta=JourneyGroupMeta(status='skipped',
                notices=['本次完整列车信息只用于核验接续身份和日期，不展示直达路线。']))
        for group in groups.values():
            group.meta.notices=list(dict.fromkeys(group.meta.notices))
        logger.info('Journey query finished: elapsed=%.2fs, groups=%s, short_options=%s',
            time.monotonic()-started,{k:(g.meta.status,len(g.plans)) for k,g in groups.items()},len(short_group.options))
        return JourneyResult(**groups,short_fallback=short_group,queried_at=now,scope=scope)

    @staticmethod
    def _label(station,scope):
        return f'{station.city_name or station.name}（同城车站）' if scope=='city' else f'{station.name}站'

    @staticmethod
    def _plan(legs,connections,kind):
        return JourneyPlan(**TransferPlanner._plan(legs,connections).model_dump(),kind=kind)

    @staticmethod
    def _top(plans,sort_by,meta):
        unique={p.id:p for p in plans}
        if len(unique)>50:
            meta.status='partial'
            meta.notices.append('仅展示本次已查路线中排序前50条。')
        return sorted(unique.values(),key=lambda p:TransferPlanner._sort_key(p,sort_by))[:50]
