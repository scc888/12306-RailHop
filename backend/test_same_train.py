"""Regression coverage for fully ticketed continuation on one physical train."""
import unittest
from unittest.mock import Mock, patch

from app.models.schemas import TrainSeatInfo, TrainStopInfo, TrainTicketInfo
from app.services.client_12306 import RailwayQueryError
from app.services.smart_planner import SmartRoutePlanner


def ticket(a='AAA', b='CCC', start='23:00', arrive='03:00', duration='04:00', **changes):
    values = dict(train_no='physical-1', train_code='K1', run_date='20261010',
                  start_station_name='甲', end_station_name='丙', from_station_name=a,
                  to_station_name=b, from_station_telecode=a, to_station_telecode=b,
                  start_time=start, arrive_time=arrive, duration=duration,
                  seats=TrainSeatInfo(yw='有', yz='2'), prices={'yw': '¥12.30', 'yz': '¥8'})
    values.update(changes)
    return TrainTicketInfo(**values)


def stop(n, name, arrive, start, dwell='2'):
    return TrainStopInfo(station_no=str(n), station_name=name, arrive_time=arrive,
                         start_time=start, stopover_time=dwell)


class SameTrainTests(unittest.TestCase):
    def setUp(self):
        self.stops = [stop(1, '甲', '--', '23:00'), stop(2, '乙', '00:58', '01:00'),
                      stop(3, '丙', '03:00', '--')]
        self.anchor = ticket(seats=TrainSeatInfo())
        self.first = ticket('AAA', 'BBB', '23:00', '00:58', '01:58')
        self.second = ticket('BBB', 'CCC', '01:00', '03:00', '02:00', train_code='K2')
        self.data = {('2026-10-10', 'AAA', 'CCC'): [self.anchor],
                     ('2026-10-10', 'AAA', 'BBB'): [self.first],
                     ('2026-10-11', 'BBB', 'CCC'): [self.second]}
        self.client = Mock()
        self.client.query_train_stops.side_effect = lambda *args, **kwargs: self.stops
        self.client.query_train_stops_strict.side_effect = lambda *args, **kwargs: self.stops
        self.client.query_tickets_strict.side_effect = lambda day, a, b, **kwargs: self.data.get((day, a, b), [])
        self.stations = Mock()
        self.stations.get_code.side_effect = {'甲': 'AAA', '乙': 'BBB', '丙': 'CCC'}.get
        self.stations.get_name.side_effect = {'AAA': '甲', 'BBB': '乙', 'CCC': '丙'}.get
        self.client_patch = patch('app.services.smart_planner.client_12306', self.client)
        self.station_patch = patch('app.services.smart_planner.station_service', self.stations)
        self.client_patch.start()
        self.station_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.addCleanup(self.station_patch.stop)
        self.planner = SmartRoutePlanner()

    def search(self, **kwargs):
        return self.planner.calculate_with_meta('2026-10-10', 'K1', 'physical-1', 'AAA', 'CCC', **kwargs)

    def test_midnight_identity_seat_choices_and_exact_prices(self):
        result = self.search()
        self.assertEqual(result['meta']['status'], 'complete')
        self.assertEqual(len(result['plans']), 1)
        plan = result['plans'][0]
        self.assertEqual(plan.plan_type, 2)
        self.assertEqual(plan.total_minutes, 240)
        self.assertEqual(plan.total_price_fen, 2460)
        self.assertEqual(plan.known_price_fen, 2460)
        self.assertEqual(plan.segments[1].train_code, 'K2')
        self.assertEqual(plan.segments[1].departure_at.isoformat(), '2026-10-11T01:00:00+08:00')
        self.assertEqual({s.code for s in plan.segments[0].seats}, {'yw', 'yz'})
        self.assertTrue(all(not s.is_extension for s in plan.segments))
        self.assertTrue(all(c.kwargs['timeout_seconds'] <= 15 for c in self.client.query_tickets_strict.call_args_list))

    def test_multiday_date_comes_from_prefix_duration(self):
        self.anchor.duration = '52:00'
        self.first.duration = '49:58'
        self.data[('2026-10-13', 'BBB', 'CCC')] = self.data.pop(('2026-10-11', 'BBB', 'CCC'))
        plans = self.search()['plans']
        self.assertEqual(plans[0].segments[1].departure_at.isoformat(), '2026-10-13T01:00:00+08:00')
        self.assertEqual(plans[0].total_minutes, 3120)

    def test_rejects_identity_run_date_actual_station_and_time_mismatch(self):
        for field, bad in [('train_no', 'other'), ('run_date', '20261011'),
                           ('run_date', None), ('from_station_telecode', 'AAB'),
                           ('start_time', '01:01'), ('duration', '26:00')]:
            with self.subTest(field=field, bad=bad):
                changed = self.second.model_copy(update={field: bad})
                self.data[('2026-10-11', 'BBB', 'CCC')] = [changed]
                self.assertEqual(self.search()['plans'], [])

    def test_requires_available_ticket_on_every_segment(self):
        for seat in ['0', '候补', '无', '--', '-1', '未开售']:
            with self.subTest(seat=seat):
                self.second.seats = TrainSeatInfo(yw=seat)
                self.assertEqual(self.search()['plans'], [])
        self.second.seats = TrainSeatInfo(yw='有')
        self.second.can_buy = False
        self.assertEqual(self.search()['plans'], [])
        self.second.can_buy = True
        self.assertEqual(self.search(allowed_seats=['ze'])['plans'], [])

    def test_unknown_price_is_not_zero_and_anchor_is_reused(self):
        self.second.prices = {}
        result = self.search(anchor_ticket=self.anchor)
        self.assertIsNone(result['plans'][0].total_price_fen)
        self.assertEqual(result['plans'][0].known_price_fen, 1230)
        self.assertFalse(any(call.args[:3] == ('2026-10-10', 'AAA', 'CCC')
                             for call in self.client.query_tickets_strict.call_args_list))

    def test_missing_or_ambiguous_station_never_falls_back(self):
        for code in [None, 'AAA']:
            with self.subTest(code=code):
                self.stations.get_code.side_effect = {'甲': 'AAA', '乙': code, '丙': 'CCC'}.get
                self.assertEqual(self.search()['plans'], [])

    def test_upstream_failure_is_reported_and_no_short_extension_is_emitted(self):
        self.client.query_tickets_strict.side_effect = RailwayQueryError('上游失败')
        result = self.search()
        self.assertEqual(result['plans'], [])
        self.assertEqual(result['meta']['status'], 'upstream_error')
        self.assertTrue(result['meta']['failed_queries'])

    def test_query_and_time_budgets_are_reported(self):
        result = self.search(max_queries=1)
        self.assertEqual(result['plans'], [])
        self.assertEqual(result['meta']['query_count'], 1)
        self.assertTrue(result['meta']['truncated'])
        self.assertEqual(result['meta']['status'], 'partial')
        self.client.reset_mock()
        result = self.search(budget_seconds=0)
        self.assertEqual(result['plans'], [])
        self.assertEqual(result['meta']['query_count'], 0)
        self.assertTrue(result['meta']['truncated'])

    def test_elapsed_network_call_stops_subsequent_requests(self):
        clock = [0]
        def delayed(day, a, b, **kwargs):
            clock[0] += 10
            return self.data.get((day, a, b), [])
        self.client.query_tickets_strict.side_effect = delayed
        with patch('app.services.smart_planner.time.monotonic', side_effect=lambda: clock[0]):
            result = self.search(budget_seconds=5)
        self.assertEqual(result['plans'], [])
        self.assertEqual(result['meta']['query_count'], 1)
        self.assertTrue(result['meta']['truncated'])
        self.client.query_train_stops_strict.assert_not_called()

    def test_three_segments_reuse_prefix_cache_and_unsold_prefix_for_timing(self):
        self.stops.insert(2, stop(3, '丁', '01:58', '02:00'))
        self.stations.get_code.side_effect = {'甲': 'AAA', '乙': 'BBB', '丁': 'DDD', '丙': 'CCC'}.get
        self.data[('2026-10-11', 'BBB', 'CCC')] = []
        self.data[('2026-10-10', 'AAA', 'DDD')] = [ticket('AAA', 'DDD', '23:00', '01:58', '02:58', seats=TrainSeatInfo())]
        self.data[('2026-10-11', 'BBB', 'DDD')] = [ticket('BBB', 'DDD', '01:00', '01:58', '00:58')]
        self.data[('2026-10-11', 'DDD', 'CCC')] = [ticket('DDD', 'CCC', '02:00', '03:00', '01:00')]
        plans = self.search(max_tickets=3)['plans']
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].ticket_count, 3)
        queried = [call.args for call in self.client.query_tickets_strict.call_args_list]
        self.assertEqual(len(queried), len(set(queried)))

    def test_missing_dwell_or_anchor_identity_never_guesses(self):
        self.stops[1].stopover_time = '--'
        self.assertEqual(self.search()['plans'], [])
        self.assertEqual(self.search()['meta']['status'], 'partial')
        self.stops[1].stopover_time = '2'
        for bad in [None, '20261011', '2026101']:
            with self.subTest(run_date=bad):
                self.anchor.run_date = bad
                self.assertEqual(self.search()['plans'], [])

    def test_conditional_short_ticket_is_separate_and_never_promises_full_fare(self):
        self.second.seats = TrainSeatInfo()
        found = self.search(include_short_fallback=True, short_fallback_only=True)
        self.assertEqual(found['plans'], [])
        self.assertEqual(len(found['short_fallbacks']), 1)
        option = found['short_fallbacks'][0]
        self.assertEqual(option.ticketed_leg.to_station, 'BBB')
        self.assertEqual(option.destination_station, 'CCC')
        self.assertEqual(option.ticketed_leg.arrival_at.isoformat(), '2026-10-11T00:58:00+08:00')
        self.assertEqual(option.scheduled_arrival_at.isoformat(), '2026-10-11T03:00:00+08:00')
        self.assertIsNone(option.total_price_fen)
        self.assertIsNone(option.extension_price_fen)
        self.assertEqual(option.known_price_fen, 800)
        self.assertIn('原票到站前', option.conditions)
        self.assertIn('下车', option.conditions)
        self.assertIn('不承诺', option.conditions)
        self.first.can_buy = False
        self.assertEqual(self.search(include_short_fallback=True, short_fallback_only=True)['short_fallbacks'], [])

    def test_malformed_same_running_train_segment_is_unverified_not_empty(self):
        self.second.start_time = '01:01'
        found = self.search()
        self.assertEqual(found['plans'], [])
        self.assertEqual(found['meta']['status'], 'partial')
        self.assertTrue(found['meta']['notices'])
    def test_legacy_list_entrypoint_and_no_short_or_long_ticket_plans(self):
        self.data[('2026-10-11', 'BBB', 'CCC')] = []
        self.assertEqual(self.planner.calculate_smart_plans('2026-10-10', 'K1', 'physical-1', 'AAA', 'CCC'), [])


if __name__ == '__main__':
    unittest.main()
