import unittest
from unittest.mock import patch
from datetime import datetime, date, timedelta
from app.models.transfer_schemas import TransferStation, TransferLeg, TransferSeat, TransferQueryRequest
from app.services.transfer_station_service import TransferStationService
from app.services.transfer_ticket_gateway import CST
from app.services.client_12306 import RailwayQueryError
from app.services.transfer_planner import TransferPlanner

NOW = datetime(2026, 10, 9, tzinfo=CST)


def station(code, minutes=None, **kwargs):
    return TransferStation(station_name=code, station_code=code, pinyin=code, pinyin_abbr=code,
        source_url='https://www.12306.cn/', source_published_at='2026-01-01', verified_at='2026-10-10',
        reference_min_minutes=minutes, **kwargs)


def leg(a, b, depart, arrive, train='G1', price=12350, seats=None):
    return TransferLeg(train_no=train, train_code=train, from_station=a, to_station=b,
        from_station_name=a, to_station_name=b, departure_at=datetime.fromisoformat(depart).replace(tzinfo=CST),
        arrival_at=datetime.fromisoformat(arrive).replace(tzinfo=CST),
        seats=seats or [TransferSeat(code='ze', name='二等座', availability='有', price_fen=price)], queried_at=NOW)


class Samples:
    def __init__(self, legs=(), fail=False):
        self.legs = list(legs)
        self.fail = fail
        self.last_issues = []
        self.calls = []

    def query(self, day, a, b, seats, timeout):
        key = (day, a, b)
        self.calls.append(key)
        if self.fail:
            raise RailwayQueryError('铁路查询失败')
        return [x for x in self.legs if (x.departure_at.date(), x.from_station, x.to_station) == key]


