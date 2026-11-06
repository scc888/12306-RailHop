"""Public railway data is reused briefly without reusing failures or sessions."""
import unittest
from unittest.mock import Mock
from unittest.mock import patch
from app.services.client_12306 import Ticket12306Client, RailwayQueryError
from app.services.query_cache import QueryCache
from test_transfer_gateway import row, railway_response


class QueryCacheTests(unittest.TestCase):
    def test_query_dependencies_isolate_cookies_and_planning_state(self):
        from app.api.journey_routes import get_journey_service
        from app.api.transfer_routes import get_transfer_planner
        for factory in (get_journey_service, get_transfer_planner):
            first, second = factory(), factory()
            try:
                a, b = next(first), next(second)
                clients = (a.client,b.client) if hasattr(a,'client') else (a.gateway.client,b.gateway.client)
                clients[0].session.cookies.set('test-cookie','first-request')
                self.assertNotIn('test-cookie', clients[1].session.cookies)
                if hasattr(a, 'transfer'):
                    self.assertIs(a.transfer.gateway.client, a.client)
                    self.assertIs(a.same_train.client, a.client)
                    self.assertIsNot(a.transfer.gateway, b.transfer.gateway)
            finally:
                first.close()
                second.close()

    def test_database_outage_falls_back_to_memory_with_backoff(self):
        cache = QueryCache(dsn='unused')
        cache._connection_pool = Mock(side_effect=ConnectionError('unavailable'))
        cache.set('tickets', ['a'], [], 15)
        self.assertEqual(cache.get('tickets', ['a']), [])
        self.assertIsNone(cache.get('tickets', ['b']))
        self.assertEqual(cache._connection_pool.call_count, 1)

    def test_another_database_initializer_does_not_block_a_ticket_query(self):
        cache = QueryCache(dsn='unused')
        cache._database_lock.acquire()
        try:
            self.assertIsNone(cache.get('tickets', ['b']))
        finally:
            cache._database_lock.release()

    def test_disabling_ticket_cache_bypasses_existing_persisted_entries(self):
        cache = QueryCache()
        client = self.client(cache)
        client.query_tickets_strict('2026-10-10','SHH','BJP')
        with patch('app.services.client_12306.settings.TICKET_CACHE_SECONDS',0):
            self.assertFalse(client.has_cached_query('tickets','2026-10-10','SHH','BJP'))
            client.query_tickets_strict('2026-10-10','SHH','BJP')
        self.assertEqual(client.session.get.call_count,2)

    def test_malformed_cache_payload_falls_back_to_the_railway(self):
        cache = QueryCache()
        cache.set('tickets', ['2026-10-10','SHH','BJP','ADULT'], [{}], 15)
        client = self.client(cache)
        self.assertEqual(client.query_tickets_strict('2026-10-10','SHH','BJP')[0].train_code,'G1')
        self.assertEqual(client.session.get.call_count,1)

    def client(self, cache, rows=None):
        client = Ticket12306Client(cache=cache)
        client.ensure_init = Mock()
        client.session.get = Mock(return_value=railway_response({
            'status': True, 'data': {'result': [row()] if rows is None else rows, 'map': {}}}))
        return client

    def test_clients_share_ticket_data_not_mutable_results_and_expire(self):
        clock = [100.0]
        cache = QueryCache(clock=lambda: clock[0])
        first, second = self.client(cache), self.client(cache)
        tickets = first.query_tickets_strict('2026-10-10', 'SHH', 'BJP')
        tickets[0].seats.ze = '无'
        reused = second.query_tickets_strict('2026-10-10', 'SHH', 'BJP')
        self.assertEqual(reused[0].seats.ze, '有')
        self.assertEqual(reused[0].run_date, '20261010')
        second.session.get.assert_not_called()
        second.ensure_init.assert_not_called()
        clock[0] += 31
        second.query_tickets_strict('2026-10-10', 'SHH', 'BJP')
        self.assertEqual(second.session.get.call_count, 1)

    def test_dates_station_direction_and_ticket_purpose_do_not_collide(self):
        client = self.client(QueryCache())
        for args in [('2026-10-10','SHH','BJP','ADULT'),
                     ('2026-10-11','SHH','BJP','ADULT'),
                     ('2026-10-10','BJP','SHH','ADULT'),
                     ('2026-10-10','AOH','BJP','ADULT'),
                     ('2026-10-10','SHH','BJP','0X00')]:
            client.query_tickets_strict(*args)
        self.assertEqual(client.session.get.call_count, 5)

    def test_successful_empty_results_are_cached_but_upstream_errors_are_not(self):
        client = self.client(QueryCache(), rows=[])
        self.assertEqual(client.query_tickets_strict('2026-10-10','SHH','BJP'), [])
        self.assertEqual(client.query_tickets_strict('2026-10-10','SHH','BJP'), [])
        self.assertEqual(client.session.get.call_count, 1)
        client.session.get.return_value = railway_response({'status':False})
        for _ in range(2):
            with self.assertRaises(RailwayQueryError):
                client.query_tickets_strict('2026-10-11','SHH','BJP')
        self.assertEqual(client.session.get.call_count, 3)

    def test_stops_are_shared_and_keep_original_expiry(self):
        clock = [100.0]
        cache = QueryCache(clock=lambda: clock[0])
        first, second = self.client(cache), self.client(cache)
        first.session.get.return_value = railway_response({'status':True,'data':{'data':[
            {'station_no':'01','station_name':'上海','arrive_time':'----','start_time':'08:00','stopover_time':'----'}]}})
        self.assertEqual(first.query_train_stops_strict('train','SHH','BJP','2026-10-10')[0].station_name, '上海')
        self.assertEqual(second.query_train_stops_strict('train','SHH','BJP','2026-10-10')[0].station_name, '上海')
        second.session.get.assert_not_called()
        clock[0] += 12 * 3600 + 1
        second.session.get.return_value = first.session.get.return_value
        second.query_train_stops_strict('train','SHH','BJP','2026-10-10')
        self.assertEqual(second.session.get.call_count, 1)

    def test_cache_is_bounded_and_does_not_extend_ttl_on_read(self):
        clock = [100.0]
        cache = QueryCache(max_entries=2, clock=lambda: clock[0])
        cache.set('tickets', ['a'], [{'value':1}], 10)
        cache.set('tickets', ['b'], [], 10)
        self.assertEqual(cache.get('tickets', ['a']), [{'value':1}])
        cache.set('tickets', ['c'], [], 10)
        self.assertIsNone(cache.get('tickets', ['b']))
        clock[0] = 110
        self.assertIsNone(cache.get('tickets', ['a']))

    def test_warm_transfer_search_avoids_network_and_artificial_pacing(self):
        from app.services.transfer_planner import TransferPlanner
        from app.services.transfer_station_service import TransferStationService
        from app.services.transfer_ticket_gateway import TransferTicketGateway
        from app.models.transfer_schemas import TransferQueryRequest
        from test_transfer_planner import NOW
        cache, pauses = QueryCache(), []
        client = self.client(cache)
        def network(url, params, **kwargs):
            day, a, b = [params['leftTicketDTO.'+key] for key in ('train_date','from_station','to_station')]
            rows = []
            if day == '2026-10-10' and (a,b) in [('SHH','NKH'),('NKH','BJP')]:
                parts = row(start='08:00' if a=='SHH' else '09:30',arrive='09:00' if a=='SHH' else '12:00',
                    duration='01:00' if a=='SHH' else '02:30').split('|')
                parts[2:8] = [a+b,'G1' if a=='SHH' else 'G2',a,b,a,b]
                rows = ['|'.join(parts)]
            return railway_response({'status':True,'data':{'result':rows,'map':{}}})
        client.session.get.side_effect = network
        request = TransferQueryRequest(from_station='SHH',to_station='BJP',train_date='2026-10-10',
            ordered_via_stations=['NKH'],min_transfer_minutes=10)
        def search():
            return TransferPlanner(TransferStationService(),TransferTicketGateway(client),sleep_fn=pauses.append).search(request,now=NOW)
        first = search()
        self.assertEqual(len(first.plans),1)
        self.assertTrue(pauses)
        client.session.get.reset_mock()
        pauses.clear()
        second = search()
        self.assertEqual([p.id for p in second.plans],[p.id for p in first.plans])
        client.session.get.assert_not_called()
        self.assertEqual(pauses,[])


if __name__ == '__main__':
    unittest.main()
