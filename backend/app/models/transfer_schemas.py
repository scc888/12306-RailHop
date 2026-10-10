"""Read-only transfer query contracts. Money is represented in integer fen."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator

SEAT_NAMES = {'ze': '二等座', 'zy': '一等座', 'swz': '商务座', 'gr': '高级软卧',
              'rw': '软卧', 'srrb': '动卧', 'yw': '硬卧', 'rz': '软座', 'yz': '硬座', 'wz': '无座'}


class TransferQueryRequest(BaseModel):
    from_station: str = Field(pattern=r'^[A-Z]{3}$')
    to_station: str = Field(pattern=r'^[A-Z]{3}$')
    train_date: date
    transfer_count: int = Field(1, ge=1, le=3)
    # None selects each station's official reference; an explicit value is a personal floor.
    min_transfer_minutes: int | None = Field(None, ge=15, le=1440)
    ordered_via_stations: list[str] = Field(default_factory=list)
    allowed_seats: list[str] = Field(default_factory=lambda: ['ze', 'zy', 'yz', 'yw', 'rw'])
    train_type: Literal['all', 'high_speed', 'regular'] = 'all'
    sort_by: Literal['duration', 'arrival', 'price'] = 'duration'

    @model_validator(mode='after')
    def validate_route(self):
        via = self.ordered_via_stations
        if self.from_station == self.to_station:
            raise ValueError('出发站和到达站不能相同')
        if len(via) > self.transfer_count or len(via) != len(set(via)):
            raise ValueError('指定中转站数量超过中转次数，或存在重复站')
        if any(code in (self.from_station, self.to_station) or len(code) != 3 or not code.isascii() or not code.isupper() or not code.isalpha() for code in via):
            raise ValueError('指定中转站必须是不同于起终点的有效电报码')
        if not self.allowed_seats or any(code not in SEAT_NAMES for code in self.allowed_seats):
            raise ValueError('请选择有效席别')
        self.allowed_seats = list(dict.fromkeys(self.allowed_seats))
        return self


class TransferStation(BaseModel):
    station_name: str
    station_code: str = Field(pattern=r'^[A-Z]{3}$')
    pinyin: str
    pinyin_abbr: str
    convenient_transfer_confirmed: bool = True
    reference_min_minutes: int | None = Field(None, ge=1)
    reference_time_source_url: str | None = None
    reference_time_checked_at: date | None = None
    reference_time_valid_from: date | None = None
    reference_time_valid_to: date | None = None
    source_url: str
    source_published_at: date
    verified_at: date
    applicable_conditions: str = ''
    conditions_supported: bool = True
    allowed_train_prefixes: list[str] = Field(default_factory=list)
    same_day_only: bool = False
    priority: int = 100

    def reference_minutes_on(self, day: date) -> int | None:
        if self.reference_time_valid_from and day < self.reference_time_valid_from:
            return None
        if self.reference_time_valid_to and day > self.reference_time_valid_to:
            return None
        return self.reference_min_minutes


class TransferSeat(BaseModel):
    code: str
    name: str
    availability: str
    price_fen: int | None = None


class TransferLeg(BaseModel):
    train_no: str
    train_code: str
    from_station: str
    to_station: str
    from_station_name: str
    to_station_name: str
    departure_at: datetime
    arrival_at: datetime
    seats: list[TransferSeat]
    queried_at: datetime
    # Internal train identity supplied by 12306; prevents splitting one running train.
    run_date: date | None = None


class TransferConnection(BaseModel):
    station: TransferStation
    wait_minutes: int
    required_minutes: int
    official_min_minutes: int | None = None
    source_url: str


class TransferPlan(BaseModel):
    id: str
    legs: list[TransferLeg]
    connections: list[TransferConnection]
    total_minutes: int
    selected_seat_codes: list[str]
    total_price_fen: int | None
    known_price_fen: int


class TransferSearchMeta(BaseModel):
    queried_at: datetime
    candidate_station_codes: list[str]
    query_count: int = 0
    failed_pairs: list[dict] = Field(default_factory=list)
    truncated: bool = False
    truncation_reasons: list[str] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict)
    station_data_checked_at: date | None = None
    status: Literal['complete', 'partial', 'upstream_error'] = 'complete'


class TransferSearchResult(BaseModel):
    plans: list[TransferPlan]
    meta: TransferSearchMeta
