import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from test_transfer_planner import Samples, NOW, leg
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_station_service import TransferStationService


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
        planner.search = lambda request: original(request, now=NOW)
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
