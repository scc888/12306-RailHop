"""
智能出行算法引擎: 实现【自定义席别偏好】与【多阶同车换座 (最多换座1~3次)】、【买短补长】、【买长乘短】
"""
import logging
from typing import List, Optional, Dict, Tuple
from ..models.schemas import SmartPlan, PlanSegment, TrainStopInfo
from .client_12306 import client_12306
from .station_service import station_service

logger = logging.getLogger(__name__)

class SmartRoutePlanner:

    def calculate_smart_plans(
        self,
        train_date: str,
        train_code: str,
        train_no: str,
        from_code: str,
        to_code: str,
        allowed_seats: Optional[List[str]] = None,
        max_tickets: int = 2,
        max_transfers: Optional[int] = None
    ) -> List[SmartPlan]:
        """
        计算智能出行方案:
        :param allowed_seats: 允许接受的席别代码列表, 如 ['ze', 'zy'] (默认None表示不限制)
        :param max_tickets: 到达终点站最多购买车票张数(分段数), 1~3, 默认 2
        :param max_transfers: 兼容旧参数名
        """
        plans: List[SmartPlan] = []
        eff_tickets = max_tickets if max_transfers is None else max_transfers
        eff_tickets = max(1, min(3, eff_tickets))
        from_name = station_service.get_name(from_code)
        to_name = station_service.get_name(to_code)

        # 1. 获取该车次的完整沿途停靠站列表
        stops = client_12306.query_train_stops(train_no, from_code, to_code, train_date)
        if not stops or len(stops) < 2:
            logger.warning(f"No stops found for train {train_code} {train_no}")
            return plans

        # 2. 定位出发站与到达站在车次线路中的下标
        from_idx = -1
        to_idx = -1

        for idx, stop in enumerate(stops):
            s_name = stop.station_name
            if from_idx == -1 and (s_name == from_name or s_name in from_name or from_name in s_name):
                from_idx = idx
            if to_idx == -1 and (s_name == to_name or s_name in to_name or to_name in s_name):
                to_idx = idx

        if from_idx == -1 or to_idx == -1 or from_idx >= to_idx:
            logger.warning(f"Could not align station indices: from_idx={from_idx}, to_idx={to_idx}")
            return plans

        journey_stops = stops[from_idx : to_idx + 1]
        n_stops = len(journey_stops)
        if n_stops < 2:
            return plans

        # 3. 建立局部区间查询缓存以防同一推算内重复发请求
        # key: (sub_from_idx, sub_to_idx)
        # value: (seat_name, count_str, price_str) or None
        segment_cache: Dict[Tuple[int, int], Optional[Tuple[str, str, str]]] = {}

        def check_segment(i: int, j: int) -> Optional[Tuple[str, str, str]]:
            """检查 journey_stops[i] 到 journey_stops[j] 区间是否有符合席别偏好的余票"""
            if (i, j) in segment_cache:
                return segment_cache[(i, j)]

            st_from_name = journey_stops[i].station_name
            st_to_name = journey_stops[j].station_name
            c_from = station_service.get_code(st_from_name) or from_code
            c_to = station_service.get_code(st_to_name) or to_code

            tickets = client_12306.query_tickets(train_date, c_from, c_to)
            matched = next((t for t in tickets if t.train_code == train_code), None)
            if not matched:
                segment_cache[(i, j)] = None
                return None

            best_seat, seat_count, seat_key = self._get_best_available_seat(matched.seats, allowed_seats)
            if not best_seat:
                segment_cache[(i, j)] = None
                return None

            price_str = matched.prices.get(seat_key, "")
            res = (best_seat, seat_count, price_str)
            segment_cache[(i, j)] = res
            return res

        # 4. 生成【同车接续/换座】方案 (按购票张数 2张 -> 最多3张 搜索)
        N = n_stops - 1  # 终点站下标
        swap_plans: List[SmartPlan] = []

        # (4.1) 买 2 张车票 (2 段行程: 0 -> i -> N，车内换座 1 次)
        if eff_tickets >= 2:
            for i in range(1, N):
                seg1 = check_segment(0, i)
                if not seg1:
                    continue
                seg2 = check_segment(i, N)
                if not seg2:
                    continue

                inter_name = journey_stops[i].station_name
                p = SmartPlan(
                    plan_type=2,
                    plan_type_name="同车接续 (买2张票)",
                    ticket_count=2,
                    transfer_count=1,
                    train_code=train_code,
                    train_no=train_no,
                    title=f"买 2 张票：在【{inter_name}】站内换座，全程有座不下车",
                    recommendation_score=95,
                    risk_level=0,
                    risk_notice=(
                        f"优质方案（共购 2 张票）：购买同一趟车【{from_name} -> {inter_name}】与【{inter_name} -> {to_name}】两张票。"
                        f"在【{inter_name}】站停靠时，无需下车出站，在车厢内移步至新座位即可继续前往目的地。"
                    ),
                    segments=[
                        self._build_segment(journey_stops[0], journey_stops[i], seg1, "第 1 程，持票上车"),
                        self._build_segment(journey_stops[i], journey_stops[N], seg2, "第 2 程，车内移步至新座位")
                    ]
                )
                swap_plans.append(p)

        # (4.2) 买 3 张车票 (3 段行程: 0 -> i -> j -> N，车内换座 2 次)，仅当 eff_tickets >= 3 时
        if eff_tickets >= 3:
            count_3_tickets = 0
            for i in range(1, N - 1):
                seg1 = check_segment(0, i)
                if not seg1:
                    continue
                for j in range(i + 1, N):
                    seg3 = check_segment(j, N)
                    if not seg3:
                        continue
                    seg2 = check_segment(i, j)
                    if not seg2:
                        continue

                    s1_name = journey_stops[i].station_name
                    s2_name = journey_stops[j].station_name
                    p = SmartPlan(
                        plan_type=2,
                        plan_type_name="同车接续 (买3张票)",
                        ticket_count=3,
                        transfer_count=2,
                        train_code=train_code,
                        train_no=train_no,
                        title=f"买 3 张票：经【{s1_name}】和【{s2_name}】站内换座，全程有座",
                        recommendation_score=90,
                        risk_level=0,
                        risk_notice=(
                            f"备选接续（共购 3 张票）：购买同一趟车 3 张车票（{from_name}→{s1_name}、{s1_name}→{s2_name}、{s2_name}→{to_name}）。"
                            f"全程无需下车，仅需在经停【{s1_name}】和【{s2_name}】站时更换车厢座位。"
                        ),
                        segments=[
                            self._build_segment(journey_stops[0], journey_stops[i], seg1, "第 1 程，持票上车"),
                            self._build_segment(journey_stops[i], journey_stops[j], seg2, "第 2 程，第一次换座"),
                            self._build_segment(journey_stops[j], journey_stops[N], seg3, "第 3 程，第二次换座直达")
                        ]
                    )
                    swap_plans.append(p)
                    count_3_tickets += 1
                    if count_3_tickets >= 4:
                        break
                if count_3_tickets >= 4:
                    break

        plans.extend(swap_plans)

        # 5. 生成【买短补长】方案 (只要第一段有票即构成保底上车方案)
        short_plans: List[SmartPlan] = []
        for i in range(1, N):
            seg1 = check_segment(0, i)
            if not seg1:
                continue

            inter_name = journey_stops[i].station_name
            is_closest = (i == 1)
            is_furthest = (i == N - 1)
            score = 83 if is_furthest else (80 if is_closest else 76)
            sub_title = (
                f"买到最近站【{inter_name}】先上车，车上补票至【{to_name}】(起步成本最低)"
                if is_closest else
                f"买到【{inter_name}】享受有座乘车，车上补剩余路程"
            )

            p = SmartPlan(
                plan_type=1,
                plan_type_name="买短补长 (买1张票)",
                ticket_count=1,
                transfer_count=0,
                train_code=train_code,
                train_no=train_no,
                title=f"买 1 张票：{sub_title}",
                recommendation_score=score,
                risk_level=2,
                risk_notice=(
                    f"温馨提醒：购买【{from_name} -> {inter_name}】正规车票正常进站乘车。"
                    f"上车后请第一时间前往列车长办公席申请办理越站补票手续。"
                    f"特别注意：春运/国庆等极端客流若列车严重超员报警，铁路部门有权暂停办理补票。"
                ),
                segments=[
                    self._build_segment(journey_stops[0], journey_stops[i], seg1, "官方正规车票，合法进站上车"),
                    PlanSegment(
                        from_station=inter_name,
                        to_station=to_name,
                        start_time=journey_stops[i].start_time,
                        arrive_time=journey_stops[N].arrive_time,
                        seat_name="车上补票",
                        seat_status="车上补票 (通常为无座)",
                        seat_price="视补票核收",
                        is_extension=True,
                        tip="列车运行途中主动找列车员补票"
                    )
                ]
            )
            short_plans.append(p)

        # 挑选最佳 2~3 个买短补长方案（最近站 + 最远站）
        if short_plans:
            selected_shorts = [short_plans[0]]
            if len(short_plans) > 1:
                selected_shorts.append(short_plans[-1])
            plans.extend(selected_shorts)

        # 6. 生成【买长乘短】方案 (多买 1~2 站提前下车)
        far_stops = stops[to_idx + 1 :]
        for far_stop in far_stops[:2]:
            far_name = far_stop.station_name
            far_code = station_service.get_code(far_name)
            if not far_code:
                continue

            tickets_far = client_12306.query_tickets(train_date, from_code, far_code)
            train_far = next((t for t in tickets_far if t.train_code == train_code), None)

            if train_far:
                best_seat, seat_count, seat_key = self._get_best_available_seat(train_far.seats, allowed_seats)
                if best_seat:
                    price_str = train_far.prices.get(seat_key, "")
                    long_plan = SmartPlan(
                        plan_type=3,
                        plan_type_name="买长乘短 (买1张票)",
                        ticket_count=1,
                        transfer_count=0,
                        train_code=train_code,
                        train_no=train_no,
                        title=f"买 1 张票：多买至后方【{far_name}】站，在【{to_name}】提前下车，规避限售",
                        recommendation_score=88,
                        risk_level=0,
                        risk_notice=(
                            f"合规策略：节假日铁路常对长途区间优先放票。购买【{from_name} -> {far_name}】车票，"
                            f"列车到达【{to_name}】时正常携带行李下车出站，出站闸机刷身份证完全畅通。"
                        ),
                        segments=[
                            PlanSegment(
                                from_station=from_name,
                                to_station=to_name,
                                start_time=stops[from_idx].start_time,
                                arrive_time=stops[to_idx].arrive_time,
                                seat_name=best_seat,
                                seat_status=f"有票 ({seat_count})",
                                seat_price=price_str,
                                is_extension=False,
                                tip=f"实际乘车区间，在{to_name}正常出站"
                            ),
                            PlanSegment(
                                from_station=to_name,
                                to_station=far_name,
                                start_time=stops[to_idx].start_time,
                                arrive_time=far_stop.arrive_time,
                                seat_name=best_seat,
                                seat_status="放弃后续区间",
                                seat_price="",
                                is_extension=False,
                                tip="多买站段，票价稍有增加"
                            )
                        ]
                    )
                    plans.append(long_plan)

        # 7. 排序：换座 1 次 (95) > 换座 2 次 (90) > 买长乘短 (88) > 换座 3 次 (85) > 买短补长 (80)
        plans.sort(key=lambda p: p.recommendation_score, reverse=True)
        return plans

    def _build_segment(
        self,
        st_from: TrainStopInfo,
        st_to: TrainStopInfo,
        seg_tuple: Tuple[str, str, str],
        tip: str
    ) -> PlanSegment:
        best_seat, seat_count, price_str = seg_tuple
        return PlanSegment(
            from_station=st_from.station_name,
            to_station=st_to.station_name,
            start_time=st_from.start_time,
            arrive_time=st_to.arrive_time,
            seat_name=best_seat,
            seat_status=f"有票 ({seat_count})",
            seat_price=price_str,
            is_extension=False,
            tip=tip
        )

    def _get_best_available_seat(
        self,
        seats,
        allowed_seats: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        从各席别中挑选符合用户偏好的最佳有票席位
        返回: (seat_name, count_str, seat_code_key) 或 (None, None, None)
        """
        priority = [
            ("ze", "二等座", seats.ze),
            ("zy", "一等座", seats.zy),
            ("yw", "硬卧", seats.yw),
            ("rw", "软卧", seats.rw),
            ("srrb", "动卧", seats.srrb),
            ("swz", "商务座", seats.swz),
            ("yz", "硬座", seats.yz),
            ("wz", "无座", seats.wz),
        ]
        allowed_set = set(allowed_seats) if allowed_seats else None

        for code, name, val in priority:
            if allowed_set and code not in allowed_set:
                continue
            if val not in ("--", "无", ""):
                return (name, val, code)
        return (None, None, None)

smart_planner = SmartRoutePlanner()
