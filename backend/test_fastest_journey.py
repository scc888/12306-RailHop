"""Fastest-query contracts and explicit station choices, with no railway network."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.transfer_schemas import TransferQueryRequest
from app.services.client_12306 import RailwayQueryError
from app.services.station_service import StationService
import test_journey as fixtures
from test_same_train import ticket


class StationScopeTests(unittest.TestCase):
    def setUp(self):
        self.stations = StationService()
        self.stations._parse_station_text(
            '@s|上海|SHH|shanghai|sh|1|sh|上海'
            '@h|上海虹桥|AOH|shanghaihongqiao|shhq|2|sh|上海'
            '@q|练塘|LTU|liantang|lt|3|sh|上海'
            '@z|驻马店|ZDN|zhumadian|zmd|4|zmd|驻马店'
            '@x|驻马店西|ZLN|zhumadianxi|zmdx|5|zmd|驻马店'
            '@a|确山|QSN|queshan|qs|6|zmd|驻马店'
            '@w|武汉|WHN|wuhan|wh|7|wh|武汉'
            '@k|汉口|HKN|hankou|hk|8|wh|武汉'
            '@c|武昌|WCN|wuchang|wc|9|wh|武汉'
            '@f|武汉示例|XXX|example|e|10|other|其他城市')

    def test_default_choices_do_not_include_county_stations_but_allow_explicit_choice(self):
        result = self.stations.station_scope('ZDN')
        self.assertEqual(set(result['default_station_codes']), {'ZDN', 'ZLN'})
        self.assertEqual({s.telecode for s in result['stations']}, {'ZDN', 'ZLN', 'QSN'})
        self.assertEqual(self.stations.resolve_scope('ZDN', 'city', ['ZDN', 'QSN']), {'ZDN', 'QSN'})
        self.assertEqual(set(self.stations.station_scope('WHN')['default_station_codes']), {'WHN', 'HKN', 'WCN'})

    def test_explicit_station_scope_never_expands_or_accepts_another_city(self):
        self.assertEqual(self.stations.resolve_scope('SHH', 'station', ['SHH']), {'SHH'})
        for scope, selected in [('city', ['SHH', 'ZDN']), ('station', ['SHH', 'AOH']), ('city', ['AOH'])]:
            with self.subTest(scope=scope, selected=selected), self.assertRaises(ValueError):
                self.stations.resolve_scope('SHH', scope, selected)

    def test_scope_api_exposes_all_choices_and_safe_defaults(self):
        with patch('app.api.routes.station_service', self.stations):
            client = TestClient(app)
            response = client.get('/api/stations/scope?station_code=ZDN')
            self.assertEqual(response.status_code, 200)
            data = response.json()['data']
            self.assertEqual(data['city_name'], '驻马店')
            self.assertEqual(set(data['default_station_codes']), {'ZDN', 'ZLN'})
            self.assertEqual({s['telecode'] for s in data['stations']}, {'ZDN', 'ZLN', 'QSN'})
            self.assertEqual(client.get('/api/stations/scope?station_code=BAD').status_code, 400)


class FastestJourneyTests(unittest.TestCase):
    setUp = fixtures.JourneyTests.setUp
    request = fixtures.JourneyTests.request

    def test_maximum_transfer_contract_accepts_two_required_stops_without_changing_legacy_exact(self):
        request = self.request(max_transfers=2, ordered_via_stations=['BBB', 'DDD'])
        self.assertEqual(request.max_transfers, 2)
        self.assertEqual(self.request(transfer_count=2).transfer_count, 2)
        self.assertIsNone(self.request(transfer_count=2).max_transfers)
        with self.assertRaises(ValidationError):
            self.request(max_transfers=1, ordered_via_stations=['BBB', 'DDD'])

    def test_empty_or_malformed_selection_is_rejected_before_query(self):
        for selected in [[], ['bad'], ['AAA', 'NOT_A_CODE']]:
            with self.subTest(selected=selected), self.assertRaises(ValidationError):
                self.request(from_station_codes=selected)

    def test_fastest_has_direct_comparison_and_respects_explicit_station_selection(self):
        result = self.service.search(self.request(mode='fastest', from_station_codes=['AAA'],
            to_station_codes=['CCC']), now=fixtures.NOW)
        self.assertEqual(len(result.direct.plans), 1)
        self.assertEqual(result.same_train.meta.status, 'skipped')
        self.assertEqual(result.scope['mode'], 'fastest')
        self.assertEqual(result.scope['origin_station_codes'], ['AAA'])
        self.assertEqual(result.scope['destination_station_codes'], ['CCC'])
        self.same.calculate_with_meta.assert_not_called()
        self.assertEqual(self.transfer.search.call_args.kwargs['origin_codes'], {'AAA'})
        self.assertEqual(self.transfer.search.call_args.args[0].sort_by, 'duration')

    def test_fastest_forces_duration_and_rejects_binding_to_one_train(self):
        request = self.request(mode='fastest', sort_by='price')
        self.assertEqual(request.sort_by, 'duration')
        with self.assertRaises(ValidationError):
            self.request(mode='fastest', selected_train=dict(train_no='train', run_date='2026-10-10',
                from_station='AAA', to_station='CCC', departure_at='2026-10-10T08:00:00+08:00'))

    def test_fastest_reuses_refreshed_direct_candidates_for_discovery(self):
        result = self.service.search(self.request(mode='fastest'),now=fixtures.NOW)
        supplied = self.transfer.search.call_args.kwargs.get('candidate_tickets')
        self.assertIsNotNone(supplied)
        self.assertEqual([t.train_no for t in supplied],['physical-1'])
        self.assertEqual(len(result.direct.plans),1)

    def test_direct_comparison_queries_selected_actual_station_pairs(self):
        self.client.query_tickets_strict.side_effect = lambda day, a, b, **kw: [ticket(a, b)]
        result = self.service.search(self.request(mode='fastest', from_station_codes=['AAA', 'AAB'],
            to_station_codes=['CCC']), now=fixtures.NOW)
        self.assertEqual({p.legs[0].from_station for p in result.direct.plans}, {'AAA', 'AAB'})
        self.assertEqual(result.direct.meta.query_count, 2)

    def test_failed_direct_comparison_does_not_prevent_transfer_search(self):
        self.client.query_tickets_strict.side_effect = RailwayQueryError('unavailable')
        result = self.service.search(self.request(mode='fastest'), now=fixtures.NOW)
        self.assertEqual(result.direct.meta.status, 'upstream_error')
        self.assertNotEqual(result.transfer.meta.status, 'skipped')
        self.transfer.search.assert_called_once()

    def test_cross_city_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.search(self.request(from_station_codes=['AAA', 'CCC']), now=fixtures.NOW)

    def test_selected_actual_pair_failure_is_not_reported_as_a_stale_train(self):
        def query(day, a, b, **kwargs):
            if a == 'AAB':
                raise RailwayQueryError('selected pair unavailable')
            return []
        self.client.query_tickets_strict.side_effect = query
        selected = dict(train_no='physical-1',run_date='2026-10-10',from_station='AAB',
            to_station='CCC',departure_at='2026-10-10T08:00:00+08:00')
        result = self.service.search(self.request(mode='all',from_station_codes=['AAA','AAB'],
            to_station_codes=['CCC'],selected_train=selected),now=fixtures.NOW)
        self.assertEqual(result.transfer.meta.status,'upstream_error')
        self.assertEqual(result.same_train.meta.status,'upstream_error')
        self.assertTrue(any('刷新' in n for n in result.transfer.meta.notices))
        self.transfer.search.assert_not_called()

    def test_incomplete_direct_discovery_marks_dependent_empty_groups_partial(self):
        def query(day, a, b, **kwargs):
            if a == 'AAB':
                raise RailwayQueryError('one pair unavailable')
            return []
        self.client.query_tickets_strict.side_effect = query
        result = self.service.search(self.request(mode='all',from_station_codes=['AAA','AAB'],
            to_station_codes=['CCC'],include_short_fallback=True),now=fixtures.NOW)
        self.assertEqual(result.direct.meta.status,'partial')
        self.assertEqual(result.same_train.meta.status,'partial')
        self.assertEqual(result.short_fallback.meta.status,'partial')
        self.assertTrue(any('失败' in n for n in result.same_train.meta.notices))
        self.assertTrue(any('失败' in n for n in result.short_fallback.meta.notices))


if __name__ == '__main__':
    unittest.main()
