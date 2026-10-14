"""Exercise fastest journey orchestration through the real ticket gateway/planner."""
import unittest
from unittest.mock import Mock

from app.models.journey_schemas import JourneyQueryRequest
from app.services.client_12306 import Ticket12306Client
from app.services.journey_service import JourneyService
from app.services.smart_planner import SmartRoutePlanner
from app.services.station_service import StationService
from app.services.transfer_planner import TransferPlanner
from app.services.transfer_station_service import TransferStationService
from app.services.transfer_ticket_gateway import TransferTicketGateway
from test_dynamic_transfers import ticket
from test_journey import NOW
from test_transfer_planner import station


class FastestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.stations = StationService()
        self.stations._parse_station_text(
            '@a|上海|AAA|shanghai|sh|0|sh|上海'
            '@b|上海虹桥|AAB|shanghaihongqiao|shhq|0|sh|上海'
            '@m|南京南|BBB|nanjingnan|njn|0|nj|南京'
            '@n|合肥南|DDD|hefeinan|hfn|0|hf|合肥'
            '@z|驻马店|CCC|zhumadian|zmd|0|zmd|驻马店'
            '@x|驻马店西|CCB|zhumadianxi|zmdx|0|zmd|驻马店'
            '@q|确山|QSN|queshan|qs|0|zmd|驻马店')
        self.railway = Ticket12306Client()
        def raw(a, b, code, start, arrive, duration):
            value = ticket(a, b, code, start=start, arrive=arrive)
            value.duration = duration
            return value
        self.rows = {
            ('AAA','CCC'): [raw('AAA','CCC','G99','08:00','13:00','05:00')],
            ('AAA','BBB'): [raw('AAA','BBB','G1','08:00','09:00','01:00')],
            ('AAB','BBB'): [raw('AAB','BBB','G2','18:00','19:00','01:00')],
            ('BBB','CCB'): [raw('BBB','CCB','G3','19:20','20:00','00:40')],
            ('BBB','CCC'): [raw('BBB','CCC','G4','13:30','15:00','01:30')],
            ('AAB','DDD'): [raw('AAB','DDD','G5','17:00','17:30','00:30')],
            ('DDD','BBB'): [raw('DDD','BBB','G6','18:00','18:30','00:30')],
            ('BBB','QSN'): [raw('BBB','QSN','G7','19:15','19:30','00:15')],
        }
        self.railway.query_tickets_strict = Mock(side_effect=lambda day,a,b,**kw:
            self.rows.get((a,b),[]) if day == '2026-10-10' else [])
        self.railway.query_train_stops_strict = Mock(return_value=[])
        refs = TransferStationService(entries=[station('BBB'),station('DDD')],directory=self.stations)
        self.planner = TransferPlanner(refs, TransferTicketGateway(self.railway),
            limits={'request_interval':0,'discovery_probes':0,'discovery_trains':0})
        same = Mock()
        same._times = SmartRoutePlanner._times
        self.service = JourneyService(self.railway,self.stations,same,self.planner)

    def test_fastest_defaults_search_actual_hubs_and_keep_direct_as_comparison(self):
        request = JourneyQueryRequest(from_station='AAA',to_station='CCC',train_date='2026-10-10',
            mode='fastest',max_transfers=2,min_transfer_minutes=15)
        result = self.service.search(request,now=NOW)
        self.assertEqual(result.transfer.plans[0].total_minutes,120)
        self.assertEqual(result.transfer.plans[0].legs[0].from_station,'AAB')
        self.assertEqual(result.transfer.plans[0].legs[-1].to_station,'CCB')
        self.assertEqual({len(p.connections) for p in result.transfer.plans},{1,2})
        self.assertFalse(any(p.legs[-1].to_station == 'QSN' for p in result.transfer.plans))
        self.assertEqual(result.direct.plans[0].total_minutes,300)
        self.assertEqual(result.same_train.meta.status,'skipped')
        self.assertLessEqual(result.transfer.meta.query_count,120)

    def test_single_station_choice_cannot_return_faster_city_alternative(self):
        request = JourneyQueryRequest(from_station='AAA',to_station='CCC',train_date='2026-10-10',
            mode='fastest',from_scope='station',to_scope='station',max_transfers=1,min_transfer_minutes=15)
        result = self.service.search(request,now=NOW)
        self.assertEqual(result.transfer.plans[0].total_minutes,420)
        self.assertTrue(all(p.legs[0].from_station=='AAA' and p.legs[-1].to_station=='CCC'
            for p in result.transfer.plans))


if __name__ == '__main__':
    unittest.main()
