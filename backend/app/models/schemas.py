"""
数据模型与响应架构定义
"""
from typing import List, Optional, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(200, description="状态码, 200为成功")
    msg: str = Field("success", description="提示信息")
    data: Optional[T] = Field(None, description="业务数据载荷")


class StationInfo(BaseModel):
    name: str = Field(..., description="车站中文名, 如 '上海'")
    telecode: str = Field(..., description="电报码, 如 'SHH'")
    pinyin: str = Field(..., description="全拼, 如 'shanghai'")
    pinyin_abbr: str = Field(..., description="拼音缩写, 如 'sh'")


class TrainSeatInfo(BaseModel):
    swz: str = Field("--", description="商务座/特等座")
    zy: str = Field("--", description="一等座")
    ze: str = Field("--", description="二等座/二等包座")
    gr: str = Field("--", description="高级软卧")
    rw: str = Field("--", description="软卧/一等卧")
    srrb: str = Field("--", description="动卧")
    yw: str = Field("--", description="硬卧/二等卧")
    rz: str = Field("--", description="软座")
    yz: str = Field("--", description="硬座")
    wz: str = Field("--", description="无座")
    has_any_ticket: bool = Field(False, description="是否有任意席别有票")


class TrainTicketInfo(BaseModel):
    train_date: str = Field("", description="查询区间的上车日期")
    train_no: str = Field(..., description="车次内部唯一标识, 如 5500000G2800")
    train_code: str = Field(..., description="旅客车次, 如 G28")
    start_station_name: str = Field(..., description="始发站")
    end_station_name: str = Field(..., description="终到站")
    from_station_name: str = Field(..., description="查询发站")
    to_station_name: str = Field(..., description="查询到站")
    from_station_telecode: str = Field(..., description="发站电报码")
    to_station_telecode: str = Field(..., description="到站电报码")
    start_time: str = Field(..., description="出发时间")
    arrive_time: str = Field(..., description="到达时间")
    duration: str = Field(..., description="历时")
    can_buy: bool = Field(True, description="是否处于可预订状态")
    secret_str: str = Field("", description="12306原始预订凭据，保留官方编码")
    waitlist_available: bool = Field(False, description="官方是否允许该车次候补")
    waitlist_seat_limits: str = Field("", description="官方限制候补的席别代码")
    seats: TrainSeatInfo = Field(..., description="席别余票情况")
    prices: Dict[str, str] = Field(default_factory=dict, description="各席别真实票价, 如 {'ze': '¥576', 'zy': '¥967'}")


class TrainStopInfo(BaseModel):
    station_no: str = Field(..., description="站序, 如 '01'")
    station_name: str = Field(..., description="站名, 如 '上海'")
    arrive_time: str = Field(..., description="到达时间")
    start_time: str = Field(..., description="发车时间")
    stopover_time: str = Field(..., description="停留时长")
    arrive_day_diff: Optional[int] = Field(None, description="到达时距离始发日的天数")


class PlanSegment(BaseModel):
    train_date: str = Field("", description="本段上车日期")
    seat_code: str = Field("", description="本段推荐席别的查询代码")
    from_station: str = Field(..., description="本段出发站")
    to_station: str = Field(..., description="本段到达站")
    from_station_telecode: str = Field("", description="出发站电报码")
    to_station_telecode: str = Field("", description="到达站电报码")
    start_time: Optional[str] = Field(None, description="发车时间")
    arrive_time: Optional[str] = Field(None, description="到达时间")
    seat_name: str = Field(..., description="席别名称, 如 '二等座' 或 '车上补票(无座)'")
    seat_status: str = Field(..., description="余票状态, 如 '有票' 或 '待上车办理'")
    seat_price: str = Field("", description="本段票价, 如 '¥153'")
    is_extension: bool = Field(False, description="是否为后续官方候补区间")
    tip: str = Field("", description="乘车贴士")


class SmartPlan(BaseModel):
    plan_id: str = Field("", description="当前会话中的方案标识，用于安全购票")
    plan_type: int = Field(..., description="方案类型: 1-买短补长, 2-同车换座, 3-买长乘短")
    plan_type_name: str = Field(..., description="类型名称")
    train_code: str = Field(..., description="车次号, 如 G28")
    train_no: str = Field(..., description="车次内部编码")
    title: str = Field(..., description="方案摘要说明")
    ticket_count: int = Field(1, description="到达终点站需购买车票张数(分段数): 1-买1张票, 2-买2张票, 3-最多买3张票")
    transfer_count: int = Field(0, description="车内换座次数: 0-无需换座, 1-换座1次, 2-换座2次")
    segments: List[PlanSegment] = Field(default_factory=list, description="乘车分段列表")
    recommendation_score: int = Field(80, description="推荐指数 (0-100)")
    risk_level: int = Field(0, description="风险等级: 0-无风险, 1-低风险, 2-中风险")
    risk_notice: str = Field("", description="操作指导与风险说明")


