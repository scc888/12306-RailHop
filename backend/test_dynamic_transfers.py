"""Regression coverage for transfers outside the convenience-reference catalogue."""
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from app.models.schemas import TrainStopInfo
from app.models.transfer_schemas import TransferQueryRequest
from app.services.station_service import StationService
from app.services.transfer_station_service import TransferStationService
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_ticket_gateway import TransferTicketGateway
from app.services.transfer_ticket_gateway import CST
from app.services.client_12306 import Ticket12306Client, RailwayQueryError
from test_transfer_planner import NOW, Samples, leg
from test_transfer_gateway import row


def directory():
    result = StationService()
    result._parse_station_text('@a|Start|AAA|start|s|0|a|上海@b|Middle|BBB|middle|m|0|b|南京'
                               '@c|Probe|CCC|probe|p|0|c|济南@z|End|ZZZ|end|e|0|z|北京')
    return result


def ticket(a, b, train, start='08:00', arrive='09:00', seat='有'):
    fields = row(start, arrive, '01:00', seat=seat).split('|')
    fields[2:8] = [train, train, a, b, a, b]
    return Ticket12306Client()._parse_ticket_results(['|'.join(fields)], {})[0]


class DynamicTransferTests(unittest.TestCase):
    def test_reused_direct_candidates_prioritize_fast_train_across_actual_endpoints(self):
        stations = directory()
        stations._parse_station_text('@a|Start|AAA|start|s|0|a|Start'
            '@ab|StartSouth|AAB|south|s|0|a|Start@b|Middle|BBB|middle|m|0|b|Middle'
            '@z|End|ZZZ|end|e|0|z|End@zy|EndSouth|ZZY|south|s|0|z|End')
        slow = [ticket('AAA','ZZZ',f'K{i}',start='08:00',arrive='20:00') for i in range(8)]
        for item in slow:
            item.duration = '12:00'
        fast = ticket('AAB','ZZY','G99',start='10:00',arrive='12:00')
        fast.duration = '02:00'
        outside_scope = ticket('XXX','ZZZ','G100')
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(return_value=[])
        inspected = []
        def stops(train,*args,**kwargs):
            inspected.append(train)
            return [TrainStopInfo(station_no=str(i),station_name=name,arrive_time='--',
                start_time='--',stopover_time='--') for i,name in enumerate(['StartSouth','Middle','EndSouth'],1)]
        railway.query_train_stops_strict = Mock(side_effect=stops)
        request = TransferQueryRequest(from_station='AAA',to_station='ZZZ',train_date='2026-10-10',
            from_scope='city',to_scope='city',from_station_codes=['AAA','AAB'],to_station_codes=['ZZZ','ZZY'])
        result = TransferPlanner(TransferStationService(entries=[],directory=stations),
            TransferTicketGateway(railway),limits={'request_interval':0,'discovery_probes':0,
                'discovery_trains':1,'max_queries':1}).search(request,now=NOW,
                    candidate_tickets=slow+[fast,outside_scope])
        self.assertEqual(result.meta.candidate_station_codes,['BBB'])
        self.assertEqual(inspected,['G99'])
        self.assertEqual(railway.query_tickets_strict.call_count,0)
        self.assertEqual(result.meta.query_count,1)
        self.assertIn('query_limit',result.meta.truncation_reasons)

    def test_empty_reused_direct_candidates_still_probe_directions_without_requery(self):
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(return_value=[])
        result = TransferPlanner(self.stations(),TransferTicketGateway(railway),limits={
            'request_interval':0,'discovery_probes':1,'max_queries':2}).search(
                self.request(ordered_via_stations=[]),now=NOW,candidate_tickets=[])
        pairs = [(call.args[1],call.args[2]) for call in railway.query_tickets_strict.call_args_list]
        self.assertEqual(pairs,[('AAA','BBB'),('BBB','ZZZ')])
        self.assertIn('direction_probe',result.meta.candidate_sources['BBB'])
        self.assertEqual(result.meta.query_count,2)

    def test_discovery_queries_explicit_alternate_actual_endpoints(self):
        stations = directory()
        stations._parse_station_text('@a|Start|AAA|start|s|0|a|Start'
            '@ab|StartSouth|AAB|south|s|0|a|Start@b|Middle|BBB|middle|m|0|b|Middle'
            '@z|End|ZZZ|end|e|0|z|End@zy|EndSouth|ZZY|south|s|0|z|End')
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs:
            [ticket('AAB','ZZY','G1')] if (a,b)==('AAB','ZZY') else [])
        railway.query_train_stops_strict = Mock(return_value=[TrainStopInfo(station_no=str(i),
            station_name=name,arrive_time='--',start_time='--',stopover_time='--')
            for i,name in enumerate(['StartSouth','Middle','EndSouth'],1)])
        request = TransferQueryRequest(from_station='AAA',to_station='ZZZ',train_date='2026-10-10',
            from_scope='city',to_scope='city',from_station_codes=['AAA','AAB'],to_station_codes=['ZZZ','ZZY'])
        result = TransferPlanner(TransferStationService(entries=[],directory=stations),
            TransferTicketGateway(railway),limits={'request_interval':0,'discovery_probes':0}).search(request,now=NOW)
        self.assertEqual(result.meta.candidate_station_codes,['BBB'])

    def test_discovery_inspects_fast_timetabled_train_before_input_order(self):
        railway = Ticket12306Client()
        slow = ticket('AAA','ZZZ','G1',start='08:00',arrive='16:00')
        slow.duration = '08:00'
        fast = ticket('AAA','ZZZ','G2',start='10:00',arrive='12:00')
        fast.duration = '02:00'
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs:
            [slow,fast] if (a,b)==('AAA','ZZZ') else [])
        def stops(train,*args,**kwargs):
            names = ['Start', 'Middle' if train=='G1' else 'Probe', 'End']
            return [TrainStopInfo(station_no=str(i),station_name=name,arrive_time='--',
                start_time='--',stopover_time='--') for i,name in enumerate(names,1)]
        railway.query_train_stops_strict = Mock(side_effect=stops)
        result = TransferPlanner(self.stations(),TransferTicketGateway(railway),limits={
            'request_interval':0,'discovery_probes':0,'discovery_trains':1}).search(
                self.request(ordered_via_stations=[]),now=NOW)
        self.assertEqual(result.meta.candidate_station_codes,['CCC'])

    def test_candidate_cap_keeps_stops_from_distinct_train_routes(self):
        stations = directory()
        stations._parse_station_text('@a|Start|AAA|start|s|0|a|Start'
            '@b|FirstSlow|BBB|first|f|0|b|One@c|SecondSlow|BBC|second|s|0|c|Two'
            '@d|FastOther|YYY|other|o|0|d|Three@z|End|ZZZ|end|e|0|z|End')
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs:
            [ticket('AAA','ZZZ','G1'),ticket('AAA','ZZZ','G2')] if (a,b)==('AAA','ZZZ') else [])
        def stops(train,*args,**kwargs):
            names = ['Start','FirstSlow','SecondSlow','End'] if train=='G1' else ['Start','FastOther','End']
            return [TrainStopInfo(station_no=str(i),station_name=name,arrive_time='--',
                start_time='--',stopover_time='--') for i,name in enumerate(names,1)]
        railway.query_train_stops_strict = Mock(side_effect=stops)
        result = TransferPlanner(TransferStationService(entries=[],directory=stations),
            TransferTicketGateway(railway),limits={'request_interval':0,'discovery_probes':0,
                'max_candidates':2}).search(self.request(ordered_via_stations=[]),now=NOW)
        self.assertEqual(set(result.meta.candidate_station_codes), {'BBB','YYY'})

    def stations(self):
        return TransferStationService(entries=[], directory=directory())

    def request(self, **changes):
        return TransferQueryRequest(**(dict(from_station='AAA', to_station='ZZZ',
            train_date='2026-10-10', ordered_via_stations=['BBB']) | changes))

    def test_manual_station_outside_catalog_is_valid_but_unknown_code_is_not(self):
        stations = self.stations()
        reference = stations.validate_via(['BBB'])[0]
        self.assertEqual(reference.station_name, 'Middle')
        self.assertFalse(reference.convenient_transfer_confirmed)
        self.assertIsNone(reference.source_url)
        self.assertIsNone(reference.verified_at)
        with self.assertRaises(ValueError):
            stations.validate_via(['BAD'])

    def test_unknown_convenience_uses_sixty_minutes_and_preserves_personal_override(self):
        for departure, selected, count, minutes in [('09:59', None, 0, None),
                ('10:00', None, 1, 60), ('09:15', 15, 1, 15)]:
            with self.subTest(departure=departure, selected=selected):
                gateway = Samples([leg('AAA','BBB','2026-10-10T08:00','2026-10-10T09:00'),
                    leg('BBB','ZZZ',f'2026-10-10T{departure}','2026-10-10T11:00','G2')])
                planner = TransferPlanner(self.stations(), gateway, limits={'request_interval':0}, sleep_fn=lambda _:None)
                result = planner.search(self.request(min_transfer_minutes=selected), now=NOW)
                self.assertEqual(len(result.plans), count)
                if count:
                    connection = result.plans[0].connections[0]
                    self.assertEqual(connection.required_minutes, minutes)
                    self.assertFalse(connection.station.convenient_transfer_confirmed)
                    self.assertIsNone(connection.source_url)

    def test_unknown_station_can_connect_across_midnight(self):
        gateway = Samples([leg('AAA','BBB','2026-10-10T22:00','2026-10-10T23:30'),
                           leg('BBB','ZZZ','2026-10-11T00:30','2026-10-11T02:00','G2')])
        result = TransferPlanner(self.stations(), gateway, limits={'request_interval':0}).search(self.request(),now=NOW)
        self.assertEqual(len(result.plans),1)
        self.assertEqual(result.plans[0].connections[0].wait_minutes,60)

    def test_no_direct_train_still_finds_non_catalog_transfer(self):
        railway = Ticket12306Client()
        rows = {('AAA','CCC'):[ticket('AAA','CCC','G1')],
                ('AAA','BBB'):[ticket('AAA','BBB','G1')],
                ('BBB','ZZZ'):[ticket('BBB','ZZZ','G2',start='10:00',arrive='11:00')]}
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs: rows.get((a,b),[]))
        railway.query_train_stops_strict = Mock(return_value=[
            TrainStopInfo(station_no='01',station_name='Start',arrive_time='----',start_time='08:00',stopover_time='----'),
            TrainStopInfo(station_no='02',station_name='Middle',arrive_time='09:00',start_time='09:05',stopover_time='5'),
            TrainStopInfo(station_no='03',station_name='Probe',arrive_time='10:00',start_time='----',stopover_time='----')])
        planner = TransferPlanner(self.stations(),TransferTicketGateway(railway),
            limits={'request_interval':0,'horizon_hours':3},sleep_fn=lambda _:None)
        result = planner.search(self.request(ordered_via_stations=[]),now=NOW)
        self.assertEqual(len(result.plans),1)
        self.assertEqual(result.plans[0].connections[0].station.station_code,'BBB')
        self.assertIn('train_stops',result.meta.candidate_sources['BBB'])
        self.assertTrue(result.meta.truncated)
        self.assertIn('dynamic_discovery',result.meta.truncation_reasons)

    def test_selected_first_train_can_continue_to_a_second_transfer_outside_its_stops(self):
        from app.models.journey_schemas import JourneyTrain, SelectedTrain
        railway = Ticket12306Client()
        raw = ticket('AAA','ZZZ','G1',start='08:00',arrive='12:00')
        raw.duration = '04:00'
        anchor = JourneyTrain(**raw.model_dump(),id='selected',
            departure_at=datetime(2026,10,10,8,tzinfo=CST),arrival_at=datetime(2026,10,10,12,tzinfo=CST),
            selection=SelectedTrain(train_no='G1',run_date='2026-10-10',from_station='AAA',to_station='ZZZ',
                departure_at='2026-10-10T08:00:00+08:00'))
        rows = {('AAA','BBB'):[ticket('AAA','BBB','G1')],
            ('BBB','CCC'):[ticket('BBB','CCC','G2',start='10:00',arrive='11:00')],
            ('CCC','ZZZ'):[ticket('CCC','ZZZ','G3',start='12:00',arrive='13:00')]}
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs: rows.get((a,b),[]) if day=='2026-10-10' else [])
        railway.query_train_stops_strict = Mock(return_value=[TrainStopInfo(station_no=str(i),station_name=name,
            arrive_time='--',start_time='--',stopover_time='--') for i,name in enumerate(['Start','Middle','End'],1)])
        planner = TransferPlanner(self.stations(),TransferTicketGateway(railway),
            limits={'request_interval':0,'horizon_hours':6},sleep_fn=lambda _:None)
        result = planner.search(self.request(ordered_via_stations=[],transfer_count=2),now=NOW,first_train=anchor)
        self.assertEqual(len(result.plans),1)
        self.assertEqual(result.plans[0].legs[0].train_no,'G1')
        self.assertEqual([connection.station.station_code for connection in result.plans[0].connections],['BBB','CCC'])
        self.assertIn('direction_probe',result.meta.candidate_sources['CCC'])

    def test_discovery_failures_and_requests_share_the_planner_budget(self):
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(side_effect=RailwayQueryError('upstream unavailable'))
        planner = TransferPlanner(self.stations(),TransferTicketGateway(railway),
            limits={'request_interval':0,'max_queries':2},sleep_fn=lambda _:None)
        result = planner.search(self.request(ordered_via_stations=[]),now=NOW)
        self.assertLessEqual(railway.query_tickets_strict.call_count,2)
        self.assertEqual(result.meta.query_count,2)
        self.assertEqual(result.meta.status,'upstream_error')
        self.assertTrue(result.meta.failed_pairs)
        self.assertIn('query_limit',result.meta.truncation_reasons)

    def test_selected_train_stops_survive_candidate_cap_when_other_probes_have_many_stops(self):
        from app.models.journey_schemas import JourneyTrain, SelectedTrain
        codes = ['BA'+chr(65+i) for i in range(26)] + ['BBA','BBB','BBC','BBD','BBE','BBF','BBG']
        stations = StationService()
        stations._parse_station_text('@a|Start|AAA|start|s|0|a|Start' + ''.join(
            f'@s|Stop{code}|{code}|{code.lower()}|x|0|{code}|Stop{code}' for code in codes)
            + '@y|SelectedStop|YYA|selected|y|0|y|SelectedStop@z|End|ZZZ|end|e|0|z|End')
        raw = ticket('AAA','ZZZ','G0',start='08:00',arrive='12:00')
        raw.duration = '04:00'
        anchor = JourneyTrain(**raw.model_dump(),id='selected',
            departure_at=datetime(2026,10,10,8,tzinfo=CST),arrival_at=datetime(2026,10,10,12,tzinfo=CST),
            selection=SelectedTrain(train_no='G0',run_date='2026-10-10',from_station='AAA',to_station='ZZZ',
                departure_at='2026-10-10T08:00:00+08:00'))
        rows = {('AAA','BAA'):[ticket('AAA','BAA','G5',seat='无')],
            ('AAA','YYA'):[ticket('AAA','YYA','G0')],
            ('YYA','BAB'):[ticket('YYA','BAB','G2',start='10:00',arrive='11:00')],
            ('BAB','ZZZ'):[ticket('BAB','ZZZ','G3',start='12:00',arrive='13:00')]}
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs: rows.get((a,b),[]) if day=='2026-10-10' else [])
        def stops(train,*args,**kwargs):
            names = ['Start','SelectedStop','End'] if train=='G0' else ['Start'] + [f'Stop{code}' for code in codes[1:]] + ['StopBAA']
            return [TrainStopInfo(station_no=str(i),station_name=name,arrive_time='--',start_time='--',stopover_time='--')
                for i,name in enumerate(names,1)]
        railway.query_train_stops_strict = Mock(side_effect=stops)
        planner = TransferPlanner(TransferStationService(entries=[],directory=stations),TransferTicketGateway(railway),
            limits={'request_interval':0,'discovery_probes':1},sleep_fn=lambda _:None)
        result = planner.search(self.request(ordered_via_stations=[],transfer_count=2),now=NOW,first_train=anchor)
        self.assertIn('YYA',result.meta.candidate_station_codes)
        self.assertEqual(len(result.plans),1)
        self.assertEqual(result.plans[0].legs[0].train_no,'G0')
        self.assertLessEqual(len(result.meta.candidate_station_codes),32)

    def test_sold_out_trains_still_supply_distinct_stop_candidates(self):
        railway = Ticket12306Client()
        anchors = [ticket('AAA','ZZZ','G1',seat='无'),ticket('AAA','ZZZ','G2',seat='无')]
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs: anchors if (a,b)==('AAA','ZZZ') else [])
        def stops(train,*args,**kwargs):
            middle = 'Middle' if train=='G1' else 'Probe'
            return [TrainStopInfo(station_no=str(i),station_name=name,arrive_time='09:00',
                start_time='09:05',stopover_time='5') for i,name in enumerate(['Start',middle,'End'],1)]
        railway.query_train_stops_strict = Mock(side_effect=stops)
        planner = TransferPlanner(self.stations(),TransferTicketGateway(railway),
            limits={'request_interval':0,'discovery_probes':0},sleep_fn=lambda _:None)
        result = planner.search(self.request(ordered_via_stations=[]),now=NOW)
        self.assertEqual(result.plans,[])
        self.assertEqual(set(result.meta.candidate_station_codes),{'BBB','CCC'})
        self.assertIn('train_stops',result.meta.candidate_sources['BBB'])
        self.assertIn('train_stops',result.meta.candidate_sources['CCC'])

    def test_total_deadline_stops_discovery_before_any_further_network_request(self):
        railway = Ticket12306Client()
        clock = [0]
        def delayed(*args,**kwargs):
            clock[0] = 50
            return [ticket('AAA','ZZZ','G1')]
        railway.query_tickets_strict = Mock(side_effect=delayed)
        railway.query_train_stops_strict = Mock()
        planner = TransferPlanner(self.stations(),TransferTicketGateway(railway),
            limits={'request_interval':0},sleep_fn=lambda _:None)
        with patch('app.services.transfer_planner.time.monotonic',side_effect=lambda:clock[0]):
            result = planner.search(self.request(ordered_via_stations=[]),now=NOW)
        self.assertEqual(result.meta.query_count,1)
        self.assertFalse(railway.query_train_stops_strict.called)
        self.assertIn('time_limit',result.meta.truncation_reasons)

    def wide_search(self, route):
        codes = ['BA'+chr(65+i) for i in range(26)] + ['BBA','BBB','BBC','BBD','BBE','BBF']
        stations = StationService()
        stations._parse_station_text('@a|Start|AAA|start|s|0|a|Start' + ''.join(
            f'@s|Stop{code}|{code}|{code.lower()}|x|0|{code}|Stop{code}' for code in codes)
            + '@z|End|ZZZ|end|e|0|z|End')
        anchor = ticket('AAA','ZZZ','G0',start='08:00',arrive='12:00',seat='无')
        anchor.duration = '04:00'
        rows = {('AAA','ZZZ'):[anchor]}
        for i,(a,b) in enumerate(zip(route,route[1:])):
            hour = 8 + 2*i
            rows[(a,b)] = [ticket(a,b,f'G{i+1}',start=f'{hour:02d}:00',arrive=f'{hour+1:02d}:00')]
        railway = Ticket12306Client()
        railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kwargs: rows.get((a,b),[]) if day=='2026-10-10' else [])
        railway.query_train_stops_strict = Mock(return_value=[TrainStopInfo(station_no=str(i),station_name=name,
            arrive_time='--',start_time='--',stopover_time='--') for i,name in enumerate(
                ['Start'] + [f'Stop{code}' for code in codes] + ['End'],1)])
        planner = TransferPlanner(TransferStationService(entries=[],directory=stations),TransferTicketGateway(railway),
            limits={'request_interval':0,'discovery_probes':0},sleep_fn=lambda _:None)
        return planner.search(self.request(ordered_via_stations=[],transfer_count=len(route)-2),now=NOW)

    def test_wide_candidates_reserve_budget_to_finish_an_already_found_two_transfer_path(self):
        result = self.wide_search(['AAA','BAA','BAB','ZZZ'])
        self.assertEqual(len(result.plans),1)
        self.assertEqual([connection.station.station_code for connection in result.plans[0].connections],['BAA','BAB'])
        self.assertLessEqual(result.meta.query_count,120)

    def test_late_candidate_can_borrow_unused_stage_budget_until_a_path_exists(self):
        result = self.wide_search(['AAA','BBF','BAA','BAB','ZZZ'])
        self.assertEqual(len(result.plans),1)
        self.assertEqual([connection.station.station_code for connection in result.plans[0].connections],['BBF','BAA','BAB'])
        self.assertLessEqual(result.meta.query_count,120)


if __name__ == '__main__':
    unittest.main()
