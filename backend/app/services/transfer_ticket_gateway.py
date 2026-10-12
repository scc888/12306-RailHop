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


def ticket_to_leg(ticket, train_date: date, allowed_seats: list[str], queried_at=None):
    """Convert a previously queried ticket without issuing another network request."""
    if not ticket.can_buy:
        return None
    seats = [TransferSeat(code=code, name=SEAT_NAMES[code], availability=getattr(ticket.seats, code),
        price_fen=parse_price_fen(ticket.prices.get(code, '')))
        for code in allowed_seats if has_ticket(getattr(ticket.seats, code, '--'))]
    if not seats:
        return None
    try:
        hour, minute = map(int, ticket.duration.split(':'))
        if hour < 0 or not 0 <= minute < 60 or hour * 60 + minute <= 0:
            raise ValueError()
        departure = datetime.combine(train_date, datetime.strptime(ticket.start_time, '%H:%M').time(), CST)
        arrival = departure + timedelta(hours=hour, minutes=minute)
        if arrival.strftime('%H:%M') != ticket.arrive_time:
            raise ValueError()
        run_date = datetime.strptime(ticket.run_date, '%Y%m%d').date() if ticket.run_date else None
        if run_date and run_date > train_date:
            raise ValueError()
    except (ValueError, OverflowError, TypeError) as exc:
        raise ValueError('上游返回的日期、时刻与历时不一致') from exc
    return TransferLeg(train_no=ticket.train_no, train_code=ticket.train_code,
        from_station=ticket.from_station_telecode, to_station=ticket.to_station_telecode,
        from_station_name=ticket.from_station_name, to_station_name=ticket.to_station_name,
        departure_at=departure, arrival_at=arrival, seats=seats,
        queried_at=queried_at or datetime.now(CST), run_date=run_date)


class TransferTicketGateway:
    def __init__(self, client=None):
        self.client = client or Ticket12306Client()
        self.last_issues = []

    def query(self, train_date: date, from_code: str, to_code: str,
              allowed_seats: list[str], timeout_seconds: float) -> list[TransferLeg]:
        return self.query_scoped(train_date, from_code, to_code, allowed_seats, timeout_seconds)

    def query_scoped(self, train_date: date, from_code: str, to_code: str,
                     allowed_seats: list[str], timeout_seconds: float, *,
                     allowed_origin_codes=None, allowed_destination_codes=None) -> list[TransferLeg]:
        """Query one official representative pair, retaining only explicitly allowed stations.

        The official response can contain other stations in the same city. It is not
        guaranteed to contain every station pair; callers must disclose that coverage.
        Omitting either set keeps that endpoint exact, including intermediate stops.
        """
        origins = set(allowed_origin_codes) if allowed_origin_codes is not None else {from_code}
        destinations = set(allowed_destination_codes) if allowed_destination_codes is not None else {to_code}
        self.last_issues = []
        tickets = self.client.query_tickets_strict(train_date.isoformat(), from_code, to_code,
                                                  timeout_seconds=timeout_seconds)
        result = []
        for ticket in tickets:
            if ticket.from_station_telecode not in origins or ticket.to_station_telecode not in destinations:
                # Official queries may include other stations in the same city.
                # Excluding those is normal filtering, not an upstream failure.
                continue
            try:
                leg = ticket_to_leg(ticket, train_date, allowed_seats)
            except ValueError as exc:
                self.last_issues.append(str(exc))
                continue
            if leg:
                result.append(leg)
        return result
