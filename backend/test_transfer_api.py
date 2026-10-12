import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from test_transfer_planner import Samples, NOW, leg
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_station_service import TransferStationService
from app.services.transfer_ticket_gateway import TransferTicketGateway
from app.services.client_12306 import Ticket12306Client
from test_transfer_gateway import row, railway_response


class TransferApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.body = dict(from_station='SHH', to_station='BJP', train_date='2026-10-10', ordered_via_stations=['NKH'])

    def test_station_search_and_real_service_flow(self):
        response = self.client.get('/api/transfers/stations?keyword=njn')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'][0]['station_code'], 'NKH')
        samples = Samples([leg('SHH','NKH','2026-10-10T08:00','2026-10-10T09:00'),
                           leg('NKH','BJP','2026-10-10T09:15','2026-10-10T12:00','G2', 20005)])
        planner = TransferPlanner(TransferStationService(), samples, sleep_fn=lambda s: None)
        original = planner.search
        planner.search = lambda request, **kwargs: original(request, now=NOW, **kwargs)
        from app.api.transfer_routes import get_transfer_planner
        app.dependency_overrides[get_transfer_planner] = lambda: planner
        try:
            result = self.client.post('/api/transfers/query', json=self.body)
            self.assertEqual(result.status_code, 200)
            payload = result.json()['data']
            self.assertEqual(payload['plans'][0]['total_price_fen'], 32355)
            self.assertEqual(payload['plans'][0]['connections'][0]['wait_minutes'], 15)
            self.assertEqual(len(payload['plans'][0]['legs']), 2)
        finally:
            app.dependency_overrides.clear()

    def test_validation_and_busy_release(self):
        from app.api.transfer_routes import transfer_lock
        self.assertEqual(self.client.post('/api/transfers/query', json=self.body | dict(min_transfer_minutes=14)).status_code, 422)
        self.assertEqual(self.client.post('/api/transfers/query', json=self.body | dict(ordered_via_stations=['AAA'])).status_code, 400)
        self.assertEqual(self.client.post('/api/transfers/query', json=self.body | dict(from_station='AAA')).status_code, 400)
        transfer_lock.acquire()
        try:
            self.assertEqual(self.client.post('/api/transfers/query', json=self.body).status_code, 429)
        finally:
            transfer_lock.release()
        self.assertEqual(self.client.post('/api/transfers/query', json=self.body | dict(ordered_via_stations=['AAA'])).status_code, 400)
        self.assertFalse(transfer_lock.locked())

    def test_two_transfers_across_midnight_through_real_gateway(self):
        from app.api.transfer_routes import get_transfer_planner

        def sample(a, b, start, arrive, duration, train, priced=True):
            parts = row(start, arrive, duration, dest=b).split('|')
            parts[2:8] = [train, train, a, b, a, b]
            parts[39] = 'O012350000M014000000' if priced else ''
            parts[31] = '有'
            return '|'.join(parts)

        responses = {
            ('2026-10-10', 'SHH', 'NKH'): [sample('SHH','NKH','23:50','01:50','02:00','G1')],
            ('2026-10-11', 'NKH', 'WHN'): [sample('NKH','WHN','02:05','03:05','01:00','G2')],
            ('2026-10-11', 'WHN', 'BJP'): [sample('WHN','BJP','03:20','05:20','02:00','G3', False)],
        }

        def network(url, params, **kwargs):
            key = tuple(params[f'leftTicketDTO.{name}'] for name in ('train_date','from_station','to_station'))
            return railway_response({'status': True, 'data': {'result': responses.get(key, []), 'map': {}}})

        railway = Ticket12306Client()
        planner = TransferPlanner(TransferStationService(), TransferTicketGateway(client=railway), sleep_fn=lambda s: None)
        original = planner.search
        planner.search = lambda request, **kwargs: original(request, now=NOW, **kwargs)
        app.dependency_overrides[get_transfer_planner] = lambda: planner
        try:
            with patch.object(railway, 'ensure_init'), patch.object(railway.session, 'get', side_effect=network):
                result = self.client.post('/api/transfers/query', json=self.body | dict(
                    transfer_count=2, ordered_via_stations=['NKH','WHN']))
                self.assertEqual(result.status_code, 200)
                plans = result.json()['data']['plans']
                self.assertEqual(len(plans), 1)
                plan = plans[0]
                self.assertEqual(len(plan['legs']), 3)
                self.assertEqual([c['station']['station_code'] for c in plan['connections']], ['NKH','WHN'])
                self.assertEqual([c['wait_minutes'] for c in plan['connections']], [15,15])
                self.assertEqual(plan['legs'][0]['arrival_at'], '2026-10-11T01:50:00+08:00')
                self.assertEqual(plan['legs'][1]['departure_at'], '2026-10-11T02:05:00+08:00')
                self.assertEqual(plan['total_minutes'], 330)
                self.assertIsNone(plan['total_price_fen'])
                self.assertEqual(plan['known_price_fen'], 24700)
                self.assertEqual([s['code'] for s in plan['legs'][0]['seats']], ['ze','zy'])
                reversed_order = self.client.post('/api/transfers/query', json=self.body | dict(
                    transfer_count=2, ordered_via_stations=['WHN','NKH']))
                self.assertEqual(reversed_order.json()['data']['plans'], [])
        finally:
            app.dependency_overrides.clear()

    def test_regular_trains_through_api_and_real_gateway(self):
        from app.api.transfer_routes import get_transfer_planner

        def sample(a, b, start, arrive, duration, train):
            parts = row(start, arrive, duration, dest=b).split('|')
            parts[2:8] = [train, train, a, b, a, b]
            parts[30] = '--'
            parts[28] = '有'
            parts[39] = '3015000000'  # Hard sleeper, 150 yuan.
            return '|'.join(parts)

        responses = {
            ('2026-10-10', 'BJP', 'SHH'): [sample('BJP','SHH','08:00','09:00','01:00','K1')],
            ('2026-10-10', 'SHH', 'HGH'): [sample('SHH','HGH','09:30','12:00','02:30','Z2')],
        }

        def network(url, params, **kwargs):
            key = tuple(params[f'leftTicketDTO.{name}'] for name in ('train_date','from_station','to_station'))
            return railway_response({'status': True, 'data': {'result': responses.get(key, []), 'map': {}}})

        railway = Ticket12306Client()
        planner = TransferPlanner(TransferStationService(), TransferTicketGateway(client=railway), sleep_fn=lambda s: None)
        original = planner.search
        planner.search = lambda request, **kwargs: original(request, now=NOW, **kwargs)
        app.dependency_overrides[get_transfer_planner] = lambda: planner
        body = self.body | dict(from_station='BJP', to_station='HGH', ordered_via_stations=['SHH'])
        try:
            with patch.object(railway, 'ensure_init'), patch.object(railway.session, 'get', side_effect=network):
                for train_type in ['all', 'regular']:
                    result = self.client.post('/api/transfers/query', json=body | dict(train_type=train_type))
                    self.assertEqual(result.status_code, 200)
                    plans = result.json()['data']['plans']
                    self.assertEqual(len(plans), 1)
                    self.assertEqual([item['train_code'] for item in plans[0]['legs']], ['K1','Z2'])
                    self.assertEqual(plans[0]['selected_seat_codes'], ['yw','yw'])
                    self.assertEqual(plans[0]['total_price_fen'], 30000)
                    self.assertEqual(plans[0]['connections'][0]['required_minutes'], 30)
                for criteria in [dict(train_type='high_speed'), dict(allowed_seats=['ze','zy'])]:
                    result = self.client.post('/api/transfers/query', json=body | criteria)
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()['data']['plans'], [])
        finally:
            app.dependency_overrides.clear()

    def test_legacy_query_contract_and_no_transactions(self):
        with patch('app.api.routes.client_12306.query_tickets', return_value=[]):
            response = self.client.get('/api/tickets/query?train_date=2026-10-10&from_station=上海&to_station=北京')
            self.assertEqual(response.json(), {'code':200, 'msg':'success', 'data':[]})
        with patch('app.api.routes.client_12306.query_train_stops', return_value=[]):
            response = self.client.get('/api/tickets/stops?train_no=X&from_station=上海&to_station=北京&depart_date=2026-10-10')
            self.assertEqual(response.json()['data'], [])
        with patch('app.api.routes.smart_planner.calculate_smart_plans', return_value=[]):
            response = self.client.get('/api/smart-plans/calculate?train_date=2026-10-10&train_no=X&train_code=G1&from_station=上海&to_station=北京')
            self.assertEqual(response.json()['data'], [])
        self.assertEqual(self.client.post('/api/orders/submit', json={}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