class PlannerTests(unittest.TestCase):
    def search(self, legs, stations=None, limits=None, **kwargs):
        gateway = Samples(legs)
        planner = TransferPlanner(TransferStationService(entries=stations or [station('BBB')]), gateway,
                                  limits=limits, sleep_fn=lambda seconds: None)
        request = TransferQueryRequest(from_station='AAA', to_station='ZZZ', train_date='2026-10-10', **kwargs)
        return planner.search(request, now=NOW), gateway

    def pair(self, minute=15, price=20005):
        return [leg('AAA','BBB','2026-10-10T08:00','2026-10-10T09:00'),
                leg('BBB','ZZZ',f'2026-10-10T09:{minute:02d}','2026-10-10T10:00', 'G2', price)]

    def test_wait_boundary_and_user_and_station_threshold(self):
        for minutes, selected, reference, count in [(14,15,None,0),(15,15,None,1),(20,30,None,0),(20,15,30,0),(30,30,None,1)]:
            with self.subTest(minutes=minutes, selected=selected, reference=reference):
                result, _ = self.search(self.pair(minutes), stations=[station('BBB', reference)], min_transfer_minutes=selected)
                self.assertEqual(len(result.plans), count)
        result, _ = self.search(self.pair())
        self.assertEqual(result.plans[0].total_minutes, 120)
        self.assertEqual(result.plans[0].total_price_fen, 32355)

    def test_exact_transfer_count_and_ordered_stations(self):
        legs = [leg('AAA','BBB','2026-10-10T08:00','2026-10-10T09:00'),
                leg('BBB','CCC','2026-10-10T09:15','2026-10-10T10:00','G2'),
                leg('CCC','DDD','2026-10-10T10:15','2026-10-10T11:00','G3'),
                leg('DDD','ZZZ','2026-10-10T11:15','2026-10-10T12:00','G4')]
        stations = [station(s) for s in ['BBB','CCC','DDD']]
        result, _ = self.search(legs, stations, transfer_count=3, ordered_via_stations=['BBB','DDD'])
        self.assertEqual(len(result.plans[0].legs), 4)
        result, _ = self.search(legs, stations, transfer_count=3, ordered_via_stations=['DDD','BBB'])
        self.assertEqual(result.plans, [])
        result, _ = self.search(legs, stations, transfer_count=2)
        self.assertEqual(result.plans, [])

    def test_midnight_and_same_train_and_departed(self):
        legs = [leg('AAA','BBB','2026-10-10T23:00','2026-10-10T23:55'),
                leg('BBB','ZZZ','2026-10-11T00:15','2026-10-11T01:00','G2')]
        result, gateway = self.search(legs)
        self.assertEqual(result.plans[0].connections[0].wait_minutes, 20)
        self.assertIn((date(2026,10,11), 'BBB','ZZZ'), gateway.calls)
        legs[1].train_no = 'G1'
        result, _ = self.search(legs)
        self.assertEqual(result.plans, [])

    def test_no_cross_station_or_repeated_station(self):
        legs = self.pair()
        legs[1].from_station = 'CCC'
        result, _ = self.search(legs)
        self.assertEqual(result.plans, [])

    def test_missing_price_and_sorting(self):
        result, _ = self.search(self.pair(price=None))
        self.assertIsNone(result.plans[0].total_price_fen)
        self.assertEqual(result.plans[0].known_price_fen, 12350)
        legs = self.pair() + [leg('AAA','BBB','2026-10-10T09:00','2026-10-10T09:10','G3', 100),
                             leg('BBB','ZZZ','2026-10-10T09:25','2026-10-10T10:15','G4', 100)]
        result, _ = self.search(legs)
        self.assertEqual(result.plans[0].total_minutes, 75)
        result, _ = self.search(legs, sort_by='arrival')
        self.assertEqual(result.plans[0].legs[-1].arrival_at.hour, 10)
        self.assertEqual(result.plans[0].legs[-1].arrival_at.minute, 0)
        result, _ = self.search(legs, sort_by='price')
        self.assertEqual(result.plans[0].total_price_fen, 200)

    def test_query_budget_and_cache_and_failures(self):
        result, gateway = self.search(self.pair(), limits={'max_queries':1})
        self.assertTrue(result.meta.truncated)
        self.assertEqual(len(gateway.calls), 1)
        result, gateway = self.search(self.pair())
        self.assertEqual(len(gateway.calls), len(set(gateway.calls)))
        planner = TransferPlanner(TransferStationService(entries=[station('BBB')]), Samples(fail=True), sleep_fn=lambda s: None)
        result = planner.search(TransferQueryRequest(from_station='AAA', to_station='ZZZ', train_date='2026-10-10'), now=NOW)
        self.assertEqual(result.meta.status, 'upstream_error')
        self.assertTrue(result.meta.failed_pairs)

    def test_catalog_train_and_same_day_restrictions(self):
        result, _ = self.search(self.pair(), stations=[station('BBB', allowed_train_prefixes=['D'])])
        self.assertEqual(result.plans, [])
        legs = [leg('AAA','BBB','2026-10-10T23:00','2026-10-10T23:55'),
                leg('BBB','ZZZ','2026-10-11T00:15','2026-10-11T01:00','G2')]
        result, _ = self.search(legs, stations=[station('BBB', same_day_only=True)])
        self.assertEqual(result.plans, [])

    def test_partial_failure_time_state_budget_and_running_identity(self):
        class Partial(Samples):
            def query(self, day, a, b, seats, timeout):
                if b == 'CCC':
                    raise RailwayQueryError('timeout')
                return super().query(day,a,b,seats,timeout)
        planner = TransferPlanner(TransferStationService(entries=[station('BBB'), station('CCC')]),
            Partial(self.pair()), sleep_fn=lambda s: None)
        request = TransferQueryRequest(from_station='AAA', to_station='ZZZ', train_date='2026-10-10')
        result = planner.search(request, now=NOW)
        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.meta.status, 'partial')
        self.assertTrue(result.meta.failed_pairs)
        for limits, reason in [({'max_seconds':0}, 'time_limit'), ({'max_states':1},'state_limit')]:
            result, _ = self.search(self.pair(), limits=limits)
            self.assertTrue(result.meta.truncated)
            self.assertIn(reason, result.meta.truncation_reasons)
        legs = self.pair()
        legs[1].train_no = legs[0].train_no
        legs[0].run_date, legs[1].run_date = date(2026,10,9), date(2026,10,10)
        result, _ = self.search(legs)
        self.assertEqual(len(result.plans), 1)
        legs[1].run_date = legs[0].run_date
        result, _ = self.search(legs)
        self.assertEqual(result.plans, [])

    def test_deadline_stops_cached_expansion_and_warm_cache(self):
        legs = self.pair() + [leg('AAA','BBB','2026-10-10T08:05','2026-10-10T09:00','G3')]
        planner = TransferPlanner(TransferStationService(entries=[station('BBB')]), Samples(legs),
            limits={'request_interval':0,'horizon_hours':3}, sleep_fn=lambda s: None)
        request = TransferQueryRequest(from_station='AAA',to_station='ZZZ',train_date='2026-10-10')
        clock=[0]
        original=planner._plan
        def finish_one(*args):
            value=original(*args)
            clock[0]=46
            return value
        with patch('app.services.transfer_planner.time.monotonic',side_effect=lambda:clock[0]), \
             patch.object(planner,'_plan',side_effect=finish_one):
            result=planner.search(request,now=NOW)
        self.assertEqual(len(result.plans),1)
        self.assertIn('time_limit',result.meta.truncation_reasons)
        planner.limits['max_seconds']=0
        with patch('app.services.transfer_planner.time.monotonic',return_value=0):
            result=planner.search(request,now=NOW)
        self.assertEqual(result.plans,[])
        self.assertIn('time_limit',result.meta.truncation_reasons)

    def test_result_limit_keeps_later_better_plan_and_marks_truncation(self):
        legs = self.pair() + [leg('AAA','BBB','2026-10-10T08:05','2026-10-10T09:00','G3',100)]
        result, _ = self.search(legs, limits={'max_results':1}, sort_by='price')
        self.assertEqual(len(result.plans),1)
        self.assertEqual(result.plans[0].legs[0].train_code,'G3')
        self.assertIn('result_limit',result.meta.truncation_reasons)

    def test_official_default_personal_floor_and_expired_reference(self):
        for reference, custom, count, required in [(60,None,0,None),(15,None,1,15),
                (None,None,1,15),(10,None,1,10),(10,30,0,None),(15,30,0,None)]:
            with self.subTest(reference=reference,custom=custom):
                result,_=self.search(self.pair(),stations=[station('BBB',reference)],min_transfer_minutes=custom)
                self.assertEqual(len(result.plans),count)
                if count:
                    connection=result.plans[0].connections[0]
                    self.assertEqual(connection.required_minutes,required)
                    self.assertEqual(connection.official_min_minutes,reference)
        expired=station('BBB',60,reference_time_valid_from='2000-01-01',reference_time_valid_to='2026-10-09')
        result,_=self.search(self.pair(),stations=[expired])
        self.assertEqual(result.plans[0].connections[0].required_minutes,15)
        self.assertIsNone(result.plans[0].connections[0].official_min_minutes)
        sixty=[self.pair()[0],leg('BBB','ZZZ','2026-10-10T10:00','2026-10-10T11:00','G2')]
        result,_=self.search(sixty,stations=[station('BBB',60)])
        self.assertEqual(result.plans[0].connections[0].required_minutes,60)
        overnight=[leg('AAA','BBB','2026-10-10T23:00','2026-10-11T00:35'),
                   leg('BBB','ZZZ','2026-10-11T00:50','2026-10-11T02:00','G2')]
        future=station('BBB',60,reference_time_valid_from='2026-10-11',reference_time_valid_to='2099-12-31')
        result,_=self.search(overnight,stations=[future])
        self.assertEqual(result.plans,[])

    def test_regular_and_mixed_train_types_with_allowed_seats(self):
        ordinary_seat=[TransferSeat(code='yw',name='硬卧',availability='有',price_fen=15000)]
        legs=[leg('AAA','BBB','2026-10-10T08:00','2026-10-10T09:00','K1',seats=ordinary_seat),
              leg('BBB','ZZZ','2026-10-10T09:15','2026-10-10T12:00','Z2',seats=ordinary_seat)]
        for selected,expected in [('all',1),('regular',1),('high_speed',0)]:
            result,_=self.search(legs,train_type=selected)
            self.assertEqual(len(result.plans),expected)
        legs[1]=leg('BBB','ZZZ','2026-10-10T09:15','2026-10-10T12:00','G2')
        result,_=self.search(legs,train_type='all')
        self.assertEqual(len(result.plans),1)
        result,_=self.search(legs,train_type='regular')
        self.assertEqual(result.plans,[])
        result,_=self.search(legs,stations=[station('BBB',allowed_train_prefixes=['G','D','C'])])
        self.assertEqual(result.plans,[])
        catalog=TransferStationService()
        self.assertEqual(catalog.validate_via(['SHH'])[0].allowed_train_prefixes,[])


if __name__ == '__main__':
    unittest.main()
