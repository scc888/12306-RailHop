import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models.journey_schemas import JourneyQueryRequest
from app.models.schemas import TrainSeatInfo
from app.models.transfer_schemas import TransferSearchResult, TransferSearchMeta
from app.services.journey_service import JourneyService
from app.services.station_service import StationService
from app.services.client_12306 import RailwayQueryError
from app.services.smart_planner import SmartRoutePlanner
from app.services.transfer_ticket_gateway import CST
from test_same_train import ticket, stop

NOW = datetime(2026, 10, 10, 7, tzinfo=CST)


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.stations = StationService()
        self.stations._parse_station_text('@a|甲|AAA|jia|j|1|1|甲城|||'
            '@aa|甲南|AAB|jianan|jn|2|1|甲城|||'
            '@c|丙|CCC|bing|b|3|2|丙城|||')
        self.client = Mock()
        self.anchor = ticket(start='08:00', arrive='12:00', duration='04:00')
        self.client.query_tickets_strict.return_value = [self.anchor]
        self.same = Mock()
        self.same._times = SmartRoutePlanner._times
        self.same.calculate_with_meta.return_value = {'plans': [], 'meta': {'status':'complete','query_count':2,'notices':[]}}
        self.transfer = Mock()
        self.transfer.limits = {'max_seconds':45}
        self.transfer.search.return_value = TransferSearchResult(plans=[], meta=TransferSearchMeta(
            queried_at=NOW, candidate_station_codes=[], query_count=2))
        self.service = JourneyService(self.client, self.stations, self.same, self.transfer)

    def request(self, **kwargs):
        return JourneyQueryRequest(from_station='AAA', to_station='CCC', train_date='2026-10-10', **kwargs)

    def test_city_name_without_namesake_station_is_searchable(self):
        self.assertEqual({s.telecode for s in self.stations.search('甲城')},{'AAA','AAB'})

    def test_conditional_fallback_opt_in_and_full_routes_suppress_it(self):
        self.anchor.seats = TrainSeatInfo()
        result = self.service.search(self.request(include_short_fallback=True),now=NOW)
        self.assertNotEqual(result.short_fallback.meta.status,'skipped')
        self.assertTrue(any(c.kwargs.get('short_fallback_only') for c in self.same.calculate_with_meta.call_args_list))
        self.assertLessEqual(self.transfer.search.call_args.kwargs['budget_seconds'],52)
        self.anchor.seats=TrainSeatInfo(yw='有')
        self.same.reset_mock()
        result=self.service.search(self.request(include_short_fallback=True),now=NOW)
        self.assertEqual(result.short_fallback.options,[])
        self.assertEqual(result.short_fallback.meta.status,'skipped')
        self.same.calculate_with_meta.assert_not_called()

    def test_real_same_train_conversion_and_conditional_fallback_are_separate(self):
        from app.services.transfer_planner import TransferPlanner
        from app.services.transfer_station_service import TransferStationService
        from test_transfer_planner import Samples, station
        self.stations._parse_station_text('@a|甲|AAA|jia|j|1|1|甲城|||'
            '@b|乙|BBB|yi|y|2|2|乙城|||@c|丙|CCC|bing|b|3|3|丙城|||')
        anchor=ticket(seats=TrainSeatInfo())
        first=ticket('AAA','BBB','23:00','00:58','01:58')
        second=ticket('BBB','CCC','01:00','03:00','02:00',seats=TrainSeatInfo())
        data={('2026-10-10','AAA','CCC'):[anchor],('2026-10-10','AAA','BBB'):[first],('2026-10-11','BBB','CCC'):[second]}
        self.client.query_tickets_strict.side_effect=lambda day,a,b,**kwargs:data.get((day,a,b),[])
        self.client.query_train_stops_strict.return_value=[stop(1,'甲','--','23:00'),stop(2,'乙','00:58','01:00'),stop(3,'丙','03:00','--')]
        service=JourneyService(self.client,self.stations,SmartRoutePlanner(),
            TransferPlanner(TransferStationService(entries=[station('BBB')]),Samples(),sleep_fn=lambda _:None))
        with patch('app.services.smart_planner.client_12306',self.client),patch('app.services.smart_planner.station_service',self.stations):
            result=service.search(self.request(mode='all',include_short_fallback=True),now=NOW)
            self.assertFalse(any(g.plans for g in (result.direct,result.same_train,result.transfer)))
            self.assertEqual(len(result.short_fallback.options),1)
            self.assertIsNone(result.short_fallback.options[0].total_price_fen)
            self.assertEqual(result.short_fallback.options[0].ticketed_leg.to_station,'BBB')
            second.seats=TrainSeatInfo(yw='有')
            result=service.search(self.request(mode='all',include_short_fallback=True),now=NOW)
            self.assertEqual(len(result.same_train.plans),1)
            self.assertEqual(result.same_train.plans[0].total_price_fen,2030)
            self.assertEqual(result.same_train.plans[0].legs[1].departure_at.isoformat(),'2026-10-11T01:00:00+08:00')
            self.assertEqual(result.short_fallback.options,[])

    def test_auto_returns_direct_and_skips_alternatives_with_explicit_status(self):
        result = self.service.search(self.request(), now=NOW)
        self.assertEqual(len(result.direct.plans),1)
        self.assertEqual(result.direct.plans[0].kind,'direct')
        self.assertEqual(result.direct.plans[0].total_price_fen,800)
        self.assertEqual(result.same_train.meta.status,'skipped')
        self.assertEqual(result.transfer.meta.status,'skipped')
        self.same.calculate_with_meta.assert_not_called()
        self.transfer.search.assert_not_called()

    def test_train_list_keeps_sold_out_trains_and_exposes_stable_selection(self):
        self.anchor.seats = TrainSeatInfo()
        result = self.service.search(self.request(mode='direct'), now=NOW)
        self.assertEqual(result.direct.plans, [])
        self.assertEqual(len(result.trains), 1)
        row = result.trains[0]
        self.assertEqual(row.train_code, 'K1')
        self.assertEqual(row.selection.train_no, self.anchor.train_no)
        self.assertEqual(row.selection.run_date.isoformat(), '2026-10-10')
        self.assertIn('run_date', row.model_dump(mode='json')['selection'])

    def test_selected_train_bypasses_four_candidate_limit_and_anchors_transfer(self):
        self.anchor.seats = TrainSeatInfo()
        self.client.query_tickets_strict.return_value = [
            self.anchor.model_copy(update={'train_no': str(i), 'train_code': f'K{i+1}'}) for i in range(7)]
        listing = self.service.search(self.request(mode='direct'), now=NOW)
        selection = listing.trains[-1].selection
        result = self.service.search(self.request(mode='all', selected_train=selection), now=NOW)
        self.same.calculate_with_meta.assert_called_once()
        self.assertEqual(self.same.calculate_with_meta.call_args.kwargs['anchor_ticket'].train_no, '6')
        anchor = self.transfer.search.call_args.kwargs['first_train']
        self.assertEqual(anchor.selection, selection)
        self.assertEqual(result.selected_train, selection)

    def test_stale_selected_train_and_failed_refresh_never_search_other_trains(self):
        selection = self.service.search(self.request(mode='direct'), now=NOW).trains[0].selection
        self.client.query_tickets_strict.return_value = [self.anchor.model_copy(update={'train_no':'other'})]
        with self.assertRaisesRegex(ValueError, '所选车次'):
            self.service.search(self.request(mode='all', selected_train=selection), now=NOW)
        self.transfer.search.assert_not_called()
        self.client.query_tickets_strict.side_effect = RailwayQueryError('failed')
        result = self.service.search(self.request(mode='all', selected_train=selection), now=NOW)
        self.assertEqual(result.transfer.meta.status, 'upstream_error')
        self.transfer.search.assert_not_called()

    def test_unverified_train_remains_visible_without_selectable_identity(self):
        self.anchor.run_date = None
        result = self.service.search(self.request(mode='direct'), now=NOW)
        self.assertEqual(len(result.trains), 1)
        self.assertIsNone(result.trains[0].selection)

    def test_auto_no_preferred_direct_seat_checks_both_alternatives(self):
        self.anchor.seats = TrainSeatInfo()
        result = self.service.search(self.request(), now=NOW)
        self.assertEqual(result.direct.plans,[])
        self.same.calculate_with_meta.assert_called_once()
        self.assertIs(self.same.calculate_with_meta.call_args.kwargs['anchor_ticket'],self.anchor)
        self.transfer.search.assert_called_once()
        self.assertEqual(result.same_train.meta.status,'partial')  # Limited city-query coverage.

    def test_city_actual_origin_allowed_but_single_station_excludes_it(self):
        self.anchor.from_station_telecode='AAB'
        result = self.service.search(self.request(mode='direct'),now=NOW)
        self.assertEqual(result.direct.plans[0].legs[0].from_station,'AAB')
        self.assertEqual(result.direct.meta.status,'partial')
        result = self.service.search(self.request(mode='direct',from_scope='station'),now=NOW)
        self.assertEqual(result.direct.plans,[])

    def test_train_type_and_past_departure_filter(self):
        self.assertEqual(self.service.search(self.request(mode='direct',train_type='high_speed'),now=NOW).direct.plans,[])
        late=NOW.replace(hour=9)
        self.assertEqual(self.service.search(self.request(mode='direct'),now=late).direct.plans,[])

    def test_failed_direct_is_not_confirmed_no_ticket_and_transfer_can_continue(self):
        failure=RailwayQueryError('private-error-value')
        failure.diagnostic_id='diagnostic-123'
        self.client.query_tickets_strict.side_effect=failure
        with self.assertLogs('app.services.journey_service',level='WARNING') as captured:
            result=self.service.search(self.request(),now=NOW)
        self.assertIn('diagnostic_id=diagnostic-123',captured.output[0])
        self.assertNotIn('private-error-value','\n'.join(captured.output))
        self.assertEqual(result.direct.meta.status,'upstream_error')
        self.assertEqual(result.same_train.meta.status,'upstream_error')
        self.transfer.search.assert_called_once()

    def test_dates_unknown_station_and_same_city_validate_before_network(self):
        for changes in [dict(train_date='2026-10-09'),dict(train_date='2026-10-25'),dict(from_station='XXX'),dict(to_station='AAB')]:
            values=self.request().model_dump() | changes
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.service.search(JourneyQueryRequest(**values),now=NOW)
        self.client.query_tickets_strict.assert_not_called()

    def test_same_train_candidate_limit_and_shared_time_budget_disclosed(self):
        self.anchor.seats=TrainSeatInfo()
        self.client.query_tickets_strict.return_value=[self.anchor.model_copy(update={'train_no':str(i)}) for i in range(7)]
        result=self.service.search(self.request(mode='same_train'),now=NOW)
        self.assertEqual(self.same.calculate_with_meta.call_count,4)
        self.assertEqual(result.same_train.meta.status,'partial')
        self.assertTrue(any('4' in n for n in result.same_train.meta.notices))
        for call in self.same.calculate_with_meta.call_args_list:
            self.assertLessEqual(call.kwargs['budget_seconds'],16)
            self.assertLessEqual(call.kwargs['max_queries'],40)

    def test_api_validation_busy_and_release(self):
        from app.api.journey_routes import get_journey_service
        from app.api.transfer_routes import transfer_lock
        app.dependency_overrides[get_journey_service]=lambda:self.service
        original=self.service.search
        self.service.search=lambda req:original(req,now=NOW)
        client=TestClient(app)
        body=self.request().model_dump(mode='json')
        try:
            self.assertEqual(client.post('/api/journeys/query',json=body).status_code,200)
            self.assertEqual(client.post('/api/journeys/query',json=body|{'mode':'bad'}).status_code,422)
            self.assertEqual(client.post('/api/journeys/query',json=body|{'train_date':'2026-10-25'}).status_code,400)
            transfer_lock.acquire()
            try:
                self.assertEqual(client.post('/api/journeys/query',json=body).status_code,429)
            finally:
                transfer_lock.release()
            self.assertFalse(transfer_lock.locked())
        finally:
            app.dependency_overrides.clear()

    def test_same_train_mode_does_not_display_direct_results(self):
        result=self.service.search(self.request(mode='same_train'),now=NOW)
        self.assertEqual(result.direct.plans,[])
        self.assertEqual(result.direct.meta.status,'skipped')
        self.same.calculate_with_meta.assert_called_once()

    def test_total_deadline_stops_later_stage_after_slow_prior_stage(self):
        clock=[0]
        def slow_same(*args,**kwargs):
            clock[0]=61
            return {'plans':[],'meta':{'status':'partial','notices':['查询时间达到上限'],'query_count':1}}
        self.same.calculate_with_meta.side_effect=slow_same
        with patch('app.services.journey_service.time.monotonic',side_effect=lambda:clock[0]):
            result=self.service.search(self.request(mode='all'),now=NOW)
        self.transfer.search.assert_not_called()
        self.assertEqual(result.transfer.meta.status,'partial')


if __name__=='__main__':
    unittest.main()
