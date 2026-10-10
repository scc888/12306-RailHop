"""
FastAPI 路由接口层
"""
import uuid
import time
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, Header, HTTPException, Body, Depends
from ..models.schemas import (
    ApiResponse,
    StationInfo,
    TrainTicketInfo,
    TrainStopInfo,
    SmartPlan,
    AuthQrCodeVO,
    AuthStatusVO,
    PassengerDTO,
    OrderSubmitParam,
    OrderSubmitResult,
    UnpaidOrderInfo,
    PlanBookingParam
)
from ..services.station_service import station_service
from ..services.client_12306 import client_12306
from ..services.smart_planner import smart_planner
from ..services.session_manager import session_manager
from ..services.auth_service import auth_service
from ..services.passenger_service import passenger_service
from ..services.order_service import order_service
from ..services.payment_service import payment_service
from ..services.booking_service import booking_service

router = APIRouter(prefix="/api", tags=["12306 查票与购票服务"])

def get_session_id(
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
    session_id: Optional[str] = Query(None)
) -> str:
    """提取或生成统一会话标识"""
    sid = x_session_id or session_id
    if not sid:
        sid = str(uuid.uuid4())
    return sid


# ==================== 1. 基础查票与推算服务 (V1) ====================

@router.get("/stations/search", response_model=ApiResponse[List[StationInfo]])
def search_stations(
    keyword: Optional[str] = Query("", description="汉字/拼音/首字母模糊搜索"),
    limit: int = Query(20, description="返回数量上限")
):
    """车站联想检索接口 (支持拼音、汉字、简拼)"""
    results = station_service.search(keyword, limit=limit)
    return ApiResponse(data=results)

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
    max_transfers: Optional[int] = Query(None, description="兼容旧参数名: 最多车内换乘次数"),
    sid: str = Depends(get_session_id)
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
    user = session_manager.get_or_create(sid)
    snapshots = {}
    for plan in plans:
        plan.plan_id = str(uuid.uuid4())
        snapshots[plan.plan_id] = {"plan": plan.model_copy(deep=True), "expires_at": time.time() + 900}
    user.extra_data["plans"] = snapshots
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


# ==================== 2. 用户认证与扫码登录 (V2) ====================

@router.get("/auth/session/init", response_model=ApiResponse[Dict[str, str]])
def init_session(sid: str = Depends(get_session_id)):
    """初始化或确认客户端 Session ID"""
    user_sess = session_manager.get_or_create(sid)
    return ApiResponse(data={"session_id": user_sess.session_id})

@router.get("/auth/qr", response_model=ApiResponse[AuthQrCodeVO])
def get_qr_code(sid: str = Depends(get_session_id)):
    """获取 12306 登录二维码 (Base64)"""
    res = auth_service.create_qr_code(sid)
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=res.get("msg", "获取二维码失败"))
    return ApiResponse(data=AuthQrCodeVO(
        uuid=res["uuid"],
        image=res["image"]
    ))

@router.get("/auth/qr/status", response_model=ApiResponse[AuthStatusVO])
def check_qr_status(sid: str = Depends(get_session_id)):
    """轮询二维码扫码状态"""
    res = auth_service.check_qr_status(sid)
    return ApiResponse(data=AuthStatusVO(
        status=res.get("status", "UNKNOWN"),
        msg=res.get("msg", ""),
        username=res.get("username")
    ))

@router.get("/auth/status", response_model=ApiResponse[Dict[str, Any]])
def get_auth_status(sid: str = Depends(get_session_id)):
    """查询当前会话登录状态"""
    return booking_action(lambda: auth_service.check_user_status(sid))

@router.post("/auth/logout", response_model=ApiResponse[Dict[str, bool]])
def logout(sid: str = Depends(get_session_id)):
    """退出 12306 登录"""
    auth_service.logout(sid)
    return ApiResponse(data={"logged_out": True})


# ==================== 3. 乘车人管理与购票交易 (V2) ====================

@router.get("/passengers", response_model=ApiResponse[List[PassengerDTO]])
def get_passengers(sid: str = Depends(get_session_id)):
    """获取当前登录账号的常用联系人/乘车人列表"""
    return booking_action(lambda: passenger_service.get_passengers(sid))

@router.post("/orders/submit", response_model=ApiResponse[OrderSubmitResult])
def submit_order(
    param: OrderSubmitParam = Body(...),
    sid: str = Depends(get_session_id)
):
    """
    提交购票排队申请并锁座
    """
    if not param.passengers:
        raise HTTPException(status_code=400, detail="乘车人列表不能为空")

    return booking_action(lambda: booking_service.book_single(sid, param))

@router.get("/orders/unpaid", response_model=ApiResponse[Optional[UnpaidOrderInfo]])
def get_unpaid_order(sid: str = Depends(get_session_id)):
    """获取当前用户的未完成（待支付）订单信息"""
    return booking_action(lambda: order_service.query_no_complete_order(sid))

@router.post("/orders/cancel", response_model=ApiResponse[Dict[str, Any]])
def cancel_unpaid_order(
    sequence_no: str = Query(..., description="待取消的订单号, 如 E123456789"),
    sid: str = Depends(get_session_id)
):
    """取消未完成订单 (注意: 每日限取消 3 次)"""
    ok, msg = order_service.cancel_no_complete_order(sid, sequence_no)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return ApiResponse(data={"success": True, "msg": msg})


@router.get("/orders/pending", response_model=ApiResponse[OrderSubmitResult])
def pending_order_result(sid: str = Depends(get_session_id)):
    return booking_action(lambda: order_service.pending_result(sid))


def booking_action(operation):
    """区分输入问题、会话权限和铁路网络异常，让前端保留原订单进度。"""
    try:
        return ApiResponse(data=operation())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/orders/{order_id}/payment")
def payment_entry(order_id: str, kind: str = Query("TICKET", pattern="^(TICKET|WAITLIST)$"), sid: str = Depends(get_session_id)):
    return booking_action(lambda: payment_service.entry(sid, order_id, kind))


@router.get("/orders/{order_id}/status")
def payment_status(order_id: str, train_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), kind: str = Query("TICKET", pattern="^(TICKET|WAITLIST)$"), sid: str = Depends(get_session_id)):
    return booking_action(lambda: payment_service.status(sid, order_id, train_date, kind))


@router.post("/bookings")
def create_booking(param: PlanBookingParam, sid: str = Depends(get_session_id)):
    return booking_action(lambda: booking_service.create(sid, param))


@router.get("/bookings/{task_id}")
def get_booking(task_id: str, sid: str = Depends(get_session_id)):
    return booking_action(lambda: booking_service.refresh(sid, task_id))


@router.post("/bookings/{task_id}/advance")
def advance_booking(task_id: str, sid: str = Depends(get_session_id)):
    return booking_action(lambda: booking_service.advance(sid, task_id))


@router.post("/bookings/{task_id}/stop")
def stop_booking(task_id: str, sid: str = Depends(get_session_id)):
    return booking_action(lambda: booking_service.stop(sid, task_id))


@router.post("/bookings/{task_id}/retry")
def retry_booking(task_id: str, sid: str = Depends(get_session_id)):
    return booking_action(lambda: booking_service.retry(sid, task_id))
