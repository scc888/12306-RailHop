"""
FastAPI 路由接口层
"""
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from ..models.schemas import (
    ApiResponse,
    StationInfo,
    TrainTicketInfo,
    TrainStopInfo,
    SmartPlan
)
from ..services.station_service import station_service
from ..services.client_12306 import client_12306
from ..services.smart_planner import smart_planner

router = APIRouter(prefix="/api", tags=["12306 查票服务"])

@router.get("/stations/search", response_model=ApiResponse[List[StationInfo]])
def search_stations(
    keyword: Optional[str] = Query("", description="汉字/拼音/首字母模糊搜索"),
    limit: int = Query(20, description="返回数量上限")
):
    """车站联想检索接口 (支持拼音、汉字、简拼)"""
    results = station_service.search(keyword, limit=limit)
    return ApiResponse(data=results)

@router.get('/stations/scope', response_model=ApiResponse[dict])
def station_scope(station_code: str = Query(..., pattern=r'^[A-Z]{3}$')):
    try:
        return ApiResponse(data=station_service.station_scope(station_code))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.get("/tickets/query", response_model=ApiResponse[List[TrainTicketInfo]])
def query_tickets(
    train_date: str = Query(..., description="乘车日期, 如 2026-10-10"),
    from_station: str = Query(..., description="出发地 (中文名或电报码, 如 '上海' 或 'SHH')"),
    to_station: str = Query(..., description="目的地 (中文名或电报码, 如 '北京' 或 'BJP')"),
    purpose_codes: str = Query("ADULT", description="票种 (ADULT/0X00)")
):
    """
    两地直达车次及余票实时查询接口
    自动将中文站名转换为 12306 电报码
    """
    from_code = station_service.get_code(from_station) or from_station
    to_code = station_service.get_code(to_station) or to_station

    if not from_code or not to_code:
        raise HTTPException(status_code=400, detail="未识别的车站名称，请输入有效车站")

    tickets = client_12306.query_tickets(
        train_date=train_date,
        from_code=from_code,
        to_code=to_code,
        purpose_codes=purpose_codes
    )
    return ApiResponse(data=tickets)

@router.get("/tickets/stops", response_model=ApiResponse[List[TrainStopInfo]])
def query_stops(
    train_no: str = Query(..., description="车次内部唯一标识, 如 5500000G2800"),
    from_station: str = Query(..., description="出发站 (中文或电报码)"),
    to_station: str = Query(..., description="到达站 (中文或电报码)"),
    depart_date: str = Query(..., description="发车日期, 如 2026-10-10")
):
    """车次沿途完整停靠站时刻表查询"""
    from_code = station_service.get_code(from_station) or from_station
    to_code = station_service.get_code(to_station) or to_station

    stops = client_12306.query_train_stops(
        train_no=train_no,
        from_code=from_code,
        to_code=to_code,
        depart_date=depart_date
    )
    return ApiResponse(data=stops)

@router.get("/smart-plans/calculate", response_model=ApiResponse[List[SmartPlan]])
def calculate_smart_plans(
    train_date: str = Query(..., description="乘车日期, 如 2026-10-10"),
    train_code: str = Query(..., description="旅客车次, 如 G28"),
    train_no: str = Query(..., description="车次内部编码, 如 5500000G2800"),
    from_station: str = Query(..., description="出发站中文或电报码"),
    to_station: str = Query(..., description="到达站中文或电报码"),
    allowed_seats: Optional[str] = Query(None, description="允许席别代码(逗号分割, 如 'ze,zy')"),
    max_tickets: int = Query(2, ge=1, le=3, description="到达终点站最多购票张数(分段数): 1~3张, 默认2张"),
    max_transfers: Optional[int] = Query(None, description="兼容旧参数名: 最多车内换乘次数")
):
    """
    针对指定售罄车次的【智能出行方案推算】接口
    支持：用户偏好席别过滤、最多购票张数限制 (1~3张, 默认2张)
    """
    from_code = station_service.get_code(from_station) or from_station
    to_code = station_service.get_code(to_station) or to_station

    if not from_code or not to_code:
        raise HTTPException(status_code=400, detail="未识别的车站名称")

    seat_list = [s.strip() for s in allowed_seats.split(",") if s.strip()] if allowed_seats else None
    eff_tickets = max_tickets if max_transfers is None else max_transfers
    eff_tickets = max(1, min(3, eff_tickets))

    plans = smart_planner.calculate_smart_plans(
        train_date=train_date,
        train_code=train_code,
        train_no=train_no,
        from_code=from_code,
        to_code=to_code,
        allowed_seats=seat_list,
        max_tickets=eff_tickets
    )
    return ApiResponse(data=plans)

@router.get("/tickets/price")
def query_ticket_price(
    train_no: str = Query(..., description="车次内部唯一标识, 如 5500000G2800"),
    from_station_no: str = Query(..., description="出发站序号, 如 01"),
    to_station_no: str = Query(..., description="到达站序号, 如 06"),
    seat_types: str = Query(..., description="席别编码串, 如 9MODO"),
    train_date: str = Query(..., description="乘车日期, 如 2026-10-10")
):
    """调用 12306 官方票价查询接口获取精准票价明细"""
    prices = client_12306.query_ticket_price(
        train_no=train_no,
        from_station_no=from_station_no,
        to_station_no=to_station_no,
        seat_types=seat_types,
        train_date=train_date
    )
    return ApiResponse(data=prices)

