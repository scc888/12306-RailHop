"""One read-only request and consistent plans for all journey types."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from .transfer_schemas import TransferQueryRequest, TransferPlan, TransferLeg


class JourneyQueryRequest(TransferQueryRequest):
    from_scope: Literal['station', 'city'] = 'city'
    to_scope: Literal['station', 'city'] = 'city'
    mode: Literal['auto','all','direct','same_train','transfer'] = 'auto'
    max_same_train_segments: int = Field(2, ge=2, le=3)
    include_short_fallback: bool = False


class JourneyPlan(TransferPlan):
    kind: Literal['direct','same_train','transfer']


class JourneyGroupMeta(BaseModel):
    model_config = ConfigDict(extra='allow')
    status: Literal['complete','partial','upstream_error','skipped'] = 'complete'
    notices: list[str] = Field(default_factory=list)
    query_count: int = 0


class JourneyGroup(BaseModel):
    plans: list[JourneyPlan] = Field(default_factory=list)
    meta: JourneyGroupMeta = Field(default_factory=JourneyGroupMeta)


class ShortTicketOption(BaseModel):
    id: str
    ticketed_leg: TransferLeg
    selected_seat_code: str
    destination_station: str
    destination_station_name: str
    scheduled_arrival_at: datetime
    known_price_fen: int
    extension_price_fen: None = None
    total_price_fen: None = None
    conditions: str = ('必须在原票到站前向列车工作人员申请补票；有运输能力时才可办理，'
        '是否允许继续乘坐由铁路现场决定。被拒绝时须在原票到站下车。'
        '前段席位仅适用于票面区间，不承诺后续有座、同席别或继续使用原席位。')
    source_url: str = 'https://mobile.12306.cn/otsmobile/h5/otsbussiness/info/transportationRules.html'


class ShortTicketGroup(BaseModel):
    options: list[ShortTicketOption] = Field(default_factory=list)
    meta: JourneyGroupMeta = Field(default_factory=lambda: JourneyGroupMeta(status='skipped'))


class JourneyResult(BaseModel):
    direct: JourneyGroup
    same_train: JourneyGroup
    transfer: JourneyGroup
    short_fallback: ShortTicketGroup = Field(default_factory=ShortTicketGroup)
    queried_at: datetime
    scope: dict
