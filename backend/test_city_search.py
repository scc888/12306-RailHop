import unittest
from datetime import date
from unittest.mock import Mock, patch

from app.models.transfer_schemas import TransferQueryRequest
from app.services.station_service import StationService
from app.services.transfer_ticket_gateway import TransferTicketGateway
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_station_service import TransferStationService
from app.services.client_12306 import Ticket12306Client
from test_transfer_gateway import railway_response, row
from test_transfer_planner import NOW, leg, station


class ScopedSamples:
    def __init__(self, legs):
        self.legs = legs
        self.calls = []
        self.last_issues = []

    def query(self, day, a, b, seats, timeout):
        return self.query_scoped(day, a, b, seats, timeout)

    def query_scoped(self, day, a, b, seats, timeout, *, allowed_origin_codes=None,
                     allowed_destination_codes=None):
        origins = set(allowed_origin_codes or [a])
        destinations = set(allowed_destination_codes or [b])
        self.calls.append((day, a, b, tuple(sorted(origins)), tuple(sorted(destinations))))
        return [item for item in self.legs if item.departure_at.date() == day
                and item.from_station in origins and item.to_station in destinations]


class CitySearchTests(unittest.TestCase):
    def request(self, **kwargs):
        return TransferQueryRequest(from_station='AAA', to_station='ZZZ', train_date='2026-10-10',
                                    **kwargs)

    def planner(self, legs, **limits):
        return TransferPlanner(TransferStationService(entries=[station('BBB')]), ScopedSamples(legs),
                               limits={'request_interval': 0, 'horizon_hours': 3, **limits},
                               sleep_fn=lambda seconds: None)

    def pair(self):
        return [leg('AAB', 'BBB', '2026-10-10T08:00', '2026-10-10T09:00'),
                leg('BBB', 'ZZY', '2026-10-10T09:15', '2026-10-10T10:00', 'G2')]

    def test_official_city_fields_group_nonprefix_stations(self):
        service = StationService()
        service._parse_station_text('@wh|武汉|WHN|wuhan|wh|1|1314|武汉|||'
            '@hk|汉口|HKN|hankou|hk|2|1314|武汉|||'
            '@wc|武昌|WCN|wuchang|wc|3|1314|武汉|||'
            '@false|武汉示例|XXX|wuhanshili|whsl|4|9999|其他城市|||'
            '@old|旧字典站|OLD|jiuzidian|jzd|5')
        self.assertEqual({s.telecode for s in service.city_stations('WHN')}, {'WHN', 'HKN', 'WCN'})
        self.assertEqual(service.city_stations('HKN')[0].city_name, '武汉')
        self.assertEqual(service.city_stations('HKN')[0].city_code, '1314')
        self.assertEqual([s.telecode for s in service.city_stations('OLD')], ['OLD'])
        self.assertEqual(service.city_stations('BAD'), [])

    def test_real_dictionary_wuchang_and_hankou_belong_to_wuhan(self):
        service = StationService()
        service.ensure_loaded()
        codes = {s.telecode for s in service.city_stations('WHN')}
        self.assertTrue({'WHN', 'HKN', 'WCN'}.issubset(codes))

    def test_gateway_city_filter_keeps_actual_station_identity(self):
        alternate = row(dest='VNP').split('|')
        alternate[6] = 'AOH'
        response = railway_response({'status': True, 'data': {'result': [row(), '|'.join(alternate),
                                        row(dest='ZZZ')], 'map': {}}})
        client = Ticket12306Client()
        client.ensure_init = Mock()
        client.session.get = Mock(return_value=response)
        gateway = TransferTicketGateway(client=client)
        values = gateway.query_scoped(date(2026, 10, 10), 'SHH', 'BJP', ['ze'], 5,
            allowed_origin_codes={'SHH', 'AOH'}, allowed_destination_codes={'BJP', 'VNP'})
        self.assertEqual([(v.from_station, v.to_station) for v in values], [('SHH', 'BJP'), ('AOH', 'VNP')])
        self.assertEqual([(v.from_station, v.to_station) for v in
            gateway.query(date(2026, 10, 10), 'SHH', 'BJP', ['ze'], 5)], [('SHH', 'BJP')])

    def test_city_origins_and_destinations_connect_but_middle_remains_exact(self):
        planner = self.planner(self.pair())
        result = planner.search(self.request(from_scope='city', to_scope='city'), now=NOW,
                                origin_codes={'AAA', 'AAB'}, destination_codes={'ZZZ', 'ZZY'})
        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].legs[0].from_station, 'AAB')
        self.assertEqual(result.plans[0].legs[-1].to_station, 'ZZY')
        self.assertEqual(set(result.meta.origin_station_codes), {'AAA', 'AAB'})
        self.assertEqual(set(result.meta.destination_station_codes), {'ZZZ', 'ZZY'})
        self.assertTrue(result.meta.truncated)
        self.assertIn('city_representative_query', result.meta.truncation_reasons)
        self.assertTrue(result.meta.coverage_notes)

        # Even a faulty broad upstream response cannot connect different actual stations.
        second = self.pair()[1].model_copy(update={'from_station': 'BBC'})
        planner = self.planner(self.pair())
        original = planner.gateway.query_scoped
        def unexpected(day, a, b, seats, timeout, **kwargs):
            if a == 'BBB':
                return [second]
            return original(day, a, b, seats, timeout, **kwargs)
        planner.gateway.query_scoped = unexpected
        result = planner.search(self.request(from_scope='city', to_scope='city'), now=NOW,
                                origin_codes={'AAA', 'AAB'}, destination_codes={'ZZZ', 'ZZY'})
        self.assertEqual(result.plans, [])

    def test_station_defaults_preserve_exact_behavior(self):
        planner = self.planner(self.pair())
        result = planner.search(self.request(), now=NOW)
        self.assertEqual(result.plans, [])
        self.assertEqual(result.meta.from_scope, 'station')
        self.assertEqual(result.meta.to_scope, 'station')
        self.assertFalse(result.meta.truncated)

    def test_scope_is_in_cache_key_and_city_calls_share_one_budget(self):
        planner = self.planner(self.pair(), max_queries=2)
        city = self.request(from_scope='city', to_scope='city')
        first = planner.search(city, now=NOW, origin_codes={'AAA'}, destination_codes={'ZZZ'})
        self.assertEqual(first.plans, [])
        second = planner.search(city, now=NOW, origin_codes={'AAA', 'AAB'},
                                destination_codes={'ZZZ', 'ZZY'})
        self.assertEqual(len(second.plans), 1)
        self.assertEqual(second.meta.query_count, 2)
        third = planner.search(city, now=NOW, origin_codes={'AAA', 'AAB'},
                               destination_codes={'ZZZ', 'ZZY'})
        self.assertEqual(len(third.plans), 1)
        self.assertEqual(third.meta.query_count, 0)
        limited = self.planner(self.pair(), max_queries=1)
        result = limited.search(city, now=NOW, origin_codes={'AAA', 'AAB'},
                                destination_codes={'ZZZ', 'ZZY'})
        self.assertEqual(result.meta.query_count, 1)
        self.assertEqual(len(limited.gateway.calls), 1)
        self.assertIn('query_limit', result.meta.truncation_reasons)
        expired = self.planner(self.pair(), max_seconds=0)
        result = expired.search(city, now=NOW, origin_codes={'AAA', 'AAB'},
                                destination_codes={'ZZZ', 'ZZY'})
        self.assertEqual(expired.gateway.calls, [])
        self.assertIn('time_limit', result.meta.truncation_reasons)

    def test_planner_resolves_city_dictionary_when_no_scope_sets_passed(self):
        service = StationService()
        service._parse_station_text('@a|起点|AAA|qidian|qd|1|1|始发城市|||'
            '@aa|起点南|AAB|qidiannan|qdn|2|1|始发城市|||'
            '@z|终点|ZZZ|zhongdian|zd|3|2|终到城市|||'
            '@zz|终点南|ZZY|zhongdiannan|zdn|4|2|终到城市|||')
        planner = self.planner(self.pair())
        with patch('app.services.transfer_planner.station_service', service):
            result = planner.search(self.request(from_scope='city', to_scope='city'), now=NOW)
        self.assertEqual(len(result.plans), 1)


if __name__ == '__main__':
    unittest.main()
