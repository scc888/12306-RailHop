import json
import unittest
from datetime import date
from unittest.mock import Mock
import requests
from app.services.client_12306 import Ticket12306Client, RailwayQueryError
from app.services.transfer_ticket_gateway import TransferTicketGateway, parse_price_fen


def railway_response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result.encoding = 'utf-8'
    result._content = (body if isinstance(body, str) else json.dumps(body)).encode()
    return result


def row(start='23:50', arrive='01:50', duration='02:00', seat='有', can_buy='Y', dest='BJP'):
    parts = [''] * 40
    parts[:12] = ['secret', '预订', 'train-1', 'G1', 'SHH', dest, 'SHH', dest, start, arrive, duration, can_buy]
    parts[13] = '20261010'
    parts[30] = seat
    parts[39] = 'O012350000'
    return '|'.join(parts)


class GatewayTests(unittest.TestCase):
    def client(self, response):
        client = Ticket12306Client()
        client.ensure_init = Mock()
        client.session.get = Mock(return_value=response)
        return client

    def test_upstream_error_is_not_no_tickets_and_old_contract_remains(self):
        for body, status in [('', 200), ('<html>oops</html>', 200), ('oops', 200),
                             ({'status': False}, 200), ({'status': True, 'data': {}}, 200), ('bad', 503)]:
            client = self.client(railway_response(body, status))
            with self.subTest(body=body), self.assertRaises(RailwayQueryError):
                client.query_tickets_strict('2026-10-10', 'SHH', 'BJP')
            self.assertEqual(client.query_tickets('2026-10-10', 'SHH', 'BJP'), [])
        client = self.client(railway_response({'status': True, 'data': {'result': [], 'map': {}}}))
        self.assertEqual(client.query_tickets_strict('2026-10-10', 'SHH', 'BJP'), [])

    def test_midnight_and_multi_day_timing_and_exact_station(self):
        data = {'status': True, 'data': {'result': [row(), row(duration='26:00'), row(dest='VNP'), row(arrive='05:00')], 'map': {}}}
        gateway = TransferTicketGateway(client=self.client(railway_response(data)))
        legs = gateway.query(date(2026, 10, 10), 'SHH', 'BJP', ['ze'], 5)
        self.assertEqual([x.arrival_at.isoformat() for x in legs], ['2026-10-11T01:50:00+08:00', '2026-10-12T01:50:00+08:00'])
        self.assertEqual(legs[0].seats[0].price_fen, 12350)

    def test_seat_availability_is_strict(self):
        rows = [row(seat=s) for s in ['有', '2', '0', '-1', '候补', '未开售', '--', '无']]
        rows.append(row(can_buy='N'))
        gateway = TransferTicketGateway(client=self.client(railway_response({'status': True, 'data': {'result': rows, 'map': {}}})))
        self.assertEqual(len(gateway.query(date(2026, 10, 10), 'SHH', 'BJP', ['ze'], 5)), 2)

    def test_extra_city_stations_are_filtered_without_marking_query_failed(self):
        gateway = TransferTicketGateway(client=self.client(railway_response({'status': True, 'data': {
            'result': [row(), row(dest='VNP')], 'map': {}}})))
        self.assertEqual(len(gateway.query(date(2026,10,10),'SHH','BJP',['ze'],5)),1)
        self.assertEqual(gateway.last_issues, [])

    def test_money_is_integer_fen_and_missing_not_zero(self):
        self.assertEqual(parse_price_fen('¥123.5'), 12350)
        self.assertEqual(parse_price_fen('¥200.05'), 20005)
        for bad in ['', '--', 'NaN', '¥-1', '¥1.001', '未知']:
            self.assertIsNone(parse_price_fen(bad))


if __name__ == '__main__':
    unittest.main()
