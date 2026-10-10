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
    run_date: Optional[str] = Field(None, exclude=True, description="内部校验列车运行日，不改变原查询响应")
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
    seats: TrainSeatInfo = Field(..., description="席别余票情况")
    prices: Dict[str, str] = Field(default_factory=dict, description="各席别真实票价, 如 {'ze': '¥576', 'zy': '¥967'}")


class TrainStopInfo(BaseModel):
    station_no: str = Field(..., description="站序, 如 '01'")
    station_name: str = Field(..., description="站名, 如 '上海'")
    arrive_time: str = Field(..., description="到达时间")
    start_time: str = Field(..., description="发车时间")
    stopover_time: str = Field(..., description="停留时长")


class PlanSegment(BaseModel):
    from_station: str = Field(..., description="本段出发站")
    to_station: str = Field(..., description="本段到达站")
    from_station_telecode: str = Field("", description="出发站电报码")
    to_station_telecode: str = Field("", description="到达站电报码")
    start_time: Optional[str] = Field(None, description="发车时间")
    arrive_time: Optional[str] = Field(None, description="到达时间")
    seat_name: str = Field(..., description="席别名称, 如 '二等座' 或 '车上补票(无座)'")
    seat_status: str = Field(..., description="余票状态, 如 '有票' 或 '待上车办理'")
    seat_price: str = Field("", description="本段票价, 如 '¥153'")
    is_extension: bool = Field(False, description="是否为上车补票区间")
    tip: str = Field("", description="乘车贴士")


class SmartPlan(BaseModel):
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