# --- 第二版：用户认证与乘车人模型 ---

class AuthQrCodeVO(BaseModel):
    uuid: str = Field(..., description="二维码唯一标识")
    image: str = Field(..., description="二维码 Base64 图片 Data URI")


class AuthStatusVO(BaseModel):
    status: str = Field(..., description="状态: WAITING(等待扫码), SCANNED(已扫码), SUCCESS(登录成功), EXPIRED(过期), ERROR")
    msg: str = Field("", description="提示消息")
    username: Optional[str] = Field(None, description="登录成功时的用户姓名")


class PassengerDTO(BaseModel):
    passenger_name: str = Field(..., description="乘车人姓名")
    passenger_id_type_code: str = Field("1", description="证件类型代码, 1为二代身份证")
    passenger_id_type_name: str = Field("中国居民身份证", description="证件类型名称")
    passenger_id_no: str = Field(..., description="脱敏身份证号")
    passenger_id_no_raw: str = Field(..., description="完整身份证号(下单专用)")
    passenger_type: str = Field("1", description="旅客类型代码, 1-成人, 2-儿童, 3-学生, 4-残军")
    passenger_type_name: str = Field("成人", description="旅客类型名称")
    mobile_no: str = Field("", description="手机号码")
    allEncStr: str = Field("", description="12306 加密校验串")


# --- 第二版：购票与订单模型 ---

class PassengerOrderParam(BaseModel):
    passenger_name: str = Field(..., description="乘车人姓名")
    passenger_id_type_code: str = Field("1", description="证件类型代码, 默认1(身份证)")
    passenger_id_no: str = Field(..., description="证件号")
    passenger_type: str = Field("1", description="旅客类型: 1-成人, 2-儿童, 3-学生")
    mobile_no: str = Field("", description="手机号")
    seat_type: str = Field("O", description="席别代码: 9-商务座, M-一等座, O-二等座, 3-硬卧, 4-软卧, 1-硬座")
    allEncStr: str = Field("", description="乘车人校验加密串")


class OrderSubmitParam(BaseModel):
    secret_str: str = Field(..., description="12306 加密串(从余票查询中获取)")
    train_date: str = Field(..., description="乘车日期, 如 2026-10-12")
    back_train_date: Optional[str] = Field(None, description="返程日期(单程同乘车日期)")
    train_code: str = Field(..., description="车次号, 如 G28")
    train_no: str = Field(..., description="车次编码, 如 5500000G2800")
    from_station_name: str = Field(..., description="出发站中文名")
    to_station_name: str = Field(..., description="到达站中文名")
    from_station_telecode: str = Field(..., description="出发站电报码")
    to_station_telecode: str = Field(..., description="到达站电报码")
    purpose_codes: str = Field("ADULT", description="票种代码, 默认 ADULT")
    passengers: List[PassengerOrderParam] = Field(..., min_length=1, max_length=5, description="乘车人列表")
    choose_seats: str = Field("", pattern=r"^(|1[ABCDF])$", description="高铁选座偏好(如 1A, 1B, 1C, 1D, 1F)")


class PlanBookingParam(BaseModel):
    plan_id: str = Field(..., min_length=1)
    passengers: List[PassengerOrderParam] = Field(..., min_length=1, max_length=5)
    choose_seats: str = Field("", pattern=r"^(|1[ABCDF])$")


class OrderSubmitResult(BaseModel):
    success: bool = Field(..., description="是否提交/锁座成功")
    order_id: Optional[str] = Field(None, description="12306 订单号")
    status: str = Field("SUCCESS", description="状态: SUCCESS, QUEUEING, FAIL")
    msg: str = Field("", description="详细提示信息")
    wait_time: int = Field(0, description="等待排队估算秒数")


class UnpaidTicketDetail(BaseModel):
    passenger_name: str = Field(..., description="乘车人姓名")
    coach_no: str = Field(..., description="车厢号, 如 05车")
    seat_no: str = Field(..., description="席位号, 如 08A号")
    seat_name: str = Field(..., description="席别名称, 如 二等座")
    ticket_type_name: str = Field(..., description="票种名称, 如 成人票")
    price: str = Field(..., description="票价")


class UnpaidOrderInfo(BaseModel):
    sequence_no: str = Field(..., description="12306 订单号, 如 E123456789")
    train_code: str = Field(..., description="车次号, 如 G28")
    train_date: str = Field(..., description="乘车日期")
    start_time: str = Field(..., description="发车时刻")
    arrive_time: str = Field(..., description="到达时刻")
    from_station_name: str = Field(..., description="出发站")
    to_station_name: str = Field(..., description="到达站")
    tickets: List[UnpaidTicketDetail] = Field(default_factory=list, description="车票明细")
    total_price: str = Field(..., description="应付总金额")
    pay_limit_time: str = Field("", description="支付截止时间")
    countdown_seconds: Optional[int] = Field(None, description="官方支付剩余秒数，未提供时为空")
