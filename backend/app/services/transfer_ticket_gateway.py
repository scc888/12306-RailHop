"""Strict ticket queries and exact local-date / money conversion for transfers."""
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from ..models.transfer_schemas import SEAT_NAMES, TransferLeg, TransferSeat
from .client_12306 import Ticket12306Client, RailwayQueryError

CST = timezone(timedelta(hours=8))


def parse_price_fen(value: str) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r'[¥￥]\d+(?:\.\d{1,2})?', value.strip()):
        return None
    try:
        return int(Decimal(value.strip()[1:]) * 100)
    except (InvalidOperation, ValueError):
        return None


def has_ticket(value: str) -> bool:
    return value == '有' or (isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0)


class TransferTicketGateway:
    def __init__(self, client=None):
        self.client = client or Ticket12306Client()
        self.last_issues = []

    def query(self, train_date: date, from_code: str, to_code: str,
              allowed_seats: list[str], timeout_seconds: float) -> list[TransferLeg]:
        self.last_issues = []
        tickets = self.client.query_tickets_strict(train_date.isoformat(), from_code, to_code,
                                                  timeout_seconds=timeout_seconds)
        result = []
        for ticket in tickets:
            if (ticket.from_station_telecode, ticket.to_station_telecode) != (from_code, to_code):
                self.last_issues.append('上游返回的站点与查询区间不一致')
                continue
            if not ticket.can_buy:
                continue
            seats = [TransferSeat(code=code, name=SEAT_NAMES[code], availability=getattr(ticket.seats, code),
                                  price_fen=parse_price_fen(ticket.prices.get(code, '')))
                     for code in allowed_seats if has_ticket(getattr(ticket.seats, code, '--'))]
            if not seats:
                continue
            try:
                hour, minute = map(int, ticket.duration.split(':'))
                if hour < 0 or not 0 <= minute < 60 or hour * 60 + minute <= 0:
                    raise ValueError()
                departure = datetime.combine(train_date, datetime.strptime(ticket.start_time, '%H:%M').time(), CST)
                arrival = departure + timedelta(hours=hour, minutes=minute)
                if arrival.strftime('%H:%M') != ticket.arrive_time:
                    raise ValueError()
            except (ValueError, OverflowError):
                self.last_issues.append('上游返回的时刻与历时不一致')
                continue
            try:
                run_date = datetime.strptime(ticket.run_date, '%Y%m%d').date() if ticket.run_date else None
            except ValueError:
                run_date = None
            result.append(TransferLeg(train_no=ticket.train_no, train_code=ticket.train_code,
                from_station=from_code, to_station=to_code, from_station_name=ticket.from_station_name,
                to_station_name=ticket.to_station_name, departure_at=departure, arrival_at=arrival,
                seats=seats, queried_at=datetime.now(CST), run_date=run_date))
        return result
