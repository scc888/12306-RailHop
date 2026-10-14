"""Budget-sensitive fastest transfer regressions using deterministic ticket legs."""
import unittest
from datetime import date

from app.models.transfer_schemas import TransferQueryRequest
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_station_service import TransferStationService
from test_transfer_planner import NOW, Samples, leg, station


class FastestPlannerTests(unittest.TestCase):
    def test_duplicate_actual_city_prefixes_do_not_spend_state_budget_twice(self):
        class CityRows(Samples):
            def query_scoped(self, day, a, b, seats, timeout, *, allowed_origin_codes=None,
                    allowed_destination_codes=None):
                self.calls.append((day,a,b))
                return [item.model_copy(deep=True) for item in self.legs
                    if item.departure_at.date() == day
                    and item.from_station in allowed_origin_codes
                    and item.to_station in allowed_destination_codes]
        codes = ['BA'+chr(65+i) for i in range(26)] + ['BBA','BBB']
        legs = [leg('AAA',code,'2026-10-10T08:00',
                    '2026-10-10T08:30' if code == 'BBB' else '2026-10-10T09:00',f'G{i}-{j}')
                for i,code in enumerate(codes) for j in range(40)]
        legs += [leg('BAA','ZZZ','2026-10-10T17:00','2026-10-10T18:00','G100'),
                 leg('BBB','ZZZ','2026-10-10T08:45','2026-10-10T09:10','G101')]
        for origins in [['AAA'],['AAA','AAB']]:
            with self.subTest(origins=origins):
                gateway = CityRows(legs)
                request = TransferQueryRequest(from_station='AAA',to_station='ZZZ',train_date='2026-10-10',
                    from_scope='city',from_station_codes=origins,min_transfer_minutes=15)
                planner = TransferPlanner(TransferStationService(entries=[station(code) for code in codes]),
                    gateway,limits={'request_interval':0})
                result = planner.search(request,now=NOW)
                self.assertEqual(result.plans[0].total_minutes,70)
                self.assertNotIn('state_limit',result.meta.truncation_reasons)
                self.assertIn((date(2026,10,10),'BBB','ZZZ'),gateway.calls)
                self.assertLessEqual(result.meta.query_count,120)

    def search(self, legs, codes, limits=None, **changes):
        request = TransferQueryRequest(**(dict(from_station='AAA', to_station='ZZZ',
            train_date='2026-10-10', min_transfer_minutes=15) | changes))
        gateway = Samples(legs)
        planner = TransferPlanner(TransferStationService(entries=[station(code) for code in codes]), gateway,
            limits={'request_interval': 0, **(limits or {})}, sleep_fn=lambda _: None)
        return planner.search(request, now=NOW), gateway

    def test_32_candidates_find_165_minutes_within_default_120_queries(self):
        codes = ['BA' + chr(65+i) for i in range(26)] + ['BBA','BBB','BBC','BBD','BBE','BBF']
        legs = [leg('AAA', code, '2026-10-10T08:00',
                    '2026-10-10T09:30' if code == 'BBF' else '2026-10-10T09:00', f'G{i+1}')
                for i, code in enumerate(codes)]
        legs += [leg('BAA','ZZZ','2026-10-10T17:00','2026-10-10T18:00','G50'),
                 leg('BBF','ZZZ','2026-10-10T09:45','2026-10-10T10:45','G51')]
        for max_transfers in [None, 2]:
            with self.subTest(max_transfers=max_transfers):
                result, gateway = self.search(legs, codes, max_transfers=max_transfers)
                self.assertEqual(result.plans[0].total_minutes, 165)
                self.assertEqual(result.plans[0].connections[0].station.station_code, 'BBF')
                self.assertLessEqual(result.meta.query_count, 120)
                self.assertEqual(len(gateway.calls), len(set(gateway.calls)))

    def test_late_departure_prefix_is_retained_despite_longer_first_leg(self):
        legs = [leg('AAA','BBB','2026-10-10T08:00','2026-10-10T08:30','G1'),
                leg('AAA','BBB','2026-10-10T10:00','2026-10-10T11:00','G2'),
                leg('BBB','ZZZ','2026-10-10T11:15','2026-10-10T12:00','G3')]
        result, gateway = self.search(legs, ['BBB'], limits={'max_queries': 2})
        self.assertEqual(result.plans[0].total_minutes, 120)
        self.assertEqual(result.plans[0].legs[0].train_code, 'G2')
        self.assertEqual(result.meta.query_count, 2)

    def test_next_day_short_route_is_queried_before_same_day_long_route(self):
        legs = [leg('AAA','BBB','2026-10-10T00:00','2026-10-10T20:00','G1'),
                leg('AAA','CCC','2026-10-10T23:00','2026-10-10T23:50','G2'),
                leg('CCC','ZZZ','2026-10-11T00:15','2026-10-11T01:00','G3')]
        result, gateway = self.search(legs, ['BBB','CCC'], limits={'max_queries':3})
        self.assertEqual([p.total_minutes for p in result.plans], [120])
        self.assertIn((date(2026,10,11),'CCC','ZZZ'), gateway.calls)

    def test_midnight_date_priority_accounts_for_station_specific_minimum(self):
        legs = [leg('AAA','BBB','2026-10-10T00:00','2026-10-10T00:30','G1'),
                leg('AAA','CCC','2026-10-10T23:00','2026-10-10T23:50','G2'),
                leg('CCC','ZZZ','2026-10-11T00:15','2026-10-11T01:00','G3')]
        gateway = Samples(legs)
        request = TransferQueryRequest(from_station='AAA',to_station='ZZZ',train_date='2026-10-10')
        planner = TransferPlanner(TransferStationService(entries=[station('BBB',1440),station('CCC',15)]),
            gateway,limits={'max_queries':3,'request_interval':0})
        result = planner.search(request,now=NOW)
        self.assertEqual([p.total_minutes for p in result.plans],[120])
        self.assertEqual(gateway.calls[-1],(date(2026,10,11),'CCC','ZZZ'))

    def test_max_depth_search_respects_global_time_query_and_state_limits(self):
        legs = [leg('AAA','BBB','2026-10-10T08:00','2026-10-10T09:00','G1'),
                leg('BBB','ZZZ','2026-10-10T09:15','2026-10-10T10:00','G2')]
        for limits, reason in [({'max_queries':1},'query_limit'),
                ({'max_states':1},'state_limit'), ({'max_seconds':0},'time_limit')]:
            with self.subTest(reason=reason):
                result, gateway = self.search(legs,['BBB'],max_transfers=2,limits=limits)
                self.assertIn(reason,result.meta.truncation_reasons)
                self.assertEqual(result.plans,[])
                self.assertLessEqual(len(gateway.calls),1)

    def test_max_two_returns_one_and_two_transfers_while_old_exact_stays_exact(self):
        legs = [leg('AAA','BBB','2026-10-10T08:00','2026-10-10T09:00','G1'),
                leg('BBB','ZZZ','2026-10-10T09:15','2026-10-10T12:00','G2'),
                leg('BBB','CCC','2026-10-10T09:15','2026-10-10T10:00','G3'),
                leg('CCC','ZZZ','2026-10-10T10:15','2026-10-10T11:00','G4')]
        result, _ = self.search(legs, ['BBB','CCC'], max_transfers=2,
                                limits={'max_queries':10})
        self.assertEqual([len(p.connections) for p in result.plans], [2,1])
        self.assertLessEqual(result.meta.query_count, 10)
        exact, _ = self.search(legs, ['BBB','CCC'], transfer_count=2)
        self.assertEqual([len(p.connections) for p in exact.plans], [2])
        required, _ = self.search(legs, ['BBB','CCC'], max_transfers=2,
            ordered_via_stations=['BBB','CCC'])
        self.assertEqual([len(p.connections) for p in required.plans], [2])

    def test_equal_duration_prefers_fewer_transfers_even_with_later_arrival(self):
        legs = [leg('AAA','BBB','2026-10-10T09:00','2026-10-10T10:00','G1'),
                leg('BBB','ZZZ','2026-10-10T10:15','2026-10-10T12:00','G2'),
                leg('AAA','CCC','2026-10-10T08:00','2026-10-10T08:30','G3'),
                leg('CCC','DDD','2026-10-10T08:45','2026-10-10T09:30','G4'),
                leg('DDD','ZZZ','2026-10-10T09:45','2026-10-10T11:00','G5')]
        result, _ = self.search(legs,['BBB','CCC','DDD'],max_transfers=2)
        self.assertEqual([p.total_minutes for p in result.plans],[180,180])
        self.assertEqual([len(p.connections) for p in result.plans],[1,2])

    def test_explicit_actual_endpoints_are_each_queried(self):
        class ExactPairs(Samples):
            def query_scoped(self, day, a, b, seats, timeout, **kwargs):
                return self.query(day,a,b,seats,timeout)
        legs = [leg('AAB','BBB','2026-10-10T08:00','2026-10-10T09:00','G1'),
                leg('BBB','ZZY','2026-10-10T09:15','2026-10-10T10:00','G2')]
        request = TransferQueryRequest(from_station='AAA', to_station='ZZZ', train_date='2026-10-10',
            from_scope='city', to_scope='city', min_transfer_minutes=15).model_copy(update={
                'from_station_codes':['AAA','AAB'], 'to_station_codes':['ZZZ','ZZY']})
        gateway = ExactPairs(legs)
        result = TransferPlanner(TransferStationService(entries=[station('BBB')]), gateway,
            limits={'request_interval':0}, sleep_fn=lambda _:None).search(request,now=NOW,
                origin_codes={'AAA','AAB'}, destination_codes={'ZZZ','ZZY'})
        self.assertEqual([p.total_minutes for p in result.plans], [120])
        self.assertIn((date(2026,10,10),'AAB','BBB'),gateway.calls)
        self.assertIn((date(2026,10,10),'BBB','ZZY'),gateway.calls)


if __name__ == '__main__':
    unittest.main()
